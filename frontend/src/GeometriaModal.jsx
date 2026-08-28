import { useState } from 'react'
import './GeometriaModal.css'

const TAMANHO = 420
const PADDING = 24

function extrairAneis(geometria) {
  if (!geometria) return []
  if (geometria.type === 'Polygon') return geometria.coordinates
  if (geometria.type === 'MultiPolygon') return geometria.coordinates.flat()
  return []
}

function calcularBBox(gruposDeAneis) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  gruposDeAneis.forEach((aneis) => {
    aneis.forEach((anel) => {
      anel.forEach(([x, y]) => {
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      })
    })
  })

  return { minX, minY, maxX, maxY }
}

function construirPath(aneis, bbox) {
  const largura = bbox.maxX - bbox.minX || 1
  const altura = bbox.maxY - bbox.minY || 1
  const area = TAMANHO - PADDING * 2
  const escala = Math.min(area / largura, area / altura)
  const deslocX = (TAMANHO - largura * escala) / 2
  const deslocY = (TAMANHO - altura * escala) / 2

  const projetar = ([x, y]) => {
    const px = (x - bbox.minX) * escala + deslocX
    const py = TAMANHO - ((y - bbox.minY) * escala + deslocY) // inverte o eixo Y (geo cresce pra cima)
    return `${px.toFixed(2)},${py.toFixed(2)}`
  }

  return aneis
    .map((anel) => `M${anel.map(projetar).join('L')}Z`)
    .join(' ')
}

export default function GeometriaModal({ par, geometria, carregando, erro, onClose }) {
  // 'ambos' mostra os dois talhões (com a sobreposição em destaque); os outros
  // dois isolam só um deles — mas o enquadramento continua o mesmo nos três
  // modos, calculado sempre a partir das duas geometrias, pra não "pular"
  const [modo, setModo] = useState('ambos')

  const aneis1 = extrairAneis(geometria?.geometria1)
  const aneis2 = extrairAneis(geometria?.geometria2)
  const temDesenho = aneis1.length > 0 || aneis2.length > 0
  const bbox = temDesenho ? calcularBBox([aneis1, aneis2].filter((a) => a.length)) : null
  const path1 = aneis1.length ? construirPath(aneis1, bbox) : ''
  const path2 = aneis2.length ? construirPath(aneis2, bbox) : ''

  const mostrarTalhao1 = modo === 'ambos' || modo === 'talhao1'
  const mostrarTalhao2 = modo === 'ambos' || modo === 'talhao2'

  return (
    <div className="modal-fundo" onClick={onClose}>
      <div className="modal-caixa" onClick={(e) => e.stopPropagation()}>
        <div className="modal-cabecalho">
          <h2>Sobreposição de geometrias</h2>
          <button className="botao-secundario" onClick={onClose}>Fechar</button>
        </div>

        {par && (
          <p className="modal-info">
            <strong>Talhão 1:</strong> {par.Fazenda1}/{par.Bloco1}/{par.Talhao1}
            {'  '}×{'  '}
            <strong>Talhão 2:</strong> {par.Fazenda2}/{par.Bloco2}/{par.Talhao2}
            {'  '}·{'  '}
            <strong>Sobreposição:</strong> {Number(par.PercentualSobreposicaoGeral).toFixed(2)}%
          </p>
        )}

        {carregando && <p>Carregando geometrias…</p>}
        {erro && <p className="erro">{erro}</p>}

        {!carregando && !erro && (
          <>
            <svg
              width={TAMANHO}
              height={TAMANHO}
              viewBox={`0 0 ${TAMANHO} ${TAMANHO}`}
              className="svg-geometrias"
            >
              {mostrarTalhao1 && path1 && <path d={path1} fillRule="evenodd" className="geom geom-1" />}
              {mostrarTalhao2 && path2 && <path d={path2} fillRule="evenodd" className="geom geom-2" />}
              {!temDesenho && (
                <text x={TAMANHO / 2} y={TAMANHO / 2} textAnchor="middle" className="sem-geometria">
                  Sem geometria pra desenhar
                </text>
              )}
            </svg>
            <div className="legenda">
              <button
                type="button"
                className={`legenda-item ${modo === 'talhao1' ? 'ativo' : ''}`}
                onClick={() => setModo('talhao1')}
              >
                <i className="cor cor-1" /> Talhão 1
              </button>
              <button
                type="button"
                className={`legenda-item ${modo === 'talhao2' ? 'ativo' : ''}`}
                onClick={() => setModo('talhao2')}
              >
                <i className="cor cor-2" /> Talhão 2
              </button>
              <button
                type="button"
                className={`legenda-item ${modo === 'ambos' ? 'ativo' : ''}`}
                onClick={() => setModo('ambos')}
              >
                <i className="cor cor-sobreposicao" /> Área sobreposta
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
