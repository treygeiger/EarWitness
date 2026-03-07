#!/bin/bash
# ──────────────────────────────────────────────────
#  EarWitness — One-Time Setup
#  Double-click this file to install dependencies.
# ──────────────────────────────────────────────────

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}══════════════════════════════════════${NC}"
echo -e "${BOLD}       EarWitness — Setup             ${NC}"
echo -e "${BOLD}══════════════════════════════════════${NC}"
echo ""

# ── Check for Python 3.11+ ──
echo -e "${BOLD}[1/4] Checking Python...${NC}"
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
        echo -e "  ${GREEN}✓${NC} Python $PY_VERSION found"
    else
        echo -e "  ${RED}✗ Python 3.11+ required (found $PY_VERSION)${NC}"
        echo "  Install from https://www.python.org/downloads/ or run: brew install python"
        echo ""
        echo "Press any key to close..."
        read -n 1
        exit 1
    fi
else
    echo -e "  ${RED}✗ Python 3 not found${NC}"
    echo "  Install from https://www.python.org/downloads/ or run: brew install python"
    echo ""
    echo "Press any key to close..."
    read -n 1
    exit 1
fi

# ── Check for ffmpeg ──
echo -e "${BOLD}[2/4] Checking ffmpeg...${NC}"
if command -v ffmpeg &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} ffmpeg found"
else
    echo -e "  ${YELLOW}! ffmpeg not found — installing via Homebrew...${NC}"
    if command -v brew &>/dev/null; then
        brew install ffmpeg
        echo -e "  ${GREEN}✓${NC} ffmpeg installed"
    else
        echo -e "  ${RED}✗ Homebrew not found. Please install ffmpeg manually:${NC}"
        echo "    brew install ffmpeg"
        echo "  Or install Homebrew first: https://brew.sh"
        echo ""
        echo "Press any key to close..."
        read -n 1
        exit 1
    fi
fi

# ── Create virtual environment and install deps ──
echo -e "${BOLD}[3/4] Installing Python dependencies...${NC}"
echo "  (This may take a few minutes on first run)"
echo ""
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
    echo -e "  ${GREEN}✓${NC} Virtual environment created"
fi
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip --quiet
pip install -r "$APP_DIR/requirements.txt" --quiet
echo -e "  ${GREEN}✓${NC} Dependencies installed"

# ── Set up .env if needed ──
echo -e "${BOLD}[4/4] Configuration...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo -e "  ${GREEN}✓${NC} Created .env from template"
    echo -e "  ${YELLOW}!${NC} You can configure API keys in the app's Settings (gear icon)"
else
    echo -e "  ${GREEN}✓${NC} .env already exists"
fi

echo ""
echo -e "${BOLD}══════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Setup complete!${NC}"
echo -e "${BOLD}══════════════════════════════════════${NC}"
echo ""
echo "  To launch EarWitness, double-click:"
echo -e "  ${BOLD}EarWitness.command${NC}"
echo ""
echo "  For local transcription, you also need a"
echo "  HuggingFace token (free). See README.md."
echo ""
echo "Press any key to close..."
read -n 1
