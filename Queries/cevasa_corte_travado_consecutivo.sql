-- Monitoramento Cevasa: detecta talhao com o mesmo corte em 2+ safras
-- consecutivas ja colhidas.
--
-- Contexto: a regra em integracao/src/Customer/Cevasa/Atualizacoes/
-- SP_AT_INT_TEMPORARIAS.sql (tabela int.TEMP_FORCACORTE) corrige o corte
-- quando o PIMS nao avanca o estagio apos a colheita, comparando cada safra
-- com a safra imediatamente anterior (T.ANOSAFRA - 1) e usando o proximo
-- estagio cadastrado a partir do estagio atual do PIMS. Essa correcao da
-- um unico passo a frente a partir do dado cru do PIMS, entao so funciona
-- certo se o talhao travar por UMA safra. Se o PIMS mantiver o mesmo
-- estagio por 2+ safras seguidas, a correcao fica presa no mesmo corte (nao
-- acumula o numero de safras travadas), e duas (ou mais) safras consecutivas
-- ja colhidas acabam aparecendo com o mesmo numero de corte na
-- int.INT_SAFRATALHAO.
--
-- Nenhum caso assim foi observado ate agora (os 1623 casos corrigidos em
-- 2026-10 eram todos de uma unica safra travada). Essa query e so um alerta
-- preventivo - nao corrige nada, so lista. Rodar manualmente no SSMS,
-- conectado no banco da Cevasa, de preferencia logo apos uma integracao.
-- Se vier alguma linha, vale investigar se a regra precisa evoluir pra
-- contar a sequencia de safras travadas em vez de dar so um passo.

SELECT
    T.CODIGO_FAZENDA,
    T.BLOCO,
    T.CODIGO_TALHAO,
    ANT.ANOSAFRA AS SAFRA_ANTERIOR,
    ANT.CORTE AS CORTE_SAFRA_ANTERIOR,
    ANT.DATACOLHEITA AS DATACOLHEITA_SAFRA_ANTERIOR,
    T.ANOSAFRA AS SAFRA_ATUAL,
    T.CORTE AS CORTE_SAFRA_ATUAL,
    T.DATACOLHEITA AS DATACOLHEITA_SAFRA_ATUAL
FROM int.INT_SAFRATALHAO T
    INNER JOIN int.INT_SAFRATALHAO ANT
        ON ANT.CODIGO_FAZENDA = T.CODIGO_FAZENDA
        AND ANT.BLOCO = T.BLOCO
        AND ANT.CODIGO_TALHAO = T.CODIGO_TALHAO
        AND CAST(ANT.ANOSAFRA AS INT) = CAST(T.ANOSAFRA AS INT) - 1
        AND ANT.CORTE = T.CORTE
WHERE
    T.DATACOLHEITA IS NOT NULL
    AND ANT.DATACOLHEITA IS NOT NULL
ORDER BY
    T.CODIGO_FAZENDA,
    T.BLOCO,
    T.CODIGO_TALHAO,
    T.ANOSAFRA;
