#!/usr/bin/env bash
set -euo pipefail

INSTANCE="${1:-gp350-analog-ads1115}"
APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
SERVICE_USER="${SERVICE_USER:-vacuum-monitor}"
CONFIG_DIR="${CONFIG_DIR:-/etc/vacuum-monitor}"
UNIT_SRC="$APP_DIR/systemd/vacuum-monitor-ads1115@.service"
UNIT_DST="/etc/systemd/system/vacuum-monitor-ads1115@.service"
EXAMPLE_CONFIG="$APP_DIR/config/examples/${INSTANCE}.ini"
LOGROTATE_SRC="$APP_DIR/logrotate/vacuum-monitor"
LOGROTATE_DST="/etc/logrotate.d/vacuum-monitor"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0 ${INSTANCE}" >&2
  exit 2
fi

if [ ! -f "$UNIT_SRC" ] || [ ! -f "$EXAMPLE_CONFIG" ]; then
  echo "Missing ADS1115 service or config template in $APP_DIR" >&2
  exit 2
fi

if ! getent group i2c >/dev/null 2>&1; then
  echo "Missing i2c group. Enable I2C and install i2c-tools first." >&2
  exit 2
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

usermod -aG i2c "$SERVICE_USER"
install -d -m 0755 "$CONFIG_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$APP_DIR/data" "$APP_DIR/logs"
install -m 0644 "$UNIT_SRC" "$UNIT_DST"

if [ -f "$LOGROTATE_SRC" ]; then
  install -m 0644 "$LOGROTATE_SRC" "$LOGROTATE_DST"
fi

if [ ! -f "$CONFIG_DIR/collector.env" ] && [ -f "$APP_DIR/config/examples/collector.env.example" ]; then
  install -m 0600 "$APP_DIR/config/examples/collector.env.example" "$CONFIG_DIR/collector.env"
fi

if [ ! -f "$CONFIG_DIR/${INSTANCE}.ini" ]; then
  install -m 0644 "$EXAMPLE_CONFIG" "$CONFIG_DIR/${INSTANCE}.ini"
fi

systemctl daemon-reload
systemctl enable "vacuum-monitor-ads1115@${INSTANCE}.service"
systemctl restart "vacuum-monitor-ads1115@${INSTANCE}.service"

echo "Installed: vacuum-monitor-ads1115@${INSTANCE}.service"
echo "Config:    $CONFIG_DIR/${INSTANCE}.ini"
echo "Logs:      journalctl -u vacuum-monitor-ads1115@${INSTANCE}.service -f"
