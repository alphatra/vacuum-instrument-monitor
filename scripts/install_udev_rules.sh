#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
RULES_SRC="${1:-$APP_DIR/udev/99-vacuum-monitor.rules}"
RULES_DST="/etc/udev/rules.d/99-vacuum-monitor.rules"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0 /path/to/99-vacuum-monitor.rules" >&2
  exit 2
fi

if [ ! -f "$RULES_SRC" ]; then
  echo "Rules file not found: $RULES_SRC" >&2
  echo "Copy udev/99-vacuum-monitor.rules.example and replace placeholders first." >&2
  exit 2
fi

if grep -Eq "REPLACE_|XXXX|YYYY" "$RULES_SRC"; then
  echo "Rules still contain placeholders. Edit serial/vendor/product first." >&2
  exit 2
fi

install -m 0644 "$RULES_SRC" "$RULES_DST"
udevadm control --reload-rules
udevadm trigger

echo "Installed: $RULES_DST"
echo "Unplug/replug USB adapters, then check: ls -l /dev/vacuum-*"
