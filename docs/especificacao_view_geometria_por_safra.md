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

## Correção aplicada

`vw_bree_full.Geometria` passou a expor `idSafra` (identificador da safra
associada), e `vw_bree_full.CadastroDeAreas` passou a expor `IDSafra`
também. Com as duas colunas disponíveis, a extração do Data Quality Monitor
(`.claude/skills/atualizar-geometrias/SKILL.md`) amarra a geometria certa
direto no join:

```sql
SELECT c.IDTalhao, c.CodigoFazenda, c.NomeFazenda, c.Bloco, c.CodigoTalhao, c.Corte, c.Safra, c.AreaTotal, c.Reforma, c.Bloqueio, c.NomeUsina_Empresa_Unidade, c.Ativo, g.GeoJson
FROM vw_bree_full.CadastroDeAreas c
INNER JOIN vw_bree_full.Geometria g ON g.IDTalhao = c.IDTalhao AND g.idSafra = c.IDSafra
WHERE c.DataInicialSafra <= GETDATE() AND c.DataFinalSafra > GETDATE() AND c.Bloqueio = 0
```

Isso garante a geometria da safra realmente ativa de cada talhão, sem
precisar de nenhuma heurística de mitigação (o `AND g.idSafra = c.IDSafra`
não pode ser omitido — sem ele, volta o problema de geometria
desatualizada). Validado nos talhões 1037/674 do GQQ (não retornam mais
nenhuma linha, correto — sem geometria pra safra ativa) e 5613/6027
(retornam com `idSafra` batendo dos dois lados).

### Tentativa alternativa descartada (heurística client-side)

No caminho até a correção real, foi tentada uma mitigação client-side em
`smartbio_cache.py` (`_filtrar_por_safra_ativa()`): comparar o `idSafra` de
cada talhão com o mais frequente (moda) do cliente, descartando quem não
batesse. **Foi revertida**: vários clientes (Cocal, GQQ) têm múltiplas
safras/cortes **legitimamente ativos ao mesmo tempo**, em proporções
comparáveis (não é uma maioria certa com poucos outliers errados) — um
talhão ativo dentro do período deve contar independente de qual safra for
a mais comum no lote. A função continua no código, desativada de propósito
(retorna o `df` intacto), com o histórico completo no comentário.
