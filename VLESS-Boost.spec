# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: VLESS-Boost.exe с UAC admin и логотипом."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "app" / "image"), "app/image"),
]
binaries = []
hiddenimports = []

for pkg in ("customtkinter", "pystray"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "PIL._tkinter_finder",
        "app",
        "app.ui",
        "app.ui.app",
        "app.ui.theme",
        "app.ui.helpers",
        "app.ui.widgets",
        "app.ui.widgets.power_button",
        "app.ui.widgets.service_card",
        "app.ui.widgets.sidebar",
        "app.ui.widgets.status_bar",
        "app.presets",
        "app.settings",
        "app.singbox",
        "app.config_builder",
        "app.vless_parser",
        "app.list_updater",
        "app.paths",
        "app.icons",
        "app.updater",
        "app.netcheck",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Важно: без UPX — иначе Windows часто показывает старую/битую иконку в панели задач
ico_candidates = [
    ROOT / "app" / "image" / "logo" / "app.ico",
    ROOT / "app" / "image" / "app.ico",
]
ico = next((p for p in ico_candidates if p.exists()), None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VLESS-Boost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    uac_uid=False,
    icon=str(ico) if ico else None,
)
