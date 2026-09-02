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

function tempoRelativo(iso) {
  if (!iso) return null
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.round(diffMs / 60000)
  if (min < 1) return 'agora mesmo'
  if (min < 60) return `há ${min} min`
  const h = Math.round(min / 60)
  if (h < 24) return `há ${h}h`
  return `há ${Math.round(h / 24)}d`
}

export default function App() {
  const [tema, setTema] = useTema()
  const [clientes, setClientes] = useState([])
  const [clienteAtivo, setClienteAtivo] = useState(null)
  const [clientesEmail, setClientesEmail] = useState(() => new Set())
  const [barraAberta, setBarraAberta] = useState(true)
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS)
  const [itens, setItens] = useState([])
  const [total, setTotal] = useState(null)
  const [ultimaExecucao, setUltimaExecucao] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [rodandoPipeline, setRodandoPipeline] = useState(false)
  const [enviandoEmail, setEnviandoEmail] = useState(false)
  const [mensagemEmail, setMensagemEmail] = useState(null)
  const [erro, setErro] = useState(null)
  const [parSelecionado, setParSelecionado] = useState(null)
  const [geometria, setGeometria] = useState(null)
  const [carregandoGeometria, setCarregandoGeometria] = useState(false)
  const [erroGeometria, setErroGeometria] = useState(null)

  const buscarClientes = useCallback(async () => {
    try {
      const resposta = await fetch(`${API_URL}/api/clientes`)
      if (!resposta.ok) throw new Error(`Falha ao buscar clientes (HTTP ${resposta.status})`)
      const dados = await resposta.json()
      setClientes(dados.itens)
      setClienteAtivo((atual) => atual ?? dados.itens[0]?.cliente ?? null)
    } catch (e) {
      setErro(e.message)
    }
  }, [])

  useEffect(() => {
    buscarClientes()
  }, [buscarClientes])

  const buscarDuplicados = useCallback(async (cliente, filtrosAtuais) => {
    if (!cliente) return
    setCarregando(true)
    setErro(null)
    try {
      const query = montarQuery(filtrosAtuais)
      const resposta = await fetch(`${API_URL}/api/duplicados?cliente=${cliente}${query ? `&${query}` : ''}`)
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
    if (clienteAtivo) buscarDuplicados(clienteAtivo, FILTROS_INICIAIS)
  }, [clienteAtivo, buscarDuplicados])

  function handleSelecionarCliente(cliente) {
    if (cliente === clienteAtivo) return
    setClienteAtivo(cliente)
    setFiltros(FILTROS_INICIAIS)
    setMensagemEmail(null)
  }

  function handleAlternarClienteEmail(cliente, event) {
    event.stopPropagation()
    setClientesEmail((atual) => {
      const novo = new Set(atual)
      if (novo.has(cliente)) novo.delete(cliente)
      else novo.add(cliente)
      return novo
    })
  }

  async function handleRodarPipeline() {
    setRodandoPipeline(true)
    setErro(null)
    try {
      const resposta = await fetch(`${API_URL}/api/pipeline/rodar?cliente=${clienteAtivo}`, { method: 'POST' })
      if (!resposta.ok) {
        const detalhe = await resposta.json().catch(() => null)
        throw new Error(detalhe?.detail || `Falha ao atualizar (HTTP ${resposta.status})`)
      }
      await Promise.all([buscarDuplicados(clienteAtivo, filtros), buscarClientes()])
    } catch (e) {
      setErro(e.message)
    } finally {
      setRodandoPipeline(false)
    }
  }

  function handleFiltrarSubmit(event) {
    event.preventDefault()
    buscarDuplicados(clienteAtivo, filtros)
  }

  function handleLimparFiltros() {
    setFiltros(FILTROS_INICIAIS)
    buscarDuplicados(clienteAtivo, FILTROS_INICIAIS)
  }

  function handleExportarExcel() {
    window.open(`${API_URL}/api/duplicados/excel?cliente=${clienteAtivo}`, '_blank')
  }

  async function handleEnviarEmail() {
    const alvos = clientesEmail.size > 0 ? [...clientesEmail] : [clienteAtivo]
    setEnviandoEmail(true)
    setErro(null)
    setMensagemEmail(null)
    try {
      const query = alvos.map((c) => `clientes=${encodeURIComponent(c)}`).join('&')
      const resposta = await fetch(`${API_URL}/api/duplicados/email?${query}`, { method: 'POST' })
      if (!resposta.ok) {
        const detalhe = await resposta.json().catch(() => null)
        throw new Error(detalhe?.detail || `Falha ao enviar e-mail (HTTP ${resposta.status})`)
      }
      const dados = await resposta.json()
      setMensagemEmail(`E-mail enviado (${dados.arquivo})`)
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviandoEmail(false)
    }
  }

  async function handleSelecionarPar(par) {
    setParSelecionado(par)
    setGeometria(null)
    setErroGeometria(null)
    setCarregandoGeometria(true)
    try {
      const resposta = await fetch(`${API_URL}/api/duplicados/${par.id}/geometria?cliente=${clienteAtivo}`)
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
    <div className="layout">
      <aside className={`barra-clientes ${barraAberta ? '' : 'recolhida'}`}>
        <button
          className="botao-recolher"
          onClick={() => setBarraAberta(!barraAberta)}
          title={barraAberta ? 'Recolher lista de clientes' : 'Expandir lista de clientes'}
          aria-label={barraAberta ? 'Recolher lista de clientes' : 'Expandir lista de clientes'}
        >
          {barraAberta ? '«' : '»'}
        </button>
        {barraAberta && (
          <div className="barra-titulo-linha">
            <p className="barra-titulo">Clientes</p>
            {clientesEmail.size > 0 && (
              <button className="limpar-selecao" onClick={() => setClientesEmail(new Set())}>
                limpar seleção
              </button>
            )}
          </div>
        )}
        <nav className="lista-clientes">
          {clientes.map((c) => (
            <div key={c.cliente} className={`cliente-item ${c.cliente === clienteAtivo ? 'ativo' : ''}`}>
              {barraAberta && (
                <input
                  type="checkbox"
                  className="cliente-checkbox"
                  checked={clientesEmail.has(c.cliente)}
                  onChange={(e) => handleAlternarClienteEmail(c.cliente, e)}
                  onClick={(e) => e.stopPropagation()}
                  title={`Incluir ${c.cliente} no próximo e-mail`}
                />
              )}
              <button
                className="cliente-botao"
                onClick={() => handleSelecionarCliente(c.cliente)}
                title={c.cliente}
              >
                <span className="cliente-nome">{c.cliente}</span>
                {barraAberta && (
                  <span className="cliente-meta">
                    {c.total === null ? 'sem dados' : `${c.total} par(es)`}
                    {c.gerado_em && <span className="cliente-data"> · {tempoRelativo(c.gerado_em)}</span>}
                  </span>
                )}
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <div className="pagina">
        <header className="cabecalho">
          <div>
            <h1>Geometrias Duplicadas {clienteAtivo && <span className="cliente-atual">— {clienteAtivo}</span>}</h1>
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
            <button
              onClick={handleEnviarEmail}
              disabled={(!total && clientesEmail.size === 0) || enviandoEmail}
              className="botao-secundario"
              title={
                clientesEmail.size > 0
                  ? `Envia o Excel de: ${[...clientesEmail].join(', ')}`
                  : `Envia o Excel de ${clienteAtivo ?? 'cliente atual'} — marque outros na barra lateral pra mandar juntos`
              }
            >
              {enviandoEmail
                ? 'Enviando…'
                : clientesEmail.size > 0
                  ? `Enviar por e-mail (${clientesEmail.size})`
                  : 'Enviar por e-mail'}
            </button>
            <button
              onClick={handleRodarPipeline}
              disabled={rodandoPipeline || !clienteAtivo}
              className="botao-primario"
              title="Recarrega o cache mais recente gerado pelo Claude Code a partir do smartbio — não recalcula na hora"
            >
              {rodandoPipeline ? 'Atualizando…' : 'Atualizar'}
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
            Dados extraídos do smartbio em: {new Date(ultimaExecucao).toLocaleString('pt-BR')}
          </span>
        )}
        {mensagemEmail && <span className="mensagem-sucesso">{mensagemEmail}</span>}
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
              <th>Motivo</th>
            </tr>
          </thead>
          <tbody>
            {itens.length === 0 && !carregando && (
              <tr>
                <td colSpan={9} className="vazio">
                  {total === 0 && ultimaExecucao === null
                    ? 'Nenhum dado ainda pra esse cliente — peça pro Claude Code extrair do smartbio.'
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
                <td className="motivo">{par.Motivo}</td>
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
    </div>
  )
}
