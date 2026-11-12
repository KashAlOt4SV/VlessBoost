"""Import AWG 3.1 profiles without executing configuration directives."""
from __future__ import annotations

import base64
import configparser
import ipaddress
import json
import re
import zlib
from dataclasses import dataclass

INTERFACE_KEYS = {
    "privatekey", "address", "listenport", "mtu", "dns", "jc", "jmin", "jmax",
    "s1", "s2", "s3", "s4", "h1", "h2", "h3", "h4", "i1", "i2", "i3", "i4", "i5",
    "j1", "j2", "j3", "itime", "headerprotectionkey", "contentpaddingaddition",
    "rekeyaftertime", "rekeytimeout", "rejectaftertime", "keepalivetimeout",
    "maxhandshakeattempts", "randomtrailers", "disablecookies", "table",
}
PEER_KEYS = {"publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"}


def _key(value: str, label: str) -> None:
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != 32 or not any(decoded):
            raise ValueError()
    except Exception:
        raise ValueError(f"Некорректный ключ {label}: нужен Base64-ключ длиной 32 байта") from None


def _find_config(value, depth=0):
    if depth > 14:
        return None
    if isinstance(value, str):
        if "[Interface]" in value and "[Peer]" in value:
            return value
        try:
            return _find_config(json.loads(value), depth + 1)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        for item in value.values():
            found = _find_config(item, depth + 1)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_config(item, depth + 1)
            if found:
                return found
    return None


def decode_profile(text: str) -> str:
    text = text.strip().lstrip("\ufeff")
    if len(text) > 2_000_000:
        raise ValueError("Профиль слишком большой")
    if text.startswith("vless://"):
        raise ValueError("VLESS-ссылка не подходит для AmneziaWG. Экспортируйте AWG 3.1 .conf из Amnezia.")
    if text.startswith("vpn://"):
        try:
            encoded = text[6:]
            data = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            # Qt qCompress prefixes zlib data with a four-byte uncompressed length.
            payload = data[4:] if len(data) > 4 and data[4] == 0x78 else data
            decoder = zlib.decompressobj()
            raw = decoder.decompress(payload, 2_000_001)
            if len(raw) > 2_000_000 or decoder.unconsumed_tail or not decoder.eof:
                raise ValueError()
            result = _find_config(json.loads(raw))
            if not result:
                raise ValueError()
            return result
        except Exception:
            raise ValueError("В vpn:// не найден AWG .conf. Импортируйте экспортированный файл AmneziaWG 3.1.") from None
    return text


@dataclass(frozen=True)
class AwgProfile:
    interface: dict[str, str]
    peer: dict[str, str]

    @property
    def endpoint(self):
        return self.peer["endpoint"]

    @property
    def host(self):
        return self.endpoint.rsplit(":", 1)[0].strip("[]")

    @property
    def ipv4(self):
        return next(str(ipaddress.ip_interface(a.strip()).ip)
                    for a in self.interface["address"].split(",")
                    if ipaddress.ip_interface(a.strip()).version == 4)

    def service_config(self) -> str:
        # DNS remains controlled by the split router; AWG must never take system DNS/routes.
        lines = ["[Interface]"]
        lines += [f"{key} = {value}" for key, value in self.interface.items() if key not in {"dns", "table"}]
        lines += ["Table = off", "", "[Peer]"]
        lines += [f"{key} = {value}" for key, value in self.peer.items()]
        return "\n".join(lines) + "\n"


def parse_awg_profile(text: str) -> AwgProfile:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(decode_profile(text))
    except configparser.Error:
        raise ValueError("Некорректный .conf: нужны секции [Interface] и [Peer] без повторяющихся полей") from None
    if set(parser.sections()) != {"Interface", "Peer"} or parser.defaults():
        raise ValueError("Поддерживается профиль с одним [Interface] и одним [Peer]")
    interface, peer = dict(parser["Interface"]), dict(parser["Peer"])
    if any("\n" in value or "\r" in value for value in (*interface.values(), *peer.values())):
        raise ValueError("Многострочные значения в .conf не поддерживаются")
    if set(interface) - INTERFACE_KEYS or set(peer) - PEER_KEYS:
        raise ValueError("Профиль содержит неподдерживаемые поля или команды PreUp/PostUp")
    for field in ("privatekey", "address", "headerprotectionkey", "s1", "s2", "s3", "s4"):
        if not interface.get(field):
            raise ValueError(f"В профиле AWG 3.1 отсутствует {field}")
    for field in ("publickey", "endpoint", "allowedips"):
        if not peer.get(field):
            raise ValueError(f"В [Peer] отсутствует {field}")
    _key(interface["privatekey"], "PrivateKey")
    _key(interface["headerprotectionkey"], "HeaderProtectionKey")
    _key(peer["publickey"], "PublicKey")
    if peer.get("presharedkey"):
        _key(peer["presharedkey"], "PresharedKey")
    try:
        addresses = [ipaddress.ip_interface(a.strip()) for a in interface["address"].split(",")]
        if not any(a.version == 4 for a in addresses):
            raise ValueError()
        for field in ("s1", "s2", "s3", "s4"):
            if not 12 <= int(interface[field]) <= 65535:
                raise ValueError()
        mtu = int(interface.get("mtu", "1280"))
        if not 576 <= mtu <= 9000:
            raise ValueError()
        interface.setdefault("mtu", "1280")
        host, port = peer["endpoint"].rsplit(":", 1)
        if not host or not 1 <= int(port) <= 65535 or not re.fullmatch(r"[\w.\-:\[\]]+", host):
            raise ValueError()
        networks = [ipaddress.ip_network(a.strip(), strict=False) for a in peer["allowedips"].split(",")]
        if ipaddress.ip_network("0.0.0.0/0") not in networks:
            raise ValueError("full")
    except ValueError:
        raise ValueError("Проверьте Address (нужен IPv4), Endpoint, MTU, S1–S4 ≥ 12 и AllowedIPs = 0.0.0.0/0") from None
    return AwgProfile(interface, peer)
