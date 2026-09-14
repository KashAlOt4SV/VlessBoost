"""Bounded readiness checks for a newly started local sing-box process."""
from __future__ import annotations

from collections import deque
import re
import threading
import logging
import socket
import subprocess
import time

from app.connection_check import read_exact

logger = logging.getLogger(__name__)


def probe_socks(port: int, timeout: float = 3.0) -> None:
    """Allow a slow greeting without starting a fresh connection every 250 ms."""
    deadline = time.monotonic() + timeout
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Истекло время подключения к локальному порту')
        sock.settimeout(remaining)
        sock.sendall(b'\x05\x01\x00')
        reply = read_exact(sock, 2, deadline)
        if reply != b'\x05\x00':
            raise ConnectionError(f'Локальный порт ответил не как SOCKS5: {reply.hex()}')


def wait_for_proxy(proc, port: int, timeout: float = 30.0) -> None:
    started = time.monotonic()
    deadline = started + timeout
    last_error = 'Локальный порт пока не отвечает'
    attempts = 0
    next_report = started
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'Ядро sing-box завершилось при запуске (код {proc.returncode}).')
        attempts += 1
        try:
            probe_socks(port, timeout=min(3.0, max(0.001, deadline-time.monotonic())))
            if proc.poll() is not None:
                raise RuntimeError(f'Ядро sing-box завершилось при запуске (код {proc.returncode}).')
            logger.info('Local proxy ready: port=%s elapsed=%.2fs attempts=%s',
                        port, time.monotonic()-started, attempts)
            return
        except OSError as exc:
            last_error = str(exc) or type(exc).__name__
        now = time.monotonic()
        if now >= next_report:
            logger.warning('Waiting for local proxy: pid=%s port=%s elapsed=%.1fs attempts=%s reason=%s',
                           proc.pid, port, now-started, attempts, last_error)
            next_report = now + 5
        remaining = deadline-time.monotonic()
        if remaining > 0:
            try:
                proc.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                pass
    raise RuntimeError(
        f'Ядро запущено, но локальный прокси 127.0.0.1:{port} не готов за {timeout:g} с.\n'
        f'Последняя ошибка: {last_error}\n'
        'Это проверка на компьютере, а не ответ VPN-сервера. '
        'Откройте вкладку «Логи» и скопируйте записи последней попытки подключения.'
    )


class CoreOutput:
    """Drain the child pipe through the application's single logging writer."""
    def __init__(self, stream):
        self.stream = stream
        self.lines = deque(maxlen=30)
        self.thread = threading.Thread(target=self._read, name='sing-box-output', daemon=True)

    def start(self):
        self.thread.start()

    def _read(self):
        try:
            while True:
                line = self.stream.readline(16384)
                if not line:
                    break
                line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line).strip()
                if line:
                    self.lines.append(line)
                    logger.info('[sing-box] %s', line)
        except (OSError, ValueError):
            logger.exception('Could not read core output')
        finally:
            self.stream.close()

    def finish(self):
        self.thread.join(timeout=2)

    def summary(self):
        lines = list(self.lines)
        errors = [line for line in lines if any(level in line.upper() for level in ('FATAL', 'ERROR', 'PANIC'))]
        return '\n'.join((errors or lines)[-5:])[-3000:]
