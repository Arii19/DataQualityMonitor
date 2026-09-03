# Roda a extração diária de geometrias duplicadas (todos os 9 clientes) via
# Claude Code headless, chamando a skill .claude/skills/atualizar-geometrias,
# e em seguida regenera dist/dashboard.html (dado pro artifact somente-leitura
# usado por quem acessa de fora da rede local).
#
# NÃO republica o artifact sozinho: a ferramenta Artifact (e, dependendo da
# configuração de autenticação, até o MCP do smartbio) não fica disponível de
# forma confiável numa sessão `claude -p` disparada pelo Agendador de Tarefas
# do Windows — testado e confirmado várias vezes (ver histórico do projeto).
# Definir CLAUDE_CODE_OAUTH_TOKEN pra "resolver" o Artifact troca o modo de
# autenticação da sessão e quebra o acesso ao MCP do smartbio, que é pior
# ainda — não faça isso. O fluxo real é: essa tarefa deixa dist/dashboard.html
# sempre atualizado no disco; pra republicar o link, rode
# scripts/publicar_dashboard.ps1 (você mesma, num terminal comum) ou peça pro
# Claude Code numa sessão ativa.
#
# Pensado pra ser disparado pelo Agendador de Tarefas do Windows — ver
# scripts/instalar_tarefa_agendada.ps1 pra registrar isso como tarefa diária.
#
# O smartbio só é consultável de dentro de uma sessão do Claude Code
# autenticada (não existe API de serviço separada) — por isso o "cron" real
# aqui é uma invocação do próprio `claude`, não um script python sozinho.
#
# URL do artifact (dashboard.html) pra republicar manualmente:
# https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$logDir = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("atualizacao_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$prompt = @"
/atualizar-geometrias todos os clientes

Depois de terminar a extração e confirmar que cache/<cliente>.json foi
regravado pros 9 clientes, rode venv/Scripts/python scripts/build_dashboard.py
(gera dist/dashboard.html com os dados novos, geometria simplificada pra
visualização). Não tente publicar nem acessar a ferramenta Artifact — isso
não roda nesta sessão headless, é feito manualmente depois.

Se a extração ou o build_dashboard.py falharem, pare e reporte o erro
claramente — não tente workaround.
"@

Write-Output "[$(Get-Date -Format o)] iniciando atualização diária..." | Tee-Object -FilePath $logFile -Append

claude -p $prompt `
  --allowedTools "Skill,Bash,Read,mcp__claude_ai_MCP_Smartbio__execute_query" `
  *>&1 | Tee-Object -FilePath $logFile -Append

Write-Output "[$(Get-Date -Format o)] finalizado. Log completo em $logFile" | Tee-Object -FilePath $logFile -Append
