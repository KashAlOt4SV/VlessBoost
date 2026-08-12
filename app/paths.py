from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _app_root() -> Path:
    # PyInstaller onefile: exe folder (bin next to exe); config lives in AppData.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _portable_config_dir() -> Path:
    return _app_root() / "config"


def _roaming_config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "VLESS-Boost"


def _migrate_config_if_needed(dest: Path) -> None:
    """Copy settings from next-to-exe config into AppData once (OTA-safe)."""
    dest.mkdir(parents=True, exist_ok=True)
    settings_dest = dest / "settings.json"
    if settings_dest.exists():
        return
    portable = _portable_config_dir()
    settings_src = portable / "settings.json"
    if settings_src.exists():
        try:
            shutil.copy2(settings_src, settings_dest)
        except OSError:
            pass
    cache_src = portable / "cache"
    cache_dest = dest / "cache"
    if cache_src.is_dir() and not cache_dest.exists():
        try:
            shutil.copytree(cache_src, cache_dest)
        except OSError:
            pass


ROOT = _app_root()
APP_DIR = Path(__file__).resolve().parent
BIN_DIR = ROOT / "bin"
# Persistent across OTA (exe may run from a new folder / temp after bad updates)
CONFIG_DIR = _roaming_config_dir()
_migrate_config_if_needed(CONFIG_DIR)
PRESETS_DIR = ROOT / "presets"
CACHE_DIR = CONFIG_DIR / "cache"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
SINGBOX_CONFIG_PATH = CONFIG_DIR / "sing-box.json"
LOG_PATH = CONFIG_DIR / "app.log"
SINGBOX_EXE = BIN_DIR / "sing-box.exe"
