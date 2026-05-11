import os
import subprocess
import tempfile

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf
from PIL import Image


def capture_screen() -> Image.Image:
    """Capture the entire virtual screen."""
    screen = Gdk.Screen.get_default()
    root = Gdk.get_default_root_window()
    w = root.get_width()
    h = root.get_height()
    return _pixbuf_to_pil(Gdk.pixbuf_get_from_window(root, 0, 0, w, h))


def capture_region(x: int, y: int, w: int, h: int) -> Image.Image:
    root = Gdk.get_default_root_window()
    return _pixbuf_to_pil(Gdk.pixbuf_get_from_window(root, x, y, w, h))


def _pixbuf_to_pil(pixbuf) -> Image.Image:
    if pixbuf is None:
        raise RuntimeError("Screen capture returned nothing.")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        pixbuf.savev(tmp, "png", [], [])
        return Image.open(tmp).copy()
    finally:
        os.unlink(tmp)


def copy_image_to_clipboard(img: Image.Image) -> None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        img.save(tmp, "PNG")
        for cmd in (
            ["xclip", "-selection", "clipboard", "-t", "image/png"],
            ["wl-copy", "--type", "image/png"],
        ):
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                with open(tmp, "rb") as fh:
                    subprocess.run(cmd, stdin=fh)
                return
        # Fallback: GTK clipboard
        _gtk_clipboard(img)
    finally:
        os.unlink(tmp)


def _gtk_clipboard(img: Image.Image):
    from gi.repository import Gtk
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    img = img.convert("RGB")
    data = img.tobytes()
    pb = GdkPixbuf.Pixbuf.new_from_data(
        data, GdkPixbuf.Colorspace.RGB, False, 8,
        img.width, img.height, img.width * 3,
    )
    clipboard.set_image(pb)
    clipboard.store()
