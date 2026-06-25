#!/usr/bin/env bash
set -euo pipefail

OWNER="${OWNER:-alphatra}"
REPO="${REPO:-vacuum-instrument-monitor}"
RUNNER_USER="${RUNNER_USER:-github-runner}"
RUNNER_DIR="${RUNNER_DIR:-/opt/actions-runner}"
RUNNER_VERSION="${RUNNER_VERSION:-2.335.1}"
RUNNER_SHA256="${RUNNER_SHA256:-6d1e85bfd1a506a8b17c1f1b9b57dba458ffed90898799aaa9f599520b0d9207}"
RUNNER_TOKEN="${GITHUB_RUNNER_TOKEN:-${1:-}}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 2
fi

if [ -z "$RUNNER_TOKEN" ]; then
  echo "Usage: GITHUB_RUNNER_TOKEN=... $0" >&2
  exit 2
fi

if ! command -v sudo >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y sudo
fi

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$RUNNER_USER"
fi

install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_DIR"
cd "$RUNNER_DIR"

archive="actions-runner-linux-arm64-${RUNNER_VERSION}.tar.gz"
url="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${archive}"

if [ ! -x ./config.sh ]; then
  curl -fL -o "$archive" "$url"
  echo "${RUNNER_SHA256}  ${archive}" | sha256sum -c -
  tar xzf "$archive"
  rm -f "$archive"
  chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"
fi

cat >/etc/sudoers.d/vacuum-monitor-deploy <<EOF
${RUNNER_USER} ALL=(root) NOPASSWD: /usr/local/sbin/vacuum-monitor-deploy
EOF
chmod 440 /etc/sudoers.d/vacuum-monitor-deploy

if [ -f .runner ]; then
  sudo -u "$RUNNER_USER" ./config.sh remove --token "$RUNNER_TOKEN" || true
fi

sudo -u "$RUNNER_USER" ./config.sh \
  --url "https://github.com/${OWNER}/${REPO}" \
  --token "$RUNNER_TOKEN" \
  --name meterdevicepi \
  --labels meterdevicepi \
  --work _work \
  --unattended \
  --replace

./svc.sh install "$RUNNER_USER"
./svc.sh start
