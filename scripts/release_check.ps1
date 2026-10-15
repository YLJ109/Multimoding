$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$requiredFiles = @(
    'README.md',
    'pyproject.toml',
    'docs\ARCHITECTURE.md',
    'docs\ENVIRONMENT.md',
    'docs\RELEASE_GUIDE.md',
    'src\dance_mirror\app.py',
    'src\dance_mirror\resources\ASSET_LICENSES.md',
    'src\dance_mirror\resources\dance_robot_cyber.glb',
    'src\dance_mirror\resources\three.core.min.js',
    'src\dance_mirror\resources\three.module.min.js'
)

Push-Location $root
try {
    Write-Host 'Release preflight: required files'
    foreach ($relativePath in $requiredFiles) {
        $path = Join-Path $root $relativePath
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required release file is missing: $relativePath"
        }
    }

    Write-Host 'Release preflight: secret scan'
    $excluded = '\\(\.pytest_cache|\.ruff_cache|\.runtime-smoke|__pycache__|build|dist)\\'
    $textExtensions = @('.py', '.md', '.toml', '.ps1', '.json', '.yaml', '.yml', '.txt', '.ini')
    $secretPatterns = @(
        'sk-[A-Za-z0-9_.-]{16,}',
        'AKIA[0-9A-Z]{16}',
        'AIza[0-9A-Za-z_-]{30,}',
        '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
    )
    $textFiles = Get-ChildItem -LiteralPath $root -Recurse -File |
        Where-Object {
            $_.FullName -notmatch $excluded -and $_.Extension.ToLowerInvariant() -in $textExtensions
        }
    foreach ($file in $textFiles) {
        foreach ($pattern in $secretPatterns) {
            $match = Select-String -LiteralPath $file.FullName -Pattern $pattern -Encoding UTF8 -List
            if ($match) {
                throw "Potential secret found in $($file.FullName):$($match.LineNumber)"
            }
        }
    }

    Write-Host 'Release preflight: environment doctor'
    & (Join-Path $PSScriptRoot 'doctor.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'Environment doctor failed.'
    }

    $manifest = [ordered]@{
        checked_at = (Get-Date).ToUniversalTime().ToString('o')
        project_root = $root
        required_files = $requiredFiles.Count
        text_files_scanned = $textFiles.Count
        secret_findings = 0
        status = 'pass'
    }
    Write-Host 'Release preflight passed.'
    $manifest | ConvertTo-Json
}
finally {
    Pop-Location
}
