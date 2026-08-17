"""Простая проверка обновлений по version.json + in-place install для Windows."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import __version__
from app.paths import CONFIG_DIR

logger = logging.getLogger(__name__)

# Dual-fetch: raw GitHub (short cache) + jsDelivr (often stale on @main).
MANIFEST_URLS = (
    "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json",
    "https://cdn.jsdelivr.net/gh/KashAlOt4SV/VlessBoost@main/update/version.json",
)
MANIFEST_URL = MANIFEST_URLS[0]

UPDATES_DIR = CONFIG_DIR / "updates"
PENDING_PATH = UPDATES_DIR / "pending.json"
STAGED_EXE_NAME = "VLESS-Boost.exe"


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
            "User-Agent": "VLESS-Boost-Updater/1.2",
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
        headers={"User-Agent": "VLESS-Boost-Updater/1.2"},
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


def _install_exe_path() -> Path:
    """Canonical install target next to the running frozen exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "VLESS-Boost.exe"
    return Path.cwd() / "VLESS-Boost.exe"


def stage_update_exe(src_exe: Path, version: str) -> Path:
    """Copy downloaded exe into AppData\\VLESS-Boost\\updates and write pending marker."""
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    staged = UPDATES_DIR / STAGED_EXE_NAME
    src_exe = Path(src_exe).resolve()
    if src_exe.resolve() != staged.resolve():
        shutil.copy2(src_exe, staged)
    install_exe = str(_install_exe_path()) if getattr(sys, "frozen", False) else ""
    pending = {
        "version": version,
        "staged": str(staged),
        "install_exe": install_exe,
        "created_at": int(time.time()),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("staged update %s -> %s (install=%s)", version, staged, install_exe)
    return staged


def clear_pending_update() -> None:
    try:
        if PENDING_PATH.exists():
            PENDING_PATH.unlink()
    except OSError:
        pass


def read_pending_update() -> dict | None:
    if not PENDING_PATH.exists():
        return None
    try:
        data = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        staged = Path(str(data.get("staged") or ""))
        if not staged.is_file() or staged.stat().st_size < 1000:
            return None
        return data
    except Exception:
        return None


def download_update_to_temp(url: str, version: str) -> Path:
    """Download .exe/.zip, then stage into AppData updates (not only Temp)."""
    tmp = Path(tempfile.gettempdir()) / f"vless-boost-update-{version}"
    tmp.mkdir(parents=True, exist_ok=True)
    for p in tmp.glob("*"):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass

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
            downloaded = tmp / Path(member).name
            if extracted.resolve() != downloaded.resolve():
                downloaded.write_bytes(extracted.read_bytes())
    else:
        downloaded = tmp / f"VLESS-Boost-{version}.exe"
        download_file(url, downloaded)

    if not downloaded.exists() or downloaded.stat().st_size < 1000:
        raise RuntimeError("Скачанный exe повреждён или пуст")
    return stage_update_exe(downloaded, version)


def _write_apply_bat(*, src: Path, dst: Path, wait_pid: int) -> Path:
    """Bat that waits until the install exe is unlocked, then replaces it.

    Must NOT use tasklist/findstr: those spawn visible consoles and can loop forever.
    """
    bat = UPDATES_DIR / "apply-update.bat"
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    src_s = str(src)
    dst_s = str(dst)
    old_s = str(dst) + ".old"
    pending_s = str(PENDING_PATH)
    lock_s = str(UPDATES_DIR / "apply.lock")
    log_s = str(UPDATES_DIR / "apply.log")
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f'set "SRC={src_s}"',
        f'set "DST={dst_s}"',
        f'set "OLD={old_s}"',
        f'set "PENDING={pending_s}"',
        f'set "LOCK={lock_s}"',
        f'set "LOG={log_s}"',
        f'echo apply start pid={int(wait_pid)} %DATE% %TIME%>>"%LOG%"',
        'echo %RANDOM%>"%LOCK%"',
        "set N=0",
        ":wait",
        "set /a N+=1",
        "if %N% GTR 90 (",
        '  echo wait timeout>>"%LOG%"',
        '  del /f /q "%LOCK%" >nul 2>&1',
        "  exit /b 1",
        ")",
        "ping 127.0.0.1 -n 2 >nul",
        'if exist "%OLD%" del /f /q "%OLD%" >nul 2>&1',
        'if exist "%DST%" del /f /q "%DST%" >nul 2>&1',
        'copy /y "%SRC%" "%DST%" >nul',
        "if errorlevel 1 goto wait",
        'del /f /q "%OLD%" >nul 2>&1',
        'del /f /q "%PENDING%" >nul 2>&1',
        'del /f /q "%LOCK%" >nul 2>&1',
        'echo ok>>"%LOG%"',
        'start "" "%DST%"',
        'del /f /q "%~f0" >nul 2>&1',
        "endlocal",
        "exit /b 0",
        "",
    ]
    bat.write_text("\r\n".join(lines), encoding="utf-8")
    return bat


CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def abort_stuck_apply_scripts() -> None:
    """Kill leftover apply-update.bat / findstr wait loops from older builds.

    Elevated updater processes often have an empty WMI CommandLine, so also match
    findstr by window title and stop its parent cmd first (otherwise the bat
    proceeds to copy/relaunch after findstr dies).
    """
    if sys.platform != "win32":
        return
    lock = UPDATES_DIR / "apply.lock"
    bat = UPDATES_DIR / "apply-update.bat"
    try:
        listed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq findstr.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        has_findstr = "findstr" in (listed.stdout or "").lower()
    except Exception:
        has_findstr = True
    if not has_findstr and not bat.exists() and not PENDING_PATH.exists() and not lock.exists():
        return
    script = (
        "$ids = @(); "
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "  $cl = $_.CommandLine; "
        "  if ($cl -and $_.Name -eq 'cmd.exe' -and $cl -match 'apply-update\\.bat') { $ids += $_.ProcessId }; "
        "  if ($cl -and $_.Name -eq 'findstr.exe' -and $cl -match '/C:\"\\d+\"') { "
        "    $ids += $_.ParentProcessId; $ids += $_.ProcessId "
        "  } "
        "}; "
        "Get-Process -Name findstr -ErrorAction SilentlyContinue | Where-Object { "
        "  $_.MainWindowTitle -match 'findstr\\s+/C:\"\\d+\"' "
        "} | ForEach-Object { "
        "  $wmi = Get-CimInstance Win32_Process -Filter (\"ProcessId={0}\" -f $_.Id) -ErrorAction SilentlyContinue; "
        "  if ($wmi) { $ids += $wmi.ParentProcessId }; "
        "  $ids += $_.Id "
        "}; "
        "$ids | Where-Object { $_ -gt 0 } | Select-Object -Unique | ForEach-Object { "
        "  Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue "
        "}"
    )
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
            shell=False,
        )
    except Exception:
        logger.warning("could not abort stuck updater processes", exc_info=True)
    try:
        if lock.exists():
            lock.unlink()
    except OSError:
        pass
    if not PENDING_PATH.exists():
        try:
            if bat.exists():
                bat.unlink()
        except OSError:
            pass


def _spawn_detached_bat(bat: Path) -> None:
    """Launch updater bat hidden so it survives parent exit without consoles."""
    lock = UPDATES_DIR / "apply.lock"
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < 180:
            logger.info("apply.lock present (%.0fs) — skip second updater", age)
            return
        try:
            lock.unlink()
        except OSError:
            pass

    try:
        lock.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    creation = 0
    startup = None
    if sys.platform == "win32":
        creation = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    subprocess.Popen(
        ["cmd.exe", "/d", "/c", str(bat)],
        cwd=str(bat.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation,
        startupinfo=startup,
        shell=False,
    )


def apply_windows_update(new_exe: Path) -> Path:
    """Prepare in-place replace of the installed VLESS-Boost.exe.

    Returns path of the apply .bat (caller starts it detached and exits).
    Settings in %LOCALAPPDATA%\\VLESS-Boost are not touched.
    """
    new_exe = Path(new_exe).resolve()
    if not new_exe.exists():
        raise RuntimeError(f"Файл обновления не найден: {new_exe}")

    if not getattr(sys, "frozen", False):
        # Dev: stage only; return exe path for manual run
        return new_exe

    dst = _install_exe_path()
    # Ensure staged copy exists under AppData
    version = __version__
    pending = read_pending_update()
    if pending and pending.get("version"):
        version = str(pending["version"])
    staged = stage_update_exe(new_exe, version)
    bat = _write_apply_bat(src=staged, dst=dst, wait_pid=os.getpid())
    logger.info("update bat ready: %s -> %s (pid=%s)", staged, dst, os.getpid())
    return bat


def launch_apply_and_exit(bat: Path) -> None:
    """Start apply bat detached and terminate this process."""
    _spawn_detached_bat(Path(bat))
    # Hard exit so file lock on running exe is released for the bat
    os._exit(0)


def apply_pending_update_on_startup() -> bool:
    """If a staged update is pending, apply it now and exit.

    Returns True if this process should stop (updater launched).
    """
    if not getattr(sys, "frozen", False):
        return False
    pending = read_pending_update()
    if not pending:
        return False
    staged = Path(str(pending.get("staged") or ""))
    if not staged.is_file():
        clear_pending_update()
        return False
    remote_ver = str(pending.get("version") or "")
    if remote_ver and _parse_ver(remote_ver) <= _parse_ver(__version__):
        # Already running the staged version (or newer)
        clear_pending_update()
        return False
    install = Path(str(pending.get("install_exe") or "")) or _install_exe_path()
    # Only auto-apply when install path matches our folder (same install)
    running = Path(sys.executable).resolve()
    if install.resolve().parent != running.parent:
        # Still allow apply into install path from pending
        pass
    try:
        bat = _write_apply_bat(src=staged, dst=install.resolve(), wait_pid=os.getpid())
        logger.info("startup: applying pending update %s", remote_ver)
        _spawn_detached_bat(bat)
        return True
    except Exception:
        logger.exception("failed to apply pending update")
        return False
