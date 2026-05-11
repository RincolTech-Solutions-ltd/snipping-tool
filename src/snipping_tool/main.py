"""
Entry point for Snipping Tool.

Provides:
  - Mode-chooser toolbar (Windows-style top-center popup)
  - Global hotkey: Ctrl+Shift+S (configurable)
  - System tray icon
  - Delay capture support
"""

import os
import sys
import time
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

try:
    gi.require_version("Keybinder", "3.0")
    from gi.repository import Keybinder
    KEYBINDER_AVAILABLE = True
except Exception:
    KEYBINDER_AVAILABLE = False

from gi.repository import Gtk, Gdk, GObject, GLib

from .overlay import SelectionOverlay, SnipMode
from .editor import EditorWindow
from . import __version__, __app_name__, __app_id__


HOTKEY = "<Ctrl><Shift>s"
ICON_NAME = "applets-screenshooter"
ICON_FALLBACK = "camera-photo"

MODES = [
    ("rect",       "Rectangular",  "selection-mode-symbolic"),
    ("freeform",   "Freeform",     "edit-select-lasso-symbolic"),
    ("window",     "Window",       "window-symbolic"),
    ("fullscreen", "Full Screen",  "view-fullscreen-symbolic"),
]


class ModeChooser(Gtk.Window):
    """
    Thin top-centre toolbar that appears when the hotkey is pressed,
    mimicking Windows' Win+Shift+S behaviour.
    """

    def __init__(self, on_mode_selected, on_cancel):
        super().__init__(type=Gtk.WindowType.POPUP)
        self._on_mode_selected = on_mode_selected
        self._on_cancel = on_cancel

        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        screen = Gdk.Screen.get_default()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self._build_ui()
        self._position()
        self.show_all()
        self.grab_focus()
        self.connect("key-press-event", self._on_key)
        self.connect("focus-out-event", lambda *_: self._cancel())

    def _build_ui(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        # Label
        lbl = Gtk.Label(label="Snipping Tool   ")
        lbl.get_style_context().add_class("dim-label")
        box.pack_start(lbl, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(sep, False, False, 8)

        # Mode buttons
        for mode_id, label, icon in MODES:
            btn = Gtk.Button(label=label)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("clicked", self._on_btn_clicked, mode_id)
            box.pack_start(btn, False, False, 4)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(sep2, False, False, 8)

        # Delay selector
        delay_lbl = Gtk.Label(label="Delay:")
        box.pack_start(delay_lbl, False, False, 0)
        self._delay_spin = Gtk.SpinButton.new_with_range(0, 10, 1)
        self._delay_spin.set_value(0)
        self._delay_spin.set_width_chars(2)
        self._delay_spin.set_tooltip_text("Delay in seconds before capture")
        box.pack_start(self._delay_spin, False, False, 4)
        box.pack_start(Gtk.Label(label="s"), False, False, 0)

        self.add(box)

    def _position(self):
        screen = Gdk.Screen.get_default()
        sw = screen.get_width()
        self.show_all()
        pw, _ph = self.get_size()
        self.move((sw - pw) // 2, 0)

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


class SnippingApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id=__app_id__)
        self._editor: list = []
        self._chooser: list = []

    # ------------------------------------------------------------------
    # GTK Application lifecycle
    # ------------------------------------------------------------------

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self._setup_tray()
        self._setup_hotkey()

    def do_activate(self):
        self.show_mode_chooser()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3
            ind = AppIndicator3.Indicator.new(
                __app_id__,
                ICON_NAME,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            menu = self._build_tray_menu()
            ind.set_menu(menu)
            self._indicator = ind
        except Exception:
            self._indicator = None

    def _build_tray_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        for mode_id, label, _ in MODES:
            item = Gtk.MenuItem(label=f"New {label} Snip")
            item.connect("activate", lambda _, m=mode_id: self._start_capture(m, 0))
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        about_item = Gtk.MenuItem(label=f"About {__app_name__}")
        about_item.connect("activate", self._show_about)
        menu.append(about_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self.quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ------------------------------------------------------------------
    # Global hotkey
    # ------------------------------------------------------------------

    def _setup_hotkey(self):
        if not KEYBINDER_AVAILABLE:
            return
        Keybinder.init()
        success = Keybinder.bind(HOTKEY, self._hotkey_activated, None)
        if not success:
            print(f"Could not bind hotkey {HOTKEY}. Another app may have claimed it.")

    def _hotkey_activated(self, _keystring, _data):
        GLib.idle_add(self.show_mode_chooser)

    # ------------------------------------------------------------------
    # Capture flow
    # ------------------------------------------------------------------

    def show_mode_chooser(self, *_args):
        if self._chooser:
            return
        chooser = ModeChooser(
            on_mode_selected=self._start_capture,
            on_cancel=lambda: None,
        )
        self._chooser.append(chooser)
        chooser.connect("destroy", lambda *_: self._chooser.clear())

    def _start_capture(self, mode: SnipMode, delay: int):
        if delay > 0:
            GLib.timeout_add(delay * 1000, self._launch_overlay, mode)
        else:
            self._launch_overlay(mode)

    def _launch_overlay(self, mode: SnipMode):
        SelectionOverlay(
            mode=mode,
            on_captured=self._on_captured,
            on_cancel=lambda: None,
        )
        return False  # one-shot GLib timeout

    def _on_captured(self, image):
        GLib.idle_add(self._open_editor, image)

    def _open_editor(self, image):
        win = EditorWindow(image, on_close=None)
        self.add_window(win)
        self._editor.append(win)
        win.connect("destroy", lambda w: self._editor.remove(w) if w in self._editor else None)
        return False

    # ------------------------------------------------------------------
    # About dialog
    # ------------------------------------------------------------------

    def _show_about(self, _widget=None):
        dialog = Gtk.AboutDialog()
        dialog.set_program_name(__app_name__)
        dialog.set_version(__version__)
        dialog.set_comments("A feature-complete snipping tool for Linux Mint and GTK desktops.")
        dialog.set_website("https://github.com/Lovepankie/snipping-tool")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_authors(["Dennis Kaweesi"])
        dialog.run()
        dialog.destroy()


def main():
    app = SnippingApp()
    # If no args, just show chooser immediately
    exit_code = app.run(sys.argv)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
