#!/usr/bin/env bash
# install.sh — install Snipping Tool system-wide on Debian/Ubuntu/Mint

set -e

INSTALL_DIR="/opt/snipping-tool"
BIN="/usr/local/bin/snipping-tool"
DESKTOP="/usr/share/applications/com.linux.snippingtool.desktop"
ICON_DIR="/usr/share/icons/hicolor/scalable/apps"

echo "Installing Snipping Tool..."

# Check for required packages
MISSING=()
python3 -c "import gi" 2>/dev/null || MISSING+=("python3-gi")
python3 -c "from PIL import Image" 2>/dev/null || MISSING+=("python3-pil")
python3 -c "import cairo" 2>/dev/null || MISSING+=("python3-cairo")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Installing missing dependencies: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}" \
        gir1.2-gtk-3.0 \
        gir1.2-keybinder-3.0 \
        libkeybinder-3.0-0 \
        xclip
fi

# Copy application files
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r src/snipping_tool "$INSTALL_DIR/"

# Install entry point
sudo tee "$BIN" > /dev/null <<EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$INSTALL_DIR")
from snipping_tool.main import main
main()
EOF
sudo chmod +x "$BIN"

# Install desktop entry
sudo mkdir -p "$(dirname "$DESKTOP")"
sudo cp data/com.linux.snippingtool.desktop "$DESKTOP"

# Install icon
sudo mkdir -p "$ICON_DIR"
sudo cp data/icons/snipping-tool.svg "$ICON_DIR/snipping-tool.svg"
sudo gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true
sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo ""
echo "Done! Launch with:"
echo "  snipping-tool"
echo "  or press Ctrl+Shift+S (set in your system keyboard shortcuts)"
echo ""
echo "To set the global hotkey automatically:"
echo "  System Settings → Keyboard → Shortcuts → Custom → Add"
echo "  Name: Snipping Tool"
echo "  Command: snipping-tool"
echo "  Key: Ctrl+Shift+S"
