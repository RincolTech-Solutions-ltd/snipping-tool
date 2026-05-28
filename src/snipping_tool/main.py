"""
Entry point for Snipping Tool.
"""

import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

try:
    gi.require_version("Keybinder", "3.0")
    from gi.repository import Keybinder
    KEYBINDER_AVAILABLE = True
except Exception:
    KEYBINDER_AVAILABLE = False

from gi.repository import Gtk, Gdk, GLib

from .overlay import SelectionOverlay, SnipMode
from .editor import EditorWindow
from . import __version__, __app_name__, __app_id__


HOTKEY = "<Ctrl><Shift>s"

MODES = [
    ("rect",       "Rectangular"),
    ("freeform",   "Freeform"),
    ("fullscreen", "Full Screen"),
]


def get_active_monitor_geometry():
    """Return geometry of the monitor containing the pointer."""
    display = Gdk.Display.get_default()
    seat = display.get_default_seat()
    pointer = seat.get_pointer()
    _screen, px, py = pointer.get_position()
    monitor = display.get_monitor_at_point(px, py)
    return monitor.get_geometry()


class ModeChooser(Gtk.Window):
    """Top-centre toolbar on the active monitor."""

    def __init__(self, on_mode_selected, on_cancel):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self._on_mode_selected = on_mode_selected
        self._on_cancel = on_cancel

        self.set_title("Snipping Tool")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_resizable(False)

        self._build_ui()
        self.show_all()
        self._position()
        self.present()
        # Only close on Escape — no focus-out close (it fires too aggressively)
        self.connect("key-press-event", self._on_key)

    def _build_ui(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_margin_start(14)
        box.set_margin_end(14)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        lbl = Gtk.Label(label="  Snipping Tool  ")
        box.pack_start(lbl, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 8)

        for mode_id, label in MODES:
            btn = Gtk.Button(label=label)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            if mode_id == "rect":
                btn.get_style_context().add_class("suggested-action")
            btn.connect("clicked", self._on_btn_clicked, mode_id)
            box.pack_start(btn, False, False, 4)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 8)
        box.pack_start(Gtk.Label(label=" Delay: "), False, False, 0)
        self._delay_spin = Gtk.SpinButton.new_with_range(0, 10, 1)
        self._delay_spin.set_value(0)
        self._delay_spin.set_width_chars(2)
        box.pack_start(self._delay_spin, False, False, 4)
        box.pack_start(Gtk.Label(label="s   "), False, False, 0)

        close_btn = Gtk.Button(label="✕")
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", lambda _: self._cancel())
        box.pack_start(close_btn, False, False, 0)

        self.add(box)

    def _position(self):
        geo = get_active_monitor_geometry()
        w, _ = self.get_size()
        # Centre horizontally on active monitor, sit at very top
        x = geo.x + (geo.width - w) // 2
        y = geo.y
        self.move(x, y)

    def _on_btn_clicked(self, _btn, mode_id: str):
        delay = int(self._delay_spin.get_value())
        self.destroy()
        self._on_mode_selected(mode_id, delay)

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._cancel()

    def _cancel(self):
        try:
            self.destroy()
        except Exception:
            pass
        self._on_cancel()


class SnippingApp:

    def __init__(self):
        self._chooser = None
        self._setup_tray()
        self._setup_hotkey()
        # Go straight to rectangular mode by default
        GLib.idle_add(lambda: self._start_capture("rect", 0))

    def _setup_tray(self):
        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3
            ind = AppIndicator3.Indicator.new(
                __app_id__,
                "applets-screenshooter",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            ind.set_menu(self._build_tray_menu())
            self._indicator = ind
        except Exception:
            self._indicator = None

    def _build_tray_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        for mode_id, label in MODES:
            item = Gtk.MenuItem(label=f"New {label} Snip")
            item.connect("activate", lambda _, m=mode_id: self._start_capture(m, 0))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        about = Gtk.MenuItem(label="About")
        about.connect("activate", lambda _: self._show_about())
        menu.append(about)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        return menu

    def _setup_hotkey(self):
        if not KEYBINDER_AVAILABLE:
            return
        Keybinder.init()
        if not Keybinder.bind(HOTKEY, lambda *_: GLib.idle_add(self.show_mode_chooser), None):
            print(f"Warning: could not bind {HOTKEY}. Set it manually in System Settings → Keyboard Shortcuts.")

    def show_mode_chooser(self, *_):
        if self._chooser:
            try:
                self._chooser.present()
            except Exception:
                pass
            return
        self._chooser = ModeChooser(
            on_mode_selected=self._start_capture,
            on_cancel=lambda: None,
        )
        self._chooser.connect("destroy", lambda *_: setattr(self, "_chooser", None))

    def _start_capture(self, mode: SnipMode, delay: int):
        if delay > 0:
            GLib.timeout_add(delay * 1000, self._launch_overlay, mode)
        else:
            self._launch_overlay(mode)

    def _launch_overlay(self, mode: SnipMode):
        SelectionOverlay(
            mode=mode,
            on_captured=lambda img: GLib.idle_add(self._open_editor, img),
            on_cancel=lambda: None,
        )
        return False

    def _open_editor(self, image):
        EditorWindow(image, on_new_snip=lambda: self._start_capture("rect", 0))
        return False

    def _show_about(self):
        d = Gtk.AboutDialog()
        d.set_program_name(__app_name__)
        d.set_version(__version__)
        d.set_comments("A feature-complete snipping tool for Linux Mint and GTK desktops.")
        d.set_website("https://github.com/Lovepankie/snipping-tool")
        d.set_license_type(Gtk.License.MIT_X11)
        d.set_authors(["Dennis Kaweesi"])
        d.run()
        d.destroy()


def main():
    # Set consistent WM_CLASS for all windows so the panel groups them
    # under a single button instead of scattering separate taskbar entries.
    GLib.set_prgname("snipping-tool")
    GLib.set_application_name("Snipping Tool")
    SnippingApp()
    Gtk.main()


if __name__ == "__main__":
    main()
