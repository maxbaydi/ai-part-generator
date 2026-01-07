$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$pythonExe = $env:AI_PART_GENERATOR_PYTHON
$pythonArgs = @()

if ([string]::IsNullOrWhiteSpace($pythonExe)) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
    $pythonArgs = @("-3")
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
  } else {
    Write-Error "Python не найден. Установите Python или задайте переменную окружения AI_PART_GENERATOR_PYTHON"
    exit 1
  }
}

& $pythonExe @pythonArgs -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  $req = Join-Path $scriptDir "requirements.txt"
  $pyDisplay = $pythonExe
  if ($pythonArgs.Count -gt 0) {
    $pyDisplay = "$pyDisplay $($pythonArgs -join ' ')"
  }
  Write-Error "Не найдены зависимости bridge (fastapi/uvicorn). Установите: $pyDisplay -m pip install -r `"$req`""
  exit 1
}

& $pythonExe @pythonArgs (Join-Path $scriptDir "app.py")

