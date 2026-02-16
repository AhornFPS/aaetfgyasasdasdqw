# Better Planetside

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

### 🐧 Linux (AppImage)

The easiest way to run Better Planetside on any Linux distribution.

1. **Download** the latest `Better_Planetside-x86_64.AppImage`.
2. **Make it executable**:
   ```bash
   chmod +x Better_Planetside-x86_64.AppImage
   ```
3. **Run it**:
   ```bash
   ./Better_Planetside-x86_64.AppImage
   ```

#### Alternative: Running from Source
If you prefer to run from source or need to develop:

1. **Setup environment**: Create a `.env` file in the project root with your Census Service ID:
   ```env
   # Your census ID (Don't forget the s: at the beginning)
   CENSUS_S_ID=s:YourCensusIDhere
   ```
2. **Run**:
   ```bash
   ./launch.sh
   ```
*Requires `python` and `pip` dependencies installed.*

#### Alternative: Building your own AppImage
You can build Linux release artifacts (AppImage + updater `.tar.gz` + `manifest.json`) using:
```bash
./create-appimage.sh
```

Include Windows artifacts in a combined manifest and upload directly to a GitHub Release:
```bash
./create-appimage.sh \
  --release-repo cedric12354/Better-Planetside \
  --tag v1.2.0 \
  --min-supported 1.1.0 \
  --windows-full /path/to/Better-Planetside-Windows-v1.2.0.zip \
  --upload-release
```

### Release Automation (Windows -> Linux)

Windows step (build, upload Windows assets, commit/push `manifest.windows.json`):
```bat
release-windows-oneclick.bat --patch Better-Planetside-1.1.0-to-1.2.0.patch.zip --patch-from 1.1.0
```

Linux step (pull, build/upload Linux assets, publish combined `manifest.json`):
```bash
./release-linux-oneclick.sh
```

## 📋 Requirements

### Windows
- Windows 10/11
- All dependencies are bundled in the executable

### Linux
- **AppImage**: Self-contained. Just needs `xprop` installed on your system for focus detection.
- **From Source**: Requires Python 3.10+, PyQt6, pygame, and other dependencies listed in [INSTALL-LINUX.md](INSTALL-LINUX.md).

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
- A release manifest template is included in `update_manifest.example.json`.
- Current auto-apply expects archive artifacts (`.zip` on Windows, `.zip`/`.tar.gz` on Linux).

Generate a release manifest with checksums:

```bash
python generate_release_manifest.py \
  --version 1.2.0 \
  --min-supported 1.1.0 \
  --base-url https://github.com/cedric12354/Better-Planetside/releases/download/v1.2.0 \
  --asset stable,windows,full,Better-Planetside-Windows-v1.2.0.zip \
  --asset stable,linux,full,dist/Better-Planetside-Linux-v1.2.0.tar.gz \
  --output manifest.json
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




## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/BetterPlanetside/issues)
- **Discord**: [Ahorn #schieberegler, Cedricc #cedricc_tv]
- **Twitch**: [Ahorn](https://www.twitch.tv/ahorn)

## ⚠️ Disclaimer

This is a third-party application and is not affiliated with, endorsed by, or connected to Daybreak Game Company LLC or PlanetSide 2.

---

**Made with ❤️ for the PlanetSide 2 community**
