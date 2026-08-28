# Data Quality Monitor — Geometrias Duplicadas

Ferramenta interna que identifica talhões cujas geometrias se sobrepõem no
banco (indicando cadastro duplicado ou inconsistente), calcula o percentual
de sobreposição de cada par e exibe o resultado numa tela web — com filtro,
exportação pra Excel e visualização gráfica das duas geometrias sobrepostas.

## Como funciona

1. **Consulta** ([Queries/geometrias.sql](Queries/geometrias.sql)): busca no SQL Server todas as
   geometrias de talhão da safra vigente (`GeometriaDeMapa` + `Talhao` +
   `HistDetalhado` + `Fazenda` + `Usina`), trazendo a geometria já em binário
   (`STAsBinary()`), que é bem mais rápido de transferir e converter do que texto (WKT).
2. **Cálculo** ([app.py](app.py) → `intersect()`): usa GeoPandas pra achar, entre todas as
   geometrias, os pares que realmente se sobrepõem (não só encostam na borda),
   calculando a área de interseção e o percentual de sobreposição de cada par.
   Só ficam os pares com mais de 1% de sobreposição.
3. **Exportação** (`salvar_excel()`): grava o resultado em `output/geometrias_duplicadas_<data>.xlsx`.
4. **API** ([api.py](api.py)): expõe esse pipeline via FastAPI pra interface web consumir.
5. **Interface** ([frontend/](frontend/)): React (Vite) — tabela com filtro, botão pra rodar o
   pipeline, exportar Excel e um modal que desenha as duas geometrias de um
   par sobreposto ao clicar na linha.

## Estrutura do projeto

```
.
├── app.py                  # pipeline: extract() -> intersect() -> salvar_excel()
├── api.py                  # API FastAPI que expõe o pipeline pro front-end
├── config.py                # variáveis de ambiente (DB + e-mail/Azure — e-mail ainda não está em uso)
├── requirements.txt         # dependências Python
├── Queries/
│   └── geometrias.sql       # consulta que extrai as geometrias do SQL Server
├── output/                  # Excel gerado a cada execução (ignorado pelo git)
└── frontend/                # interface React (Vite)
    └── src/
        ├── App.jsx           # tela principal: filtros, tabela, ações
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

Abra `http://localhost:5173`, clique em **"Rodar pipeline"** pra calcular as
sobreposições e depois em qualquer linha da tabela pra ver o desenho das
duas geometrias sobrepostas.

> Se a porta 8000/8001 já estiver em uso por outro processo na sua máquina,
> rode o uvicorn numa porta livre e ajuste `API_URL` em
> [frontend/src/App.jsx](frontend/src/App.jsx).

## API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/pipeline/rodar` | Roda a consulta + cálculo de sobreposição e atualiza o cache/Excel |
| `GET` | `/api/duplicados` | Lista os pares calculados (filtros: `fazenda`, `usina`, `safra`, `percentual_minimo`) |
| `GET` | `/api/duplicados/{id}/geometria` | Geometria (GeoJSON) das duas talhões de um par, pra desenhar na tela |
| `GET` | `/api/duplicados/excel` | Baixa o último Excel gerado |

Documentação interativa (Swagger) disponível em `http://localhost:8001/docs`
com a API rodando.

## Pendências conhecidas

- `config.py` já tem variáveis pra envio de e-mail (`EMAIL_*`) e Azure AD
  (`AZURE_*`), mas isso ainda não foi implementado em nenhum lugar — hoje o
  resultado só fica disponível na tela e no Excel gerado em `output/`.
