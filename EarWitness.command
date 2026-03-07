#!/bin/bash
# ──────────────────────────────────────────────────
#  EarWitness — Launcher
#  Double-click this file to start the app.
# ──────────────────────────────────────────────────

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# Check that setup has been run
if [ ! -d "$APP_DIR/venv" ]; then
    echo ""
    echo "  EarWitness hasn't been set up yet."
    echo "  Please double-click 'EarWitness Setup.command' first."
    echo ""
    echo "Press any key to close..."
    read -n 1
    exit 1
fi

# Activate virtual environment
source "$APP_DIR/venv/bin/activate"

# Clear the terminal and show status
clear
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         EarWitness is running        ║"
echo "  ║                                      ║"
echo "  ║   Open:  http://localhost:8000       ║"
echo "  ║                                      ║"
echo "  ║   Close this window to stop.         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Open browser after a short delay (server needs a moment to start)
(sleep 1.5 && open "http://localhost:8000") &

# Start the server (foreground — closing Terminal window kills it)
python "$APP_DIR/run.py"
