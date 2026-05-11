# Snipping Tool for Linux

A full-featured screenshot and annotation tool for Linux Mint (and any GTK3 desktop), built to match — and surpass — the Windows Snipping Tool experience.

![Snipping Tool](data/icons/snipping-tool.svg)

## Features

| Feature | Windows Snipping Tool | This Tool |
|---|---|---|
| Rectangular snip | Yes | Yes |
| Freeform snip | Yes | Yes |
| Window snip | Yes | Yes |
| Full-screen snip | Yes | Yes |
| Capture delay | Yes (1–5s) | Yes (0–10s) |
| Pen annotation | Yes | Yes |
| Highlighter | Yes | Yes |
| Text annotation | Yes | Yes |
| Arrow tool | No | **Yes** |
| Rectangle / Ellipse shapes | No | **Yes** |
| Eraser | Yes | Yes |
| Undo / Redo | Yes | Yes |
| Auto-copy to clipboard | Yes | Yes |
| Save PNG / JPEG | Yes | Yes |
| Global hotkey | Win+Shift+S | Ctrl+Shift+S |
| System tray | No | **Yes** |
| Native GTK look | n/a | Yes |

## Installation

### Option 1: Quick install (recommended)

```bash
git clone https://github.com/Lovepankie/snipping-tool.git
cd snipping-tool
./install.sh
```

### Option 2: Install the .deb package

Download the latest `.deb` from the [Releases](https://github.com/Lovepankie/snipping-tool/releases) page, then:

```bash
sudo dpkg -i snipping-tool_1.0.0_all.deb
sudo apt-get install -f   # fix any missing dependencies
```

### Option 3: Manual

```bash
git clone https://github.com/Lovepankie/snipping-tool.git
cd snipping-tool
# Install dependencies
sudo apt-get install python3-gi python3-gi-cairo python3-pil python3-cairo \
    gir1.2-gtk-3.0 gir1.2-keybinder-3.0 libkeybinder-3.0-0 xclip
# Run directly
python3 -m snipping_tool.main   # from inside src/
# or
./snipping-tool
```

## Dependencies

All dependencies are available in the default Linux Mint / Ubuntu repositories:

- `python3-gi` — PyGObject (GTK3 bindings)
- `python3-pil` — Pillow (image processing)
- `python3-cairo` — Cairo bindings
- `gir1.2-keybinder-3.0` — Global hotkey support
- `xclip` — Clipboard integration

## Global Hotkey Setup

The app registers `Ctrl+Shift+S` automatically via keybinder. If it conflicts with another app, set it manually:

**Linux Mint Cinnamon:**
> System Settings → Keyboard → Keyboard Shortcuts → Custom Shortcuts → Add Custom Shortcut
> - Name: `Snipping Tool`
> - Command: `snipping-tool`
> - Key: `Ctrl+Shift+S`

## How to Use

1. Press `Ctrl+Shift+S` (or launch from the app menu)
2. Choose a snip mode from the toolbar that appears at the top
3. Drag to select your region (or click a window, or capture full screen)
4. The screenshot opens in the editor and is auto-copied to clipboard
5. Annotate, then **Copy** or **Save**

### Snip modes

- **Rectangular** — drag to select any rectangle
- **Freeform** — draw any shape by holding and dragging
- **Window** — hover over a window and click to capture it
- **Full Screen** — instantly captures everything

### Annotation tools

| Tool | Shortcut | Description |
|---|---|---|
| Pen | — | Freehand drawing |
| Highlighter | — | Semi-transparent color brush |
| Arrow | — | Draw arrows pointing to things |
| Rectangle | — | Draw rectangles |
| Ellipse | — | Draw circles/ellipses |
| Text | — | Click to add a text label |
| Eraser | — | Erase annotations |
| Undo | Ctrl+Z | Undo last action |
| Redo | Ctrl+Y | Redo last action |

## Building the .deb yourself

```bash
./build-deb.sh
sudo dpkg -i snipping-tool_1.0.0_all.deb
```

## Contributing

Pull requests are welcome. Please open an issue first for major changes.

## License

MIT License. See [LICENSE](LICENSE).
