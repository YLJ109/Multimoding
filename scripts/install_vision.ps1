param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python interpreter not found: $python"
}

$env:PYTHONNOUSERSITE = '1'

if (-not $SkipInstall) {
    & $python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) {
        throw 'PyTorch CUDA installation failed.'
    }

    & $python -m pip install ultralytics onnxruntime-gpu
    if ($LASTEXITCODE -ne 0) {
        throw 'YOLO runtime installation failed.'
    }

    & $python -m pip install mediapipe sounddevice
    if ($LASTEXITCODE -ne 0) {
        throw 'MediaPipe/audio input installation failed.'
    }

    & $python -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print('gpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
}

$appHome = if ($env:DANCE_MIRROR_HOME) {
    [System.IO.Path]::GetFullPath($env:DANCE_MIRROR_HOME)
} else {
    Join-Path $env:LOCALAPPDATA 'DanceMirror'
}
$models = Join-Path $appHome 'models'
New-Item -ItemType Directory -Force -Path $models | Out-Null
$modelPath = Join-Path $models 'yolo11n-pose.pt'
$expectedSha256 = '869E83FCDFFDC7371FA4E34CD8E51C838CC729571D1635E5141E3075E9319DC0'

$needsDownload = $true
if (Test-Path -LiteralPath $modelPath) {
    $existingSha256 = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash
    $needsDownload = $existingSha256 -ne $expectedSha256
}

if ($needsDownload) {
    $downloadUrls = @(
        'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt',
        'https://hf-mirror.com/Ultralytics/YOLO11/resolve/main/yolo11n-pose.pt'
    )
    $downloaded = $false
    foreach ($url in $downloadUrls) {
        & curl.exe -L --fail --retry 2 --retry-delay 2 --max-time 120 -o $modelPath $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $modelPath)) {
            $downloaded = $true
            break
        }
    }
    if (-not $downloaded) {
        throw 'Unable to download yolo11n-pose.pt from the configured sources.'
    }
}

$actualSha256 = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash
if ($actualSha256 -ne $expectedSha256) {
    throw "YOLO weight checksum mismatch: $actualSha256"
}

$env:DANCE_MIRROR_MODEL_PATH = $modelPath
& $python -c "import os; from ultralytics import YOLO; p=os.environ['DANCE_MIRROR_MODEL_PATH']; YOLO(p); print('model', p)"
if ($LASTEXITCODE -ne 0) {
    throw 'Downloaded YOLO model could not be loaded.'
}
