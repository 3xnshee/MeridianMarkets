# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

block_cipher = None
project_dir = Path(sys.argv[0]).resolve().parent

datas, binaries, hiddenimports = collect_all('webview')
datas += [(str(project_dir / 'index.html'), '.')]
private_provider = project_dir / 'private' / 'provider.js'
if private_provider.exists():
    datas += [(str(private_provider), 'private')]
build_info = project_dir / 'build-info.json'
if build_info.exists():
    datas += [(str(build_info), '.')]

exe_kwargs = {
    'name': 'MeridianMarkets',
    'debug': False,
    'bootloader_ignore_signals': False,
    'strip': False,
    'upx': True,
    'console': False,
}

if sys.platform.startswith('win'):
    exe_kwargs['icon'] = str(project_dir / 'app.ico')
    version_file = project_dir / 'version-info.txt'
    if version_file.exists():
        exe_kwargs['version'] = str(version_file)

a = Analysis(
    ['server.py'],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    **exe_kwargs,
)
