"""Exportação em PDF dos relatórios do ManagerVision (Smartbio), via login
automatizado com Playwright.

Por que precisa de um navegador de verdade: cada relatório é uma SPA que
busca os dados ao vivo via fetch() para rotas relativas do próprio domínio
do cliente (ex.: /ManagerVision/Data/{query_id}), autenticadas pela sessão
logada — abrir o HTML fora desse domínio/sessão (arquivo local, anexo de
e-mail) sempre dá "Failed to fetch". Rodando com Playwright + login real,
o navegador headless carrega a página exatamente como um usuário logado
carregaria, e a impressão em PDF sai com os dados de verdade.

Uma única conta (MANAGERVISION_USER/MANAGERVISION_PASSWORD no .env) vale
pra todos os clientes/subdomínios smartbreeder.com.br — por isso a sessão é
reaproveitada entre vários relatórios da mesma chamada, logando só uma vez.

## Mídia de impressão

Cada relatório do ManagerVision já vem com seu próprio CSS `@media print`
(usado pelo botão "Exportar PDF" de dentro da própria página): esconde os
botões de ação e às vezes define um `@page` com tamanho próprio. Por isso
NÃO chamamos `page.emulate_media("screen")` antes de gerar o PDF — deixamos
o Playwright usar a mídia "print" (comportamento padrão de `page.pdf()`),
que já aplica esse CSS sozinho. `prefer_css_page_size` faz o tamanho de
página respeitar o `@page` do relatório quando ele existe; quando não
existe, cai no fallback A4 retrato passado como `format`/`landscape`.

Só um PDF de uma página por relatório — sem clicar em aba nem mexer em
filtro: sai com a aba/filtro padrão que já vem selecionado quando a página
abre, igual ao que o usuário veria entrando na tela sem tocar em nada. Um
relatório com várias abas (ex.: "Volumetria de Dados") só é capturado com a
aba inicial (normalmente "Gráfico") — não itera pelas outras.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from config import MANAGERVISION_USER, MANAGERVISION_PASSWORD

TIMEOUT_MS = 30000
VIEWPORT = {"width": 1600, "height": 1000}


def _logar(page):
    page.wait_for_selector('input[name="email"]', timeout=15000)
    page.fill('input[name="email"]', MANAGERVISION_USER)
    page.fill('input[name="senha"]', MANAGERVISION_PASSWORD)
    with page.expect_navigation(timeout=20000):
        page.click('button:has-text("Entrar")')
    page.wait_for_load_state("networkidle", timeout=20000)


def _exportar_um(page, item, destino_dir: Path) -> Path:
    page.goto(item["url"], wait_until="networkidle", timeout=TIMEOUT_MS)
    if "Chart" not in page.url:
        _logar(page)
        page.goto(item["url"], wait_until="networkidle", timeout=TIMEOUT_MS)
    if "Chart" not in page.url:
        raise RuntimeError(
            f"Não consegui abrir o relatório '{item['titulo']}' mesmo após logar "
            f"(URL final: {page.url}). Confira o usuário/senha no .env."
        )

    # dá um tempo pras queries de dados (fetch ao vivo) terminarem depois do
    # networkidle — alguns relatórios têm gráficos que renderizam com um
    # pequeno atraso depois da resposta da query
    page.wait_for_timeout(2000)

    caminho = destino_dir / f"{item['chart_id']}.pdf"
    page.pdf(
        path=str(caminho),
        print_background=True,
        prefer_css_page_size=True,
        format="A4",
        landscape=False,
    )
    return caminho


def exportar_varios_pdf(itens: list[dict], destino_dir) -> list[tuple[dict, Path]]:
    """Exporta um PDF por item (cada item precisa de chart_id/titulo/url — o
    formato salvo em cache/managervision/<cliente>.json). Loga uma vez só,
    reaproveitando a sessão pros itens seguintes do mesmo domínio/cliente.
    Retorna [(item, caminho_pdf), ...] na mesma ordem de entrada."""
    if not MANAGERVISION_USER or not MANAGERVISION_PASSWORD:
        raise RuntimeError(
            "MANAGERVISION_USER / MANAGERVISION_PASSWORD não configurados no .env "
            "— sem isso não dá pra logar no ManagerVision pra exportar PDF."
        )
    if not itens:
        return []

    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)

    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        try:
            for item in itens:
                caminho = _exportar_um(page, item, destino_dir)
                resultados.append((item, caminho))
        finally:
            browser.close()

    return resultados
