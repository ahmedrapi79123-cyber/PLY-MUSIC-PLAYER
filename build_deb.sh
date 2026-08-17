#!/bin/bash
# Automation script to compile the PLY music player into a .deb package.
set -e

APP_NAME="ply-player"
VERSION="1.0.0"
ARCH="all"
DEB_FILE="${APP_NAME}_${VERSION}_${ARCH}.deb"
BUILD_DIR="ply_deb_build"

echo "=== PLY Debian Package Builder ==="
echo "Building: ${DEB_FILE}"

# 1. Clean previous build
rm -rf "$BUILD_DIR"
rm -f "$DEB_FILE"

# 2. Create directory structure
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/512x512/apps"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/128x128/apps"
mkdir -p "${BUILD_DIR}/usr/share/pixmaps"
mkdir -p "${BUILD_DIR}/usr/share/ply/assets"

# 3. DEBIAN/control — no pystray (not in apt), uses system libayatana or pystray optionally
cat > "${BUILD_DIR}/DEBIAN/control" << 'EOF'
Package: ply-player
Version: 1.0.0
Section: sound
Priority: optional
Architecture: all
Depends: python3 (>= 3.10),
 python3-tk,
 python3-gi,
 python3-gst-1.0,
 gstreamer1.0-plugins-base,
 gstreamer1.0-plugins-good,
 gstreamer1.0-plugins-ugly,
 python3-mutagen,
 python3-rich,
 python3-pil,
 python3-pil.imagetk,
 libayatana-appindicator3-1 | python3-pystray
Recommends: gstreamer1.0-libav
Maintainer: Ahmed <developer@ply.org>
Description: PLY - A modern command-line and graphical music player
 PLY is a lightweight music player powered by GStreamer with a Tkinter GUI,
 Rich terminal TUI, MPRIS2 desktop integration, and system tray support.
 .
 Features: playback of MP3/OGG/FLAC/WAV/Opus/M4A, playlist management,
 cover art display, dark/light themes, and MPRIS2 media key support.
EOF

# 4. Desktop entry
cat > "${BUILD_DIR}/usr/share/applications/io.github.ahmed.ply.desktop" << 'EOF'
[Desktop Entry]
Name=PLY Music Player
GenericName=Music Player
Comment=Simple and lightweight music player
Exec=/usr/bin/ply %U
Icon=io.github.ahmed.ply
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Player;Music;
Keywords=Music;Audio;Player;MP3;OGG;WAV;FLAC;
StartupNotify=true
MimeType=audio/mpeg;audio/ogg;audio/x-wav;audio/flac;audio/opus;audio/mp4;
EOF

# 5. Launcher script
cat > "${BUILD_DIR}/usr/bin/ply" << 'EOF'
#!/bin/bash
# PLY Music Player launcher

# Ensure D-Bus session bus is available (needed when launched from desktop)
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    BUS_SOCK="/run/user/$(id -u)/bus"
    if [ -S "$BUS_SOCK" ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=${BUS_SOCK}"
    fi
fi

# Ensure DISPLAY is set (for X11 / XFCE)
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    export DISPLAY=:0
fi

exec python3 /usr/share/ply/main.py "$@"
EOF

# 6. Copy Python source files
echo "Copying source files..."
cp main.py cli.py gui.py player.py playlist.py \
   library.py settings.py config.py themes.py \
   icons.py utils.py mpris.py \
   "${BUILD_DIR}/usr/share/ply/"

# Copy optional files if they exist
for f in requirements.txt LICENSE README.md; do
    [ -f "$f" ] && cp "$f" "${BUILD_DIR}/usr/share/ply/"
done

# 7. Copy assets
cp -r assets/. "${BUILD_DIR}/usr/share/ply/assets/"

# 8. Copy icons — source: assets/music.png (128x128 RGBA)
ICON_SRC="assets/music.png"

if [ ! -f "$ICON_SRC" ]; then
    echo "ERROR: Icon not found at $ICON_SRC"
    exit 1
fi

# 128x128 (original size)
cp "$ICON_SRC" "${BUILD_DIR}/usr/share/icons/hicolor/128x128/apps/io.github.ahmed.ply.png"
cp "$ICON_SRC" "${BUILD_DIR}/usr/share/pixmaps/io.github.ahmed.ply.png"

# 256x256 and 512x512 — resize with Python Pillow
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/512x512/apps"
python3 - "$ICON_SRC" \
    "${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps/io.github.ahmed.ply.png" \
    "${BUILD_DIR}/usr/share/icons/hicolor/512x512/apps/io.github.ahmed.ply.png" << 'PYEOF'
import sys
from PIL import Image
src = sys.argv[1]
for size, dest in [(256, sys.argv[2]), (512, sys.argv[3])]:
    img = Image.open(src).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)
    img.save(dest, "PNG")
    print(f"  Created {size}x{size}: {dest}")
PYEOF

# 9. postinst: update icon cache and desktop database after install
cat > "${BUILD_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
fi
EOF

# 10. Set correct permissions
chmod 755 "${BUILD_DIR}/usr/bin/ply"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"
chmod -R 755 "${BUILD_DIR}/usr/share/ply"
find "${BUILD_DIR}/usr/share/ply" -name "*.py" -exec chmod 644 {} \;
chmod 644 "${BUILD_DIR}/DEBIAN/control"
chmod 644 "${BUILD_DIR}/usr/share/applications/io.github.ahmed.ply.desktop"

# 11. Build the .deb
echo "Building .deb package..."
dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${DEB_FILE}"

# 12. Cleanup
rm -rf "${BUILD_DIR}"

echo ""
echo "✅ Package ready: ${DEB_FILE}"
echo ""
echo "To install:  sudo dpkg -i ${DEB_FILE}"
echo "To run:      ply"
