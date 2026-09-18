"""Manda o e-mail diário de geometrias duplicadas.

Clientes cujo destinatário (config.destinatarios_do_cliente) bate com
EMAIL_RECIPIENTS do .env vão todos JUNTOS num único e-mail, com um Excel só
que tem uma aba por usina (não por cliente) — hoje isso é todo mundo, já que
config.EMAIL_POR_CLIENTE está vazio. Se algum cliente ganhar ali um
destinatário diferente do padrão, ele sai desse grupo consolidado e passa a
ser mandado separado (Excel próprio, gerado por smartbio_cache.py, e-mail só
pra ele) — assim como funcionava antes desse consolidado existir.

Roda automaticamente todo dia, logo após /atualizar-geometrias, dentro de
scripts/atualizar_diario_geometrias.ps1.

Rodar sem argumentos:
    python scripts/enviar_email_geometrias.py
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import EMAIL_RECIPIENTS, destinatarios_do_cliente  # noqa: E402
from email_utils import enviar_email  # noqa: E402
from smartbio_cache import CACHE_DIR, CLIENTES, OUTPUT_DIR  # noqa: E402


def _ultimo_excel(cliente: str):
    candidatos = sorted(OUTPUT_DIR.glob(f"{cliente}_duplicados_*.xlsx"))
    return candidatos[-1] if candidatos else None


def _carregar_itens(cliente: str):
    caminho = CACHE_DIR / f"{cliente}.json"
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))["itens"]


def _nome_aba(nome: str, usados: set) -> str:
    """Nome de aba do Excel: só até 31 caracteres, sem os caracteres que o
    Excel recusa (: \\ / ? * [ ]), sem repetir (duas usinas não podem cair na
    mesma aba)."""
    limpo = re.sub(r'[:\\/?*\[\]]', "-", nome or "Sem usina").strip() or "Sem usina"
    limpo = limpo[:31]
    base, sufixo_n = limpo, 2
    while limpo in usados:
        sufixo = f" ({sufixo_n})"
        limpo = base[: 31 - len(sufixo)] + sufixo
        sufixo_n += 1
    usados.add(limpo)
    return limpo


def _gerar_excel_por_usina(clientes: list[str], timestamp: str) -> Path | None:
    """Junta os pares de todos os `clientes` informados e monta um único
    Excel com uma aba por usina (Usina1 do par; Usina2 quase sempre é a
    mesma). Retorna None se nenhum dos clientes tiver cache ainda."""
    linhas_por_usina = defaultdict(list)
    for cliente in clientes:
        itens = _carregar_itens(cliente)
        if not itens:
            continue
        for item in itens:
            usina = item.get("Usina1") or item.get("Usina2") or "Sem usina"
            linhas_por_usina[usina].append(item)

    if not linhas_por_usina:
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    caminho = OUTPUT_DIR / f"geometrias_duplicadas_consolidado_{timestamp}.xlsx"
    usados = set()
    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for usina in sorted(linhas_por_usina):
            df = pd.DataFrame(linhas_por_usina[usina]).drop(
                columns=["id", "Geometria1", "Geometria2"], errors="ignore"
            )
            df.to_excel(writer, sheet_name=_nome_aba(usina, usados), index=False)

    return caminho


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    grupo_padrao = tuple(sorted(EMAIL_RECIPIENTS))

    consolidados = []  # clientes que caem no e-mail junto (destinatário == EMAIL_RECIPIENTS)
    individuais = []  # (cliente, destinatarios) com destinatário próprio, diferente do padrão

    for cliente in CLIENTES:
        destinatarios = destinatarios_do_cliente(cliente)
        if tuple(sorted(destinatarios)) == grupo_padrao:
            consolidados.append(cliente)
        else:
            individuais.append((cliente, destinatarios))

    enviados, falhas = [], []

    if consolidados:
        arquivo = _gerar_excel_por_usina(consolidados, timestamp)
        if not arquivo:
            print(f"Consolidado: nenhum cache encontrado ainda pra {consolidados} — pulado")
        else:
            try:
                enviar_email(
                    arquivo,
                    assunto="Geometrias Duplicadas - Consolidado",
                    corpo=(
                        "Segue em anexo o relatório de geometrias duplicadas de "
                        f"{', '.join(consolidados)}, uma aba por usina."
                    ),
                    destinatarios=list(EMAIL_RECIPIENTS),
                )
                enviados.append(f"Consolidado ({', '.join(consolidados)})")
                print(f"OK  Consolidado -> {', '.join(EMAIL_RECIPIENTS)} ({arquivo.name})")
            except Exception as exc:
                falhas.append(("Consolidado", str(exc)))
                print(f"ERRO Consolidado: {exc}")

    for cliente, destinatarios in individuais:
        arquivo = _ultimo_excel(cliente)
        if not arquivo:
            print(f"{cliente}: sem Excel gerado — pulado")
            continue
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
    print(f"Enviados: {len(enviados)} ({', '.join(enviados)})")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
