# Meridian Markets

A local market dashboard with a Python backend and a single shared HTML frontend. The desktop app uses the same UI as the localhost version, so the packaged build looks and behaves the same on Linux and Windows.

## Features
- Local API for Yahoo Finance quotes, history, search, state, and app metadata
- Native desktop launch with the same `index.html` UI
- PyInstaller packaging for Linux and Windows
- Persistent dashboard state through the backend

## Run
### Desktop app
Linux or Windows:

```bash
python server.py
```

### Browser mode
Use this when you want the app to open in your default browser:

```bash
python server.py --browser
```

## Build with PyInstaller
### Linux
```bash
./build-linux.sh
```

Output: `dist/MeridianMarkets`

### Windows
```bat
build-windows.bat
```

Output: `dist\\MeridianMarkets.exe`

## Release packages
### Linux
```bash
./package-release.sh
```

### Windows
```bat
package-release.bat
```

These scripts create portable release folders and zip files under `release/`.

## How to download
1. Open the GitHub repository page.
2. Click **Releases** on the right side or in the repository navigation.
3. Open the latest `v0.1.0` release.
4. Download the published asset for your platform. For this release, the packaged download is `MeridianMarkets-0.1.0-linux.zip`.
5. Extract the archive and run the packaged app from the extracted folder.

If you are on Windows, use `build-windows.bat` to build the EXE locally until a Windows release asset is published.

## Development workflow
Use a simple branch layout:
- `dev` for active development and integration
- `feature/*` for new features
- `fix/*` for bug fixes
- `docs/*` for documentation updates

Commit messages should stay short and clear, using Conventional Commits when practical, for example:
- `feat: add watchlist search`
- `fix: prevent duplicate saves`
- `docs: update release instructions`

## Open-source / private integration boundary
The public repo stays fully usable without any private trading or wallet service.
- The UI can expose Trading and Wallet tabs without requiring credentials.
- A private provider can be added later through `window.MERIDIAN_PRIVATE_PROVIDER` or a private backend with the same contract.
- The public build falls back to a no-op provider in `private/provider.js`.
- All sensitive auth, wallet, and order-routing logic should live outside the public repo.

See `integrations/README.md` for the provider contract and recommended endpoint shape.

## Backend API
- `GET /api/health` — health check
- `GET /api/meta` — app metadata and defaults
- `GET /api/search?q=...` — symbol search
- `GET /api/quotes?symbols=SPGI,SPFF&range=1d` — quotes and history
- `GET /api/state` and `POST /api/state` — saved dashboard state

## Project files
- `server.py` — backend and desktop launcher
- `index.html` — dashboard UI
- `build-linux.sh` / `build-windows.bat` — build scripts
- `package-release.sh` / `package-release.bat` — release packaging
- `build-branch-dist.sh` — creates `dist/main/` and `dist/dev/` app variants for QC/testing
- `MeridianMarkets.spec` — PyInstaller spec
- `private/provider.js` — public no-op trading/wallet provider hook

## Requirements
- Python 3.11+
- PyInstaller
- pywebview
- yfinance
- A compatible desktop environment for native window mode

## Notes
- The Linux and Windows builds both ship the same dashboard UI.
- The backend stores dashboard state locally so views and saved data persist across restarts.
- `dist/main/` and `dist/dev/` can be generated with `build-branch-dist.sh` when you need side-by-side QC builds.
- If port `8787` is already in use, stop the existing instance before starting another.
