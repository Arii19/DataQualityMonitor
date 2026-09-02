# Data Quality Monitor — Geometrias Duplicadas

Ferramenta interna que identifica talhões cujas geometrias se sobrepõem no
banco (indicando cadastro duplicado ou inconsistente), calcula o percentual
de sobreposição de cada par, classifica o motivo mais provável (mesmo talhão
físico com ciclo não fechado, fazenda cadastrada 2x, cadastro duplicado ou
erro de digitalização de limite) e exibe o resultado numa tela web — com
barra de clientes, filtro, exportação pra Excel e visualização gráfica das
duas geometrias sobrepostas.

## Duas fontes de dado

O projeto tem dois jeitos de extrair os talhões, porque nem todo cliente é
acessível do mesmo lugar:

- **SQL Server direto** ([app.py](app.py) `extract()`, via pyodbc): pensado
  originalmente pra um banco só (o do `.env`). Ainda funciona standalone
  (`python app.py`), mas a tela web hoje usa o fluxo do smartbio abaixo.
- **smartbio, multi-cliente** ([smartbio_cache.py](smartbio_cache.py)): os 9
  clientes da barra lateral (Atvos, SantaAdelia, Cevasa, CMAA, Guaira, GQQ,
  JPA, Cocal, IPE) só são consultáveis pelo smartbio, e o smartbio só é
  acessível de dentro de uma sessão do Claude Code com o MCP configurado — o
  backend (`api.py`), rodando sozinho via uvicorn, não tem essa credencial.
  Por isso a atualização de dado é sempre pedida pro Claude, não clicada
  direto na tela.

## Como funciona (fluxo smartbio, usado pela tela)

1. **Extração**: peça pro Claude Code "atualizar o cliente X" (ou "todos").
   Ele consulta `vw_bree_full.CadastroDeAreas` + `vw_bree_full.Geometria` via
   MCP smartbio pra aquele cliente e salva o CSV bruto em `raw/<cliente>/`.
2. **Cálculo** ([smartbio_cache.py](smartbio_cache.py)): lê esse CSV, roda a mesma lógica de
   sobreposição de `app.py.intersect()` (GeoPandas: sjoin espacial + área de
   interseção/união, só pares com mais de 1% de sobreposição real) e
   classifica o motivo (`app.py.classificar_motivo()`), e grava o resultado em
   `cache/<cliente>.json` + `output/<cliente>_duplicados_<data>.xlsx`.
3. **API** ([api.py](api.py)): serve `/api/duplicados` direto de `cache/<cliente>.json` —
   não recalcula nada, nem toca no smartbio ou no SQL Server. O botão
   "Atualizar" da tela só relê esse arquivo do disco (útil se o Claude acabou
   de gerar um cache novo enquanto a tela estava aberta).
4. **Interface** ([frontend/](frontend/)): React (Vite) — barra lateral com os 9 clientes
   (mostra total de pares e "gerado há Xh" de cada um), tabela com filtro,
   exportar Excel, enviar e-mail e um modal que desenha as duas geometrias de
   um par sobreposto ao clicar na linha.

`raw/` e `cache/` não entram no git (dado extraído e derivado, não código) —
rodar `python smartbio_cache.py <Cliente>` depois de uma extração nova do
Claude é o que repovoa os dois.

## Estrutura do projeto

```
.
├── app.py                  # pipeline SQL Server: extract() -> intersect() -> salvar_excel()
│                           #   (intersect()/classificar_motivo() também são reusados por smartbio_cache.py)
├── smartbio_cache.py       # pipeline smartbio: lê raw/<cliente>/*.csv -> cache/<cliente>.json + Excel
├── api.py                  # API FastAPI que serve cache/<cliente>.json pro front-end
├── config.py                # variáveis de ambiente (DB + e-mail/Azure — e-mail ainda não está em uso)
├── requirements.txt         # dependências Python
├── Queries/
│   └── geometrias.sql       # consulta que extrai as geometrias do SQL Server (fluxo app.py)
├── raw/                     # CSV bruto extraído do smartbio por cliente (ignorado pelo git)
├── cache/                   # cache/<cliente>.json consumido pela API (ignorado pelo git)
├── output/                  # Excel gerado a cada execução (ignorado pelo git)
└── frontend/                # interface React (Vite)
    └── src/
        ├── App.jsx           # tela principal: barra de clientes, filtros, tabela, ações
        ├── GeometriaModal.jsx# desenho SVG das duas geometrias de um par
        └── *.css
```

## Pré-requisitos

- Python 3.13+ com um driver ODBC do SQL Server instalado (`ODBC Driver 18
  for SQL Server` por padrão)
- Node.js 22+ (o front-end foi feito com Vite 5)
- Acesso ao banco SQL Server configurado no `.env`

## Configuração

### 1. Backend

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz do projeto com as credenciais do banco:

```
DB_SERVER=SRV\INSTANCIA
DB_DATABASE=NomeDoBanco
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_SERVER_CERTIFICATE=yes

# autenticação do Windows (padrão) ou usuário/senha do SQL Server
DB_TRUSTED_CONNECTION=yes
DB_USER=
DB_PASSWORD=
```

### 2. Frontend

```powershell
cd frontend
npm install
```

## Como rodar

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
extrair aquele cliente do smartbio de novo (ele roda `smartbio_cache.py
<Cliente>`) — o botão **"Atualizar"** só relê o cache do disco, não recalcula
nada sozinho.

> Se a porta 8000/8001 já estiver em uso por outro processo na sua máquina,
> rode o uvicorn numa porta livre e ajuste `API_URL` em
> [frontend/src/App.jsx](frontend/src/App.jsx).

## Dashboard remoto (Artifact, somente leitura)

Pra colegas de outras cidades/fora da rede local acessarem os mesmos dados
sem precisar de VPN, backend rodando ou porta aberta: existe um segundo
front-end, [scripts/dashboard_template.html](scripts/dashboard_template.html),
publicado como Claude Artifact (link fixo, privado, compartilhável):

- Mesma experiência da tela local (barra de clientes, filtro, tabela,
  modal de geometria sobreposta, exportar Excel), **sem** o envio de
  e-mail — isso continua só na tela local.
- Sem backend: todo o dado (metadados + geometria, já *simplificada* pra
  visualização — `shapely.simplify` + arredondamento de coordenadas, só
  nesse artifact) fica embutido no próprio HTML. Os 9 clientes somados
  ficam por volta de 2.7MB simplificados (30MB+ na resolução original),
  bem abaixo do limite de 16MB de um artifact.
- **Atualizado 1x/dia**, automaticamente: [scripts/atualizar_diario.ps1](scripts/atualizar_diario.ps1)
  — a mesma tarefa agendada do Windows que já fazia a extração diária —
  agora também roda [scripts/build_dashboard.py](scripts/build_dashboard.py)
  (regenera `dist/dashboard.html` a partir do `cache/<cliente>.json` mais
  recente) e republica esse HTML no artifact **sempre no mesmo link**
  (republicar não troca a URL).

Gerar/republicar manualmente (fora do agendamento diário):

```powershell
.\venv\Scripts\python scripts\build_dashboard.py   # gera dist/dashboard.html
```

e peça pro Claude Code publicar `dist/dashboard.html` no artifact existente
(ele precisa da URL — está registrada como `$artifactUrl` no topo de
`scripts/atualizar_diario.ps1`).

## API

Toda rota abaixo de `/api/duplicados*` e `/api/pipeline/rodar` exige o
parâmetro `cliente` (um dos 9 nomes da barra lateral). Nenhuma delas calcula
nada — todas leem `cache/<cliente>.json`, que só é populado pelo
`smartbio_cache.py` (via extração do Claude).

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/clientes` | Lista os 9 clientes, com total de pares e data do cache de cada um |
| `POST` | `/api/pipeline/rodar?cliente=X` | Confirma que existe cache pra esse cliente e devolve a data em que foi gerado — não recalcula |
| `GET` | `/api/duplicados?cliente=X` | Lista os pares calculados desse cliente (filtros: `fazenda`, `usina`, `safra`, `percentual_minimo`) |
| `GET` | `/api/duplicados/{id}/geometria?cliente=X` | Geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela |
| `GET` | `/api/duplicados/excel?cliente=X` | Baixa o último Excel gerado pra esse cliente |
| `POST` | `/api/duplicados/email?clientes=X&clientes=Y` | Envia por e-mail os clientes selecionados (Microsoft Graph, via `config.py`/`email_utils.py`). Um cliente só: anexa o Excel já gerado por ele. Mais de um: monta um único Excel com uma aba por cliente (cada aba já tem uma coluna `Cliente` também) em vez de vários anexos. |

Documentação interativa (Swagger) disponível em `http://localhost:8001/docs`
com a API rodando.
