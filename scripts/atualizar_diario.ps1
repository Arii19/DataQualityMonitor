# Roda a extração diária de geometrias duplicadas (todos os 9 clientes) via
# Claude Code headless, chamando a skill .claude/skills/atualizar-geometrias.
# Pensado pra ser disparado pelo Agendador de Tarefas do Windows — ver
# scripts/instalar_tarefa_agendada.ps1 pra registrar isso como tarefa diária.
#
# O smartbio só é consultável de dentro de uma sessão do Claude Code
# autenticada (não existe API de serviço separada) — por isso o "cron" real
# aqui é uma invocação do próprio `claude`, não um script python sozinho.

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$logDir = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("atualizacao_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$prompt = "/atualizar-geometrias todos os clientes"

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append -Encoding utf8

claude -p $prompt `
  --allowedTools "Skill,Bash,Read,mcp__claude_ai_MCP_Smartbio__execute_query" `
  *>&1 | Tee-Object -FilePath $logFile -Append -Encoding utf8

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append -Encoding utf8
