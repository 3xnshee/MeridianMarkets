#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
SHORTCUT_DST="$DESKTOP_DIR/MeridianMarkets.desktop"
PROJECT_DIR="$(pwd)"
WRAPPER_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
WRAPPER_PATH="$WRAPPER_DIR/meridian-markets-launcher"
BIN_PATH="$PROJECT_DIR/dist/MeridianMarkets"
if [[ ! -f "$BIN_PATH" ]]; then
  BIN_PATH="$PROJECT_DIR/release/MeridianMarkets-0.1.0-linux/MeridianMarkets"
fi
BUILD_INFO_PATH="$PROJECT_DIR/dist/build-info.json"
if [[ ! -f "$BUILD_INFO_PATH" ]]; then
  BUILD_INFO_PATH="$PROJECT_DIR/release/MeridianMarkets-0.1.0-linux/build-info.json"
fi

mkdir -p "$DESKTOP_DIR" "$WRAPPER_DIR"
if [[ -f "$BIN_PATH" ]]; then
  python3 - "$WRAPPER_PATH" "$BIN_PATH" "$BUILD_INFO_PATH" "$SHORTCUT_DST" "$PROJECT_DIR" <<'WRAPPERPY'
from pathlib import Path
import shlex
import sys
import textwrap

wrapper_path = Path(sys.argv[1])
bin_path = sys.argv[2]
build_info_path = sys.argv[3]
shortcut_dst = Path(sys.argv[4])
project_dir = Path(sys.argv[5])

wrapper = textwrap.dedent("""\
#!/usr/bin/env bash
set -euo pipefail
BIN_PATH=__BIN_PATH__
BUILD_INFO_PATH=__BUILD_INFO_PATH__
URL="http://127.0.0.1:8787"
EXPECTED_BUILD_ID="$(python3 - \"$BUILD_INFO_PATH\" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8'))
except Exception:
    data = {}
print(str(data.get('build_id', 'dev')))
PY
)"

is_server_healthy() {
  python3 - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=1)
PY
}

running_build_id() {
  python3 - <<'PY'
import json
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8787/api/meta', timeout=1) as response:
        payload = json.load(response)
except Exception:
    print('')
    raise SystemExit(0)
print(str(payload.get('build_id', '')))
PY
}

stop_running_server() {
  pkill -f 'MeridianMarkets.*--server-only' >/dev/null 2>&1 || true
}

wait_for_server() {
  for _ in $(seq 1 50); do
    if is_server_healthy; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

start_server() {
  "$BIN_PATH" --server-only >/tmp/meridian-markets.log 2>&1 &
}

if is_server_healthy; then
  CURRENT_BUILD_ID="$(running_build_id || true)"
  if [[ -n "${EXPECTED_BUILD_ID:-}" && "${CURRENT_BUILD_ID:-}" != "${EXPECTED_BUILD_ID}" ]]; then
    stop_running_server
    sleep 0.4
  fi
fi

if ! is_server_healthy; then
  start_server
  wait_for_server >/dev/null 2>&1 || true
fi

( xdg-open "$URL" >/dev/null 2>&1 || python3 -c 'import sys,webbrowser; webbrowser.open(sys.argv[1])' "$URL" >/dev/null 2>&1 ) &
""")
wrapper = wrapper.replace("__BIN_PATH__", shlex.quote(bin_path))
wrapper = wrapper.replace("__BUILD_INFO_PATH__", shlex.quote(build_info_path))
wrapper_path.write_text(wrapper, encoding='utf-8')
wrapper_path.chmod(0o755)
shortcut_dst.write_text(textwrap.dedent(f"""\
[Desktop Entry]
Version=1.0
Type=Application
Name=Meridian Markets
Comment=Launch the packaged Meridian Markets app
Exec={wrapper_path}
Icon={project_dir / 'app.ico'}
Terminal=false
Categories=Finance;Office;Utility;
StartupNotify=true
"""), encoding='utf-8')
shortcut_dst.chmod(0o755)
WRAPPERPY
else
  cp -f "$PROJECT_DIR/MeridianMarkets.desktop" "$SHORTCUT_DST"
fi
chmod +x "$SHORTCUT_DST"
if command -v gio >/dev/null 2>&1; then
  gio set -t string "$SHORTCUT_DST" metadata::trusted true >/dev/null 2>&1 || true
fi

echo "Shortcut created: $SHORTCUT_DST"
echo "Launcher created: $WRAPPER_PATH"
