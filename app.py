import os
from datetime import datetime
from pathlib import Path

import pyodbc
import numpy as np
import pandas as pd
from dotenv import load_dotenv
import geopandas


load_dotenv()


DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_TRUSTED_CONNECTION = os.getenv("DB_TRUSTED_CONNECTION", "yes")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_TRUST_SERVER_CERTIFICATE = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")


def conect():
    if not DB_SERVER:
        raise ValueError("DB_SERVER não foi encontrado no .env")

    if not DB_DATABASE:
        raise ValueError("DB_DATABASE não foi encontrado no .env")

    conn_str = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        f"TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE};"
    )

    if DB_TRUSTED_CONNECTION.lower() == "yes":
        conn_str += "Trusted_Connection=yes;"
    else:
        if not DB_USER or not DB_PASSWORD:
            raise ValueError(
                "DB_USER e DB_PASSWORD são obrigatórios quando DB_TRUSTED_CONNECTION não é yes"
            )

        conn_str += (
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
        )

    return pyodbc.connect(conn_str)


def extract(caminho_sql, params=None):
    caminho_sql = Path(caminho_sql)

    if not caminho_sql.exists():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {caminho_sql}")

    query = caminho_sql.read_text(encoding="utf-8")

    conn = conect()

    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    finally:
        conn.close()


def classificar_motivo(pares):
    mesma_fazenda = pares["Fazenda1"] == pares["Fazenda2"]
    mesmo_talhao = pares["Talhao1"] == pares["Talhao2"]
    mesmo_nome_fazenda = pares["NomeFazenda_1"] == pares["NomeFazenda_2"]
    quase_identico = pares["PercentualSobreposicaoGeral"] > 90

    condicoes = [
        mesma_fazenda & mesmo_talhao,
        mesmo_nome_fazenda & ~mesma_fazenda,
        mesma_fazenda & quase_identico,
        mesma_fazenda,
    ]
    motivos = [
        "Mesmo talhão físico (ciclo/safra anterior não foi fechado)",
        "Fazenda cadastrada com código duplicado",
        "Códigos de talhão diferentes quase 100% sobrepostos",
        "Talhões vizinhos com sobreposição parcial de limite",
    ]
    return np.select(condicoes, motivos, default="Fazendas diferentes com sobreposição de limite")


def intersect(df):
    """Retorna os pares de talhões cuja área realmente se sobrepõe (contato
    apenas na borda, sem área/linha em comum, é descartado), já com o
    percentual de sobreposição de cada talhão e da área conjunta.

    É o equivalente em Python do self join com bounding box + STIntersects/
    STIntersection/STUnion feito em SQL: em vez do bbox manual, usa o índice
    espacial do GeoPandas (sjoin) pra achar candidatos, e só depois calcula
    área/interseção/união apenas para esses candidatos — por isso é bem mais
    leve que rodar a query pesada direto no banco."""
    gdf = geopandas.GeoDataFrame(
        df.drop(columns=["DadosSHP"]),
        # o SQL já manda a geometria em binário (STAsBinary/WKB) em vez de texto
        # (STAsText/WKT): é bem mais compacto de trafegar e muito mais rápido de
        # parsear (WKB não precisa converter cada coordenada de texto pra float)
        geometry=geopandas.GeoSeries.from_wkb(df["DadosSHP"]),
    ).reset_index().rename(columns={"index": "id_geom"})

    pares = geopandas.sjoin(gdf, gdf, predicate="intersects", lsuffix="1", rsuffix="2")

    # remove o cruzamento de uma geometria com ela mesma e os pares
    # duplicados (A x B e B x A)
    pares = pares[pares["id_geom_1"] < pares["id_geom_2"]]

    geom_por_id = gdf.set_index("id_geom").geometry
    geom_1 = geom_por_id.loc[pares["id_geom_1"]].reset_index(drop=True)
    geom_2 = geom_por_id.loc[pares["id_geom_2"]].reset_index(drop=True)

    # remove contato que é só "encostar" na borda, sem sobreposição real
    tem_sobreposicao_real = ~geom_1.touches(geom_2).to_numpy()
    pares = pares[tem_sobreposicao_real].reset_index(drop=True)
    geom_1 = geom_1[tem_sobreposicao_real].reset_index(drop=True)
    geom_2 = geom_2[tem_sobreposicao_real].reset_index(drop=True)

    # equivalente ao STIntersection(...).STArea() / STUnion(...).STArea() do SQL
    area_1 = geom_1.area
    area_2 = geom_2.area
    area_intersecao = geom_1.intersection(geom_2).area
    area_uniao = (area_1 + area_2 - area_intersecao).replace(0, float("nan"))

    pares["PercentualSobreposto1"] = area_intersecao / area_1 * 100
    pares["PercentualSobreposto2"] = area_intersecao / area_2 * 100
    pares["PercentualSobreposicaoGeral"] = area_intersecao / area_uniao * 100

    # equivalente ao WHERE PercentualSobreposicaoGeral <> 0.00 and > 0.20 do SQL
    pares = pares[pares["PercentualSobreposicaoGeral"] > 1.0]

    # geometria de cada talhão (formato GeoJSON), pra desenhar as duas
    # geometrias na tela quando o usuário selecionar um par na interface.
    # usa lista (não .apply numa GeoSeries) de propósito: o resultado é um
    # dict comum (__geo_interface__), e o geopandas às vezes reconhece esses
    # dicts como geometria de verdade quando atribuídos via GeoSeries.apply,
    # o que quebra to_json() depois achando que ainda tem uma coluna de
    # geometria ativa.
    pares["Geometria1"] = [g.__geo_interface__ for g in geom_1.loc[pares.index]]
    pares["Geometria2"] = [g.__geo_interface__ for g in geom_2.loc[pares.index]]

    colunas = {
        "AnoSafra_1": "AnoSafra1", "AnoSafra_2": "AnoSafra2",
        "fazenda_1": "Fazenda1", "fazenda_2": "Fazenda2",
        "Bloco_1": "Bloco1", "Bloco_2": "Bloco2",
        "Talhao_1": "Talhao1", "Talhao_2": "Talhao2",
        "Corte_1": "Corte1", "Corte_2": "Corte2",
        "IDTalhao_1": "IDTalhao1", "IDTalhao_2": "IDTalhao2",
        "RazaoSocial_1": "Usina1", "RazaoSocial_2": "Usina2",
        "Reforma_1": "Reforma1", "Reforma_2": "Reforma2",
        "TomboSafra_1": "TomboSafra1", "TomboSafra_2": "TomboSafra2",
        "DataColheita_1": "DataColheita1", "DataColheita_2": "DataColheita2",
        "DataPlantio_1": "DataPlantio1", "DataPlantio_2": "DataPlantio2",
        "SiglaExterna_1": "SiglaExterna1", "SiglaExterna_2": "SiglaExterna2",
    }
    pares = pares.rename(columns=colunas)
    pares["Motivo"] = classificar_motivo(pares)
    colunas_finais = list(colunas.values()) + [
        "PercentualSobreposicaoGeral", "Motivo", "Geometria1", "Geometria2",
    ]
    pares = pares[colunas_finais].sort_values(["Fazenda1", "Bloco1", "Talhao1"]).reset_index(drop=True)

    return pares


def salvar_excel(pares, pasta_saida="output"):
    """Salva os pares de talhões duplicados/sobrepostos em um arquivo Excel."""
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_arquivo = pasta_saida / f"geometrias_duplicadas_{timestamp}.xlsx"

    # as colunas de geometria (GeoJSON) são só pra tela; não fazem sentido numa célula do Excel
    colunas_geometria = ["Geometria1", "Geometria2"]
    pares_para_excel = pares.drop(columns=colunas_geometria, errors="ignore")
    pares_para_excel.to_excel(caminho_arquivo, index=False, sheet_name="Duplicados")

    return caminho_arquivo


def main():
    print("Iniciando consulta...")
    df = extract(Path("Queries") / "geometrias.sql")
    print(df)

    pares = intersect(df)
    print(f"{len(pares)} par(es) de talhões com sobreposição de área > 0,20% encontrados")
    print(pares)

    caminho_arquivo = salvar_excel(pares)
    print(f"Arquivo salvo em: {caminho_arquivo}")


if __name__ == "__main__":
    main()