"""Power button widget — uses the flat power_button.png asset."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.icons import make_power_button_image
from app.ui.theme import POWER_SIZE


class PowerButton(ctk.CTkFrame):
    def __init__(self, master, command: Callable[[], None], *, size: int = POWER_SIZE, **kw):
        super().__init__(master, fg_color="transparent", width=size + 12, height=size + 12, **kw)
        self.pack_propagate(False)
        self._command = command
        self._size = size
        self._on = False
        self._connecting = False
        self._glow = 100
        self._refs: list = []
        self._cache: dict[tuple, ctk.CTkImage] = {}

        self.label = ctk.CTkLabel(self, text="", cursor="hand2")
        self.label.pack(expand=True)
        self.label.bind("<Button-1>", lambda _e: self._command())
        self.label.bind("<Enter>", lambda _e: self._hover(True))
        self.label.bind("<Leave>", lambda _e: self._hover(False))
        self.refresh()

    def _image(self, *, on: bool, glow: int = 100) -> ctk.CTkImage:
        # Flat asset — ignore glow for cache (keeps one image per on/off)
        key = (on, self._size)
        if key not in self._cache:
            pil = make_power_button_image(self._size, on=on, glow=100)
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(self._size, self._size))
            self._cache[key] = img
            self._refs.append(img)
        return self._cache[key]

    def _hover(self, entering: bool) -> None:
        # No glow churn — asset is flat
        return

    def set_state(self, *, on: bool = False, connecting: bool = False, glow: int | None = None) -> None:
        self._on = on
        self._connecting = connecting
        if glow is not None:
            self._glow = glow
        self.label.configure(image=self._image(on=on or connecting))

    def refresh(self) -> None:
        self.set_state(on=self._on, connecting=self._connecting, glow=self._glow)
