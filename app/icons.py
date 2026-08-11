"""Логотипы приложения и пресетов."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.paths import ROOT


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return ROOT


IMAGE_DIR = _resource_root() / "app" / "image"
if not IMAGE_DIR.exists():
    IMAGE_DIR = Path(__file__).resolve().parent / "image"

LOGO_DIR = IMAGE_DIR / "logo"
if not LOGO_DIR.exists():
    LOGO_DIR = IMAGE_DIR  # старый путь

PRESETS_PNG_DIR = IMAGE_DIR / "logo_presets" / "png"
PRESETS_SVG_DIR = IMAGE_DIR / "logo_presets"

# preset_id -> имя файла в logo_presets/png
PRESET_LOGO_FILE: dict[str, str] = {
    "discord": "discord.png",
    "youtube": "youtube.png",
    "instagram": "instagram.png",
    "facebook": "meta.png",
    "twitter": "x.png",
    "tiktok": "tiktok.png",
    "twitch": "twitch.png",
    "netflix": "netflix.png",
    "spotify": "spotify.png",
    "telegram": "telegram.png",
    "openai": "chatgpt.png",
    "claude": "claude.png",
    "gemini": "googlegemini.png",
    "reddit": "reddit.png",
    "steam": "steam.png",
    "epic": "epicgames.png",
    "cloudflare": "cloudflare.png",
    "google": "google.png",
    "github": "github.png",
    "whatsapp": "whatsapp.png",
    "linkedin": "linkedin.png",
    "browsers": "googlechrome.png",
    "deadlock-mods": "deadlock-mod-manager.png",
    "speedtest": "speedtest.png",
}

_GLYPHS: dict[str, str] = {
    "antifilter-community": "AF",
    "custom": "+",
}


def load_logo(size: int = 64) -> Image.Image:
    for base in (LOGO_DIR, IMAGE_DIR):
        for name in (f"logo_{size}.png", "logo_256.png", "logo_128.png", "logo_48.png", "logo_32.png"):
            path = base / name
            if path.exists():
                img = Image.open(path).convert("RGBA")
                if img.size != (size, size):
                    img = img.resize((size, size), Image.Resampling.LANCZOS)
                return img
    img = Image.new("RGBA", (size, size), (11, 18, 32, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill=(59, 158, 255, 255))
    return img


def app_ico_path() -> Path | None:
    for base in (LOGO_DIR, IMAGE_DIR):
        p = base / "app.ico"
        if p.exists():
            return p
    return None


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeui.ttf", "SegoeUI.ttf", "arial.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        return (59, 158, 255)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _to_white_alpha(src: Image.Image) -> Image.Image:
    """Логотип → белый силуэт по alpha-каналу (быстро)."""
    src = src.convert("RGBA")
    _r, _g, _b, a = src.split()
    white = Image.new("L", src.size, 255)
    return Image.merge("RGBA", (white, white, white, a))


@lru_cache(maxsize=64)
def make_preset_icon(preset_id: str, color: str, size: int = 40) -> Image.Image:
    """Иконка пресета: бренд-лого на цветном скруглённом фоне."""
    r, g, b = _hex_rgb(color)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=max(8, size // 4),
        fill=(r, g, b, 255),
    )

    logo_name = PRESET_LOGO_FILE.get(preset_id)
    logo_path = PRESETS_PNG_DIR / logo_name if logo_name else None
    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo = _to_white_alpha(logo)
        pad = max(6, size // 5)
        logo.thumbnail((size - pad * 2, size - pad * 2), Image.Resampling.LANCZOS)
        x = (size - logo.width) // 2
        y = (size - logo.height) // 2
        canvas.paste(logo, (x, y), logo)
        return canvas

    # fallback glyph
    glyph = _GLYPHS.get(preset_id, preset_id[:1].upper())
    font = _font(size // 2 if len(glyph) <= 2 else size // 3)
    bbox = draw.textbbox((0, 0), glyph, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 1), glyph, fill=(255, 255, 255, 255), font=font)
    return canvas


def build_app_ico(dest: Path | None = None) -> Path:
    """Multi-size ICO из app/image/logo/logo_*.png"""
    dest = dest or (LOGO_DIR / "app.ico")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 256]
    images: list[Image.Image] = []
    for s in sizes:
        path = LOGO_DIR / f"logo_{s}.png"
        if not path.exists():
            path = IMAGE_DIR / f"logo_{s}.png"
        if path.exists():
            im = Image.open(path).convert("RGBA")
            if im.size != (s, s):
                im = im.resize((s, s), Image.Resampling.LANCZOS)
            images.append(im)
        else:
            images.append(load_logo(s))
    # сохраняем через самый крупный — Windows читает все размеры из ICO
    images[-1].save(dest, format="ICO", sizes=[(s, s) for s in sizes])
    # копия в корень image для совместимости
    alt = IMAGE_DIR / "app.ico"
    if alt != dest:
        images[-1].save(alt, format="ICO", sizes=[(s, s) for s in sizes])
    return dest
