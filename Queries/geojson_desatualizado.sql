-- Talhões cujo GeoJson (dbo.GeometriaGeoJson.GeoJsonSimplificada — o que o
-- smartbio/vw_mcp.Geometria_DEBUG expõe e o pipeline usa) não bate com o
-- DadosSHP de dbo.GeometriaDeMapa (o que a validação em banco usa).
--
-- Rodar no SSMS, no banco do cliente. Os IDTalhao com PctIgual < 70 vão
-- pra geojson_desatualizado.json (raiz do projeto), que tira do dashboard
-- todo par que envolva um deles. Entre ~80 e 95 é só ruído da simplificação
-- do GeoJson — ignorar.
--
-- Só trata GeoJson do tipo Polygon (a maioria). Caso conhecido: Ferrari,
-- fazenda 2008, talhão 1 (IDTalhao 44935) — DadosSHP de 10,7 ha, GeoJson
-- ainda com o desenho antigo de 37,6 ha em cima do talhão 2.

drop table if exists #GeoJsonDesatualizado;

;with base as (
  select gm.IDTalhao, gm.IDSafra, f.Codigo as Fazenda, t.Bloco, t.Codigo as Talhao, h.AreaTotal,
         iif(gm.DadosSHP.STSrid != 4326, geometry::STGeomFromText(gm.DadosSHPTexto, 4326), gm.DadosSHP).MakeValid() as Shp,
         json_query(gj.GeoJsonSimplificada, '$.geometry.coordinates') as Coords
  from dbo.HistDetalhado h
    join dbo.Talhao t on t.IDTalhao = h.IDTalhao
    join dbo.Fazenda f on f.IDFazenda = t.IDFazenda
    join dbo.GeometriaDeMapa gm on gm.IDTalhao = h.IDTalhao and gm.IDSafra = h.IDSafra
    join dbo.GeometriaGeoJson gj on gj.IDGeometriaDeMapa = gm.IDGeometriaDeMapa
  where h.DataInicialSafra <= getdate() and h.DataFinalSafra > getdate() and h.Bloqueio = 0
    and json_value(gj.GeoJsonSimplificada, '$.geometry.type') = 'Polygon'
),
conv as (
  select *, geometry::STGeomFromText('POLYGON((' +
           replace(replace(replace(replace(replace(replace(replace(Coords,
             ']],[[', ')$('), '],[', '|'), '[', ''), ']', ''), ',', ' '), '|', ','), ')$(', '),(')
           + '))', 4326).MakeValid() as Gj
  from base
)
select IDTalhao, IDSafra, Fazenda, Bloco, Talhao, AreaTotal,
       Shp.STArea() as AreaShp, Gj.STArea() as AreaGeoJson,
       cast(Shp.STIntersection(Gj).STArea() / nullif(Shp.STUnion(Gj).STArea(), 0) * 100 as decimal(6,2)) as PctIgual
into #GeoJsonDesatualizado
from conv;

select * from #GeoJsonDesatualizado
where PctIgual < 95
order by PctIgual;

-- só os IDs, já no formato da lista do geojson_desatualizado.json:
select string_agg(cast(IDTalhao as varchar(20)), ', ') as IDTalhao
from #GeoJsonDesatualizado
where PctIgual < 70;
