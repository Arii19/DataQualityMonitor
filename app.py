"""Classificação do motivo de cada par sobreposto, usada por
smartbio_cache.calcular_sobreposicoes()."""

import numpy as np


def classificar_motivo(pares):
    """`pares` precisa ter `PercentualSobreposto1`/`PercentualSobreposto2`
    (percentual de cada talhão individualmente, além do geral) —
    `smartbio_cache.calcular_sobreposicoes()` já calcula os dois antes de
    chamar esta função."""
    mesma_fazenda = pares["Fazenda1"] == pares["Fazenda2"]
    mesmo_talhao = pares["Talhao1"] == pares["Talhao2"]
    mesmo_nome_fazenda = pares["NomeFazenda_1"] == pares["NomeFazenda_2"]
    quase_identico = pares["PercentualSobreposicaoGeral"] > 90

    # um dos talhões está quase inteiro dentro do outro (>90% da área DELE,
    # não da união) — sinal de subdivisão (ex.: sub-talhão registrado dentro
    # do maior), não erro de limite entre vizinhos. Confirmado em dados reais
    # (Atvos).
    contido = (pares["PercentualSobreposto1"] > 90) | (pares["PercentualSobreposto2"] > 90)

    condicoes = [
        mesma_fazenda & mesmo_talhao,
        mesmo_nome_fazenda & ~mesma_fazenda,
        mesma_fazenda & quase_identico,
        mesma_fazenda & contido,
        mesma_fazenda,
    ]
    motivos = [
        "Mesmo talhão físico (ciclo/safra anterior não foi fechado)",
        "Fazenda cadastrada com código duplicado",
        "Códigos de talhão diferentes quase 100% sobrepostos",
        "Provável subdivisão — área menor contida dentro do talhão maior",
        "Talhões vizinhos com sobreposição parcial de limite",
    ]
    return np.select(condicoes, motivos, default="Fazendas diferentes com sobreposição de limite")
