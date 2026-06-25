#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BINARY_NAME="${BINARY_NAME:-vacuum-collector}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
MODE="${MODE:-onefile}"
DIST_DIR="${DIST_DIR:-$APP_DIR/dist}"
WORK_DIR="${WORK_DIR:-$APP_DIR/build/pyinstaller}"
SPEC_DIR="${SPEC_DIR:-$APP_DIR/build/spec}"
INSTALL_DIR="${INSTALL_DIR:-}"
UV_BIN="${UV_BIN:-}"

usage() {
  cat <<EOF
Usage: $0 [--onefile|--onedir] [--install /absolute/dir]

Build Linux binary with PyInstaller.

Environment:
  APP_DIR=$APP_DIR
  BINARY_NAME=$BINARY_NAME
  PYTHON_VERSION=$PYTHON_VERSION
  MODE=$MODE
  DIST_DIR=$DIST_DIR
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --onefile)
      MODE="onefile"
      shift
      ;;
    --onedir)
      MODE="onedir"
      shift
      ;;
    --install)
      INSTALL_DIR="${2:-}"
      if [ -z "$INSTALL_DIR" ]; then
        echo "--install needs absolute dir" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$(uname -s)" != "Linux" ]; then
  echo "Build must run on target Linux architecture." >&2
  echo "Raspberry Pi ARM64 binary: build on ARM64 Linux." >&2
  exit 2
fi

if [[ "$MODE" != "onefile" && "$MODE" != "onedir" ]]; then
  echo "MODE must be onefile or onedir" >&2
  exit 2
fi

if [ -n "$INSTALL_DIR" ] && [[ "$INSTALL_DIR" != /* ]]; then
  echo "--install path must be absolute: $INSTALL_DIR" >&2
  exit 2
fi

cd "$APP_DIR"
mkdir -p "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR"

PYINSTALLER_ARGS=(
  --clean
  --noconfirm
  "--$MODE"
  --name "$BINARY_NAME"
  --distpath "$DIST_DIR"
  --workpath "$WORK_DIR"
  --specpath "$SPEC_DIR"
  --paths "$APP_DIR"
  --collect-submodules serial
  --collect-submodules collectors
  --collect-submodules simulators
  collectors/gp350_collector.py
)

run_pyinstaller() {
  if [ -z "$UV_BIN" ]; then
    if command -v uv >/dev/null 2>&1; then
      UV_BIN="$(command -v uv)"
    elif [ -x /usr/local/bin/uv ]; then
      UV_BIN="/usr/local/bin/uv"
    elif [ -x "$HOME/.local/bin/uv" ]; then
      UV_BIN="$HOME/.local/bin/uv"
    fi
  fi

  if [ -n "$UV_BIN" ] && [ -x "$UV_BIN" ]; then
    "$UV_BIN" run --group build --python "$PYTHON_VERSION" \
      pyinstaller "${PYINSTALLER_ARGS[@]}"
    return
  fi

  python3 -m venv "$APP_DIR/.build-venv"
  "$APP_DIR/.build-venv/bin/python" -m pip install --upgrade pip
  "$APP_DIR/.build-venv/bin/python" -m pip install pyinstaller pyserial
  "$APP_DIR/.build-venv/bin/pyinstaller" "${PYINSTALLER_ARGS[@]}"
}

run_pyinstaller

if [ "$MODE" = "onefile" ]; then
  ARTIFACT="$DIST_DIR/$BINARY_NAME"
else
  ARTIFACT="$DIST_DIR/$BINARY_NAME/$BINARY_NAME"
fi

if [ ! -x "$ARTIFACT" ]; then
  echo "Build failed, artifact missing: $ARTIFACT" >&2
  exit 1
fi

"$ARTIFACT" --help >/dev/null

if [ -n "$INSTALL_DIR" ]; then
  mkdir -p "$INSTALL_DIR"
  if [ "$MODE" = "onefile" ]; then
    install -m 0755 "$ARTIFACT" "$INSTALL_DIR/$BINARY_NAME"
  else
    rm -rf "$INSTALL_DIR/$BINARY_NAME"
    cp -a "$DIST_DIR/$BINARY_NAME" "$INSTALL_DIR/"
  fi
fi

echo "Built: $ARTIFACT"
if [ -n "$INSTALL_DIR" ]; then
  echo "Installed to: $INSTALL_DIR"
fi
