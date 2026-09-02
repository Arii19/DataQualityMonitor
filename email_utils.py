"""Envio de e-mail via Microsoft Graph, usando o fluxo client credentials
(app-only) do Azure AD — sem precisar de login interativo de usuário.

Requer, no .env: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
(credenciais do app registrado no Azure AD, com a permissão de aplicativo
Mail.Send consentida pelo administrador do tenant) e EMAIL_SENDER (a caixa
que aparece como remetente — precisa ser uma caixa real do tenant).
"""

import base64
import mimetypes
from pathlib import Path

import msal
import requests

from config import (
    AZURE_TENANT_ID,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    EMAIL_SENDER,
    EMAIL_RECIPIENTS,
    EMAIL_SUBJECT,
)

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


def _obter_token():
    if not (AZURE_TENANT_ID and AZURE_CLIENT_ID and AZURE_CLIENT_SECRET):
        raise ValueError(
            "AZURE_TENANT_ID, AZURE_CLIENT_ID e AZURE_CLIENT_SECRET são obrigatórios no .env"
        )

    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        client_credential=AZURE_CLIENT_SECRET,
    )
    resultado = app.acquire_token_for_client(scopes=GRAPH_SCOPE)

    if "access_token" not in resultado:
        raise RuntimeError(
            "Falha ao autenticar no Azure AD: "
            f"{resultado.get('error')} - {resultado.get('error_description')}"
        )

    return resultado["access_token"]


def _anexo_em_base64(caminho_arquivo):
    caminho_arquivo = Path(caminho_arquivo)
    tipo_mime, _ = mimetypes.guess_type(caminho_arquivo.name)
    conteudo = caminho_arquivo.read_bytes()

    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": caminho_arquivo.name,
        "contentType": tipo_mime or "application/octet-stream",
        "contentBytes": base64.b64encode(conteudo).decode("ascii"),
    }


def enviar_email(caminho_arquivo, assunto=None, corpo=None, destinatarios=None):
    """Envia um arquivo por e-mail via Microsoft Graph. Usa remetente/assunto/
    destinatários do .env por padrão; qualquer um pode ser sobrescrito por
    parâmetro."""
    if not EMAIL_SENDER:
        raise ValueError("EMAIL_SENDER não foi encontrado no .env")

    destinatarios = destinatarios or EMAIL_RECIPIENTS
    if not destinatarios:
        raise ValueError("Nenhum destinatário configurado (EMAIL_RECIPIENTS no .env)")

    token = _obter_token()

    mensagem = {
        "message": {
            "subject": assunto or EMAIL_SUBJECT,
            "body": {
                "contentType": "Text",
                "content": corpo or "Segue em anexo o relatório gerado pelo Data Quality Monitor.",
            },
            "toRecipients": [
                {"emailAddress": {"address": destinatario}} for destinatario in destinatarios
            ],
            "attachments": [_anexo_em_base64(caminho_arquivo)],
        },
        "saveToSentItems": "true",
    }

    resposta = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{EMAIL_SENDER}/sendMail",
        headers={"Authorization": f"Bearer {token}"},
        json=mensagem,
        timeout=30,
    )

    if resposta.status_code != 202:
        raise RuntimeError(f"Falha ao enviar e-mail (HTTP {resposta.status_code}): {resposta.text}")

    return True


def _excel_mais_recente(pasta_saida="output"):
    """Acha o último Excel de duplicidades gerado (maior timestamp no nome)."""
    arquivos = sorted(Path(pasta_saida).glob("geometrias_duplicadas_*.xlsx"))
    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum Excel encontrado em {pasta_saida}/. Rode o pipeline (app.py) primeiro."
        )
    return arquivos[-1]


if __name__ == "__main__":
    arquivo = _excel_mais_recente()
    enviar_email(arquivo)
    print(f"E-mail enviado com sucesso ({arquivo.name}).")
