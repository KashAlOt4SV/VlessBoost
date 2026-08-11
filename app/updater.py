"""Простая проверка обновлений по version.json."""

from __future__ import annotations

import json
import logging
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import __version__

logger = logging.getLogger(__name__)

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
    req = urllib.request.Request(url, headers={"User-Agent": "VLESS-Boost-Updater"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    return dest


def download_update_to_temp(url: str, version: str) -> Path:
    """Скачивает .exe или .zip (с exe внутри) во временную папку."""
    tmp = Path(tempfile.gettempdir()) / f"vless-boost-update-{version}"
    tmp.mkdir(parents=True, exist_ok=True)
    lower = url.lower()
    if lower.endswith(".zip"):
        zip_path = tmp / "update.zip"
        download_file(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".exe")]
            if not names:
                raise RuntimeError("В архиве обновления нет .exe")
            # предпочитаем VLESS-Boost.exe
            names.sort(key=lambda n: (0 if "vless-boost" in n.lower() else 1, n))
            target_name = Path(names[0]).name
            zf.extract(names[0], tmp)
            extracted = tmp / names[0]
            # если был подкаталог — перенесём в корень tmp
            final = tmp / target_name
            if extracted.resolve() != final.resolve():
                final.write_bytes(extracted.read_bytes())
            return final
    exe_path = tmp / f"VLESS-Boost-{version}.exe"
    return download_file(url, exe_path)
