"""Простая проверка обновлений по version.json."""

from __future__ import annotations

import json
import logging
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import __version__

logger = logging.getLogger(__name__)

# Dual-fetch: raw GitHub (short cache) + jsDelivr (often stale on @main).
# Keep first URL as the preferred source; pick the newer windows.version.
MANIFEST_URLS = (
    "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json",
    "https://cdn.jsdelivr.net/gh/KashAlOt4SV/VlessBoost@main/update/version.json",
)
MANIFEST_URL = MANIFEST_URLS[0]


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


def _fetch_manifest(url: str) -> dict | None:
    bust = f"{url}{'&' if '?' in url else '?'}t={int(time.time())}"
    req = urllib.request.Request(
        bust,
        headers={
            "User-Agent": "VLESS-Boost-Updater/1.1",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("update manifest failed (%s): %s", url, exc)
        return None


def _windows_from_manifest(data: dict) -> WindowsUpdate | None:
    win = data.get("windows") or {}
    remote = str(win.get("version") or "").strip()
    url = str(win.get("url") or "").strip()
    if not remote or not url:
        return None
    return WindowsUpdate(version=remote, url=url)


def check_windows_update(current: str | None = None) -> WindowsUpdate | None:
    cur = current or __version__
    best: WindowsUpdate | None = None
    for manifest_url in MANIFEST_URLS:
        data = _fetch_manifest(manifest_url)
        if not data:
            continue
        cand = _windows_from_manifest(data)
        if not cand:
            continue
        if best is None or _parse_ver(cand.version) > _parse_ver(best.version):
            best = cand
    if best is None:
        return None
    if _parse_ver(best.version) <= _parse_ver(cur):
        return None
    return best


def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "VLESS-Boost-Updater/1.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} при скачивании: {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Сеть: {exc.reason}") from exc
    return dest


def download_update_to_temp(url: str, version: str) -> Path:
    """Скачивает .exe или .zip (с exe внутри) во временную папку."""
    tmp = Path(tempfile.gettempdir()) / f"vless-boost-update-{version}"
    if tmp.exists():
        for p in tmp.glob("*"):
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
    tmp.mkdir(parents=True, exist_ok=True)
    lower = url.split("?", 1)[0].lower()
    logger.info("download update: %s", url)
    if lower.endswith(".zip"):
        zip_path = tmp / "update.zip"
        download_file(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".exe") and not n.endswith("/")]
            if not names:
                raise RuntimeError("В архиве обновления нет .exe")
            names.sort(key=lambda n: (0 if "vless-boost" in Path(n).name.lower() else 1, n))
            member = names[0]
            zf.extract(member, tmp)
            extracted = tmp / member
            final = tmp / Path(member).name
            if extracted.resolve() != final.resolve():
                final.write_bytes(extracted.read_bytes())
            if not final.exists() or final.stat().st_size < 1000:
                raise RuntimeError("Скачанный exe повреждён или пуст")
            return final
    exe_path = tmp / f"VLESS-Boost-{version}.exe"
    download_file(url, exe_path)
    if exe_path.stat().st_size < 1000:
        raise RuntimeError("Скачанный файл слишком маленький — проверьте URL релиза")
    return exe_path
