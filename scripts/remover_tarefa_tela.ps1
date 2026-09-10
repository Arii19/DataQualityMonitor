# Remove a tarefa agendada criada por scripts/instalar_tarefa_tela.ps1.
# Não derruba a tela/túnel já em execução — só impede que subam de novo
# sozinhos no próximo login. Pra parar agora: feche os processos
# uvicorn/cloudflared.exe pelo Gerenciador de Tarefas.

$ErrorActionPreference = "Stop"

$nomeTarefa = "DataQualityMonitor - Tela"

schtasks /Delete /F /TN $nomeTarefa

Write-Output "Tarefa '$nomeTarefa' removida."
