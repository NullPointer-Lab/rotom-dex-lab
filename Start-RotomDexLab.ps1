$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Updater = Join-Path $ProjectRoot "Update-RotomDexLab.ps1"
if ((Test-Path $Updater) -and $env:ROTOM_DEX_SKIP_UPDATE -ne "1") {
  powershell -ExecutionPolicy Bypass -File $Updater
}
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$Port = if ($env:ROTOM_DEX_PORT) { $env:ROTOM_DEX_PORT } else { "8765" }
$BindHost = if ($env:ROTOM_DEX_BIND_HOST) { $env:ROTOM_DEX_BIND_HOST } else { "0.0.0.0" }

if (-not ($Port -match '^\d{1,5}$') -or [int]$Port -lt 1 -or [int]$Port -gt 65535) {
  throw "ROTOM_DEX_PORT inválido: $Port"
}
if (-not ($BindHost -match '^[A-Za-z0-9\.:-]+$')) {
  throw "ROTOM_DEX_BIND_HOST inválido: $BindHost"
}

$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
  Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $LanIp) { $LanIp = "127.0.0.1" }
$UiUrl = "http://${LanIp}:${Port}"

Write-Host "Iniciando Rotom Dex Lab..." -ForegroundColor Cyan
Write-Host "UI na rede interna: $UiUrl" -ForegroundColor Green
Write-Host "Atenção: a bridge ficará acessível na LAN. Use apenas em rede doméstica confiável." -ForegroundColor Yellow
Set-Location $ProjectRoot

if (-not (Test-Path (Join-Path $ProjectRoot ".venv"))) {
  Write-Host "Ambiente virtual não encontrado. Criando .venv..." -ForegroundColor Yellow
  python -m venv .venv
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -r requirements.txt
}

$ArduinoCli = Get-Command arduino-cli -ErrorAction SilentlyContinue
if (-not $ArduinoCli) {
  Write-Host "Aviso: arduino-cli não encontrado no PATH. A UI abrirá, mas comandos Arduino falharão até instalar/configurar." -ForegroundColor Yellow
}

Start-Process -FilePath $Python -WorkingDirectory $ProjectRoot -ArgumentList @(
  "-m",
  "uvicorn",
  "bridge.server:app",
  "--host",
  $BindHost,
  "--port",
  $Port
)

Start-Sleep -Seconds 2
Start-Process $UiUrl
