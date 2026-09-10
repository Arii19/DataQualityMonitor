# Roda a extração diária de geometrias duplicadas E dos relatórios
# ManagerVision (todos os 9 clientes) via Claude Code headless, chamando as
# skills .claude/skills/atualizar-geometrias e
# .claude/skills/atualizar-relatorios-managervision, e gera os PDFs dos
# relatórios (Playwright). No final, manda os e-mails automáticos por
# cliente: um com o Excel de geometrias duplicadas e outro com os PDFs dos
# relatórios ManagerVision, cada um só pro(s) destinatário(s) daquele
# cliente (config.EMAIL_POR_CLIENTE).
#
# Não tem passo de "publicar dashboard" nenhum: a tela (React + FastAPI),
# local e a exposta via túnel Cloudflare (scripts/iniciar_tela.ps1, ver
# README "Dashboard remoto"), lê cache/ e output/ direto do disco — o mesmo
# disco que esta tarefa escreve. A tela reflete o dado mais novo sozinha,
# sem rebuild nem restart de nada.
#
# Pensado pra ser disparado pelo Agendador de Tarefas do Windows — ver
# scripts/instalar_tarefa_agendada.ps1 pra registrar isso como tarefa diária.
#
# O smartbio só é consultável de dentro de uma sessão do Claude Code
# autenticada (não existe API de serviço separada) — por isso o "cron" real
# aqui é uma invocação do próprio `claude`, não um script python sozinho. Já
# a geração de PDF (Playwright) e o envio dos e-mails não precisam do MCP —
# mas ficam dentro do mesmo prompt/sessão só pra manter tudo num log só.

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
  venv/Scripts/python scripts/enviar_email_geometrias.py
  venv/Scripts/python scripts/enviar_email_relatorios.py

Esses dois scripts mandam um e-mail por cliente (um de geometrias, um de
relatórios), cada um só pro(s) destinatário(s) daquele cliente — não é
preciso fazer mais nada manualmente pra isso, nem publicar nada em lugar
nenhum.

Se qualquer passo falhar (extração, geração de PDF ou envio de e-mail),
pare e reporte o erro claramente — não tente workaround.
"@

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append

& $claudeCmd -p $prompt `
  --allowedTools "Skill,Bash,Read,Write,mcp__claude_ai_MCP_Smartbio__execute_query,mcp__claude_ai_MCP_Smartbio__list_charts" `
  *>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append
