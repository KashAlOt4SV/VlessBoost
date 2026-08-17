from __future__ import annotations

import json
from typing import Any

from app.paths import SINGBOX_CONFIG_PATH
from app.presets import get_preset
from app.settings import Settings
from app.vless_parser import endpoint_to_singbox_outbound, parse_vless_url

# Всегда напрямую — рабочие сервисы не должны уезжать в VLESS
PROTECT_DIRECT_DOMAINS = [
    # Microsoft 365 / Teams / Outlook
    "microsoft.com",
    "microsoftonline.com",
    "microsoft.net",
    "office.com",
    "office.net",
    "office365.com",
    "outlook.com",
    "outlook.office.com",
    "outlook.office365.com",
    "teams.microsoft.com",
    "teams.cdn.office.net",
    "sharepoint.com",
    "sharepointonline.com",
    "lync.com",
    "skype.com",
    "live.com",
    "msn.com",
    "windows.com",
    "windows.net",
    "windowsupdate.com",
    "azure.com",
    "azureedge.net",
    "msauth.net",
    "msftauth.net",
    "msftidentity.com",
    "microsoftazuread-sso.com",
    # Часто нужные рабочие / банк / госуслуги (не бустим)
    "gosuslugi.ru",
    "mos.ru",
    "nalog.ru",
]


def collect_routes(settings: Settings) -> tuple[list[str], list[str], list[str]]:
    """Собирает processes / domains / ip_cidr из включённых пресетов."""
    processes: list[str] = []
    domains: list[str] = []
    ips: list[str] = []

    for preset_id, on in settings.enabled.items():
        if not on:
            continue
        preset = get_preset(preset_id)
        if not preset:
            continue

        if settings.route_processes:
            processes.extend(preset.processes)
            if preset_id == "custom":
                processes.extend(settings.custom_processes)

        if settings.route_domains:
            if preset_id == "custom":
                domains.extend(settings.custom_domains)
            else:
                domains.extend(preset.effective_domains())

        if settings.route_ips:
            ips.extend(preset.effective_ips())

    def uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in items:
            x = (x or "").strip()
            if not x or x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    return uniq(processes), uniq(domains), uniq(ips)


def build_singbox_config(settings: Settings) -> dict[str, Any]:
    if not settings.vless_url.strip():
        raise ValueError("Сначала укажите VLESS ссылку в настройках")

    processes, domains, ips = collect_routes(settings)
    if not processes and not domains and not ips:
        raise ValueError("Включите хотя бы один сервис или добавьте свои домены")

    endpoint = parse_vless_url(settings.vless_url)
    proxy = endpoint_to_singbox_outbound(endpoint, tag="proxy")

    protect = list(PROTECT_DIRECT_DOMAINS)
    if getattr(settings, "protect_direct", True):
        protect.extend(settings.protect_domains or [])

    # Sniff only long enough to classify TLS/HTTP/QUIC — long sniff delays Discord UDP.
    route_rules: list[dict[str, Any]] = [
        {"action": "sniff", "timeout": "200ms"},
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "outbound": "direct"},
    ]
    if protect:
        route_rules.append({"domain_suffix": uniq_list(protect), "outbound": "direct"})

    if processes:
        route_rules.append({"process_name": processes, "outbound": "proxy"})
    if domains:
        route_rules.append({"domain_suffix": domains, "outbound": "proxy"})
    if ips:
        chunk = 1500
        for i in range(0, len(ips), chunk):
            route_rules.append({"ip_cidr": ips[i : i + chunk], "outbound": "proxy"})

    # DNS: НЕ используем address=local — с TUN это ломает обычные сайты
    dns_rules: list[dict[str, Any]] = []
    if processes:
        dns_rules.append({"process_name": processes, "server": "dns-remote"})
    if domains:
        dns_rules.append({"domain_suffix": domains, "server": "dns-remote"})
    if protect:
        dns_rules.insert(0, {"domain_suffix": uniq_list(protect), "server": "dns-direct"})

    return {
        "log": {"level": settings.log_level or "info", "timestamp": True},
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "address": "https://1.1.1.1/dns-query",
                    "detour": "proxy",
                    "address_resolver": "dns-bootstrap",
                },
                {
                    "tag": "dns-direct",
                    "address": "udp://8.8.8.8",
                    "detour": "direct",
                },
                {
                    "tag": "dns-bootstrap",
                    "address": "udp://1.1.1.1",
                    "detour": "direct",
                },
            ],
            "rules": dns_rules,
            "final": "dns-direct",
            "strategy": "ipv4_only",
            "independent_cache": True,
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": settings.tun_interface or "vless-split",
                "address": ["172.19.0.1/30"],
                # 1500 + VLESS/TLS overhead fragments Discord voice/Go Live UDP.
                "mtu": 1400,
                "auto_route": True,
                # strict_route=true часто ломает обычный (direct) трафик на Windows
                "strict_route": False,
                "stack": "mixed",
                "endpoint_independent_nat": True,
                "udp_timeout": "5m",
            },
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": settings.socks_port,
            },
        ],
        "outbounds": [
            proxy,
            {
                "type": "direct",
                "tag": "direct",
            },
        ],
        "route": {
            "auto_detect_interface": True,
            "default_domain_resolver": "dns-direct",
            "rules": route_rules,
            "final": "direct",
        },
    }


def uniq_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = (x or "").strip().lower().lstrip(".")
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def write_singbox_config(settings: Settings) -> tuple[list[str], list[str], list[str]]:
    config = build_singbox_config(settings)
    SINGBOX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SINGBOX_CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    return collect_routes(settings)
