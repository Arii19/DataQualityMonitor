"""Gera o cache de sobreposições de geometria a partir de CSVs extraídos do
smartbio (MCP), um cliente por vez — só uma sessão do Claude com MCP
consegue consultar o smartbio; api.py não tem essa credencial.

Fluxo: Claude extrai vw_bree_full.CadastroDeAreas+Geometria via MCP para
raw/<cliente>/*.csv -> este script calcula sobreposições (lógica de
app.py.intersect/classificar_motivo) e grava cache/<cliente>.json +
output/<cliente>_duplicados.xlsx -> api.py serve do cache, sem tocar no
smartbio/SQL Server.

Rodar sozinho: `python smartbio_cache.py <Cliente> [<raw_dir>]` ou sem
argumentos pra processar todos os clientes com pasta em raw/.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas
import numpy as np
import pandas as pd
from shapely import wkb
from shapely.geometry import shape

from app import classificar_motivo

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

CLIENTES = ["Atvos", "SantaAdelia", "Cevasa", "CMAA", "Guaira", "GQQ", "JPA", "Cocal", "IPE"]

# Histórico: vw_bree_full.Geometria não amarrava geometria por safra (ver
# docs/especificacao_view_geometria_por_safra.md). _filtrar_geometria_suspeita()
# comparava AreaTotal x área do GeoJson como mitigação, mas causava falso
# negativo (GQQ, talhão 758). Com o join IDTalhao+IDSafra corrigido na
# extração, a mitigação ficou desnecessária — desativada de propósito, assim
# como _filtrar_por_safra_ativa() logo abaixo.


# caracteres de controle que o Excel/openpyxl recusam em célula de texto —
# já apareceu em NomeFazenda vindo do smartbio (dado sujo na origem).
_CARACTERES_ILEGAIS_EXCEL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitizar_para_excel(df):
    df = df.copy()
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, str)).any():
            df[col] = df[col].map(
                lambda v: _CARACTERES_ILEGAIS_EXCEL.sub("", v) if isinstance(v, str) else v
            )
    return df


def _parse_geojson(valor):
    """Aceita GeoJSON de texto (extração normal) ou WKB em hex (extração via
    Queries/geometria_correta_por_safra.sql, já que o SQL Server não tem
    STAsGeoJSON()).

    Desde 2026-09-10 a coluna GeoJson vem embrulhada num objeto Feature
    (`{"type":"Feature","geometry":{...}}`) em vez da geometria pura —
    mudança do lado do smartbio. shape() só entende geometria pura, então
    desembrulha o Feature antes de passar pra ele."""
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    if texto and all(c in "0123456789abcdefABCDEF" for c in texto) and len(texto) % 2 == 0:
        try:
            return wkb.loads(bytes.fromhex(texto))
        except Exception:
            return None
    try:
        dado = json.loads(valor)
        if isinstance(dado, dict) and str(dado.get("type", "")).lower() == "feature":
            dado = dado.get("geometry")
        return shape(dado)
    except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
        return None


def _filtrar_por_safra_ativa(df):
    """DESATIVADA — devolve df intacto (mantida só pra não quebrar a
    assinatura usada em carregar_bruto).

    Tentativa anterior: comparar idSafra com a moda do lote pra achar
    geometria de safra errada. Insegura em geral — Cocal e GQQ têm duas
    populações de idSafra legitimamente ativas em paralelo (cortes/ciclos
    diferentes), então a moda excluiria talhões ativos de verdade (ex.:
    talhão 6027 do GQQ, confirmado ativo no banco). Precisaria do join
    estrito por HistDetalhado (só com acesso direto ao banco, ver
    Queries/geometria_correta_por_safra.sql). Retorna (df, vazio) até existir
    um critério seguro."""
    return df, df.iloc[0:0].copy()


def _filtrar_geometria_suspeita(df):
    """DESATIVADA — devolve (df, vazio, vazio) (mantida só pra não quebrar a
    assinatura usada em carregar_bruto).

    Comparava área do GeoJson com AreaTotal oficial pra achar geometria de
    outra safra/corte, mitigando o problema descrito em
    _filtrar_por_safra_ativa(). Causava falso negativo (GQQ, talhão 758:
    AreaTotal=0 mas duplicidade real). Com o join IDTalhao+IDSafra corrigido
    na extração, ficou redundante e só arriscada — desativada."""
    return df, df.iloc[0:0].copy(), df.iloc[0:0].copy()


def carregar_bruto(pasta_cliente, cliente=None):
    """Lê todos os CSVs extraídos do smartbio pra um cliente (pode ser mais de um arquivo)."""
    pasta_cliente = Path(pasta_cliente)
    cliente = cliente or pasta_cliente.name
    arquivos = sorted(pasta_cliente.glob("*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum CSV encontrado em {pasta_cliente}")

    df = pd.concat(
        (pd.read_csv(a, dtype=str, keep_default_na=False, na_values=[""]) for a in arquivos),
        ignore_index=True,
    )
    df = df.drop(columns=["_cliente"], errors="ignore")

    # A extração via MCP já veio (10/09) com linhas duplicadas literalmente
    # (mesmo IDTalhao/Corte/Safra/GeoJson), provável fan-out em
    # CadastroDeAreas — não filtrar isso infla a contagem de pares (chegou a
    # inflar a Atvos de ~300 pra 17 mil "pares"). Descarta linhas 100%
    # idênticas em todas as colunas, geometria inclusa.
    antes = len(df)
    df = df.drop_duplicates(ignore_index=True)
    duplicadas = antes - len(df)
    if duplicadas:
        print(f"  {duplicadas} linha(s) duplicada(s) por completo (mesmo IDTalhao/Corte/Safra/GeoJson) descartada(s) da extração")

    df["IDTalhao"] = pd.to_numeric(df["IDTalhao"], errors="coerce").astype("Int64")
    df["Corte"] = pd.to_numeric(df["Corte"], errors="coerce")
    df["Safra"] = pd.to_numeric(df["Safra"], errors="coerce")
    df["AreaTotal"] = pd.to_numeric(df["AreaTotal"], errors="coerce")

    df["geometry"] = df["GeoJson"].apply(_parse_geojson)
    invalidas = df["geometry"].isna().sum()
    if invalidas:
        print(f"  {invalidas} geometria(s) inválida(s)/vazia(s) descartada(s)")
    df = df[df["geometry"].notna()].reset_index(drop=True)

    df, outra_safra = _filtrar_por_safra_ativa(df)
    if len(outra_safra):
        print(
            f"  {len(outra_safra)} talhão(ões) com geometria de safra diferente da "
            f"ativa (idSafra não bate com a moda do lote) descartado(s) do cálculo"
        )

    df, excluidos, sinalizados = _filtrar_geometria_suspeita(df)
    if len(excluidos):
        print(
            f"  {len(excluidos)} talhão(ões) com geometria de outra safra/corte "
            f"(divergência grande com a AreaTotal oficial) descartado(s) do cálculo"
        )
    if len(sinalizados):
        print(
            f"  {len(sinalizados)} talhão(ões) com AreaTotal oficial zerada mas com "
            f"desenho — mantido(s) no cálculo, mas sinalizado(s) pra revisão manual"
        )
    if len(outra_safra) or len(excluidos) or len(sinalizados):
        colunas_relatorio = [
            c for c in ["IDTalhao", "CodigoFazenda", "NomeFazenda", "Bloco", "CodigoTalhao",
                        "Corte", "Safra", "idSafra", "AreaTotal", "AreaCalculadaHa", "NomeUsina_Empresa_Unidade"]
            if c in df.columns or c in outra_safra.columns
        ]
        relatorio = pd.concat([
            outra_safra.reindex(columns=colunas_relatorio).assign(Situacao="Excluído do cálculo (idSafra diferente da ativa)"),
            excluidos.reindex(columns=colunas_relatorio).assign(Situacao="Excluído do cálculo (divergência de área)"),
            sinalizados.reindex(columns=colunas_relatorio).assign(Situacao="Sinalizado — revisar manualmente (AreaTotal zerada)"),
        ], ignore_index=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _sanitizar_para_excel(relatorio).to_excel(OUTPUT_DIR / f"{cliente}_geometria_suspeita.xlsx", index=False)
        print(f"  ver output/{cliente}_geometria_suspeita.xlsx")

    return df


def calcular_sobreposicoes(df, cliente):
    """Mesma lógica de app.py.intersect(), adaptada pras colunas do smartbio
    (CadastroDeAreas usa código de fazenda/talhão). `cliente` só entra como
    coluna no resultado, pra identificar a origem no Excel multi-cliente."""
    gdf = geopandas.GeoDataFrame(
        df.drop(columns=["GeoJson"]), geometry="geometry"
    ).reset_index().rename(columns={"index": "id_geom"})

    pares = geopandas.sjoin(gdf, gdf, predicate="intersects", lsuffix="1", rsuffix="2")
    pares = pares[pares["id_geom_1"] < pares["id_geom_2"]]

    geom_por_id = gdf.set_index("id_geom").geometry
    geom_1 = geom_por_id.loc[pares["id_geom_1"]].reset_index(drop=True)
    geom_2 = geom_por_id.loc[pares["id_geom_2"]].reset_index(drop=True)

    tem_sobreposicao_real = ~geom_1.touches(geom_2).to_numpy()
    pares = pares[tem_sobreposicao_real].reset_index(drop=True)
    geom_1 = geom_1[tem_sobreposicao_real].reset_index(drop=True)
    geom_2 = geom_2[tem_sobreposicao_real].reset_index(drop=True)

    area_1 = geom_1.area
    area_2 = geom_2.area
    area_intersecao = geom_1.intersection(geom_2).area
    area_uniao = (area_1 + area_2 - area_intersecao).replace(0, float("nan"))

    pares["PercentualSobreposto1"] = area_intersecao / area_1 * 100
    pares["PercentualSobreposto2"] = area_intersecao / area_2 * 100
    pares["PercentualSobreposicaoGeral"] = area_intersecao / area_uniao * 100

    # mesmo filtro de app.py.intersect(). NÃO faz .reset_index(drop=True)
    # aqui: pares precisa manter os rótulos antigos de geom_1/geom_2 pro
    # .loc[pares.index] logo abaixo — resetar já causou geometria trocada
    # entre talhões (ver histórico).
    pares = pares[pares["PercentualSobreposicaoGeral"] > 1.0]

    # lista, não .apply numa GeoSeries: ver app.py.intersect()
    pares["Geometria1"] = [g.__geo_interface__ for g in geom_1.loc[pares.index]]
    pares["Geometria2"] = [g.__geo_interface__ for g in geom_2.loc[pares.index]]

    colunas = {
        "Safra_1": "AnoSafra1", "Safra_2": "AnoSafra2",
        "CodigoFazenda_1": "Fazenda1", "CodigoFazenda_2": "Fazenda2",
        "Bloco_1": "Bloco1", "Bloco_2": "Bloco2",
        "CodigoTalhao_1": "Talhao1", "CodigoTalhao_2": "Talhao2",
        "Corte_1": "Corte1", "Corte_2": "Corte2",
        "IDTalhao_1": "IDTalhao1", "IDTalhao_2": "IDTalhao2",
        "NomeUsina_Empresa_Unidade_1": "Usina1", "NomeUsina_Empresa_Unidade_2": "Usina2",
        "Reforma_1": "Reforma1", "Reforma_2": "Reforma2",
    }
    pares = pares.rename(columns=colunas)
    # classificar_motivo espera Fazenda1/2, Talhao1/2, PercentualSobreposicaoGeral
    # (renomeados), PercentualSobreposto1/2 e NomeFazenda_1/2 (não renomeados).
    pares["Motivo"] = classificar_motivo(pares)
    pares["Cliente"] = cliente

    colunas_finais = ["Cliente"] + list(colunas.values()) + [
        "PercentualSobreposicaoGeral", "Motivo", "Geometria1", "Geometria2",
    ]
    pares = pares[colunas_finais].sort_values(
        ["Fazenda1", "Bloco1", "Talhao1"]
    ).reset_index(drop=True)

    return pares


def salvar_cache(cliente, pares):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # DataFrame comum (não GeoDataFrame): garante que to_json() serialize
    # Geometria1/2 como dict comum, não como geometria ativa.
    pares_planas = pd.DataFrame(pares).reset_index().rename(columns={"index": "id"})
    payload = {
        "cliente": cliente,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "total": len(pares),
        "itens": json.loads(pares_planas.to_json(orient="records")),
    }
    (CACHE_DIR / f"{cliente}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_excel = OUTPUT_DIR / f"{cliente}_duplicados_{timestamp}.xlsx"
    _sanitizar_para_excel(pares.drop(columns=["Geometria1", "Geometria2"], errors="ignore")).to_excel(
        caminho_excel, index=False, sheet_name="Duplicados"
    )

    return caminho_excel


def processar_cliente(cliente, pasta_raw=None):
    pasta_raw = Path(pasta_raw) if pasta_raw else RAW_DIR / cliente
    print(f"[{cliente}] lendo CSVs de {pasta_raw}...")
    df = carregar_bruto(pasta_raw, cliente=cliente)
    print(f"[{cliente}] {len(df)} talhões válidos, calculando sobreposições...")
    pares = calcular_sobreposicoes(df, cliente)
    caminho_excel = salvar_cache(cliente, pares)
    print(f"[{cliente}] {len(pares)} par(es) sobreposto(s) -> cache/{cliente}.json e {caminho_excel}")
    return pares


def main():
    if len(sys.argv) > 1:
        cliente = sys.argv[1]
        pasta_raw = sys.argv[2] if len(sys.argv) > 2 else None
        processar_cliente(cliente, pasta_raw)
        return

    for cliente in CLIENTES:
        pasta_raw = RAW_DIR / cliente
        if not pasta_raw.exists():
            print(f"[{cliente}] sem dados brutos em {pasta_raw}, pulando")
            continue
        processar_cliente(cliente)


if __name__ == "__main__":
    main()
