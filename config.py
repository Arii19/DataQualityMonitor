import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")  # caixa que aparece como remetente
EMAIL_RECIPIENTS = [
    r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "").split(",") if r.strip()
]
EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", "Relatório de Geometrias Duplicadas")

# Destinatários por cliente pros e-mails diários automáticos (scripts/
# enviar_email_geometrias.py e enviar_email_relatorios.py). Cliente ausente
# cai no default: EMAIL_RECIPIENTS do .env.
EMAIL_POR_CLIENTE = {
    "Cocal": ["otavio.almeida@smartbreeder.com.br"],
    "Atvos": ["ariane.rodrigues@smartbreeder.com.br"],
}


def destinatarios_do_cliente(cliente: str) -> list[str]:
    """Destinatário(s) do cliente (EMAIL_POR_CLIENTE), ou EMAIL_RECIPIENTS padrão."""
    return EMAIL_POR_CLIENTE.get(cliente, EMAIL_RECIPIENTS)


# login pra autenticar via Playwright nos relatórios do ManagerVision
# (mesma conta serve todos os clientes/subdomínios smartbreeder.com.br)
MANAGERVISION_USER = os.getenv("MANAGERVISION_USER")
MANAGERVISION_PASSWORD = os.getenv("MANAGERVISION_PASSWORD")
