 select GM.IDGeometriaDeMapa, f.Codigo as fazenda, t.Bloco, t.Codigo AS Talhao,
    H.IDHistDetalhado, h.AnoSafra, gm.DataInclusao, gm.IDSafra, h.DataColheita,u.RazaoSocial, h.TomboSafra, h.Corte, gm.DadosSHP.STAsText() AS DadosSHP, gm.IDTalhao,
    tp.descricao as Vinculo, h.Reforma, h.SiglaExterna, h.DataPlantio
 from GeometriaDeMapa gm inner join Talhao t on t.IDTalhao =  gm.IDTalhao
        inner join HistDetalhado h on h.IDTalhao =gm.IDTalhao and h.IDFazenda = gm.IDFazenda and h.IDSafra = gm.IDSafra and h.IDUsina = gm.IDUsina
		inner join Fazenda f on f.IDFazenda = gm.IDFazenda and f.IDFazenda = t.IDFazenda
		inner join usina u on u.IDUsina = gm.IDUsina
		inner join tpvinculo tp on tp.idtpvinculo = f.idtpvinculo
		where h.DataInicialSafra <= GETDATE()
		and h.DataFinalSafra > GETDATE()
		and h.Bloqueio = 0