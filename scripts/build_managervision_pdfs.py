"""Gera (em lote) o PDF de todos os relatórios do ManagerVision já em cache
(cache/managervision/<cliente>.json), um cliente por vez — login uma vez por
cliente/domínio, reaproveitado pros relatórios seguintes daquele cliente.

Aqui só gera e mede os arquivos em
output/managervision_pdf/<cliente>/<chart_id>.pdf — a tela (local e a
publicada via túnel, scripts/iniciar_tela.ps1) lê esses PDFs direto do
disco, sem precisar de nenhum passo de build/embed separado.

Rodar com:
    python scripts/build_managervision_pdfs.py
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from managervision_pdf import exportar_varios_pdf  # noqa: E402

CACHE_DIR = BASE_DIR / "cache" / "managervision"
OUTPUT_DIR = BASE_DIR / "output" / "managervision_pdf"

CLIENTES = ["Atvos", "SantaAdelia", "Cevasa", "CMAA", "Guaira", "GQQ", "JPA", "Cocal", "IPE"]


def main():
    total_bytes = 0
    total_ok = 0
    total_erro = 0
    inicio_geral = time.time()

    for cliente in CLIENTES:
        caminho_cache = CACHE_DIR / f"{cliente}.json"
        if not caminho_cache.exists():
            print(f"{cliente}: sem cache, pulando")
            continue

        dados = json.loads(caminho_cache.read_text(encoding="utf-8"))
        itens = dados["itens"]
        destino = OUTPUT_DIR / cliente
        print(f"\n=== {cliente}: {len(itens)} relatorio(s) ===")

        t0 = time.time()
        try:
            resultados = exportar_varios_pdf(itens, destino)
        except Exception as exc:
            print(f"  ERRO GERAL no cliente {cliente}: {exc}")
            total_erro += len(itens)
            continue

        exportados_ids = {item["chart_id"] for item, _ in resultados}
        for item in itens:
            if item["chart_id"] not in exportados_ids:
                print(f"  FALHOU: {item['titulo']}")
                total_erro += 1

        for item, caminho in resultados:
            tamanho = caminho.stat().st_size
            total_bytes += tamanho
            total_ok += 1
            print(f"  OK: {item['titulo'][:60]:60s} {tamanho/1024:7.1f} KB")

        print(f"  ({cliente} levou {time.time()-t0:.1f}s)")

    print(f"\n=== RESUMO ===")
    print(f"OK: {total_ok}  ERRO: {total_erro}")
    print(f"Total bruto: {total_bytes/1024/1024:.2f} MB")
    print(f"Estimado em base64 (~1.37x): {total_bytes*1.37/1024/1024:.2f} MB")
    print(f"Tempo total: {(time.time()-inicio_geral)/60:.1f} min")


if __name__ == "__main__":
    main()
