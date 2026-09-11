"""Gera o artifact estático (dashboard.html) a partir dos cache/<cliente>.json,
pra publicação fora da rede local: como o artifact não acessa backend, todo
o dado fica embutido no HTML como JSON. Geometrias são simplificadas
(shapely.simplify + arredondamento) só pra esse embed, sem alterar o cache
original — os 9 clientes somados passam de 30MB na resolução original e
ficam por volta de 3MB simplificados, cabendo no limite de 16MB do artifact.

Rodar depois de recomputar os caches (`python smartbio_cache.py`):

    python scripts/build_dashboard.py

Gera dist/dashboard.html, pronto pra publicar/republicar (sempre no mesmo link).
"""

import base64
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
MANAGERVISION_CACHE_DIR = CACHE_DIR / "managervision"
MANAGERVISION_PDF_DIR = BASE_DIR / "output" / "managervision_pdf"
TEMPLATE_PATH = BASE_DIR / "scripts" / "dashboard_template.html"
DIST_DIR = BASE_DIR / "dist"
DIST_PATH = DIST_DIR / "dashboard.html"

CLIENTES = ["Atvos", "SantaAdelia", "Cevasa", "CMAA", "Guaira", "GQQ", "JPA", "Cocal", "IPE"]

# limite real do Artifact é 16MB; mira em 15MB pra deixar margem de segurança
TAMANHO_MAXIMO_ARTIFACT_MB = 15

# colunas mantidas no embed (Geometria1/2 é substituída pela versão simplificada)
COLUNAS = [
    "id", "AnoSafra1", "AnoSafra2", "Fazenda1", "Fazenda2", "Bloco1", "Bloco2",
    "Talhao1", "Talhao2", "IDTalhao1", "IDTalhao2", "Corte1", "Corte2",
    "Usina1", "Usina2", "PercentualSobreposicaoGeral", "Motivo",
]


def _arredondar(coords, ndigits=6):
    if isinstance(coords[0], (float, int)):
        return [round(c, ndigits) for c in coords]
    return [_arredondar(c, ndigits) for c in coords]


def _simplificar(geometria_dict):
    """Reduz vértices pra visualização (algumas geometrias passam de 30 mil
    pontos) sem mudar a forma perceptível — só pro desenho, nunca pro cálculo."""
    try:
        geom = shape(geometria_dict)
    except Exception:
        return geometria_dict
    minx, miny, maxx, maxy = geom.bounds
    diagonal = math.hypot(maxx - minx, maxy - miny)
    tolerancia = max(diagonal / 400, 0.0000015)
    simplificada = geom.simplify(tolerancia, preserve_topology=True)
    if simplificada.is_empty:
        simplificada = geom
    resultado = dict(mapping(simplificada))
    resultado["coordinates"] = _arredondar(resultado["coordinates"])
    return resultado


def montar_dados():
    clientes_meta = []
    pares_por_cliente = {}

    for cliente in CLIENTES:
        caminho = CACHE_DIR / f"{cliente}.json"
        if not caminho.exists():
            clientes_meta.append({"cliente": cliente, "total": None, "geradoEm": None})
            pares_por_cliente[cliente] = []
            continue

        bruto = json.loads(caminho.read_text(encoding="utf-8"))
        clientes_meta.append({
            "cliente": cliente,
            "total": bruto["total"],
            "geradoEm": bruto["gerado_em"],
        })

        itens = []
        for item in bruto["itens"]:
            linha = {chave: item.get(chave) for chave in COLUNAS}
            linha["Geometria1"] = _simplificar(item["Geometria1"])
            linha["Geometria2"] = _simplificar(item["Geometria2"])
            itens.append(linha)
        pares_por_cliente[cliente] = itens

    return {
        "publicadoEm": datetime.now(timezone.utc).isoformat(),
        "clientes": clientes_meta,
        "pares": pares_por_cliente,
    }


def montar_relatorios():
    """Monta os metadados dos relatórios por cliente e a lista achatada de
    PDFs já em disco, usada depois pra decidir quais cabem no Artifact."""
    relatorios_por_cliente = {}
    gerado_em = None
    candidatos_pdf = []  # (entrada_dict, caminho_pdf, tamanho_bytes)

    for cliente in CLIENTES:
        caminho = MANAGERVISION_CACHE_DIR / f"{cliente}.json"
        if not caminho.exists():
            relatorios_por_cliente[cliente] = []
            continue

        bruto = json.loads(caminho.read_text(encoding="utf-8"))
        if gerado_em is None or (bruto.get("gerado_em") or "") > gerado_em:
            gerado_em = bruto.get("gerado_em")

        itens = []
        for item in bruto["itens"]:
            entrada = {
                "chart_id": item["chart_id"],
                "titulo": item["titulo"],
                "description": item["description"],
                "url": item["url"],
                "pdfBase64": None,
            }
            itens.append(entrada)

            pdf_path = MANAGERVISION_PDF_DIR / cliente / f"{item['chart_id']}.pdf"
            if pdf_path.exists():
                candidatos_pdf.append((entrada, pdf_path, pdf_path.stat().st_size))

        relatorios_por_cliente[cliente] = itens

    return relatorios_por_cliente, gerado_em, candidatos_pdf


def _preencher_pdfs_no_orcamento(candidatos_pdf, bytes_ja_usados):
    """Embute o PDF (base64) de cada relatório, do menor pro maior, até
    estourar TAMANHO_MAXIMO_ARTIFACT_MB — o resto fica só com link.
    Retorna (incluidos, excluidos)."""
    limite_bytes = TAMANHO_MAXIMO_ARTIFACT_MB * 1024 * 1024
    orcamento_pdf = max(0, limite_bytes - bytes_ja_usados)

    candidatos_pdf.sort(key=lambda c: c[2])
    usado = 0
    incluidos = []
    excluidos = []
    for entrada, pdf_path, tamanho in candidatos_pdf:
        tamanho_base64_estimado = math.ceil(tamanho / 3) * 4
        if usado + tamanho_base64_estimado > orcamento_pdf:
            excluidos.append(entrada["titulo"])
            continue
        entrada["pdfBase64"] = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
        usado += tamanho_base64_estimado
        incluidos.append(entrada["titulo"])

    return incluidos, excluidos


def build():
    dados = montar_dados()
    relatorios_por_cliente, relatorios_gerado_em, candidatos_pdf = montar_relatorios()
    dados["relatorios"] = relatorios_por_cliente
    dados["relatoriosGeradoEm"] = relatorios_gerado_em

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__DADOS_JSON__" not in template:
        raise RuntimeError(f"Placeholder __DADOS_JSON__ não encontrado em {TEMPLATE_PATH}")

    # mede o tamanho de tudo menos os PDFs, pra saber o orçamento que sobra
    baseline_html = template.replace("__DADOS_JSON__", json.dumps(dados, ensure_ascii=False))
    bytes_sem_pdfs = len(baseline_html.encode("utf-8"))

    incluidos, excluidos = _preencher_pdfs_no_orcamento(candidatos_pdf, bytes_sem_pdfs)

    final_html = template.replace("__DADOS_JSON__", json.dumps(dados, ensure_ascii=False))

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(final_html, encoding="utf-8")

    tamanho_mb = len(final_html.encode("utf-8")) / 1024 / 1024
    print(f"dist/dashboard.html gerado ({tamanho_mb:.2f}MB)")
    for meta in dados["clientes"]:
        print(f"  {meta['cliente']:15s} {meta['total']} par(es)")

    print(f"\nRelatórios ManagerVision: {len(incluidos)} com PDF embutido, {len(excluidos)} só com link (não couberam no limite)")
    for titulo in excluidos:
        print(f"  sem PDF embutido (só link): {titulo}")


if __name__ == "__main__":
    build()
