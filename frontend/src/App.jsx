import { useCallback, useEffect, useState } from 'react'
import './App.css'
import GeometriaModal from './GeometriaModal'

const API_URL = 'http://127.0.0.1:8001'

const FILTROS_INICIAIS = {
  fazenda: '',
  usina: '',
  safra: '',
  percentualMinimo: '',
}

function montarQuery(filtros) {
  const params = new URLSearchParams()
  if (filtros.fazenda) params.set('fazenda', filtros.fazenda)
  if (filtros.usina) params.set('usina', filtros.usina)
  if (filtros.safra) params.set('safra', filtros.safra)
  if (filtros.percentualMinimo) params.set('percentual_minimo', filtros.percentualMinimo)
  return params.toString()
}

function formatarPercentual(valor) {
  if (valor === null || valor === undefined) return '-'
  return `${Number(valor).toFixed(2)}%`
}

function temaInicial() {
  try {
    const salvo = localStorage.getItem('tema')
    if (salvo === 'light' || salvo === 'dark') return salvo
  } catch {
    // localStorage indisponível (ex.: navegação privada) — cai pro padrão do sistema
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function useTema() {
  const [tema, setTema] = useState(temaInicial)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tema)
    try {
      localStorage.setItem('tema', tema)
    } catch {
      // ignora se não for possível persistir
    }
  }, [tema])

  return [tema, setTema]
}

export default function App() {
  const [tema, setTema] = useTema()
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS)
  const [itens, setItens] = useState([])
  const [total, setTotal] = useState(null)
  const [ultimaExecucao, setUltimaExecucao] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [rodandoPipeline, setRodandoPipeline] = useState(false)
  const [erro, setErro] = useState(null)
  const [parSelecionado, setParSelecionado] = useState(null)
  const [geometria, setGeometria] = useState(null)
  const [carregandoGeometria, setCarregandoGeometria] = useState(false)
  const [erroGeometria, setErroGeometria] = useState(null)

  const buscarDuplicados = useCallback(async (filtrosAtuais) => {
    setCarregando(true)
    setErro(null)
    try {
      const query = montarQuery(filtrosAtuais)
      const resposta = await fetch(`${API_URL}/api/duplicados${query ? `?${query}` : ''}`)
      if (resposta.status === 404) {
        setItens([])
        setTotal(0)
        setUltimaExecucao(null)
        return
      }
      if (!resposta.ok) {
        throw new Error(`Falha ao buscar duplicados (HTTP ${resposta.status})`)
      }
      const dados = await resposta.json()
      setItens(dados.itens)
      setTotal(dados.total)
      setUltimaExecucao(dados.ultima_execucao)
    } catch (e) {
      setErro(e.message)
    } finally {
      setCarregando(false)
    }
  }, [])

  useEffect(() => {
    buscarDuplicados(FILTROS_INICIAIS)
  }, [buscarDuplicados])

  async function handleRodarPipeline() {
    setRodandoPipeline(true)
    setErro(null)
    try {
      const resposta = await fetch(`${API_URL}/api/pipeline/rodar`, { method: 'POST' })
      if (!resposta.ok) {
        const detalhe = await resposta.json().catch(() => null)
        throw new Error(detalhe?.detail || `Falha ao rodar o pipeline (HTTP ${resposta.status})`)
      }
      await buscarDuplicados(filtros)
    } catch (e) {
      setErro(e.message)
    } finally {
      setRodandoPipeline(false)
    }
  }

  function handleFiltrarSubmit(event) {
    event.preventDefault()
    buscarDuplicados(filtros)
  }

  function handleLimparFiltros() {
    setFiltros(FILTROS_INICIAIS)
    buscarDuplicados(FILTROS_INICIAIS)
  }

  function handleExportarExcel() {
    window.open(`${API_URL}/api/duplicados/excel`, '_blank')
  }

  async function handleSelecionarPar(par) {
    setParSelecionado(par)
    setGeometria(null)
    setErroGeometria(null)
    setCarregandoGeometria(true)
    try {
      const resposta = await fetch(`${API_URL}/api/duplicados/${par.id}/geometria`)
      if (!resposta.ok) {
        const detalhe = await resposta.json().catch(() => null)
        throw new Error(detalhe?.detail || `Falha ao buscar geometria (HTTP ${resposta.status})`)
      }
      setGeometria(await resposta.json())
    } catch (e) {
      setErroGeometria(e.message)
    } finally {
      setCarregandoGeometria(false)
    }
  }

  function handleFecharModal() {
    setParSelecionado(null)
    setGeometria(null)
    setErroGeometria(null)
  }

  return (
    <div className="pagina">
      <header className="cabecalho">
        <div>
          <h1>Geometrias Duplicadas</h1>
          <p className="subtitulo">
            Talhões com sobreposição de área acima do limite configurado
          </p>
        </div>
        <div className="acoes-topo">
          <button
            onClick={() => setTema(tema === 'dark' ? 'light' : 'dark')}
            className="botao-secundario botao-tema"
            title={tema === 'dark' ? 'Mudar para modo claro' : 'Mudar para modo escuro'}
            aria-label={tema === 'dark' ? 'Mudar para modo claro' : 'Mudar para modo escuro'}
          >
            {tema === 'dark' ? '☀️' : '🌙'}
          </button>
          <button onClick={handleExportarExcel} disabled={!total} className="botao-secundario">
            Exportar Excel
          </button>
          <button onClick={handleRodarPipeline} disabled={rodandoPipeline} className="botao-primario">
            {rodandoPipeline ? 'Rodando…' : 'Rodar pipeline'}
          </button>
        </div>
      </header>

      <form className="filtros" onSubmit={handleFiltrarSubmit}>
        <input
          type="text"
          placeholder="Fazenda"
          value={filtros.fazenda}
          onChange={(e) => setFiltros({ ...filtros, fazenda: e.target.value })}
        />
        <input
          type="text"
          placeholder="Usina"
          value={filtros.usina}
          onChange={(e) => setFiltros({ ...filtros, usina: e.target.value })}
        />
        <input
          type="text"
          placeholder="Safra"
          value={filtros.safra}
          onChange={(e) => setFiltros({ ...filtros, safra: e.target.value })}
        />
        <input
          type="number"
          step="0.01"
          min="0"
          max="100"
          placeholder="% sobreposição mínima"
          value={filtros.percentualMinimo}
          onChange={(e) => setFiltros({ ...filtros, percentualMinimo: e.target.value })}
        />
        <button type="submit" className="botao-primario">Filtrar</button>
        <button type="button" onClick={handleLimparFiltros} className="botao-secundario">Limpar</button>
      </form>

      <div className="barra-status">
        {carregando && <span>Carregando…</span>}
        {!carregando && total !== null && (
          <span>{total} par(es) encontrado(s)</span>
        )}
        {ultimaExecucao && (
          <span className="ultima-execucao">
            Última execução do pipeline: {new Date(ultimaExecucao).toLocaleString('pt-BR')}
          </span>
        )}
      </div>

      {erro && <p className="erro">{erro}</p>}

      <div className="tabela-wrapper">
        <table>
          <thead>
            <tr>
              <th>Safra</th>
              <th>Fazenda</th>
              <th>Bloco</th>
              <th>Talhão</th>
              <th>ID Talhão</th>
              <th>Corte</th>
              <th>Usina</th>
              <th>% Sobreposição</th>
            </tr>
          </thead>
          <tbody>
            {itens.length === 0 && !carregando && (
              <tr>
                <td colSpan={8} className="vazio">
                  {total === 0 && ultimaExecucao === null
                    ? 'Nenhum resultado ainda — clique em "Rodar pipeline" para calcular.'
                    : 'Nenhum par encontrado com os filtros atuais.'}
                </td>
              </tr>
            )}
            {itens.map((par) => (
              <tr key={par.id} onClick={() => handleSelecionarPar(par)} className="linha-clicavel">
                <td>
                  {par.AnoSafra1} <span className="vs">×</span> {par.AnoSafra2}
                </td>
                <td>
                  {par.Fazenda1} <span className="vs">×</span> {par.Fazenda2}
                </td>
                <td>
                  {par.Bloco1} <span className="vs">×</span> {par.Bloco2}
                </td>
                <td>
                  {par.Talhao1} <span className="vs">×</span> {par.Talhao2}
                </td>
                <td>
                  {par.IDTalhao1} <span className="vs">×</span> {par.IDTalhao2}
                </td>
                <td>
                  {par.Corte1} <span className="vs">×</span> {par.Corte2}
                </td>
                <td>
                  {par.Usina1} <span className="vs">×</span> {par.Usina2}
                </td>
                <td className="percentual">{formatarPercentual(par.PercentualSobreposicaoGeral)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {parSelecionado && (
        <GeometriaModal
          par={parSelecionado}
          geometria={geometria}
          carregando={carregandoGeometria}
          erro={erroGeometria}
          onClose={handleFecharModal}
        />
      )}
    </div>
  )
}
