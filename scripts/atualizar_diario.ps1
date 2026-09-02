# Roda a extração diária de geometrias duplicadas (todos os 9 clientes) via
# Claude Code headless, chamando a skill .claude/skills/atualizar-geometrias,
# e em seguida regenera e republica o dashboard somente-leitura (Artifact)
# usado por quem acessa de fora da rede local — sempre no mesmo link.
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

# URL fixo do artifact publicado (dashboard.html) — republicar nesse mesmo
# link não gera um novo endereço, só troca o conteúdo. Se o link mudar (ex.:
# artifact recriado do zero), atualize aqui.
$artifactUrl = "https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60"

$prompt = @"
/atualizar-geometrias todos os clientes

Depois de terminar a extração e confirmar que cache/<cliente>.json foi
regravado pros 9 clientes, faça mais isso, nessa ordem:

1. Rode venv/Scripts/python scripts/build_dashboard.py (gera
   dist/dashboard.html com os dados novos, geometria simplificada pra
   visualização).
2. Use a ferramenta Artifact com action "read" e url "$artifactUrl" pra
   carregar a versão publicada atual (obrigatório antes de publicar de novo).
3. Use a ferramenta Artifact com action "publish", file_path
   "dist/dashboard.html" e url "$artifactUrl" (mesmas capabilities já
   configuradas, não precisa repetir) pra republicar no mesmo link.

Se qualquer um desses 3 passos falhar, pare e reporte o erro claramente —
não tente workaround.
"@

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append

claude -p $prompt `
  --allowedTools "Skill,Bash,Read,Artifact,mcp__claude_ai_MCP_Smartbio__execute_query" `
  *>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append
