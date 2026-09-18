"""API que serve o cache de geometrias duplicadas (cache/<cliente>.json,
gerado por smartbio_cache.py via MCP smartbio) para o front React. Não
recalcula nada nem acessa o smartbio diretamente.

Rodar com:
    uvicorn api:app --reload --port 8001
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from email_utils import enviar_email
from smartbio_cache import CACHE_DIR, CLIENTES, OUTPUT_DIR

app = FastAPI(title="Data Quality Monitor - Geometrias Duplicadas")

# permite chamadas do front local (Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _carregar_cache(cliente: str) -> dict:
    caminho = CACHE_DIR / f"{cliente}.json"
    if not caminho.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum dado ainda para '{cliente}'. Peça pro Claude Code rodar "
                f"'smartbio_cache.py {cliente}' com uma extração fresca do smartbio."
            ),
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def _ultimo_excel(cliente: str) -> Optional[Path]:
    candidatos = sorted(OUTPUT_DIR.glob(f"{cliente}_duplicados_*.xlsx"))
    return candidatos[-1] if candidatos else None


def _gerar_excel_multi_aba(clientes: list[str]) -> Path:
    """Monta um Excel com uma aba por cliente, pra anexar num único e-mail."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = OUTPUT_DIR / f"multiplos_clientes_{timestamp}.xlsx"

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for cliente in clientes:
            dados = _carregar_cache(cliente)
            df = pd.DataFrame(dados["itens"]).drop(
                columns=["id", "Geometria1", "Geometria2"], errors="ignore"
            )
            # aba do Excel: máx. 31 caracteres
            df.to_excel(writer, sheet_name=cliente[:31], index=False)

    return caminho


def _bate_filtro(item: dict, fazenda, usina, safra, talhao, percentual_minimo) -> bool:
    if fazenda:
        alvo = fazenda.lower()
        if alvo not in str(item.get("Fazenda1", "")).lower() and alvo not in str(item.get("Fazenda2", "")).lower():
            return False
    if talhao:
        alvo = talhao.lower()
        if alvo not in str(item.get("Talhao1", "")).lower() and alvo not in str(item.get("Talhao2", "")).lower():
            return False
    if usina:
        alvo = usina.lower()
        if alvo not in str(item.get("Usina1", "")).lower() and alvo not in str(item.get("Usina2", "")).lower():
            return False
    if safra:
        alvo = safra.lower()
        if alvo not in str(item.get("AnoSafra1", "")).lower() and alvo not in str(item.get("AnoSafra2", "")).lower():
            return False
    if percentual_minimo is not None:
        if (item.get("PercentualSobreposicaoGeral") or 0) < percentual_minimo:
            return False
    return True


@app.get("/api/clientes")
def listar_clientes():
    """Lista clientes com a data do último cache (None se nunca extraído)."""
    itens = []
    for cliente in CLIENTES:
        caminho = CACHE_DIR / f"{cliente}.json"
        if caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            itens.append({
                "cliente": cliente,
                "total": dados["total"],
                "gerado_em": dados["gerado_em"],
            })
        else:
            itens.append({"cliente": cliente, "total": None, "gerado_em": None})
    return {"itens": itens}


@app.post("/api/pipeline/rodar")
def rodar_pipeline(cliente: str):
    """Não recalcula — só confirma que existe cache e devolve a data de geração."""
    dados = _carregar_cache(cliente)
    return {"total": dados["total"], "ultima_execucao": dados["gerado_em"]}


@app.get("/api/duplicados")
def listar_duplicados(
    cliente: str,
    fazenda: Optional[str] = None,
    usina: Optional[str] = None,
    safra: Optional[str] = None,
    talhao: Optional[str] = None,
    percentual_minimo: Optional[float] = None,
):
    """Lista os pares do cache do cliente, com filtros opcionais."""
    dados = _carregar_cache(cliente)
    itens = [i for i in dados["itens"] if _bate_filtro(i, fazenda, usina, safra, talhao, percentual_minimo)]

    # sem geometria: o desenho é buscado sob demanda em /geometria
    itens_lista = [
        {k: v for k, v in item.items() if k not in ("Geometria1", "Geometria2")}
        for item in itens
    ]

    return {
        "total": len(itens),
        "ultima_execucao": dados["gerado_em"],
        "itens": itens_lista,
    }


@app.get("/api/duplicados/{par_id}/geometria")
def obter_geometria(par_id: int, cliente: str):
    """Retorna a geometria (GeoJSON) dos dois talhões de um par."""
    dados = _carregar_cache(cliente)
    for item in dados["itens"]:
        if item["id"] == par_id:
            return {"geometria1": item["Geometria1"], "geometria2": item["Geometria2"]}

    raise HTTPException(status_code=404, detail="Par não encontrado.")


@app.get("/api/duplicados/excel")
def baixar_excel(cliente: str):
    """Retorna o último Excel gerado pra esse cliente."""
    arquivo = _ultimo_excel(cliente)
    if not arquivo:
        raise HTTPException(status_code=404, detail=f"Nenhum arquivo gerado ainda pra '{cliente}'.")

    return FileResponse(
        arquivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=arquivo.name,
    )


@app.post("/api/duplicados/email")
def enviar_por_email(clientes: List[str] = Query(...)):
    """Envia por e-mail os dados dos clientes selecionados: um só anexa o
    Excel já gerado; mais de um monta um Excel com uma aba por cliente."""
    for cliente in clientes:
        _carregar_cache(cliente)  # 404 cedo se faltar dado

    if len(clientes) == 1:
        arquivo = _ultimo_excel(clientes[0])
        if not arquivo:
            raise HTTPException(status_code=404, detail=f"Nenhum arquivo gerado ainda pra '{clientes[0]}'.")
    else:
        arquivo = _gerar_excel_multi_aba(clientes)

    try:
        enviar_email(arquivo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"enviado": True, "arquivo": arquivo.name}
