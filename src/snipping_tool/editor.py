"""
Annotation editor window.

Displays the captured image and lets the user annotate it with:
  - Pen (freehand draw)
  - Highlighter (semi-transparent brush)
  - Arrow
  - Rectangle / Ellipse shapes
  - Text
  - Eraser
  - Crop
"""

import os
import io
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango
import cairo
from PIL import Image

from .capture import copy_image_to_clipboard


# ---------------------------------------------------------------------------
# Tool types
# ---------------------------------------------------------------------------

TOOL_PEN = "pen"
TOOL_HIGHLIGHTER = "highlighter"
TOOL_ARROW = "arrow"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"
TOOL_TEXT = "text"
TOOL_ERASER = "eraser"
TOOL_CROP = "crop"


@dataclass
class Stroke:
    tool: str
    color: Tuple[float, float, float, float]
    size: float
    points: List[Tuple[float, float]] = field(default_factory=list)
    text: str = ""

    # For single-click shapes: start + end points
    p1: Optional[Tuple[float, float]] = None
    p2: Optional[Tuple[float, float]] = None


# ---------------------------------------------------------------------------
# Canvas widget
# ---------------------------------------------------------------------------

class AnnotationCanvas(Gtk.DrawingArea):

    def __init__(self, image: Image.Image):
        super().__init__()
        self._image = image.convert("RGBA")
        self._surface: Optional[cairo.ImageSurface] = None
        self._strokes: List[Stroke] = []
        self._redo_stack: List[Stroke] = []
        self._current_stroke: Optional[Stroke] = None
        self._active_tool = None  # no tool active on open — user must click a tool to draw
        self._color = (1.0, 0.0, 0.0, 1.0)
        self._size = 3.0
        self._text_entry_active = False
        self._pending_text_pos: Optional[Tuple[float, float]] = None

        self._img_surface = self._pil_to_cairo(self._image)

        self.set_size_request(image.width, image.height)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.set_can_focus(True)
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("key-press-event", self._on_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tool(self, tool: str):
        self._active_tool = tool

    def set_color(self, r: float, g: float, b: float, a: float = 1.0):
        self._color = (r, g, b, a)

    def set_size(self, size: float):
        self._size = size

    def undo(self):
        if self._strokes:
            self._redo_stack.append(self._strokes.pop())
            self.queue_draw()

    def redo(self):
        if self._redo_stack:
            self._strokes.append(self._redo_stack.pop())
            self.queue_draw()

    def get_result_image(self) -> Image.Image:
        """Render everything onto the base image and return as PIL Image."""
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self._image.width, self._image.height
        )
        cr = cairo.Context(surface)
        cr.set_source_surface(self._img_surface, 0, 0)
        cr.paint()
        self._render_strokes(cr, self._strokes)
        buf = bytes(surface.get_data())
        result = Image.frombuffer("RGBA", (surface.get_width(), surface.get_height()), buf, "raw", "BGRA")
        return result.convert("RGB")

    # ------------------------------------------------------------------
    # Cairo helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pil_to_cairo(img: Image.Image) -> cairo.ImageSurface:
        img = img.convert("RGBA")
        data = bytearray(img.tobytes("raw", "BGRA"))
        surface = cairo.ImageSurface.create_for_data(
            data, cairo.FORMAT_ARGB32, img.width, img.height
        )
        return surface

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_draw(self, _widget, cr: cairo.Context):
        cr.set_source_surface(self._img_surface, 0, 0)
        cr.paint()
        self._render_strokes(cr, self._strokes)
        if self._current_stroke:
            self._render_stroke(cr, self._current_stroke)

    def _render_strokes(self, cr: cairo.Context, strokes: List[Stroke]):
        for stroke in strokes:
            self._render_stroke(cr, stroke)

    def _render_stroke(self, cr: cairo.Context, stroke: Stroke):
        cr.save()
        r, g, b, a = stroke.color
        if stroke.tool == TOOL_HIGHLIGHTER:
            cr.set_source_rgba(r, g, b, 0.35)
            cr.set_line_cap(cairo.LINE_CAP_SQUARE)
        elif stroke.tool == TOOL_ERASER:
            cr.set_source_rgba(1, 1, 1, 1)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
        else:
            cr.set_source_rgba(r, g, b, a)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)

        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(stroke.size)

        if stroke.tool in (TOOL_PEN, TOOL_HIGHLIGHTER, TOOL_ERASER):
            if len(stroke.points) < 2:
                cr.restore()
                return
            cr.move_to(*stroke.points[0])
            for pt in stroke.points[1:]:
                cr.line_to(*pt)
            cr.stroke()

        elif stroke.tool == TOOL_ARROW and stroke.p1 and stroke.p2:
            self._draw_arrow(cr, stroke.p1, stroke.p2, stroke.size)

        elif stroke.tool == TOOL_RECT and stroke.p1 and stroke.p2:
            x = min(stroke.p1[0], stroke.p2[0])
            y = min(stroke.p1[1], stroke.p2[1])
            w = abs(stroke.p2[0] - stroke.p1[0])
            h = abs(stroke.p2[1] - stroke.p1[1])
            cr.rectangle(x, y, w, h)
            cr.stroke()

        elif stroke.tool == TOOL_ELLIPSE and stroke.p1 and stroke.p2:
            x = min(stroke.p1[0], stroke.p2[0])
            y = min(stroke.p1[1], stroke.p2[1])
            w = abs(stroke.p2[0] - stroke.p1[0])
            h = abs(stroke.p2[1] - stroke.p1[1])
            if w > 0 and h > 0:
                cr.save()
                cr.translate(x + w / 2, y + h / 2)
                cr.scale(w / 2, h / 2)
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.stroke()

        elif stroke.tool == TOOL_TEXT and stroke.p1 and stroke.text:
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(stroke.size * 5)
            cr.move_to(*stroke.p1)
            cr.show_text(stroke.text)

        cr.restore()

    def _draw_arrow(self, cr: cairo.Context, p1, p2, width):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1:
            return
        cr.move_to(*p1)
        cr.line_to(*p2)
        cr.stroke()
        angle = math.atan2(dy, dx)
        head = max(12, width * 4)
        spread = math.pi / 6
        for sign in (1, -1):
            ax = p2[0] - head * math.cos(angle - sign * spread)
            ay = p2[1] - head * math.sin(angle - sign * spread)
            cr.move_to(*p2)
            cr.line_to(ax, ay)
            cr.stroke()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_press(self, _widget, event: Gdk.EventButton):
        if event.button != 1 or self._active_tool is None:
            return
        x, y = event.x, event.y

        if self._active_tool == TOOL_TEXT:
            self._start_text_input(x, y)
            return

        self._redo_stack.clear()
        self._current_stroke = Stroke(
            tool=self._active_tool,
            color=self._color,
            size=self._size,
            p1=(x, y),
        )
        if self._active_tool in (TOOL_PEN, TOOL_HIGHLIGHTER, TOOL_ERASER):
            self._current_stroke.points.append((x, y))

    def _on_motion(self, _widget, event: Gdk.EventMotion):
        if not self._current_stroke:
            return
        x, y = event.x, event.y
        if self._current_stroke.tool in (TOOL_PEN, TOOL_HIGHLIGHTER, TOOL_ERASER):
            self._current_stroke.points.append((x, y))
        else:
            self._current_stroke.p2 = (x, y)
        self.queue_draw()

    def _on_release(self, _widget, event: Gdk.EventButton):
        if not self._current_stroke:
            return
        x, y = event.x, event.y
        self._current_stroke.p2 = (x, y)
        self._strokes.append(self._current_stroke)
        self._current_stroke = None
        self.queue_draw()

    def _on_key(self, _widget, event: Gdk.EventKey):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval == Gdk.KEY_z:
            self.undo()
        elif ctrl and event.keyval == Gdk.KEY_y:
            self.redo()

    def _start_text_input(self, x: float, y: float):
        dialog = Gtk.Dialog(title="Add Text", transient_for=self.get_toplevel(), flags=0)
        dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        entry = Gtk.Entry()
        entry.set_placeholder_text("Type your text…")
        entry.set_width_chars(30)
        dialog.get_content_area().add(entry)
        dialog.show_all()
        entry.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))
        response = dialog.run()
        text = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and text:
            self._redo_stack.clear()
            stroke = Stroke(
                tool=TOOL_TEXT,
                color=self._color,
                size=self._size,
                p1=(x, y),
                text=text,
            )
            self._strokes.append(stroke)
            self.queue_draw()


# ---------------------------------------------------------------------------
# Editor window
# ---------------------------------------------------------------------------

COLORS = [
    ("Red",    (1.0, 0.0, 0.0, 1.0)),
    ("Blue",   (0.0, 0.4, 1.0, 1.0)),
    ("Green",  (0.0, 0.7, 0.2, 1.0)),
    ("Yellow", (1.0, 0.9, 0.0, 1.0)),
    ("Black",  (0.0, 0.0, 0.0, 1.0)),
    ("White",  (1.0, 1.0, 1.0, 1.0)),
]

TOOLS = [
    (TOOL_PEN,         "Pen",         "edit-symbolic"),
    (TOOL_HIGHLIGHTER, "Highlight",   "tool-highlight-symbolic"),
    (TOOL_ARROW,       "Arrow",       "go-up-symbolic"),
    (TOOL_RECT,        "Rectangle",   "object-select-symbolic"),
    (TOOL_ELLIPSE,     "Ellipse",     "media-record-symbolic"),
    (TOOL_TEXT,        "Text",        "insert-text-symbolic"),
    (TOOL_ERASER,      "Eraser",      "edit-clear-symbolic"),
]


class EditorWindow(Gtk.Window):

    def __init__(self, image: Image.Image, on_close: Optional[Callable] = None, on_new_snip: Optional[Callable] = None):
        super().__init__(title="Snipping Tool")
        self._image = image
        self._on_close = on_close
        self._on_new_snip = on_new_snip
        self._saved_path: Optional[str] = None
        self._auto_filename = self._make_filename()

        self.set_default_size(min(image.width + 40, 1400), min(image.height + 140, 900))
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._build_ui()
        self.connect("delete-event", self._on_delete)
        self.show_all()

        # Auto-save to ~/Pictures and copy to clipboard
        try:
            copy_image_to_clipboard(image)
        except Exception:
            pass
        try:
            image.convert("RGB").save(self._auto_filename, "PNG")
        except Exception:
            pass

    @staticmethod
    def _make_filename() -> str:
        pictures = os.path.join(os.path.expanduser("~"), "Pictures")
        os.makedirs(pictures, exist_ok=True)
        ts = datetime.now().strftime("%d%m%y%H%M%S")
        return os.path.join(pictures, f"scst_{ts}.png")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Snipping Tool")
        self.set_titlebar(header)

        # Action buttons in header
        self._btn_copy = Gtk.Button(label="Copy")
        self._btn_copy.get_style_context().add_class("suggested-action")
        self._btn_copy.connect("clicked", self._on_copy)
        header.pack_end(self._btn_copy)

        self._btn_save = Gtk.Button(label="Save")
        self._btn_save.connect("clicked", self._on_save)
        header.pack_end(self._btn_save)

        self._btn_new = Gtk.Button(label="New Snip")
        self._btn_new.connect("clicked", self._on_new)
        header.pack_start(self._btn_new)

        # Toolbar
        toolbar = self._build_toolbar()
        vbox.pack_start(toolbar, False, False, 0)

        # Canvas in scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._canvas = AnnotationCanvas(self._image)
        scroll.add(self._canvas)
        vbox.pack_start(scroll, True, True, 0)

        # Set rectangle as active tool now that canvas exists
        self._canvas.set_tool(TOOL_RECT)
        self._canvas.set_color(1.0, 0.0, 0.0, 1.0)

        # Status bar
        self._status = Gtk.Label(label=f"  {self._image.width} x {self._image.height} px   |   Saved to {self._auto_filename}")
        self._status.set_xalign(0)
        self._status.get_style_context().add_class("dim-label")
        vbox.pack_start(self._status, False, False, 4)

    def _build_toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_margin_start(8)
        bar.set_margin_end(8)
        bar.set_margin_top(6)
        bar.set_margin_bottom(6)

        # Tool buttons — Rectangle is default selected
        tool_group: Optional[Gtk.RadioButton] = None
        self._tool_buttons = {}
        for tool_id, label, icon_name in TOOLS:
            btn = Gtk.RadioButton.new_from_widget(tool_group)
            if tool_group is None:
                tool_group = btn
            btn.set_mode(False)
            try:
                img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
                btn.add(img)
                btn.set_tooltip_text(label)
            except Exception:
                btn.set_label(label[:3])
            btn.connect("toggled", self._on_tool_toggled, tool_id)
            bar.pack_start(btn, False, False, 0)
            self._tool_buttons[tool_id] = btn

        # Pre-select rectangle tool
        self._tool_buttons[TOOL_RECT].set_active(True)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        # Color buttons — red is selected by default
        self._color_buttons = {}
        self._color_providers = {}
        for color_name, rgba in COLORS:
            btn = Gtk.Button()
            btn.set_size_request(26, 26)
            btn.set_tooltip_text(color_name)
            btn.connect("clicked", self._on_color_clicked, rgba, color_name)
            self._color_buttons[color_name] = (btn, rgba)
            bar.pack_start(btn, False, False, 2)

        self._selected_color_name = "Red"
        self._refresh_color_buttons()

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        # Brush size
        size_label = Gtk.Label(label="Size:")
        bar.pack_start(size_label, False, False, 0)
        self._size_spin = Gtk.SpinButton.new_with_range(1, 30, 1)
        self._size_spin.set_value(3)
        self._size_spin.connect("value-changed", self._on_size_changed)
        bar.pack_start(self._size_spin, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        # Undo / Redo
        btn_undo = Gtk.Button(label="Undo")
        btn_undo.connect("clicked", lambda _: self._canvas.undo())
        bar.pack_start(btn_undo, False, False, 0)

        btn_redo = Gtk.Button(label="Redo")
        btn_redo.connect("clicked", lambda _: self._canvas.redo())
        bar.pack_start(btn_redo, False, False, 0)

        return bar

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_tool_toggled(self, btn: Gtk.RadioButton, tool_id: str):
        if btn.get_active():
            self._canvas.set_tool(tool_id)

    def _on_color_clicked(self, _btn, rgba, color_name):
        self._selected_color_name = color_name
        self._canvas.set_color(*rgba)
        self._refresh_color_buttons()

    def _refresh_color_buttons(self):
        for name, (btn, rgba) in self._color_buttons.items():
            r, g, b, a = rgba
            selected = (name == self._selected_color_name)
            ring = "box-shadow: 0 0 0 3px white, 0 0 0 5px rgba(0,0,0,0.5);" if selected else ""
            css = (
                f"button {{ background: rgb({int(r*255)},{int(g*255)},{int(b*255)}); "
                f"min-width: 26px; min-height: 26px; padding: 0; border-radius: 50%; "
                f"border: none; {ring} }}"
            )
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            ctx = btn.get_style_context()
            # Remove previous provider for this button before adding new one
            if name in self._color_providers:
                ctx.remove_provider(self._color_providers[name])
            ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
            self._color_providers[name] = provider

    def _on_size_changed(self, spin):
        self._canvas.set_size(spin.get_value())

    def _on_copy(self, _btn):
        try:
            img = self._canvas.get_result_image()
            copy_image_to_clipboard(img)
            self._set_status("Copied to clipboard.")
        except Exception as e:
            self._set_status(f"Copy failed: {e}")

    def _on_save(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title="Save Screenshot",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )
        dialog.set_do_overwrite_confirmation(True)

        # Default folder: ~/Pictures (create if missing)
        pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures")
        os.makedirs(pictures_dir, exist_ok=True)
        dialog.set_current_folder(pictures_dir)

        # Default filename: scst_DDMMYYHHmmss.png
        timestamp = datetime.now().strftime("%d%m%y%H%M%S")
        dialog.set_current_name(f"scst_{timestamp}.png")

        for name, pattern in [("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*")]:
            f = Gtk.FileFilter()
            f.set_name(name)
            f.add_pattern(pattern)
            dialog.add_filter(f)

        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            if not path.lower().endswith((".png", ".jpg", ".jpeg")):
                path += ".png"
            try:
                img = self._canvas.get_result_image()
                img.save(path)
                self._saved_path = path
                self._set_status(f"Saved: {path}")
            except Exception as e:
                self._set_status(f"Save failed: {e}")
        dialog.destroy()

    def _on_new(self, _btn):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            text="Start a new snip?",
            secondary_text="The current screenshot is auto-saved to ~/Pictures. "
                           "Save your annotations now, or discard them.",
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Discard & New Snip", Gtk.ResponseType.NO)
        dialog.add_button("Save & New Snip", Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.YES)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.CANCEL:
            return
        if response == Gtk.ResponseType.YES:
            self._on_save(None)
        self.destroy()
        if self._on_new_snip:
            self._on_new_snip()

    def _on_delete(self, _widget, _event):
        if self._on_close:
            self._on_close()
        return False

    def _set_status(self, msg: str):
        self._status.set_text(f"  {self._image.width} x {self._image.height} px   |   {msg}")
