@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   JLCEDA Design Companion Bridge - One-Click Start
echo ============================================
echo.

cd /d "%~dp0"

REM --- Configuration ---
set "SERVER_DIR=%~dp0"

REM --- Step 1: Check Python ---
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Attempting to install via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install Python automatically.
        echo Please install Python 3.8+ manually from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    echo Python installed. You may need to restart this script for PATH to take effect.
    echo.
    pause
    exit /b 0
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   Found Python %%v

REM --- Step 2: Verify bundled bridge server files ---
echo.
echo [2/5] Verifying bundled bridge server files...

set "FILES=server.py routing_runner.py easyeda_to_kicad.py kicad_diff.py layer_mapping.py models.py coord_transform.py analysis.py review.py verify_precision.py requirements.txt"

set "DOWNLOAD_OK=1"
for %%f in (%FILES%) do (
    if not exist "!SERVER_DIR!\%%f" (
        set "DOWNLOAD_OK=0"
        echo   ERROR: Missing bundled file %%f
    ) else (
        echo   %%f already exists, skipping
    )
)

if "!DOWNLOAD_OK!"=="0" (
    echo.
    echo ERROR: The extension bundle is incomplete. Reinstall a complete release package.
    echo.
    pause
    exit /b 1
)
echo   All files OK

REM --- Step 3: Check pip dependencies ---
echo.
echo [3/5] Checking Python dependencies...

python -c "import fastapi; import uvicorn; import numpy" 2>nul
if errorlevel 1 (
    echo   Installing dependencies ^(this may take a few minutes^)...
    python -m pip install --timeout 60 --retries 5 -r "!SERVER_DIR!\requirements.txt"
    if errorlevel 1 (
        echo   Official PyPI failed; retrying via Tsinghua mirror ^(faster in China^)...
        python -m pip install --timeout 60 --retries 5 -i https://pypi.tuna.tsinghua.edu.cn/simple -r "!SERVER_DIR!\requirements.txt"
        if errorlevel 1 (
            echo.
            echo ERROR: Failed to install Python dependencies.
            echo The exact pip error is shown above this message.
            echo Try manually with the China mirror:
            echo   python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
            echo.
            pause
            exit /b 1
        )
    )
)
echo   Dependencies OK

REM --- Step 4: Check KiCadRoutingTools ---
echo.
echo [4/5] Checking KiCadRoutingTools...

set "TOOLS_DIR=%~dp0KiCadRoutingTools"
if not exist "!TOOLS_DIR!\route.py" (
    echo   KiCadRoutingTools not found, downloading...
    set "ZIP_FILE=%~dp0KiCadRoutingTools.zip"
    curl -fsSL "https://github.com/drandyhaas/KiCadRoutingTools/archive/refs/tags/v0.18.0.zip" -o "!ZIP_FILE!"
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to download KiCadRoutingTools.
        echo Please check your network connection.
        echo.
        pause
        exit /b 1
    )
    echo   Extracting...
    %SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -Command "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '%~dp0' -Force" 2>nul
    if errorlevel 1 (
        tar -xf "!ZIP_FILE!" -C "%~dp0" 2>nul
        if errorlevel 1 (
            echo.
            echo ERROR: Failed to extract KiCadRoutingTools.
            echo.
            pause
            exit /b 1
        )
    )
    for /d %%D in ("%~dp0KiCadRoutingTools-*") do ren "%%D" KiCadRoutingTools 2>nul
    del "!ZIP_FILE!"
)
echo   KiCadRoutingTools OK

REM --- Step 4b: Setup Rust router ---
set "RUST_LIB=!TOOLS_DIR!\rust_router\grid_router.pyd"
if not exist "!RUST_LIB!" (
    echo   Setting up Rust router ^(downloading prebuilt binary, or building from source^)...
    cd /d "!TOOLS_DIR!"
    python build_router.py --tag v0.18.0
    if errorlevel 1 (
        echo.
        echo   ERROR: Rust router setup failed.
        echo   Check your network, or install Rust from https://rustup.rs/ and re-run.
        echo.
        pause
        exit /b 1
    )
    echo   Rust router ready
    cd /d "%~dp0"
) else (
    echo   Rust router OK
)

REM --- Step 5: Start server ---
echo.
echo [5/5] Starting bridge server...
echo.
echo ============================================
echo   Server running at http://127.0.0.1:8766
echo   Press Ctrl+C to stop
echo ============================================
echo.

cd /d "!SERVER_DIR!"
python server.py
pause
