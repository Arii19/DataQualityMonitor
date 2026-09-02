"""Gera o artifact estático (dashboard.html) a partir dos cache/<cliente>.json.

Parte do fluxo de publicação pra pessoas de fora da rede local (ver
README/pedido do usuário): como o artifact publicado não tem acesso a
nenhum backend, todo o dado (metadados + geometria) fica embutido no
próprio HTML como JSON. As geometrias são simplificadas (shapely.simplify
+ arredondamento de coordenadas) só pra esse embed — o cache original,
usado pela tela local (React+FastAPI) e por qualquer recomputo, não é
alterado. É isso que faz o embed caber no limite de 16MB de um artifact:
os 9 clientes somados, na resolução original, passam de 30MB; simplificados
pra visualização ficam por volta de 3MB.

Rodar depois de recomputar os caches (`python smartbio_cache.py`):

    python scripts/build_dashboard.py

Gera dist/dashboard.html, pronto pra publicar/republicar como Artifact
(sempre no mesmo link — republicar só troca o conteúdo).
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
TEMPLATE_PATH = BASE_DIR / "scripts" / "dashboard_template.html"
DIST_DIR = BASE_DIR / "dist"
DIST_PATH = DIST_DIR / "dashboard.html"

CLIENTES = ["Atvos", "SantaAdelia", "Cevasa", "CMAA", "Guaira", "GQQ", "JPA", "Cocal", "IPE"]

# colunas mantidas no embed (sem Geometria1/2 crua — essa é substituída pela
# versão simplificada logo abaixo)
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
    """Reduz a quantidade de vértices pra visualização (algumas geometrias
    de talhão real passam de 30 mil pontos) sem mudar a forma perceptível —
    só usado no desenho do artifact, nunca no cálculo de sobreposição."""
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


def build():
    dados = montar_dados()
    dados_json = json.dumps(dados, ensure_ascii=False)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__DADOS_JSON__" not in template:
        raise RuntimeError(f"Placeholder __DADOS_JSON__ não encontrado em {TEMPLATE_PATH}")
    final_html = template.replace("__DADOS_JSON__", dados_json)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(final_html, encoding="utf-8")

    tamanho_mb = len(final_html.encode("utf-8")) / 1024 / 1024
    print(f"dist/dashboard.html gerado ({tamanho_mb:.2f}MB)")
    for meta in dados["clientes"]:
        print(f"  {meta['cliente']:15s} {meta['total']} par(es)")


if __name__ == "__main__":
    build()
