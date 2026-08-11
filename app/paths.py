from __future__ import annotations

import sys
from pathlib import Path


def _app_root() -> Path:
    # PyInstaller onefile: данные/конфиг рядом с .exe, не в _MEIPASS
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _app_root()
APP_DIR = Path(__file__).resolve().parent
BIN_DIR = ROOT / "bin"
CONFIG_DIR = ROOT / "config"
PRESETS_DIR = ROOT / "presets"
CACHE_DIR = CONFIG_DIR / "cache"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
SINGBOX_CONFIG_PATH = CONFIG_DIR / "sing-box.json"
LOG_PATH = CONFIG_DIR / "app.log"
SINGBOX_EXE = BIN_DIR / "sing-box.exe"
