"""Exportação em PDF dos relatórios do ManagerVision (Smartbio), via login
automatizado com Playwright.

Precisa de navegador de verdade: cada relatório é uma SPA que busca dados ao
vivo via fetch() em rotas do domínio do cliente, autenticadas pela sessão
logada — abrir o HTML fora dessa sessão dá "Failed to fetch". Uma única
conta (MANAGERVISION_USER/PASSWORD no .env) serve todos os clientes; a
sessão é reaproveitada entre relatórios da mesma chamada.

Não chamamos `page.emulate_media("screen")`: a mídia "print" padrão já
aplica o CSS `@media print` próprio de cada relatório (esconde botões,
define `@page` quando existe). `prefer_css_page_size` respeita esse `@page`;
sem ele, cai no fallback A4 retrato.

Captura só a aba/filtro padrão de cada relatório (sem clicar em outras abas
ou mexer em filtro).
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

    # tempo extra pras queries/gráficos terminarem de renderizar após o networkidle
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
    """Exporta um PDF por item (chart_id/titulo/url, formato de
    cache/managervision/<cliente>.json). Loga uma vez só, reaproveitando a
    sessão. Retorna [(item, caminho_pdf), ...] na ordem de entrada."""
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
