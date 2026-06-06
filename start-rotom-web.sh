#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${ROTOM_DEX_PORT:-8765}"
TOKEN="${ROTOM_DEX_SESSION_TOKEN:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(16))
PY
)}"
URL="http://127.0.0.1:${PORT}/chat?token=${TOKEN}"

if [ ! -x .venv/bin/python ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "Preciso do uv para criar o ambiente Python. Peça ajuda ao papai."
    exit 1
  fi
  uv venv .venv
fi

if ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, httpx, pydantic, serial
PY
then
  uv pip install -r requirements.txt
fi

export ROTOM_DEX_SESSION_TOKEN="$TOKEN"
export ROTOM_DEX_HERMES_LOCAL_CLI="${ROTOM_DEX_HERMES_LOCAL_CLI:-1}"
export ROTOM_DEX_HERMES_TIMEOUT_SECONDS="${ROTOM_DEX_HERMES_TIMEOUT_SECONDS:-90}"
export ROTOM_DEX_PORT="$PORT"

echo "==== Rotom Web Chat ===="
echo "Abrindo: $URL"
echo "Feche esta janela para parar o servidor."

(
  sleep 2
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
) &

exec .venv/bin/python -m uvicorn bridge.server:app --host 127.0.0.1 --port "$PORT"
