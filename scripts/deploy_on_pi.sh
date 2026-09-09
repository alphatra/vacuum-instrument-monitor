#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
SERVICE="${SERVICE:-vacuum-monitor-collector.service}"
SERVICE_PATTERN="${SERVICE_PATTERN:-vacuum-monitor-collector@*.service}"
ADS1115_SERVICE_PATTERN="${ADS1115_SERVICE_PATTERN:-vacuum-monitor-ads1115@*.service}"
UV_BIN="${UV_BIN:-/usr/local/bin/uv}"

# Deploy the exact commit the caller (CI-gated workflow) verified, never the
# branch tip: main may have moved past the tested commit by the time we run.
TARGET_SHA="${TARGET_SHA:-${1:-}}"
if [ -z "$TARGET_SHA" ]; then
  echo "TARGET_SHA (commit to deploy) is required, via env or first argument." >&2
  exit 1
fi

cd "$APP_DIR"

git fetch origin
if ! git cat-file -e "$TARGET_SHA^{commit}" 2>/dev/null; then
  echo "Commit $TARGET_SHA not found in $APP_DIR after fetch." >&2
  exit 1
fi
git reset --hard "$TARGET_SHA"

if [ ! -x "$UV_BIN" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
fi

# Rebuilds .venv with the system interpreter and restores SERVICE_USER
# ownership. A plain `uv sync` here would leave .venv owned by root and the
# service would fail on start.
APP_DIR="$APP_DIR" UV_BIN="$UV_BIN" "$APP_DIR/scripts/prepare_runtime.sh"

mapfile -t units < <(
  systemctl list-units --full --all --plain "$SERVICE_PATTERN" "$ADS1115_SERVICE_PATTERN" \
    | awk '{print $1}' \
    | grep -E '^vacuum-monitor-(collector|ads1115)@' || true
)

if [ "${#units[@]}" -gt 0 ]; then
  systemctl restart "${units[@]}"
elif systemctl list-unit-files "$SERVICE" >/dev/null 2>&1; then
  systemctl restart "$SERVICE"
else
  echo "No collector systemd service installed; deploy only."
fi
