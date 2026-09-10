"""Manda, pra cada cliente, um e-mail separado com o Excel de geometrias
duplicadas mais recente (output/<cliente>_duplicados_*.xlsx), pro(s)
destinatário(s) daquele cliente (config.EMAIL_POR_CLIENTE, com fallback pro
EMAIL_RECIPIENTS padrão do .env). Cliente sem Excel gerado ainda é só
avisado no resumo e pulado — não é erro.

Roda automaticamente todo dia, logo depois de /atualizar-geometrias, dentro
de scripts/atualizar_diario.ps1.

Rodar sem argumentos:
    python scripts/enviar_email_geometrias.py
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import destinatarios_do_cliente  # noqa: E402
from email_utils import enviar_email  # noqa: E402
from smartbio_cache import CLIENTES, OUTPUT_DIR  # noqa: E402


def _ultimo_excel(cliente: str):
    candidatos = sorted(OUTPUT_DIR.glob(f"{cliente}_duplicados_*.xlsx"))
    return candidatos[-1] if candidatos else None


def main():
    enviados, sem_arquivo, falhas = [], [], []

    for cliente in CLIENTES:
        arquivo = _ultimo_excel(cliente)
        if not arquivo:
            sem_arquivo.append(cliente)
            continue

        destinatarios = destinatarios_do_cliente(cliente)
        try:
            enviar_email(
                arquivo,
                assunto=f"Geometrias Duplicadas - {cliente}",
                corpo=f"Segue em anexo o relatório de geometrias duplicadas de {cliente}.",
                destinatarios=destinatarios,
            )
            enviados.append(cliente)
            print(f"OK  {cliente} -> {', '.join(destinatarios)} ({arquivo.name})")
        except Exception as exc:
            falhas.append((cliente, str(exc)))
            print(f"ERRO {cliente}: {exc}")

    print()
    print(f"Enviados: {len(enviados)}/{len(CLIENTES)}")
    if sem_arquivo:
        print(f"Sem Excel gerado (pulado): {sem_arquivo}")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
