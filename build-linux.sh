#!/bin/bash
# Build script for Better Planetside on Linux
# Creates a standalone executable using PyInstaller

set -e  # Exit on error

echo "=== Better Planetside Linux Build Script ==="
echo ""

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

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist "Better Planetside.spec.backup"

# Build with PyInstaller
echo "Building executable..."
pyinstaller "Better Planetside.spec" --clean

echo ""
echo "=== Build Complete ==="
echo "Executable location: dist/Better Planetside/Better Planetside"
echo ""
echo "To create a distributable archive:"
echo "  cd dist && tar -czf Better-Planetside-Linux.tar.gz 'Better Planetside'"
echo ""
