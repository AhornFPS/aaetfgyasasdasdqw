﻿# Better Planetside

A powerful overlay and stat tracking application for PlanetSide 2, featuring real-time statistics, customizable overlays, Twitch chat integration, and comprehensive player tracking.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)


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

### 🪟 Windows (Portable EXE)

1. **Download** the latest `Better-Planetside-Windows.zip` from the releases.
2. **Extract** the folder to a location of your choice.
3. **Run** `Better Planetside.exe`. 
   * *Note: No installation required. All dependencies are bundled.*
  
### 🪟 Windows (Installer)

1. **Download** the latest `Better-Planetside-Installer.exe` from the releases.
2. **Install** to a location of your choice.
3. **Run** `Better Planetside.exe`.
      * *Note: This is basically the same as the portable version, but gives you a way to uninstall and set shortcuts for you.*

### 🐧 Linux (.tar.gz)

Linux releases are distributed as a `.tar.gz` archive.

1. **Download** the latest `Better-Planetside-Linux-vX.Y.Z.tar.gz`.
2. **Extract** it:
   ```bash
   tar -xzf Better-Planetside-Linux-vX.Y.Z.tar.gz
   ```
3. **Go into** the extracted folder:
   ```bash
   cd "Better Planetside"
   ```
4. **Make the binary executable** (first run only):
   ```bash
   chmod +x "Better Planetside"
   ```
5. **Run it**:
   ```bash
   ./Better\ Planetside
   ```


## 📋 Requirements

### Windows
- Windows 10/11
- All dependencies are bundled in the executable

### Linux
- **Release archive (`.tar.gz`)**: Extract and run the included `Better Planetside` binary.
- **Important**: `xprop` must be installed on your system for overlay focus detection.

### PlanetSide 2
- **Game Mode**: Borderless Windowed (required for overlay visibility)


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
2. Enter the **Twitch channel name you want to get messages from**
3. Configure **chat display settings**
4. Chat messages appear in-game overlay

## 🛠️ Configuration

All settings are stored in a per-user `config.json` and can be modified through the UI:

- **Windows**: `%APPDATA%\\BetterPlanetside\\config.json`
- **Linux**: `$XDG_CONFIG_HOME/BetterPlanetside/config.json` (fallback: `~/.config/BetterPlanetside/config.json`)

- **Overlay Elements**: Position, size, colors, fonts
- **Events**: Custom kill streak events with images/sounds
- **Stats Widget**: Displayed statistics and formatting
- **Crosshair**: Custom crosshair images and positioning
- **Twitch**: Channel, message duration, font size

Schema migrations are applied automatically on startup (for example event-name renames), so existing user configs stay compatible across releases.

### Updates

- Use **Settings -> Check for updates** to query the latest GitHub release.
- The updater supports `manifest.json` release assets with platform-specific **patch** and **full** packages.
- Downloaded updates are staged under the user config directory in `updates/staging/` with checksum verification.
- Staged updates can be applied via **apply-on-restart** with rollback to a backup folder if swap fails.
- Apply scripts are written to user-writable paths:
  - Windows: `%APPDATA%\BetterPlanetside\updates\scripts\apply_update.ps1`
  - Linux: `$XDG_CONFIG_HOME/BetterPlanetside/updates/scripts/apply_update.sh` (fallback: `~/.config/BetterPlanetside/updates/scripts/apply_update.sh`)
- Apply logs are written to `updates/apply_update.log` in that same user config directory.


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




## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/cedric12354/BetterPlanetside/issues)
- **Discord**: [Ahorn #schieberegler, Cedricc #cedricc_tv]
- **Twitch**: [Ahorn](https://www.twitch.tv/ahorn)

## ⚠️ Disclaimer

This is a third-party application and is not affiliated with, endorsed by, or connected to Daybreak Game Company LLC or PlanetSide 2.

---

**Made with ❤️ for the PlanetSide 2 community**

