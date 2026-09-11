"""Envio de e-mail via Microsoft Graph, com client credentials (app-only) do
Azure AD — sem login interativo.

Requer no .env: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (app
registrado no Azure AD, com permissão Mail.Send consentida pelo admin do
tenant) e EMAIL_SENDER (caixa real do tenant, usada como remetente).
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


def _enviar_mensagem(assunto, corpo, destinatarios, anexos=None):
    if not EMAIL_SENDER:
        raise ValueError("EMAIL_SENDER não foi encontrado no .env")

    destinatarios = destinatarios or EMAIL_RECIPIENTS
    if not destinatarios:
        raise ValueError("Nenhum destinatário configurado (EMAIL_RECIPIENTS no .env)")

    token = _obter_token()

    corpo_mensagem = {
        "subject": assunto or EMAIL_SUBJECT,
        "body": {
            "contentType": "Text",
            "content": corpo or "Segue em anexo o relatório das geometrias duplicadas.",
        },
        "toRecipients": [
            {"emailAddress": {"address": destinatario}} for destinatario in destinatarios
        ],
    }
    if anexos:
        corpo_mensagem["attachments"] = [_anexo_em_base64(caminho) for caminho in anexos]

    resposta = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{EMAIL_SENDER}/sendMail",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": corpo_mensagem, "saveToSentItems": "true"},
        timeout=30,
    )

    if resposta.status_code != 202:
        raise RuntimeError(f"Falha ao enviar e-mail (HTTP {resposta.status_code}): {resposta.text}")

    return True


def enviar_email(caminho_arquivo, assunto=None, corpo=None, destinatarios=None):
    """Envia um ou mais arquivos anexados num único e-mail (aceita um caminho
    ou lista). Usa remetente/assunto/destinatários do .env por padrão,
    sobrescrevíveis por parâmetro."""
    caminhos = [caminho_arquivo] if isinstance(caminho_arquivo, (str, Path)) else list(caminho_arquivo)
    if not caminhos:
        raise ValueError("Nenhum arquivo pra anexar")

    return _enviar_mensagem(assunto, corpo, destinatarios, anexos=caminhos)


def enviar_email_texto(assunto=None, corpo=None, destinatarios=None):
    """Envia um e-mail só de texto, sem anexo (ex.: links do ManagerVision,
    que dependem da sessão/domínio do cliente pra carregar dados)."""
    return _enviar_mensagem(assunto, corpo, destinatarios)


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
