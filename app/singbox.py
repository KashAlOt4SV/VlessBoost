from __future__ import annotations

import ctypes
import json
import logging
import os
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


class SingBoxManager:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

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

    def start(self, settings: Settings) -> None:
        if self.running:
            return
        if not is_admin():
            raise PermissionError(
                "Для TUN-режима нужны права администратора. "
                "Перезапустите программу от имени администратора."
            )

        self.ensure_binary()
        write_singbox_config(settings)

        # Проверка конфига
        check = subprocess.run(
            [str(SINGBOX_EXE), "check", "-c", str(SINGBOX_CONFIG_PATH)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if check.returncode != 0:
            raise RuntimeError(
                "Конфиг sing-box невалиден:\n"
                + (check.stderr or check.stdout or "unknown error")
            )

        log_fh = LOG_PATH.open("a", encoding="utf-8")
        log_fh.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_fh.flush()

        self._proc = subprocess.Popen(
            [str(SINGBOX_EXE), "run", "-c", str(SINGBOX_CONFIG_PATH)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(BIN_DIR),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(0.8)
        if self._proc.poll() is not None:
            raise RuntimeError(
                f"sing-box сразу завершился (код {self._proc.returncode}). "
                f"Смотрите лог: {LOG_PATH}"
            )
        logger.info("sing-box запущен, pid=%s", self._proc.pid)

    def stop(self) -> None:
        if not self._proc:
            return
        proc = self._proc
        self._proc = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        logger.info("sing-box остановлен")

    def status_text(self) -> str:
        if self.running and self._proc:
            return f"Работает (pid {self._proc.pid})"
        return "Остановлен"
