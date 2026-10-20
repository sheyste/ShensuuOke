# -*- mode: python ; coding: utf-8 -*-
import os, sys
try:
    _root_dir = os.path.dirname(os.path.abspath(SPEC)) if 'SPEC' in globals() else os.getcwd()
    _ver_json = os.path.join(_root_dir, 'packaging', 'version.json')
    if os.path.exists(_ver_json):
        import json
        with open(_ver_json, 'r', encoding='utf-8') as _f:
            _ver = json.load(_f).get('version', '1.0.0')
        print(f"=== ShensuuOke Spec Packaging Version: v{_ver} ===")
except Exception as _e:
    print(f"=== ShensuuOke Spec Warning: Could not read version: {_e} ===")

from PyInstaller.utils.hooks import collect_all

datas = [('app/resources', 'app/resources'), ('runtime/soundfonts/*.sf2', 'runtime/soundfonts')]
if os.path.exists('.env'):
    datas.append(('.env', '.'))
binaries = [('runtime/ffmpeg/ffmpeg.exe', 'runtime/ffmpeg'), ('runtime/fluidsynth/*.dll', 'runtime/fluidsynth')]
hiddenimports = []
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('qrcode')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyfluidsynth')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShensuuOke',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='packaging/file_version_info.txt',
    icon=['app/resources/icons/logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShensuuOke',
)
