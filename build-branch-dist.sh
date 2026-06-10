#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MAIN_BRANCH="${MAIN_BRANCH:-main}"
DEV_BRANCH="${DEV_BRANCH:-dev}"
VERSION="0.1.0"

BUILD_BRANCH="$MAIN_BRANCH" ./build-linux.sh

if [[ ! -f dist/MeridianMarkets && ! -f dist/MeridianMarkets.exe ]]; then
  echo "Could not find a packaged executable in dist/." >&2
  exit 1
fi

if [[ -f dist/build-info.json ]]; then
  BUILD_ID="$(python3 - <<'PY'
from pathlib import Path
import json
path = Path('dist/build-info.json')
raw = json.loads(path.read_text(encoding='utf-8'))
print(raw.get('build_id', 'dev'))
PY
)"
  BUILT_AT="$(python3 - <<'PY'
from pathlib import Path
import json
path = Path('dist/build-info.json')
raw = json.loads(path.read_text(encoding='utf-8'))
print(raw.get('built_at', ''))
PY
)"
else
  BUILD_ID="dev"
  BUILT_AT=""
fi

copy_variant() {
  local branch="$1"
  local target_dir="dist/$branch"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"

  if [[ -f dist/MeridianMarkets ]]; then
    cp -f dist/MeridianMarkets "$target_dir/MeridianMarkets"
    chmod +x "$target_dir/MeridianMarkets" 2>/dev/null || true
  fi
  if [[ -f dist/MeridianMarkets.exe ]]; then
    cp -f dist/MeridianMarkets.exe "$target_dir/MeridianMarkets.exe"
  fi

  cp -f README.md "$target_dir/README.md"
  cp -f run-dashboard.sh "$target_dir/run-dashboard.sh"
  cp -f app.ico "$target_dir/app.ico"
  chmod +x "$target_dir/run-dashboard.sh" 2>/dev/null || true

  python3 - "$target_dir" "$branch" "$VERSION" "$BUILD_ID" "$BUILT_AT" <<'PY'
from pathlib import Path
import json
import sys

target_dir = Path(sys.argv[1])
branch = sys.argv[2]
version = sys.argv[3]
build_id = sys.argv[4]
built_at = sys.argv[5]

build_info = {
    "version": version,
    "branch": branch,
    "build_id": build_id,
    "built_at": built_at,
}
(target_dir / "build-info.json").write_text(json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  cat > "$target_dir/MeridianMarkets.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Meridian Markets (${branch})
Comment=Launch the packaged Meridian Markets app (${branch} build)
Exec=/usr/bin/env bash -lc '"$PWD/$target_dir/MeridianMarkets"'
Icon=$PWD/$target_dir/app.ico
Terminal=false
Categories=Finance;Office;Utility;
StartupNotify=true
EOF
  chmod +x "$target_dir/MeridianMarkets.desktop" 2>/dev/null || true
}

copy_variant "$MAIN_BRANCH"
copy_variant "$DEV_BRANCH"

echo
if [[ -f dist/main/MeridianMarkets ]]; then
  echo "Main build: dist/main/MeridianMarkets"
elif [[ -f dist/main/MeridianMarkets.exe ]]; then
  echo "Main build: dist/main/MeridianMarkets.exe"
fi
if [[ -f dist/dev/MeridianMarkets ]]; then
  echo "Dev build: dist/dev/MeridianMarkets"
elif [[ -f dist/dev/MeridianMarkets.exe ]]; then
  echo "Dev build: dist/dev/MeridianMarkets.exe"
fi
