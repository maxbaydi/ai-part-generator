$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

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
    Write-Error "Python not found. Install Python or set AI_PART_GENERATOR_PYTHON environment variable"
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
  Write-Error "Bridge dependencies not found (fastapi/uvicorn). Install: $pyDisplay -m pip install -r `"$req`""
  exit 1
}

& $pythonExe @pythonArgs (Join-Path $scriptDir "app.py")

