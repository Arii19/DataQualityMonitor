# Roda a extração diária de geometrias duplicadas E dos relatórios
# ManagerVision (todos os 9 clientes) via Claude Code headless, chamando as
# skills .claude/skills/atualizar-geometrias e
# .claude/skills/atualizar-relatorios-managervision, gera os PDFs dos
# relatórios (Playwright) e regenera dist/dashboard.html (dado pro artifact
# somente-leitura usado por quem acessa de fora da rede local). No final,
# manda um e-mail avisando que está pronto pra republicar.
#
# NÃO republica o artifact sozinho: a ferramenta Artifact (e, dependendo da
# configuração de autenticação, até o MCP do smartbio) não fica disponível de
# forma confiável numa sessão `claude -p` disparada pelo Agendador de Tarefas
# do Windows — testado e confirmado várias vezes (ver histórico do projeto).
# Definir CLAUDE_CODE_OAUTH_TOKEN pra "resolver" o Artifact troca o modo de
# autenticação da sessão e quebra o acesso ao MCP do smartbio, que é pior
# ainda — não faça isso. O fluxo real é: essa tarefa deixa dist/dashboard.html
# sempre atualizado no disco, e avisa por e-mail; pra republicar o link, rode
# scripts/publicar_dashboard.ps1 (você mesma, num terminal comum) ou peça pro
# Claude Code numa sessão ativa ("republica o dashboard").
#
# Pensado pra ser disparado pelo Agendador de Tarefas do Windows — ver
# scripts/instalar_tarefa_agendada.ps1 pra registrar isso como tarefa diária.
#
# O smartbio só é consultável de dentro de uma sessão do Claude Code
# autenticada (não existe API de serviço separada) — por isso o "cron" real
# aqui é uma invocação do próprio `claude`, não um script python sozinho. Já
# a geração de PDF (Playwright) e o build do dashboard não precisam do MCP —
# mas ficam dentro do mesmo prompt/sessão só pra manter tudo num log só.
#
# URL do artifact (dashboard.html) pra republicar manualmente:
# https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# O Agendador de Tarefas do Windows não herda o PATH de um terminal
# interativo — "claude" (gerenciado pelo nvm em C:\tools\nvm\nodejs) não é
# encontrado nesse contexto, e a tarefa falha em menos de 1s sem log nenhum
# (já aconteceu, "Último resultado: 1"). Por isso chamamos pelo caminho
# completo, em vez de confiar em `claude` estar no PATH.
$claudeCmd = "C:\tools\nvm\nodejs\claude.cmd"
if (-not (Test-Path $claudeCmd)) {
    throw "claude.cmd não encontrado em $claudeCmd — o nvm deve ter mudado de lugar. Rode 'where.exe claude' num terminal interativo e atualize esse caminho."
}

$logDir = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("atualizacao_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$prompt = @"
/atualizar-geometrias todos os clientes

Depois de terminar a extração e confirmar que cache/<cliente>.json foi
regravado pros 9 clientes, rode /atualizar-relatorios-managervision todos os
clientes (atualiza cache/managervision/<cliente>.json via MCP e gera os PDFs
via Playwright — esse passo de PDF pode levar uns 8 minutos, dê um timeout
de pelo menos 600000ms no Bash pra ele).

Por fim, com os dois caches atualizados, rode em sequência:
  venv/Scripts/python scripts/build_dashboard.py
  venv/Scripts/python scripts/notificar_dashboard_pronto.py

Não tente publicar nem acessar a ferramenta Artifact — isso não roda nesta
sessão headless, é feito manualmente depois (é isso que o e-mail do último
passo avisa).

Se qualquer passo falhar (extração, geração de PDF, build ou notificação),
pare e reporte o erro claramente — não tente workaround.
"@

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append

& $claudeCmd -p $prompt `
  --allowedTools "Skill,Bash,Read,Write,mcp__claude_ai_MCP_Smartbio__execute_query,mcp__claude_ai_MCP_Smartbio__list_charts" `
  *>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append
