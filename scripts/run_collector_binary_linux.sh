#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
BINARY_PATH="${BINARY_PATH:-$APP_DIR/bin/vacuum-collector}"

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

if [ ! -x "$BINARY_PATH" ]; then
  echo "Binary not executable: $BINARY_PATH" >&2
  echo "Build/install first: scripts/build_linux_binary.sh --install $APP_DIR/bin" >&2
  exit 127
fi

cd "$APP_DIR"
mkdir -p data logs
exec "$BINARY_PATH" --config "$CONFIG_PATH" "$@"
