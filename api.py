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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from email_utils import enviar_email
from managervision_pdf import exportar_varios_pdf
from smartbio_cache import (
    CACHE_DIR,
    CLIENTES,
    OUTPUT_DIR,
    limpar_excels_antigos,
    salvar_excel_por_aba,
    ultimo_excel,
)

app = FastAPI(title="Data Quality Monitor - Geometrias Duplicadas")

# permite chamadas do front local (Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


MANAGERVISION_CACHE_DIR = CACHE_DIR / "managervision"

# cache/<cliente>.json já decodificado, por cliente: (mtime_ns, dados). Só
# relê do disco quando smartbio_cache.py grava um arquivo novo (mtime muda)
# — antes cada requisição decodificava o JSON inteiro (Atvos tem ~10MB), e
# /api/clientes fazia isso com os 10 só pra ler total/gerado_em.
_CACHE_EM_MEMORIA: dict[str, tuple[int, dict]] = {}


def _carregar_cache(cliente: str) -> dict:
    """Dados do cache do cliente, com dois índices montados uma vez por
    versão do arquivo: `_por_id` (par pelo id) e `_itens_sem_geometria`
    (lista leve pra tabela). Não alterar o dict devolvido — é compartilhado
    entre requisições."""
    caminho = CACHE_DIR / f"{cliente}.json"
    try:
        mtime = caminho.stat().st_mtime_ns
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum dado ainda para '{cliente}'. Peça pro Claude Code rodar "
                f"'smartbio_cache.py {cliente}' com uma extração fresca do smartbio."
            ),
        ) from None

    em_memoria = _CACHE_EM_MEMORIA.get(cliente)
    if em_memoria and em_memoria[0] == mtime:
        return em_memoria[1]

    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["_por_id"] = {item["id"]: item for item in dados["itens"]}
    # sem geometria: o desenho é buscado sob demanda em /geometria
    dados["_itens_sem_geometria"] = [
        {k: v for k, v in item.items() if k not in ("Geometria1", "Geometria2")}
        for item in dados["itens"]
    ]
    _CACHE_EM_MEMORIA[cliente] = (mtime, dados)
    return dados


def _gerar_excel_multi_aba(clientes: list[str]) -> Path:
    """Monta um Excel com uma aba por cliente, pra anexar num único e-mail."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = salvar_excel_por_aba(
        OUTPUT_DIR / f"multiplos_clientes_{timestamp}.xlsx",
        {cliente: _carregar_cache(cliente)["itens"] for cliente in clientes},
    )
    limpar_excels_antigos("multiplos_clientes_*.xlsx")
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
        try:
            dados = _carregar_cache(cliente)
        except HTTPException:
            itens.append({"cliente": cliente, "total": None, "gerado_em": None})
            continue
        itens.append({
            "cliente": cliente,
            "total": dados["total"],
            "gerado_em": dados["gerado_em"],
        })
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
    itens = [
        i for i in dados["_itens_sem_geometria"]
        if _bate_filtro(i, fazenda, usina, safra, talhao, percentual_minimo)
    ]

    return {
        "total": len(itens),
        "ultima_execucao": dados["gerado_em"],
        "itens": itens,
    }


@app.get("/api/duplicados/{par_id}/geometria")
def obter_geometria(par_id: int, cliente: str):
    """Retorna a geometria (GeoJSON) dos dois talhões de um par."""
    item = _carregar_cache(cliente)["_por_id"].get(par_id)
    if not item:
        raise HTTPException(status_code=404, detail="Par não encontrado.")
    return {"geometria1": item["Geometria1"], "geometria2": item["Geometria2"]}


@app.get("/api/duplicados/excel")
def baixar_excel(cliente: str):
    """Retorna o último Excel gerado pra esse cliente."""
    arquivo = ultimo_excel(cliente)
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
        arquivo = ultimo_excel(clientes[0])
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
    """Lista os relatórios do ManagerVision em cache pra esse cliente
    (populado via MCP Smartbio; este backend não acessa o ManagerVision)."""
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
    """Loga no ManagerVision (Playwright) e devolve o PDF do relatório com dados ao vivo."""
    item = _selecionar_relatorios(cliente, [chart_id])[0]

    try:
        [(_, caminho)] = exportar_varios_pdf([item], OUTPUT_DIR / "managervision_pdf" / cliente)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    nome_arquivo = f"{item['titulo']}.pdf".replace("/", "-")
    return FileResponse(caminho, media_type="application/pdf", filename=nome_arquivo)


@app.post("/api/relatorios/email")
def enviar_relatorios_por_email(cliente: str, arquivos: List[str] = Query(...)):
    """Gera um PDF de cada relatório selecionado (Playwright) e manda todos num só e-mail."""
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


@app.post("/api/relatorios/email-todos")
def enviar_todos_relatorios_por_email():
    """Gera o PDF de TODOS os relatórios em cache, de TODOS os clientes
    (Playwright, ao vivo — um cliente por vez, a sessão de login é
    reaproveitada entre os relatórios do mesmo cliente e refeita sozinha ao
    trocar de cliente/subdomínio) e manda tudo anexado num único e-mail, pro
    destinatário padrão (EMAIL_RECIPIENTS do .env — hoje o trio ariane/
    otavio/jose). Pode levar vários minutos com todos os clientes."""
    por_cliente = {}
    for cliente in CLIENTES:
        itens = _carregar_relatorios(cliente)["itens"]
        if itens:
            por_cliente[cliente] = itens

    if not por_cliente:
        raise HTTPException(status_code=404, detail="Nenhum relatório em cache pra nenhum cliente.")

    caminhos = []
    titulos_por_cliente = {}
    for cliente, itens in por_cliente.items():
        try:
            exportados = exportar_varios_pdf(itens, OUTPUT_DIR / "managervision_pdf" / cliente)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao gerar PDFs de {cliente}: {exc}") from exc
        caminhos.extend(caminho for _, caminho in exportados)
        titulos_por_cliente[cliente] = [item["titulo"] for item, _ in exportados]

    corpo_linhas = ["Segue em anexo todos os relatórios ManagerVision, por cliente:", ""]
    for cliente, titulos in titulos_por_cliente.items():
        corpo_linhas.append(f"{cliente}:")
        corpo_linhas.extend(f"  - {t}" for t in titulos)
    corpo = "\n".join(corpo_linhas)

    try:
        enviar_email(caminhos, assunto="Relatórios ManagerVision - Todos os clientes", corpo=corpo)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"enviado": True, "total": len(caminhos), "clientes": list(por_cliente.keys())}
