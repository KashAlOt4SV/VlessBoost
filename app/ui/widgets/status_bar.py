"""Bottom status bar."""

from __future__ import annotations

import customtkinter as ctk

from app import __version__
from app.ui.theme import COLORS, FONT_UI


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, height=36, fg_color=COLORS["footer"], corner_radius=0, **kw)
        self.pack_propagate(False)
        self.left = ctk.CTkLabel(
            self,
            text=f"Версия: {__version__}  ·  ● Актуальная версия  ·  Режим: VLESS  ·  Протокол: TCP + TLS",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.left.pack(side="left", padx=18)
        self.ping = ctk.CTkLabel(
            self,
            text="Пинг: —",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="e",
        )
        self.ping.pack(side="right", padx=18)
        self.server = ctk.CTkLabel(
            self,
            text="Сервер: —",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="e",
        )
        self.server.pack(side="right", padx=(0, 8))

    def set_ping(self, text: str, color: str | None = None) -> None:
        self.ping.configure(text=text, text_color=color or COLORS["muted"])

    def set_server(self, text: str) -> None:
        self.server.configure(text=f"Сервер: {text}")
