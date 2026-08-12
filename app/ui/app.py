from __future__ import annotations

import logging
import math
import threading

import customtkinter as ctk
import pystray
from tkinter import messagebox

from app.config_builder import collect_routes
from app.icons import app_ico_path, load_logo, make_preset_icon
from app.list_updater import LIST_CACHE, update_all_remote
from app.netcheck import ping_vless_url
from app.presets import CATEGORY_LABELS, CATALOG, Preset
from app.settings import Settings, load_settings, save_settings
from app.singbox import SingBoxManager, is_admin, relaunch_as_admin
from app.ui.helpers import (
    danger_btn,
    enable_text_clipboard,
    ghost_btn,
    primary_btn,
    tray_icon,
    trim_log_file,
)
from app.ui.perf import perf
from app.ui.theme import COLORS, FONT_UI, FONT_UI_BLACK, FONT_UI_BOLD, FONT_MONO
from app.ui.widgets import PowerButton, ServiceCard, ServiceRow, Sidebar, StatusBar
from app.vless_parser import parse_vless_url

logger = logging.getLogger(__name__)


class BoosterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.settings = load_settings()
        self.manager = SingBoxManager()
        self._busy = False
        self._tray: pystray.Icon | None = None
        self._search_after: str | None = None
        self._status_blink_after: str | None = None
        self._status_blink_bright = True
        self._session_after: str | None = None
        self._session_started_at: float | None = None
        self._last_ping_ms: int | None = None
        self._logo_refs: list = []
        self._icons: dict[str, ctk.CTkImage] = {}
        self._power_images: dict[tuple, ctk.CTkImage] = {}
        self._power_glow = 100
        self._power_anim_after: str | None = None
        self._connect_anim_after: str | None = None
        self._items: dict[str, ServiceCard | ServiceRow] = {}
        self._catalog_built = False
        self._catalog_cols = 0
        self._filter_layout_sig: str | None = None
        self._view_mode = self.settings.view_mode if self.settings.view_mode in {"cards", "list"} else "cards"
        self._home_services_sig: str | None = None
        self._minimizing_to_tray = False
        self._current_page = "home"
        self._resize_after: str | None = None

        trim_log_file()

        self.title("VLESS Boost")
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.configure(fg_color=COLORS["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_unmap)
        self.bind("<Map>", self._on_map)
        self._apply_window_icons()

        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass

        self._build()
        with perf("startup refresh_status"):
            self._refresh_status()
        self.after(20, self._startup_fade_in)
        self.after(600, self._maybe_admin_prompt)
        self.after(900, self._check_orphan_on_startup)

    def _apply_window_icons(self) -> None:
        import tkinter as tk

        from app.icons import LOGO_DIR

        ico = app_ico_path()
        if ico and ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                try:
                    self.iconbitmap(str(ico))
                except Exception:
                    pass
        photos = []
        for name in ("logo_32.png", "logo_48.png", "logo_16.png", "logo_128.png"):
            p = LOGO_DIR / name
            if p.exists():
                try:
                    photos.append(tk.PhotoImage(file=str(p)))
                except Exception:
                    pass
        if photos:
            try:
                self.iconphoto(True, *photos)
            except Exception:
                try:
                    self.iconphoto(True, photos[0])
                except Exception:
                    pass
            self._logo_refs.extend(photos)

    def _icon(self, preset: Preset, size: int = 40) -> ctk.CTkImage:
        key = f"{preset.id}:{size}"
        if key in self._icons:
            return self._icons[key]
        pil = make_preset_icon(preset.id, preset.color, size)
        img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
        self._icons[key] = img
        return img

    def _build(self) -> None:
        root = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        root.pack(fill="both", expand=True)

        body = ctk.CTkFrame(root, fg_color=COLORS["bg"], corner_radius=0)
        body.pack(fill="both", expand=True)

        self.sidebar = Sidebar(
            body,
            on_nav=self._show_page,
            on_disconnect=self._stop,
            logo_refs=self._logo_refs,
        )
        self.sidebar.pack(side="left", fill="y")
        # Compat aliases for existing handlers
        self.status_dot = self.sidebar.status_dot
        self.status_lbl = self.sidebar.status_lbl
        self.side_session_lbl = self.sidebar.session_lbl
        self.side_server_lbl = self.sidebar.server_lbl
        self.side_disconnect_btn = self.sidebar.disconnect_btn

        right = ctk.CTkFrame(body, fg_color=COLORS["bg"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self.main = ctk.CTkFrame(right, fg_color=COLORS["bg"], corner_radius=0)
        self.main.pack(fill="both", expand=True)

        self.status_bar = StatusBar(right)
        self.status_bar.pack(fill="x", side="bottom")
        self.footer_ping_lbl = self.status_bar.ping
        self.footer_lbl = self.status_bar.left

        self.page_home = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_boost = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_settings = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_lists = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_logs = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_update = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_support = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_about = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)

        self._build_home_page()
        self._build_boost_page()
        self._build_settings_page()
        self._build_lists_page()
        self._build_logs_page()
        self._build_update_page()
        self._build_support_page()
        self._build_about_page()
        self._show_page("home")
        self._refresh_server_labels()
        self.bind("<Configure>", self._on_window_configure)

    def _on_window_configure(self, event) -> None:
        if event.widget is not self:
            return
        # Resize must never refetch data — only maybe reflow visible catalog columns.
        if self._current_page != "boost" or self._view_mode != "cards" or not self._catalog_built:
            return
        cols = self._catalog_columns()
        if cols == self._catalog_cols:
            return
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.after(180, self._relayout_catalog_columns)

    def _catalog_columns(self) -> int:
        try:
            w = self.winfo_width()
        except Exception:
            w = 1280
        if w >= 1400:
            return 3
        if w >= 1050:
            return 2
        return 1

    def _relayout_catalog_columns(self) -> None:
        self._resize_after = None
        if self._current_page != "boost" or self._view_mode != "cards" or not self._items:
            return
        cols = self._catalog_columns()
        if cols == self._catalog_cols:
            return
        with perf("catalog column relayout"):
            self._apply_filter()

    def _show_page(self, name: str) -> None:
        with perf(f"ListsPage.open" if name == "lists" else f"page.open:{name}"):
            pages = {
                "home": self.page_home,
                "boost": self.page_boost,
                "settings": self.page_settings,
                "lists": self.page_lists,
                "logs": self.page_logs,
                "update": self.page_update,
                "support": self.page_support,
                "about": self.page_about,
            }
            if name == self._current_page and pages[name].winfo_ismapped():
                if name == "lists":
                    self._paint_lists_status(force=False)
                elif name == "home":
                    self._refresh_home_services()
                return
            for p in pages.values():
                p.pack_forget()
            pages[name].pack(fill="both", expand=True, padx=24, pady=18)
            self._current_page = name
            if hasattr(self, "sidebar"):
                self.sidebar.set_active(name)
            if name == "boost":
                self._ensure_catalog()
            if name == "lists":
                self._paint_lists_status(force=False)
            if name == "logs":
                self._refresh_logs()
            if name == "home":
                self._refresh_home_services()

    def _build_home_page(self) -> None:
        page = self.page_home
        hero = ctk.CTkFrame(
            page,
            fg_color=COLORS["panel"],
            corner_radius=22,
            border_width=1,
            border_color=COLORS["border"],
        )
        hero.pack(fill="x", pady=(0, 14))

        top = ctk.CTkFrame(hero, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(18, 8))
        ctk.CTkLabel(
            top,
            text="Главная",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
            text_color=COLORS["muted"],
        ).pack(side="left")
        self.home_off_btn = danger_btn(
            top, "Выключить", self._stop, width=120, height=36
        )
        self.home_off_btn.pack(side="right")

        center = ctk.CTkFrame(hero, fg_color="transparent")
        center.pack(fill="x", padx=22, pady=(4, 22))

        power_wrap = ctk.CTkFrame(center, fg_color="transparent", width=180, height=180)
        power_wrap.pack(side="left", padx=(4, 24))
        power_wrap.pack_propagate(False)
        self.power_btn = PowerButton(power_wrap, command=self._toggle_boost)
        self.power_btn.pack(expand=True)

        info = ctk.CTkFrame(center, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)
        self.home_title_lbl = ctk.CTkLabel(
            info,
            text="Вы не подключены",
            font=ctk.CTkFont(family="Segoe UI Black", size=28),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.home_title_lbl.pack(anchor="w", pady=(18, 4))
        self.home_sub_lbl = ctk.CTkLabel(
            info,
            text="Нажмите кнопку питания, чтобы ускорить выбранные сервисы.",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self.home_sub_lbl.pack(anchor="w")

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.pack(anchor="w", pady=(16, 0))
        self.home_ping_chip = ctk.CTkLabel(
            meta,
            text="Пинг: —",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["ok"],
            fg_color=COLORS["elevated"],
            corner_radius=10,
            padx=12,
            pady=6,
        )
        self.home_ping_chip.pack(side="left", padx=(0, 8))
        self.home_server_chip = ctk.CTkLabel(
            meta,
            text="Сервер: —",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"],
            fg_color=COLORS["elevated"],
            corner_radius=10,
            padx=12,
            pady=6,
        )
        self.home_server_chip.pack(side="left")

        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 12))
        self.stat_session = self._stat_card(stats, "Время сессии", "—")
        self.stat_session.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.stat_ping = self._stat_card(stats, "Пинг", "—")
        self.stat_ping.pack(side="left", fill="x", expand=True, padx=6)
        self.stat_protocol = self._stat_card(stats, "Протокол", "VLESS / TCP+TLS")
        self.stat_protocol.pack(side="left", fill="x", expand=True, padx=6)
        self.stat_enabled = self._stat_card(stats, "Активные сервисы", "0")
        self.stat_enabled.pack(side="left", fill="x", expand=True, padx=(6, 0))
        # Traffic not available in backend — keep placeholder only
        self.stat_traffic = None

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(
            head,
            text="Активные сервисы",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=16),
            text_color=COLORS["text"],
        ).pack(side="left")
        ghost_btn(head, "Все", lambda: self._show_page("boost"), width=72, height=30).pack(
            side="right"
        )

        self.home_services = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent_dim"],
        )
        self.home_services.pack(fill="both", expand=True)
        self._refresh_home_services()

    def _stat_card(self, parent, title: str, value: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 0))
        val = ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(family="Segoe UI Black", size=22),
            text_color=COLORS["text"],
            anchor="w",
        )
        val.pack(fill="x", padx=16, pady=(2, 14))
        card._value_lbl = val  # type: ignore[attr-defined]
        return card

    def _refresh_home_services(self) -> None:
        if not hasattr(self, "home_services"):
            return
        enabled = [p for p in CATALOG if self.settings.is_enabled(p.id)]
        sig = ",".join(p.id for p in enabled[:12])
        if hasattr(self, "stat_enabled"):
            self.stat_enabled._value_lbl.configure(text=str(len(enabled)))  # type: ignore[attr-defined]
        if sig == self._home_services_sig and self.home_services.winfo_children():
            return
        self._home_services_sig = sig
        for child in self.home_services.winfo_children():
            child.destroy()
        if not enabled:
            ctk.CTkLabel(
                self.home_services,
                text="Нет включённых сервисов — откройте «Сервисы».",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=13),
            ).pack(anchor="w", pady=8)
            return
        for preset in enabled[:12]:
            row = ctk.CTkFrame(
                self.home_services,
                fg_color=COLORS["card"],
                corner_radius=12,
                border_width=1,
                border_color=COLORS["border"],
            )
            row.pack(fill="x", pady=4)
            try:
                icon = self._icon(preset, 28)
                ctk.CTkLabel(row, text="", image=icon, width=36).pack(
                    side="left", padx=(12, 8), pady=10
                )
            except Exception:
                pass
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                box,
                text=preset.name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text"],
                anchor="w",
            ).pack(anchor="w")
            cat = CATEGORY_LABELS.get(preset.category, preset.category)
            ctk.CTkLabel(
                box,
                text=cat,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["muted"],
                anchor="w",
            ).pack(anchor="w")
            sw = ctk.CTkSwitch(
                row,
                text="",
                width=42,
                command=lambda pid=preset.id: self._toggle_preset_from_home(pid),
                progress_color=COLORS["accent"],
            )
            sw.select()
            sw.pack(side="right", padx=14)

    def _toggle_preset_from_home(self, preset_id: str) -> None:
        self.settings.set_enabled(preset_id, False)
        save_settings(self.settings)
        self._home_services_sig = None
        item = self._items.get(preset_id)
        if item is not None:
            item.set_enabled(False)
        self._update_summary()
        self._refresh_home_services()

    def _build_support_page(self) -> None:
        page = self.page_support
        ctk.CTkLabel(
            page,
            text="Поддержка",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            page,
            text="Если что-то не работает — откройте «Логи», скопируйте хвост и напишите в Issues на GitHub.",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            wraplength=720,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(8, 16))
        ghost_btn(
            page,
            "Открыть GitHub",
            lambda: __import__("webbrowser").open(
                "https://github.com/KashAlOt4SV/VlessBoost/issues"
            ),
            width=180,
            height=40,
        ).pack(anchor="w")

    def _build_about_page(self) -> None:
        from app import __version__

        page = self.page_about
        ctk.CTkLabel(
            page,
            text="О приложении",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            page,
            text=(
                f"VLESS Boost {__version__}\n"
                "Ускоряет выбранные сайты и программы через ваш VLESS,\n"
                "остальной трафик идёт напрямую.\n\n"
                "Настройки и ссылка VPN хранятся в:\n"
                "%LOCALAPPDATA%\\VLESS-Boost\\"
            ),
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(10, 0))

    def _refresh_server_labels(self) -> None:
        host = "—"
        raw = (self.settings.vless_url or "").strip()
        if raw:
            try:
                ep = parse_vless_url(raw)
                host = f"{ep.server}:{ep.port}"
            except Exception:
                host = "ссылка сохранена"
        if hasattr(self, "side_server_lbl"):
            self.side_server_lbl.configure(text=f"Сервер: {host}")
        if hasattr(self, "home_server_chip"):
            self.home_server_chip.configure(text=host)
        if hasattr(self, "status_bar"):
            self.status_bar.set_server(host)

    def _build_boost_page(self) -> None:
        page = self.page_boost

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            left,
            text="Сервисы",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="Включите нужные сервисы — они пойдут через ваш VPN. Остальной интернет без изменений.",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(4, 0))

        self.boost_btn = primary_btn(
            header,
            "Включить",
            self._toggle_boost,
            width=160,
            height=50,
            font=ctk.CTkFont(family="Segoe UI Black", size=16),
        )
        self.boost_btn.pack(side="right")

        conn_bar = ctk.CTkFrame(page, fg_color=COLORS["panel"], corner_radius=14)
        conn_bar.pack(fill="x", pady=(0, 10))
        conn_inner = ctk.CTkFrame(conn_bar, fg_color="transparent")
        conn_inner.pack(fill="x", padx=14, pady=10)
        self.ping_lbl = ctk.CTkLabel(
            conn_inner,
            text="Пинг: —",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.ping_lbl.pack(side="left")
        ghost_btn(conn_inner, "Пинг сервера", self._ping_server, width=130, height=36).pack(
            side="right", padx=(8, 0)
        )
        ghost_btn(
            conn_inner,
            "Проверить соединение",
            self._check_active_connection,
            width=180,
            height=36,
        ).pack(side="right")

        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))

        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            toolbar,
            placeholder_text="Поиск сервиса…",
            textvariable=self.search_var,
            width=250,
            height=40,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
        )
        search.pack(side="left")
        search.bind("<KeyRelease>", self._on_search_typed)
        enable_text_clipboard(search)

        self.cat_var = ctk.StringVar(value="Все")
        ctk.CTkOptionMenu(
            toolbar,
            values=["Все"] + list(CATEGORY_LABELS.values()),
            variable=self.cat_var,
            command=lambda _: self._apply_filter(),
            width=160,
            height=40,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            button_color=COLORS["ghost"],
            button_hover_color=COLORS["ghost_hover"],
            dropdown_fg_color=COLORS["panel"],
            dropdown_hover_color=COLORS["ghost_hover"],
            text_color=COLORS["text"],
        ).pack(side="left", padx=8)

        ghost_btn(toolbar, "Популярное", self._enable_popular, width=120, height=40).pack(
            side="left"
        )
        ghost_btn(toolbar, "Сбросить", self._disable_all, width=100, height=40).pack(
            side="left", padx=6
        )

        view_box = ctk.CTkFrame(
            toolbar,
            fg_color=COLORS["elevated"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        view_box.pack(side="right", padx=(8, 0))
        self.view_cards_btn = ctk.CTkButton(
            view_box,
            text="Карточки",
            width=96,
            height=34,
            corner_radius=10,
            command=lambda: self._set_view("cards"),
            font=ctk.CTkFont(size=12),
        )
        self.view_cards_btn.pack(side="left", padx=3, pady=3)
        self.view_list_btn = ctk.CTkButton(
            view_box,
            text="Список",
            width=88,
            height=34,
            corner_radius=10,
            command=lambda: self._set_view("list"),
            font=ctk.CTkFont(size=12),
        )
        self.view_list_btn.pack(side="left", padx=(0, 3), pady=3)

        self.summary_lbl = ctk.CTkLabel(
            toolbar, text="", font=ctk.CTkFont(size=12), text_color=COLORS["muted"]
        )
        self.summary_lbl.pack(side="right", padx=(0, 10))

        self.catalog_host = ctk.CTkScrollableFrame(
            page,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent_dim"],
        )
        self.catalog_host.pack(fill="both", expand=True)

        # Defer heavy card creation until first open of «Сервисы»
        self._sync_view_buttons()
        self._update_summary()

    def _sync_view_buttons(self) -> None:
        cards = self._view_mode == "cards"
        self.view_cards_btn.configure(
            fg_color=COLORS["accent"] if cards else "transparent",
            hover_color=COLORS["accent_hover"] if cards else COLORS["ghost_hover"],
            text_color="#061018" if cards else COLORS["text"],
        )
        self.view_list_btn.configure(
            fg_color=COLORS["accent"] if not cards else "transparent",
            hover_color=COLORS["accent_hover"] if not cards else COLORS["ghost_hover"],
            text_color="#061018" if not cards else COLORS["text"],
        )

    def _set_view(self, mode: str) -> None:
        if mode not in {"cards", "list"} or mode == self._view_mode:
            self._sync_view_buttons()
            return
        self._view_mode = mode
        self.settings.view_mode = mode
        save_settings(self.settings)
        self._sync_view_buttons()
        self._catalog_built = False
        self._ensure_catalog(force=True)

    def _clear_catalog(self) -> None:
        for child in self.catalog_host.winfo_children():
            child.destroy()
        self._items.clear()
        self._catalog_built = False
        self._catalog_cols = 0
        self._filter_layout_sig = None

    def _ensure_catalog(self, *, force: bool = False) -> None:
        if self._catalog_built and self._items and not force:
            return
        with perf("Cards creation"):
            self._render_catalog()

    def _render_catalog(self) -> None:
        self._clear_catalog()
        q = (self.search_var.get() or "").strip().lower() if hasattr(self, "search_var") else ""
        cat_label = self.cat_var.get() if hasattr(self, "cat_var") else "Все"
        cat_id = None
        if cat_label != "Все":
            for k, v in CATEGORY_LABELS.items():
                if v == cat_label:
                    cat_id = k
                    break

        if self._view_mode == "cards":
            cols = max(1, self._catalog_columns())
            self.catalog_host.grid_columnconfigure(tuple(range(max(cols, 3))), weight=1)
            row = col = 0
            for preset in CATALOG:
                card = ServiceCard(
                    self.catalog_host,
                    preset,
                    enabled=self.settings.is_enabled(preset.id),
                    icon=self._icon(preset, 44),
                    on_toggle=self._on_toggle,
                )
                self._items[preset.id] = card
                visible = True
                if cat_id and preset.category != cat_id:
                    visible = False
                if visible and q:
                    hay = f"{preset.name} {preset.description} {preset.id}".lower()
                    visible = q in hay
                if visible:
                    card.place_grid(row, col, sticky="nsew", padx=6, pady=6)
                    col += 1
                    if col >= cols:
                        col = 0
                        row += 1
                else:
                    card.set_visible(False)
            self._catalog_cols = cols
        else:
            for preset in CATALOG:
                row_w = ServiceRow(
                    self.catalog_host,
                    preset,
                    enabled=self.settings.is_enabled(preset.id),
                    icon=self._icon(preset, 40),
                    on_toggle=self._on_toggle,
                )
                self._items[preset.id] = row_w
                visible = True
                if cat_id and preset.category != cat_id:
                    visible = False
                if visible and q:
                    hay = f"{preset.name} {preset.description} {preset.id}".lower()
                    visible = q in hay
                if visible:
                    row_w.pack(fill="x", padx=2, pady=4)
                    row_w._visible = True
                else:
                    row_w.set_visible(False)
            self._catalog_cols = 1

        self._filter_layout_sig = self._compute_filter_sig()
        self._catalog_built = True

    def _compute_filter_sig(self) -> str:
        q = (self.search_var.get() or "").strip().lower() if hasattr(self, "search_var") else ""
        cat = self.cat_var.get() if hasattr(self, "cat_var") else "Все"
        cols = self._catalog_columns() if self._view_mode == "cards" else 1
        return f"{self._view_mode}|{cols}|{cat}|{q}"

    def _on_search_typed(self, _event=None) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(140, self._apply_filter)

    def _reset_catalog_scroll(self) -> None:
        try:
            canvas = getattr(self.catalog_host, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0)
        except Exception:
            pass

    def _apply_filter(self) -> None:
        if not self._items:
            return
        sig = self._compute_filter_sig()
        if sig == self._filter_layout_sig:
            return

        q = (self.search_var.get() or "").strip().lower()
        cat_label = self.cat_var.get()
        cat_id = None
        if cat_label != "Все":
            for k, v in CATEGORY_LABELS.items():
                if v == cat_label:
                    cat_id = k
                    break

        visible: list[ServiceCard | ServiceRow] = []
        for preset in CATALOG:
            item = self._items.get(preset.id)
            if not item:
                continue
            ok = True
            if cat_id and preset.category != cat_id:
                ok = False
            if ok and q:
                hay = f"{preset.name} {preset.description} {preset.id}".lower()
                ok = q in hay
            if ok:
                visible.append(item)
            else:
                item.set_visible(False)

        if self._view_mode == "cards":
            cols = max(1, self._catalog_columns())
            try:
                self.catalog_host.grid_columnconfigure(tuple(range(cols)), weight=1)
            except Exception:
                pass
            row = col = 0
            for item in visible:
                assert isinstance(item, ServiceCard)
                item.place_grid(row, col, sticky="nsew", padx=6, pady=6)
                col += 1
                if col >= cols:
                    col = 0
                    row += 1
            self._catalog_cols = cols
        else:
            for item in visible:
                assert isinstance(item, ServiceRow)
                item.set_visible(True)

        self._filter_layout_sig = sig
        self._reset_catalog_scroll()

    def _on_toggle(self, preset_id: str, value: bool) -> None:
        self.settings.set_enabled(preset_id, value)
        save_settings(self.settings)
        self._home_services_sig = None
        self._update_summary()
        self._refresh_home_services()

    def _update_summary(self) -> None:
        enabled = sum(1 for p in CATALOG if self.settings.is_enabled(p.id))
        try:
            procs, doms, ips = collect_routes(self.settings)
            self.summary_lbl.configure(text=f"Выбрано: {enabled} · {len(doms)} сайтов")
        except Exception:
            self.summary_lbl.configure(text=f"Выбрано: {enabled}")

    def _enable_popular(self) -> None:
        for p in CATALOG:
            if p.popular and p.id not in {"browsers", "antifilter-community"}:
                self.settings.set_enabled(p.id, True)
                if p.id in self._items:
                    self._items[p.id].set_enabled(True)
        save_settings(self.settings)
        self._update_summary()

    def _disable_all(self) -> None:
        for p in CATALOG:
            self.settings.set_enabled(p.id, False)
            if p.id in self._items:
                self._items[p.id].set_enabled(False)
        save_settings(self.settings)
        self._update_summary()

    def _build_settings_page(self) -> None:
        page = self.page_settings
        ctk.CTkLabel(
            page,
            text="Настройки",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            page,
            text="Подключение VPN и дополнительные правила",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 14))

        box = ctk.CTkScrollableFrame(
            page,
            fg_color=COLORS["panel"],
            corner_radius=18,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent_dim"],
        )
        box.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=18)

        ctk.CTkLabel(
            inner,
            text="Ссылка на VPN",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text="Вставьте ссылку, которую вы получили от провайдера VPN",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(2, 6))
        self.vless_box = ctk.CTkTextbox(
            inner,
            height=96,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
        )
        self.vless_box.pack(fill="x", pady=(0, 8))
        self.vless_box.insert("1.0", self.settings.vless_url)
        enable_text_clipboard(self.vless_box)

        ping_row = ctk.CTkFrame(inner, fg_color="transparent")
        ping_row.pack(fill="x", pady=(0, 14))
        self.settings_ping_lbl = ctk.CTkLabel(
            ping_row,
            text="Пинг до сервера: —",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.settings_ping_lbl.pack(side="left")
        ghost_btn(ping_row, "Измерить пинг", self._ping_server, width=140, height=34).pack(
            side="right"
        )

        self.var_proc = ctk.BooleanVar(value=self.settings.route_processes)
        self.var_dom = ctk.BooleanVar(value=self.settings.route_domains)
        self.var_ip = ctk.BooleanVar(value=self.settings.route_ips)
        self.var_protect = ctk.BooleanVar(value=getattr(self.settings, "protect_direct", True))

        for text, var in (
            ("Ускорять программы целиком (по имени файла)", self.var_proc),
            ("Ускорять по адресам сайтов", self.var_dom),
            ("Ускорять по спискам IP-адресов", self.var_ip),
            ("Не трогать рабочие сервисы (почта, офис, видеозвонки)", self.var_protect),
        ):
            ctk.CTkCheckBox(
                inner,
                text=text,
                variable=var,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                checkmark_color="#061018",
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=13),
                corner_radius=6,
            ).pack(anchor="w", pady=5)

        ctk.CTkLabel(
            inner,
            text="Свои сайты",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(16, 2))
        ctk.CTkLabel(
            inner,
            text="По одному адресу на строку, например youtube.com",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 6))
        self.custom_domains = ctk.CTkTextbox(
            inner,
            height=90,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.custom_domains.pack(fill="x")
        self.custom_domains.insert("1.0", "\n".join(self.settings.custom_domains))
        enable_text_clipboard(self.custom_domains)

        ctk.CTkLabel(
            inner,
            text="Свои программы",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(14, 2))
        ctk.CTkLabel(
            inner,
            text="По одному имени файла на строку, например Discord.exe",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 6))
        self.custom_procs = ctk.CTkTextbox(
            inner,
            height=70,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.custom_procs.pack(fill="x")
        self.custom_procs.insert("1.0", "\n".join(self.settings.custom_processes))
        enable_text_clipboard(self.custom_procs)

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x", pady=(18, 0))
        ghost_btn(btns, "Проверить ссылку", self._validate_vless, width=150, height=42).pack(
            side="left"
        )
        ghost_btn(
            btns,
            "Проверить соединение",
            self._check_active_connection,
            width=180,
            height=42,
        ).pack(side="left", padx=8)
        primary_btn(btns, "Сохранить", self._save_settings_ui, width=140, height=42).pack(
            side="right"
        )

    def _vless_raw(self) -> str:
        if hasattr(self, "vless_box"):
            raw = self.vless_box.get("1.0", "end").strip()
            if raw:
                return raw
        return (self.settings.vless_url or "").strip()

    def _ping_server(self) -> None:
        raw = self._vless_raw()
        if not raw:
            messagebox.showwarning(
                "Нет ссылки",
                "Сначала вставьте vless:// ссылку в настройках.",
                parent=self,
            )
            return
        self._set_ping_text("Пинг: измеряю…", COLORS["muted"])

        def work() -> None:
            try:
                result = ping_vless_url(raw)
                if result.ok and result.ms is not None:
                    text = f"Пинг: ~{result.ms:.0f} мс  ({result.host}:{result.port})"
                    color = COLORS["ok"] if result.ms < 200 else (
                        COLORS["accent"] if result.ms < 400 else COLORS["danger"]
                    )
                else:
                    text = f"Пинг: нет ответа ({result.error or 'ошибка'}) — {result.host}:{result.port}"
                    color = COLORS["danger"]
                self.after(0, lambda: self._set_ping_text(text, color))
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._set_ping_text(f"Пинг: ошибка — {exc}", COLORS["danger"]),
                )

        threading.Thread(target=work, daemon=True).start()

    def _set_ping_text(self, text: str, color: str) -> None:
        if hasattr(self, "ping_lbl"):
            self.ping_lbl.configure(text=text, text_color=color)
        if hasattr(self, "footer_ping_lbl"):
            self.footer_ping_lbl.configure(text=text, text_color=color)
        if hasattr(self, "home_ping_chip"):
            self.home_ping_chip.configure(text=text, text_color=color)
        if hasattr(self, "stat_ping"):
            # Strip "Пинг: " prefix for compact card
            short = text
            if short.startswith("Пинг:"):
                short = short[len("Пинг:") :].strip()
            self.stat_ping._value_lbl.configure(text=short or "—", text_color=color)  # type: ignore[attr-defined]
        if hasattr(self, "status_bar"):
            self.status_bar.set_ping(text, color)
        if hasattr(self, "settings_ping_lbl"):
            pretty = text if text.startswith("Пинг") else text
            if pretty.startswith("Пинг:"):
                pretty = "Пинг до сервера:" + pretty[len("Пинг:") :]
            self.settings_ping_lbl.configure(text=pretty, text_color=color)

    def _session_text(self) -> str:
        import time

        if not self._session_started_at:
            return "—"
        elapsed = max(0, int(time.time() - self._session_started_at))
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _tick_session(self) -> None:
        self._session_after = None
        if not self.manager.running:
            return
        text = self._session_text()
        if hasattr(self, "side_session_lbl"):
            self.side_session_lbl.configure(text=f"Сессия: {text}")
        if hasattr(self, "stat_session"):
            self.stat_session._value_lbl.configure(text=text)  # type: ignore[attr-defined]
        self._session_after = self.after(1000, self._tick_session)

    def _start_session_timer(self) -> None:
        import time

        if self._session_started_at is None:
            self._session_started_at = time.time()
        if self._session_after is None:
            self._tick_session()

    def _stop_session_timer(self) -> None:
        if self._session_after is not None:
            try:
                self.after_cancel(self._session_after)
            except Exception:
                pass
            self._session_after = None
        self._session_started_at = None
        if hasattr(self, "side_session_lbl"):
            self.side_session_lbl.configure(text="Сессия: —")
        if hasattr(self, "stat_session"):
            self.stat_session._value_lbl.configure(text="—")  # type: ignore[attr-defined]

    def _check_orphan_on_startup(self) -> None:
        def work() -> None:
            try:
                external = self.manager.external_instances()
            except Exception:
                return
            if not external or self.manager.running:
                return
            self.after(0, lambda: self._prompt_orphan(external))

        threading.Thread(target=work, daemon=True).start()

    def _prompt_orphan(self, external: list[tuple[int, str]]) -> None:
        if self.manager.running or not external:
            return
        self._stop_status_blink()
        pids = ", ".join(str(p) for p, _ in external)
        if hasattr(self, "status_dot"):
            self.status_dot.configure(text_color=COLORS["accent"])
        self.status_lbl.configure(
            text=f"Зависший sing-box (pid {pids})",
            text_color=COLORS["accent"],
        )
        if messagebox.askyesno(
            "Найдено активное соединение",
            "Обнаружен работающий sing-box от прошлого запуска.\n"
            f"PID: {pids}\n\n"
            "Остановить его сейчас?",
            parent=self,
        ):
            try:
                killed = self.manager.kill_external()
                messagebox.showinfo(
                    "Готово",
                    f"Остановлено процессов: {len(killed)}",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
            self._refresh_status()

    def _check_active_connection(self) -> None:
        def work() -> None:
            try:
                managed = self.manager.running
                external = self.manager.external_instances()
                self.after(0, lambda: self._show_connection_check(managed, external))
            except Exception as exc:
                self.after(
                    0,
                    lambda: messagebox.showerror("Проверка", str(exc), parent=self),
                )

        threading.Thread(target=work, daemon=True).start()

    def _show_connection_check(
        self,
        managed: bool,
        external: list[tuple[int, str]],
    ) -> None:
        if managed and self.manager.managed_pid():
            messagebox.showinfo(
                "Соединение",
                f"Ускорение активно в этом приложении.\n"
                f"PID sing-box: {self.manager.managed_pid()}",
                parent=self,
            )
            return
        if external:
            pids = ", ".join(str(p) for p, _ in external)
            if messagebox.askyesno(
                "Зависшее соединение",
                "sing-box всё ещё работает, хотя приложение его не контролирует.\n"
                f"PID: {pids}\n\n"
                "Убить процесс и подключить заново?",
                parent=self,
            ):
                try:
                    self.manager.kill_external()
                except Exception as exc:
                    messagebox.showerror("Ошибка", str(exc), parent=self)
                    return
                self._refresh_status()
                if messagebox.askyesno(
                    "Подключить",
                    "Старый процесс остановлен.\nВключить ускорение сейчас?",
                    parent=self,
                ):
                    self._start()
            else:
                self._refresh_status()
            return
        messagebox.showinfo(
            "Соединение",
            "Активного sing-box не найдено. Можно включать ускорение.",
            parent=self,
        )
        self._refresh_status()

    def _validate_vless(self) -> None:
        raw = self.vless_box.get("1.0", "end").strip()
        try:
            ep = parse_vless_url(raw)
            messagebox.showinfo(
                "Ссылка подходит",
                f"Сервер: {ep.server}\nПорт: {ep.port}\nИмя: {ep.name}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Не удалось прочитать ссылку", str(exc), parent=self)

    def _save_settings_ui(self) -> None:
        raw = self.vless_box.get("1.0", "end").strip()
        if raw:
            try:
                parse_vless_url(raw)
            except Exception as exc:
                messagebox.showerror("Ссылка VPN", str(exc), parent=self)
                return
        self.settings.vless_url = raw
        self.settings.route_processes = bool(self.var_proc.get())
        self.settings.route_domains = bool(self.var_dom.get())
        self.settings.route_ips = bool(self.var_ip.get())
        self.settings.protect_direct = bool(self.var_protect.get())
        self.settings.view_mode = self._view_mode
        self.settings.custom_domains = [
            ln.strip() for ln in self.custom_domains.get("1.0", "end").splitlines() if ln.strip()
        ]
        self.settings.custom_processes = [
            ln.strip() for ln in self.custom_procs.get("1.0", "end").splitlines() if ln.strip()
        ]
        if self.settings.custom_domains or self.settings.custom_processes:
            self.settings.set_enabled("custom", True)
        save_settings(self.settings)
        self._update_summary()
        self._refresh_server_labels()
        self._refresh_home_services()
        messagebox.showinfo("Готово", "Настройки сохранены", parent=self)

    def _build_lists_page(self) -> None:
        page = self.page_lists
        ctk.CTkLabel(
            page,
            text="Обновление списков",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            page,
            text="Скачайте свежие адреса сайтов для более точной работы ускорения",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(4, 14))

        box = ctk.CTkFrame(page, fg_color=COLORS["panel"], corner_radius=18)
        box.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        primary_btn(
            inner,
            "Обновить все списки",
            self._update_lists,
            width=220,
            height=44,
        ).pack(anchor="w")
        ghost_btn(
            inner,
            "Только общий список блокировок",
            lambda: self._update_lists(["antifilter-community"]),
            width=260,
            height=40,
        ).pack(anchor="w", pady=10)

        self.lists_log = ctk.CTkTextbox(
            inner,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.lists_log.pack(fill="both", expand=True, pady=(8, 0))
        enable_text_clipboard(self.lists_log)
        self._paint_lists_status(force=True)

    def _paint_lists_status(self, *, force: bool = False) -> None:
        """Show cached list status instantly — never network on page open."""
        if not hasattr(self, "lists_log"):
            return
        with perf("lists status (cache)"):
            lines = LIST_CACHE.status_lines()
        header = (
            "Статус локального кеша списков (без сети).\n"
            "Нажмите «Обновить», чтобы скачать свежие данные в фоне.\n"
            "Общий список блокировок большой — включайте его только если нужно.\n"
            "\n"
        )
        body = "\n".join(lines) if lines else "Кеш пуст — обновите списки."
        text = header + body + "\n"
        if not force:
            try:
                current = self.lists_log.get("1.0", "end-1c")
                if current == text:
                    return
            except Exception:
                pass
        self.lists_log.delete("1.0", "end")
        self.lists_log.insert("1.0", text)

    def _update_lists(self, only: list[str] | None = None) -> None:
        if self._busy:
            return
        self._busy = True
        LIST_CACHE.invalidate()
        self.lists_log.insert("end", "\nОбновление в фоне…\n")

        def work() -> None:
            try:
                with perf("Lists API"):
                    results = update_all_remote(only)
                lines = []
                for pid, stats in results.items():
                    if "error" in stats:
                        lines.append(f"✗ {pid}: {stats['error']}")
                    else:
                        lines.append(
                            f"✓ {pid}: сайтов {stats.get('domains', 0)}, IP {stats.get('ips', 0)}"
                        )
                msg = "\n".join(lines) or "Нечего обновлять"
                self.after(0, lambda: self._lists_done(msg))
            except Exception as exc:
                err = str(exc) or repr(exc)
                self.after(0, lambda m=err: self._lists_done(f"Ошибка: {m}"))

        threading.Thread(target=work, daemon=True).start()

    def _lists_done(self, msg: str) -> None:
        self._busy = False
        self._paint_lists_status(force=True)
        self.lists_log.insert("end", "\nРезультат обновления:\n" + msg + "\n")
        self.lists_log.see("end")
        self._update_summary()

    def _build_logs_page(self) -> None:
        page = self.page_logs
        ctk.CTkLabel(
            page,
            text="Логи",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            page,
            text="Журнал приложения и sing-box — удобно смотреть, почему падает соединение",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(4, 14))

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        primary_btn(row, "Обновить", self._refresh_logs, width=140, height=40).pack(side="left")
        danger_btn(row, "Удалить логи", self._clear_logs, width=150, height=40).pack(
            side="left", padx=10
        )
        ghost_btn(row, "Открыть папку", self._open_log_folder, width=160, height=40).pack(
            side="left"
        )
        ctk.CTkLabel(
            row,
            text="Автоочистка: хвост ~2500 строк",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
        ).pack(side="right")

        self.app_logs = ctk.CTkTextbox(
            page,
            corner_radius=14,
            fg_color=COLORS["card"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.app_logs.pack(fill="both", expand=True)
        enable_text_clipboard(self.app_logs)

    def _refresh_logs(self) -> None:
        from app.paths import LOG_PATH

        if not hasattr(self, "app_logs"):
            return
        trim_log_file()
        self.app_logs.delete("1.0", "end")
        try:
            if LOG_PATH.exists():
                text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                text = "\n".join(lines[-800:])
                self.app_logs.insert("1.0", text or "(пусто)")
            else:
                self.app_logs.insert("1.0", f"Файл ещё не создан:\n{LOG_PATH}")
        except Exception as exc:
            self.app_logs.insert("1.0", f"Не удалось прочитать лог: {exc}")
        self.app_logs.see("end")

    def _clear_logs(self) -> None:
        from app.paths import LOG_PATH

        if not messagebox.askyesno(
            "Удалить логи",
            "Очистить журнал приложения?\nФайл app.log будет опустошён.",
            parent=self,
        ):
            return
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.write_text("", encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Логи", str(exc), parent=self)
            return
        self._refresh_logs()
        messagebox.showinfo("Готово", "Логи очищены.", parent=self)

    def _open_log_folder(self) -> None:
        from app.paths import CONFIG_DIR
        import os

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(CONFIG_DIR))

    def _build_update_page(self) -> None:
        from app import __version__

        page = self.page_update
        ctk.CTkLabel(
            page,
            text="Обновление приложения",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=26),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            page,
            text=f"Текущая версия: {__version__}",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(4, 14))

        box = ctk.CTkFrame(page, fg_color=COLORS["panel"], corner_radius=18)
        box.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        primary_btn(
            inner,
            "Проверить обновления",
            self._check_app_update,
            width=220,
            height=44,
        ).pack(anchor="w")
        self.update_log = ctk.CTkTextbox(
            inner,
            corner_radius=12,
            fg_color=COLORS["elevated"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=220,
        )
        self.update_log.pack(fill="both", expand=True, pady=(12, 0))
        self.update_log.insert(
            "1.0",
            "Проверка идёт по version.json в интернете.\n"
            "Если найдётся новая версия — скачается exe и предложит установить.\n",
        )
        enable_text_clipboard(self.update_log)

    def _check_app_update(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.update_log.insert("end", "\nПроверяю…\n")

        def work() -> None:
            try:
                from app.updater import (
                    apply_windows_update,
                    check_windows_update,
                    download_update_to_temp,
                )
                import os
                import subprocess

                # Persist link/settings before replacing the exe
                try:
                    if hasattr(self, "vless_box"):
                        raw = self.vless_box.get("1.0", "end").strip()
                        if raw:
                            self.settings.vless_url = raw
                    save_settings(self.settings)
                except Exception:
                    pass

                upd = check_windows_update()
                if not upd:
                    self.after(0, lambda: self._update_done("Обновлений нет."))
                    return
                self.after(
                    0,
                    lambda: self.update_log.insert(
                        "end", f"Найдено {upd.version}, скачиваю…\n"
                    ),
                )
                path = download_update_to_temp(upd.url, upd.version)
                launcher = apply_windows_update(path)

                def ask() -> None:
                    self._busy = False
                    self.update_log.insert("end", f"Скачано: {path}\n")
                    self.update_log.insert(
                        "end",
                        "Настройки (ссылка VPN) хранятся в %LOCALAPPDATA%\\VLESS-Boost и сохранятся.\n",
                    )
                    if messagebox.askyesno(
                        "Обновление",
                        f"Версия {upd.version} скачана.\n"
                        "Установить на место текущей программы?\n"
                        "(ссылка VPN и настройки сохранятся)",
                        parent=self,
                    ):
                        subprocess.Popen(
                            ["cmd.exe", "/c", str(launcher)],
                            shell=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        self.destroy()
                        os._exit(0)

                self.after(0, ask)
            except Exception as exc:
                err = str(exc) or repr(exc)
                self.after(0, lambda m=err: self._update_done(f"Ошибка: {m}"))

        threading.Thread(target=work, daemon=True).start()

    def _update_done(self, msg: str) -> None:
        self._busy = False
        self.update_log.insert("end", msg + "\n")
        self.update_log.see("end")

    def _toggle_boost(self) -> None:
        if self.manager.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        if self._busy:
            return
        raw = self.vless_box.get("1.0", "end").strip()
        if raw:
            self.settings.vless_url = raw
            self.settings.protect_direct = bool(self.var_protect.get())
            save_settings(self.settings)

        if not self.settings.vless_url.strip():
            messagebox.showwarning(
                "Нужна ссылка VPN",
                "Откройте «Настройки» и вставьте ссылку на ваш VPN.",
                parent=self,
            )
            self._show_page("settings")
            return
        if not is_admin():
            if messagebox.askyesno(
                "Нужны права администратора",
                "Для работы ускорения нужны права администратора.\nПерезапустить приложение?",
                parent=self,
            ):
                relaunch_as_admin()
            return

        # Зависший sing-box с прошлого запуска
        try:
            external = self.manager.external_instances()
        except Exception:
            external = []
        if external and not self.manager.running:
            pids = ", ".join(str(p) for p, _ in external)
            if not messagebox.askyesno(
                "Активное соединение",
                "Найден работающий sing-box от прошлого запуска.\n"
                f"PID: {pids}\n\n"
                "Убить его и подключиться заново?",
                parent=self,
            ):
                return
            # start() тоже убьёт, но сделаем явно до busy
            self.manager.kill_external()

        self._busy = True
        self.boost_btn.configure(text="…", state="disabled")
        if hasattr(self, "home_title_lbl"):
            self.home_title_lbl.configure(text="Подключение…", text_color=COLORS["accent"])
        self._start_connect_animation()

        def work() -> None:
            try:
                self.settings = load_settings()
                self.manager.start(self.settings, kill_external=True)
                self.after(0, lambda: self._after_start(True, "Ускорение включено"))
            except Exception as exc:
                logger.exception("start failed")
                err = str(exc) or repr(exc)
                self.after(0, lambda m=err: self._after_start(False, m))

        threading.Thread(target=work, daemon=True).start()

    def _after_start(self, ok: bool, msg: str) -> None:
        self._busy = False
        self._stop_connect_animation()
        self.boost_btn.configure(state="normal")
        self._refresh_status()
        if ok:
            messagebox.showinfo(
                "Готово",
                msg + "\nЕсли программа уже была открыта — перезапустите её.",
                parent=self,
            )
            # Автопинг после успешного старта
            self.after(200, self._ping_server)
        else:
            messagebox.showerror("Не удалось включить", msg, parent=self)

    def _stop(self) -> None:
        try:
            self.manager.stop()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
        self._refresh_status()

    def _stop_status_blink(self) -> None:
        if self._status_blink_after is not None:
            try:
                self.after_cancel(self._status_blink_after)
            except Exception:
                pass
            self._status_blink_after = None
        self._status_blink_bright = True

    def _tick_status_blink(self) -> None:
        self._status_blink_after = None
        if not self.manager.running:
            return
        if not self.winfo_viewable():
            self._status_blink_after = self.after(1000, self._tick_status_blink)
            return
        self._status_blink_bright = not self._status_blink_bright
        # Blink ONLY the dot — label text stays solid green
        color = COLORS["ok"] if self._status_blink_bright else COLORS["ok_dim"]
        try:
            if hasattr(self, "status_dot"):
                self.status_dot.configure(text_color=color)
        except Exception:
            return
        self._status_blink_after = self.after(750, self._tick_status_blink)

    def _start_status_blink(self) -> None:
        if self._status_blink_after is not None:
            return
        self._status_blink_bright = True
        self._status_blink_after = self.after(750, self._tick_status_blink)

    def _set_power_visual(self, *, hover: bool = False, connecting: bool = False) -> None:
        if not hasattr(self, "power_btn"):
            return
        on = self.manager.running
        glow = self._power_glow
        if connecting:
            glow = max(glow, 120)
        elif hover:
            glow = min(140, glow + 20)
        try:
            if isinstance(self.power_btn, PowerButton):
                self.power_btn.set_state(on=on, connecting=connecting, glow=glow)
            else:
                self.power_btn.configure(image=self._power_image(on=on or connecting, glow=glow))
        except Exception:
            pass

    def _power_image(self, *, on: bool, glow: int = 100):
        # Legacy fallback — prefer PowerButton widget
        from app.icons import make_power_button_image

        key = (on, int(glow))
        if key not in self._power_images:
            pil = make_power_button_image(168, on=on, glow=int(glow))
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(168, 168))
            self._power_images[key] = img
            self._logo_refs.append(img)
        return self._power_images[key]

    def _startup_fade_in(self) -> None:
        # Fewer alpha steps: translucent intermediate frames cause blur/ghosting.
        def step(a: float = 0.0) -> None:
            a = min(1.0, a + 0.25)
            try:
                self.attributes("-alpha", a)
            except Exception:
                return
            if a < 1.0:
                self.after(16, lambda: step(a))
            else:
                self._pulse_power_intro()

        step()

    def _pulse_power_intro(self) -> None:
        # Brief glow pulse on first paint
        frames = [70, 90, 115, 130, 110, 100]
        idx = {"i": 0}

        def tick() -> None:
            if idx["i"] >= len(frames) or self.manager.running:
                self._power_glow = 100
                self._set_power_visual()
                return
            self._power_glow = frames[idx["i"]]
            idx["i"] += 1
            self._set_power_visual()
            self._power_anim_after = self.after(55, tick)

        tick()

    def _start_connect_animation(self) -> None:
        self._stop_connect_animation()
        phase = {"t": 0}

        def tick() -> None:
            if self.manager.running or not self._busy:
                self._power_glow = 100
                self._set_power_visual()
                self._connect_anim_after = None
                return
            phase["t"] += 1
            # Quantize glow to cut PIL regenerations / image churn
            raw = 85 + int(35 * (0.5 + 0.5 * math.sin(phase["t"] / 3)))
            self._power_glow = int(round(raw / 5) * 5)
            self._set_power_visual(connecting=True)
            self._connect_anim_after = self.after(50, tick)

        tick()

    def _stop_connect_animation(self) -> None:
        if self._connect_anim_after is not None:
            try:
                self.after_cancel(self._connect_anim_after)
            except Exception:
                pass
            self._connect_anim_after = None

    def _on_unmap(self, event) -> None:
        if event.widget is not self:
            return
        if self._minimizing_to_tray:
            return
        try:
            if self.state() == "iconic":
                self._minimizing_to_tray = True
                self.after(30, self._minimize_to_tray)
        except Exception:
            pass

    def _on_map(self, _event=None) -> None:
        # Restore from minimize/tray must NOT reload lists or rebuild catalog.
        self._minimizing_to_tray = False

    def _minimize_to_tray(self) -> None:
        try:
            self.withdraw()
            self._ensure_tray()
        finally:
            self._minimizing_to_tray = False

    def _refresh_status(self) -> None:
        running = self.manager.running
        if running:
            if hasattr(self, "status_dot"):
                self.status_dot.configure(text="●", text_color=COLORS["ok"])
            self.status_lbl.configure(text="Подключено", text_color=COLORS["ok"])
            self._start_status_blink()
            self._start_session_timer()
            self.boost_btn.configure(
                text="Выключить",
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                text_color="#FFFFFF",
            )
            self._power_glow = 115
            self._set_power_visual()
            if hasattr(self, "home_title_lbl"):
                self.home_title_lbl.configure(text="Вы подключены", text_color=COLORS["ok"])
            if hasattr(self, "home_sub_lbl"):
                self.home_sub_lbl.configure(
                    text="Ваши данные защищены и передаются через VPN."
                )
            if hasattr(self, "side_disconnect_btn"):
                self.side_disconnect_btn.configure(state="normal")
            if hasattr(self, "home_off_btn"):
                self.home_off_btn.configure(state="normal")
            self._refresh_server_labels()
            self._refresh_home_services()
            return

        # Process scan via PowerShell is slow — never block GUI thread.
        self._apply_idle_status_ui()
        self._refresh_server_labels()
        self._refresh_home_services()

        def work() -> None:
            try:
                ext = self.manager.external_instances()
            except Exception:
                ext = []
            try:
                if not self.winfo_exists():
                    return
                self.after(0, lambda e=ext: self._apply_external_status(e))
            except RuntimeError:
                return

        threading.Thread(target=work, daemon=True).start()

    def _apply_idle_status_ui(self) -> None:
        self._stop_status_blink()
        self._stop_session_timer()
        if hasattr(self, "status_dot"):
            self.status_dot.configure(text="●", text_color=COLORS["muted"])
        self.status_lbl.configure(text="Выключено", text_color=COLORS["muted"])
        self.boost_btn.configure(
            text="Включить",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#061018",
        )
        self._power_glow = 100
        self._set_power_visual()
        if hasattr(self, "home_title_lbl"):
            self.home_title_lbl.configure(text="Вы не подключены", text_color=COLORS["text"])
        if hasattr(self, "home_sub_lbl"):
            self.home_sub_lbl.configure(
                text="Нажмите кнопку питания, чтобы ускорить выбранные сервисы."
            )
        if hasattr(self, "side_disconnect_btn"):
            self.side_disconnect_btn.configure(state="disabled")
        if hasattr(self, "home_off_btn"):
            self.home_off_btn.configure(state="disabled")

    def _apply_external_status(self, ext: list) -> None:
        if self.manager.running:
            return
        if not ext:
            return
        pids = ", ".join(str(p) for p, _ in ext)
        if hasattr(self, "status_dot"):
            self.status_dot.configure(text="●", text_color=COLORS["accent"])
        self.status_lbl.configure(
            text=f"Зависший sing-box ({pids})",
            text_color=COLORS["accent"],
        )
        if hasattr(self, "home_title_lbl"):
            self.home_title_lbl.configure(
                text="Найден зависший процесс", text_color=COLORS["accent"]
            )

    def _maybe_admin_prompt(self) -> None:
        if not is_admin():
            self._stop_status_blink()
            if hasattr(self, "status_dot"):
                self.status_dot.configure(text_color=COLORS["accent"])
            self.status_lbl.configure(
                text="Нужен запуск от администратора",
                text_color=COLORS["accent"],
            )

    def _on_close(self) -> None:
        # Always allow tray hide when setting enabled; else confirm if VPN running
        if self.settings.minimize_to_tray:
            self.withdraw()
            self._ensure_tray()
            return
        if self.manager.running:
            if not messagebox.askyesno(
                "Выход",
                "Ускорение сейчас включено. Выключить и закрыть приложение?",
                parent=self,
            ):
                return
            self.manager.stop()
        if self._tray:
            self._tray.stop()
        self.destroy()

    def _ensure_tray(self) -> None:
        if self._tray:
            return

        def show(icon=None, item=None):
            def do():
                self.deiconify()
                self.state("normal")
                self.lift()
                try:
                    self.attributes("-topmost", True)
                    self.after(80, lambda: self.attributes("-topmost", False))
                except Exception:
                    pass

            self.after(0, do)

        def stop_boost(icon=None, item=None):
            self.after(0, self._stop)

        def quit_app(icon=None, item=None):
            def do():
                try:
                    self.manager.stop()
                except Exception:
                    pass
                if self._tray:
                    self._tray.stop()
                    self._tray = None
                self.destroy()

            self.after(0, do)

        menu = pystray.Menu(
            pystray.MenuItem("Открыть", show, default=True),
            pystray.MenuItem("Выключить", stop_boost),
            pystray.MenuItem("Выход", quit_app),
        )
        self._tray = pystray.Icon("vless-boost", tray_icon(True), "VLESS Boost", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()


def run_app() -> None:
    app = BoosterApp()
    app.mainloop()
