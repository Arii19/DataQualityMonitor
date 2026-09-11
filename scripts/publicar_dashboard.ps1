# Regenera dist/dashboard.html a partir do cache mais recente.
#
# NÃO publica sozinho no artifact: a ferramenta de publicação só existe numa
# sessão interativa do Claude Code/claude.ai, não numa chamada `claude -p`
# isolada (testado e confirmado).
#
# Fluxo real:
#   1. Rode este script (ou espere a tarefa das 07:55) pra deixar
#      dist/dashboard.html atualizado no disco.
#   2. Numa conversa do Claude Code, peça "atualiza e republica o
#      dashboard" — ele republica dist/dashboard.html no mesmo link.
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

# URL do artifact: https://claude.ai/code/artifact/db50ea50-a6bf-415a-9c2c-e3bea1e8ae60

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
