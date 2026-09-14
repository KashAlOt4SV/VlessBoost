from __future__ import annotations

import ctypes
from copy import deepcopy
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from app.config_builder import write_singbox_config
from app.paths import BIN_DIR, LOG_PATH, SINGBOX_CONFIG_PATH, SINGBOX_EXE
from app.settings import Settings
from app.startup_check import CoreOutput, wait_for_proxy

logger = logging.getLogger(__name__)

# Актуальный стабильный релиз sing-box (windows amd64)
SINGBOX_VERSION = "1.11.15"
SINGBOX_ZIP_URL = (
    f"https://github.com/SagerNet/sing-box/releases/download/"
    f"v{SINGBOX_VERSION}/sing-box-{SINGBOX_VERSION}-windows-amd64.zip"
)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Перезапуск текущего процесса с правами администратора (нужно для TUN)."""
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )


def _create_no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


_PROCESS_CACHE: tuple[float, list[tuple[int, str]]] | None = None
_PROCESS_CACHE_TTL = 2.5


def list_singbox_processes(*, force: bool = False) -> list[tuple[int, str]]:
    """Все процессы sing-box.exe: (pid, executable_path).

    Results are cached briefly so repeated UI status checks do not spawn
    PowerShell on every paint / page switch / restore.
    """
    global _PROCESS_CACHE
    now = time.monotonic()
    if (
        not force
        and _PROCESS_CACHE is not None
        and (now - _PROCESS_CACHE[0]) < _PROCESS_CACHE_TTL
    ):
        return list(_PROCESS_CACHE[1])

    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'sing-box.exe'\" | "
        "Select-Object ProcessId, ExecutablePath | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=_create_no_window(),
        )
    except Exception as exc:
        logger.warning("list sing-box failed: %s", exc)
        return []
    text = (out.stdout or "").strip()
    if not text:
        result: list[tuple[int, str]] = []
        _PROCESS_CACHE = (now, result)
        return result
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    result = []
    for row in data:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        path = str(row.get("ExecutablePath") or "").strip()
        result.append((pid, path))
    _PROCESS_CACHE = (now, result)
    return list(result)


def list_our_singbox_processes(*, force: bool = False) -> list[tuple[int, str]]:
    """sing-box из нашей папки bin/ (или без пути — считаем своим)."""
    our = SINGBOX_EXE.resolve()
    found = []
    for pid, path in list_singbox_processes(force=force):
        # Unknown paths and other VPN clients are never ours to terminate.
        if not path:
            continue
        try:
            if Path(path).resolve() == our:
                found.append((pid, path))
        except OSError:
            continue
    return found


def kill_pids(pids: list[int]) -> list[int]:
    """Убивает процессы, возвращает список успешно завершённых pid."""
    global _PROCESS_CACHE
    killed: list[int] = []
    for pid in pids:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_create_no_window(),
            )
            if result.returncode == 0:
                killed.append(pid)
        except Exception as exc:
            logger.warning("taskkill %s failed: %s", pid, exc)
    _PROCESS_CACHE = None
    return killed


class SingBoxManager:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self.active_settings: Settings | None = None
        self._output: CoreOutput | None = None
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def managed_pid(self) -> int | None:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc.pid
        return None

    def external_instances(self, *, force: bool = False) -> list[tuple[int, str]]:
        """Чужие/зависшие sing-box (не наш текущий Popen)."""
        mine = self.managed_pid()
        return [
            (pid, path)
            for pid, path in list_our_singbox_processes(force=force)
            if pid != mine
        ]

    def has_external_instance(self, *, force: bool = False) -> bool:
        return bool(self.external_instances(force=force))

    def kill_external(self) -> list[int]:
        pids = [pid for pid, _ in self.external_instances(force=True)]
        if not pids:
            return []
        killed = kill_pids(pids)
        logger.info("killed external sing-box: %s", killed)
        return killed

    def ensure_binary(self) -> Path:
        if SINGBOX_EXE.exists():
            return SINGBOX_EXE
        logger.info("Скачиваю sing-box %s…", SINGBOX_VERSION)
        self._download_singbox()
        if not SINGBOX_EXE.exists():
            raise RuntimeError("Не удалось установить sing-box.exe")
        return SINGBOX_EXE

    def _download_singbox(self) -> None:
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "sing-box.zip"
            urllib.request.urlretrieve(SINGBOX_ZIP_URL, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path)
            found = next(tmp_path.rglob("sing-box.exe"), None)
            if found is None:
                raise RuntimeError("В архиве sing-box нет sing-box.exe")
            shutil.copy2(found, SINGBOX_EXE)

    def start(self, settings: Settings, *, kill_external: bool = True) -> None:
        if self.running:
            return
        if not is_admin():
            raise PermissionError(
                "Для TUN-режима нужны права администратора. "
                "Перезапустите программу от имени администратора."
            )

        self.ensure_binary()
        logger.info("Starting core: tun=%s local_port=%s", settings.tun_interface, settings.socks_port)
        write_singbox_config(settings)

        check = subprocess.run(
            [str(SINGBOX_EXE), "check", "-c", str(SINGBOX_CONFIG_PATH)],
            capture_output=True,
            text=True,
            creationflags=_create_no_window(),
            timeout=20,
        )
        if check.returncode != 0:
            raise RuntimeError(
                "Конфиг sing-box невалиден:\n"
                + (check.stderr or check.stdout or "unknown error")
            )

        if kill_external and self.has_external_instance():
            self.kill_external()

        logger.info('--- core start ---')
        self._proc = subprocess.Popen(
            [str(SINGBOX_EXE), 'run', '-c', str(SINGBOX_CONFIG_PATH)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            cwd=str(BIN_DIR), creationflags=_create_no_window(),
        )
        self._output = CoreOutput(self._proc.stdout)
        self._output.start()
        try:
            wait_for_proxy(self._proc, settings.socks_port)
        except Exception as exc:
            logger.exception('Core did not become ready')
            output = self._output
            self.stop()  # Drain final core messages before reporting the failure.
            detail = output.summary() if output else ''
            self._log_adapter_state()
            message = str(exc)
            if detail:
                message += '\n\nПоследние сообщения ядра:\n' + detail
            message += '\n\nПолный журнал доступен во вкладке «Логи».'
            raise RuntimeError(message) from exc
        self.active_settings = deepcopy(settings)
        logger.info("sing-box запущен, pid=%s", self._proc.pid)

    def _log_adapter_state(self) -> None:
        """Read-only evidence for driver/startup failures; never resets adapters."""
        command = (
            "Get-CimInstance Win32_NetworkAdapter | "
            "Where-Object { $_.Name -match 'Wintun|sing-tun' -or $_.ServiceName -match 'wintun' } | "
            "Select-Object Name,NetEnabled,NetConnectionStatus,ConfigManagerErrorCode | "
            "ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=8,
                creationflags=_create_no_window(),
            )
            if result.returncode == 0:
                logger.warning("TUN adapter snapshot: %s", (result.stdout or "").strip() or "no matching adapters")
            else:
                logger.warning("Adapter query failed: code=%s", result.returncode)
        except Exception as exc:
            logger.warning("Adapter query unavailable: %s", exc)

    def stop(self) -> None:
        if self._proc:
            proc = self._proc
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            if self._output is not None:
                self._output.finish()
                self._output = None
            self._proc = None
            self.active_settings = None
            logger.info("sing-box остановлен")

    def status_text(self) -> str:
        if self.running and self._proc:
            return f"Работает (pid {self._proc.pid})"
        external = self.external_instances()
        if external:
            pids = ", ".join(str(p) for p, _ in external)
            return f"Найден зависший sing-box (pid {pids})"
        return "Остановлен"
