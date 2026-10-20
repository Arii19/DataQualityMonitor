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

# Destinatários por cliente pro e-mail diário automático (scripts/
# enviar_email_geometrias.py). Cliente ausente cai no default: EMAIL_RECIPIENTS
# do .env — hoje isso é todo mundo, e por isso os 9 clientes vão consolidados
# num só e-mail (uma aba por usina, ver enviar_email_geometrias.py). Um
# cliente só volta a ser mandado separado (Excel próprio, e-mail próprio) se
# ganhar aqui um destinatário diferente de EMAIL_RECIPIENTS.
EMAIL_POR_CLIENTE = {}


# Domínios para os quais a fila de "Enviar PDFs por e-mail" do dashboard
# (scripts/enviar_fila_relatorios.py) pode mandar — qualquer pessoa da
# organização pode pedir um envio, e ele sai da caixa EMAIL_SENDER, então só
# domínios conhecidos. EMAIL_DOMINIOS_PERMITIDOS no .env (separados por
# vírgula); sem ele, smartbreeder.com.br + os domínios de EMAIL_RECIPIENTS.
EMAIL_DOMINIOS_PERMITIDOS = sorted({
    d.strip().lower().lstrip("@")
    for d in (
        os.getenv("EMAIL_DOMINIOS_PERMITIDOS", "").split(",")
        if os.getenv("EMAIL_DOMINIOS_PERMITIDOS")
        else ["smartbreeder.com.br", *(r.split("@")[-1] for r in EMAIL_RECIPIENTS)]
    )
    if d.strip()
})


def destinatarios_do_cliente(cliente: str) -> list[str]:
    """Destinatário(s) do cliente (EMAIL_POR_CLIENTE), ou EMAIL_RECIPIENTS padrão."""
    return EMAIL_POR_CLIENTE.get(cliente, EMAIL_RECIPIENTS)


# login pra autenticar via Playwright nos relatórios do ManagerVision
# (mesma conta serve todos os clientes/subdomínios smartbreeder.com.br) —
# usado só sob demanda, quando alguém pede um PDF pela tela local
# (managervision_pdf.py); não faz parte de nenhuma automação diária.
MANAGERVISION_USER = os.getenv("MANAGERVISION_USER")
MANAGERVISION_PASSWORD = os.getenv("MANAGERVISION_PASSWORD")
