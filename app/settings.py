from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from app.paths import SETTINGS_PATH
from app.presets import CATALOG


@dataclass
class Settings:
    vless_url: str = ""
    # Какие пресеты включены
    enabled: dict[str, bool] = field(default_factory=dict)
    # Бустить также процессы из включённых пресетов
    route_processes: bool = True
    # Бустить домены / IP из включённых пресетов
    route_domains: bool = True
    route_ips: bool = True
    # Свои домены для пресета custom
    custom_domains: list[str] = field(default_factory=list)
    custom_processes: list[str] = field(default_factory=list)
    tun_interface: str = "vless-split"
    socks_port: int = 10808
    clash_api_port: int = 9090
    log_level: str = "info"
    minimize_to_tray: bool = True
    # Рабочие / служебные сайты всегда напрямую
    protect_direct: bool = True
    protect_domains: list[str] = field(default_factory=list)
    # cards | list
    view_mode: str = "cards"

    def __post_init__(self) -> None:
        if not self.enabled:
            self.enabled = {p.id: p.enabled_default for p in CATALOG}

    def is_enabled(self, preset_id: str) -> bool:
        if preset_id in self.enabled:
            return bool(self.enabled[preset_id])
        preset = next((p for p in CATALOG if p.id == preset_id), None)
        return bool(preset.enabled_default) if preset else False

    def set_enabled(self, preset_id: str, value: bool) -> None:
        self.enabled[preset_id] = value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        base = cls()
        known = set(asdict(base).keys())
        kwargs = {k: v for k, v in data.items() if k in known}
        # Миграция со старого формата
        if "vless_url" in data and "enabled" not in data:
            kwargs.setdefault("enabled", {p.id: p.enabled_default for p in CATALOG})
            if data.get("mode") == "process":
                kwargs["route_domains"] = False
        return cls(**{**asdict(base), **kwargs})


def load_settings() -> Settings:
    if not SETTINGS_PATH.exists():
        settings = Settings()
        save_settings(settings)
        return settings
    with SETTINGS_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    settings = Settings.from_dict(data)
    # Добавляем новые пресеты, которых ещё нет в файле
    for p in CATALOG:
        if p.id not in settings.enabled:
            settings.enabled[p.id] = p.enabled_default
    return settings


def save_settings(settings: Settings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(deepcopy(settings.to_dict()), fh, ensure_ascii=False, indent=2)
