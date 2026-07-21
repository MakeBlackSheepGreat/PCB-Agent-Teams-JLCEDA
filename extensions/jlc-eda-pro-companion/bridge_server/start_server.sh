#!/usr/bin/env bash
# JLCEDA Design Companion Bridge - One-Click Start (Linux / macOS)
set -u

echo "============================================"
echo "  JLCEDA Design Companion Bridge - One-Click Start"
echo "============================================"
echo

# --- Resolve script directory (works on Linux & macOS, handles symlinks) ---
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# --- Configuration ---
SERVER_DIR="$SCRIPT_DIR"

# --- Helpers ---
fail() {
    echo
    echo "ERROR: $1"
    echo
    exit 1
}

# Pick a Python interpreter (prefer python3).
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
fi

# --- Step 1: Check Python ---
echo "[1/5] Checking Python..."
if [ -z "$PY" ]; then
    echo "Python not found. Attempting to install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew >/dev/null 2>&1; then
            brew install python
        else
            fail "Homebrew not found. Install Python 3.8+ from https://www.python.org/downloads/ and re-run this script."
        fi
    else
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y python3 python3-pip
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y python3 python3-pip
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S --noconfirm python python-pip
        else
            fail "Could not detect a package manager. Install Python 3.8+ manually and re-run this script."
        fi
    fi
    if command -v python3 >/dev/null 2>&1; then
        PY="python3"
    elif command -v python >/dev/null 2>&1; then
        PY="python"
    else
        fail "Python installation did not succeed. Please install Python 3.8+ manually."
    fi
fi
echo "  Found $("$PY" --version 2>&1)"

# --- Step 2: Verify bundled bridge server files ---
echo
echo "[2/5] Verifying bundled bridge server files..."

FILES="server.py routing_runner.py easyeda_to_kicad.py kicad_diff.py layer_mapping.py models.py coord_transform.py analysis.py review.py verify_precision.py requirements.txt"

if command -v curl >/dev/null 2>&1; then
    DL() { curl -fsSL "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
    DL() { wget -q "$1" -O "$2"; }
else
    fail "Neither curl nor wget is available. Please install one and re-run this script."
fi

for f in $FILES; do
    if [ ! -f "$SERVER_DIR/$f" ]; then
        fail "Missing bundled file: $f. Reinstall a complete release package."
    else
        echo "  $f already exists, skipping"
    fi
done
echo "  All files OK"

# --- Step 3: Check pip dependencies ---
echo
echo "[3/5] Checking Python dependencies..."

if ! "$PY" -c "import fastapi; import uvicorn; import numpy" 2>/dev/null; then
    echo "  Installing dependencies (this may take a few minutes)..."
    if ! "$PY" -m pip install --timeout 60 --retries 5 -r "$SERVER_DIR/requirements.txt"; then
        echo "  Official PyPI failed; retrying via Tsinghua mirror (faster in China)..."
        if ! "$PY" -m pip install --timeout 60 --retries 5 -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$SERVER_DIR/requirements.txt"; then
            fail "Failed to install Python dependencies. The exact pip error is shown above. Manual retry with the China mirror: $PY -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt"
        fi
    fi
fi
echo "  Dependencies OK"

# --- Step 4: Check KiCadRoutingTools ---
echo
echo "[4/5] Checking KiCadRoutingTools..."

TOOLS_DIR="$SCRIPT_DIR/KiCadRoutingTools"
if [ ! -f "$TOOLS_DIR/route.py" ]; then
    echo "  KiCadRoutingTools not found, downloading..."
    ZIP_FILE="$SCRIPT_DIR/KiCadRoutingTools.zip"
    if ! DL "https://github.com/drandyhaas/KiCadRoutingTools/archive/refs/tags/v0.18.0.zip" "$ZIP_FILE"; then
        fail "Failed to download KiCadRoutingTools. Please check your network connection."
    fi
    echo "  Extracting..."
    if command -v unzip >/dev/null 2>&1; then
        unzip -q -o "$ZIP_FILE" -d "$SCRIPT_DIR" || fail "Failed to extract KiCadRoutingTools."
    elif command -v tar >/dev/null 2>&1; then
        tar -xf "$ZIP_FILE" -C "$SCRIPT_DIR" || fail "Failed to extract KiCadRoutingTools."
    else
        fail "Neither unzip nor tar is available to extract the archive."
    fi
    rm -rf "$TOOLS_DIR"
    mv "$SCRIPT_DIR"/KiCadRoutingTools-* "$TOOLS_DIR"
    rm -f "$ZIP_FILE"
fi
echo "  KiCadRoutingTools OK"

# --- Step 4b: Build / fetch Rust router ---
# build_router.py downloads a prebuilt binary by default and falls back to a
# local cargo build, so a Rust toolchain is optional.
if [ ! -f "$TOOLS_DIR/rust_router/grid_router.so" ]; then
    echo "  Setting up Rust router (downloading prebuilt binary, or building from source)..."
    ( cd "$TOOLS_DIR" && "$PY" build_router.py --tag v0.18.0 ) || \
        fail "Rust router setup failed. Install Rust from https://rustup.rs/ and re-run, or check your network."
    echo "  Rust router ready"
else
    echo "  Rust router OK"
fi

# --- Step 5: Start server ---
echo
echo "[5/5] Starting bridge server..."
echo
echo "============================================"
echo "  Server running at http://127.0.0.1:8766"
echo "  Press Ctrl+C to stop"
echo "============================================"
echo

cd "$SERVER_DIR"
exec "$PY" server.py
