# Remove a tarefa agendada criada por instalar_tarefa_agendada.ps1.

$nomeTarefa = "DataQualityMonitor - Atualizar geometrias"
schtasks /Delete /TN $nomeTarefa /F
Write-Output "Tarefa '$nomeTarefa' removida."
