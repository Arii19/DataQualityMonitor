---
name: atualizar-relatorios-managervision
description: Atualiza cache/managervision/<cliente>.json com a lista de relatórios (charts) registrados no ManagerVision (MCP Smartbio) para os clientes do Data Quality Monitor, e gera um PDF de cada um. Use quando o usuário pedir "atualiza os relatórios do ManagerVision" ou como parte da atualização diária do dashboard.
---

# Atualizar relatórios ManagerVision (Data Quality Monitor)

Repopula `cache/managervision/<cliente>.json` (metadado dos relatórios) e os
PDFs em `output/managervision_pdf/<cliente>/`, usados pelo painel
"Relatórios ManagerVision" da tela local e do Artifact (`dist/dashboard.html`
via `scripts/build_dashboard.py`). Rode no diretório do projeto.

Clientes válidos (mesma lista de `atualizar-geometrias`) e URL de acesso de
cada um (pra montar o link "Visualizar" — `<url_acesso>ManagerVision/Chart/<chart_id>`):

| Cliente | url_acesso |
|---|---|
| Atvos | https://atvos.smartbreeder.com.br/ |
| SantaAdelia | https://santaadelia.smartbreeder.com.br/ |
| Cevasa | https://cevasa.smartbreeder.com.br/ |
| CMAA | https://cmaa.smartbreeder.com.br/ |
| Guaira | https://guaira.smartbreeder.com.br/ |
| GQQ | https://gqq.smartbreeder.com.br/ |
| JPA | https://jpa.smartbreeder.com.br/ |
| Cocal | https://cocal.smartbreeder.com.br/ |
| IPE | https://ipe.smartbreeder.com.br/ |

Se o pedido for "atualiza todos" ou não especificar, rode os 9.

## Passo 1 — metadado (precisa do MCP)

Pra cada cliente, chame `mcp__claude_ai_MCP_Smartbio__list_charts(nome_cliente=<Cliente>)`
e grave `cache/managervision/<Cliente>.json` nesse formato (sobrescreve o
anterior; se `list_charts` devolver lista vazia, ainda assim não precisa
gravar arquivo — a API já trata ausência de arquivo como lista vazia):

```json
{
  "cliente": "<Cliente>",
  "gerado_em": "<timestamp ISO 8601 UTC de agora>",
  "itens": [
    {
      "chart_id": "<chart_id devolvido>",
      "titulo": "<titulo devolvido>",
      "description": "<description devolvida>",
      "url": "<url_acesso do cliente>ManagerVision/Chart/<chart_id>",
      "criado_por": "<created_by devolvido>",
      "criado_em": "<created_at devolvido>"
    }
  ]
}
```

Pode disparar os `list_charts` de vários clientes em paralelo (chamadas
independentes no mesmo turno) — diferente do `execute_query` de geometrias,
aqui não tem histórico de vir cliente errado, mas confira o campo `cliente`
no topo de cada JSON gravado antes de seguir, por segurança.

## Passo 2 — gerar os PDFs (não precisa do MCP)

Depois de atualizar os JSONs, rode via Bash (dê um timeout generoso — no
mínimo 600000ms/10min; com os ~47 relatórios atuais dos 9 clientes leva
uns 8 minutos, login por cliente + ~10s por relatório):

```bash
./venv/Scripts/python scripts/build_managervision_pdfs.py
```

Isso loga no ManagerVision via Playwright (usuário/senha do `.env`,
`MANAGERVISION_USER`/`MANAGERVISION_PASSWORD`) e salva um PDF de cada
relatório em `output/managervision_pdf/<cliente>/<chart_id>.pdf`. Se esse
passo falhar (ex.: login mudou, seletor da página mudou), pare e reporte o
erro — não é algo pra tentar contornar sozinho.

## No final

Confirme lendo `cache/managervision/<Cliente>.json` (quantos itens) pra cada
cliente atualizado, e quantos PDFs foram gerados (o script já imprime um
resumo OK/ERRO no final). Resuma pro usuário. Isso não regenera sozinho o
`dist/dashboard.html` — isso é `scripts/build_dashboard.py`, que também
decide quais PDFs cabem embutidos no limite de 16MB do Artifact.
