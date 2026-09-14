"""Viewport-rendered service catalog; no per-service native window hierarchy."""
import math
import tkinter as tk
import customtkinter as ctk
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
        self._pending = None
        self._signature = None
        self._hover = None
        self._focus = 0
        self._hits = []
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
        item.enabled = not item.enabled
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
                tx,ty,tw=x+16*scale,y+78*scale,right-x-32*scale
            else:
                tx,ty,tw=titlex,y+40*scale,textwidth
            self.canvas.create_text(tx,ty,text=p.description,anchor='nw',width=tw,
                                    font=(FONT_UI,-round(12*scale)),fill=COLORS['muted'])
            sx,sy=right-58*scale,y+24*scale
            self._rounded(sx,sy,sx+42*scale,sy+22*scale,11*scale,COLORS['primary'] if active else '#243044')
            cx=sx+(31 if active else 11)*scale
            self.canvas.create_oval(cx-8*scale,sy+3*scale,cx+8*scale,sy+19*scale,fill='white',outline='')
            self._hits.append((x,y,right,bottom,item))
        if not self.visible:
            self.canvas.create_text(w/2,40*scale,text='Сервисы не найдены',fill=COLORS['muted'],font=(FONT_UI,14))

    def _set_scaling(self, *args):
        super()._set_scaling(*args)
        if hasattr(self, '_photos'):
            self._photos.clear()
            self.invalidate()

    def destroy(self):
        if self._pending is not None:
            self.after_cancel(self._pending)
        super().destroy()
