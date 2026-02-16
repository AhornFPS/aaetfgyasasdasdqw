#!/bin/bash
# Build script for Better Planetside on Linux
# Creates a standalone executable using PyInstaller
# Reads version from version.py (version bumping is done via build-windows.bat)

set -e  # Exit on error

echo "=== Better Planetside Linux Build Script ==="
echo ""

# ---------------------------------------------------------
# 1. READ VERSION
# ---------------------------------------------------------
VERSION_FILE="version.py"

if [ ! -f "$VERSION_FILE" ]; then
    echo "ERROR: $VERSION_FILE not found!"
    exit 1
fi

VERSION=$(grep -oP 'VERSION = "\K[0-9]+\.[0-9]+\.[0-9]+' "$VERSION_FILE")
echo "Building version: $VERSION"

# ---------------------------------------------------------
# 2. BUILD ENVIRONMENT
# ---------------------------------------------------------

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Creating virtual environment..."
    python -m venv build_env
    source build_env/bin/activate
else
    echo "Using existing virtual environment: $VIRTUAL_ENV"
fi

# Install build dependencies
echo "Installing build dependencies..."
pip install --upgrade pip
pip install pyinstaller

# Install application dependencies
echo "Installing application dependencies..."
pip install -r requirements.txt

# ---------------------------------------------------------
# 3. BUILD
# ---------------------------------------------------------

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist "Better Planetside.spec.backup"

# Build with PyInstaller
echo "Building executable..."
pyinstaller "Better Planetside.spec" --clean

echo ""
echo "=== Build Complete ==="
echo "Version: $VERSION"
echo "Executable location: dist/Better Planetside/Better Planetside"
echo ""
echo "Optional Linux archive + manifest:"
echo "  cd dist && tar -czf Better-Planetside-Linux-v${VERSION}.tar.gz 'Better Planetside'"
echo "  python generate_release_manifest.py --version ${VERSION} --asset stable,linux,full,dist/Better-Planetside-Linux-v${VERSION}.tar.gz --output manifest.linux.json"
echo ""
echo "To create a distributable archive:"
echo "  cd dist && tar -czf Better-Planetside-Linux-v${VERSION}.tar.gz 'Better Planetside'"
echo ""
