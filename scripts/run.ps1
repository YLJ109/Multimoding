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
    & $python -m dance_mirror.app
}
finally {
    Pop-Location
}
