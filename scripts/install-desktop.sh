#!/usr/bin/env bash
# Install Local AI Hub as a desktop app: icon (SVG + PNG sizes) + .desktop entry
# into ~/.local/share, so it appears in the app launcher and can be pinned.
# Double-clicking runs the venv Python directly — no terminal, no activation.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
NAME="local-ai-hub"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
HICOLOR="$DATA/icons/hicolor"

[ -x "$PY" ] || { echo "venv Python not found at $PY — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }

echo "Rendering icon PNGs..."
"$PY" "$REPO/scripts/render_icon.py" "$REPO/assets/$NAME.svg" "$HICOLOR"

echo "Installing scalable SVG..."
install -Dm644 "$REPO/assets/$NAME.svg" "$HICOLOR/scalable/apps/$NAME.svg"

echo "Writing .desktop entry..."
DESK="$DATA/applications/$NAME.desktop"
mkdir -p "$(dirname "$DESK")"
cat > "$DESK" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Local AI Hub
GenericName=Local AI Service Manager
Comment=Manage local AI services (Ollama, Open WebUI, ComfyUI) and their models
Exec="$PY" "$REPO/app.py"
Path=$REPO
Icon=$NAME
Terminal=false
Categories=Utility;
Keywords=AI;LLM;Ollama;OpenWebUI;ComfyUI;models;
StartupNotify=true
StartupWMClass=local-ai-hub
EOF

echo "Refreshing desktop + icon caches..."
update-desktop-database "$DATA/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HICOLOR" 2>/dev/null || true
kbuildsycoca6 2>/dev/null || kbuildsycoca5 2>/dev/null || true

echo "Done. 'Local AI Hub' should now be in your application launcher."
echo "  desktop file: $DESK"
