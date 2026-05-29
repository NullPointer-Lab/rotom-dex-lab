$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Updater = Join-Path $ProjectRoot "Update-RotomDexLab.ps1"
if ((Test-Path $Updater) -and $env:ROTOM_DEX_SKIP_UPDATE -ne "1") {
  powershell -ExecutionPolicy Bypass -File $Updater
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Port = if ($env:ROTOM_DEX_PORT) { $env:ROTOM_DEX_PORT } else { "8765" }
$BindHost = if ($env:ROTOM_DEX_BIND_HOST) { $env:ROTOM_DEX_BIND_HOST } else { "0.0.0.0" }
$LogFile = Join-Path $ProjectRoot "rotom-dex-lab.log"

if (-not ($Port -match '^\d{1,5}$') -or [int]$Port -lt 1 -or [int]$Port -gt 65535) {
  throw "ROTOM_DEX_PORT inválido: $Port"
}
if (-not ($BindHost -match '^[A-Za-z0-9\.:-]+$')) {
  throw "ROTOM_DEX_BIND_HOST inválido: $BindHost"
}

Set-Location $ProjectRoot

# Always run from the venv Python. Create/install it if missing.
if (-not (Test-Path $VenvPython)) {
  Write-Host "Ambiente virtual não encontrado. Criando .venv..." -ForegroundColor Yellow
  python -m venv .venv
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -r requirements.txt
}

# Verify FastAPI/uvicorn are importable in the chosen Python before launching.
& $VenvPython -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Instalando dependências Python..." -ForegroundColor Yellow
  & $VenvPython -m pip install -r requirements.txt
  & $VenvPython -c "import fastapi, uvicorn" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "Não consegui carregar fastapi/uvicorn no Python do .venv. Veja $LogFile."
  }
}

$ArduinoCli = Get-Command arduino-cli -ErrorAction SilentlyContinue
if (-not $ArduinoCli) {
  Write-Host "Aviso: arduino-cli não encontrado no PATH. A UI abrirá, mas comandos Arduino falharão até instalar/configurar." -ForegroundColor Yellow
}

# Session token (PIN) for the LAN safety layer. Generate one if not provided.
if (-not $env:ROTOM_DEX_SESSION_TOKEN) {
  $env:ROTOM_DEX_SESSION_TOKEN = [Convert]::ToBase64String([Guid]::NewGuid().ToByteArray()).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
$Token = $env:ROTOM_DEX_SESSION_TOKEN

$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
  Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $LanIp) { $LanIp = "127.0.0.1" }
$UiUrl = "http://${LanIp}:${Port}/?token=${Token}"
$HealthUrl = "http://127.0.0.1:${Port}/api/health"

Write-Host "Iniciando Rotom Dex Lab..." -ForegroundColor Cyan
Write-Host "UI na rede interna: $UiUrl" -ForegroundColor Green
Write-Host "PIN de acesso: $Token" -ForegroundColor Green
Write-Host "Atenção: a bridge ficará acessível na LAN. Use apenas em rede doméstica confiável." -ForegroundColor Yellow
Write-Host "Log do servidor: $LogFile" -ForegroundColor DarkGray

# Start the server detached, redirecting stdout/stderr to a visible log file.
$Server = Start-Process -FilePath $VenvPython -WorkingDirectory $ProjectRoot -PassThru `
  -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" -ArgumentList @(
    "-m", "uvicorn", "bridge.server:app", "--host", $BindHost, "--port", $Port
  )

# Poll /api/health before opening the browser.
$Healthy = $false
for ($i = 0; $i -lt 30; $i++) {
  if ($Server.HasExited) { break }
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
    if ($resp.StatusCode -eq 200) { $Healthy = $true; break }
  } catch {
    Start-Sleep -Milliseconds 500
  }
}

if ($Healthy) {
  Write-Host "Servidor pronto! Abrindo o navegador..." -ForegroundColor Green
  Start-Process $UiUrl
} else {
  Write-Host ""
  Write-Host "O Rotom Dex Lab não respondeu a tempo. :(" -ForegroundColor Red
  Write-Host "Peça ajuda ao papai. O que conferir:" -ForegroundColor Yellow
  Write-Host "  1. Veja o arquivo de log: $LogFile (e $LogFile.err)" -ForegroundColor Yellow
  Write-Host "  2. Confira se a porta $Port já não está em uso." -ForegroundColor Yellow
  Write-Host "  3. Rode novamente: .\Start-RotomDexLab.ps1" -ForegroundColor Yellow
  if (Test-Path "$LogFile.err") {
    Write-Host "--- Últimas linhas do erro ---" -ForegroundColor DarkGray
    Get-Content "$LogFile.err" -Tail 15
  }
}
