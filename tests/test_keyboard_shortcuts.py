"""
Unit tests for EditorWindow keyboard shortcuts.
Stubs out GTK/Cairo/PIL so no display or compositor is needed.
"""

import sys
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub all native imports before the editor module loads
# ---------------------------------------------------------------------------
for _mod in [
    "gi", "gi.repository",
    "gi.repository.Gtk", "gi.repository.Gdk",
    "gi.repository.GdkPixbuf", "gi.repository.GObject", "gi.repository.Pango",
    "cairo", "PIL", "PIL.Image",
]:
    sys.modules[_mod] = MagicMock()

import gi
gi.require_version = MagicMock()

from gi.repository import Gdk, Gtk

# Gtk.Window must be a real Python class so EditorWindow.__new__ works
class _FakeWindow:
    def __init__(self, *args, **kwargs):
        pass
    def __getattr__(self, name):
        return MagicMock()

Gtk.Window = _FakeWindow

# Bind real GTK3 keyval / modifier constants
_CTRL = 4
Gdk.ModifierType.CONTROL_MASK = _CTRL
Gdk.KEY_z = 0x7A
Gdk.KEY_y = 0x79
Gdk.KEY_n = 0x6E
Gdk.KEY_s = 0x73

# Stub the capture sibling so the import resolves
sys.modules["snipping_tool.capture"] = MagicMock()

sys.path.insert(0, "/media/genius/New Volume/Engineering/Programming/Snipping_tool/src")
from snipping_tool.editor import EditorWindow  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Event:
    """Minimal stand-in for Gdk.EventKey."""
    def __init__(self, keyval: int, ctrl: bool = False):
        self.keyval = keyval
        self.state = _CTRL if ctrl else 0


def _make_window() -> EditorWindow:
    """Build an EditorWindow bypassing GTK construction."""
    win = EditorWindow.__new__(EditorWindow)
    win._canvas = MagicMock()
    win._on_save = MagicMock()
    win._on_new = MagicMock()
    return win


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWindowKeyShortcuts(unittest.TestCase):

    def test_ctrl_z_triggers_undo(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_z, ctrl=True))
        win._canvas.undo.assert_called_once()
        self.assertTrue(result)

    def test_ctrl_y_triggers_redo(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_y, ctrl=True))
        win._canvas.redo.assert_called_once()
        self.assertTrue(result)

    def test_ctrl_n_triggers_new_snip(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_n, ctrl=True))
        win._on_new.assert_called_once_with(None)
        self.assertTrue(result)

    def test_ctrl_s_triggers_save(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_s, ctrl=True))
        win._on_save.assert_called_once_with(None)
        self.assertTrue(result)

    def test_z_without_ctrl_is_ignored(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_z, ctrl=False))
        win._canvas.undo.assert_not_called()
        self.assertFalse(result)

    def test_s_without_ctrl_is_ignored(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(Gdk.KEY_s, ctrl=False))
        win._on_save.assert_not_called()
        self.assertFalse(result)

    def test_unhandled_key_returns_false(self):
        win = _make_window()
        result = win._on_window_key(None, _Event(0x61))  # 'a'
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
