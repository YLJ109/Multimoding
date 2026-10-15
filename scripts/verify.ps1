$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python interpreter not found: $python"
}

$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = Join-Path $root 'src'

Push-Location $root
try {
    & (Join-Path $PSScriptRoot 'release_check.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'release preflight failed' }
    & $python -m compileall -q src tests
    if ($LASTEXITCODE -ne 0) { throw 'compileall failed' }
    & $python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw 'ruff failed' }
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
    & $python scripts\smoke_webengine.py verify
    if ($LASTEXITCODE -ne 0) { throw 'WebEngine renderer smoke test failed' }
}
finally {
    Pop-Location
}
