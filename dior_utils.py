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
# 1. BASE_DIR: Configs, logs, and the DB are located here
# ---------------------------------------------------------
# Robust detection: Check for PyInstaller flag OR AppImage environment variables
IS_PACKAGED = getattr(sys, 'frozen', False) or 'APPDIR' in os.environ

if IS_PACKAGED:
    BASE_DIR = get_user_data_dir()
    if sys.stdout:
        print(f"DEBUG: PACKAGED MODE DETECTED. BASE_DIR: {BASE_DIR}")
        sys.stdout.flush()
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "ps2_master.db")
if sys.stdout:
    print(f"DEBUG: FINAL DB_PATH: {DB_PATH}")
    sys.stdout.flush()

# ---------------------------------------------------------
# 2. ASSETS_DIR: Images and sounds are located here (Read-Only)
# ---------------------------------------------------------
if hasattr(sys, '_MEIPASS'):
    ASSETS_DIR = os.path.join(sys._MEIPASS, "assets")
else:
    ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

IMAGES_DIR = os.path.join(ASSETS_DIR, "Images")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "Sounds")
CROSSHAIR_DIR = os.path.join(ASSETS_DIR, "Crosshair")

# Ensure subfolders exist (if writable)
try:
    if not IS_PACKAGED:
        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(SOUNDS_DIR, exist_ok=True)
        os.makedirs(CROSSHAIR_DIR, exist_ok=True)
except Exception:
    pass


# ---------------------------------------------------------
# 3. ASSET PATH: Images and sounds are located here
# ---------------------------------------------------------
def get_asset_path(filename):
    """
    Reliably finds resources, whether in development or PyInstaller EXE.
    Intelligent routing to 'Images' or 'Sounds' subfolders.
    """
    if not filename:
        return ""

    # Path cleaning
    filename = filename.replace("assets/", "").replace("assets\\", "")
    filename = filename.replace("Images/", "").replace("Images\\", "")
    filename = filename.replace("Sounds/", "").replace("Sounds\\", "")
    filename = filename.replace("Crosshair/", "").replace("Crosshair\\", "")

    lower_f = filename.lower()

    # 1. SPECIAL CASE: Crosshairs
    if lower_f.startswith("ch_") or "crosshair" in lower_f:
        return os.path.join(CROSSHAIR_DIR, filename)

    # 2. Images
    if lower_f.endswith(('.png', '.jpg', '.jpeg', '.gif')):
        return os.path.join(IMAGES_DIR, filename)
    elif lower_f.endswith(('.mp3', '.ogg', '.wav')):
        return os.path.join(SOUNDS_DIR, filename)

    return os.path.join(ASSETS_DIR, filename)


# ---------------------------------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------------------------------
def clean_path(path_str):
    """Removes 'No file selected' and empty paths, returns only filenames."""
    if not path_str or "No file selected" in path_str:
        return ""
    return os.path.basename(path_str)


def log_exception(exc_type, exc_value, exc_traceback):
    """Global error handler for log files."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Write error to file
    error_file = os.path.join(BASE_DIR, "crash_log.txt")
    with open(error_file, "a") as f:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

    # Output error to console as well
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
