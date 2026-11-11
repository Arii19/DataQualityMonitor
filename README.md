# Data Quality Monitor — Geometrias Duplicadas

Ferramenta interna que identifica talhões cujas geometrias se sobrepõem no
banco (indicando cadastro duplicado ou inconsistente), calcula o percentual
de sobreposição de cada par, classifica o motivo mais provável (mesmo talhão
físico com ciclo não fechado, fazenda cadastrada 2x, cadastro duplicado ou
erro de digitalização de limite) e exibe o resultado em duas telas: uma
local (React + FastAPI) e um dashboard remoto somente-leitura, publicado
como link.

## Fonte de dado: smartbio via MCP

Os 10 clientes da barra lateral (Atvos, SantaAdelia, Cevasa, CMAA, Guaira,
GQQ, JPA, Cocal, IPE, Ferrari) só são consultáveis pelo smartbio, e o smartbio só é
acessível de dentro de uma sessão do Claude Code com o MCP configurado — o
backend (`api.py`), rodando sozinho via uvicorn, não tem essa credencial.
Por isso a atualização de dado é sempre pedida pro Claude, não clicada
direto na tela. `app.py` mantém só `classificar_motivo()`, usada por
`smartbio_cache.py` — não tem mais conexão de banco própria nem entry point standalone.

## Como funciona (fluxo smartbio, usado pelas duas telas)

1. **Extração**: peça pro Claude Code "atualizar o cliente X" (ou "todos") —
   ele segue [.claude/skills/atualizar-geometrias/SKILL.md](.claude/skills/atualizar-geometrias/SKILL.md).
   Consulta `vw_mcp.CadastroDeAreas` + `vw_mcp.Geometria_DEBUG`
   via MCP smartbio (join amarrado por `IDTalhao` **e** `IDSafra`, com
   deduplicação, pra garantir a geometria da safra realmente ativa de cada
   talhão — detalhe técnico em
   [docs/especificacao_view_geometria_por_safra.md](docs/especificacao_view_geometria_por_safra.md))
   e salva o CSV bruto em `raw/<cliente>/`.
2. **Cálculo** ([smartbio_cache.py](smartbio_cache.py)): lê esse CSV, roda a
   lógica de sobreposição de `calcular_sobreposicoes()` (GeoPandas: sjoin
   espacial + área de interseção/união, só pares de talhões com IDTalhao diferente e mais de 0,20% de
   sobreposição real), classifica o motivo (`app.py.classificar_motivo()`)
   e grava o resultado em `cache/<cliente>.json` +
   `output/<cliente>_duplicados_<data>.xlsx` (só os 10 Excels mais recentes de
   cada tipo ficam em `output/` — `MANTER_EXCELS` em `smartbio_cache.py`).
3. **API** ([api.py](api.py)): serve `/api/duplicados` direto de
   `cache/<cliente>.json` — não recalcula nada, nem toca no smartbio ou no
   SQL Server. O botão "Atualizar" da tela só relê esse arquivo do disco
   (útil se o Claude acabou de gerar um cache novo enquanto a tela estava
   aberta).
4. **Interface local** ([frontend/](frontend/)): React (Vite) — barra
   lateral com os 10 clientes (total de pares e "gerado há Xh" de cada um),
   tabela com filtro, exportar Excel, enviar e-mail, painel de Relatórios
   ManagerVision (ver abaixo) e um modal que desenha as duas geometrias de
   um par sobreposto ao clicar na linha.
5. **Dashboard remoto** ([scripts/dashboard_template.html](scripts/dashboard_template.html)):
   mesma experiência de visualização de geometrias, sem backend e sem
   e-mail — publicado como Claude Artifact pra acesso de fora da rede local
   (detalhes abaixo). Não tem o painel de Relatórios ManagerVision: esse é
   só da tela local, porque depende de logar ao vivo no ManagerVision
   (Playwright), algo que só o backend local faz.

`raw/` e `cache/` não entram no git (dado extraído e derivado, não código) —
rodar `python smartbio_cache.py <Cliente>` depois de uma extração nova do
Claude é o que repovoa os dois.

## Estrutura do projeto

```
.
├── app.py                    # classificar_motivo(), usada por smartbio_cache.py
├── smartbio_cache.py          # pipeline smartbio: lê raw/<cliente>/*.csv -> cache/<cliente>.json + Excel
├── api.py                     # API FastAPI que serve cache/<cliente>.json pro front-end local
├── config.py                  # variáveis de ambiente (e-mail/Azure, EMAIL_POR_CLIENTE, login ManagerVision)
├── email_utils.py             # envio de e-mail via Microsoft Graph
├── managervision_pdf.py       # exporta PDF de um relatório ManagerVision ao vivo (Playwright) — sob demanda, chamado pela API
├── requirements.txt           # dependências Python
├── Queries/
│   └── geometria_correta_por_safra.sql  # consulta de referência com o join por safra (histórico do bug corrigido)
├── docs/
│   └── especificacao_view_geometria_por_safra.md  # spec da correção aplicada nas views do smartbio
├── scripts/
│   ├── atualizar_diario_geometrias.ps1  # tarefa agendada (07:55): extração de geometrias + regenera dist/dashboard.html + e-mail
│   ├── instalar_tarefa_agendada.ps1 / remover_tarefa_agendada.ps1  # registra/remove a tarefa acima
│   ├── build_dashboard.py     # gera dist/dashboard.html a partir do cache/*.json mais recente
│   ├── publicar_dashboard.ps1 # regenera dist/dashboard.html (publicar é sempre via Claude Code, ver abaixo)
│   ├── dashboard_template.html # front-end do dashboard remoto (HTML+JS sem build step)
│   └── enviar_email_geometrias.py     # e-mail automático de geometrias (consolidado por usina, ou separado se EMAIL_POR_CLIENTE tiver o cliente)
├── raw/                       # CSV bruto extraído do smartbio por cliente (ignorado pelo git)
├── cache/                     # cache/<cliente>.json consumido pela API (ignorado pelo git)
├── output/                    # Excel + relatórios de geometria suspeita, gerados a cada execução (ignorado pelo git)
├── dist/                      # dashboard.html gerado, pronto pra publicar (ignorado pelo git)
└── frontend/                  # interface local React (Vite)
    └── src/
        ├── App.jsx             # tela principal: barra de clientes, filtros, tabela, painel de relatórios, ações
        ├── GeometriaModal.jsx  # desenho SVG das duas geometrias de um par
        └── *.css
```

Populando `cache/managervision/<cliente>.json` (metadado dos relatórios que
aparecem no painel): peça pro Claude Code "atualiza os relatórios do
ManagerVision" — segue
[.claude/skills/atualizar-relatorios-managervision/SKILL.md](.claude/skills/atualizar-relatorios-managervision/SKILL.md).
Isso só grava o metadado (título, descrição, link); o PDF de cada relatório
é gerado ao vivo, na hora, quando alguém clica em "Baixar PDF" ou "Enviar
por e-mail" na tela — não tem geração em lote nem automação diária pra
isso.

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

O último passo baixa o Chromium usado pelo Playwright pra exportar em PDF um
relatório do ManagerVision sob demanda (ver `managervision_pdf.py`) — sem
ele, só o download do binário do navegador, os endpoints
`/api/relatorios/*/pdf` e `/api/relatorios/email` falham (o resto da tela
funciona normalmente sem esse passo).

Crie um arquivo `.env` na raiz do projeto com as credenciais de e-mail (via
Microsoft Graph, usadas por `config.py`/`email_utils.py` — ver `## API`
abaixo) e o login do ManagerVision (usado pelo Playwright só quando alguém
pede um PDF pela tela — a mesma conta funciona em todos os
clientes/subdomínios smartbreeder.com.br):

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
sem regra própria em `EMAIL_POR_CLIENTE` ([config.py](config.py) — hoje
vazio, ou seja, os 10 clientes caem no padrão). Todo cliente que cai no
padrão vai **junto num e-mail só**, com um Excel de uma aba por usina (em vez
de uma aba por cliente) — ver
[scripts/enviar_email_geometrias.py](scripts/enviar_email_geometrias.py). Só
volta a ser um e-mail separado (Excel próprio, só daquele cliente) se ele
ganhar uma entrada em `EMAIL_POR_CLIENTE` com destinatário diferente de
`EMAIL_RECIPIENTS`.

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

## Dashboard remoto (Artifact, somente leitura)

Pra colegas de outras cidades/fora da rede local acessarem os mesmos dados
sem precisar de VPN, backend rodando ou porta aberta: existe um segundo
front-end, [scripts/dashboard_template.html](scripts/dashboard_template.html),
publicado como Claude Artifact — link fixo e privado, compartilhável.

- Mesma experiência da tela local (barra de clientes, filtro, tabela, modal
  de geometria sobreposta, exportar Excel), **sem** o envio de e-mail — isso
  continua só na tela local.
- Sem backend: todo o dado (metadados + geometria, simplificada só nesse
  artifact — `shapely.simplify` + arredondamento de coordenadas) fica
  embutido no próprio HTML. Os 10 clientes somados ficam bem abaixo do limite
  de 16MB de um artifact.
- `dist/dashboard.html` é **regenerado sozinho, 1x/dia (07:55)**, pela mesma
  tarefa agendada do Windows que faz a extração
  ([scripts/atualizar_diario_geometrias.ps1](scripts/atualizar_diario_geometrias.ps1)).
  Essa mesma tarefa também manda, todo dia, o e-mail de geometrias — junto
  num Excel só (aba por usina) pros clientes sem destinatário próprio,
  separado pros que tiverem (ver `EMAIL_POR_CLIENTE` em
  [config.py](config.py) e
  [scripts/enviar_email_geometrias.py](scripts/enviar_email_geometrias.py)).
- **Publicar no link é sempre pedido numa conversa do Claude Code** — "atualiza
  e republica o dashboard". A publicação em si não roda fora de uma sessão
  interativa (nem agendada, nem via script solto), então não tem um comando
  que você rode sozinha pra isso; `scripts/publicar_dashboard.ps1 -Rebuild`
  só deixa `dist/dashboard.html` pronto no disco. O pedido no chat leva menos
  de um minuto e não muda a URL, só o conteúdo.

## API

Toda rota abaixo de `/api/duplicados*` e `/api/pipeline/rodar` exige o
parâmetro `cliente` (um dos 10 nomes da barra lateral). Nenhuma delas calcula
nada — todas leem `cache/<cliente>.json`, que só é populado pelo
`smartbio_cache.py` (via extração do Claude).

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/clientes` | Lista os 10 clientes, com total de pares e data do cache de cada um |
| `POST` | `/api/pipeline/rodar?cliente=X` | Confirma que existe cache pra esse cliente e devolve a data em que foi gerado — não recalcula |
| `GET` | `/api/duplicados?cliente=X` | Lista os pares calculados desse cliente (filtros: `fazenda`, `usina`, `safra`, `talhao`, `percentual_minimo`) |
| `GET` | `/api/duplicados/{id}/geometria?cliente=X` | Geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela |
| `GET` | `/api/duplicados/excel?cliente=X` | Baixa o último Excel gerado pra esse cliente |
| `POST` | `/api/duplicados/email?clientes=X&clientes=Y` | Envia por e-mail os clientes selecionados (Microsoft Graph, via `config.py`/`email_utils.py`). Um cliente só: anexa o Excel já gerado por ele. Mais de um: monta um único Excel com uma aba por cliente (cada aba já tem uma coluna `Cliente` também) em vez de vários anexos. |
| `GET` | `/api/relatorios?cliente=X` | Lista os relatórios ManagerVision em cache pra esse cliente (metadado só — `cache/managervision/<cliente>.json`, populado pela skill, não pela API) |
| `GET` | `/api/relatorios/{chart_id}/pdf?cliente=X` | Loga no ManagerVision (Playwright, ao vivo) e devolve o PDF desse relatório — pode levar alguns segundos |
| `POST` | `/api/relatorios/email?cliente=X&arquivos=Y&arquivos=Z` | Gera o PDF de cada relatório selecionado (Playwright, ao vivo) e manda todos anexados num único e-mail |
| `POST` | `/api/relatorios/email-todos` | Botão "Enviar todos de todos os clientes" do painel. Gera o PDF de **todos** os relatórios em cache dos 10 clientes (ao vivo, um cliente por vez) e manda tudo num e-mail só pro destinatário padrão (`EMAIL_RECIPIENTS`) — pode levar vários minutos |

Documentação interativa (Swagger) disponível em `http://localhost:8001/docs`
com a API rodando.
