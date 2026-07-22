#!/bin/bash
# Automation script to compile the PLY music player into a .deb package.
set -e

echo "Starting PLY Debian Package build..."

# 1. Clean previous build items
rm -rf ply_deb_build
rm -f ply-player_1.0.0_all.deb

# 2. Build folder structure
mkdir -p ply_deb_build/DEBIAN
mkdir -p ply_deb_build/usr/bin
mkdir -p ply_deb_build/usr/share/applications
mkdir -p ply_deb_build/usr/share/pixmaps
mkdir -p ply_deb_build/usr/share/ply/assets

# 3. Create packaging control configuration
cat << 'EOF' > ply_deb_build/DEBIAN/control
Package: ply-player
Version: 1.0.0
Section: sound
Priority: optional
Architecture: all
Depends: python3, python3-tk, python3-gi, python3-mutagen, python3-rich, python3-pil, python3-pil.imagetk
Maintainer: PLY Developer <developer@ply.org>
Description: A professional, modern command-line and graphical music player.
EOF

# 4. Create Desktop shortcut launcher
cat << 'EOF' > ply_deb_build/usr/share/applications/ply.desktop
[Desktop Entry]
Name=PLY Music Player
Comment=A modern CLI and GUI music player
Exec=/usr/bin/ply --gui
Icon=music
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Player;
EOF

# 5. Create launcher execution script
cat << 'EOF' > ply_deb_build/usr/bin/ply
#!/bin/bash
# PLY Music Player launcher
# Ensure DBUS session and display are available (needed when launched from desktop)
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    # Try to find the running user session bus
    SESSION_FILE=$(ls /run/user/$(id -u)/bus 2>/dev/null | head -1)
    if [ -n "$SESSION_FILE" ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
    fi
fi

if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

exec python3 /usr/share/ply/main.py "$@"
EOF

# 6. Copy sources and configurations
cp main.py cli.py gui.py player.py playlist.py library.py settings.py config.py themes.py icons.py utils.py mpris.py requirements.txt LICENSE README.md ply_deb_build/usr/share/ply/
cp -r assets/* ply_deb_build/usr/share/ply/assets/
cp assets/music.png ply_deb_build/usr/share/pixmaps/music.png

# 7. Apply standard POSIX permissions
chmod 755 ply_deb_build/usr/bin/ply
chmod -R 755 ply_deb_build/usr/share/ply
chmod 755 ply_deb_build/DEBIAN
chmod 644 ply_deb_build/DEBIAN/control
chmod 644 ply_deb_build/usr/share/applications/ply.desktop
chmod 644 ply_deb_build/usr/share/pixmaps/music.png

# 8. Compile the Debian package
dpkg-deb --build --root-owner-group ply_deb_build ply-player_1.0.0_all.deb

# 9. Clean up temporary files
rm -rf ply_deb_build

echo "Debian package created: ply-player_1.0.0_all.deb"
