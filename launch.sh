#!/bin/bash
# Better Planetside Launcher for Linux
# Ensures all dependencies are available before launching

APP_NAME="Better Planetside"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== $APP_NAME Launcher ==="
echo ""

# Check for required system commands
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ Missing required command: $1"
        return 1
    else
        echo "✅ Found: $1"
        return 0
    fi
}

# Check Python
if ! check_command python && ! check_command python3; then
    echo ""
    echo "Python is not installed. Please install Python 3.10 or higher."
    exit 1
fi

# Determine python command
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

# Check xprop (for focus detection)
if ! check_command xprop; then
    echo ""
    echo "⚠️  Warning: xprop not found. Focus detection may not work properly."
    echo "   Install with: sudo pacman -S xorg-xprop (Arch)"
    echo "              or: sudo apt install x11-utils (Debian/Ubuntu)"
fi

echo ""
echo "Checking Python modules..."

# Check if PyQt6 is available
$PYTHON_CMD -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ PyQt6 not found"
    echo ""
    echo "Please install system dependencies:"
    echo "  Arch/CachyOS: sudo pacman -S python-pyqt6 python-pyqt6-webengine"
    echo "  Ubuntu/Debian: sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine"
    echo ""
    echo "Or see INSTALL-LINUX.md for full installation instructions."
    exit 1
else
    echo "✅ PyQt6 found"
fi

echo ""
echo "Starting $APP_NAME..."
echo ""

# Launch the application
cd "$SCRIPT_DIR"
exec $PYTHON_CMD "Dior Client.py"
