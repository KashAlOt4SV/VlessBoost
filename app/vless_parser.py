from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class VlessEndpoint:
    uuid: str
    server: str
    port: int
    name: str = "vless"
    encryption: str = "none"
    flow: str = ""
    network: str = "tcp"
    security: str = "none"
    sni: str = ""
    alpn: list[str] = field(default_factory=list)
    fingerprint: str = ""
    public_key: str = ""
    short_id: str = ""
    spider_x: str = ""
    path: str = ""
    host: str = ""
    service_name: str = ""
    grpc_mode: str = "gun"
    allow_insecure: bool = False
    packet_encoding: str = ""

    def validate(self) -> None:
        if not self.uuid:
            raise ValueError("В VLESS ссылке нет UUID")
        if not self.server:
            raise ValueError("В VLESS ссылке нет адреса сервера")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Некорректный порт: {self.port}")


_VLESS_RE = re.compile(r"^vless://", re.IGNORECASE)


def _first(qs: dict[str, list[str]], key: str, default: str = "") -> str:
    values = qs.get(key) or qs.get(key.lower()) or []
    return values[0] if values else default


def parse_vless_url(raw: str) -> VlessEndpoint:
    """Разбирает vless:// UUID@host:port?...#name"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Пустая VLESS ссылка")
    if not _VLESS_RE.match(text):
        raise ValueError("Ссылка должна начинаться с vless://")

    # urlparse плохо ест fragment с кириллицей — обрабатываем вручную
    name = "vless"
    if "#" in text:
        text, frag = text.split("#", 1)
        name = unquote(frag) or name

    parsed = urlparse(text)
    uuid = unquote(parsed.username or "")
    server = parsed.hostname or ""
    port = parsed.port or 443
    qs = parse_qs(parsed.query, keep_blank_values=True)

    alpn_raw = _first(qs, "alpn")
    alpn = [p.strip() for p in alpn_raw.split(",") if p.strip()] if alpn_raw else []

    insecure = _first(qs, "allowInsecure") or _first(qs, "insecure")
    packet_encoding = _first(qs, "packetEncoding") or _first(qs, "packet_encoding")

    endpoint = VlessEndpoint(
        uuid=uuid,
        server=server,
        port=int(port),
        name=name,
        encryption=_first(qs, "encryption", "none") or "none",
        flow=_first(qs, "flow"),
        network=_first(qs, "type", "tcp") or "tcp",
        security=_first(qs, "security", "none") or "none",
        sni=_first(qs, "sni"),
        alpn=alpn,
        fingerprint=_first(qs, "fp") or _first(qs, "fingerprint"),
        public_key=_first(qs, "pbk") or _first(qs, "publicKey"),
        short_id=_first(qs, "sid") or _first(qs, "shortId"),
        spider_x=_first(qs, "spx") or _first(qs, "spiderX"),
        path=unquote(_first(qs, "path")),
        host=_first(qs, "host"),
        service_name=_first(qs, "serviceName") or _first(qs, "service_name"),
        grpc_mode=_first(qs, "mode", "gun") or "gun",
        allow_insecure=insecure in {"1", "true", "True", "yes"},
        packet_encoding=packet_encoding,
    )
    endpoint.validate()
    return endpoint


def endpoint_to_singbox_outbound(endpoint: VlessEndpoint, tag: str = "proxy") -> dict[str, Any]:
    """Собирает outbound VLESS для sing-box."""
    outbound: dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": endpoint.server,
        "server_port": endpoint.port,
        "uuid": endpoint.uuid,
        # Discord voice/Go Live and streams are UDP — xudp keeps them on one tunnel.
        # tcp_keep_alive is sing-box 1.13+; Windows bundles 1.11.15.
        "packet_encoding": endpoint.packet_encoding or "xudp",
        "connect_timeout": "8s",
        "udp_fragment": True,
    }
    if endpoint.flow:
        outbound["flow"] = endpoint.flow

    # TLS / Reality
    security = (endpoint.security or "none").lower()
    if security in {"tls", "reality"}:
        tls: dict[str, Any] = {
            "enabled": True,
            "server_name": endpoint.sni or endpoint.host or endpoint.server,
            "insecure": endpoint.allow_insecure,
        }
        if endpoint.alpn:
            tls["alpn"] = endpoint.alpn
        if endpoint.fingerprint:
            tls["utls"] = {"enabled": True, "fingerprint": endpoint.fingerprint}
        if security == "reality":
            if not endpoint.public_key:
                raise ValueError("Для Reality нужен параметр pbk (public key)")
            reality: dict[str, Any] = {
                "enabled": True,
                "public_key": endpoint.public_key,
                "short_id": endpoint.short_id or "",
            }
            # Xray spiderX / spx — в sing-box опционально как path-подсказка не используется;
            # оставляем short_id + pbk (достаточно для Reality).
            tls["reality"] = reality
        outbound["tls"] = tls

    # Transport
    network = (endpoint.network or "tcp").lower()
    if network == "ws":
        transport: dict[str, Any] = {"type": "ws", "path": endpoint.path or "/"}
        if endpoint.host:
            transport["headers"] = {"Host": endpoint.host}
        outbound["transport"] = transport
    elif network in {"httpupgrade", "http_upgrade"}:
        transport = {"type": "httpupgrade", "path": endpoint.path or "/"}
        if endpoint.host:
            transport["host"] = endpoint.host
        outbound["transport"] = transport
    elif network == "grpc":
        outbound["transport"] = {
            "type": "grpc",
            "service_name": endpoint.service_name or "",
        }
    elif network == "http":
        transport = {"type": "http", "path": endpoint.path or "/"}
        if endpoint.host:
            transport["host"] = [endpoint.host]
        outbound["transport"] = transport
    elif network not in {"tcp", "raw"}:
        raise ValueError(f"Неподдерживаемый transport: {network}")

    return outbound
