#!/bin/bash
set -euo pipefail

# Configuration
APP_NAME="Better Planetside"
APP_NAME_SLUG="better-planetside"
ICON_SOURCE="assets/Images/BetterPlannetsideIcon.png"
BUILD_DIR="dist/Better Planetside"
APPDIR="AppDir"
DEFAULT_RELEASE_REPO="cedric12354/Better-Planetside"

RELEASE_REPO="${RELEASE_REPO:-$DEFAULT_RELEASE_REPO}"
CHANNEL="${CHANNEL:-stable}"
MIN_SUPPORTED="${MIN_SUPPORTED:-}"
TAG="${TAG:-}"
UPLOAD_RELEASE="${UPLOAD_RELEASE:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"

usage() {
    cat <<EOF
Usage: ./create-appimage.sh [options]

Builds Linux artifacts, generates manifest.linux.json, and optionally uploads assets.

Options:
  --release-repo OWNER/REPO     GitHub releases repo (default: ${DEFAULT_RELEASE_REPO})
  --channel NAME                Manifest channel (default: stable)
  --min-supported VERSION       Manifest min_supported value (optional)
  --tag TAG                     Release tag, e.g. v1.2.0 (default: v<version>)
  --upload-release              Upload AppImage, tar.gz and manifest via gh
  --skip-build                  Skip build-linux.sh and package current dist output
  --help                        Show this help

Environment alternatives:
  RELEASE_REPO, CHANNEL, MIN_SUPPORTED, TAG, UPLOAD_RELEASE, SKIP_BUILD
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release-repo)
            RELEASE_REPO="$2"
            shift 2
            ;;
        --channel)
            CHANNEL="$2"
            shift 2
            ;;
        --min-supported)
            MIN_SUPPORTED="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --upload-release)
            UPLOAD_RELEASE=1
            shift
            ;;
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

echo "=== Creating Linux release artifacts for $APP_NAME ==="

# 1. Build
if [[ "$SKIP_BUILD" == "1" ]]; then
    echo "Skipping build-linux.sh (--skip-build)."
else
    echo "Cleaning previous distribution and rebuilding..."
    rm -rf "$BUILD_DIR"
    bash build-linux.sh
fi

# 2. Resolve version and output names
VERSION=$(grep -oP 'VERSION = "\K[0-9]+\.[0-9]+\.[0-9]+' version.py)
if [[ -z "$TAG" ]]; then
    TAG="v${VERSION}"
fi
OUTPUT_NAME="Better_Planetside-v${VERSION}-x86_64.AppImage"
LINUX_TAR="Better-Planetside-Linux-v${VERSION}.tar.gz"
MANIFEST_PATH="manifest.linux.json"
BASE_URL="https://github.com/${RELEASE_REPO}/releases/download/${TAG}"

echo ""
echo "Packaging version $VERSION..."

# 3. Prepare AppDir structure
echo "Setting up AppDir structure..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# 4. Copy application files
echo "Copying application files..."
cp -r "$BUILD_DIR" "$APPDIR/usr/bin/$APP_NAME_SLUG"

# 5. Setup Icon
echo "Setting up icon..."
if [ -f "$ICON_SOURCE" ]; then
    cp "$ICON_SOURCE" "$APPDIR/$APP_NAME_SLUG.png"
    cp "$ICON_SOURCE" "$APPDIR/.DirIcon"
else
    echo "Warning: Icon file $ICON_SOURCE not found. Using placeholder."
    touch "$APPDIR/$APP_NAME_SLUG.png"
fi

# 6. Create Desktop Entry
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
X-AppImage-Version=$VERSION
EOF

# 7. Create AppRun script
echo "Creating AppRun script..."
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
unset PYTHONPATH
unset PYTHONHOME
exec "\${HERE}/usr/bin/$APP_NAME_SLUG/Better Planetside" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# 8. Download AppImage tools if needed
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Downloading appimagetool..."
    wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# 8.5 Download runtime if needed (to avoid appimagetool hanging on download)
if [ ! -f "runtime-x86_64" ] || [ $(stat -c%s "runtime-x86_64" 2>/dev/null || echo 0) -lt 800000 ]; then
    echo "Downloading AppImage runtime..."
    RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
    if command -v aria2c >/dev/null 2>&1; then
        aria2c -x 16 -s 16 -o "runtime-x86_64" "$RUNTIME_URL" --allow-overwrite=true
    else
        wget --tries=10 --timeout=30 "$RUNTIME_URL" -O "runtime-x86_64"
    fi
    
    if [ $(stat -c%s "runtime-x86_64" 2>/dev/null || echo 0) -lt 800000 ]; then
        echo "ERROR: AppImage runtime download failed or is incomplete."
        exit 1
    fi
    chmod +x runtime-x86_64
fi

# 9. Build AppImage
echo "Building AppImage..."
# Use --runtime-file to skip appimagetool's internal download
ARCH=x86_64 ./appimagetool-x86_64.AppImage --appimage-extract-and-run --runtime-file runtime-x86_64 "$APPDIR" "$OUTPUT_NAME"

# 10. Build Linux updater archive (.tar.gz)
echo "Creating Linux updater archive..."
tar -czf "$LINUX_TAR" -C dist "Better Planetside"

# 11. Generate Linux-only manifest
echo "Generating manifest at ${MANIFEST_PATH}..."
manifest_cmd=(
    python generate_release_manifest.py
    --version "$VERSION"
    --base-url "$BASE_URL"
    --asset "${CHANNEL},linux,full,${LINUX_TAR}"
    --output "$MANIFEST_PATH"
)
if [[ -n "$MIN_SUPPORTED" ]]; then
    manifest_cmd+=(--min-supported "$MIN_SUPPORTED")
fi
"${manifest_cmd[@]}"

# 12. Cleanup
echo "Cleaning up build artifacts..."
rm -rf "$APPDIR"
rm -rf build dist build_env

# 13. Optional upload
if [[ "$UPLOAD_RELEASE" == "1" ]]; then
    if ! command -v gh >/dev/null 2>&1; then
        echo "ERROR: gh CLI is required for --upload-release."
        exit 1
    fi

    echo "Uploading assets to ${RELEASE_REPO} (${TAG})..."
    upload_args=("$LINUX_TAR" "$MANIFEST_PATH")

    gh release upload "$TAG" "${upload_args[@]}" --repo "$RELEASE_REPO" --clobber
fi

echo ""
echo "=== Linux Release Artifacts Ready ==="
echo "Version:            $VERSION"
echo "Tag:                $TAG"
echo "Release repo:       $RELEASE_REPO"
echo "AppImage:           $OUTPUT_NAME"
echo "Linux updater tar:  $LINUX_TAR"
echo "Manifest:           $MANIFEST_PATH"
echo "Base URL:           $BASE_URL"
if [[ "$UPLOAD_RELEASE" == "1" ]]; then
    echo "Upload:             completed"
else
    echo "Upload:             skipped (use --upload-release)"
fi
echo ""
