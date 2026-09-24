# -*- mode: python ; coding: utf-8 -*-
# SmartGestureOS — PyInstaller ONEDIR spec
# Build: python -m PyInstaller --noconfirm --clean packaging\windows\SmartGesture.spec

import os
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent.parent

# ---------------------------------------------------------------------------
# Collect CustomTkinter runtime data (themes, fonts, assets)
# ---------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_data_files

ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Core runtime resources
        (str(ROOT / 'models'), 'models'),
        (str(ROOT / 'config'), 'config'),
        # CustomTkinter assets
        *ctk_datas,
    ],
    hiddenimports=[
        # Standard library modules loaded at runtime
        'queue',
        'threading',
        'tkinter',
        'tkinter.ttk',
        # Third-party
        'psutil',
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageGrab',
        'PIL.ImageTk',
        'customtkinter',
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.vision',
        'pycaw',
        'pycaw.pycaw',
        'comtypes',
        'comtypes.client',
        'comtypes.server',
        'comtypes.automation',
        'comtypes.gen',
        'screeninfo',
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        'screen_brightness_control',
        'platformdirs',
        'keyboard',
        'pywinstyles',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Development-only packages
        'pytest',
        'matplotlib',
        'IPython',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SmartGestureOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # Keep UPX off for reliability with MediaPipe/OpenCV
    console=False,       # Windowed mode for production
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # Add .ico path here when available
    version=None,        # Add version_info.txt here when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SmartGestureOS',
)
