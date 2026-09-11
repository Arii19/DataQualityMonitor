# Roda a extração diária de geometrias duplicadas e dos relatórios
# ManagerVision (9 clientes) via Claude Code headless (skills
# atualizar-geometrias e atualizar-relatorios-managervision), gera os PDFs
# (Playwright), regenera dist/dashboard.html e manda os e-mails automáticos
# por cliente (Excel de geometrias + PDFs de relatórios), cada um só pro(s)
# destinatário(s) daquele cliente (config.EMAIL_POR_CLIENTE).
#
# NÃO republica o artifact sozinho: a ferramenta Artifact não fica disponível
# numa sessão `claude -p` do Agendador de Tarefas (testado e confirmado).
# Definir CLAUDE_CODE_OAUTH_TOKEN pra contornar isso quebra o acesso ao MCP
# do smartbio — não faça isso. Esta tarefa só deixa dist/dashboard.html
# atualizado no disco; pra republicar, rode scripts/publicar_dashboard.ps1 ou
# peça numa sessão ativa do Claude Code ("republica o dashboard").
#
# Disparado pelo Agendador de Tarefas do Windows (ver
# scripts/instalar_tarefa_agendada.ps1). O smartbio só é consultável de
# dentro de uma sessão autenticada do Claude Code — por isso o "cron" real
# aqui é uma invocação do `claude`, não um script python isolado.
#
# URL do artifact (dashboard.html) pra republicar manualmente:
# https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# O Agendador de Tarefas não herda o PATH interativo — "claude" (via nvm)
# não é encontrado nesse contexto e a tarefa falha sem log (já aconteceu).
# Por isso chamamos pelo caminho completo.
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
  venv/Scripts/python scripts/enviar_email_geometrias.py
  venv/Scripts/python scripts/enviar_email_relatorios.py

Os dois últimos scripts mandam um e-mail por cliente (um de geometrias, um
de relatórios), cada um só pro(s) destinatário(s) daquele cliente — não é
preciso fazer mais nada manualmente pra isso.

Não tente publicar nem acessar a ferramenta Artifact — isso não roda nesta
sessão headless, é feito manualmente depois, num terminal comum
(scripts/publicar_dashboard.ps1) ou numa sessão ativa do Claude Code
("republica o dashboard").

Se qualquer passo falhar (extração, geração de PDF, build ou envio de
e-mail), pare e reporte o erro claramente — não tente workaround.
"@

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append

& $claudeCmd -p $prompt `
  --allowedTools "Skill,Bash,Read,Write,mcp__claude_ai_MCP_Smartbio__execute_query,mcp__claude_ai_MCP_Smartbio__list_charts" `
  *>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append
