"""Каталог сервисов для буста: домены, процессы, remote-источники."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.paths import CACHE_DIR, PRESETS_DIR


@dataclass
class Preset:
    id: str
    name: str
    category: str
    description: str
    color: str = "#3BA3C7"
    processes: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    # remote: обновляемые списки
    remote_domains_url: str = ""
    remote_domains_format: str = ""  # v2fly | plain
    remote_ip_url: str = ""
    enabled_default: bool = False
    popular: bool = True

    def effective_domains(self) -> list[str]:
        """Локальные + закешированные remote-домены."""
        domains = list(self.domains)
        cache = CACHE_DIR / f"{self.id}.domains.txt"
        if cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                d = _clean_domain(line)
                if d:
                    domains.append(d)
        # unique preserve order
        seen: set[str] = set()
        out: list[str] = []
        for d in domains:
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out

    def effective_ips(self) -> list[str]:
        cache = CACHE_DIR / f"{self.id}.ipcidr.txt"
        if not cache.exists():
            return []
        out: list[str] = []
        for line in cache.read_text(encoding="utf-8").splitlines():
            cidr = line.strip()
            if cidr and not cidr.startswith("#") and "/" in cidr:
                out.append(cidr)
        return out


def _clean_domain(raw: str) -> str:
    line = raw.strip()
    if not line or line.startswith("#"):
        return ""
    # v2fly: "full:example.com" / "domain @attr" / "include:xxx"
    if line.startswith("include:"):
        return ""
    if line.startswith("full:"):
        line = line[5:].split()[0]
    else:
        line = line.split()[0]
    line = line.lstrip(".").lower()
    if not re.match(r"^[a-z0-9._*-]+$", line):
        return ""
    return line


# --- Встроенный каталог популярных сервисов ---

CATALOG: list[Preset] = [
    Preset(
        id="discord",
        name="Discord",
        category="apps",
        description="Звонки, чаты и вложения",
        color="#5865F2",
        enabled_default=True,
        popular=True,
        processes=[
            "Discord.exe",
            "DiscordPTB.exe",
            "DiscordCanary.exe",
            "DiscordDevelopment.exe",
        ],
        domains=[
            "discord.com",
            "discord.gg",
            "discord.media",
            "discordapp.com",
            "discordapp.net",
            "discordcdn.com",
            "discord.status",
            "discordstatus.com",
            "dis.gd",
            "discord.co",
            "discord.gift",
            "discord.gifts",
            "discord.new",
            "discord.store",
            "discord.tools",
            "discord-activities.com",
            "discordactivities.com",
            "cdn.discordapp.com",
            "media.discordapp.net",
            "gateway.discord.gg",
            "images-ext-1.discordapp.net",
            "images-ext-2.discordapp.net",
            "dl.discordapp.net",
            "updates.discord.com",
            "streamkit.discord.com",
            "latency.discord.media",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/discord",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="youtube",
        name="YouTube",
        category="streaming",
        description="Видео и трансляции без тормозов",
        color="#FF0033",
        enabled_default=True,
        popular=True,
        domains=[
            "youtube.com",
            "youtu.be",
            "youtube-nocookie.com",
            "youtubegaming.com",
            "ytimg.com",
            "ggpht.com",
            "googlevideo.com",
            "youtubei.googleapis.com",
            "youtube.googleapis.com",
            "yt3.ggpht.com",
            "yt3.googleusercontent.com",
            "jnn-pa.googleapis.com",
            "wide-youtube.l.google.com",
            "youtube-ui.l.google.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/youtube",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="instagram",
        name="Instagram",
        category="social",
        description="Лента, сторис и сообщения",
        color="#E1306C",
        popular=True,
        domains=[
            "instagram.com",
            "cdninstagram.com",
            "instagram.c10r.facebook.com",
            "ig.me",
            "igsonar.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/instagram",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="facebook",
        name="Facebook / Meta",
        category="social",
        description="Facebook и Messenger",
        color="#1877F2",
        popular=True,
        domains=[
            "facebook.com",
            "facebook.net",
            "fb.com",
            "fb.me",
            "fbcdn.net",
            "fbsbx.com",
            "messenger.com",
            "meta.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/facebook",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="twitter",
        name="X (Twitter)",
        category="social",
        description="Лента и медиа X",
        color="#1D9BF0",
        popular=True,
        domains=[
            "x.com",
            "twitter.com",
            "twimg.com",
            "t.co",
            "pscp.tv",
            "periscope.tv",
            "tweetdeck.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/twitter",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="tiktok",
        name="TikTok",
        category="social",
        description="Видео и лента TikTok",
        color="#25F4EE",
        popular=True,
        domains=[
            "tiktok.com",
            "tiktokv.com",
            "tiktokcdn.com",
            "tiktokcdn-us.com",
            "musical.ly",
            "byteoversea.com",
            "ibytedtos.com",
            "ttlivecdn.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/tiktok",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="twitch",
        name="Twitch",
        category="streaming",
        description="Стримы и чат",
        color="#9146FF",
        popular=True,
        processes=["Twitch.exe"],
        domains=[
            "twitch.tv",
            "twitchcdn.net",
            "jtvnw.net",
            "ttvnw.net",
            "twitchsvc.net",
            "ext-twitch.tv",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/twitch",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="netflix",
        name="Netflix",
        category="streaming",
        description="Фильмы и сериалы",
        color="#E50914",
        popular=True,
        domains=[
            "netflix.com",
            "netflix.net",
            "nflxvideo.net",
            "nflxso.net",
            "nflximg.net",
            "nflxext.com",
            "fast.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/netflix",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="spotify",
        name="Spotify",
        category="streaming",
        description="Музыка и подкасты",
        color="#1DB954",
        popular=True,
        processes=["Spotify.exe"],
        domains=[
            "spotify.com",
            "spotifycdn.com",
            "scdn.co",
            "spoti.fi",
            "audio-ak-spotify-com.akamaized.net",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/spotify",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="telegram",
        name="Telegram",
        category="apps",
        description="Сообщения и звонки",
        color="#2AABEE",
        popular=True,
        processes=["Telegram.exe"],
        domains=[
            "telegram.org",
            "t.me",
            "tx.me",
            "telegram.me",
            "telesco.pe",
            "cdn-telegram.org",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/telegram",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="openai",
        name="ChatGPT / OpenAI",
        category="ai",
        description="ChatGPT и сервисы OpenAI",
        color="#10A37F",
        popular=True,
        domains=[
            "openai.com",
            "chatgpt.com",
            "chat.openai.com",
            "auth0.openai.com",
            "oaistatic.com",
            "oaiusercontent.com",
            "openaiapi-site.azureedge.net",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/openai",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="claude",
        name="Claude / Anthropic",
        category="ai",
        description="Claude AI от Anthropic",
        color="#D4A27F",
        popular=True,
        domains=[
            "anthropic.com",
            "claude.ai",
        ],
    ),
    Preset(
        id="gemini",
        name="Gemini / Google AI",
        category="ai",
        description="Gemini от Google",
        color="#8E75B2",
        popular=True,
        domains=[
            "gemini.google.com",
            "bard.google.com",
            "generativelanguage.googleapis.com",
            "ai.google.dev",
        ],
    ),
    Preset(
        id="reddit",
        name="Reddit",
        category="social",
        description="Посты, картинки и видео",
        color="#FF4500",
        popular=True,
        domains=[
            "reddit.com",
            "redditmedia.com",
            "redditstatic.com",
            "redd.it",
            "reddituploads.com",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/reddit",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="steam",
        name="Steam",
        category="gaming",
        description="Магазин и загрузки игр",
        color="#1B2838",
        popular=True,
        processes=["steam.exe", "steamwebhelper.exe"],
        domains=[
            "steampowered.com",
            "steamcommunity.com",
            "steamgames.com",
            "steamusercontent.com",
            "steamcontent.com",
            "steamstatic.com",
            "steam-chat.com",
            "steamserver.net",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/steam",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="epic",
        name="Epic Games",
        category="gaming",
        description="Магазин и лаунчер Epic",
        color="#2A2A2A",
        popular=True,
        processes=["EpicGamesLauncher.exe", "EpicWebHelper.exe"],
        domains=[
            "epicgames.com",
            "unrealengine.com",
            "fortnite.com",
            "epicgames.dev",
        ],
    ),
    Preset(
        id="cloudflare",
        name="Cloudflare",
        category="infra",
        description="Сервисы Cloudflare",
        color="#F38020",
        popular=False,
        domains=[
            "cloudflare.com",
            "cloudflare.net",
            "cloudflareinsights.com",
            "cf-ipfs.com",
            "one.one.one.one",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/cloudflare",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="google",
        name="Google",
        category="infra",
        description="Поиск и сервисы Google",
        color="#4285F4",
        popular=False,
        domains=[
            "google.com",
            "googleapis.com",
            "gstatic.com",
            "googleusercontent.com",
            "google.com.ua",
            "google.ru",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/google",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="github",
        name="GitHub",
        category="dev",
        description="Репозитории и проекты",
        color="#24292F",
        popular=True,
        domains=[
            "github.com",
            "githubusercontent.com",
            "githubassets.com",
            "github.io",
            "ghcr.io",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/github",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="whatsapp",
        name="WhatsApp",
        category="apps",
        description="Сообщения WhatsApp",
        color="#25D366",
        popular=True,
        processes=["WhatsApp.exe"],
        domains=[
            "whatsapp.com",
            "whatsapp.net",
            "wa.me",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/whatsapp",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="linkedin",
        name="LinkedIn",
        category="social",
        description="Профили и вакансии",
        color="#0A66C2",
        popular=False,
        domains=["linkedin.com", "licdn.com", "lnkd.in"],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/linkedin",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="deadlock-mods",
        name="Deadlock Mod Manager",
        category="gaming",
        description="Моды для Deadlock",
        color="#7CFF6B",
        popular=True,
        domains=[
            "deadlockmods.app",
            "www.deadlockmods.app",
            "gamebanana.com",
            "images.gamebanana.com",
            "dl.gamebanana.com",
            "api.gamebanana.com",
        ],
    ),
    Preset(
        id="speedtest",
        name="Speedtest (Ookla)",
        category="infra",
        description="Проверка скорости интернета",
        color="#1F9EFF",
        popular=True,
        processes=["Speedtest.exe"],
        domains=[
            "speedtest.net",
            "www.speedtest.net",
            "ookla.com",
            "ooklaserver.net",
            "cdnst.net",
            "speedtestcustom.com",
            "pingtest.net",
            "cellmaps.com",
            "webtest.net",
            "speedtest.co",
        ],
        remote_domains_url="https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/ookla-speedtest",
        remote_domains_format="v2fly",
    ),
    Preset(
        id="browsers",
        name="Весь браузер",
        category="apps",
        description="Весь трафик браузера",
        color="#F4A261",
        popular=True,
        processes=[
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "brave.exe",
            "opera.exe",
            "opera_gx.exe",
            "vivaldi.exe",
            "browser.exe",
            "chromium.exe",
        ],
        domains=[],
    ),
    Preset(
        id="antifilter-community",
        name="Antifilter Community",
        category="lists",
        description="Большой список заблокированных сайтов",
        color="#E9C46A",
        popular=False,
        enabled_default=False,
        domains=[],
        remote_domains_url="https://community.antifilter.download/list/domains.lst",
        remote_domains_format="plain",
        remote_ip_url="https://community.antifilter.download/list/community.lst",
    ),
    Preset(
        id="custom",
        name="Свои домены",
        category="lists",
        description="Ваши сайты и программы",
        color="#9CA3AF",
        popular=True,
        domains=[],
    ),
]


CATEGORY_LABELS = {
    "apps": "Приложения",
    "streaming": "Стриминг",
    "social": "Соцсети",
    "ai": "AI",
    "gaming": "Игры",
    "infra": "Инфра",
    "dev": "Dev",
    "lists": "Списки",
}


def get_preset(preset_id: str) -> Preset | None:
    for p in CATALOG:
        if p.id == preset_id:
            return p
    return None


def presets_by_category() -> dict[str, list[Preset]]:
    out: dict[str, list[Preset]] = {}
    for p in CATALOG:
        out.setdefault(p.category, []).append(p)
    return out


def load_user_overrides() -> dict[str, Any]:
    path = PRESETS_DIR / "user_overrides.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_overrides(preset: Preset) -> Preset:
    data = load_user_overrides().get(preset.id) or {}
    if "domains" in data and isinstance(data["domains"], list):
        preset.domains = list(dict.fromkeys([*preset.domains, *data["domains"]]))
    if "processes" in data and isinstance(data["processes"], list):
        preset.processes = list(dict.fromkeys([*preset.processes, *data["processes"]]))
    return preset


def all_presets() -> list[Preset]:
    return [apply_overrides(Preset(**{**p.__dict__})) for p in CATALOG]
