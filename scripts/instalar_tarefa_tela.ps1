# Registra a tarefa agendada do Windows que sobe a tela+API+túnel
# (scripts/iniciar_tela.ps1). Idealmente seria um gatilho "ao entrar no
# Windows" (ONLOGON), mas esse tipo de gatilho foi recusado ("Acesso
# negado") no ambiente onde isso foi criado — parece uma restrição de
# segurança contra persistência automática, não algo resolvível com
# permissão de admin. A alternativa: uma tarefa DIÁRIA que repete de hora
# em hora o dia inteiro — como scripts/iniciar_tela.ps1 é idempotente (mata
# a instância anterior antes de subir de novo), cada disparo garante que a
# tela/túnel estão de pé, e um processo que caiu no meio do dia volta em
# até 1h, sem precisar de reboot/login pra "religar" nada.
#
# Se no seu ambiente o gatilho ONLOGON funcionar (não deu bloqueado), pode
# trocar `/SC DAILY /ST 07:00 /RI 60 /DU 24:00` por `/SC ONLOGON` abaixo —
# mais simples e sobe na hora que você loga, não só na próxima "hora
# cheia".
#
# Rode isso uma vez, manualmente, num PowerShell comum (não precisa admin,
# a tarefa fica só pro seu usuário).
#
# Reexecutar este script atualiza a tarefa existente (SchTasks /Create /F).
# Pra remover: scripts/remover_tarefa_tela.ps1

$ErrorActionPreference = "Stop"

$nomeTarefa = "DataQualityMonitor - Tela"
$raiz = Split-Path -Parent $PSScriptRoot
$scriptAlvo = Join-Path $raiz "scripts\iniciar_tela.ps1"

$acao = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptAlvo`""

schtasks /Create /F `
  /TN $nomeTarefa `
  /TR "powershell.exe $acao" `
  /SC DAILY `
  /ST 07:00 `
  /RI 60 `
  /DU 24:00 `
  /RL LIMITED

Write-Output "Tarefa '$nomeTarefa' criada — sobe a tela+túnel às 07:00 e revalida de hora em hora o dia todo."
Write-Output "Pra rodar uma vez agora e conferir: schtasks /Run /TN `"$nomeTarefa`""
Write-Output "O link público fica salvo em tunnel_url.txt depois de cada início."
