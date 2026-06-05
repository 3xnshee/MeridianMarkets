#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --upgrade pyinstaller pywebview PyQt6 PyQt6-WebEngine qtpy yfinance
python3 make-icon.py
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json

root = Path.cwd()
build_info = {
    "version": "0.1.0",
    "build_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"),
    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
}
(root / "build-info.json").write_text(json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(root / "dist").mkdir(exist_ok=True)
(root / "dist" / "build-info.json").write_text(json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
python3 -m PyInstaller --noconfirm --clean MeridianMarkets.spec

echo
if [[ -f dist/MeridianMarkets ]]; then
  chmod +x dist/MeridianMarkets

  cat > dist/MeridianMarkets.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Meridian Markets
Comment=Launch the packaged Meridian Markets app
Exec=$PWD/dist/MeridianMarkets
Icon=$PWD/app.ico
Terminal=false
Categories=Finance;Office;Utility;
StartupNotify=true
EOF
  chmod +x dist/MeridianMarkets.desktop
  echo "Build complete. Double-click dist/MeridianMarkets (the executable binary)."
elif [[ -f dist/MeridianMarkets.exe ]]; then
  echo "Build complete. Check the dist/MeridianMarkets.exe file."
else
  echo "Build complete. Check the dist/ folder."
fi
