# Better Planetside

A powerful overlay and stat tracking application for PlanetSide 2, featuring real-time statistics, customizable overlays, Twitch chat integration, and comprehensive player tracking.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

### 🎯 In-Game Overlay
- **Real-time Stats Display**: K/D, KPM, HSR, and session statistics
- **Kill Streak Tracker**: Visual and audio feedback for multi-kills and streaks
- **Custom Crosshair**: Fully customizable crosshair overlay
- **Kill Feed**: Track your kills, deaths, and special events
- **Twitch Chat Integration**: View Twitch chat messages in-game

### 📊 Statistics & Tracking
- **Live Session Stats**: Track your performance in real-time
- **Character Management**: Monitor multiple characters across servers
- **Dashboard**: Visualize player population and faction balance
- **Database Integration**: Local caching for fast lookups

### 🎨 Customization
- **Fully Configurable Overlay**: Position, size, colors, and opacity
- **Custom Events**: Create custom kill streak events with images and sounds
- **Edit Mode**: Drag-and-drop positioning for all overlay elements
- **Theme Support**: Dark mode UI with customizable colors

## 🚀 Quick Start

### Windows

1. **Download** the latest release
2. **Extract** the archive
3. **Run** `Better Planetside.exe`

### Linux

#### Option 1: Run from Source (Recommended)

```bash
# Install system dependencies (Arch/CachyOS)
sudo pacman -S python-pyqt6 python-pyqt6-webengine python-requests \
               python-websockets python-pillow python-pygame python-dotenv xorg-xprop

# Run the launcher
./launch.sh
```

#### Option 2: Build Standalone Executable

```bash
# Build the application
./build-linux.sh

# Run from dist folder
cd dist/Better\ Planetside
./Better\ Planetside
```

**For other Linux distributions**, see [INSTALL-LINUX.md](INSTALL-LINUX.md)

## 📋 Requirements

### Windows
- Windows 10/11
- All dependencies are bundled in the executable

### Linux
- Python 3.10 or higher
- PyQt6 and PyQt6-WebEngine
- xprop (for window focus detection)
- See [INSTALL-LINUX.md](INSTALL-LINUX.md) for complete list

### PlanetSide 2
- **Game Mode**: Borderless Windowed (required for overlay visibility)
- **API Key**: Optional, for enhanced features

## 🎮 Usage

### First Launch

1. **Start the application**
2. **Add your character** in the Characters tab
3. **Configure overlay** in the Overlay tab
4. **Launch PlanetSide 2** in Borderless Windowed mode
5. **Overlay appears automatically** when the game is detected

### Overlay Controls

- **Edit Mode**: Toggle in Overlay settings to reposition elements
- **Test Mode**: Preview overlay elements without being in-game
- **Master Switch**: Enable/disable the entire overlay

### Twitch Integration

1. Go to **Settings** → **Twitch**
2. Enter your **Twitch channel name**
3. Configure **chat display settings**
4. Chat messages appear in-game overlay

## 🛠️ Configuration

All settings are stored in `config.json` and can be modified through the UI:

- **Overlay Elements**: Position, size, colors, fonts
- **Events**: Custom kill streak events with images/sounds
- **Stats Widget**: Displayed statistics and formatting
- **Crosshair**: Custom crosshair images and positioning
- **Twitch**: Channel, message duration, font size

## 📁 Project Structure

```
BetterPlanetside/
├── Dior Client.py           # Main application
├── overlay_window.py        # Overlay rendering
├── census_worker.py         # PlanetSide 2 API integration
├── twitch_worker.py         # Twitch chat integration
├── dashboard_qt.py          # Dashboard UI
├── characters_qt.py         # Character management
├── settings_qt.py           # Settings UI
├── overlay_config_qt.py     # Overlay configuration
├── dior_utils.py            # Utility functions
├── dior_db.py               # Database handler
├── assets/                  # Images, sounds, fonts
├── requirements.txt         # Python dependencies
├── launch.sh                # Linux launcher
├── build-linux.sh           # Linux build script
└── Better Planetside.spec   # PyInstaller configuration
```

## 🐛 Troubleshooting

### Overlay not visible
- Ensure PlanetSide 2 is in **Borderless Windowed** mode
- Check that **Master Switch** is enabled in Overlay settings
- On Linux, verify `xprop` is installed

### Stats not updating
- Verify your **character name** is correct
- Check **internet connection** to Daybreak API
- Look for errors in the application log

### Twitch chat not working
- Verify **channel name** is correct (without #)
- Check **internet connection**
- Ensure Twitch channel exists and is live

### Linux: Overlay moves with main window
- The application should automatically use XWayland
- If issues persist, run: `QT_QPA_PLATFORM=xcb python "Dior Client.py"`

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **PlanetSide 2 Census API** - Daybreak Games
- **PyQt6** - GUI framework
- **Black Ops One Font** - James Grieshaber (SIL Open Font License)
- **Community** - For feedback and testing

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/BetterPlanetside/issues)
- **Discord**: [Your Discord Server]
- **Twitch**: [Your Twitch Channel]

## ⚠️ Disclaimer

This is a third-party application and is not affiliated with, endorsed by, or connected to Daybreak Game Company LLC or PlanetSide 2. Use at your own risk.

---

**Made with ❤️ for the PlanetSide 2 community**
