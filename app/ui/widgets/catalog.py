"""Viewport-rendered service catalog; no per-service native window hierarchy."""
import math
import time
import tkinter as tk
import customtkinter as ctk
from PIL import ImageTk
from app.ui.widgets.rocker import render_rocker
from app.presets import CATEGORY_LABELS
from app.ui.theme import COLORS, FONT_UI
from app.ui.widgets.scrolling import StableScrollbar


class CatalogItem:
    def __init__(self, view, preset, enabled):
        self.view, self.preset, self.enabled = view, preset, enabled

    def set_enabled(self, value):
        if self.enabled != value:
            self.enabled = value
            self.view.invalidate()


class CatalogView(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.pop('scrollbar_button_color', None)
        kw.pop('scrollbar_button_hover_color', None)
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, bg=COLORS['bg'], highlightthickness=0, takefocus=True)
        self.bar = StableScrollbar(self, command=self._scroll, button_color=COLORS['border'],
                                   button_hover_color=COLORS['accent_dim'])
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=self._scrolled)
        self.items = {}
        self.visible = []
        self.mode = 'cards'
        self.columns = 2
        self.icons = {}
        self._photos = {}
        self._toggle_photos = {}
        self._toggle_nodes = {}
        self._transitions = {}
        self._animation_job = None
        self._pending = None
        self._signature = None
        self._hover = None
        self._focus = 0
        self._hits = []
        self.bind('<Unmap>', self._finish_animations, add='+')
        self.bind('<Map>', lambda e: self.invalidate(), add='+')
        self.canvas.bind('<Configure>', lambda e: self.invalidate())
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Motion>', self._motion)
        self.canvas.bind('<Leave>', lambda e: self._set_hover(None))
        self.canvas.bind('<space>', self._key_toggle)
        self.canvas.bind('<Return>', self._key_toggle)
        self.canvas.bind('<Down>', lambda e: self._navigate(1))
        self.canvas.bind('<Up>', lambda e: self._navigate(-1))
        self.canvas.bind('<FocusIn>', lambda e: self.invalidate())
        self.canvas.bind('<FocusOut>', lambda e: self.invalidate())

    def set_data(self, presets, enabled, icons, on_toggle):
        self.items = {p.id: CatalogItem(self, p, enabled(p.id)) for p in presets}
        self.icons = icons
        self.on_toggle = on_toggle
        self._signature = None
        return self.items

    def filter(self, query, category, mode, columns):
        self.visible = [item for item in self.items.values()
                        if (not category or item.preset.category == category)
                        and (not query or query in f'{item.preset.name} {item.preset.description} {item.preset.id}'.lower())]
        self.mode, self.columns = mode, columns if mode == 'cards' else 1
        self._focus = 0
        self.canvas.yview_moveto(0)
        self.invalidate()

    def invalidate(self):
        self._signature = None
        if self._pending is None:
            self._pending = self.after_idle(self._paint)

    def _scroll(self, *args):
        self.canvas.yview(*args)

    def _scrolled(self, first, last):
        self.bar.set(first, last)
        if self._pending is None:
            self._pending = self.after_idle(self._paint)

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), 'units')
        return 'break'

    def _motion(self, event):
        y = self.canvas.canvasy(event.y)
        hit = next((item.preset.id for x1,y1,x2,y2,item in self._hits
                    if x1 <= event.x <= x2 and y1 <= y <= y2), None)
        self._set_hover(hit)

    def _set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self.canvas.configure(cursor='hand2' if key else '')
            self.invalidate()

    def _click(self, event):
        self.canvas.focus_set()
        y = self.canvas.canvasy(event.y)
        for x1,y1,x2,y2,item in self._hits:
            if x1 <= event.x <= x2 and y1 <= y <= y2:
                self._focus = self.visible.index(item)
                self._toggle(item)
                break

    def _toggle(self, item):
        key = item.preset.id
        current = self._toggle_progress(key, item.enabled)
        item.enabled = not item.enabled
        self._transitions[key] = (time.perf_counter(), current, float(item.enabled))
        if self._animation_job is None:
            self._animation_job = self.after(16, self._animate_toggles)
        self.invalidate()
        self.on_toggle(item.preset.id, item.enabled)

    def _key_toggle(self, event):
        if self.visible:
            self._toggle(self.visible[self._focus])
        return 'break'

    def _navigate(self, delta):
        if self.visible:
            self._focus = max(0, min(len(self.visible)-1, self._focus + delta))
            y = (self._focus // self.columns) * self._row_height
            top = self.canvas.canvasy(0)
            if y < top or y + self._row_height > top + self.canvas.winfo_height():
                self.canvas.yview_moveto(y / max(1, self._total_height))
            self.invalidate()
        return 'break'

    def _rounded(self, x1,y1,x2,y2,r, fill, outline=''):
        return self.canvas.create_polygon(
            x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
            x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1,
            smooth=True, splinesteps=16, fill=fill, outline=outline, width=1)

    def _paint(self):
        self._pending = None
        scale = self._get_widget_scaling()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        rowh = (142 if self.mode == 'cards' else 82) * scale
        self._row_height = rowh
        self._total_height = max(h, math.ceil(len(self.visible) / self.columns) * rowh)
        region = (0,0,w,self._total_height)
        if region != getattr(self, "_region", None):
            self._region = region
            self.canvas.configure(scrollregion=region, yscrollincrement=max(1,int(30*scale)))
        top = self.canvas.canvasy(0)
        sig = (w,h,top,self.mode,self.columns,scale,self._hover,self._focus,
               self.canvas.focus_get() is self.canvas,tuple((i.preset.id,i.enabled) for i in self.visible))
        if sig == self._signature:
            return
        self._signature = sig
        self.canvas.delete('all')
        self._toggle_nodes.clear()
        self._hits = []
        cellw = w / self.columns
        start = max(0, int(top // rowh) * self.columns)
        end = min(len(self.visible), (int((top+h)//rowh)+1)*self.columns)
        for index in range(start,end):
            item = self.visible[index]; p = item.preset
            x = (index % self.columns)*cellw+6*scale
            y = (index // self.columns)*rowh+6*scale
            right = x+cellw-12*scale; bottom = y+rowh-12*scale
            active = item.enabled
            color = COLORS['card_on'] if active else COLORS['card_hover'] if p.id==self._hover else COLORS['card']
            border = COLORS['border_on'] if active or p.id==self._hover else COLORS['border']
            if index == self._focus and self.canvas.focus_get() is self.canvas:
                border = COLORS['cyan']
            self._rounded(x,y,right,bottom,14*scale,color,border)
            image_key = (p.id,scale)
            if image_key not in self._photos:
                self._photos[image_key] = self.icons[p.id].create_scaled_photo_image(scale,'dark')
            self.canvas.create_image(x+16*scale,y+14*scale,image=self._photos[image_key],anchor='nw')
            titlex=x+68*scale
            textwidth=max(50,right-titlex-66*scale)
            self.canvas.create_text(titlex,y+16*scale,text=p.name,anchor='nw',width=textwidth,
                                    font=(FONT_UI,-round(14*scale),'bold'),fill=COLORS['text'])
            if self.mode=='cards':
                self.canvas.create_text(titlex,y+43*scale,text=CATEGORY_LABELS.get(p.category,p.category),anchor='nw',
                                        font=(FONT_UI,-round(11*scale)),fill=COLORS['muted'])
                tx,ty,tw=x+16*scale,y+78*scale,right-x-82*scale
            else:
                tx,ty,tw=titlex,y+40*scale,textwidth
            self.canvas.create_text(tx,ty,text=p.description,anchor='nw',width=tw,
                                    font=(FONT_UI,-round(12*scale)),fill=COLORS['muted'])
            node = self.canvas.create_image(right-16*scale, (y+bottom)/2,
                image=self._toggle_image(self._toggle_progress(p.id, active), scale), anchor='e')
            self._toggle_nodes[p.id] = node
            self._hits.append((x,y,right,bottom,item))
        if not self.visible:
            self.canvas.create_text(w/2,40*scale,text='Сервисы не найдены',fill=COLORS['muted'],font=(FONT_UI,14))

    def _toggle_progress(self, key, enabled):
        transition = self._transitions.get(key)
        if transition is None:
            return float(enabled)
        start, origin, target = transition
        t = min(1.0, (time.perf_counter() - start) / 0.22)
        eased = t * t * (3 - 2 * t)
        return origin + (target - origin) * eased

    def _toggle_image(self, progress, scale):
        key = (scale, self.mode)
        if key not in self._toggle_photos:
            width, height = (32, 66) if self.mode == 'cards' else (26, 54)
            size = (max(1, round(width*scale)), max(1, round(height*scale)))
            frames = [ImageTk.PhotoImage(render_rocker(size, index/16), master=self.canvas)
                      for index in range(17)]
            self._toggle_photos[key] = frames
        return self._toggle_photos[key][max(0, min(16, round(progress*16)))]

    def _animate_toggles(self):
        self._animation_job = None
        now = time.perf_counter()
        scale = self._get_widget_scaling()
        for key, (start, origin, target) in list(self._transitions.items()):
            node = self._toggle_nodes.get(key)
            if node is not None:
                self.canvas.itemconfigure(node, image=self._toggle_image(
                    self._toggle_progress(key, bool(target)), scale))
            if now - start >= 0.22:
                self._transitions.pop(key, None)
        if self._transitions:
            self._animation_job = self.after(16, self._animate_toggles)

    def _finish_animations(self, event=None):
        if self._animation_job is not None:
            self.after_cancel(self._animation_job)
            self._animation_job = None
        self._transitions.clear()
        self._signature = None

    def _set_scaling(self, *args):
        super()._set_scaling(*args)
        if hasattr(self, '_photos'):
            self._photos.clear()
            self._toggle_photos.clear()
            self.invalidate()

    def destroy(self):
        self._finish_animations()
        if self._pending is not None:
            self.after_cancel(self._pending)
        super().destroy()
