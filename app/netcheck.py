"""Сетевые проверки: пинг до VLESS-сервера."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from app.vless_parser import parse_vless_url


@dataclass
class PingResult:
    host: str
    port: int
    ms: float | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.ms is not None and self.error is None


def tcp_ping(host: str, port: int, timeout: float = 3.0) -> PingResult:
    """Примерный RTT через TCP connect (ICMP часто закрыт у VPN-серверов)."""
    started = time.perf_counter()
    try:
        # IPv4 предпочтительнее для простоты; если host — домен, getaddrinfo сам решит
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not infos:
            return PingResult(host, port, None, "Не удалось разрешить адрес")
        family, socktype, proto, _, sockaddr = infos[0]
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
        ms = (time.perf_counter() - started) * 1000.0
        return PingResult(host, port, ms)
    except socket.timeout:
        return PingResult(host, port, None, "Таймаут")
    except OSError as exc:
        return PingResult(host, port, None, str(exc))


def ping_vless_url(raw: str, timeout: float = 3.0) -> PingResult:
    ep = parse_vless_url(raw.strip())
    return tcp_ping(ep.server, ep.port, timeout=timeout)
