"""
Selection overlay.

Strategy: capture the full screen FIRST, then display that screenshot
as the overlay background (dimmed). The user draws their selection on
top of the frozen image. No system-level grabs — no freeze risk.
"""

import math
from typing import Callable, List, Optional, Tuple

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import cairo
from PIL import Image

from .capture import capture_screen, capture_region

SnipMode = str  # "rect" | "freeform" | "window" | "fullscreen"


def _pil_to_cairo_surface(img: Image.Image) -> cairo.ImageSurface:
    img = img.convert("RGBA")
    data = bytearray(img.tobytes("raw", "BGRA"))
    return cairo.ImageSurface.create_for_data(
        data, cairo.FORMAT_ARGB32, img.width, img.height
    )


class SelectionOverlay(Gtk.Window):

    def __init__(self, mode: SnipMode, on_captured, on_cancel: Callable):
        super().__init__(type=Gtk.WindowType.POPUP)
        self._mode = mode
        self._on_captured = on_captured
        self._on_cancel = on_cancel

        self._dragging = False
        self._start: Optional[Tuple[int, int]] = None
        self._cur: Optional[Tuple[int, int]] = None
        self._freeform: List[Tuple[int, int]] = []

        # Capture screen BEFORE showing anything
        try:
            self._full_img = capture_screen()
        except Exception as e:
            print(f"Capture error: {e}")
            on_cancel()
            return

        self._bg_surface = _pil_to_cairo_surface(self._full_img)

        vw = self._full_img.width
        vh = self._full_img.height

        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.move(0, 0)
        self.resize(vw, vh)

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.set_can_focus(True)

        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._motion)
        self.connect("key-press-event", self._key)

        self.show_all()
        self.grab_focus()

        win = self.get_window()
        win.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair"))

        if mode == "fullscreen":
            GObject.timeout_add(80, self._do_fullscreen)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, _w, cr: cairo.Context):
        vw = self._full_img.width
        vh = self._full_img.height

        # Background: the frozen screenshot
        cr.set_source_surface(self._bg_surface, 0, 0)
        cr.paint()

        # Dim everything
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(0, 0, vw, vh)
        cr.fill()

        if self._mode == "fullscreen":
            return

        if self._mode == "rect" and self._dragging and self._start and self._cur:
            x, y, w, h = self._rect()
            if w > 0 and h > 0:
                # Cut dim from selection — show original screenshot through
                cr.save()
                cr.set_operator(cairo.OPERATOR_SOURCE)
                cr.set_source_surface(self._bg_surface, 0, 0)
                cr.rectangle(x, y, w, h)
                cr.fill()
                cr.restore()
                # Blue border
                cr.set_source_rgba(0.2, 0.55, 1.0, 1.0)
                cr.set_line_width(2)
                cr.rectangle(x + 1, y + 1, w - 2, h - 2)
                cr.stroke()
                # Size label
                self._label(cr, x, y, w, h)

        elif self._mode == "freeform" and len(self._freeform) > 2:
            cr.save()
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_surface(self._bg_surface, 0, 0)
            cr.move_to(*self._freeform[0])
            for p in self._freeform[1:]:
                cr.line_to(*p)
            cr.close_path()
            cr.fill()
            cr.restore()
            cr.set_source_rgba(0.2, 0.55, 1.0, 1.0)
            cr.set_line_width(2)
            cr.move_to(*self._freeform[0])
            for p in self._freeform[1:]:
                cr.line_to(*p)
            cr.close_path()
            cr.stroke()

    def _label(self, cr, x, y, w, h):
        txt = f"{int(w)} × {int(h)}"
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        ext = cr.text_extents(txt)
        lx = x + w / 2 - ext.width / 2
        ly = y - 10 if y > 30 else y + h + 20
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(lx - 6, ly - ext.height - 2, ext.width + 12, ext.height + 6)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(lx, ly)
        cr.show_text(txt)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _press(self, _w, ev: Gdk.EventButton):
        if ev.button != 1:
            return
        self._start = (int(ev.x_root), int(ev.y_root))
        self._cur = self._start
        self._dragging = True
        if self._mode == "freeform":
            self._freeform = [self._start]

    def _motion(self, _w, ev: Gdk.EventMotion):
        self._cur = (int(ev.x_root), int(ev.y_root))
        if self._dragging and self._mode == "freeform":
            self._freeform.append(self._cur)
        self.queue_draw()

    def _release(self, _w, ev: Gdk.EventButton):
        if ev.button != 1 or not self._dragging:
            return
        self._dragging = False
        self._cur = (int(ev.x_root), int(ev.y_root))

        if self._mode == "rect":
            x, y, w, h = self._rect()
            if w < 5 or h < 5:
                self._cancel()
                return
            self._finish_region(x, y, w, h)

        elif self._mode == "freeform":
            if len(self._freeform) < 3:
                self._cancel()
                return
            self._finish_freeform()

    def _key(self, _w, ev: Gdk.EventKey):
        if ev.keyval == Gdk.KEY_Escape:
            self._cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rect(self):
        x = min(self._start[0], self._cur[0])
        y = min(self._start[1], self._cur[1])
        w = abs(self._cur[0] - self._start[0])
        h = abs(self._cur[1] - self._start[1])
        return x, y, w, h

    def _do_fullscreen(self):
        self._close()
        self._on_captured(self._full_img.copy())
        return False

    def _finish_region(self, x, y, w, h):
        img = self._full_img.crop((x, y, x + w, y + h))
        self._close()
        self._on_captured(img)

    def _finish_freeform(self):
        from PIL import ImageDraw
        pts = self._freeform
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bx, by = min(xs), min(ys)
        bw = max(xs) - bx
        bh = max(ys) - by
        if bw < 5 or bh < 5:
            self._cancel()
            return
        base = self._full_img.crop((bx, by, bx + bw, by + bh))
        mask = Image.new("L", (bw, bh), 0)
        draw = ImageDraw.Draw(mask)
        draw.polygon([(px - bx, py - by) for px, py in pts], fill=255)
        result = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        result.paste(base.convert("RGBA"), mask=mask)
        self._close()
        self._on_captured(result)

    def _cancel(self):
        self._close()
        self._on_cancel()

    def _close(self):
        self.hide()
        self.destroy()
