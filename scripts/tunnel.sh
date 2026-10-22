#!/usr/bin/env bash
set -euo pipefail
# Requires a running local server: uv run python scripts/serve.py --port 8768
exec cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8768 --protocol http2
