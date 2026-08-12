"""Left sidebar: brand, nav, connection status."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.icons import load_logo
from app.ui.helpers import danger_btn
from app.ui.theme import COLORS, FONT_UI, FONT_UI_BLACK, FONT_UI_BOLD, SIDEBAR_WIDTH


NAV_ITEMS = (
    ("home", "Главная"),
    ("boost", "Сервисы"),
    ("settings", "Настройки"),
    ("update", "Обновления"),
    ("logs", "Логи"),
    ("lists", "Списки"),
    ("support", "Поддержка"),
    ("about", "О приложении"),
)


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_nav: Callable[[str], None],
        on_disconnect: Callable[[], None],
        *,
        logo_refs: list,
        **kw,
    ):
        super().__init__(master, width=SIDEBAR_WIDTH, fg_color=COLORS["panel"], corner_radius=0, **kw)
        self.pack_propagate(False)
        self._on_nav = on_nav
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._nav_accents: dict[str, ctk.CTkFrame] = {}
        self._active = "home"

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 16))
        try:
            logo = load_logo(40)
            img = ctk.CTkImage(light_image=logo, dark_image=logo, size=(40, 40))
            logo_refs.append(img)
            ctk.CTkLabel(brand, text="", image=img).pack(side="left", padx=(0, 10))
        except Exception:
            pass
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(
            titles,
            text="VLESS",
            font=ctk.CTkFont(family=FONT_UI_BLACK, size=16),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="BOOST",
            font=ctk.CTkFont(family=FONT_UI_BLACK, size=16),
            text_color=COLORS["primary"],
            anchor="w",
        ).pack(anchor="w")

        nav_wrap = ctk.CTkFrame(self, fg_color="transparent")
        nav_wrap.pack(fill="x", pady=(4, 0))
        for key, label in NAV_ITEMS:
            row = ctk.CTkFrame(nav_wrap, fg_color="transparent", height=44)
            row.pack(fill="x", padx=10, pady=2)
            row.pack_propagate(False)
            accent = ctk.CTkFrame(row, width=3, fg_color="transparent", corner_radius=2)
            accent.pack(side="left", fill="y", padx=(0, 6), pady=8)
            btn = ctk.CTkButton(
                row,
                text=f"  {label}",
                command=lambda k=key: self._on_nav(k),
                anchor="w",
                height=40,
                corner_radius=10,
                fg_color="transparent",
                hover_color=COLORS["ghost_hover"],
                text_color=COLORS["text_secondary"],
                font=ctk.CTkFont(family=FONT_UI, size=14),
            )
            btn.pack(side="left", fill="both", expand=True)
            self._nav_btns[key] = btn
            self._nav_accents[key] = accent

        foot = ctk.CTkFrame(
            self,
            fg_color=COLORS["card"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        foot.pack(side="bottom", fill="x", padx=12, pady=14)
        status_row = ctk.CTkFrame(foot, fg_color="transparent")
        status_row.pack(fill="x", padx=14, pady=(12, 2))
        self.status_dot = ctk.CTkLabel(
            status_row, text="●", font=ctk.CTkFont(size=14), text_color=COLORS["muted"], width=18
        )
        self.status_dot.pack(side="left")
        self.status_lbl = ctk.CTkLabel(
            status_row,
            text="Выключено",
            font=ctk.CTkFont(family=FONT_UI_BOLD, size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.status_lbl.pack(side="left", fill="x", expand=True)
        self.session_lbl = ctk.CTkLabel(
            foot,
            text="Сессия: —",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.session_lbl.pack(fill="x", padx=14, pady=0)
        self.server_lbl = ctk.CTkLabel(
            foot,
            text="Сервер: —",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.server_lbl.pack(fill="x", padx=14, pady=(0, 8))
        self.disconnect_btn = danger_btn(
            foot, "Отключить", on_disconnect, width=180, height=34,
            font=ctk.CTkFont(family=FONT_UI_BOLD, size=12),
        )
        self.disconnect_btn.pack(padx=14, pady=(0, 12))
        self.set_active("home")

    def set_active(self, key: str) -> None:
        self._active = key
        for k, btn in self._nav_btns.items():
            active = k == key
            btn.configure(
                fg_color=COLORS["nav_active"] if active else "transparent",
                text_color=COLORS["text"] if active else COLORS["text_secondary"],
            )
            self._nav_accents[k].configure(fg_color=COLORS["primary"] if active else "transparent")
