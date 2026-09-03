# Regenera dist/dashboard.html a partir do cache mais recente.
#
# NÃO publica sozinho no artifact (mesmo rodando manualmente, num terminal
# comum) — testamos: funcionou quando disparado de dentro de uma sessão do
# Claude Code (VS Code), mas falhou com "ferramenta Artifact não disponível"
# quando rodado direto num terminal comum pela usuária. A ferramenta que
# publica em claude.ai/code/artifact/... parece só existir dentro de uma
# sessão interativa do Claude Code/claude.ai — não numa chamada `claude -p`
# isolada, não importa quem ou como dispara.
#
# Fluxo real, sem mais tentativa de automatizar isso via script:
#   1. Rode este script (ou espere a tarefa das 07:40) pra deixar
#      dist/dashboard.html atualizado no disco.
#   2. Numa conversa com o Claude Code (esta mesma ou outra), peça:
#      "atualiza e republica o dashboard" — ele lê a versão publicada atual
#      e republica dist/dashboard.html no mesmo link (URL abaixo).
#
# Uso:
#   .\scripts\publicar_dashboard.ps1            # só confere que dist/dashboard.html existe
#   .\scripts\publicar_dashboard.ps1 -Rebuild   # regenera a partir do cache/*.json mais recente

param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# URL do artifact — cole numa conversa do Claude Code junto do pedido de
# republicar, se for útil: https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60

if ($Rebuild) {
    Write-Output "Regenerando dist/dashboard.html a partir do cache atual..."
    & .\venv\Scripts\python.exe scripts\build_dashboard.py
}

if (-not (Test-Path "dist\dashboard.html")) {
    Write-Output "dist\dashboard.html não existe. Rode com -Rebuild, ou primeiro:"
    Write-Output "  .\venv\Scripts\python.exe scripts\build_dashboard.py"
    exit 1
}

Write-Output ""
Write-Output "dist\dashboard.html pronto. Pra publicar no link, peça numa conversa do Claude Code:"
Write-Output '  "atualiza e republica o dashboard"'
