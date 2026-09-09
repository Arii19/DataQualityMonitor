"""API que expõe o pipeline de geometrias duplicadas para a interface React.

Os dados não vêm mais de um SQL Server acessado direto por pyodbc: os 9
clientes vivem no smartbio, que só uma sessão do Claude com o MCP consegue
consultar — este backend, rodando sozinho via uvicorn, não tem essa
credencial. Por isso ele serve os dados de cache/<cliente>.json, gerado por
smartbio_cache.py sempre que alguém pede pro Claude "atualizar o cliente X".
Não existe cálculo ao vivo aqui: "rodar pipeline" apenas relê o cache do
disco, e a tela mostra a data em que aquele cache foi gerado.

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
from managervision_pdf import exportar_varios_pdf
from smartbio_cache import CACHE_DIR, CLIENTES, OUTPUT_DIR

app = FastAPI(title="Data Quality Monitor - Geometrias Duplicadas")

# libera o front-end local (Vite) a chamar essa API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


MANAGERVISION_CACHE_DIR = CACHE_DIR / "managervision"


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
    """Monta um único Excel com uma aba por cliente (a partir do cache atual
    de cada um), pra anexar num e-mail com vários clientes selecionados sem
    virar um anexo por cliente."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = OUTPUT_DIR / f"multiplos_clientes_{timestamp}.xlsx"

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for cliente in clientes:
            dados = _carregar_cache(cliente)
            df = pd.DataFrame(dados["itens"]).drop(
                columns=["id", "Geometria1", "Geometria2"], errors="ignore"
            )
            # nome de aba do Excel tem limite de 31 caracteres
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
    """Lista os clientes disponíveis pra barra lateral, com a data do cache
    de cada um (None se ainda não foi extraído nenhuma vez)."""
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
    """Não recalcula nada — só confirma que existe cache pra esse cliente e
    devolve a data em que ele foi gerado. O cálculo em si só acontece quando
    alguém pede pro Claude Code extrair aquele cliente do smartbio de novo."""
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
    """Lista os pares já calculados pro cliente selecionado, com filtros opcionais."""
    dados = _carregar_cache(cliente)
    itens = [i for i in dados["itens"] if _bate_filtro(i, fazenda, usina, safra, talhao, percentual_minimo)]

    # a lista fica leve (sem geometria) — o desenho de cada par só é buscado
    # sob demanda em /api/duplicados/{id}/geometria quando o usuário clica na linha
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
    """Retorna a geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela."""
    dados = _carregar_cache(cliente)
    for item in dados["itens"]:
        if item["id"] == par_id:
            return {"geometria1": item["Geometria1"], "geometria2": item["Geometria2"]}

    raise HTTPException(status_code=404, detail="Par não encontrado.")


@app.get("/api/duplicados/excel")
def baixar_excel(cliente: str):
    """Retorna pra download o último Excel gerado pra esse cliente."""
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
    """Envia os dados dos clientes selecionados por e-mail, via Microsoft
    Graph. Um cliente só: anexa o Excel já gerado por ele. Mais de um:
    monta um único Excel com uma aba por cliente, em vez de um anexo pra
    cada um."""
    for cliente in clientes:
        _carregar_cache(cliente)  # 404 cedo se algum cliente não tiver dado

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


def _carregar_relatorios(cliente: str) -> dict:
    caminho = MANAGERVISION_CACHE_DIR / f"{cliente}.json"
    if not caminho.exists():
        return {"itens": []}
    return json.loads(caminho.read_text(encoding="utf-8"))


@app.get("/api/relatorios")
def listar_relatorios(cliente: str):
    """Lista os relatórios do ManagerVision (Smartbio) já baixados em cache
    pra esse cliente: título, descrição e link pro relatório ao vivo. Esse
    cache só é populado por uma sessão do Claude com o MCP Smartbio — esse
    backend não acessa o ManagerVision diretamente, então a lista fica vazia
    até alguém pedir pro Claude Code atualizar."""
    return _carregar_relatorios(cliente)


def _selecionar_relatorios(cliente: str, chart_ids: List[str]) -> list[dict]:
    dados = _carregar_relatorios(cliente)
    por_id = {item["chart_id"]: item for item in dados["itens"]}

    selecionados = []
    for chart_id in chart_ids:
        item = por_id.get(chart_id)
        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"Relatório '{chart_id}' não encontrado no cache de '{cliente}'.",
            )
        selecionados.append(item)
    return selecionados


@app.get("/api/relatorios/{chart_id}/pdf")
def baixar_relatorio_pdf(chart_id: str, cliente: str):
    """Loga no ManagerVision (Playwright) e devolve o PDF de um relatório,
    com os dados ao vivo — pra download direto pelo botão da tela."""
    item = _selecionar_relatorios(cliente, [chart_id])[0]

    try:
        [(_, caminho)] = exportar_varios_pdf([item], OUTPUT_DIR / "managervision_pdf" / cliente)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    nome_arquivo = f"{item['titulo']}.pdf".replace("/", "-")
    return FileResponse(caminho, media_type="application/pdf", filename=nome_arquivo)


@app.post("/api/relatorios/email")
def enviar_relatorios_por_email(cliente: str, arquivos: List[str] = Query(...)):
    """Gera um PDF de cada relatório selecionado (login automatizado via
    Playwright, com dados ao vivo) e manda todos anexados num único e-mail."""
    selecionados = _selecionar_relatorios(cliente, arquivos)
    if not selecionados:
        raise HTTPException(status_code=400, detail="Nenhum relatório selecionado.")

    try:
        exportados = exportar_varios_pdf(selecionados, OUTPUT_DIR / "managervision_pdf" / cliente)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    caminhos = [caminho for _, caminho in exportados]
    titulos = [item["titulo"] for item, _ in exportados]
    corpo = f"Segue em anexo os relatórios do ManagerVision ({cliente}):\n\n" + "\n".join(
        f"- {t}" for t in titulos
    )

    try:
        enviar_email(caminhos, assunto=f"Relatórios ManagerVision - {cliente}", corpo=corpo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"enviado": True, "total": len(caminhos)}
