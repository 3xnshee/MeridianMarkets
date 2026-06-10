#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION="0.1.0"
RELEASE_NAME="MeridianMarkets-${VERSION}-linux"
RELEASE_ROOT="release"
RELEASE_DIR="${RELEASE_ROOT}/${RELEASE_NAME}"
ZIP_FILE="${RELEASE_ROOT}/${RELEASE_NAME}.zip"

rm -rf "$RELEASE_DIR" "$ZIP_FILE"
mkdir -p "$RELEASE_DIR" "$RELEASE_ROOT"

python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --upgrade pyinstaller pywebview PyQt6 PyQt6-WebEngine qtpy yfinance
python3 make-icon.py
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import os

root = Path.cwd()
build_info = {
    "version": "0.1.0",
    "branch": os.environ.get("BUILD_BRANCH", "dev"),
    "build_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"),
    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
}
(root / "build-info.json").write_text(json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(root / "dist").mkdir(exist_ok=True)
(root / "dist" / "build-info.json").write_text(json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
python3 -m PyInstaller --noconfirm --clean MeridianMarkets.spec

if [[ -f dist/MeridianMarkets ]]; then
  cp -f dist/MeridianMarkets "$RELEASE_DIR/MeridianMarkets"
elif [[ -f dist/MeridianMarkets.exe ]]; then
  cp -f dist/MeridianMarkets.exe "$RELEASE_DIR/MeridianMarkets.exe"
else
  echo "Could not find a packaged executable in dist/." >&2
  exit 1
fi

cp -f README.md "$RELEASE_DIR/README.md"
cp -f run-dashboard.sh "$RELEASE_DIR/run-dashboard.sh"
cp -f app.ico "$RELEASE_DIR/app.ico"
if [[ -f dist/build-info.json ]]; then
  cp -f dist/build-info.json "$RELEASE_DIR/build-info.json"
fi
cat > "$RELEASE_DIR/MeridianMarkets.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Meridian Markets
Comment=Launch the packaged Meridian Markets app
Exec=/usr/bin/env bash -lc '"$RELEASE_DIR/MeridianMarkets"'
Icon=$RELEASE_DIR/app.ico
Terminal=false
Categories=Finance;Office;Utility;
StartupNotify=true
EOF
chmod +x "$RELEASE_DIR/MeridianMarkets" 2>/dev/null || true
chmod +x "$RELEASE_DIR/run-dashboard.sh" 2>/dev/null || true
chmod +x "$RELEASE_DIR/MeridianMarkets.desktop" 2>/dev/null || true

python3 - <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

release_dir = Path("release/MeridianMarkets-0.1.0-linux")
zip_file = Path("release/MeridianMarkets-0.1.0-linux.zip")
with ZipFile(zip_file, "w", compression=ZIP_DEFLATED) as zf:
    for path in release_dir.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(release_dir.parent))
PY

echo
echo "Release package created: ${ZIP_FILE}"
echo "Folder: ${RELEASE_DIR}"
