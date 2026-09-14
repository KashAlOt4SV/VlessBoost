"""Non-reentrant CustomTkinter scrollbars (compatible with CTk 5.2.2).

CTk's stock scrollbar pumps idle events inside _draw. During resize that
recursively paints partially laid out pages. Keep its renderer and colors,
but let the application's event loop deliver the completed frame.
"""
import customtkinter as ctk


class StableScrollbar(ctk.CTkScrollbar):
    def _draw(self, no_color_updates=False):
        ctk.CTkBaseClass._draw(self, no_color_updates)

        corrected_start_value, corrected_end_value = self._get_scrollbar_values_for_minimum_pixel_size()
        requires_recoloring = self._draw_engine.draw_rounded_scrollbar(self._apply_widget_scaling(self._current_width),
                                                                       self._apply_widget_scaling(self._current_height),
                                                                       self._apply_widget_scaling(self._corner_radius),
                                                                       self._apply_widget_scaling(self._border_spacing),
                                                                       corrected_start_value,
                                                                       corrected_end_value,
                                                                       self._orientation)

        if no_color_updates is False or requires_recoloring:
            if self._hover_state is True:
                self._canvas.itemconfig("scrollbar_parts",
                                        fill=self._apply_appearance_mode(self._button_hover_color),
                                        outline=self._apply_appearance_mode(self._button_hover_color))
            else:
                self._canvas.itemconfig("scrollbar_parts",
                                        fill=self._apply_appearance_mode(self._button_color),
                                        outline=self._apply_appearance_mode(self._button_color))

            if self._fg_color == "transparent":
                self._canvas.configure(bg=self._apply_appearance_mode(self._bg_color))
                self._canvas.itemconfig("border_parts",
                                        fill=self._apply_appearance_mode(self._bg_color),
                                        outline=self._apply_appearance_mode(self._bg_color))
            else:
                self._canvas.configure(bg=self._apply_appearance_mode(self._fg_color))
                self._canvas.itemconfig("border_parts",
                                        fill=self._apply_appearance_mode(self._fg_color),
                                        outline=self._apply_appearance_mode(self._fg_color))

        # Paint is dispatched by Tk after layout settles; never reenter idle tasks.

    def set(self, start_value, end_value):
        values = float(start_value), float(end_value)
        if values != (self._start_value, self._end_value):
            self._start_value, self._end_value = values
            self._draw()


def replace_bar(old):
    options = {name: getattr(old, {"width": "_desired_width", "height": "_desired_height"}.get(name, "_" + name)) for name in (
        "width", "height", "corner_radius", "border_spacing", "bg_color", "fg_color",
        "button_color", "button_hover_color", "orientation", "command")}
    grid = old.grid_info()
    parent = old.master
    old.destroy()
    new = StableScrollbar(parent, **options)
    if grid:
        new.grid(**grid)
    return new


class ScrollableFrame(ctk.CTkScrollableFrame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._scrollbar = replace_bar(self._scrollbar)
        self._parent_canvas.configure(**{
            "yscrollcommand" if self._orientation == "vertical" else "xscrollcommand": self._scrollbar.set})


class Textbox(ctk.CTkTextbox):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._x_scrollbar = replace_bar(self._x_scrollbar)
        self._y_scrollbar = replace_bar(self._y_scrollbar)
        self._textbox.configure(xscrollcommand=self._x_scrollbar.set, yscrollcommand=self._y_scrollbar.set)

    def _check_if_scrollbars_needed(self, event=None, continue_loop=False):
        # A hidden scrollbar is not evidence that a hidden page needs a regrid.
        if self.winfo_viewable():
            super()._check_if_scrollbars_needed(event, False)
        if continue_loop and self.winfo_exists():
            self.after(self._scrollbar_update_time,
                       lambda: self._check_if_scrollbars_needed(continue_loop=True))


