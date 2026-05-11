#!/usr/bin/env bash
# build-deb.sh — build the .deb package

set -e

VERSION="1.0.0"
PKG="snipping-tool"
DEB_DIR="packaging/debian"

echo "Preparing package structure..."

# Copy application source
mkdir -p "$DEB_DIR/opt/snipping-tool"
cp -r src/snipping_tool "$DEB_DIR/opt/snipping-tool/"

# Install entry point wrapper
mkdir -p "$DEB_DIR/usr/bin"
cat > "$DEB_DIR/usr/bin/snipping-tool" << 'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/snipping-tool")
from snipping_tool.main import main
main()
EOF
chmod +x "$DEB_DIR/usr/bin/snipping-tool"

# Desktop file
mkdir -p "$DEB_DIR/usr/share/applications"
cp data/com.linux.snippingtool.desktop "$DEB_DIR/usr/share/applications/"

# Icon
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/scalable/apps"
cp data/icons/snipping-tool.svg "$DEB_DIR/usr/share/icons/hicolor/scalable/apps/"

# Fix permissions
chmod 755 "$DEB_DIR/DEBIAN/postinst"
chmod 755 "$DEB_DIR/DEBIAN/prerm"

# Build
echo "Building .deb..."
dpkg-deb --build "$DEB_DIR" "${PKG}_${VERSION}_all.deb"

echo ""
echo "Built: ${PKG}_${VERSION}_all.deb"
echo "Install with: sudo dpkg -i ${PKG}_${VERSION}_all.deb"
echo "Fix deps if needed: sudo apt-get install -f"
