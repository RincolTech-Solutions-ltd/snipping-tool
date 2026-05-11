import subprocess
import tempfile
import os

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf
from PIL import Image


def capture_fullscreen() -> Image.Image:
    """Capture all monitors combined."""
    display = Gdk.Display.get_default()
    n = display.get_n_screens() if hasattr(display, "get_n_screens") else 1
    screen = display.get_default_screen()
    root = Gdk.get_default_root_window()
    width = screen.get_width()
    height = screen.get_height()
    return _capture_region(0, 0, width, height)


def capture_region(x: int, y: int, width: int, height: int) -> Image.Image:
    return _capture_region(x, y, width, height)


def capture_window_at(wx: int, wy: int) -> Image.Image:
    """Capture the window under the given screen coordinates."""
    display = Gdk.Display.get_default()
    screen = display.get_default_screen()
    window = screen.get_window_at_pointer()[0] if hasattr(screen, "get_window_at_pointer") else None
    if window is None:
        return capture_fullscreen()
    origin = window.get_origin()
    _, x, y = origin
    geom = window.get_geometry()
    _, wx2, wy2, w, h = geom
    return _capture_region(x, y, w, h)


def _capture_region(x: int, y: int, width: int, height: int) -> Image.Image:
    root = Gdk.get_default_root_window()
    pixbuf = Gdk.pixbuf_get_from_window(root, x, y, width, height)
    if pixbuf is None:
        raise RuntimeError("Failed to capture screen region")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        pixbuf.savev(tmp_path, "png", [], [])
        img = Image.open(tmp_path).copy()
    finally:
        os.unlink(tmp_path)
    return img


def image_to_pixbuf(img: Image.Image) -> GdkPixbuf.Pixbuf:
    """Convert a PIL Image to a GdkPixbuf for display in GTK."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes()
    return GdkPixbuf.Pixbuf.new_from_bytes(
        data_bytes := __import__("gi.repository.GLib", fromlist=["Bytes"]).Bytes.new(data),
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        img.width,
        img.height,
        img.width * 4,
    )


def copy_image_to_clipboard(img: Image.Image) -> None:
    """Copy a PIL Image to the system clipboard via xclip or xsel."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        img.save(tmp_path, "PNG")
        if subprocess.run(["which", "xclip"], capture_output=True).returncode == 0:
            with open(tmp_path, "rb") as f:
                subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png"],
                    stdin=f,
                    check=True,
                )
        elif subprocess.run(["which", "wl-copy"], capture_output=True).returncode == 0:
            with open(tmp_path, "rb") as f:
                subprocess.run(["wl-copy", "--type", "image/png"], stdin=f, check=True)
        else:
            _copy_via_gtk(img)
    finally:
        os.unlink(tmp_path)


def _copy_via_gtk(img: Image.Image) -> None:
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    if img.mode != "RGB":
        img = img.convert("RGB")
    data = img.tobytes()
    pixbuf = GdkPixbuf.Pixbuf.new_from_data(
        data,
        GdkPixbuf.Colorspace.RGB,
        False,
        8,
        img.width,
        img.height,
        img.width * 3,
    )
    clipboard.set_image(pixbuf)
    clipboard.store()
