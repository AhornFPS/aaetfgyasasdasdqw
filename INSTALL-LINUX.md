# Better Planetside - Linux Installation Guide

## System Requirements

### Required Packages (Install via package manager)
```bash
# For Arch/CachyOS/Manjaro
sudo pacman -S python-pyqt6 python-pyqt6-webengine python-requests python-websockets \
               python-pillow python-pygame python-dotenv xorg-xprop

# For Ubuntu/Debian
sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine python3-requests python3-websockets \
                 python3-pil python3-pygame python3-dotenv x11-utils

# For Fedora
sudo dnf install python3-qt6 python3-qt6-webengine python3-requests python3-websockets \
                 python3-pillow python3-pygame python3-dotenv xorg-x11-utils
```

### Optional (for building from source)
```bash
# Arch/CachyOS
sudo pacman -S python-pyinstaller

# Ubuntu/Debian
sudo apt install pyinstaller

# Fedora
sudo dnf install pyinstaller
```

## Installation Methods

### Method 1: Run from Source (Recommended for Development)

1. **Clone or extract the repository**
   ```bash
   cd BetterPlanetside
   ```

2. **Install system dependencies** (see above)

3. **Run the application**
   ```bash
   python "Dior Client.py"
   ```

### Method 2: Build Standalone Executable

1. **Install build dependencies**
   ```bash
   pip install pyinstaller
   ```

2. **Run the build script**
   ```bash
   ./build-linux.sh
   ```

3. **The executable will be in `dist/Better Planetside/`**
   ```bash
   cd dist/Better\ Planetside
   ./Better\ Planetside
   ```

4. **Create distributable archive**
   ```bash
   cd dist
   tar -czf Better-Planetside-Linux.tar.gz "Better Planetside"
   ```

### Method 3: Install via pip (Virtual Environment)

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run**
   ```bash
   python "Dior Client.py"
   ```

## Distribution

### For End Users (Standalone Package)

Create a distributable package:

```bash
./build-linux.sh
cd dist
tar -czf Better-Planetside-Linux-x86_64.tar.gz "Better Planetside"
```

**Users can then:**
1. Extract: `tar -xzf Better-Planetside-Linux-x86_64.tar.gz`
2. Run: `cd "Better Planetside" && ./Better\ Planetside`

### For Developers (Source Distribution)

Share the entire repository with:
- `requirements.txt` - Python dependencies
- `INSTALL-LINUX.md` - This installation guide
- Source files

## Troubleshooting

### "ModuleNotFoundError: No module named 'PyQt6'"
Install system packages (see Required Packages above)

### "xprop: command not found"
Install `xorg-xprop` (Arch) or `x11-utils` (Debian/Ubuntu)

### Overlay doesn't appear over game
- Make sure the game is running in **Borderless Windowed** mode
- Try running with: `QT_QPA_PLATFORM=xcb python "Dior Client.py"`

### Font issues
The Black Ops One font is bundled with the application and loads automatically.

## Notes

- **XWayland**: The application automatically uses XWayland on Linux for better overlay compatibility
- **Proton/Steam**: Works with Proton games when they're in Borderless Windowed mode
- **Focus Detection**: Uses `xprop` to detect when the game is in focus
