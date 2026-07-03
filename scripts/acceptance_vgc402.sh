#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CONFIG_PATH="${1:-$APP_DIR/config/examples/vgc402.ini}"
DURATION_SECONDS="${DURATION_SECONDS:-20}"
OUT_DIR="${OUT_DIR:-$APP_DIR/acceptance/vgc402-$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
UV_BIN="${UV_BIN:-}"

if [[ "$CONFIG_PATH" != /* ]]; then
  CONFIG_PATH="$(cd "$(dirname "$CONFIG_PATH")" && pwd)/$(basename "$CONFIG_PATH")"
fi

if [ ! -f "$CONFIG_PATH" ]; then
  echo "Config file not found: $CONFIG_PATH" >&2
  exit 2
fi

if [ -z "$UV_BIN" ]; then
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  elif [ -x /usr/local/bin/uv ]; then
    UV_BIN="/usr/local/bin/uv"
  elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
  fi
fi

if [ -z "$UV_BIN" ] || [ ! -x "$UV_BIN" ]; then
  echo "uv not found; set UV_BIN=/path/to/uv" >&2
  exit 127
fi

mkdir -p "$OUT_DIR"
cd "$APP_DIR"

echo "Acceptance output: $OUT_DIR"
echo "Config: $CONFIG_PATH"

"$UV_BIN" run --no-dev --python "$PYTHON_VERSION" \
  python -m collectors.gp350_collector \
  --config "$CONFIG_PATH" \
  --discover | tee "$OUT_DIR/discover.txt"

if command -v timeout >/dev/null 2>&1; then
  timeout --signal=INT "$DURATION_SECONDS" \
    "$UV_BIN" run --no-dev --python "$PYTHON_VERSION" \
      python -m collectors.gp350_collector \
      --config "$CONFIG_PATH" | tee "$OUT_DIR/collector.txt" || true
else
  echo "Missing timeout command. Run collector manually for $DURATION_SECONDS seconds."
  "$UV_BIN" run --no-dev --python "$PYTHON_VERSION" \
    python -m collectors.gp350_collector \
    --config "$CONFIG_PATH" | tee "$OUT_DIR/collector.txt"
fi

echo "Done. Check CSV/log paths from config and compare CH1/CH2 with VGC402 screen."
