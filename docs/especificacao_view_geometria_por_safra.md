# Especificação: correção da view `vw_bree_full.Geometria` (aplicada)

## Problema (histórico)

A view `vw_bree_full.Geometria`, originalmente exposta ao MCP do smartbio,
tinha só 2 colunas:

| Coluna | Tipo |
|---|---|
| `IDTalhao` | string |
| `GeoJson` | string |

Ela devolvia **uma única geometria por `IDTalhao`**, sem nenhuma referência
de safra (`IDSafra`) — pegando "a última geometria digitalizada" ou algo
equivalente, sem relação com qual safra está ativa agora.

Isso causava **falsos positivos de sobreposição** no Data Quality Monitor:
um talhão podia não ter geometria nenhuma pra safra ativa (ex.: talhão
novo, ainda não desenhado) e mesmo assim a view devolvia um contorno
antigo, de uma safra/corte anterior — que aparentava sobrepor talhões
vizinhos sem que isso fosse real hoje.

### Caso confirmado (cliente GQQ)

- **IDTalhao 1037** (Fazenda 13011, Talhão 2104): a `AreaTotal` oficial pra
  safra ativa era **0,00 ha**, e uma consulta direta em `GeometriaDeMapa`
  amarrada por `IDSafra` (ver query de referência abaixo) **não retornava
  nenhuma linha** pra esse talhão — ele não tinha geometria pra safra ativa.
- Mesmo assim, `vw_bree_full.Geometria` devolvia um `GeoJson` de **17,14 ha**
  pra esse `IDTalhao` — de uma safra/corte anterior — que o Data Quality
  Monitor então reportava como sobreposto com o talhão vizinho 5613 (falso
  positivo).

### Consulta de referência (correta, roda direto no banco, não via MCP)

```sql
select gm.DadosSHP.STGeometryType() AS tipo_geometria, GM.IDGeometriaDeMapa,
  f.Codigo as fazenda, t.Bloco, t.Codigo AS Talhao,
  H.IDHistDetalhado, h.AnoSafra, gm.DataInclusao, gm.IDSafra, h.DataColheita,
  u.RazaoSocial, h.TomboSafra, h.Corte, gm.DadosSHP, gm.IDTalhao
from GeometriaDeMapa gm
  inner join Talhao t on t.IDTalhao = gm.IDTalhao
  inner join HistDetalhado h on h.IDTalhao = gm.IDTalhao
    and h.IDFazenda = gm.IDFazenda and h.IDSafra = gm.IDSafra
    and h.IDUsina = gm.IDUsina
  inner join Fazenda f on f.IDFazenda = gm.IDFazenda and f.IDFazenda = t.IDFazenda
  inner join usina u on u.IDUsina = gm.IDUsina
where h.DataInicialSafra <= GETDATE()
  and h.DataFinalSafra > GETDATE()
  and h.Bloqueio = 0
```

## Tentativa 1: expor `idSafra`/`IDSafra` na view original (insuficiente)

`vw_bree_full.Geometria` passou a expor `idSafra` (identificador da safra
associada), e `vw_bree_full.CadastroDeAreas` passou a expor `IDSafra`
também. A ideia era juntar por `g.IDTalhao = c.IDTalhao AND g.idSafra =
c.IDSafra` — mas isso **não bastou**: a view `Geometria` continuava
devolvendo só **uma linha por `IDTalhao`** (escolhida por algum critério
interno, não necessariamente a da safra ativa), então linhas válidas de
outras safras que existiam na tabela crua ficavam escondidas mesmo com a
coluna disponível.

**Prova concreta**: o talhão 119679498 (Atvos) tem safra ativa = 32.
`vw_bree_full.Geometria` só mostrava esse talhão com `idSafra=20040`
(geometria de outra safra). Só que consultando a tabela crua
(`GeometriaGeoJson`/`GeometriaDeMapa`) direto, a linha com `idSafra=32`
**existia de verdade** — a view estava escondendo ela. Isso gerava o
problema oposto do original: duplicidades reais ficavam invisíveis (74+
pares confirmados só no cliente Atvos).

### Tentativa descartada: heurística client-side por moda

No caminho até a correção real, foi tentada uma mitigação client-side em
`smartbio_cache.py` (`_filtrar_por_safra_ativa()`): comparar o `idSafra` de
cada talhão com o mais frequente (moda) do cliente, descartando quem não
batesse. **Foi revertida**: vários clientes (Cocal, GQQ) têm múltiplas
safras/cortes **legitimamente ativos ao mesmo tempo**, em proporções
comparáveis (não é uma maioria certa com poucos outliers errados) — um
talhão ativo dentro do período deve contar independente de qual safra for
a mais comum no lote. A função continua no código, desativada de propósito
(retorna o `df` intacto), com o histórico completo no comentário.

## Correção aplicada: `vw_bree_full.Geometria_DEBUG` (passthrough)

Foi criada uma segunda view, `vw_bree_full.Geometria_DEBUG`, como
passthrough **sem** a seleção de "uma geometria por talhão" — mesmas 3
colunas (`IDTalhao`, `GeoJson`, `idSafra`), mas com uma linha por
combinação real de `(IDTalhao, idSafra)` existente na tabela crua. A
extração do Data Quality Monitor (`.claude/skills/atualizar-geometrias/SKILL.md`)
usa essa view:

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

O `ROW_NUMBER()`/`rn = 1` é necessário porque, sendo passthrough, a view
também expõe duplicatas reais da tabela crua — chegamos a achar um talhão
(SantaAdelia, IDTalhao 52046) com **52 linhas idênticas** pra exatamente o
mesmo `(IDTalhao, idSafra)`. Sem essa deduplicação, o join gera fan-out (1
talhão × 52 linhas = 52 "cópias"), e o cálculo de sobreposição as compara
entre si como talhões diferentes — chegou a inflar a SantaAdelia de 73
para 3875 "pares" só com esse artefato. Com `rn = 1`, sobra exatamente uma
linha por `(IDTalhao, idSafra)`, e como todas as duplicatas dentro do
mesmo talhão+safra são a mesma geometria (ou reentrada redundante), não
importa qual delas o `ROW_NUMBER()` escolhe.

Essa combinação (view passthrough + join por `IDTalhao`+`idSafra` +
deduplicação) resolve os dois problemas de vez, sem nenhuma heurística por
área ou por safra mais comum:

- Validado nos talhões 1037/674 do GQQ: não retornam mais nenhuma linha
  (correto — sem geometria pra safra ativa).
- Validado no talhão 119679498 da Atvos: agora retorna com `idSafra=32`
  (a safra ativa certa), não mais o `20040` desatualizado.
- Validado no talhão 52046 da SantaAdelia: agora retorna 1 linha só, não
  52.

**Não use `vw_bree_full.Geometria` (a original) nem omita o `ROW_NUMBER()`
— os dois passos são necessários.**
