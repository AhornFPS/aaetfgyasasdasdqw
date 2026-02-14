#!/bin/bash
set -e

# Configuration
APP_NAME="Better Planetside"
APP_NAME_SLUG="better-planetside"
ICON_SOURCE="assets/christiandior.png" # Assuming this is the logo
BUILD_DIR="dist/Better Planetside"
APPDIR="AppDir"
OUTPUT_NAME="Better_Planetside-x86_64.AppImage"

echo "=== Creating AppImage for $APP_NAME ==="

# 1. Always build the application to ensure latest changes
echo "Cleaning previous distribution and rebuilding..."
rm -rf "$BUILD_DIR"
bash build-linux.sh

# 2. Prepare AppDir structure
echo "Setting up AppDir structure..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# 3. Copy application files
echo "Copying application files..."
cp -r "$BUILD_DIR" "$APPDIR/usr/bin/$APP_NAME_SLUG"

# 4. Setup Icon
echo "Setting up icon..."
if [ -f "$ICON_SOURCE" ]; then
    cp "$ICON_SOURCE" "$APPDIR/$APP_NAME_SLUG.png"
    cp "$ICON_SOURCE" "$APPDIR/.DirIcon"
else
    echo "Warning: Icon file $ICON_SOURCE not found. Using placeholder."
    touch "$APPDIR/$APP_NAME_SLUG.png"
fi

# 5. Create Desktop Entry
echo "Creating .desktop file..."
cat > "$APPDIR/$APP_NAME_SLUG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=$APP_NAME_SLUG
Icon=$APP_NAME_SLUG
Categories=Game;Utility;
Terminal=false
StartupNotify=true
EOF

# 6. Create AppRun script
echo "Creating AppRun script..."
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/bin/$APP_NAME_SLUG/Better Planetside" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# 7. Download appimagetool if needed
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Downloading appimagetool..."
    wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# 8. Build AppImage
echo "Building AppImage..."
# Use --appimage-extract-and-run to avoid FUSE issues in some environments
ARCH=x86_64 ./appimagetool-x86_64.AppImage --appimage-extract-and-run "$APPDIR" "$OUTPUT_NAME"

echo ""
echo "=== AppImage Created Successfully! ==="
echo "Output: $OUTPUT_NAME"
