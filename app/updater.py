"""Простая проверка обновлений по version.json."""

from __future__ import annotations

import json
import logging
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app import __version__

logger = logging.getLogger(__name__)

# Замените на свой raw URL (GitHub Releases / raw / CDN)
MANIFEST_URL = "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json"


@dataclass
class WindowsUpdate:
    version: str
    url: str


def _parse_ver(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in (v or "0").split("."):
        try:
            parts.append(int("".join(ch for ch in p if ch.isdigit()) or "0"))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_windows_update(current: str | None = None) -> WindowsUpdate | None:
    cur = current or __version__
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("update check failed: %s", exc)
        return None
    win = data.get("windows") or {}
    remote = str(win.get("version") or "").strip()
    url = str(win.get("url") or "").strip()
    if not remote or not url:
        return None
    if _parse_ver(remote) <= _parse_ver(cur):
        return None
    return WindowsUpdate(version=remote, url=url)


def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    return dest


def download_update_to_temp(url: str, version: str) -> Path:
    path = Path(tempfile.gettempdir()) / f"VLESS-Boost-{version}.exe"
    return download_file(url, path)
