import sys
import os
import traceback

IS_WINDOWS = sys.platform.startswith("win")

# ---------------------------------------------------------
# 1. BASE_DIR: Hier liegen Configs, Logs und die DB
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Wenn wir eine EXE sind, ist das der Ordner, in dem die .exe liegt
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Wenn wir ein Skript sind, ist das der Projektordner
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "ps2_master.db")


# ---------------------------------------------------------
# 2. ASSET PATH: Hier liegen Bilder und Sounds
# ---------------------------------------------------------
def get_asset_path(filename):
    """
    Findet Ressourcen zuverlässig, egal ob Development oder PyInstaller EXE.
    """
    if not filename:
        return ""

    # Pfadbereinigung (falls User "assets/bild.png" statt "bild.png" schreibt)
    filename = filename.replace("assets/", "").replace("assets\\", "")

    # Prüfen, ob wir im PyInstaller Temp-Ordner laufen
    if hasattr(sys, '_MEIPASS'):
        base_path = os.path.join(sys._MEIPASS, "assets")
    else:
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    return os.path.join(base_path, filename)


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
