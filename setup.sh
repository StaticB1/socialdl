#!/usr/bin/env bash
# One-time setup: create the virtualenv and install socialdl (+ its deps).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "→ creating virtualenv (.venv)"
python3 -m venv .venv

echo "→ installing socialdl and dependencies (gallery-dl, yt-dlp, mcp, fastapi, uvicorn)"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e .

echo "→ linking commands into ~/.local/bin (if on PATH)"
mkdir -p "$HOME/.local/bin"
for cmd in socialdl socialdl-mcp socialdl-serve; do
  ln -sfn "$HERE/.venv/bin/$cmd" "$HOME/.local/bin/$cmd"
done

cat <<'EOF'
✓ done. Three ways to use it:

  CLI :  socialdl natgeo --platform instagram --images-only --json
  MCP :  socialdl-mcp                 (register with an MCP client)
  HTTP:  socialdl-serve               (REST API on 127.0.0.1:8000, docs at /docs)

Auth: export a cookies.txt from a logged-in browser and pass --cookies FILE
(or set it in ~/.config/socialdl/config.toml). See README.md.
EOF
