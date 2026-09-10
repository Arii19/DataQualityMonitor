# Sobe a tela (React, build de produção) + API (FastAPI, mesma origem —
# ver StaticFiles em api.py) e o túnel Cloudflare, os dois como processos
# separados do PowerShell que os lançou — fecham a janela/sessão que rodou
# este script e eles continuam rodando (Start-Process não os prende a um
# processo pai, diferente de rodar direto no terminal).
#
# Idempotente E preguiçoso: se a tela e o túnel já estão de pé e saudáveis,
# NÃO mexe em nada — só confirma e sai. Isso importa porque o "quick
# tunnel" da Cloudflare gera um link novo (aleatório) cada vez que reinicia;
# reiniciar sem necessidade trocaria o link que as pessoas já têm
# salvo/aberto. Só mata e sobe de novo quando algo really está caído.
#
# Pensado pra rodar em tarefa agendada do tipo "diária com repetição"
# (scripts/instalar_tarefa_tela.ps1) em vez de "ao entrar no Windows": esse
# tipo de gatilho (ONLOGON) é bloqueado neste ambiente (parece restrição de
# segurança contra persistência automática). A repetição de hora em hora
# serve só pra detectar e religar algo que caiu de verdade — como o script
# não mexe em nada quando já está tudo saudável, o link fica estável o dia
# inteiro entre uma queda e outra.
#
# Não usa Docker: uvicorn e cloudflared.exe (baixado em tools/cloudflared.exe
# por não precisar de instalador/UAC) rodam nativos, direto no Windows.

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$logDir = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Processo-ApiRodando {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*api:app*" } |
        Select-Object -First 1
}

function Api-Saudavel {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8001/healthz" -UseBasicParsing -TimeoutSec 3
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

$tunnelProcesso = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
$apiProcesso = Processo-ApiRodando

if ($tunnelProcesso -and $apiProcesso -and (Api-Saudavel)) {
    $urlAtual = Join-Path $raiz "tunnel_url.txt"
    Write-Output "Tela e túnel já estão de pé e saudáveis — não mexi em nada (link continua o mesmo)."
    if (Test-Path $urlAtual) {
        Write-Output "Link público: $(Get-Content $urlAtual)"
    }
    Write-Output "Local: http://localhost:8001"
    exit 0
}

Write-Output "Algo não está saudável — encerrando instância anterior (se houver) antes de religar..."
# uvicorn.exe (venv\Scripts) roda como processo "python", não "uvicorn" —
# por isso filtra pela linha de comando (via CIM), não por nome de processo,
# senão mataria qualquer python.exe do sistema, não só o nosso.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*api:app*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$uvicorn = Join-Path $raiz "venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicorn)) {
    throw "venv\Scripts\uvicorn.exe não encontrado — rode 'pip install -r requirements.txt' no venv primeiro."
}

$cloudflared = Join-Path $raiz "tools\cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    throw "tools\cloudflared.exe não encontrado — baixe de https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe e salve em tools\cloudflared.exe."
}

Write-Output "Build da tela (frontend/dist)..."
Push-Location (Join-Path $raiz "frontend")
npm run build
Pop-Location

Write-Output "Subindo a API+tela (porta 8001)..."
Start-Process -FilePath $uvicorn `
  -ArgumentList "api:app --host 0.0.0.0 --port 8001" `
  -WorkingDirectory $raiz `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logDir "tela_out.log") `
  -RedirectStandardError (Join-Path $logDir "tela_err.log")

Write-Output "Subindo o túnel Cloudflare..."
$tunnelLog = Join-Path $logDir "tunnel.log"
Remove-Item $tunnelLog -ErrorAction SilentlyContinue
Start-Process -FilePath $cloudflared `
  -ArgumentList "tunnel --no-autoupdate --url http://localhost:8001" `
  -WorkingDirectory $raiz `
  -WindowStyle Hidden `
  -RedirectStandardError $tunnelLog

Write-Output "Aguardando o túnel registrar o link (uns 10s)..."
Start-Sleep -Seconds 10

$linha = Select-String -Path $tunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
if ($linha) {
    $url = $linha.Matches[0].Value
    Set-Content -Path (Join-Path $raiz "tunnel_url.txt") -Value $url
    Write-Output "Link publico (NOVO — o anterior parou de funcionar): $url  (tambem salvo em tunnel_url.txt)"
} else {
    Write-Output "Não achei o link ainda em $tunnelLog — confira esse arquivo em alguns segundos."
}

Write-Output "Local: http://localhost:8001"
