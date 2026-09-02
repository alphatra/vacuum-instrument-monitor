#!/usr/bin/env bash
# Prepare the Python runtime so the systemd units can actually start.
#
# The units run as SERVICE_USER with ProtectHome=true. That hides /home from
# the service, which breaks two defaults that look fine when you test the
# collector manually as your login user:
#
#   - uv installed by its official installer lands in ~/.local/bin, and a
#     symlink in /usr/local/bin still points into /home.
#   - `uv venv` without an explicit interpreter may install a managed Python
#     under ~/.local/share/uv, so .venv/bin/python also points into /home.
#
# This script makes uv a real file outside /home, builds .venv with the system
# interpreter, hands both to SERVICE_USER, and records the matching
# PYTHON_VERSION. Safe to re-run.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vacuum-instrument-monitor}"
SERVICE_USER="${SERVICE_USER:-vacuum-monitor}"
CONFIG_DIR="${CONFIG_DIR:-/etc/vacuum-monitor}"
UV_BIN="${UV_BIN:-/usr/local/bin/uv}"
SYSTEM_PYTHON="${SYSTEM_PYTHON:-/usr/bin/python3}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2
  exit 2
fi

if [ ! -x "$SYSTEM_PYTHON" ]; then
  echo "System interpreter not found: $SYSTEM_PYTHON" >&2
  exit 2
fi

# uv must be a real file outside /home, reachable under ProtectHome=true.
if [ -L "$UV_BIN" ]; then
  uv_target="$(readlink -f "$UV_BIN")"
  if [ -x "$uv_target" ]; then
    echo "Replacing symlinked uv with a real copy (ProtectHome-safe)"
    cp "$uv_target" "$UV_BIN.tmp"
    mv "$UV_BIN.tmp" "$UV_BIN"
    chmod 0755 "$UV_BIN"
  fi
elif [ ! -x "$UV_BIN" ]; then
  for candidate in /usr/local/bin/uv /usr/bin/uv "$HOME/.local/bin/uv" /root/.local/bin/uv; do
    if [ -x "$candidate" ] && [ "$candidate" != "$UV_BIN" ]; then
      cp "$candidate" "$UV_BIN"
      chmod 0755 "$UV_BIN"
      break
    fi
  done
fi

if [ ! -x "$UV_BIN" ]; then
  echo "uv not found. Install it first:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh" >&2
  exit 2
fi

# Build .venv with the system interpreter so nothing points into /home.
echo "Building .venv with $SYSTEM_PYTHON"
"$UV_BIN" venv --python "$SYSTEM_PYTHON" "$APP_DIR/.venv" >/dev/null
(cd "$APP_DIR" && "$UV_BIN" sync --no-dev --python "$SYSTEM_PYTHON" >/dev/null)

venv_python="$(readlink -f "$APP_DIR/.venv/bin/python")"
case "$venv_python" in
  /home/*)
    echo "Refusing to finish: .venv/bin/python resolves into /home ($venv_python)." >&2
    echo "The service cannot read it under ProtectHome=true." >&2
    exit 1
    ;;
esac

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.venv"

# Record the interpreter version the unit should ask for.
python_version="$("$SYSTEM_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
install -d -m 0755 "$CONFIG_DIR"
touch "$CONFIG_DIR/collector.env"
chmod 0600 "$CONFIG_DIR/collector.env"

if grep -q '^PYTHON_VERSION=' "$CONFIG_DIR/collector.env"; then
  sed -i "s|^PYTHON_VERSION=.*|PYTHON_VERSION=${python_version}|" "$CONFIG_DIR/collector.env"
else
  echo "PYTHON_VERSION=${python_version}" >> "$CONFIG_DIR/collector.env"
fi

if grep -q '^UV_BIN=' "$CONFIG_DIR/collector.env"; then
  sed -i "s|^UV_BIN=.*|UV_BIN=${UV_BIN}|" "$CONFIG_DIR/collector.env"
else
  echo "UV_BIN=${UV_BIN}" >> "$CONFIG_DIR/collector.env"
fi

echo "Runtime ready:"
echo "  uv:             $UV_BIN"
echo "  venv python:    $venv_python"
echo "  venv owner:     $SERVICE_USER"
echo "  PYTHON_VERSION: $python_version"
