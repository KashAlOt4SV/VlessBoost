"""Shared UI helpers (clipboard, buttons, log trim)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

from app.icons import load_logo
from app.ui.theme import COLORS, FONT_UI, FONT_UI_BOLD, LOG_KEEP_LINES, LOG_MAX_BYTES


def trim_log_file(path: Path | None = None, *, max_bytes: int = LOG_MAX_BYTES, keep_lines: int = LOG_KEEP_LINES) -> None:
    from app.paths import LOG_PATH

    target = path or LOG_PATH
    try:
        if not target.exists():
            return
        if target.stat().st_size <= max_bytes:
            return
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        target.write_text("\n".join(lines[-keep_lines:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def primary_btn(master, text: str, command, *, width=140, height=42, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 12,
        "fg_color": COLORS["primary"],
        "hover_color": COLORS["primary_hover"],
        "text_color": "#061018",
        "border_width": 1,
        "border_color": COLORS["cyan"],
        "font": ctk.CTkFont(family=FONT_UI_BOLD, size=13),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


def ghost_btn(master, text: str, command, *, width=110, height=36, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 12,
        "fg_color": COLORS["ghost"],
        "hover_color": COLORS["ghost_hover"],
        "text_color": COLORS["text"],
        "border_width": 1,
        "border_color": COLORS["border"],
        "font": ctk.CTkFont(family=FONT_UI, size=12),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


def danger_btn(master, text: str, command, *, width=140, height=42, **kw) -> ctk.CTkButton:
    opts = {
        "width": width,
        "height": height,
        "corner_radius": 12,
        "fg_color": COLORS["danger"],
        "hover_color": COLORS["danger_hover"],
        "text_color": "#FFFFFF",
        "border_width": 1,
        "border_color": "#FF8A93",
        "font": ctk.CTkFont(family=FONT_UI_BOLD, size=13),
    }
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)


def tray_icon(active: bool) -> Image.Image:
    try:
        base = load_logo(64)
        if not active:
            overlay = Image.new("RGBA", base.size, (0, 0, 0, 110))
            return Image.alpha_composite(base, overlay)
        return base
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (22, 139, 255, 255) if active else (102, 122, 148, 255)
        draw.ellipse((4, 4, 60, 60), fill=color)
        return img


def enable_text_clipboard(widget) -> None:
    """Ctrl+V/C/X/A and right-click paste for CTk Entry/Textbox (RU layout safe)."""
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
