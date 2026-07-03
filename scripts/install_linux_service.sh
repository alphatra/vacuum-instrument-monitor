#!/usr/bin/env bash
set -euo pipefail

INSTANCE="${1:-gp350-1}"
APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
SERVICE_USER="${SERVICE_USER:-vacuum-monitor}"
CONFIG_DIR="${CONFIG_DIR:-/etc/vacuum-monitor}"
UNIT_SRC="$APP_DIR/systemd/vacuum-monitor-collector@.service"
UNIT_DST="/etc/systemd/system/vacuum-monitor-collector@.service"
EXAMPLE_CONFIG="$APP_DIR/config/examples/${INSTANCE}.ini"
LOGROTATE_SRC="$APP_DIR/logrotate/vacuum-monitor"
LOGROTATE_DST="/etc/logrotate.d/vacuum-monitor"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0 ${INSTANCE}" >&2
  exit 2
fi

if [ ! -f "$UNIT_SRC" ]; then
  echo "Missing unit file: $UNIT_SRC" >&2
  echo "Set APP_DIR=/absolute/project/path if project is not in /opt." >&2
  exit 2
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if getent group dialout >/dev/null 2>&1; then
  usermod -aG dialout "$SERVICE_USER"
fi

install -d -m 0755 "$CONFIG_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$APP_DIR/data" "$APP_DIR/logs"
install -m 0644 "$UNIT_SRC" "$UNIT_DST"

if [ -f "$LOGROTATE_SRC" ]; then
  install -m 0644 "$LOGROTATE_SRC" "$LOGROTATE_DST"
fi

if [ ! -f "$CONFIG_DIR/collector.env" ]; then
  if [ -f "$APP_DIR/config/examples/collector.env.example" ]; then
    install -m 0600 "$APP_DIR/config/examples/collector.env.example" \
      "$CONFIG_DIR/collector.env"
  fi
fi

if [ ! -f "$CONFIG_DIR/${INSTANCE}.ini" ]; then
  if [ -f "$EXAMPLE_CONFIG" ]; then
    install -m 0644 "$EXAMPLE_CONFIG" "$CONFIG_DIR/${INSTANCE}.ini"
  else
    install -m 0644 "$APP_DIR/config/config.ini" "$CONFIG_DIR/${INSTANCE}.ini"
  fi
fi

systemctl daemon-reload
systemctl enable "vacuum-monitor-collector@${INSTANCE}.service"
systemctl restart "vacuum-monitor-collector@${INSTANCE}.service"

echo "Installed: vacuum-monitor-collector@${INSTANCE}.service"
echo "Config:    $CONFIG_DIR/${INSTANCE}.ini"
echo "Env:       $CONFIG_DIR/collector.env"
echo "Logs:      journalctl -u vacuum-monitor-collector@${INSTANCE}.service -f"
echo "Logrotate: $LOGROTATE_DST"
