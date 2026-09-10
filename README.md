# Data Quality Monitor — Geometrias Duplicadas

Ferramenta interna que identifica talhões cujas geometrias se sobrepõem no
banco (indicando cadastro duplicado ou inconsistente), calcula o percentual
de sobreposição de cada par, classifica o motivo mais provável (mesmo talhão
físico com ciclo não fechado, fazenda cadastrada 2x, cadastro duplicado ou
erro de digitalização de limite) e exibe o resultado em duas telas: uma
local (React + FastAPI) e a mesma tela publicada via Cloudflare Tunnel, pra
acesso de fora da rede local.

## Fonte de dado: smartbio via MCP

Os 9 clientes da barra lateral (Atvos, SantaAdelia, Cevasa, CMAA, Guaira,
GQQ, JPA, Cocal, IPE) só são consultáveis pelo smartbio, e o smartbio só é
acessível de dentro de uma sessão do Claude Code com o MCP configurado — o
backend (`api.py`), rodando sozinho via uvicorn, não tem essa credencial.
Por isso a atualização de dado é sempre pedida pro Claude, não clicada
direto na tela. `app.py` mantém só as funções de cálculo reaproveitadas por
`smartbio_cache.py` (`intersect()`, `classificar_motivo()`, `salvar_excel()`)
— não tem mais conexão de banco própria nem entry point standalone.

## Como funciona (fluxo smartbio, usado pelas duas telas)

1. **Extração**: peça pro Claude Code "atualizar o cliente X" (ou "todos") —
   ele segue [.claude/skills/atualizar-geometrias/SKILL.md](.claude/skills/atualizar-geometrias/SKILL.md).
   Consulta `vw_bree_full.CadastroDeAreas` + `vw_bree_full.Geometria_DEBUG`
   via MCP smartbio (join amarrado por `IDTalhao` **e** `IDSafra`, com
   deduplicação, pra garantir a geometria da safra realmente ativa de cada
   talhão — detalhe técnico em
   [docs/especificacao_view_geometria_por_safra.md](docs/especificacao_view_geometria_por_safra.md))
   e salva o CSV bruto em `raw/<cliente>/`.
2. **Cálculo** ([smartbio_cache.py](smartbio_cache.py)): lê esse CSV, roda a
   mesma lógica de sobreposição de `app.py.intersect()` (GeoPandas: sjoin
   espacial + área de interseção/união, só pares com mais de 1% de
   sobreposição real), classifica o motivo (`app.py.classificar_motivo()`)
   e grava o resultado em `cache/<cliente>.json` +
   `output/<cliente>_duplicados_<data>.xlsx`.
3. **API** ([api.py](api.py)): serve `/api/duplicados` direto de
   `cache/<cliente>.json` — não recalcula nada, nem toca no smartbio ou no
   SQL Server. O botão "Atualizar" da tela só relê esse arquivo do disco
   (útil se o Claude acabou de gerar um cache novo enquanto a tela estava
   aberta).
4. **Interface local** ([frontend/](frontend/)): React (Vite) — barra
   lateral com os 9 clientes (total de pares e "gerado há Xh" de cada um),
   tabela com filtro, exportar Excel, enviar e-mail e um modal que desenha
   as duas geometrias de um par sobreposto ao clicar na linha.
5. **Dashboard remoto** ([scripts/iniciar_tela.ps1](scripts/iniciar_tela.ps1)):
   mesmo build de produção do frontend, servido pela própria API (`api.py`
   monta `frontend/dist` como estático) e exposto via Cloudflare Tunnel —
   detalhes abaixo.

`raw/` e `cache/` não entram no git (dado extraído e derivado, não código) —
rodar `python smartbio_cache.py <Cliente>` depois de uma extração nova do
Claude é o que repovoa os dois.

## Estrutura do projeto

```
.
├── app.py                    # funções de cálculo reaproveitadas por smartbio_cache.py:
│                              #   intersect() (sjoin espacial), classificar_motivo(), salvar_excel()
├── smartbio_cache.py          # pipeline smartbio: lê raw/<cliente>/*.csv -> cache/<cliente>.json + Excel
├── api.py                     # API FastAPI que serve cache/<cliente>.json + a tela (build de produção) numa origem só
├── config.py                  # variáveis de ambiente (e-mail/Azure, EMAIL_POR_CLIENTE)
├── email_utils.py             # envio de e-mail via Microsoft Graph
├── managervision_pdf.py       # exporta PDF dos relatórios ManagerVision via Playwright
├── requirements.txt           # dependências Python
├── tools/
│   └── cloudflared.exe        # binário nativo do túnel Cloudflare (baixado, não instalado — sem UAC)
├── Queries/
│   └── geometria_correta_por_safra.sql  # consulta de referência com o join por safra (histórico do bug corrigido)
├── docs/
│   └── especificacao_view_geometria_por_safra.md  # spec da correção aplicada nas views do smartbio
├── scripts/
│   ├── atualizar_diario.ps1   # tarefa agendada do Windows: extração diária + PDFs + e-mails automáticos
│   ├── instalar_tarefa_agendada.ps1 / remover_tarefa_agendada.ps1
│   ├── build_managervision_pdfs.py    # gera os PDFs de todos os relatórios em cache/managervision/*.json
│   ├── enviar_email_geometrias.py     # e-mail automático (por cliente) do Excel de duplicados
│   ├── enviar_email_relatorios.py     # e-mail automático (por cliente) dos PDFs do ManagerVision
│   ├── iniciar_tela.ps1               # sobe a tela+API+túnel Cloudflare (ver "Dashboard remoto" abaixo)
│   └── instalar_tarefa_tela.ps1 / remover_tarefa_tela.ps1
├── raw/                       # CSV bruto extraído do smartbio por cliente (ignorado pelo git)
├── cache/                     # cache/<cliente>.json consumido pela API (ignorado pelo git)
├── output/                    # Excel + PDFs de relatórios, gerados a cada execução (ignorado pelo git)
└── frontend/                  # tela React (Vite) — mesmo build usado local e no dashboard remoto
    └── src/
        ├── App.jsx             # tela principal: barra de clientes, filtros, tabela, ações
        ├── GeometriaModal.jsx  # desenho SVG das duas geometrias de um par
        └── *.css
```

## Pré-requisitos

- Python 3.13+
- Node.js 22+ (o front-end foi feito com Vite 5)
- Acesso ao smartbio via MCP, de dentro de uma sessão do Claude Code (é o
  único jeito de extrair dado — ver "Fonte de dado" acima)

## Configuração

### 1. Backend

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python -m playwright install chromium
```

O último passo baixa o Chromium usado pelo Playwright pra exportar em PDF os
relatórios do ManagerVision (ver `managervision_pdf.py`) — sem ele, só o
download do binário do navegador, os endpoints `/api/relatorios/*/pdf` e
`/api/relatorios/email` falham.

Crie um arquivo `.env` na raiz do projeto com as credenciais de e-mail (via
Microsoft Graph, usadas por `config.py`/`email_utils.py` — ver `## API`
abaixo) e o login do ManagerVision (usado pelo Playwright pra autenticar e
carregar os dados ao vivo dos relatórios — a mesma conta funciona em todos
os clientes/subdomínios smartbreeder.com.br):

```
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
EMAIL_SENDER=
EMAIL_RECIPIENTS=fulano@empresa.com, ciclano@empresa.com
EMAIL_SUBJECT=Relatório de Geometrias Duplicadas
MANAGERVISION_USER=
MANAGERVISION_PASSWORD=
```

`EMAIL_RECIPIENTS` é o destinatário **padrão**, usado por qualquer cliente
sem regra própria. Pra mandar um cliente específico só pra alguém em
particular (ex.: Cocal só pro Otávio), edite `EMAIL_POR_CLIENTE` em
[config.py](config.py) — cliente ausente desse dicionário cai no
`EMAIL_RECIPIENTS` do `.env`.

### 2. Frontend

```powershell
cd frontend
npm install
```

## Como rodar (tela local)

Backend e frontend rodam em processos separados:

```powershell
# Terminal 1 — API (porta 8001)
.\venv\Scripts\uvicorn api:app --reload --port 8001

# Terminal 2 — interface (porta 5173)
cd frontend
npm run dev
```

Abra `http://localhost:5173`, escolha um cliente na barra lateral e clique em
qualquer linha da tabela pra ver o desenho das duas geometrias sobrepostas.
Se a lista de um cliente estiver vazia ou desatualizada, peça pro Claude Code
extrair aquele cliente do smartbio de novo — o botão **"Atualizar"** só relê
o cache do disco, não recalcula nada sozinho.

> Se a porta 8000/8001 já estiver em uso por outro processo na sua máquina,
> rode o uvicorn numa porta livre e ajuste `API_URL` em
> [frontend/src/App.jsx](frontend/src/App.jsx).

## Dashboard remoto (Cloudflare Tunnel, sem Docker)

Pra colegas de outras cidades/fora da rede local acessarem os mesmos dados
sem VPN nem porta aberta no roteador: `scripts/iniciar_tela.ps1` builda a
tela (`frontend/dist`), sobe o `uvicorn` (que serve a tela + a API na mesma
porta — ver o mount de `StaticFiles` no final de `api.py`) e o túnel
Cloudflare, tudo nativo no Windows (sem Docker/container nenhum —
`tools/cloudflared.exe` é o binário baixado direto, sem instalador/UAC).
`tools/` é ignorado pelo git — baixe uma vez, antes do primeiro
`iniciar_tela.ps1`:

```powershell
mkdir tools -Force
curl.exe -L -o tools\cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
```

```powershell
.\scripts\iniciar_tela.ps1
```

O link público sai no console e fica salvo em `tunnel_url.txt`.

- `cache/` e `output/` são lidos direto do disco — o mesmo
  `atualizar_diario.ps1` que já roda todo dia (extração + PDFs + e-mails,
  ver `scripts/enviar_email_geometrias.py`/`enviar_email_relatorios.py`)
  continua escrevendo ali, e a tela reflete o dado mais novo sozinha, sem
  rebuild nem restart de nada — não tem passo de "publicar" nenhum.
- O link (`https://<algo>.trycloudflare.com`) muda toda vez que o processo
  do túnel reinicia — é um "quick tunnel" gratuito, sem conta Cloudflare.
  Pra um link fixo, precisa de um domínio numa conta Cloudflare (fora do
  escopo de hoje).
- Sem login: quem tem o link acessa — link privado, não listado.
- **Pra rodar sozinho, sem precisar lembrar**: `scripts/instalar_tarefa_tela.ps1`
  registra uma tarefa agendada que sobe tudo às 07:00 e revalida de hora em
  hora o dia inteiro (o script é idempotente — mata a instância anterior
  antes de subir de novo, então repetir não duplica processo nem conflita
  porta). O ideal seria um gatilho "ao entrar no Windows", mas esse tipo foi
  recusado neste ambiente (parece restrição de segurança contra persistência
  automática) — se funcionar no seu, dá pra trocar por `/SC ONLOGON` no
  script, mais simples.
- Só funciona enquanto o notebook estiver ligado — se a máquina
  desligar/hibernar, a tela cai (volta sozinha na próxima janela da tarefa,
  não precisa religar nada na mão).

## API

Toda rota abaixo de `/api/duplicados*` e `/api/pipeline/rodar` exige o
parâmetro `cliente` (um dos 9 nomes da barra lateral). Nenhuma delas calcula
nada — todas leem `cache/<cliente>.json`, que só é populado pelo
`smartbio_cache.py` (via extração do Claude).

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/clientes` | Lista os 9 clientes, com total de pares e data do cache de cada um |
| `POST` | `/api/pipeline/rodar?cliente=X` | Confirma que existe cache pra esse cliente e devolve a data em que foi gerado — não recalcula |
| `GET` | `/api/duplicados?cliente=X` | Lista os pares calculados desse cliente (filtros: `fazenda`, `usina`, `safra`, `talhao`, `percentual_minimo`) |
| `GET` | `/api/duplicados/{id}/geometria?cliente=X` | Geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela |
| `GET` | `/api/duplicados/excel?cliente=X` | Baixa o último Excel gerado pra esse cliente |
| `POST` | `/api/duplicados/email?clientes=X&clientes=Y` | Envia por e-mail os clientes selecionados (Microsoft Graph, via `config.py`/`email_utils.py`). Um cliente só: anexa o Excel já gerado por ele. Mais de um: monta um único Excel com uma aba por cliente (cada aba já tem uma coluna `Cliente` também) em vez de vários anexos. |

Documentação interativa (Swagger) disponível em `http://localhost:8001/docs`
com a API rodando.
