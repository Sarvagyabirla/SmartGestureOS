# -*- mode: python ; coding: utf-8 -*-
# SmartGestureOS — PyInstaller ONEDIR spec
# Build: python -m PyInstaller --noconfirm --clean packaging\windows\SmartGesture.spec

import runpy
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent.parent

# ---------------------------------------------------------------------------
# Collect CustomTkinter runtime data (themes, fonts, assets)
# ---------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

ctk_datas = collect_data_files('customtkinter')
# MediaPipe 0.10.35 locates its C API through importlib.resources and ctypes.
# Static import analysis alone cannot discover the package or its native DLL.
mediapipe_datas = collect_data_files('mediapipe')
mediapipe_binaries = collect_dynamic_libs('mediapipe')
notice_datas = runpy.run_path(str(ROOT / 'scripts' / 'build_notices.py'))['collect_runtime_notices'](ROOT)
version = runpy.run_path(str(ROOT / 'src' / 'version.py'))['__version__']
version_tuple = tuple(int(part) for part in version.split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                      mask=0x3f, flags=0, OS=0x40004, fileType=0x1,
                      subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'SmartGestureOS Project'),
            StringStruct('FileDescription', 'Gesture Control for Windows'),
            StringStruct('FileVersion', version),
            StringStruct('InternalName', 'SmartGestureOS'),
            StringStruct('OriginalFilename', 'SmartGestureOS.exe'),
            StringStruct('ProductName', 'SmartGestureOS'),
            StringStruct('ProductVersion', version),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=mediapipe_binaries,
    datas=[
        # Core runtime resources
        (str(ROOT / 'models'), 'models'),
        (str(ROOT / 'config'), 'config'),
        # CustomTkinter assets
        *ctk_datas,
        *mediapipe_datas,
        *notice_datas,
        (str(ROOT / 'LICENSE'), '.'),
        (str(ROOT / 'THIRD_PARTY_NOTICES.md'), '.'),
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
        'mediapipe.tasks.c',
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
    icon=str(ROOT / 'packaging' / 'windows' / 'SmartGestureOS.ico'),
    version=version_info,
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
