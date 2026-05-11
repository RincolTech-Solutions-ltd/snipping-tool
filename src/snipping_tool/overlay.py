"""
Fullscreen selection overlay.

Dims the entire screen, lets the user drag-select a rectangular region
(or click a window, or capture full screen), then calls back with the
chosen geometry. Free-form mode lets the user draw an arbitrary polygon.
"""

import math
from typing import Callable, Optional, Tuple, List

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import cairo

from .capture import capture_fullscreen, capture_region

SnipMode = str  # "rect" | "freeform" | "window" | "fullscreen"

TOOLBAR_HEIGHT = 56
TOOLBAR_PAD = 8
BUTTON_W = 120
BUTTON_H = 38
OVERLAY_ALPHA = 0.40


class SelectionOverlay(Gtk.Window):
    """Transparent fullscreen window for region selection."""

    def __init__(
        self,
        mode: SnipMode,
        on_captured,  # Callable[[PIL.Image.Image], None]
        on_cancel: Callable[[], None],
    ):
        super().__init__(type=Gtk.WindowType.POPUP)
        self._mode = mode
        self._on_captured = on_captured
        self._on_cancel = on_cancel

        self._start_x = 0
        self._start_y = 0
        self._cur_x = 0
        self._cur_y = 0
        self._dragging = False
        self._freeform_points: List[Tuple[int, int]] = []
        self._background: Optional[GdkPixbuf.Pixbuf] = None

        self._setup_window()
        self._connect_signals()
        self._show()

    def _setup_window(self):
        screen = Gdk.Screen.get_default()
        w = screen.get_width()
        h = screen.get_height()

        self.set_app_paintable(True)
        self.set_visual(screen.get_rgba_visual())
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.move(0, 0)
        self.resize(w, h)

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )

    def _connect_signals(self):
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("key-press-event", self._on_key)

    def _show(self):
        self.show_all()
        self.grab_focus()
        win = self.get_window()
        cursor = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair")
        win.set_cursor(cursor)
        Gtk.grab_add(self)

        if self._mode == "fullscreen":
            GObject.timeout_add(80, self._do_fullscreen)

    def _do_fullscreen(self):
        self._capture_and_finish(0, 0, *self._screen_size())
        return False

    def _screen_size(self) -> Tuple[int, int]:
        screen = Gdk.Screen.get_default()
        return screen.get_width(), screen.get_height()

    def _on_draw(self, _widget, cr: cairo.Context):
        screen = Gdk.Screen.get_default()
        w = screen.get_width()
        h = screen.get_height()

        # Dim overlay
        cr.set_source_rgba(0, 0, 0, OVERLAY_ALPHA)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        if self._mode == "window":
            self._draw_window_highlight(cr)
            return

        if not self._dragging:
            return

        if self._mode == "rect":
            x, y, rw, rh = self._selection_rect()
            # Clear dim inside selection
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.rectangle(x, y, rw, rh)
            cr.fill()
            cr.set_operator(cairo.OPERATOR_OVER)
            # Selection border
            cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)
            cr.set_line_width(2)
            cr.rectangle(x, y, rw, rh)
            cr.stroke()
            # Size label
            self._draw_size_label(cr, x, y, rw, rh)

        elif self._mode == "freeform" and len(self._freeform_points) > 1:
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.move_to(*self._freeform_points[0])
            for px, py in self._freeform_points[1:]:
                cr.line_to(px, py)
            cr.close_path()
            cr.fill()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)
            cr.set_line_width(2)
            cr.move_to(*self._freeform_points[0])
            for px, py in self._freeform_points[1:]:
                cr.line_to(px, py)
            cr.close_path()
            cr.stroke()

    def _draw_size_label(self, cr, x, y, w, h):
        label = f"{abs(int(w))} x {abs(int(h))}"
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        ext = cr.text_extents(label)
        px = x + w / 2 - ext.width / 2
        py = y - 8 if y > 24 else y + abs(h) + 20
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(px - 5, py - ext.height - 3, ext.width + 10, ext.height + 6)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(px, py)
        cr.show_text(label)

    def _draw_window_highlight(self, cr):
        disp = Gdk.Display.get_default()
        screen = disp.get_default_screen()
        ptr = screen.get_window_at_pointer()
        if ptr and ptr[0]:
            win = ptr[0]
            orig = win.get_origin()
            geom = win.get_geometry()
            _, gx, gy, gw, gh = geom
            _, ox, oy = orig
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.rectangle(ox, oy, gw, gh)
            cr.fill()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
            cr.set_line_width(3)
            cr.rectangle(ox, oy, gw, gh)
            cr.stroke()

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1:
            return
        if self._mode == "window":
            self._capture_hovered_window()
            return
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._cur_x = event.x_root
        self._cur_y = event.y_root
        self._dragging = True
        if self._mode == "freeform":
            self._freeform_points = [(event.x_root, event.y_root)]

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        self._cur_x = event.x_root
        self._cur_y = event.y_root
        if self._dragging and self._mode == "freeform":
            self._freeform_points.append((event.x_root, event.y_root))
        if self._mode == "window":
            self.queue_draw()
        elif self._dragging:
            self.queue_draw()

    def _on_release(self, _widget, event: Gdk.EventButton):
        if event.button != 1 or not self._dragging:
            return
        self._dragging = False
        self._cur_x = event.x_root
        self._cur_y = event.y_root

        if self._mode == "rect":
            x, y, w, h = self._selection_rect()
            if w < 5 or h < 5:
                self._on_cancel()
                self._close()
                return
            self._capture_and_finish(int(x), int(y), int(w), int(h))

        elif self._mode == "freeform":
            if len(self._freeform_points) < 3:
                self._on_cancel()
                self._close()
                return
            self._capture_freeform()

    def _on_key(self, _widget, event: Gdk.EventKey):
        if event.keyval == Gdk.KEY_Escape:
            self._on_cancel()
            self._close()

    def _selection_rect(self) -> Tuple[float, float, float, float]:
        x = min(self._start_x, self._cur_x)
        y = min(self._start_y, self._cur_y)
        w = abs(self._cur_x - self._start_x)
        h = abs(self._cur_y - self._start_y)
        return x, y, w, h

    def _capture_and_finish(self, x: int, y: int, w: int, h: int):
        self._close()
        try:
            img = capture_region(x, y, w, h)
            self._on_captured(img)
        except Exception as e:
            print(f"Capture error: {e}")
            self._on_cancel()

    def _capture_freeform(self):
        from PIL import Image, ImageDraw
        pts = self._freeform_points
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bx, by = int(min(xs)), int(min(ys))
        bw = int(max(xs) - bx)
        bh = int(max(ys) - by)
        if bw < 5 or bh < 5:
            self._on_cancel()
            self._close()
            return
        self._close()
        try:
            base = capture_region(bx, by, bw, bh)
            mask = Image.new("L", (bw, bh), 0)
            draw = ImageDraw.Draw(mask)
            local_pts = [(x - bx, y - by) for x, y in pts]
            draw.polygon(local_pts, fill=255)
            result = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            base = base.convert("RGBA")
            result.paste(base, mask=mask)
            self._on_captured(result)
        except Exception as e:
            print(f"Freeform capture error: {e}")
            self._on_cancel()

    def _capture_hovered_window(self):
        disp = Gdk.Display.get_default()
        screen = disp.get_default_screen()
        ptr = screen.get_window_at_pointer()
        if not ptr or not ptr[0]:
            self._on_cancel()
            self._close()
            return
        win = ptr[0]
        orig = win.get_origin()
        geom = win.get_geometry()
        _, gx, gy, gw, gh = geom
        _, ox, oy = orig
        self._capture_and_finish(ox, oy, gw, gh)

    def _close(self):
        Gtk.grab_remove(self)
        self.hide()
        self.destroy()
