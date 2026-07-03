#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
BINARY_PATH="${BINARY_PATH:-$APP_DIR/bin/vacuum-collector}"
CONFIG_PATH="${1:-}"

if [ "$(uname -s)" != "Linux" ]; then
  echo "This check is meant for target Linux, ideally Raspberry Pi ARM64." >&2
  exit 2
fi

if [ ! -x "$BINARY_PATH" ]; then
  echo "Binary missing or not executable: $BINARY_PATH" >&2
  exit 2
fi

echo "Kernel:       $(uname -a)"
echo "Architecture: $(uname -m)"
if command -v file >/dev/null 2>&1; then
  file "$BINARY_PATH"
fi

"$BINARY_PATH" --help >/dev/null
echo "Binary help:  OK"

if [ -n "$CONFIG_PATH" ]; then
  if [[ "$CONFIG_PATH" != /* ]]; then
    echo "Config path must be absolute: $CONFIG_PATH" >&2
    exit 2
  fi
  "$BINARY_PATH" --config "$CONFIG_PATH" --discover
fi
