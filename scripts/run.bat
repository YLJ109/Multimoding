@echo off
setlocal

rem Resolve repo root from this script location (scripts\.. -> repo root)
set "ROOT=%~dp0.."

rem Fixed interpreter from the project's conda environment
set "PYTHON=C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Python interpreter not found: %PYTHON%
    echo Please verify the conda environment path.
    pause
    exit /b 1
)

rem Keep the managed env isolated from any user-level Python install
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH=%ROOT%\src"

rem Uncomment the next line to run headless (no display), e.g. CI / virtual display:
rem set "QT_QPA_PLATFORM=offscreen"

cd /d "%ROOT%"
"%PYTHON%" -m dance_mirror.app

if errorlevel 1 (
    echo [ERROR] DanceMirror exited with code %errorlevel%.
    pause
)

endlocal
