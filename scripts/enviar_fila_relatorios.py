"""Envia os pedidos da fila "Enviar arquivos por e-mail" (PDF, XLSX, CSV) do dashboard publicado.

A página (scripts/dashboard_template.html) não manda e-mail: cada visitante
salva PDFs no banco do artifact (pedidos/<uid>/arquivos/<fid>, conteúdo em
base64 picado em .../partes/<n>) e grava o pedido em pedidos/<uid>/itens/<pid>
referenciando os <fid>. Uma tarefa agendada no Claude
baixa esses documentos com a ferramenta ArtifactData (`out_dir`) e roda este
script, que remonta os PDFs, confere tudo e envia via Microsoft Graph
(email_utils). O status volta pro banco pela própria tarefa, a partir do
JSON de resultado que este script grava.

    python scripts/enviar_fila_relatorios.py <out_dir> [--nomes nomes.json]

<out_dir> é a pasta passada como `out_dir` nas leituras (layout
<out_dir>/<collection>/<doc_id>.json). `--nomes` é um JSON {uid: nome} com o
nome de quem pediu (ArtifactData action "profiles"), usado só no corpo do
e-mail.

Idempotente: cada pedido enviado fica registrado em
output/fila_relatorios/enviados.json e nunca sai duas vezes, mesmo que a
tarefa caia antes de marcar o status no banco.
"""

import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import EMAIL_DOMINIOS_PERMITIDOS  # noqa: E402
from email_utils import enviar_email  # noqa: E402
from smartbio_cache import OUTPUT_DIR  # noqa: E402

FILA_DIR = OUTPUT_DIR / "fila_relatorios"
REGISTRO_ENVIADOS = FILA_DIR / "enviados.json"

# mesmos limites da página
MAX_TOTAL_BYTES = int(2.8 * 1024 * 1024)
MAX_DESTINATARIOS = 20

# tipos aceitos (mesmos da página) e como reconhecer o conteúdo de cada um —
# a extensão sozinha não basta, o arquivo vem de qualquer pessoa da organização
TIPOS_ACEITOS = {
    ".pdf": lambda c: c.startswith(b"%PDF-"),
    ".xlsx": lambda c: c.startswith(b"PK\x03\x04"),  # xlsx é um zip
    ".csv": lambda c: b"\x00" not in c[:65536],  # texto puro
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _campos(caminho: Path) -> dict:
    """Campos do documento salvo pelo ArtifactData (aceita o documento puro
    ou embrulhado em {"data": {...}})."""
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    if isinstance(doc.get("data"), dict):
        return doc["data"]
    return doc


def _nome_seguro(nome: str, extensao: str, usados: set) -> str:
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome or "relatorio").strip(". ") or "relatorio"
    if base.lower().endswith(extensao):
        base = base[: -len(extensao)]
    final, n = base + extensao, 2
    while final.lower() in usados:
        final = f"{base} ({n}){extensao}"
        n += 1
    usados.add(final.lower())
    return final


def _validar_destinatarios(destinatarios) -> list[str]:
    if not isinstance(destinatarios, list) or not destinatarios:
        raise ValueError("pedido sem destinatário")
    if len(destinatarios) > MAX_DESTINATARIOS:
        raise ValueError(f"mais de {MAX_DESTINATARIOS} destinatários")
    limpos = []
    for d in destinatarios:
        d = str(d).strip()
        if not _EMAIL.match(d):
            raise ValueError(f"e-mail inválido: {d}")
        dominio = d.rsplit("@", 1)[1].lower()
        if dominio not in EMAIL_DOMINIOS_PERMITIDOS:
            raise ValueError(
                f"domínio não liberado para envio: {dominio} "
                f"(liberados: {', '.join(EMAIL_DOMINIOS_PERMITIDOS)})"
            )
        limpos.append(d)
    return limpos


def _remontar_arquivos(pasta_arquivos: Path, arquivos, destino: Path) -> list[Path]:
    """Remonta cada arquivo do pedido (PDF, XLSX ou CSV) a partir de
    <pasta_arquivos>/<fid>/partes/<n>.json."""
    if not isinstance(arquivos, list) or not arquivos:
        raise ValueError("pedido sem arquivo")
    destino.mkdir(parents=True, exist_ok=True)
    caminhos, usados, total = [], set(), 0
    for meta in arquivos:
        fid = str(meta.get("fid") or "")
        n = int(meta.get("partes") or 0)
        extensao = Path(str(meta.get("nome") or "")).suffix.lower()
        if extensao not in TIPOS_ACEITOS:
            raise ValueError(f"tipo não aceito: {meta.get('nome')} (só {', '.join(TIPOS_ACEITOS)})")
        if not fid or n < 1:
            raise ValueError(f"arquivo sem conteúdo: {meta.get('nome')}")
        pedacos = []
        for pi in range(n):
            parte = pasta_arquivos / fid / "partes" / f"{pi}.json"
            if not parte.exists():
                raise ValueError(f"'{meta.get('nome')}' não está mais salvo (foi excluído?)")
            pedacos.append(_campos(parte).get("dados") or "")
        conteudo = base64.b64decode("".join(pedacos), validate=True)
        if not TIPOS_ACEITOS[extensao](conteudo):
            raise ValueError(f"o conteúdo de '{meta.get('nome')}' não é {extensao[1:].upper()}")
        total += len(conteudo)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("anexos passam do limite de 2,8 MB por e-mail")
        caminho = destino / _nome_seguro(meta.get("nome"), extensao, usados)
        caminho.write_bytes(conteudo)
        caminhos.append(caminho)
    return caminhos


def _corpo(pedido: dict, nome_solicitante: str | None, caminhos: list[Path]) -> str:
    linhas = []
    mensagem = (pedido.get("mensagem") or "").strip()
    linhas.append(mensagem or "Segue em anexo o(s) relatório(s) do ManagerVision.")
    linhas.append("")
    linhas.append("Anexos:")
    linhas.extend(f"  - {c.name}" for c in caminhos)
    linhas.append("")
    quem = nome_solicitante or "um usuário da SmartBreeder"
    cliente = f" ({pedido['cliente']})" if pedido.get("cliente") else ""
    linhas.append(f"—\nEnviado pelo Data Quality Monitor a pedido de {quem}{cliente}.")
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--nomes", type=Path)
    args = parser.parse_args()

    nomes = json.loads(args.nomes.read_text(encoding="utf-8")) if args.nomes else {}
    FILA_DIR.mkdir(parents=True, exist_ok=True)
    enviados = json.loads(REGISTRO_ENVIADOS.read_text(encoding="utf-8")) if REGISTRO_ENVIADOS.exists() else {}

    resultados = {}
    for item in sorted(args.out_dir.glob("pedidos/*/itens/*.json")):
        uid, pid = item.parent.parent.name, item.stem
        pedido = _campos(item)
        if pedido.get("status") not in (None, "pendente"):
            continue
        chave = f"{uid}/{pid}"
        res = {"uid": uid, "pid": pid}

        if chave in enviados:
            res.update(status="enviado", enviadoEm=enviados[chave]["enviadoEm"])
            resultados[chave] = res
            print(f"JÁ ENVIADO {chave} — só falta marcar o status")
            continue

        try:
            destinatarios = _validar_destinatarios(pedido.get("destinatarios"))
            caminhos = _remontar_arquivos(args.out_dir / "pedidos" / uid / "arquivos", pedido.get("arquivos"),
                                      FILA_DIR / pid)
            assunto = (pedido.get("assunto") or "").strip() or "Relatórios ManagerVision"
            enviar_email(caminhos, assunto=assunto, corpo=_corpo(pedido, nomes.get(uid), caminhos),
                         destinatarios=destinatarios)
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira status "erro" do pedido
            res.update(status="erro", erro=str(exc)[:500])
            print(f"ERRO {chave}: {exc}")
        else:
            agora = datetime.now(timezone.utc).isoformat()
            enviados[chave] = {"enviadoEm": agora, "destinatarios": destinatarios,
                               "arquivos": [c.name for c in caminhos]}
            REGISTRO_ENVIADOS.write_text(json.dumps(enviados, ensure_ascii=False, indent=1), encoding="utf-8")
            res.update(status="enviado", enviadoEm=agora)
            print(f"OK  {chave} -> {', '.join(destinatarios)} ({len(caminhos)} arquivo(s))")
        resultados[chave] = res

    saida = FILA_DIR / "resultado_ultima_execucao.json"
    saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(resultados)} pedido(s) processado(s). Resultado em {saida}")


if __name__ == "__main__":
    main()
