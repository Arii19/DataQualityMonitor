# Registra a tarefa agendada do Windows que roda a atualização diária
# (scripts/atualizar_diario.ps1) todo dia às 06:00, hora local.
# Rode isso uma vez, manualmente, num PowerShell comum (não precisa admin,
# a tarefa fica só pro seu usuário).
#
# Reexecutar este script atualiza a tarefa existente (SchTasks /Create /F).
# Pra remover: scripts/remover_tarefa_agendada.ps1

$ErrorActionPreference = "Stop"

$nomeTarefa = "DataQualityMonitor - Atualizar geometrias"
$raiz = Split-Path -Parent $PSScriptRoot
$scriptAlvo = Join-Path $raiz "scripts\atualizar_diario.ps1"

$acao = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptAlvo`""

schtasks /Create /F `
  /TN $nomeTarefa `
  /TR "powershell.exe $acao" `
  /SC DAILY `
  /ST 07:40 `
  /RL LIMITED

Write-Output "Tarefa '$nomeTarefa' criada — roda todo dia às 07:40 (precisa do notebook ligado/logado nesse horário)."
Write-Output "Pra rodar uma vez agora e conferir: schtasks /Run /TN `"$nomeTarefa`""
Write-Output "Pra ver o histórico: abra o 'Agendador de Tarefas' do Windows e procure por '$nomeTarefa'."
