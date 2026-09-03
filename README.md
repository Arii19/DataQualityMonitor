# Data Quality Monitor — Geometrias Duplicadas

Ferramenta interna que identifica talhões cujas geometrias se sobrepõem no
banco (indicando cadastro duplicado ou inconsistente), calcula o percentual
de sobreposição de cada par, classifica o motivo mais provável (mesmo talhão
físico com ciclo não fechado, fazenda cadastrada 2x, cadastro duplicado ou
erro de digitalização de limite) e exibe o resultado em duas telas: uma
local (React + FastAPI) e um dashboard remoto somente-leitura, publicado
como link.

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
   Consulta `vw_bree_full.CadastroDeAreas` + `vw_bree_full.Geometria` via MCP
   smartbio (join amarrado por `IDTalhao` **e** `IDSafra`, pra garantir a
   geometria da safra realmente ativa de cada talhão) e salva o CSV bruto em
   `raw/<cliente>/`.
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
5. **Dashboard remoto** ([scripts/dashboard_template.html](scripts/dashboard_template.html)):
   mesma experiência de visualização, sem backend e sem e-mail — publicado
   como Claude Artifact pra acesso de fora da rede local (detalhes abaixo).

`raw/` e `cache/` não entram no git (dado extraído e derivado, não código) —
rodar `python smartbio_cache.py <Cliente>` depois de uma extração nova do
Claude é o que repovoa os dois.

## Estrutura do projeto

```
.
├── app.py                    # funções de cálculo reaproveitadas por smartbio_cache.py:
│                              #   intersect() (sjoin espacial), classificar_motivo(), salvar_excel()
├── smartbio_cache.py          # pipeline smartbio: lê raw/<cliente>/*.csv -> cache/<cliente>.json + Excel
├── api.py                     # API FastAPI que serve cache/<cliente>.json pro front-end local
├── config.py                  # variáveis de ambiente (e-mail/Azure — envio ainda não está em uso)
├── requirements.txt           # dependências Python
├── Queries/
│   └── geometria_correta_por_safra.sql  # consulta de referência com o join por safra (histórico do bug corrigido)
├── docs/
│   └── especificacao_view_geometria_por_safra.md  # spec da correção aplicada nas views do smartbio
├── scripts/
│   ├── atualizar_diario.ps1   # tarefa agendada do Windows: extração diária + regenera dist/dashboard.html
│   ├── instalar_tarefa_agendada.ps1 / remover_tarefa_agendada.ps1
│   ├── build_dashboard.py     # gera dist/dashboard.html a partir do cache/*.json mais recente
│   ├── publicar_dashboard.ps1 # regenera dist/dashboard.html (publicar é sempre via Claude Code, ver abaixo)
│   └── dashboard_template.html # front-end do dashboard remoto (HTML+JS sem build step)
├── raw/                       # CSV bruto extraído do smartbio por cliente (ignorado pelo git)
├── cache/                     # cache/<cliente>.json consumido pela API (ignorado pelo git)
├── output/                    # Excel + relatórios de geometria suspeita, gerados a cada execução (ignorado pelo git)
├── dist/                      # dashboard.html gerado, pronto pra publicar (ignorado pelo git)
└── frontend/                  # interface local React (Vite)
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
```

Crie um arquivo `.env` na raiz do projeto com as credenciais de e-mail (via
Microsoft Graph, usadas por `config.py`/`email_utils.py` — ver `## API`
abaixo):

```
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
EMAIL_SENDER=
EMAIL_RECIPIENTS=fulano@empresa.com, ciclano@empresa.com
EMAIL_SUBJECT=Relatório de Geometrias Duplicadas
```

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
  embutido no próprio HTML. Os 9 clientes somados ficam bem abaixo do limite
  de 16MB de um artifact.
- `dist/dashboard.html` é **regenerado sozinho, 1x/dia**, pela mesma tarefa
  agendada do Windows que faz a extração ([scripts/atualizar_diario.ps1](scripts/atualizar_diario.ps1)).
- **Publicar no link é sempre pedido numa conversa do Claude Code** — "atualiza
  e republica o dashboard". A publicação em si não roda fora de uma sessão
  interativa (nem agendada, nem via script solto), então não tem um comando
  que você rode sozinha pra isso; `scripts/publicar_dashboard.ps1 -Rebuild`
  só deixa `dist/dashboard.html` pronto no disco. O pedido no chat leva menos
  de um minuto e não muda a URL, só o conteúdo.

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
