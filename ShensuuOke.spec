# -*- mode: python ; coding: utf-8 -*-
import os, sys
try:
    _root_dir = os.path.dirname(os.path.abspath(SPEC)) if 'SPEC' in globals() else os.getcwd()
    _bump_script = os.path.join(_root_dir, 'packaging', 'bump_version.py')
    if os.path.exists(_bump_script):
        import importlib.util
        _spec = importlib.util.spec_from_file_location("bump_version", _bump_script)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _ver = _mod.bump_version()
        print(f"=== ShensuuOke Build Version: v{_ver} ===")
except Exception as _e:
    print(f"=== ShensuuOke Spec Warning: Could not bump version: {_e} ===")

from PyInstaller.utils.hooks import collect_all

datas = [('app/resources', 'app/resources'), ('runtime/soundfonts/*.sf2', 'runtime/soundfonts')]
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
