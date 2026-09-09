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
   INNER JOIN (
       SELECT IDTalhao, idSafra, GeoJson,
              ROW_NUMBER() OVER (PARTITION BY IDTalhao, idSafra ORDER BY (SELECT NULL)) AS rn
       FROM vw_bree_full.Geometria_DEBUG
   ) g ON g.IDTalhao = c.IDTalhao AND g.idSafra = c.IDSafra AND g.rn = 1
   WHERE c.DataInicialSafra <= GETDATE() AND c.DataFinalSafra > GETDATE() AND c.Bloqueio = 0
   ```

   Usa `Geometria_DEBUG`, não `Geometria` — a `Geometria` original só
   devolve uma linha por `IDTalhao` (às vezes a de uma safra errada,
   escondendo linhas válidas de outra safra que existem na tabela crua). A
   `Geometria_DEBUG` é um passthrough sem essa seleção — mas por ser
   passthrough, também expõe duplicatas reais da tabela crua: já achamos
   talhão com **52 linhas idênticas** pra exatamente o mesmo
   `(IDTalhao, idSafra)` (SantaAdelia, IDTalhao 52046). Sem o
   `ROW_NUMBER()`/`rn = 1` acima, isso vira fan-out no join (1 talhão × 52
   linhas de geometria = 52 "cópias" do mesmo talhão), e o cálculo de
   sobreposição as compara entre si como se fossem talhões diferentes —
   gerando uma explosão de pares falsos (chegou a inflar a SantaAdelia de
   73 pra 3875 "pares"). O `ROW_NUMBER()` garante **uma linha por
   `(IDTalhao, idSafra)`** antes do join com `CadastroDeAreas`, sem
   depender de qual das duplicatas é "a certa" (dentro do mesmo talhão +
   safra, presume-se que sejam a mesma geometria ou uma reentrada
   redundante — qualquer uma serve). Detalhe completo (incluindo por que a
   heurística "safra mais comum do lote" foi tentada e revertida antes
   dessa correção) em docs/especificacao_view_geometria_por_safra.md.
   **Não troque `Geometria_DEBUG` de volta por `Geometria`, não omita o
   `AND` do join, e não tire o `ROW_NUMBER()`/`rn = 1`.**

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
