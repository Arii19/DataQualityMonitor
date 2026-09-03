---
name: atualizar-geometrias
description: Extrai talhões ativos + geometria de um ou mais clientes do smartbio (MCP) e regenera o cache de sobreposições (cache/<cliente>.json + Excel) usado pela tela do Data Quality Monitor. Use quando o usuário pedir "atualiza o(s) cliente(s) X" ou "roda a extração diária de geometrias".
---

# Atualizar geometrias duplicadas (Data Quality Monitor)

Repopula `cache/<cliente>.json` (e o Excel em `output/`) com dado fresco do
smartbio, pra cada cliente pedido. Rode isso no diretório do projeto
(`c:\Users\ariane.rodrigues\Documents\DataQualityMonitor`).

Clientes válidos (nomes exatos no smartbio):
`Atvos`, `SantaAdelia`, `Cevasa`, `CMAA`, `Guaira`, `GQQ`, `JPA`, `Cocal`, `IPE`

Se o pedido for "atualiza todos" ou não especificar, rode os 9. Se pedir um
nome que não bate exato com a lista (ex.: "Santa Adélia", "ipê"), mapeie pro
nome exato antes de seguir.

## Passo a passo, por cliente

1. **Extrair do smartbio** — chame `mcp__claude_ai_MCP_Smartbio__execute_query`
   com esse SQL (mesma consulta de sempre, `clients: ["<Cliente>"]`):

   ```sql
   SELECT c.IDTalhao, c.CodigoFazenda, c.NomeFazenda, c.Bloco, c.CodigoTalhao, c.Corte, c.Safra, c.AreaTotal, c.Reforma, c.Bloqueio, c.NomeUsina_Empresa_Unidade, c.Ativo, g.GeoJson
   FROM vw_bree_full.CadastroDeAreas c
   INNER JOIN vw_bree_full.Geometria g ON g.IDTalhao = c.IDTalhao AND g.idSafra = c.IDSafra
   WHERE c.DataInicialSafra <= GETDATE() AND c.DataFinalSafra > GETDATE() AND c.Bloqueio = 0
   ```

   O `AND g.idSafra = c.IDSafra` é essencial — resolve de vez o problema
   documentado em docs/especificacao_view_geometria_por_safra.md (a view
   `Geometria` podia devolver geometria de uma safra antiga pra um talhão
   sem desenho pra safra ativa). Antes disso as duas colunas de safra
   (`IDSafra` em `CadastroDeAreas`, `idSafra` em `Geometria`) não existiam;
   agora que existem dos dois lados, o join garante a geometria certa
   diretamente, sem precisar de nenhuma heurística por área ou por
   "safra mais comum do lote" (tentamos isso e reverteu — ver histórico do
   projeto e comentário em `_filtrar_por_safra_ativa` em
   `smartbio_cache.py`: vários clientes têm múltiplas safras/cortes
   legitimamente ativos ao mesmo tempo, então esse tipo de heurística some
   com dado real). **Não omita esse `AND` do join.**

   Isso devolve um `download_url` (expira em ~600s — baixe logo em seguida).
   Clientes grandes (Atvos, Cocal, IPE, CMAA, SantaAdelia) passam de 100MB;
   é normal, não precisa dividir por usina — um `execute_query` por cliente
   dá conta.

2. **Baixar o CSV** — `curl -sL -o raw/<Cliente>/dados.csv "<download_url>"`
   (crie a pasta `raw/<Cliente>/` se não existir). Isso substitui qualquer
   CSV antigo daquele cliente — não precisa limpar antes.

3. Pode disparar os `execute_query` de vários clientes em paralelo (chamadas
   independentes no mesmo turno) e ir baixando cada um assim que o
   `download_url` sair, em vez de fazer tudo em série.

   ⚠️ **Já aconteceu de vir com o dado do cliente errado quando disparado em
   paralelo**: o `download_url` recebido não correspondia ao cliente pedido
   (veio deslocado — a resposta de um cliente saiu associada ao request de
   outro). Por isso, **depois de baixar cada CSV, confirme a coluna
   `_cliente` da primeira linha antes de seguir pro próximo** — se não bater
   com o cliente esperado, pare e re-extraia aquele cliente sozinho (sem
   paralelismo) antes de continuar. Não rode `smartbio_cache.py` com um CSV
   não conferido.

## Depois de ter os CSVs de todos os clientes pedidos

Rode de uma vez (recalcula sobreposição + Motivo + grava cache/Excel):

```bash
cd "c:/Users/ariane.rodrigues/Documents/DataQualityMonitor"
./venv/Scripts/python smartbio_cache.py            # todos os 9, ou:
./venv/Scripts/python smartbio_cache.py <Cliente>  # um só
```

Isso é a mesma lógica de `app.py.intersect()` + `classificar_motivo()`,
aplicada aos CSVs em `raw/`. Client grande (Atvos/Cocal/IPE) pode levar
1-2 minutos pra rodar o sjoin espacial — normal.

## No final

Confirme o resultado lendo `cache/<Cliente>.json` (`total` e `gerado_em`) pra
cada cliente atualizado, e resuma pro usuário: quantos pares cada cliente
ficou e a que horas rodou. Não precisa reiniciar o `uvicorn` nem o frontend —
a API já lê o cache do disco a cada request.

Se algum `execute_query` der erro tipo `could not append value ... to the
builder` (mistura de tipo numa coluna, geralmente data), é porque alguma
coluna extra foi adicionada à consulta acima com tipo inconsistente entre
linhas — tire a coluna problemática ou explicite `CONVERT(varchar(10), col,
120)` nela, como documentado no histórico do projeto.
