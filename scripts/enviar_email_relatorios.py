"""Manda, pra cada cliente, um e-mail separado com os PDFs de todos os
relatórios do ManagerVision cadastrados em cache/managervision/<cliente>.json,
pro(s) destinatário(s) daquele cliente (config.EMAIL_POR_CLIENTE, com
fallback pro EMAIL_RECIPIENTS padrão do .env).

Não gera PDF aqui — só anexa os que já foram gerados em
output/managervision_pdf/<cliente>/<chart_id>.pdf pelo passo anterior do
pipeline (scripts/build_managervision_pdfs.py, chamado pela skill
/atualizar-relatorios-managervision). Cliente sem relatório cadastrado ou
sem nenhum PDF em disco é só avisado no resumo e pulado — não é erro.

Roda automaticamente todo dia, logo depois de /atualizar-relatorios-managervision,
dentro de scripts/atualizar_diario.ps1.

Rodar sem argumentos:
    python scripts/enviar_email_relatorios.py
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import destinatarios_do_cliente  # noqa: E402
from email_utils import enviar_email  # noqa: E402
from smartbio_cache import CACHE_DIR, CLIENTES, OUTPUT_DIR  # noqa: E402

MANAGERVISION_CACHE_DIR = CACHE_DIR / "managervision"


def _relatorios_do_cliente(cliente: str) -> list[dict]:
    caminho = MANAGERVISION_CACHE_DIR / f"{cliente}.json"
    if not caminho.exists():
        return []
    return json.loads(caminho.read_text(encoding="utf-8"))["itens"]


def _pdfs_gerados(cliente: str, itens: list[dict]) -> list[dict]:
    """Cruza o cache de metadado com os PDFs que já existem em disco (gerados
    por scripts/build_managervision_pdfs.py, que roda antes deste script no
    pipeline diário) — devolve só os itens com PDF pronto, com o caminho anexado."""
    pasta = OUTPUT_DIR / "managervision_pdf" / cliente
    prontos = []
    for item in itens:
        caminho = pasta / f"{item['chart_id']}.pdf"
        if caminho.exists():
            prontos.append({**item, "_pdf": caminho})
    return prontos


def main():
    enviados, sem_relatorio, falhas = [], [], []

    for cliente in CLIENTES:
        itens = _relatorios_do_cliente(cliente)
        prontos = _pdfs_gerados(cliente, itens)
        if not prontos:
            sem_relatorio.append(cliente)
            continue

        destinatarios = destinatarios_do_cliente(cliente)
        caminhos = [item["_pdf"] for item in prontos]
        corpo = f"Segue em anexo os relatórios do ManagerVision ({cliente}):\n\n" + "\n".join(
            f"- {item['titulo']}" for item in prontos
        )
        try:
            enviar_email(
                caminhos,
                assunto=f"Relatórios ManagerVision - {cliente}",
                corpo=corpo,
                destinatarios=destinatarios,
            )
            enviados.append(cliente)
            print(f"OK  {cliente} -> {', '.join(destinatarios)} ({len(caminhos)} PDF(s))")
        except Exception as exc:
            falhas.append((cliente, str(exc)))
            print(f"ERRO {cliente}: {exc}")

    print()
    print(f"Enviados: {len(enviados)}/{len(CLIENTES)}")
    if sem_relatorio:
        print(f"Sem relatório/PDF disponível (pulado): {sem_relatorio}")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
