# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os

ROOT = Path(SPECPATH)
a = Analysis(
    [str(ROOT / "main.py")], pathex=[str(ROOT)],
    binaries=[], datas=[], hiddenimports=[],
    excludes=["tkinter", "customtkinter", "pystray", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtPdf", "PySide6.QtMultimedia", "PIL", "numpy"],
    noarchive=False, optimize=1,
)
# Qt's Windows build imports the OS ICU ABI (unsuffixed ucnv_* exports).
# A Poppler ICU on the build machine's PATH has the same filename but a
# different ABI. Bundling it breaks QtCore with ERROR_PROC_NOT_FOUND (127).
# Modern Windows provides the matching system icuuc.dll; do not shadow it.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith(("icuuc", "icuin", "icudt"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="VEIL",
    console=False, debug=False, strip=False, upx=False,
    uac_admin=os.environ.get("VEIL_BUILD_NO_UAC") != "1",
    icon=str(ROOT / "app/image/veil.ico"),
    disable_windowed_traceback=False,
)
# Folder distribution avoids one-file extraction at every startup.
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VEIL")
