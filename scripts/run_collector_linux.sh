#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
UV_BIN="${UV_BIN:-}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 /absolute/path/to/config.ini [collector args...]" >&2
  exit 2
fi

CONFIG_PATH="$1"
shift

if [[ "$CONFIG_PATH" != /* ]]; then
  echo "Config path must be absolute: $CONFIG_PATH" >&2
  exit 2
fi

if [ ! -f "$CONFIG_PATH" ]; then
  echo "Config file not found: $CONFIG_PATH" >&2
  exit 2
fi

cd "$APP_DIR"
mkdir -p data logs

if [ -z "$UV_BIN" ]; then
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  elif [ -x /usr/local/bin/uv ]; then
    UV_BIN="/usr/local/bin/uv"
  elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
  fi
fi

if [ -n "$UV_BIN" ] && [ -x "$UV_BIN" ]; then
  exec "$UV_BIN" run --no-dev --python "$PYTHON_VERSION" \
    python -m collectors.gp350_collector --config "$CONFIG_PATH" "$@"
fi

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" -m collectors.gp350_collector --config "$CONFIG_PATH" "$@"
fi

echo "No uv or .venv Python found. Run: uv sync --no-dev" >&2
exit 127
