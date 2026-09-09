"""Manda um e-mail avisando que dist/dashboard.html foi atualizado no disco
e está pronto pra ser republicado no Artifact — a publicação em si não pode
ser automatizada (ferramenta Artifact não fica disponível numa sessão
`claude -p` headless, ver comentário em scripts/atualizar_diario.ps1), então
esse e-mail é o que fecha o loop: alguém só precisa abrir uma conversa do
Claude Code e pedir "republica o dashboard".

Rodar depois de scripts/build_dashboard.py, sem argumentos:
    python scripts/notificar_dashboard_pronto.py
"""

import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from email_utils import enviar_email_texto  # noqa: E402

URL_ARTIFACT = "https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60"
DIST_PATH = BASE_DIR / "dist" / "dashboard.html"


def main():
    if not DIST_PATH.exists():
        print(f"ERRO: {DIST_PATH} não existe — rode build_dashboard.py antes.")
        sys.exit(1)

    tamanho_mb = DIST_PATH.stat().st_size / 1024 / 1024
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    corpo = (
        f"O dashboard foi atualizado no disco ({tamanho_mb:.2f}MB) em {agora}, "
        f"com dados novos de geometrias e relatórios ManagerVision.\n\n"
        f"A publicação no link não é automática — abra uma conversa do Claude Code "
        f"e peça \"republica o dashboard\" pra colocar essa versão no ar em:\n"
        f"{URL_ARTIFACT}"
    )

    enviar_email_texto(assunto="Dashboard atualizado — pronto pra republicar", corpo=corpo)
    print("E-mail de notificação enviado.")


if __name__ == "__main__":
    main()
