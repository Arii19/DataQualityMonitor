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

# Destinatários específicos por cliente (usina) pros e-mails automáticos
# diários de geometrias/relatórios (scripts/enviar_email_geometrias.py e
# scripts/enviar_email_relatorios.py). Cliente que não aparece aqui cai no
# default: todo mundo do EMAIL_RECIPIENTS do .env. A ideia é que, conforme
# cada usina definir seu próprio responsável, essa lista vá crescendo até
# cobrir os 9 clientes de smartbio_cache.CLIENTES.
EMAIL_POR_CLIENTE = {
    "Cocal": ["otavio.almeida@smartbreeder.com.br"],
    "Atvos": ["ariane.rodrigues@smartbreeder.com.br"],
}


def destinatarios_do_cliente(cliente: str) -> list[str]:
    """Devolve o(s) destinatário(s) específico(s) de um cliente (EMAIL_POR_CLIENTE),
    ou o EMAIL_RECIPIENTS padrão do .env se o cliente não tiver regra própria."""
    return EMAIL_POR_CLIENTE.get(cliente, EMAIL_RECIPIENTS)


# login usado pra autenticar via Playwright nos relatórios do ManagerVision
# (mesma conta funciona em todos os clientes/subdomínios smartbreeder.com.br)
MANAGERVISION_USER = os.getenv("MANAGERVISION_USER")
MANAGERVISION_PASSWORD = os.getenv("MANAGERVISION_PASSWORD")
