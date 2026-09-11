from datetime import datetime
from pathlib import Path

import numpy as np
import geopandas


def classificar_motivo(pares):
    """`pares` precisa ter `PercentualSobreposto1`/`PercentualSobreposto2`
    (percentual de cada talhão individualmente, além do geral) — `intersect()`
    já calcula os dois antes de chamar esta função."""
    mesma_fazenda = pares["Fazenda1"] == pares["Fazenda2"]
    mesmo_talhao = pares["Talhao1"] == pares["Talhao2"]
    mesmo_nome_fazenda = pares["NomeFazenda_1"] == pares["NomeFazenda_2"]
    quase_identico = pares["PercentualSobreposicaoGeral"] > 90

    # um dos talhões está quase inteiro dentro do outro (>90% da área DELE,
    # não da união) — sinal de subdivisão (ex.: sub-talhão registrado dentro
    # do maior), não erro de limite entre vizinhos. Confirmado em dados reais
    # (Atvos).
    contido = (pares["PercentualSobreposto1"] > 90) | (pares["PercentualSobreposto2"] > 90)

    condicoes = [
        mesma_fazenda & mesmo_talhao,
        mesmo_nome_fazenda & ~mesma_fazenda,
        mesma_fazenda & quase_identico,
        mesma_fazenda & contido,
        mesma_fazenda,
    ]
    motivos = [
        "Mesmo talhão físico (ciclo/safra anterior não foi fechado)",
        "Fazenda cadastrada com código duplicado",
        "Códigos de talhão diferentes quase 100% sobrepostos",
        "Provável subdivisão — área menor contida dentro do talhão maior",
        "Talhões vizinhos com sobreposição parcial de limite",
    ]
    return np.select(condicoes, motivos, default="Fazendas diferentes com sobreposição de limite")


def intersect(df):
    """Retorna os pares de talhões cuja área realmente se sobrepõe (contato só
    na borda é descartado), com o percentual de sobreposição de cada talhão
    e da área conjunta. Equivale ao self join com bbox + STIntersects/
    STIntersection/STUnion do SQL, mas usa o índice espacial do GeoPandas
    (sjoin) pra achar candidatos antes de calcular área — mais leve."""
    gdf = geopandas.GeoDataFrame(
        df.drop(columns=["DadosSHP"]),
        # geometria vem em WKB (STAsBinary), não WKT: mais compacto e rápido de parsear
        geometry=geopandas.GeoSeries.from_wkb(df["DadosSHP"]),
    ).reset_index().rename(columns={"index": "id_geom"})

    pares = geopandas.sjoin(gdf, gdf, predicate="intersects", lsuffix="1", rsuffix="2")

    # remove auto-cruzamento e pares duplicados (A×B e B×A)
    pares = pares[pares["id_geom_1"] < pares["id_geom_2"]]

    geom_por_id = gdf.set_index("id_geom").geometry
    geom_1 = geom_por_id.loc[pares["id_geom_1"]].reset_index(drop=True)
    geom_2 = geom_por_id.loc[pares["id_geom_2"]].reset_index(drop=True)

    # remove contato só na borda, sem sobreposição real
    tem_sobreposicao_real = ~geom_1.touches(geom_2).to_numpy()
    pares = pares[tem_sobreposicao_real].reset_index(drop=True)
    geom_1 = geom_1[tem_sobreposicao_real].reset_index(drop=True)
    geom_2 = geom_2[tem_sobreposicao_real].reset_index(drop=True)

    # equivale a STIntersection(...).STArea() / STUnion(...).STArea() do SQL
    area_1 = geom_1.area
    area_2 = geom_2.area
    area_intersecao = geom_1.intersection(geom_2).area
    area_uniao = (area_1 + area_2 - area_intersecao).replace(0, float("nan"))

    pares["PercentualSobreposto1"] = area_intersecao / area_1 * 100
    pares["PercentualSobreposto2"] = area_intersecao / area_2 * 100
    pares["PercentualSobreposicaoGeral"] = area_intersecao / area_uniao * 100

    # equivale a WHERE PercentualSobreposicaoGeral <> 0.00 and > 0.20 do SQL
    pares = pares[pares["PercentualSobreposicaoGeral"] > 1.0]

    # geometria de cada talhão (GeoJSON), pra desenhar na tela. Usa lista, não
    # .apply numa GeoSeries: senão o geopandas confunde o dict com geometria
    # de verdade e quebra o to_json() depois.
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

    # colunas de geometria são só pra tela; não cabem numa célula do Excel
    colunas_geometria = ["Geometria1", "Geometria2"]
    pares_para_excel = pares.drop(columns=colunas_geometria, errors="ignore")
    pares_para_excel.to_excel(caminho_arquivo, index=False, sheet_name="Duplicados")

    return caminho_arquivo
