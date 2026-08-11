from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

from app.paths import CACHE_DIR
from app.presets import Preset, _clean_domain, get_preset

logger = logging.getLogger(__name__)

USER_AGENT = "VLESS-Split-Booster/1.0"


def _fetch_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_domain_list(text: str, fmt: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if fmt == "v2fly":
            d = _clean_domain(line)
        else:
            d = _clean_domain(line.split("#")[0])
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def parse_ip_list(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        cidr = line.strip().split("#")[0].strip()
        if not cidr or "/" not in cidr:
            continue
        if cidr not in seen:
            seen.add(cidr)
            out.append(cidr)
    return out


def update_preset_lists(preset: Preset) -> dict[str, int]:
    """Скачивает remote-списки пресета в cache/. Возвращает счётчики."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"domains": 0, "ips": 0}

    if preset.remote_domains_url:
        logger.info("Updating domains for %s", preset.id)
        text = _fetch_text(preset.remote_domains_url)
        domains = parse_domain_list(text, preset.remote_domains_format or "plain")
        path = CACHE_DIR / f"{preset.id}.domains.txt"
        path.write_text("\n".join(domains) + ("\n" if domains else ""), encoding="utf-8")
        stats["domains"] = len(domains)

    if preset.remote_ip_url:
        logger.info("Updating IP CIDR for %s", preset.id)
        text = _fetch_text(preset.remote_ip_url)
        ips = parse_ip_list(text)
        path = CACHE_DIR / f"{preset.id}.ipcidr.txt"
        path.write_text("\n".join(ips) + ("\n" if ips else ""), encoding="utf-8")
        stats["ips"] = len(ips)

    return stats


def update_all_remote(preset_ids: list[str] | None = None) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    ids = preset_ids or []
    if not ids:
        from app.presets import CATALOG

        ids = [p.id for p in CATALOG if p.remote_domains_url or p.remote_ip_url]

    for pid in ids:
        preset = get_preset(pid)
        if not preset:
            continue
        if not preset.remote_domains_url and not preset.remote_ip_url:
            continue
        try:
            results[pid] = update_preset_lists(preset)
        except Exception as exc:
            logger.exception("Failed to update %s", pid)
            results[pid] = {"error": str(exc)}  # type: ignore[dict-item]
    return results
