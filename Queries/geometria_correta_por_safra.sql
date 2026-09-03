-- Consulta de referência: amarra a geometria pela safra ativa via
-- GeometriaDeMapa+HistDetalhado (mesmo padrão usado por app.py
-- historicamente, antes de app.py perder a conexão de banco própria — ver
-- docs/especificacao_view_geometria_por_safra.md). Documenta o problema que
-- levou à correção aplicada em vw_bree_full.Geometria/CadastroDeAreas (que
-- agora expõem idSafra/IDSafra e são usadas direto pela extração da skill
-- atualizar-geometrias — não é mais necessário rodar isso manualmente pro
-- fluxo normal).
--
-- Ainda é útil como referência/depuração: rodar direto no SSMS, conectada
-- no banco do cliente que quiser inspecionar, pra conferir manualmente se
-- um talhão específico tem (ou não) geometria pra safra ativa.

SELECT
    gm.IDTalhao,
    gj.GeoJsonSimplificada AS GeoJson,
    gm.IDSafra
FROM dbo.GeometriaDeMapa gm
    INNER JOIN dbo.GeometriaGeoJson gj ON gj.IDGeometriaDeMapa = gm.IDGeometriaDeMapa
    INNER JOIN dbo.HistDetalhado h
        ON h.IDTalhao = gm.IDTalhao
        AND h.IDFazenda = gm.IDFazenda
        AND h.IDSafra = gm.IDSafra
        AND h.IDUsina = gm.IDUsina
WHERE
    h.DataInicialSafra <= GETDATE()
    AND h.DataFinalSafra > GETDATE()
    AND h.Bloqueio = 0
    -- AND gm.IDTalhao IN (...)  -- opcional, pra inspecionar talhões específicos
