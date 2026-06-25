#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-vacuum-monitor-collector.service}"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"

cd "$APP_DIR"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -x "$UV_BIN" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

"$UV_BIN" sync --no-dev

if systemctl list-unit-files "$SERVICE" >/dev/null 2>&1; then
  systemctl restart "$SERVICE"
else
  echo "Service $SERVICE not installed; deploy only."
fi
