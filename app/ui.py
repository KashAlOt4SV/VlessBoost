from __future__ import annotations

import logging
import threading
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray
import tkinter as tk
from tkinter import messagebox

from app.config_builder import collect_routes
from app.icons import app_ico_path, load_logo, make_preset_icon
from app.list_updater import update_all_remote
from app.netcheck import ping_vless_url
from app.presets import CATEGORY_LABELS, CATALOG, Preset
from app.settings import Settings, load_settings, save_settings
from app.singbox import SingBoxManager, is_admin, relaunch_as_admin
from app.vless_parser import parse_vless_url

logger = logging.getLogger(__name__)

COLORS = {
    "bg": "#070B12",
    "panel": "#0E1520",
    "elevated": "#141C28",
    "card": "#121A26",
    "card_on": "#182636",
    "border": "#243247",
    "border_on": "#3B9EFF",
    "text": "#F2F6FB",
    "muted": "#8B9BB0",
    "accent": "#3B9EFF",
    "accent_hover": "#5BB0FF",
    "accent_dim": "#1E6FBF",
    "ok": "#3DDC97",
    "danger": "#FF6B7A",
    "danger_hover": "#FF8490",
    "ghost": "#1A2433",
    "ghost_hover": "#243044",
}


def _tray_icon(active: bool) -> Image.Image:
    try:
        base = load_logo(64)
        if not active:
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 110))
            return Image.alpha_composite(base, overlay)
        return base
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (59, 158, 255, 255) if active else (139, 155, 176, 255)
        draw.ellipse((4, 4, 60, 60), fill=color)
        return img


def primary_btn(master, text: str, command, *, width=140, height=42, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 12,
        "fg_color": COLORS["accent"],
        "hover_color": COLORS["accent_hover"],
        "text_color": "#061018",
        "font": ctk.CTkFont(family="Segoe UI Semibold", size=13),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


def ghost_btn(master, text: str, command, *, width=110, height=36, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 10,
        "fg_color": COLORS["ghost"],
        "hover_color": COLORS["ghost_hover"],
        "text_color": COLORS["text"],
        "border_width": 1,
        "border_color": COLORS["border"],
        "font": ctk.CTkFont(size=12),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


def enable_text_clipboard(widget) -> None:
    """Make Ctrl+V/C/X/A and right-click paste work on CTk Entry/Textbox (Windows + RU layout).

    CustomTkinter wraps tk Entry/Text; with a Russian keyboard layout Ctrl+V often
    arrives as keysym ``м`` (same physical key), so the stock ``<Control-v>`` binding
    never fires. We handle Windows virtual-key codes (layout-independent) and
    Cyrillic keysyms explicitly.
    """
    target = getattr(widget, "_textbox", None) or getattr(widget, "_entry", None) or widget
    is_text = str(target.winfo_class()) == "Text"

    def _get_clip() -> str:
        try:
            return target.clipboard_get()
        except tk.TclError:
            return ""

    def _has_selection() -> bool:
        if is_text:
            return bool(target.tag_ranges("sel"))
        try:
            return bool(target.selection_present())
        except tk.TclError:
            return False

    def _delete_selection() -> None:
        if not _has_selection():
            return
        try:
            target.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def do_paste(_event=None):
        data = _get_clip()
        if not data:
            return "break"
        _delete_selection()
        try:
            target.insert("insert", data)
        except tk.TclError:
            pass
        return "break"

    def do_copy(_event=None):
        if not _has_selection():
            return "break"
        try:
            data = target.get("sel.first", "sel.last") if is_text else target.selection_get()
            target.clipboard_clear()
            target.clipboard_append(data)
        except tk.TclError:
            pass
        return "break"

    def do_cut(event=None):
        do_copy(event)
        _delete_selection()
        return "break"

    def do_select_all(_event=None):
        try:
            if is_text:
                target.tag_add("sel", "1.0", "end-1c")
                target.mark_set("insert", "1.0")
                target.see("insert")
            else:
                target.select_range(0, "end")
                target.icursor("end")
        except tk.TclError:
            pass
        return "break"

    def on_ctrl_key(event):
        # Windows VK_* are stable across keyboard layouts (V=0x56, C=0x43, X=0x58, A=0x41).
        # Skip when Latin keysym already matched a more specific <Control-v> binding.
        ks = (getattr(event, "keysym", None) or "").lower()
        if ks in ("v", "c", "x", "a"):
            return None
        code = getattr(event, "keycode", None)
        if code == 86:
            return do_paste(event)
        if code == 67:
            return do_copy(event)
        if code == 88:
            return do_cut(event)
        if code == 65:
            return do_select_all(event)
        return None

    # Latin + virtual <<Paste>> (Shift-Insert / OS paste)
    for seq, handler in (
        ("<Control-v>", do_paste),
        ("<Control-V>", do_paste),
        ("<Control-Shift-v>", do_paste),
        ("<Control-Shift-V>", do_paste),
        ("<<Paste>>", do_paste),
        ("<Control-c>", do_copy),
        ("<Control-C>", do_copy),
        ("<<Copy>>", do_copy),
        ("<Control-x>", do_cut),
        ("<Control-X>", do_cut),
        ("<<Cut>>", do_cut),
        ("<Control-a>", do_select_all),
        ("<Control-A>", do_select_all),
    ):
        target.bind(seq, handler)

    # Russian layout: physical V/C/X/A → м/с/ч/ф
    for seq, handler in (
        ("<Control-м>", do_paste),
        ("<Control-М>", do_paste),
        ("<Control-с>", do_copy),
        ("<Control-С>", do_copy),
        ("<Control-ч>", do_cut),
        ("<Control-Ч>", do_cut),
        ("<Control-ф>", do_select_all),
        ("<Control-Ф>", do_select_all),
    ):
        target.bind(seq, handler)

    # Layout-independent fallback (covers odd keysyms Tk may emit under Ctrl)
    target.bind("<Control-KeyPress>", on_ctrl_key)

    menu = tk.Menu(target, tearoff=0)
    menu.add_command(label="Вставить", command=lambda: do_paste())
    menu.add_command(label="Копировать", command=lambda: do_copy())
    menu.add_command(label="Вырезать", command=lambda: do_cut())
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: do_select_all())

    def show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    target.bind("<Button-3>", show_menu)


def danger_btn(master, text: str, command, *, width=140, height=42, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 12,
        "fg_color": COLORS["danger"],
        "hover_color": COLORS["danger_hover"],
        "text_color": "#FFFFFF",
        "font": ctk.CTkFont(family="Segoe UI Semibold", size=13),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


class ServiceCard(ctk.CTkFrame):
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
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border_on"] if enabled else COLORS["border"],
        )
        self.preset = preset
        self.on_toggle = on_toggle
        self.var = ctk.BooleanVar(value=enabled)
        self._visible = True
        self._grid_info: dict | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))

        ctk.CTkLabel(top, text="", image=icon, width=44, height=44).pack(side="left")

        titles = ctk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True, padx=(12, 8))
        ctk.CTkLabel(
            titles,
            text=preset.name,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text=CATEGORY_LABELS.get(preset.category, preset.category),
            font=ctk.CTkFont(size=11),
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
            progress_color=COLORS["accent"],
            button_color="#FFFFFF",
            button_hover_color="#F3F7FC",
            fg_color="#2A3548",
        )
        self.switch.pack(side="right")

        ctk.CTkLabel(
            self,
            text=preset.description,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
            wraplength=280,
        ).pack(fill="x", padx=14, pady=(0, 14))

    def _changed(self) -> None:
        on = bool(self.var.get())
        self.configure(
            fg_color=COLORS["card_on"] if on else COLORS["card"],
            border_color=COLORS["border_on"] if on else COLORS["border"],
        )
        self.on_toggle(self.preset.id, on)

    def set_enabled(self, value: bool) -> None:
        self.var.set(value)
        self.configure(
            fg_color=COLORS["card_on"] if value else COLORS["card"],
            border_color=COLORS["border_on"] if value else COLORS["border"],
        )

    def set_visible(self, visible: bool) -> None:
        if visible == self._visible:
            return
        self._visible = visible
        if visible:
            info = self._grid_info or {}
            self.grid(**info)
        else:
            self.grid_remove()


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
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border_on"] if enabled else COLORS["border"],
            height=64,
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
            font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            text,
            text=preset.description,
            font=ctk.CTkFont(size=11),
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
            progress_color=COLORS["accent"],
            button_color="#FFFFFF",
            button_hover_color="#F3F7FC",
            fg_color="#2A3548",
        )
        self.switch.pack(side="right", padx=16)

    def _changed(self) -> None:
        on = bool(self.var.get())
        self.configure(
            fg_color=COLORS["card_on"] if on else COLORS["elevated"],
            border_color=COLORS["border_on"] if on else COLORS["border"],
        )
        self.on_toggle(self.preset.id, on)

    def set_enabled(self, value: bool) -> None:
        self.var.set(value)
        self.configure(
            fg_color=COLORS["card_on"] if value else COLORS["elevated"],
            border_color=COLORS["border_on"] if value else COLORS["border"],
        )

    def set_visible(self, visible: bool) -> None:
        if visible == self._visible:
            return
        self._visible = visible
        if visible:
            self.pack(fill="x", padx=2, pady=4)
        else:
            self.pack_forget()


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
        self._logo_refs: list = []
        self._icons: dict[str, ctk.CTkImage] = {}
        self._items: dict[str, ServiceCard | ServiceRow] = {}
        self._view_mode = self.settings.view_mode if self.settings.view_mode in {"cards", "list"} else "cards"

        self.title("VLESS Boost")
        self.geometry("1080x740")
        self.minsize(920, 640)
        self.configure(fg_color=COLORS["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_window_icons()

        self._build()
        self._refresh_status()
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

        side = ctk.CTkFrame(root, width=228, fg_color=COLORS["panel"], corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(24, 18))
        try:
            logo = load_logo(48)
            logo_img = ctk.CTkImage(light_image=logo, dark_image=logo, size=(48, 48))
            self._logo_refs.append(logo_img)
            ctk.CTkLabel(brand, text="", image=logo_img).pack(side="left", padx=(0, 12))
        except Exception:
            pass
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(
            titles,
            text="VLESS",
            font=ctk.CTkFont(family="Segoe UI Black", size=18),
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="BOOST",
            font=ctk.CTkFont(family="Segoe UI Black", size=18),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")

        self.nav_boost = self._nav_btn(side, "Сервисы", lambda: self._show_page("boost"), True)
        self.nav_settings = self._nav_btn(side, "Настройки", lambda: self._show_page("settings"))
        self.nav_lists = self._nav_btn(side, "Обновление списков", lambda: self._show_page("lists"))
        self.nav_logs = self._nav_btn(side, "Логи", lambda: self._show_page("logs"))
        self.nav_update = self._nav_btn(side, "Обновление приложения", lambda: self._show_page("update"))

        self.status_lbl = ctk.CTkLabel(
            side,
            text="Выключено",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        )
        self.status_lbl.pack(side="bottom", padx=18, pady=20, anchor="w")

        self.main = ctk.CTkFrame(root, fg_color=COLORS["bg"], corner_radius=0)
        self.main.pack(side="left", fill="both", expand=True)

        self.page_boost = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_settings = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_lists = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_logs = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)
        self.page_update = ctk.CTkFrame(self.main, fg_color=COLORS["bg"], corner_radius=0)

        self._build_boost_page()
        self._build_settings_page()
        self._build_lists_page()
        self._build_logs_page()
        self._build_update_page()
        self._show_page("boost")

    def _nav_btn(self, parent, text: str, cmd, active: bool = False) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=cmd,
            anchor="w",
            height=44,
            corner_radius=12,
            fg_color=COLORS["elevated"] if active else "transparent",
            hover_color=COLORS["ghost_hover"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14),
        )
        btn.pack(fill="x", padx=12, pady=3)
        return btn

    def _show_page(self, name: str) -> None:
        for p in (self.page_boost, self.page_settings, self.page_lists, self.page_logs, self.page_update):
            p.pack_forget()
        {
            "boost": self.page_boost,
            "settings": self.page_settings,
            "lists": self.page_lists,
            "logs": self.page_logs,
            "update": self.page_update,
        }[name].pack(fill="both", expand=True, padx=24, pady=20)
        mapping = {
            "boost": self.nav_boost,
            "settings": self.nav_settings,
            "lists": self.nav_lists,
            "logs": self.nav_logs,
            "update": self.nav_update,
        }
        for key, btn in mapping.items():
            btn.configure(fg_color=COLORS["elevated"] if key == name else "transparent")
        if name == "logs":
            self._refresh_logs()

    def _build_boost_page(self) -> None:
        page = self.page_boost

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            left,
            text="Что ускорить",
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
            placeholder_text="Найти сервис…",
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

        # Переключатель вида
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

        self._render_catalog()
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
        self._render_catalog()
        self._apply_filter()

    def _clear_catalog(self) -> None:
        for child in self.catalog_host.winfo_children():
            child.destroy()
        self._items.clear()

    def _render_catalog(self) -> None:
        self._clear_catalog()
        if self._view_mode == "cards":
            self.catalog_host.grid_columnconfigure((0, 1), weight=1)
            row = col = 0
            for preset in CATALOG:
                card = ServiceCard(
                    self.catalog_host,
                    preset,
                    enabled=self.settings.is_enabled(preset.id),
                    icon=self._icon(preset, 44),
                    on_toggle=self._on_toggle,
                )
                card._grid_info = {"row": row, "column": col, "sticky": "nsew", "padx": 6, "pady": 6}
                card.grid(**card._grid_info)
                self._items[preset.id] = card
                col += 1
                if col > 1:
                    col = 0
                    row += 1
        else:
            for preset in CATALOG:
                row_w = ServiceRow(
                    self.catalog_host,
                    preset,
                    enabled=self.settings.is_enabled(preset.id),
                    icon=self._icon(preset, 40),
                    on_toggle=self._on_toggle,
                )
                row_w.pack(fill="x", padx=2, pady=4)
                self._items[preset.id] = row_w

    def _on_search_typed(self, _event=None) -> None:
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(100, self._apply_filter)

    def _apply_filter(self) -> None:
        q = (self.search_var.get() or "").strip().lower()
        cat_label = self.cat_var.get()
        cat_id = None
        if cat_label != "Все":
            for k, v in CATEGORY_LABELS.items():
                if v == cat_label:
                    cat_id = k
                    break
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
            item.set_visible(ok)

    def _on_toggle(self, preset_id: str, value: bool) -> None:
        self.settings.set_enabled(preset_id, value)
        save_settings(self.settings)
        self._update_summary()

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
        if hasattr(self, "settings_ping_lbl"):
            # Настройки: чуть другой префикс
            pretty = text if text.startswith("Пинг") else text
            if pretty.startswith("Пинг:"):
                pretty = "Пинг до сервера:" + pretty[len("Пинг:") :]
            self.settings_ping_lbl.configure(text=pretty, text_color=color)

    def _check_orphan_on_startup(self) -> None:
        try:
            external = self.manager.external_instances()
        except Exception:
            return
        if not external or self.manager.running:
            return
        self._stop_status_blink()
        pids = ", ".join(str(p) for p, _ in external)
        self.status_lbl.configure(
            text=f"⚠ Зависший sing-box (pid {pids})",
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
        self.lists_log.insert(
            "1.0",
            "Рекомендуем обновить списки один раз после установки.\n"
            "Общий список блокировок большой — включайте его только если нужно.\n",
        )
        enable_text_clipboard(self.lists_log)

    def _update_lists(self, only: list[str] | None = None) -> None:
        if self._busy:
            return
        self._busy = True
        self.lists_log.insert("end", "\nОбновление…\n")

        def work() -> None:
            try:
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
        self.lists_log.insert("end", msg + "\n")
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
        ghost_btn(row, "Открыть папку", self._open_log_folder, width=160, height=40).pack(
            side="left", padx=10
        )

        self.app_logs = ctk.CTkTextbox(
            page,
            corner_radius=12,
            fg_color=COLORS["elevated"],
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
        self.app_logs.delete("1.0", "end")
        try:
            if LOG_PATH.exists():
                text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
                # хвост, чтобы не тормозить UI
                lines = text.splitlines()
                text = "\n".join(lines[-800:])
                self.app_logs.insert("1.0", text or "(пусто)")
            else:
                self.app_logs.insert("1.0", f"Файл ещё не создан:\n{LOG_PATH}")
        except Exception as exc:
            self.app_logs.insert("1.0", f"Не удалось прочитать лог: {exc}")
        self.app_logs.see("end")

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
                from app.updater import check_windows_update, download_update_to_temp
                import os
                import subprocess

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

                def ask() -> None:
                    self._busy = False
                    self.update_log.insert("end", f"Скачано: {path}\n")
                    if messagebox.askyesno(
                        "Обновление",
                        f"Версия {upd.version} скачана.\nЗапустить установку и закрыть программу?",
                        parent=self,
                    ):
                        subprocess.Popen([str(path)], shell=False)
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
        self._status_blink_bright = not self._status_blink_bright
        # Clear blink: full green ↔ dim green on the ● only (label keeps "● Включено")
        color = COLORS["ok"] if self._status_blink_bright else "#1A6B4A"
        try:
            self.status_lbl.configure(text_color=color)
        except Exception:
            return
        self._status_blink_after = self.after(750, self._tick_status_blink)

    def _start_status_blink(self) -> None:
        if self._status_blink_after is not None:
            return
        self._status_blink_bright = True
        self._status_blink_after = self.after(750, self._tick_status_blink)

    def _refresh_status(self) -> None:
        if self.manager.running:
            self.status_lbl.configure(text="● Включено", text_color=COLORS["ok"])
            self._start_status_blink()
            self.boost_btn.configure(
                text="Выключить",
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                text_color="#FFFFFF",
            )
        elif self.manager.has_external_instance():
            self._stop_status_blink()
            pids = ", ".join(str(p) for p, _ in self.manager.external_instances())
            self.status_lbl.configure(
                text=f"⚠ Зависший sing-box ({pids})",
                text_color=COLORS["accent"],
            )
            self.boost_btn.configure(
                text="Включить",
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#061018",
            )
        else:
            self._stop_status_blink()
            self.status_lbl.configure(text="○ Выключено", text_color=COLORS["muted"])
            self.boost_btn.configure(
                text="Включить",
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#061018",
            )

    def _maybe_admin_prompt(self) -> None:
        if not is_admin():
            self._stop_status_blink()
            self.status_lbl.configure(
                text="Нужен запуск от администратора",
                text_color=COLORS["accent"],
            )

    def _on_close(self) -> None:
        if self.settings.minimize_to_tray and self.manager.running:
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
            self.after(0, self.deiconify)

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
                self.destroy()

            self.after(0, do)

        menu = pystray.Menu(
            pystray.MenuItem("Открыть", show, default=True),
            pystray.MenuItem("Выключить", stop_boost),
            pystray.MenuItem("Выход", quit_app),
        )
        self._tray = pystray.Icon("vless-boost", _tray_icon(True), "VLESS Boost", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()


def run_app() -> None:
    app = BoosterApp()
    app.mainloop()
