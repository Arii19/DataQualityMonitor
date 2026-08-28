"""API que expõe o pipeline de geometrias duplicadas para a interface React.

Rodar com:
    uvicorn api:app --reload
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import extract, intersect, salvar_excel

app = FastAPI(title="Data Quality Monitor - Geometrias Duplicadas")

# libera o front-end local (Vite) a chamar essa API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# cache em memória do último resultado calculado, pra não bater no banco
# a cada filtro/atualização de tela
_cache = {"pares": None, "ultima_execucao": None, "ultimo_arquivo": None}


def _dataframe_para_registros(df):
    """Converte o DataFrame pra lista de dicts JSON-safe (NaN/NaT viram null,
    datas viram string ISO) usando o próprio serializador do pandas."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _rodar_pipeline():
    df = extract(Path("Queries") / "geometrias.sql")
    pares = intersect(df)
    arquivo = salvar_excel(pares)

    _cache["pares"] = pares
    _cache["ultima_execucao"] = datetime.now().isoformat()
    _cache["ultimo_arquivo"] = arquivo

    return pares


@app.post("/api/pipeline/rodar")
def rodar_pipeline():
    """Executa a consulta + cálculo de sobreposição e atualiza o cache."""
    try:
        pares = _rodar_pipeline()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"total": len(pares), "ultima_execucao": _cache["ultima_execucao"]}


@app.get("/api/duplicados")
def listar_duplicados(
    fazenda: Optional[str] = None,
    usina: Optional[str] = None,
    safra: Optional[str] = None,
    percentual_minimo: Optional[float] = None,
):
    """Lista os pares já calculados, com filtros opcionais."""
    if _cache["pares"] is None:
        raise HTTPException(
            status_code=404,
            detail="Nenhum resultado calculado ainda. Rode o pipeline primeiro.",
        )

    pares = _cache["pares"]

    if fazenda:
        pares = pares[
            pares["Fazenda1"].astype(str).str.contains(fazenda, case=False, na=False)
            | pares["Fazenda2"].astype(str).str.contains(fazenda, case=False, na=False)
        ]
    if usina:
        pares = pares[
            pares["Usina1"].astype(str).str.contains(usina, case=False, na=False)
            | pares["Usina2"].astype(str).str.contains(usina, case=False, na=False)
        ]
    if safra:
        pares = pares[
            pares["AnoSafra1"].astype(str).str.contains(safra, case=False, na=False)
            | pares["AnoSafra2"].astype(str).str.contains(safra, case=False, na=False)
        ]
    if percentual_minimo is not None:
        pares = pares[pares["PercentualSobreposicaoGeral"] >= percentual_minimo]

    # a lista fica leve (sem geometria) — o desenho de cada par só é buscado
    # sob demanda em /api/duplicados/{id}/geometria quando o usuário clica na linha
    pares_lista = (
        pares.drop(columns=["Geometria1", "Geometria2"], errors="ignore")
        .reset_index()
        .rename(columns={"index": "id"})
    )

    return {
        "total": len(pares),
        "ultima_execucao": _cache["ultima_execucao"],
        "itens": _dataframe_para_registros(pares_lista),
    }


@app.get("/api/duplicados/{par_id}/geometria")
def obter_geometria(par_id: int):
    """Retorna a geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela."""
    if _cache["pares"] is None:
        raise HTTPException(
            status_code=404,
            detail="Nenhum resultado calculado ainda. Rode o pipeline primeiro.",
        )

    pares = _cache["pares"]
    if par_id not in pares.index:
        raise HTTPException(status_code=404, detail="Par não encontrado.")

    linha = pares.loc[par_id]
    return {
        "geometria1": linha["Geometria1"],
        "geometria2": linha["Geometria2"],
    }


@app.get("/api/duplicados/excel")
def baixar_excel():
    """Retorna pra download o último Excel gerado pelo pipeline."""
    arquivo = _cache["ultimo_arquivo"]
    if not arquivo or not Path(arquivo).exists():
        raise HTTPException(
            status_code=404,
            detail="Nenhum arquivo gerado ainda. Rode o pipeline primeiro.",
        )

    return FileResponse(
        arquivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=Path(arquivo).name,
    )
