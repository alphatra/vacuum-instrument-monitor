#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-vacuum-monitor-collector.service}"
SERVICE_PATTERN="${SERVICE_PATTERN:-vacuum-monitor-collector@*.service}"
UV_BIN="${UV_BIN:-/usr/local/bin/uv}"

cd "$APP_DIR"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -x "$UV_BIN" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

"$UV_BIN" sync --no-dev

mapfile -t units < <(
  systemctl list-units --full --all --plain "$SERVICE_PATTERN" \
    | awk '{print $1}' \
    | grep '^vacuum-monitor-collector@' || true
)

if [ "${#units[@]}" -gt 0 ]; then
  systemctl restart "${units[@]}"
elif systemctl list-unit-files "$SERVICE" >/dev/null 2>&1; then
  systemctl restart "$SERVICE"
else
  echo "No collector systemd service installed; deploy only."
fi
