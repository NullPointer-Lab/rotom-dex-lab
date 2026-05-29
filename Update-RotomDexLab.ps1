$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Write-Rotom($Message, $Color = "Cyan") {
  Write-Host "[Rotom Dex] $Message" -ForegroundColor $Color
}

function Update-FromGitIfAvailable {
  if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) { return $false }
  $Git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $Git) {
    Write-Rotom "Git não está instalado. Pulando atualização automática." "Yellow"
    return $false
  }

  Write-Rotom "Procurando atualizações..."
  git pull --ff-only
  if ($LASTEXITCODE -ne 0) {
    Write-Rotom "Não consegui atualizar pelo Git. Vou continuar com a versão que já está aqui." "Yellow"
    return $false
  }
  Write-Rotom "Atualização concluída." "Green"
  return $true
}

function Update-FromZipIfConfigured {
  $UpdateUrl = $env:ROTOM_DEX_UPDATE_URL
  if (-not $UpdateUrl) { return $false }

  if (-not ($UpdateUrl -match '^https://')) {
    Write-Rotom "Atualização por ZIP exige URL HTTPS. Pulando atualização." "Yellow"
    return $false
  }
  $ExpectedSha256 = $env:ROTOM_DEX_UPDATE_SHA256
  if (-not $ExpectedSha256) {
    Write-Rotom "Atualização por ZIP exige ROTOM_DEX_UPDATE_SHA256. Pulando atualização para evitar código sem verificação." "Yellow"
    return $false
  }

  $TempDir = Join-Path $env:TEMP ("rotom-dex-update-" + [Guid]::NewGuid().ToString("N"))
  $ZipPath = Join-Path $TempDir "rotom-dex-lab.zip"
  $ExtractDir = Join-Path $TempDir "extract"
  New-Item -ItemType Directory -Force -Path $TempDir, $ExtractDir | Out-Null

  try {
    Write-Rotom "Baixando atualização..."
    Invoke-WebRequest -Uri $UpdateUrl -OutFile $ZipPath
    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
      throw "SHA256 diferente do esperado"
    }
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
    $Source = Get-ChildItem $ExtractDir | Select-Object -First 1
    if ($Source -and $Source.PSIsContainer) { $SourcePath = $Source.FullName } else { $SourcePath = $ExtractDir }

    Write-Rotom "Instalando atualização..."
    robocopy $SourcePath $ProjectRoot /E /XD .venv .git __pycache__ /XF config\projects.json | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy falhou com código $LASTEXITCODE" }
    Write-Rotom "Atualização instalada." "Green"
    return $true
  } catch {
    Write-Rotom "Não consegui atualizar pelo ZIP: $($_.Exception.Message). Vou continuar com a versão atual." "Yellow"
    return $false
  } finally {
    Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
  }
}

$Updated = Update-FromGitIfAvailable
if (-not $Updated) { [void](Update-FromZipIfConfigured) }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Rotom "Criando ambiente Python..." "Yellow"
  python -m venv .venv
}

Write-Rotom "Atualizando pacotes Python..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

Write-Rotom "Pronto. Agora abra o Rotom Dex Lab." "Green"
