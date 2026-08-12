"""Service catalog cards / rows."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.presets import CATEGORY_LABELS, Preset
from app.ui.theme import CARD_RADIUS, COLORS, FONT_UI, FONT_UI_BOLD


class ServiceCard(ctk.CTkFrame):
    """Single-frame card (no nested shadow) to cut widget count and resize artifacts."""

    def __init__(
        self,
        master,
        preset: Preset,
        enabled: bool,
        icon: ctk.CTkImage,
        on_toggle: Callable[[str, bool], None],
    ):
        super().__init__(
            master,
            fg_color=COLORS["card_on"] if enabled else COLORS["card"],
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=COLORS["border_on"] if enabled else COLORS["border"],
        )
        self.preset = preset
        self.on_toggle = on_toggle
        self.var = ctk.BooleanVar(value=enabled)
        self._visible = True
        self._grid_info: dict | None = None
        self._grid_key: tuple | None = None
        self._hover = False

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(top, text="", image=icon, width=44, height=44).pack(side="left")
        titles = ctk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True, padx=(12, 8))
        ctk.CTkLabel(
            titles,
            text=preset.name,
            font=ctk.CTkFont(family=FONT_UI_BOLD, size=15),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text=CATEGORY_LABELS.get(preset.category, preset.category),
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(anchor="w")
        self.switch = ctk.CTkSwitch(
            top,
            text="",
            width=48,
            height=24,
            variable=self.var,
            command=self._changed,
            progress_color=COLORS["primary"],
            button_color="#FFFFFF",
            button_hover_color="#F3F7FC",
            fg_color="#243044",
        )
        self.switch.pack(side="right")
        ctk.CTkLabel(
            self,
            text=preset.description,
            font=ctk.CTkFont(family=FONT_UI, size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=260,
        ).pack(fill="x", padx=16, pady=(0, 14))

        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, _e=None) -> None:
        if self.var.get() or self._hover:
            return
        self._hover = True
        self.configure(fg_color=COLORS["card_hover"], border_color=COLORS["border_hover"])

    def _on_leave(self, _e=None) -> None:
        try:
            x, y = self.winfo_pointerxy()
            wx, wy = self.winfo_rootx(), self.winfo_rooty()
            if wx <= x <= wx + self.winfo_width() and wy <= y <= wy + self.winfo_height():
                return
        except Exception:
            pass
        self._hover = False
        self._style(bool(self.var.get()))

    def _style(self, on: bool) -> None:
        self.configure(
            fg_color=COLORS["card_on"] if on else COLORS["card"],
            border_color=COLORS["border_on"] if on else COLORS["border"],
        )

    def _changed(self) -> None:
        on = bool(self.var.get())
        self._hover = False
        self._style(on)
        self.on_toggle(self.preset.id, on)

    def set_enabled(self, value: bool) -> None:
        self.var.set(value)
        self._style(value)

    def place_grid(self, row: int, column: int, **kw) -> None:
        key = (row, column, kw.get("padx"), kw.get("pady"), kw.get("sticky"))
        self._grid_info = {"row": row, "column": column, **kw}
        if self._visible and self._grid_key == key:
            return
        self._grid_key = key
        self._visible = True
        self.grid(**self._grid_info)

    def set_visible(self, visible: bool) -> None:
        if visible == self._visible and visible:
            return
        if not visible:
            if not self._visible:
                return
            self._visible = False
            self._grid_key = None
            self.grid_remove()
            return
        info = self._grid_info or {"row": 0, "column": 0, "sticky": "nsew", "padx": 6, "pady": 6}
        self._visible = True
        self.grid(**info)


class ServiceRow(ctk.CTkFrame):
    def __init__(
        self,
        master,
        preset: Preset,
        enabled: bool,
        icon: ctk.CTkImage,
        on_toggle: Callable[[str, bool], None],
    ):
        super().__init__(
            master,
            fg_color=COLORS["card_on"] if enabled else COLORS["elevated"],
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=COLORS["border_on"] if enabled else COLORS["border"],
            height=68,
        )
        self.pack_propagate(False)
        self.preset = preset
        self.on_toggle = on_toggle
        self.var = ctk.BooleanVar(value=enabled)
        self._visible = True

        ctk.CTkLabel(self, text="", image=icon, width=40, height=40).pack(
            side="left", padx=(14, 10), pady=10
        )
        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side="left", fill="both", expand=True, pady=10)
        ctk.CTkLabel(
            text,
            text=preset.name,
            font=ctk.CTkFont(family=FONT_UI_BOLD, size=14),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text,
            text=preset.description,
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(anchor="w")
        self.switch = ctk.CTkSwitch(
            self,
            text="",
            width=48,
            height=24,
            variable=self.var,
            command=self._changed,
            progress_color=COLORS["primary"],
            button_color="#FFFFFF",
            button_hover_color="#F3F7FC",
            fg_color="#243044",
        )
        self.switch.pack(side="right", padx=16)

    def _style(self, on: bool) -> None:
        self.configure(
            fg_color=COLORS["card_on"] if on else COLORS["elevated"],
            border_color=COLORS["border_on"] if on else COLORS["border"],
        )

    def _changed(self) -> None:
        on = bool(self.var.get())
        self._style(on)
        self.on_toggle(self.preset.id, on)

    def set_enabled(self, value: bool) -> None:
        self.var.set(value)
        self._style(value)

    def set_visible(self, visible: bool) -> None:
        if visible == self._visible:
            return
        self._visible = visible
        if visible:
            self.pack(fill="x", padx=2, pady=4)
        else:
            self.pack_forget()
