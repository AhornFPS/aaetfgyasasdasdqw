import sys
import os
import traceback

IS_WINDOWS = sys.platform.startswith("win")

def get_user_data_dir():
    app_name = "BetterPlanetside"
    # Try to find a writable base
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
    else:
        # Standard Linux XDG path
        base = os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.expanduser("~/.config")
    
    data_dir = os.path.join(base, app_name)
    
    # Ensure the directory exists
    try:
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    except:
        # Emergency fallback to home
        fallback = os.path.expanduser("~/.BetterPlanetside_fallback")
        os.makedirs(fallback, exist_ok=True)
        return fallback

# ---------------------------------------------------------
# 1. BASE_DIR: Hier liegen Configs, Logs und die DB
# ---------------------------------------------------------
# Robust detection: Check for PyInstaller flag OR AppImage environment variables
IS_PACKAGED = getattr(sys, 'frozen', False) or 'APPDIR' in os.environ

if IS_PACKAGED:
    BASE_DIR = get_user_data_dir()
    print(f"DEBUG: PACKAGED MODE DETECTED. BASE_DIR: {BASE_DIR}")
    sys.stdout.flush() 
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "ps2_master.db")
print(f"DEBUG: FINAL DB_PATH: {DB_PATH}")
sys.stdout.flush()

# ---------------------------------------------------------
# 2. ASSETS_DIR: Hier liegen Bilder und Sounds (Read-Only)
# ---------------------------------------------------------
if hasattr(sys, '_MEIPASS'):
    ASSETS_DIR = os.path.join(sys._MEIPASS, "assets")
else:
    ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


# ---------------------------------------------------------
# 3. ASSET PATH: Hier liegen Bilder und Sounds
# ---------------------------------------------------------
def get_asset_path(filename):
    """
    Findet Ressourcen zuverlässig, egal ob Development oder PyInstaller EXE.
    """
    if not filename:
        return ""

    # Pfadbereinigung (falls User "assets/bild.png" statt "bild.png" schreibt)
    filename = filename.replace("assets/", "").replace("assets\\", "")

    return os.path.join(ASSETS_DIR, filename)


# ---------------------------------------------------------
# 3. HELPER FUNKTIONEN
# ---------------------------------------------------------
def clean_path(path_str):
    """Entfernt 'No file selected' und leere Pfade, gibt nur Dateinamen zurück."""
    if not path_str or "No file selected" in path_str:
        return ""
    return os.path.basename(path_str)


def log_exception(exc_type, exc_value, exc_traceback):
    """Globaler Error-Handler für Log-Dateien."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Fehler in Datei schreiben
    error_file = os.path.join(BASE_DIR, "crash_log.txt")
    with open(error_file, "a") as f:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

    # Fehler auch in Konsole ausgeben
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
