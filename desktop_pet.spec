# -*- mode: python ; coding: utf-8 -*-
import sys

# pynput 在运行期按平台动态导入后端，PyInstaller 静态分析看不到，必须显式声明，
# 否则打包后键盘联动会静默失效（PYNPUT_AVAILABLE 变 False）。
if sys.platform == 'win32':
    _pynput_backends = ['pynput.keyboard._win32', 'pynput.mouse._win32']
else:
    _pynput_backends = ['pynput.keyboard._darwin', 'pynput.mouse._darwin']

a = Analysis(
    ['desktop_pet.py'],
    pathex=[],
    binaries=[],
    datas=[('images', 'images')],
    hiddenimports=_pynput_backends,
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
    a.binaries,
    a.datas,
    [],
    name='iKun',              # 产物名与 README / dist 目录保持一致
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
