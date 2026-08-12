from __future__ import annotations

import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from app.paths import CACHE_DIR
from app.presets import Preset, _clean_domain, get_preset

logger = logging.getLogger(__name__)

USER_AGENT = "VLESS-Split-Booster/1.0"
_MAX_WORKERS = 8


@dataclass
class ListCache:
    """In-memory status of remote lists (file-backed cache under CACHE_DIR)."""

    last_results: dict[str, dict] = field(default_factory=dict)
    last_fetch_at: float | None = None
    _status_sig: str | None = None
    _status_lines: list[str] = field(default_factory=list)

    def invalidate(self) -> None:
        self._status_sig = None
        self.last_results.clear()
        self.last_fetch_at = None

    def cache_path(self, preset_id: str, kind: str) -> Path:
        return CACHE_DIR / f"{preset_id}.{kind}.txt"

    def file_stats(self, preset_id: str) -> dict[str, int | float]:
        """Read counts / mtime from disk without network."""
        out: dict[str, int | float] = {"domains": 0, "ips": 0, "mtime": 0.0}
        dpath = self.cache_path(preset_id, "domains")
        ipath = self.cache_path(preset_id, "ipcidr")
        if dpath.exists():
            try:
                text = dpath.read_text(encoding="utf-8", errors="replace")
                out["domains"] = sum(1 for ln in text.splitlines() if ln.strip())
                out["mtime"] = max(float(out["mtime"]), dpath.stat().st_mtime)
            except OSError:
                pass
        if ipath.exists():
            try:
                text = ipath.read_text(encoding="utf-8", errors="replace")
                out["ips"] = sum(1 for ln in text.splitlines() if ln.strip())
                out["mtime"] = max(float(out["mtime"]), ipath.stat().st_mtime)
            except OSError:
                pass
        return out

    def status_lines(self, preset_ids: list[str] | None = None) -> list[str]:
        """Instant cached status for UI (no network)."""
        from app.presets import CATALOG

        ids = preset_ids or [
            p.id for p in CATALOG if p.remote_domains_url or p.remote_ip_url
        ]
        sig = "|".join(ids)
        # Include mtimes so disk updates invalidate the memo
        mtimes: list[str] = []
        for pid in ids:
            for kind in ("domains", "ipcidr"):
                p = self.cache_path(pid, kind)
                try:
                    mtimes.append(f"{pid}:{kind}:{p.stat().st_mtime}" if p.exists() else f"{pid}:{kind}:0")
                except OSError:
                    mtimes.append(f"{pid}:{kind}:0")
        full_sig = sig + ";" + ";".join(mtimes)
        if full_sig == self._status_sig and self._status_lines:
            return list(self._status_lines)

        lines: list[str] = []
        for pid in ids:
            st = self.file_stats(pid)
            if not st["domains"] and not st["ips"]:
                lines.append(f"○ {pid}: ещё не скачан")
                continue
            when = ""
            if st["mtime"]:
                when = time.strftime(" · %d.%m %H:%M", time.localtime(float(st["mtime"])))
            lines.append(
                f"● {pid}: сайтов {int(st['domains'])}, IP {int(st['ips'])}{when}"
            )
        self._status_sig = full_sig
        self._status_lines = lines
        return list(lines)

    def remember_results(self, results: dict[str, dict]) -> None:
        self.last_results = dict(results)
        self.last_fetch_at = time.time()
        self._status_sig = None


LIST_CACHE = ListCache()


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
    """Download remote lists in parallel. Invalidates ListCache status memo."""
    LIST_CACHE.invalidate()
    results: dict[str, dict[str, int]] = {}
    ids = preset_ids or []
    if not ids:
        from app.presets import CATALOG

        ids = [p.id for p in CATALOG if p.remote_domains_url or p.remote_ip_url]

    jobs: list[Preset] = []
    for pid in ids:
        preset = get_preset(pid)
        if not preset:
            continue
        if not preset.remote_domains_url and not preset.remote_ip_url:
            continue
        jobs.append(preset)

    def _one(preset: Preset) -> tuple[str, dict]:
        try:
            return preset.id, update_preset_lists(preset)
        except Exception as exc:
            logger.exception("Failed to update %s", preset.id)
            return preset.id, {"error": str(exc)}

    if not jobs:
        return results

    workers = min(_MAX_WORKERS, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, p) for p in jobs]
        for fut in as_completed(futs):
            pid, stats = fut.result()
            results[pid] = stats  # type: ignore[assignment]

    LIST_CACHE.remember_results(results)
    return results
