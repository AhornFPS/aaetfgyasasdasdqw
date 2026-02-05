import os
import sys
import ctypes

# DPI Awareness erzwingen, bevor GUI-Module geladen werden
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 1 = Process_System_DPI_Aware
except Exception:
    pass

# Qt-Skalierung fixen
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
import shutil
import subprocess
import time
import requests
import threading
import json
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from queue import Queue, Empty
from PIL import Image, ImageTk, ImageSequence, ImageGrab
import pydirectinput
import sqlite3
import dashboard_qt  # Die neue Datei muss im gleichen Ordner liegen!
import launcher_qt
import characters_qt
import settings_qt
import overlay_config_qt
from census_worker import CensusWorker, S_ID, PS2_DETECTION
from overlay_window import QtOverlay, PathDrawingLayer, OverlaySignals
from dior_utils import BASE_DIR, get_asset_path, log_exception, clean_path
from dior_db import DatabaseHandler

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QMainWindow, QListWidget, QStackedWidget, QGraphicsDropShadowEffect,
    QColorDialog, QFileDialog # <--- QColorDialog und QFileDialog sicherstellen
)
from PyQt6.QtGui import (

    QPixmap,
    QColor,
    QPainter,
    QPen,
    QBrush,
    QTransform,
    QMovie



)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QObject,
    QTimer,
    QPoint,
    QSize
)

DUMMY_STATS_HTML = """
<div style="font-family: 'Black Ops One', sans-serif; font-weight: bold; color: #00f2ff; 
            text-shadow: 1px 1px 2px #000; text-align: center; font-size: 22px; white-space: nowrap;">
    KD: <span style="color: #00ff00;">3.50</span> &nbsp;&nbsp;
    K: <span style="color: white;">42</span> &nbsp;&nbsp;
    D: <span style="color: white;">12</span> &nbsp;&nbsp;
    HSR: <span style="color: #ffcc00;">45%</span> &nbsp;&nbsp;
    KPM: <span style="color: #ffcc00;">1.2</span> &nbsp;&nbsp;
    <span style="color: #aaa;">TIME: 01:23</span>
</div>
"""


class WorkerSignals(QObject):
    # Signal: Erfolg (True/False), Name, Fehlernachricht
    add_char_finished = pyqtSignal(bool, str, str)
    # NEUES SIGNAL für den Monitor
    game_status_changed = pyqtSignal(bool)  # True = Start, False = Stop


class DiorMainHub(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("DIOR CLIENT - PS2 MASTER")
        self.resize(1400, 900)

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SEITENLEISTE (Navigation) ---
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(200)
        self.nav_list.setObjectName("NavBar")
        # WICHTIG: Die Reihenfolge muss mit dem Stack übereinstimmen!
        self.nav_list.addItems(["DASHBOARD", "LAUNCHER", "CHARACTERS", "OVERLAY", "SETTINGS"])

        self.nav_list.setStyleSheet("""
            QListWidget { background-color: #1a1a1a; border: none; outline: none; }
            QListWidget::item { padding: 25px; color: #4a6a7a; font-family: 'Consolas'; font-weight: bold; }
            QListWidget::item:selected { background-color: #252525; color: #00f2ff; border-left: 4px solid #00f2ff; }
        """)

        # --- CONTENT BEREICH (Stacked Widget) ---
        self.stack = QStackedWidget()

        # Wir holen uns die Fenster aus dem Controller (DiorClientGUI)
        self.stack.addWidget(self.controller.dash_window)  # Index 0
        self.stack.addWidget(self.controller.launcher_win)  # Index 1
        self.stack.addWidget(self.controller.char_win)  # Index 2
        self.stack.addWidget(self.controller.ovl_config_win)  # Index 3
        self.stack.addWidget(self.controller.settings_win)  # Index 4

        main_layout.addWidget(self.nav_list)
        main_layout.addWidget(self.stack)

        # Interne Verbindung: Klick auf Liste -> Stack wechselt
        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)

        # Startseite setzen
        self.nav_list.setCurrentRow(0)

try:
    import pygame

    pygame.mixer.init()
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    print("ACHTUNG: 'pygame' fehlt. Sounds werden nicht abgespielt.")

def get_short_name(path):
    """Gibt nur den Dateinamen ohne den kompletten Pfad zurück"""
    return os.path.basename(path) if path else "No file selected"

sys.excepthook = log_exception

# Globale Konstanten
CONFIG_FILE = "config.json"

class DiorClientGUI:
    def __init__(self):
        # 1. BASIS & DB INITIALISIERUNG
        self.BASE_DIR = BASE_DIR  # Kommt jetzt aus dem Import 'dior_utils'
        self.db = DatabaseHandler()  # Kommt aus 'dior_db'

        # 2. DATEN LADEN
        self.config = self.load_config()
        self.char_data = self.db.load_my_chars()

        # Cache laden (Gibt jetzt 2 Dictionaries zurück: Namen und Outfits)
        self.name_cache, self.outfit_cache = self.db.load_player_cache()

        # 2. LOGIK-VARIABLEN
        self.ps2_dir = self.config.get("ps2_path", "")
        self.current_world_id = self.config.get("world_id", "10")
        self.current_character_id = ""
        self.is_hud_editing = False
        self.overlay_win = None

        self.server_map = {
            "Wainwright (EU)": "10", "Osprey (US)": "1",
            "SolTech (Asia)": "40", "Jaeger": "19"
        }

        # Signale für Worker
        self.worker_signals = WorkerSignals()
        self.worker_signals.add_char_finished.connect(self.finalize_add_char_slot)
        self.worker_signals.game_status_changed.connect(self.handle_game_status_change)

        # Tracking Variables
        self.killstreak_count = 0
        self.kill_counter = 0
        self.is_dead = False
        self.was_revived = False
        self.streak_timeout = 12.0
        self.pop_history = [0] * 100
        self.myTeamId = 0
        self.currentZone = 0
        self.myWorldID = self.current_world_id
        self.last_kill_time = 0
        self.live_stats = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0, "Total": 0}
        self.session_stats = {}
        self.active_players = {}

        self.db_player_count = 0
        self.update_db_count_cache()

        # Enforcer / Watchdog / Network
        self.observer = None
        self.last_killer_name = "None"
        self.last_killer_id = "0"
        self.last_evidence_url = ""
        self.item_db = {}
        self.id_queue = Queue()  # WICHTIG: Hier initialisieren für Cache Worker
        self.websocket = None
        self.loop = None

        # Pfade
        self.assets_path = os.path.join("assets", "Planetside 2 ini")
        self.source_high = os.path.join(self.assets_path, "UserOptions_high.ini")
        self.source_low = os.path.join(self.assets_path, "UserOptions_low.ini")

        # 3. QT APP & FENSTER INITIALISIEREN
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setStyle("Fusion")

        # Unter-Fenster erstellen
        # Unter-Fenster erstellen
        self.dash_window = dashboard_qt.DashboardWidget(self)
        self.dash_controller = dashboard_qt.DashboardController(self.dash_window)

        # --- FIX START: Dropdown mit Config synchronisieren ---
        # Wir suchen den Namen zur geladenen ID (z.B. "10" -> "Wainwright (EU)")
        init_server_name = self.get_server_name_by_id(self.current_world_id)

        # Wir setzen das Dropdown auf diesen Namen, ohne das Signal zu feuern (blockSignals)
        if hasattr(self.dash_window, 'server_combo'):
            self.dash_window.server_combo.blockSignals(True)
            idx = self.dash_window.server_combo.findText(init_server_name)
            if idx >= 0:
                self.dash_window.server_combo.setCurrentIndex(idx)
            self.dash_window.server_combo.blockSignals(False)
        # --- FIX ENDE ---

        self.launcher_win = launcher_qt.LauncherWidget(self)
        self.char_win = characters_qt.CharacterWidget(self)
        self.ovl_config_win = overlay_config_qt.OverlayConfigWindow(self)
        self.settings_win = settings_qt.SettingsWidget(self)

        # Overlay erstellen
        self.overlay_win = QtOverlay(self)

        # 4. MAIN HUB (Die Hülle)
        self.main_hub = DiorMainHub(self)

        # 5. SIGNALE VERBINDEN
        self.connect_all_qt_signals()

        self.refresh_char_list_ui()

        # 6. DATEN IN DIE FENSTER LADEN
        # WICHTIG: Das hier lädt die Checkboxen UND erzwingt die Config-Werte
        self.load_overlay_config_to_qt()
        self.settings_win.load_config(self.config, self.ps2_dir)

        # Positionen initialisieren
        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()

        # 7. ANZEIGEN
        self.main_hub.show()

        # 8. HINTERGRUND-THREADS
        threading.Thread(target=self.cache_worker, daemon=True).start()
        print("SYS: Cache Worker Thread gestartet.")

        self.census = CensusWorker(self)
        self.census.start()

        threading.Thread(target=self.ps2_process_monitor, daemon=True).start()

        # Item DB
        csv_path = os.path.join(self.BASE_DIR, "assets", "sanction-list.csv")
        if os.path.exists(csv_path):
            self.load_item_db(csv_path)

        # Stats Timer
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_live_graph)
        self.stats_timer.start(1000)

        # Session Startzeit
        self.session_start_time = time.time()
        self.last_graph_point_time = time.time()

        self._streak_test_timer = None
        self._streak_backup = None

    def save_global_event_duration(self):
        """Speichert die globale Event-Dauer."""
        try:
            val = int(self.ovl_config_win.ent_global_duration.text())
        except ValueError:
            val = 3000
            self.ovl_config_win.ent_global_duration.setText("3000")

        self.config["event_global_duration"] = val
        self.save_config()
        self.add_log(f"SYS: Globale Event-Dauer auf {val}ms gesetzt.")

    def toggle_killfeed_visibility(self):
        """Schaltet den Killfeed an/aus."""
        ui = self.ovl_config_win

        # 1. Config holen & toggeln
        if "killfeed" not in self.config: self.config["killfeed"] = {}
        current_state = self.config["killfeed"].get("active", True)
        new_state = not current_state

        self.config["killfeed"]["active"] = new_state
        self.save_config()

        # 2. Button Optik
        if new_state:
            ui.btn_toggle_feed.setText("KILLFEED: ON")
            ui.btn_toggle_feed.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        else:
            ui.btn_toggle_feed.setText("KILLFEED: OFF")
            ui.btn_toggle_feed.setStyleSheet(
                "background-color: #440000; color: white; font-weight: bold; border-radius: 4px;")

            # Sofort leeren/verstecken wenn ausgeschaltet
            if self.overlay_win:
                self.overlay_win.feed_label.hide()
                self.overlay_win.feed_label.clear()

        state_str = "ENABLED" if new_state else "DISABLED"
        self.add_log(f"UI: Killfeed {state_str}")

    def toggle_stats_visibility(self):
        """Schaltet das Stats-Widget an/aus."""
        ui = self.ovl_config_win

        if "stats_widget" not in self.config: self.config["stats_widget"] = {}
        new_state = not self.config["stats_widget"].get("active", True)

        self.config["stats_widget"]["active"] = new_state
        self.save_config()

        # Button Optik
        if new_state:
            ui.btn_toggle_stats.setText("STATS WIDGET: ON")
            ui.btn_toggle_stats.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        else:
            ui.btn_toggle_stats.setText("STATS WIDGET: OFF")
            ui.btn_toggle_stats.setStyleSheet(
                "background-color: #440000; color: white; font-weight: bold; border-radius: 4px;")

        # Sofort Refresh
        self.refresh_ingame_overlay()


    def update_db_count_cache(self):
        """Liest die Anzahl der einzigartigen Spieler aus der DB."""
        try:
            conn = sqlite3.connect("ps2_master.db")
            cursor = conn.cursor()
            count = cursor.execute("SELECT COUNT(*) FROM player_cache").fetchone()[0]
            conn.close()
            self.db_player_count = count
        except Exception as e:
            print(f"DB Count Error: {e}")

    def update_stats_position_safe(self):
        """Berechnet die Position des Stats-Widgets sicher und konsistent."""
        if not self.overlay_win: return

        # 1. Config laden
        cfg = self.config.get("stats_widget", {})

        # Gespeicherte Koordinaten (Linke obere Ecke des Hintergrunds)
        x_conf = cfg.get("x", 50)
        y_conf = cfg.get("y", 500)

        # Umrechnen auf aktuelle Bildschirm-Skalierung
        bg_x = self.overlay_win.s(x_conf)
        bg_y = self.overlay_win.s(y_conf)

        # 2. Hintergrund bewegen
        self.overlay_win.safe_move(self.overlay_win.stats_bg_label, bg_x, bg_y)

        # 3. Text Position relativ dazu berechnen

        # Größen erzwingen (Wichtig!)
        self.overlay_win.stats_bg_label.adjustSize()
        self.overlay_win.stats_text_label.adjustSize()

        bg_w = self.overlay_win.stats_bg_label.width()
        bg_h = self.overlay_win.stats_bg_label.height()

        # Fallback Größen (falls Bild noch lädt oder fehlt)
        # Dies ist wichtig für den "leeren" Edit-Modus
        if bg_w < 10: bg_w = int(450 * self.overlay_win.ui_scale)
        if bg_h < 10: bg_h = int(60 * self.overlay_win.ui_scale)

        txt_w = self.overlay_win.stats_text_label.width()
        txt_h = self.overlay_win.stats_text_label.height()

        # Offsets aus Config (Slider)
        tx_offset = self.overlay_win.s(cfg.get("tx", 0))
        ty_offset = self.overlay_win.s(cfg.get("ty", 0))

        # --- MATHE FIX ---

        # 1. Mitte des Hintergrunds finden (Absolute Bildschirmkoordinaten)
        center_bg_x = bg_x + (bg_w / 2)
        center_bg_y = bg_y + (bg_h / 2)

        # 2. Text-Startpunkt berechnen:
        # Mitte - halbe Textbreite + Benutzer-Offset
        final_text_x = center_bg_x - (txt_w / 2) + tx_offset
        final_text_y = center_bg_y - (txt_h / 2) + ty_offset

        self.overlay_win.safe_move(self.overlay_win.stats_text_label, int(final_text_x), int(final_text_y))

        # Damit das Text-Label immer VOR dem Hintergrund liegt
        self.overlay_win.stats_text_label.raise_()

    def update_main_config_from_settings(self, data):
        """Empfängt die bereinigten Daten aus settings_qt."""

        # Audio Volume speichern
        if "audio_volume" in data:
            vol = data["audio_volume"]
            self.config["audio_volume"] = vol

            # Falls du PyGame Sound nutzt, hier direkt Volume setzen
            if globals().get("HAS_SOUND", False):
                try:
                    # Pygame Volume ist float 0.0 bis 1.0
                    import pygame
                    # Wir setzen einen globalen Mix, falls Sounds abgespielt werden
                    # (Hinweis: pygame.mixer.Sound(path).set_volume(...) müsste pro Sound passieren,
                    # aber wir speichern es hier für spätere Nutzung)
                    pass
                except:
                    pass

        self.save_config()
        self.add_log(f"SYS: Globale Einstellungen gespeichert (Vol: {data.get('audio_volume')}%)")

    def clean_path(self, path_str):
        """Entfernt 'No file selected' und leere Pfade."""
        if not path_str or "No file selected" in path_str:
            return ""
        return os.path.basename(path_str)  # Nur Dateiname speichern

    def handle_game_status_change(self, is_running):
        """Dieser Slot läuft garantiert im Main-Thread!"""
        # Wir setzen den Status sofort hier im Main-Thread,
        # damit alle UI-Funktionen (wie refresh_ingame_overlay) denselben Stand haben.
        self.ps2_running = is_running

        if is_running:
            self.on_game_started()
        else:
            self.on_game_stopped()

    # --- HILFSMETHODE FÜR DEN CONTROLLER ---
    def switch_to_tab(self, index):
        """Wechselt den Tab und aktualisiert die Seitenleiste visuell."""
        self.nav_list.setCurrentRow(index)

    def on_game_started(self):
        """Wird aufgerufen, wenn PS2 gestartet wurde (läuft im Main-Thread)."""
        self.add_log("MONITOR: PlanetSide 2 erkannt. Prüfe Einstellungen...")

        master_active = self.config.get("overlay_master_active", True)

        if master_active:
            self.add_log("MONITOR: Master-Switch ist AN -> Starte Overlay.")

            if self.overlay_win:
                # Fenster zeigen
                self.overlay_win.showFullScreen()
                self.overlay_win.raise_()

                # Crosshair
                self.update_crosshair_from_qt()

                # Killfeed (leeren)
                if hasattr(self.overlay_win, 'feed_label'):
                    self.overlay_win.feed_label.show()
                    self.overlay_win.feed_label.setText("")
                    self.overlay_win.update_killfeed_pos()

                # Streak
                streak_active = self.config.get("streak", {}).get("active", True)
                if streak_active:
                    self.update_streak_display()

                # WICHTIG: Kein manuelles .show() für Stats hier!
                # Wir überlassen das komplett dem Loop.

                # Loop sofort triggern
                self.refresh_ingame_overlay()

    def on_game_stopped(self):
        """Wird aufgerufen, wenn PS2 beendet wurde."""
        self.add_log("MONITOR: PlanetSide 2 geschlossen.")

        # Logik stoppen
        self.stop_overlay_logic()

        if self.overlay_win:
            # Nur verstecken, wenn wir nicht gerade editieren
            if not getattr(self, "is_hud_editing", False):
                # 1. Crosshair weg
                self.overlay_win.crosshair_label.hide()

                # 2. Stats weg (NEU)
                self.overlay_win.stats_bg_label.hide()
                self.overlay_win.stats_text_label.hide()

                # 3. Killfeed weg (NEU)
                self.overlay_win.feed_label.hide()
                self.overlay_win.feed_label.clear()

                # 4. Streak weg
                self.overlay_win.streak_bg_label.hide()
                self.overlay_win.streak_text_label.hide()
                for k in self.overlay_win.knife_labels:
                    k.hide()

                # Optional: Overlay ganz ausblenden (spart Ressourcen)
                # self.overlay_win.hide()

    # --- CROSSHAIR LOGIK (NEU) ---
    def browse_crosshair_qt(self):
        """Datei auswählen, kopieren und Textfeld setzen."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self.main_hub, "Wähle Crosshair Bild", self.BASE_DIR, "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            filename = os.path.basename(file_path)
            target_path = get_asset_path(filename)

            # In Assets kopieren, falls nötig
            if os.path.abspath(file_path) != os.path.abspath(target_path):
                try:
                    shutil.copy2(file_path, target_path)
                except Exception as e:
                    print(f"Copy Error: {e}")

            # WICHTIG: Signale kurz blockieren, damit update_crosshair_from_qt
            # nicht doppelt aufgerufen wird (einmal durch setText, einmal manuell)
            self.ovl_config_win.cross_path.blockSignals(True)
            self.ovl_config_win.cross_path.setText(filename)
            self.ovl_config_win.cross_path.blockSignals(False)

            # Jetzt einmal sauber speichern
            self.update_crosshair_from_qt()

    def update_crosshair_from_qt(self):
        """Liest UI-Werte, bereinigt den Pfad und speichert."""
        ui = self.ovl_config_win

        # 1. Rohdaten aus UI
        is_active = ui.check_cross.isChecked()
        raw_text = ui.cross_path.text().strip()

        # 2. Bereinigen: Wir wollen nur den Dateinamen speichern!
        # Falls der User einen vollen Pfad reinkopiert hat, schneiden wir ihn ab.
        filename = os.path.basename(raw_text)

        # Leerer Pfad -> Standard
        if not filename:
            filename = "crosshair.png"

        # 3. Config Update
        if "crosshair" not in self.config:
            self.config["crosshair"] = {}

        self.config["crosshair"]["active"] = is_active
        self.config["crosshair"]["file"] = filename  # Nur der Name!

        # Speichern
        self.save_config()
        # print(f"DEBUG: Crosshair saved -> Active: {is_active}, File: {filename}")

        # 4. Live Update (Hier brauchen wir den vollen Pfad für Qt)
        if self.overlay_win:
            full_path = get_asset_path(filename)

            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, "is_hud_editing", False)
            should_show = (is_active and game_running) or edit_mode

            current_size = self.config["crosshair"].get("size", 32)
            self.overlay_win.update_crosshair(full_path, current_size, should_show)

    def center_crosshair_qt(self):
        """Zentriert das Crosshair neu auf dem aktuellen Bildschirm."""
        # 1. Logik ausführen
        self.center_crosshair()  # Diese Methode existiert bereits in Teil 3 deines Codes

        # 2. Feedback
        self.add_log("CROSSHAIR: Auf Bildschirmmitte zurückgesetzt.")

    def apply_event_layout_to_all(self):
        """Kopiert Position & Größe des aktuellen Events auf ALLE anderen."""
        from PyQt6.QtWidgets import QMessageBox

        # Welches Event ist gerade offen?
        ui = self.ovl_config_win
        source_name = ui.lbl_editing.text().replace("EDITING: ", "").strip()

        if source_name == "NONE" or not source_name:
            return

        # Sicherheitsabfrage
        reply = QMessageBox.question(ui, "Layout übertragen?",
                                     f"Soll das Layout von '{source_name}' (Position & Größe) auf ALLE anderen Events übertragen werden?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Werte ermitteln
        # Entweder vom Overlay (falls Edit Mode an) oder aus Config
        if self.overlay_win and self.overlay_win.event_preview_label.isVisible():
            pos = self.overlay_win.event_preview_label.pos()
            new_x = int(pos.x() / self.overlay_win.ui_scale)
            new_y = int(pos.y() / self.overlay_win.ui_scale)
        else:
            src_data = self.config.get("events", {}).get(source_name, {})
            new_x = src_data.get("x", 100)
            new_y = src_data.get("y", 200)

        new_scale = ui.slider_evt_scale.value() / 100.0

        # Auf alle anwenden
        count = 0
        if "events" not in self.config: self.config["events"] = {}

        for evt_key in self.config["events"]:
            if evt_key == source_name: continue

            # Nur Layout ändern, Bilder/Sounds behalten!
            self.config["events"][evt_key]["x"] = new_x
            self.config["events"][evt_key]["y"] = new_y
            self.config["events"][evt_key]["scale"] = new_scale
            count += 1

        self.save_config()
        self.add_log(f"SYS: Layout auf {count} Events übertragen.")
        QMessageBox.information(ui, "Erfolg", f"Layout erfolgreich übertragen!")

    def process_search_results_qt(self, stats, weapons):
        """Wird im Haupt-Thread aufgerufen, wenn der Worker fertig ist."""
        try:
            self.add_log("DASHBOARD: Rendering Character Data...")
            self.char_win.update_overview(stats)
            self.char_win.update_weapons(weapons)

            self.char_win.btn_search.setEnabled(True)
            self.char_win.btn_search.setText("SEARCH")
            self.add_log(f"SUCCESS: Character UI updated.")
        except Exception as e:
            self.add_log(f"RENDER ERROR: {e}")

    def toggle_master_switch_qt(self, checked):
        """Speichert den Master-Switch Status."""
        self.config["overlay_master_active"] = checked
        self.save_config()

        state = "AKTIVIERT" if checked else "DEAKTIVIERT"
        self.add_log(f"SYS: Master-Switch {state}")

        # Sofort reagieren, falls Spiel schon läuft
        if getattr(self, 'ps2_running', False):
            if checked:
                self.on_game_started()
            else:
                self.on_game_stopped()

    def connect_all_qt_signals(self):
        """Zentrales Management aller PyQt6 Signale (Strukturiert & Clean)."""
        print("SYS: Connecting GUI signals...")

        # Shortcuts
        hub = self.main_hub
        ui = self.ovl_config_win
        dash = self.dash_controller

        # ---------------------------------------------------------
        # 1. NAVIGATION & HAUPTFENSTER
        # ---------------------------------------------------------
        if hasattr(dash, 'btn_play'):
            self.safe_connect(dash.btn_play.clicked, lambda: hub.switch_to_tab(1))
        if hasattr(dash, 'btn_chars'):
            self.safe_connect(dash.btn_chars.clicked, lambda: hub.switch_to_tab(2))
        if hasattr(dash, 'btn_overlay'):
            self.safe_connect(dash.btn_overlay.clicked, lambda: hub.switch_to_tab(3))
        if hasattr(dash, 'btn_settings'):
            self.safe_connect(dash.btn_settings.clicked, lambda: hub.switch_to_tab(4))

        if hasattr(dash, 'signals') and hasattr(dash.signals, 'server_changed'):
            self.safe_connect(dash.signals.server_changed, self.change_server_logic)

        if self.overlay_win:
            self.safe_connect(self.overlay_win.signals.edit_mode_toggled, self.toggle_hud_edit_mode)

        # ---------------------------------------------------------
        # 2. OVERLAY TAB: IDENTITY
        # ---------------------------------------------------------
        # Char Select
        self.safe_connect(ui.char_combo.currentTextChanged, self.update_active_char)
        # Add & Delete
        self.safe_connect(ui.btn_add_char.clicked, self.add_char_qt)
        self.safe_connect(ui.btn_del_char.clicked, self.delete_char_qt)
        self.safe_connect(ui.char_input.returnPressed, self.add_char_qt)
        # Master Switch
        self.safe_connect(ui.check_master.toggled, self.toggle_master_switch_qt)

        # ---------------------------------------------------------
        # 3. OVERLAY TAB: EVENTS
        # ---------------------------------------------------------
        # Event Auswahl im Grid
        try:
            ui.signals.setting_changed.disconnect()
        except:
            pass
        ui.signals.setting_changed.connect(
            lambda key, val: self.load_event_ui_data(val) if key == "event_selection" else None
        )
        if hasattr(ui, 'ent_global_duration'):
            ui.ent_global_duration.editingFinished.connect(self.save_global_event_duration)

        # Live-Preview bei Texteingabe
        ui.ent_evt_img.textChanged.connect(lambda text: ui.update_preview_image(get_asset_path(text)))

        # Browse Buttons
        try:
            ui.btn_browse_evt_img.clicked.disconnect()
        except:
            pass
        ui.btn_browse_evt_img.clicked.connect(lambda: self.browse_file_qt(ui.ent_evt_img, "png"))

        try:
            ui.btn_browse_evt_snd.clicked.disconnect()
        except:
            pass
        ui.btn_browse_evt_snd.clicked.connect(lambda: self.browse_file_qt(ui.ent_evt_snd, "audio"))

        # Save Button
        self.safe_connect(ui.btn_save_event.clicked, self.save_event_ui_data)

        # Test / Edit / Special Buttons
        self.safe_connect(ui.btn_test_preview.clicked,
                          lambda: self.trigger_overlay_event(ui.lbl_editing.text().replace("EDITING: ", "")))
        self.safe_connect(ui.btn_edit_hud.clicked, self.toggle_hud_edit_mode)

        if hasattr(ui, 'btn_apply_all'):
            self.safe_connect(ui.btn_apply_all.clicked, self.apply_event_layout_to_all)
        if hasattr(ui, 'btn_queue_toggle'):
            self.safe_connect(ui.btn_queue_toggle.clicked, lambda: self.toggle_event_queue_qt())

        # ---------------------------------------------------------
        # 4. OVERLAY TAB: KILLSTREAK
        # ---------------------------------------------------------
        # Hauptbild Browse
        try:
            ui.btn_browse_streak_img.clicked.disconnect()
        except:
            pass
        ui.btn_browse_streak_img.clicked.connect(lambda: self.browse_file_qt(ui.ent_streak_img, "png"))

        # Messer Icons Browse (Dynamisch)
        for faction, btn in ui.knife_browse_btns.items():
            target_field = ui.knife_inputs[faction]
            try:
                btn.clicked.disconnect()
            except:
                pass
            btn.clicked.connect(lambda _, tf=target_field: self.browse_file_qt(tf, "png"))

        # Auto-Save bei Checkboxen & Slidern
        self.safe_connect(ui.check_streak_master.toggled, self.save_streak_settings_from_qt)
        self.safe_connect(ui.check_streak_anim.toggled, self.save_streak_settings_from_qt)

        for slider in [ui.slider_tx, ui.slider_ty, ui.slider_scale]:
            self.safe_connect(slider.valueChanged, self.save_streak_settings_from_qt)

        # Design (Farbe/Größe)
        self.safe_connect(ui.btn_pick_color.clicked, self.pick_streak_color_qt)
        self.safe_connect(ui.combo_font_size.currentTextChanged, self.save_streak_settings_from_qt)

        # Path Recording
        self.safe_connect(ui.btn_path_record.clicked, self.start_path_record)
        self.safe_connect(ui.btn_path_clear.clicked, self.clear_path)

        # Action Buttons
        self.safe_connect(ui.btn_save_streak.clicked, self.save_streak_settings_from_qt)
        self.safe_connect(ui.btn_edit_streak.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_streak.clicked, self.test_streak_visuals)

        # ---------------------------------------------------------
        # 5. OVERLAY TAB: CROSSHAIR
        # ---------------------------------------------------------
        # Checkbox & Textfeld Änderung -> Sofort speichern
        self.safe_connect(ui.check_cross.toggled, self.update_crosshair_from_qt)
        self.safe_connect(ui.cross_path.textChanged, self.update_crosshair_from_qt)

        # Browse
        try:
            ui.btn_browse_cross.clicked.disconnect()
        except:
            pass
        ui.btn_browse_cross.clicked.connect(self.browse_crosshair_qt)

        # Center & Edit
        self.safe_connect(ui.btn_center_cross.clicked, self.center_crosshair_qt)
        self.safe_connect(ui.btn_edit_cross.clicked, self.toggle_hud_edit_mode)

        # ---------------------------------------------------------
        # 6. OVERLAY TAB: STATS & FEED
        # ---------------------------------------------------------
        # Sliders
        for slider in [ui.slider_st_scale, ui.slider_st_tx, ui.slider_st_ty]:
            self.safe_connect(slider.valueChanged, self.save_stats_config_from_qt)

        # Browse Buttons für Stats
        try:
            ui.btn_browse_stats_bg.clicked.disconnect()
        except:
            pass
        ui.btn_browse_stats_bg.clicked.connect(lambda: self.browse_file_qt(ui.ent_stats_img, "png"))

        try:
            ui.btn_browse_hs_icon.clicked.disconnect()
        except:
            pass
        ui.btn_browse_hs_icon.clicked.connect(lambda: self.browse_file_qt(ui.ent_hs_icon, "png"))

        # Save & Edit Actions
        self.safe_connect(ui.btn_save_stats.clicked, self.save_stats_config_from_qt)
        self.safe_connect(ui.btn_edit_hud_stats.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_stats.clicked, self.test_stats_visuals)
        self.safe_connect(ui.btn_toggle_stats.clicked, self.toggle_stats_visibility)
        self.safe_connect(ui.btn_toggle_feed.clicked, self.toggle_killfeed_visibility)
        self.safe_connect(ui.check_show_revives.toggled, self.save_stats_config_from_qt)

        # ---------------------------------------------------------
        # 7. OVERLAY TAB: VOICE MACROS
        # ---------------------------------------------------------
        self.safe_connect(ui.btn_save_voice.clicked, self.save_voice_config_from_qt)
        for combo in ui.voice_combos.values():
            self.safe_connect(combo.currentIndexChanged, self.save_voice_config_from_qt)

        # ---------------------------------------------------------
        # 8. SUB-FENSTER (CHARACTERS, LAUNCHER, SETTINGS)
        # ---------------------------------------------------------
        # Character Search
        self.safe_connect(self.char_win.signals.search_requested, self.run_search)
        self.safe_connect(self.char_win.signals.search_finished, self.process_search_results_qt)

        # Launcher
        self.safe_connect(self.launcher_win.signals.launch_requested, self.execute_launch)

        # Settings (HIER WAREN DIE ÄNDERUNGEN)
        self.safe_connect(self.settings_win.signals.browse_ps2_requested, self.browse_ps2_folder)
        self.safe_connect(self.settings_win.signals.change_bg_requested, self.change_background_file)

        # WICHTIG: Das Save-Signal verbinden!
        self.safe_connect(self.settings_win.signals.save_requested, self.update_main_config_from_settings)

        print("SYS: All signals routed successfully.")

    def browse_ps2_folder(self):
        """Wählt den PS2 Ordner und speichert ihn sofort permanent."""
        path = filedialog.askdirectory(title="PlanetSide 2 Installationsordner wählen")
        if path:
            self.ps2_dir = path

            # WICHTIG: In das Config-Dictionary schreiben!
            self.config["ps2_path"] = path

            # Update im Settings-Fenster (visuelles Feedback)
            if hasattr(self, 'settings_win'):
                self.settings_win.lbl_ps2_path.setText(path)

            self.save_config()  # Korrekte Speicher-Funktion aufrufen
            self.add_log(f"SYS: PS2 Path set and saved to {path}")

    def add_char_qt(self):
        """Startet den Thread."""
        ui = self.ovl_config_win
        name = ui.char_input.text().strip()

        if not name:
            self.add_log("INFO: Bitte einen Namen eingeben.")
            return

        self.add_log(f"SYS: Suche '{name}' in API...")

        # UI sperren
        ui.btn_add_char.setEnabled(False)
        ui.btn_add_char.setText("...")
        ui.char_input.setEnabled(False)

        # Thread starten
        threading.Thread(target=self._add_char_worker, args=(name,), daemon=True).start()

    def _add_char_worker(self, name):
        """Hintergrund-Thread: Sucht Charakter und speichert ihn via DB-Handler."""
        success = False
        real_name = ""
        error_msg = ""

        try:
            url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/?name.first_lower={name.lower()}"
            response = requests.get(url, timeout=10)
            r = response.json()

            if r.get('returned', 0) > 0:
                c_list = r['character_list'][0]
                cid = c_list['character_id']
                real_name = c_list['name']['first']
                world_id = c_list.get('world_id', '0')

                # --- DB OPERATION (NEU & SAUBER) ---
                # Wir nutzen die Methode aus dior_db.py
                self.db.save_char_to_db(cid, real_name, world_id)

                # Dictionary Update (RAM)
                self.char_data[real_name] = cid
                success = True
            else:
                error_msg = f"Charakter '{name}' nicht gefunden."

        except Exception as e:
            error_msg = f"API Fehler: {e}"

        # Signal senden
        self.worker_signals.add_char_finished.emit(success, real_name, error_msg)

    def finalize_add_char_slot(self, success, real_name, error_msg):
        """
        Dieser Slot wird AUTOMATISCH im Haupt-Thread ausgeführt,
        wenn das Signal empfangen wird.
        """
        ui = self.ovl_config_win

        # UI entsperren
        ui.btn_add_char.setEnabled(True)
        ui.btn_add_char.setText("ADD")
        ui.char_input.setEnabled(True)
        ui.char_input.setFocus()

        if success:
            self.add_log(f"SYS: '{real_name}' hinzugefügt.")
            ui.char_input.clear()

            # Jetzt muss das Update funktionieren
            self.refresh_char_list_ui(select_name=real_name)
        else:
            self.add_log(f"ERR: {error_msg}")
            ui.char_input.selectAll()

    def delete_char_qt(self):
        """Löscht den aktuell ausgewählten Charakter."""
        ui = self.ovl_config_win
        name = ui.char_combo.currentText()

        if name in self.char_data:
            try:
                # --- DB OPERATION (NEU) ---
                self.db.remove_my_char(name)

                del self.char_data[name]
                self.add_log(f"SYS: {name} deleted.")

                # GUI Update
                self.refresh_char_list_ui()

            except Exception as e:
                self.add_log(f"ERR: Delete failed: {e}")

    def refresh_char_list_ui(self, select_name=None):
        """Aktualisiert das Dropdown und setzt den aktiven Charakter."""
        ui = self.ovl_config_win

        # 1. Signale blockieren
        ui.char_combo.blockSignals(True)

        # 2. Liste neu aufbauen
        ui.char_combo.clear()

        # Sortierte Liste ist schöner
        names = sorted(list(self.char_data.keys()))
        ui.char_combo.addItems(names)

        # 3. Auswahl setzen
        if select_name and select_name in names:
            ui.char_combo.setCurrentText(select_name)
            self.update_active_char(select_name)

        elif names:
            # --- VERBESSERUNG ---
            # Versuche den zuletzt gewählten Namen wiederherzustellen
            current_active = getattr(self, "current_selected_char_name", "")
            if current_active and current_active in names:
                ui.char_combo.setCurrentText(current_active)
                self.update_active_char(current_active)
            else:
                # Fallback: Den ersten nehmen
                ui.char_combo.setCurrentIndex(0)
                self.update_active_char(names[0])
            # --------------------

        # 4. Signale wieder freigeben
        ui.char_combo.blockSignals(False)

    def pick_streak_color_qt(self):
        """Öffnet einen Qt-Farbwähler für die Killstreak-Zahl."""
        # Aktuelle Farbe aus Config holen (als Startwert)
        current_hex = self.config.get("streak", {}).get("color", "#ffffff")
        initial = QColor(current_hex)

        # Dialog öffnen
        color = QColorDialog.getColor(initial, self.main_hub, "Wähle HUD Farbe")

        if color.isValid():
            hex_color = color.name()  # Gibt z.B. "#ff0000" zurück

            # 1. In Config schreiben
            if "streak" not in self.config: self.config["streak"] = {}
            self.config["streak"]["color"] = hex_color

            # 2. Button-Farbe im UI aktualisieren (visuelles Feedback)
            # Wir setzen den Hintergrund des Buttons auf die gewählte Farbe
            # Und die Textfarbe auf Schwarz oder Weiß je nach Helligkeit
            text_col = "black" if color.lightness() > 128 else "white"
            self.ovl_config_win.btn_pick_color.setStyleSheet(
                f"background-color: {hex_color}; color: {text_col}; font-weight: bold; border: 1px solid #555;"
            )

            # 3. Speichern und Overlay updaten
            self.save_streak_settings_from_qt()

    def safe_connect(self, signal, slot):
        """Trennt eine Verbindung sicherheitshalber, bevor sie neu gesetzt wird."""
        try:
            signal.disconnect(slot)
        except TypeError:
            pass  # War noch nicht verbunden, alles gut
        signal.connect(slot)

    def on_event_selected_in_qt(self, event_name):
        """Wird gerufen, wenn man im Grid auf ein Event klickt."""
        ui = self.ovl_config_win
        # Daten aus der Config holen (Sektion 'events')
        ev_conf = self.config.get("events", {})
        data = ev_conf.get(event_name, {})

        # 1. Label aktualisieren
        ui.lbl_editing.setText(f"EDITING: {event_name}")

        # 2. Felder befüllen (mit Fallback-Werten, falls leer)
        ui.ent_evt_img.setText(data.get("img", "default.png"))
        ui.ent_evt_snd.setText(data.get("sound", "none.ogg"))

        # Scale Slider (Config Wert * 100 für den Slider-Bereich)
        scale_val = int(data.get("scale", 1.0) * 100)
        ui.slider_evt_scale.setValue(scale_val)

        # Duration
        ui.ent_evt_duration.setText(str(data.get("duration", 3000)))

        self.add_log(f"UI: Settings for '{event_name}' loaded.")

    def save_streak_settings_from_qt(self):
        """
        Liest Killstreak-Settings aus der GUI, sichert den Live-Pfad
        und bewahrt versteckte Einstellungen (Bold/Shadow).
        """
        s_ui = self.ovl_config_win

        # 1. Config Initialisieren
        if "streak" not in self.config: self.config["streak"] = {}
        current_conf = self.config["streak"]

        def clean_path(text):
            if not text or "No file selected" in text:
                return ""
            return os.path.basename(text.strip())

        # --- A) DATEN AUS DEM LIVE-OVERLAY HOLEN ---
        final_path_data = current_conf.get("custom_path", [])
        if self.overlay_win and hasattr(self.overlay_win, 'custom_path'):
            final_path_data = self.overlay_win.custom_path

        # --- B) DATEN AUS DER GUI LESEN ---
        is_active = s_ui.check_streak_master.isChecked()
        anim_active = s_ui.check_streak_anim.isChecked()

        main_img = clean_path(s_ui.ent_streak_img.text())
        if not main_img: main_img = "KS_Counter.png"

        try:
            speed = int(s_ui.ent_streak_speed.text())
        except ValueError:
            speed = 50

        tx = s_ui.slider_tx.value()
        ty = s_ui.slider_ty.value()
        scale = s_ui.slider_scale.value() / 100.0

        try:
            size_val = int(s_ui.combo_font_size.currentText())
        except ValueError:
            size_val = 26

        knife_tr = clean_path(s_ui.knife_inputs["TR"].text())
        knife_nc = clean_path(s_ui.knife_inputs["NC"].text())
        knife_vs = clean_path(s_ui.knife_inputs["VS"].text())

        # --- C) FARBE (SPECIAL CASE) ---
        # Die Farbe wird vom Color-Picker direkt in die Config geschrieben.
        # Wir laden sie hier also neu, damit sie beim Speichern nicht mit einem alten Wert überschrieben wird.
        current_color = current_conf.get("color", "#ffffff")

        # --- D) LEGACY WERTE BEWAHREN (NICHT IN GUI VORHANDEN) ---
        # Diese Werte gibt es in der Qt-GUI nicht mehr (keine Checkboxen dafür),
        # daher dürfen wir sie nicht nullen/löschen, sondern behalten die alten bei.
        keep_shadow = current_conf.get("shadow_size", 0)
        keep_bold = current_conf.get("bold", False)
        keep_underline = current_conf.get("underline", False)

        # --- E) FINAL UPDATE ---
        self.config["streak"].update({
            "active": is_active,
            "anim_active": anim_active,
            "img": main_img,
            "speed": speed,
            "tx": tx,
            "ty": ty,
            "scale": scale,
            "size": size_val,

            # Die aktuelle Farbe (vom Picker gesetzt)
            "color": current_color,

            # Die bewahrten Legacy-Werte
            "shadow_size": keep_shadow,
            "bold": keep_bold,
            "underline": keep_underline,

            # Pfade
            "knife_tr": knife_tr,
            "knife_nc": knife_nc,
            "knife_vs": knife_vs,

            # Pfad-Daten
            "custom_path": final_path_data
        })

        self.save_config()
        self.update_streak_display()

        self.add_log("SYS: Killstreak-Einstellungen gespeichert.")

    def save_stats_config_from_qt(self):
        """Liest Stats & Feed Settings aus Qt und speichert sie (OHNE Active-Reset)."""
        s_ui = self.ovl_config_win

        # Aktuelle Config holen
        current_st_conf = self.config.get("stats_widget", {})
        current_kf_conf = self.config.get("killfeed", {})

        # --- STATS WIDGET DATEN ---
        # KORREKTUR: Wir lesen NICHT die Checkbox. Wir behalten den Status bei,
        # den der Toggle-Button gesetzt hat.
        saved_active_state = current_st_conf.get("active", True)

        st_data = {
            "active": saved_active_state,  # <--- WICHTIG: Alten Wert behalten!
            "img": s_ui.ent_stats_img.text(),
            "tx": s_ui.slider_st_tx.value(),
            "ty": s_ui.slider_st_ty.value(),
            "scale": s_ui.slider_st_scale.value() / 100.0,

            # Position behalten
            "x": current_st_conf.get("x", 50),
            "y": current_st_conf.get("y", 500)
        }

        # --- KILLFEED DATEN ---
        # Auch hier: Active Status vom Button behalten
        kf_active_state = current_kf_conf.get("active", True)

        kf_data = {
            "active": kf_active_state,  # <--- WICHTIG
            "hs_icon": s_ui.ent_hs_icon.text(),
            "show_revives": s_ui.check_show_revives.isChecked(),  # Das ist OK (Checkbox existiert)

            # Position behalten
            "x": current_kf_conf.get("x", 50),
            "y": current_kf_conf.get("y", 200)
        }

        # Dictionaries updaten (Merge)
        if "stats_widget" not in self.config: self.config["stats_widget"] = {}
        self.config["stats_widget"].update(st_data)

        if "killfeed" not in self.config: self.config["killfeed"] = {}
        self.config["killfeed"].update(kf_data)

        self.save_config()
        self.add_log("SYS: Stats & Killfeed configuration updated.")

        # Positionen live anwenden
        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()
            self.refresh_ingame_overlay()

    def save_voice_config_from_qt(self):
        """Liest Voice Macros aus Qt und speichert sie."""
        new_v = {}
        for key, combo in self.ovl_config_win.voice_combos.items():
            new_v[key] = combo.currentText()

        self.config["auto_voice"] = new_v
        self.save_config()
        self.add_log("SYS: Auto-Voice Macros saved.")

    def load_overlay_config_to_qt(self):
        """Überträgt ALLE Config-Werte in die Qt-Oberfläche (Safe Loading)"""

        # 1. REFERENZEN HOLEN
        ui = self.ovl_config_win

        s_conf = self.config.get("streak", {})
        st_conf = self.config.get("stats_widget", {"active": True})
        kf_conf = self.config.get("killfeed", {})
        v_conf = self.config.get("auto_voice", {})
        c_conf = self.config.get("crosshair", {})
        ev_conf = self.config.get("events", {})

        # --- QUEUE BUTTON ---
        queue_active = self.config.get("event_queue_active", True)

        # Globalen Timer laden (Standard 3000ms)
        g_dur = self.config.get("event_global_duration", 3000)
        ui.ent_global_duration.setText(str(g_dur))

        ui.btn_queue_toggle.setChecked(queue_active)

        if queue_active:
            ui.btn_queue_toggle.setText("QUEUE: ON")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; padding: 10px;")
        else:
            ui.btn_queue_toggle.setText("QUEUE: OFF")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #440000; color: #ffcccc; font-weight: bold; padding: 10px;")

        if self.overlay_win:
            self.overlay_win.queue_enabled = queue_active

            # --- TAB 1: IDENTITY & MASTER SWITCH ---
            active_char = getattr(self, 'current_selected_char_name', "SELECT_UNIT...")

            ui.char_combo.blockSignals(True)
            idx = ui.char_combo.findText(active_char)
            if idx >= 0:
                ui.char_combo.setCurrentIndex(idx)
            else:
                ui.char_combo.setCurrentText(active_char)
            ui.char_combo.blockSignals(False)

            master_state = self.config.get("overlay_master_active", True)
            ui.check_master.blockSignals(True)
            ui.check_master.setChecked(master_state)
            ui.check_master.blockSignals(False)
            self.config["overlay_master_active"] = master_state

        # --- TAB 2: EVENTS ---
        if hasattr(ui, 'event_checkboxes'):
            for ev_name, checkbox in ui.event_checkboxes.items():
                entry = ev_conf.get(ev_name, {})
                is_active = entry.get("active", True) if isinstance(entry, dict) else True
                checkbox.setChecked(is_active)

        if hasattr(ui, 'lbl_editing'): ui.lbl_editing.setText("EDITING: NONE")
        ui.ent_evt_img.clear()
        ui.ent_evt_snd.clear()

        # --- TAB 3: KILLSTREAK ---
        # A) TEXTFELDER
        saved_img = s_conf.get("img", "")
        ui.ent_streak_img.setText(saved_img if saved_img else "KS_Counter.png")
        ui.ent_streak_speed.setText(str(s_conf.get("speed", 50)))

        for fac in ["TR", "NC", "VS"]:
            if fac in ui.knife_inputs:
                config_key = f"knife_{fac.lower()}"
                saved_val = s_conf.get(config_key, "")
                ui.knife_inputs[fac].setText(saved_val)

        # B) ELEMENTE MIT SIGNALEN
        ui.slider_tx.blockSignals(True)
        ui.slider_ty.blockSignals(True)
        ui.slider_scale.blockSignals(True)

        ui.slider_tx.setValue(s_conf.get("tx", 0))
        ui.slider_ty.setValue(s_conf.get("ty", 0))
        ui.slider_scale.setValue(int(s_conf.get("scale", 1.0) * 100))

        ui.slider_tx.blockSignals(False)
        ui.slider_ty.blockSignals(False)
        ui.slider_scale.blockSignals(False)

        ui.check_streak_master.blockSignals(True)
        ui.check_streak_anim.blockSignals(True)
        ui.check_streak_master.setChecked(s_conf.get("active", True))
        ui.check_streak_anim.setChecked(s_conf.get("anim_active", True))
        ui.check_streak_master.blockSignals(False)
        ui.check_streak_anim.blockSignals(False)

        ui.combo_font_size.blockSignals(True)
        current_size = str(s_conf.get("size", 26))
        idx = ui.combo_font_size.findText(current_size)
        if idx >= 0:
            ui.combo_font_size.setCurrentIndex(idx)
        else:
            ui.combo_font_size.setCurrentText(current_size)
        ui.combo_font_size.blockSignals(False)

        c_hex = s_conf.get("color", "#ffffff")
        text_col = "black" if QColor(c_hex).lightness() > 128 else "white"
        ui.btn_pick_color.setStyleSheet(
            f"background-color: {c_hex}; color: {text_col}; font-weight: bold; border: 1px solid #555; padding: 3px; border-radius: 3px;")

        # --- TAB 4: CROSSHAIR ---
        ui.check_cross.blockSignals(True)
        ui.cross_path.blockSignals(True)
        ui.check_cross.setChecked(c_conf.get("active", True))
        saved_file = c_conf.get("file", "")
        if not saved_file: saved_file = "crosshair.png"
        ui.cross_path.setText(saved_file)
        ui.check_cross.blockSignals(False)
        ui.cross_path.blockSignals(False)

        # --- TAB 5: STATS & FEED ---
        st_active = st_conf.get("active", True)
        if st_active:
            ui.btn_toggle_stats.setText("STATS WIDGET: ON")
            ui.btn_toggle_stats.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        else:
            ui.btn_toggle_stats.setText("STATS WIDGET: OFF")
            ui.btn_toggle_stats.setStyleSheet(
                "background-color: #440000; color: white; font-weight: bold; border-radius: 4px;")

        ui.ent_stats_img.setText(st_conf.get("img", "stats_bg.png"))

        # Sliders (wie gehabt)
        ui.slider_st_tx.blockSignals(True);
        ui.slider_st_tx.setValue(st_conf.get("tx", 0));
        ui.slider_st_tx.blockSignals(False)
        ui.slider_st_ty.blockSignals(True);
        ui.slider_st_ty.setValue(st_conf.get("ty", 0));
        ui.slider_st_ty.blockSignals(False)
        ui.slider_st_scale.blockSignals(True);
        ui.slider_st_scale.setValue(int(st_conf.get("scale", 1.0) * 100));
        ui.slider_st_scale.blockSignals(False)

        # 2. Killfeed Button Status
        kf_active = kf_conf.get("active", True)
        if kf_active:
            ui.btn_toggle_feed.setText("KILLFEED: ON")
            ui.btn_toggle_feed.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        else:
            ui.btn_toggle_feed.setText("KILLFEED: OFF")
            ui.btn_toggle_feed.setStyleSheet(
                "background-color: #440000; color: white; font-weight: bold; border-radius: 4px;")

        ui.ent_hs_icon.setText(kf_conf.get("hs_icon", "headshot.png"))
        ui.check_show_revives.setChecked(kf_conf.get("show_revives", True))

        # --- TAB 6: VOICE MACROS ---
        for key, combo in ui.voice_combos.items():
            val = v_conf.get(key, "OFF")
            idx = combo.findText(str(val))
            if idx >= 0: combo.setCurrentIndex(idx)

        # --- OVERLAY INIT ---
        if self.overlay_win:
            # 1. Crosshair initialisieren
            ch_active = c_conf.get("active", True)
            ch_file = c_conf.get("file", "crosshair.png")
            if not ch_file: ch_file = "crosshair.png"
            full_path = get_asset_path(ch_file)
            current_size = c_conf.get("size", 32)

            # Crosshair Logik
            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, "is_hud_editing", False)
            should_show = (ch_active and game_running) or edit_mode
            self.overlay_win.update_crosshair(full_path, current_size, should_show)

            # 2. Killstreak Init
            self.update_streak_display()

            # 3. Killfeed Position Init
            if hasattr(self.overlay_win, 'update_killfeed_pos'):
                self.overlay_win.update_killfeed_pos()

            # 4. LOOP STARTEN (Verzögert)
            # Wir machen hier KEINE manuelle Positionierung mehr.
            # Der Loop (refresh_ingame_overlay) kümmert sich um alles.
            QTimer.singleShot(500, self.refresh_ingame_overlay)

        self.add_log("SYS: Overlay configuration synchronized.")

    def prepare_stats_for_qt(self, char_data):
        """Formatiert die API-Daten für das characters_qt Fenster."""
        c = char_data.get('custom_stats', {})
        return {
            'name': c.get('name', '-'),
            'fac_short': {"1": "VS", "2": "NC", "3": "TR", "4": "NSO"}.get(char_data.get('faction_id'), "-"),
            'server': c.get('server', '-'),
            'outfit': c.get('outfit', '-'),
            'rank': c.get('rank', '-'),
            'time_played': c.get('time_played', '-'),
            'lt_kills': c.get('lt_kills', '0'),
            'lt_deaths': c.get('lt_deaths', '0'),
            'lt_kd': c.get('lt_kd', '0.00'),
            'lt_kpm': c.get('lt_kpm', '0.00'),
            'lt_kph': c.get('lt_kph', '0.00'),
            'lt_spm': c.get('lt_spm', '0.00'),
            'lt_score': c.get('lt_score', '0'),
            'm30_kills': c.get('m30_kills', '0'),
            'm30_deaths': c.get('m30_deaths', '0'),
            'm30_kd': c.get('m30_kd', '0.00'),
            'm30_kpm': c.get('m30_kpm', '0.00'),
            'm30_kph': c.get('m30_kph', '0.00'),
            'm30_spm': c.get('m30_spm', '0.00'),
            'm30_score': c.get('m30_score', '0')
        }

    def change_server_logic(self, world_id):
        self.current_world_id = world_id
        self.add_log(f"DASHBOARD: Switching to World ID {world_id}")
        # Hier könntest du den Websocket neu starten oder die Config speichern
        self.config["world_id"] = world_id
        self.save_config()
        self.start_websocket_thread()

    def ps2_process_monitor(self):
        """Überwacht den Prozess und nutzt Signale."""
        self.ps2_running = None
        import subprocess
        import time

        print("MONITOR: Thread wartet auf GUI...")
        time.sleep(2.0)
        print("MONITOR: Thread gestartet.")

        while True:
            try:
                # Tasklist Abfrage
                output = subprocess.check_output('TASKLIST /FI "IMAGENAME eq PlanetSide2_x64.exe"', shell=True).decode(
                    "cp1252", errors="ignore")
                is_now_running = "PlanetSide2_x64.exe" in output

                if self.ps2_running is None or is_now_running != self.ps2_running:
                    self.ps2_running = is_now_running

                    if is_now_running:
                        print("MONITOR: Spiel erkannt -> Sende Signal START")
                        # STATT QTIMER: Signal senden!
                        self.worker_signals.game_status_changed.emit(True)
                    else:
                        if self.ps2_running is not None:
                            print("MONITOR: Spiel weg -> Sende Signal STOP")
                        # STATT QTIMER: Signal senden!
                        self.worker_signals.game_status_changed.emit(False)

            except Exception as e:
                print(f"Monitor Error: {e}")

            time.sleep(4)

    def start_path_edit(self):
        """Aktiviert den Klick-Modus für die Messer-Linie"""
        if self.overlay_win:
            # 1. Path-Modus im Overlay einschalten
            self.overlay_win.path_edit_active = True
            # 2. Maus-Durchlässigkeit ausschalten, damit Klicks registriert werden
            self.overlay_win.set_mouse_passthrough(False)
            # 3. Alten Pfad für neue Aufnahme leeren
            self.overlay_win.custom_path = []
            self.add_log("PATH-EDIT: Klicke jetzt um den Schädel. Beende mit 'SAVE STREAK'.")

    def start_path_record(self):
        if not self.overlay_win: return
        ui = self.ovl_config_win

        is_recording = getattr(self.overlay_win, "path_edit_active", False)

        if not is_recording:
            # --- START ---
            self.overlay_win.path_edit_active = True
            self.overlay_win.set_mouse_passthrough(False)
            self.overlay_win.custom_path = []

            # Layer aktivieren & Fokus holen
            self.overlay_win.path_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.overlay_win.path_layer.setGeometry(self.overlay_win.rect())
            self.overlay_win.path_layer.show()
            self.overlay_win.path_layer.raise_()
            self.overlay_win.activateWindow()
            self.overlay_win.setFocus()

            # QT BUTTON UPDATE
            ui.btn_path_record.setText("STOP RECORDING (SPACE)")
            ui.btn_path_record.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold;")

            # Dummy Streak anzeigen
            self.temp_streak_backup = getattr(self, 'killstreak_count', 0)
            self.killstreak_count = 10
            self.streak_factions = (["TR", "NC", "VS"] * 4)[:10]
            self.update_streak_display()

            self.add_log("PATH: Recording started. Click points -> Press SPACE to save.")
        else:
            # --- STOP ---
            self.overlay_win.path_edit_active = False
            self.overlay_win.set_mouse_passthrough(True)
            self.overlay_win.path_layer.hide()

            # QT BUTTON RESET
            ui.btn_path_record.setText("REC PATH")
            ui.btn_path_record.setStyleSheet("background-color: #aa4400; color: white; font-weight: bold;")

            # Pfad speichern (übernimmt custom_path automatisch aus Overlay)
            self.save_streak_settings_from_qt()
            self.add_log("PATH: Recording stopped and saved.")

    def clear_path(self):
        if "streak" in self.config:
            self.config["streak"]["custom_path"] = []
            if self.overlay_win: self.overlay_win.custom_path = []
            self.save_config()
            self.update_streak_display()
            self.add_log("PATH: Pfad gelöscht.")



    def center_crosshair_qt(self):
        """Zentriert das Crosshair basierend auf der aktuellen Overlay-Größe."""
        if not self.overlay_win:
            self.add_log("ERR: Overlay nicht gestartet. Bitte PS2 starten oder Overlay aktivieren.")
            return

        # 1. Tatsächliche Bildschirmgröße vom Overlay holen
        screen_w = self.overlay_win.width()
        screen_h = self.overlay_win.height()
        current_ui_scale = self.overlay_win.ui_scale

        # 2. Die Mitte berechnen
        mid_x = screen_w // 2
        mid_y = screen_h // 2

        # 3. WICHTIG: Rückrechnung auf die Config-Koordinaten (1080p Basis)
        # Da update_crosshair() später wieder 'self.s()' (Skalierung) anwendet,
        # müssen wir hier durch die Skalierung teilen.
        config_x = int(mid_x / current_ui_scale)
        config_y = int(mid_y / current_ui_scale)

        # 4. In Config schreiben
        if "crosshair" not in self.config: self.config["crosshair"] = {}
        self.config["crosshair"]["x"] = config_x
        self.config["crosshair"]["y"] = config_y

        # Aktivieren, damit man es sieht
        self.ovl_config_win.check_cross.setChecked(True)

        # 5. Speichern und Anzeigen
        self.save_crosshair_settings_qt()
        self.add_log(f"CROSSHAIR: Zentriert auf {config_x}x{config_y} (Screen: {screen_w}x{screen_h})")

    def apply_crosshair_settings(self):
        try:
            # 1. Pfad auslesen
            new_file = self.ent_cross_path.get()

            # 2. Aktiv-Status auslesen (Checkbox)
            if hasattr(self, 'crosshair_active_var'):
                is_active = self.crosshair_active_var.get()
            else:
                is_active = True

            # 3. Config updaten
            if "crosshair" not in self.config:
                self.config["crosshair"] = {}

            # Wir speichern den WUNSCH des Users (Checkbox-Status)
            self.config["crosshair"]["file"] = new_file
            self.config["crosshair"]["active"] = is_active

            current_size = self.config["crosshair"].get("size", 32)
            self.config["crosshair"]["size"] = current_size

            # Permanent speichern
            self.save_config()
            self.add_log(f"SYSTEM: Crosshair-Konfiguration aktualisiert.")

            # --- LOGIK-FIX: Sichtbarkeit ---
            # Wir zeigen es nur an, wenn der User es will (is_active) UND das Spiel läuft.
            # (Ausnahme: Edit-Modus, aber das regelt das Overlay selbst, wenn wir False senden)
            game_running = getattr(self, 'ps2_running', False)
            should_show = is_active and game_running

            # Live-Update an das Qt-Fenster senden
            if self.overlay_win:
                full_path = get_asset_path(new_file)
                self.overlay_win.update_crosshair(full_path, current_size, should_show)

        except Exception as e:
            self.add_log(f"Error saving crosshair: {e}")
            traceback.print_exc()

    def save_crosshair_settings_qt(self):
        """Liest UI-Werte aus dem Crosshair-Tab, speichert in Config und updatet Overlay."""
        ui = self.ovl_config_win

        # 1. Werte aus der GUI lesen
        is_active = ui.check_cross.isChecked()
        file_path = ui.cross_path.text().strip()

        # 2. Config Dictionary vorbereiten, falls nicht existent
        if "crosshair" not in self.config:
            self.config["crosshair"] = {}

        # 3. Werte aktualisieren (alte Werte wie Größe/Position beibehalten)
        self.config["crosshair"]["active"] = is_active
        self.config["crosshair"]["file"] = file_path

        # Fallback für Größe, falls noch nicht gesetzt
        if "size" not in self.config["crosshair"]:
            self.config["crosshair"]["size"] = 32

        # 4. In datei speichern
        self.save_config()

        # 5. Overlay live aktualisieren (wenn Spiel läuft oder Edit Mode an ist)
        if self.overlay_win:
            # Pfad auflösen
            full_path = get_asset_path(file_path)

            # Soll es angezeigt werden? (User will es AN + (Spiel läuft ODER Edit Mode))
            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, 'is_hud_editing', False)
            should_show = is_active and (game_running or edit_mode)

            size = self.config["crosshair"].get("size", 32)

            # Update Befehl an Overlay senden
            self.overlay_win.update_crosshair(full_path, size, should_show)

        # Log nur schreiben, wenn es kein automatisches Event beim Tippen ist (optional)
        # self.add_log("CROSSHAIR: Einstellungen gespeichert.")

    def get_time_diff_str(self, past_date_str, mode="login"):
        if not past_date_str or past_date_str == "Unknown":
            return "Unknown"
        try:
            from datetime import datetime
            # Die API gibt Daten wie "2026-01-15 07:14:15" zurück
            # Wir versuchen das Standard-Format zu parsen
            try:
                past_date = datetime.strptime(past_date_str, '%Y-%m-%d %H:%M:%S')
            except:
                # Fallback falls Millisekunden dabei sind
                past_date = datetime.strptime(past_date_str.split(".")[0], '%Y-%m-%d %H:%M:%S')

            now = datetime.now()
            diff = now - past_date

            # 12h Format mit AM/PM
            pretty_date = past_date.strftime('%Y-%m-%d %I:%M%p MEZ')

            if mode == "login":
                days = diff.days
                hours = diff.seconds // 3600
                return f"{pretty_date} ({days}d {hours}h)"
            else:
                years = diff.days // 365
                months = (diff.days % 365) // 30
                return f"{pretty_date} ({years}Y {months}M)"
        except Exception as e:
            print(f"Zeitfehler: {e}")
            return past_date_str

    def load_item_db(self, filepath):
        """Lädt die Waffen-Datenbank aus dem assets-Ordner"""
        self.item_db = {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                next(f)  # Überspringt: Item ID, Item Category, Is Vehicle Weapon...
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 6:
                        item_id = parts[0]
                        item_name = parts[3]
                        weapon_class = parts[1]  # 'none', 'max', 'infantry', 'vehicle'

                        # Wir speichern es so, dass du später leicht darauf zugreifen kannst
                        self.item_db[item_id] = {
                            "name": item_name,
                            "type": weapon_class
                        }
            print(f"Datenbank geladen: {len(self.item_db)} Items gefunden.")
        except Exception as e:
            print(f"Fehler beim Laden der Item-DB: {e}")


    def load_config(self):
        """Lädt die zentrale Konfiguration."""
        config_path = os.path.join(BASE_DIR, "config.json")
        default_conf = {
            "ps2_path": "",
            "overlay_master_active": True,  # <--- WICHTIG: Standard auf True setzen!
            "crosshair": {"file": "crosshair.png", "size": 32, "active": True},
            "events": {},
            "streak": {"img": "KS_Counter.png", "active": True}
        }

        loaded_conf = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded_conf = json.load(f)
            except Exception as e:
                print(f"Config Load Error: {e}")

        # Fehlende Werte mit Standards auffüllen (Merge)
        default_conf.update(loaded_conf)
        return default_conf


    def save_overlay_config(self):
        """Wrapper, damit alte Aufrufe im Code weiterhin funktionieren"""
        self.save_config()
        self.add_log("Einstellungen in config.json gesichert.")



    # --- UI & NAVIGATION ---

    def show_dashboard(self):
        """Wechselt in der Qt-Oberfläche zum Dashboard-Tab"""
        self.current_tab = "Dashboard"
        # Falls dein MainHub ein QStackedWidget für Tabs nutzt:
        if hasattr(self.main_hub, 'stacked_widget'):
            # Index 0 ist meist das Dashboard
            self.main_hub.stacked_widget.setCurrentIndex(0)

        self.add_log("DASHBOARD: View active.")
        # Initialer Trigger für Daten-Update
        self.update_live_graph()


    def update_dashboard_elements(self):
        """Sendet echte Live-Daten an das neue PyQt6 Dashboard via Signale."""
        if not hasattr(self, 'dash_window') or not hasattr(self, 'dash_controller'):
            return

        # Aktuell ausgewählte Server-ID holen (Standard: 10/EU)
        current_wid = str(getattr(self, 'current_world_id', '10'))

        # 1. POPULATION (Total inkl. NSO/Unknown für den Graphen)
        total_players = self.live_stats.get("Total", 0)
        self.dash_controller.signals.update_population.emit(total_players)

        # 2. FRAKTIONEN (Für die Balken)
        # FIX: Wir senden KEINE "NSO" Daten an die Balken-Logik.
        # Dadurch berechnet das Dashboard die 100% Basis nur aus (TR + NC + VS).
        # Unzugewiesene NSO verfälschen so nicht mehr die Balance-Anzeige.
        faction_data = {
            "TR": self.live_stats.get("TR", 0),
            "NC": self.live_stats.get("NC", 0),
            "VS": self.live_stats.get("VS", 0)
            # "NSO": ...  <-- ENTFERNT für die %-Berechnung
        }
        self.dash_controller.signals.update_factions.emit(faction_data)

        # 3. PLAYER LISTE VORBEREITEN
        active_ids = self.active_players.keys()
        now = time.time()
        prepared_players = []

        for p_id, p in self.session_stats.items():
            # Nur Spieler berücksichtigen, die noch als 'aktiv' markiert sind
            if not isinstance(p, dict) or p_id not in active_ids:
                continue

            # --- SERVER FILTER ---
            if str(p.get("world_id", "0")) != current_wid:
                continue

            # --- NAMEN-FIX ---
            p_name = p.get("name")
            if p_name in ["Unknown", "Searching...", None]:
                p_name = self.name_cache.get(p_id, f"ID: {p_id[-4:]}")

            # --- KPM LOGIK ---
            p_start = p.get("start", now)
            active_min = max((now - p_start) / 60, 0.5)

            # Paket schnüren
            prepared_players.append({
                "name": p_name,
                "fac": p.get("faction", "NSO"),  # Hier ist NSO ok, damit man sieht wer es ist
                "k": p.get("k", 0),
                "d": p.get("d", 0),
                "a": p.get("a", 0),
                "active_min": active_min
            })

        # 4. SORTIEREN & SENDEN
        prepared_players.sort(key=lambda x: x['k'], reverse=True)

        self.dash_controller.signals.update_top_list.emit(prepared_players)
        self.dash_controller.signals.update_db_count.emit(self.db_player_count)


    def switch_server(self, name, new_id):
        """Wechselt die Anzeige-ID und löscht lokale Stats (kein Reconnect nötig)"""
        if str(new_id) == str(self.current_world_id) and getattr(self, "needs_reconnect", False) == False:
            return

        self.add_log(f"SYSTEM: Dashboard-Filter auf {name} (ID: {new_id}) gesetzt.")

        # 1. Variablen updaten
        self.current_server_name = name
        self.current_world_id = str(new_id)

        # 2. Config speichern
        self.config["world_id"] = self.current_world_id
        self.save_config()

        # 3. Label aktualisieren
        if hasattr(self, 'lbl_server_title'):
            self.lbl_server_title.config(text=f"{name.upper()} LIVE TELEMETRY ▾")

        # 4. DATEN RESET (Damit der neue Server bei 0 anfängt)
        self.pop_history = [0] * 100
        self.session_stats = {}
        self.active_players = {}
        self.live_stats = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0, "Total": 0}

        if self.current_tab == "Dashboard":
            self.update_dashboard_elements()

    def get_server_name_by_id(self, world_id):
        """Sucht den Anzeigenamen zum Server anhand der World-ID"""
        world_id = str(world_id)
        for name, wid in self.server_map.items():
            if str(wid) == world_id:
                return name
        return f"Unknown ({world_id})"

    def save_config(self):
        """Speichert die aktuelle Konfiguration sicher auf Festplatte."""
        try:
            # Wir säubern die Config von evtl. eingeschlichenen Qt-Objekten
            clean_config = {}
            for k, v in self.config.items():
                # Nur einfache Datentypen zulassen
                if isinstance(v, (str, int, float, bool, dict, list)):
                    clean_config[k] = v

            config_path = os.path.join(self.BASE_DIR, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(clean_config, f, indent=4)
            self.add_log("SYS: Konfiguration erfolgreich gespeichert.")
        except Exception as e:
            self.add_log(f"ERR: Fehler beim Speichern der JSON: {e}")

    def destroy_overlay_window(self):
        if self.overlay_win:
            self.overlay_win.hide()
        self.overlay_running = False
        self.add_log("Overlay: deaktiviert.")

    def create_overlay_window(self):
        if self.overlay_win:
            self.overlay_win.show()
            self.overlay_win.raise_()
            self.overlay_running = True
            self.overlay_enabled = True
            self.add_log("Overlay: aktiviert.")

    def trigger_overlay_event(self, event_type):
        """Triggert Bild/Sound im Overlay.
           Logik:
           - Queue AN: Individuelle Dauer > Globale Dauer
           - Queue AUS: Globale Dauer überschreibt immer (Force Override)
        """
        if not hasattr(self, 'overlay_win') or not self.overlay_win:
            return

        # 1. CONFIG-DATEN SUCHEN (ROBUST & CASE-INSENSITIVE)
        events_dict = self.config.get("events", {})
        event_data = events_dict.get(event_type)

        # Fallback Suche (Case-Insensitive)
        if not event_data:
            for key, val in events_dict.items():
                if key.lower() == event_type.lower():
                    event_data = val
                    break

        if not event_data:
            return

        # 2. KOORDINATEN & STATUS LADEN
        try:
            abs_x = int(event_data.get("x", event_data.get("x_offset", 0)))
            abs_y = int(event_data.get("y", event_data.get("y_offset", 0)))
            scale = float(event_data.get("scale", 1.0))
        except (ValueError, TypeError):
            abs_x, abs_y, scale = 0, 0, 1.0

        # --- NEUE DAUER-LOGIK (DURATION) ---
        queue_active = self.config.get("event_queue_active", True)
        global_dur = int(self.config.get("event_global_duration", 3000))
        specific_dur = int(event_data.get("duration", 0))


        if not queue_active:
            # MODUS: QUEUE AUS -> Globaler Timer erzwingen!
            # Wir ignorieren hier bewusst 'specific_dur', damit alle Events
            # gleich lange stehen bleiben (wie gewünscht).
            dur = global_dur
        else:
            # MODUS: QUEUE AN -> Individuelle Dauer hat Vorrang
            if specific_dur > 0:
                dur = specific_dur
            else:
                dur = global_dur  # Fallback


        if (event_type.lower() == "hitmarker"):
            dur = specific_dur

        # 3. BILD-PFAD ERMITTELN
        img_path = ""
        img_name = event_data.get("img")
        if img_name:
            temp_path = get_asset_path(img_name)
            if os.path.exists(temp_path):
                img_path = temp_path

        # 4. SOUND-PFAD ERMITTELN
        sound_path = ""
        has_sound = globals().get("HAS_SOUND", False)
        if has_sound:
            snd_name = event_data.get("snd")
            if snd_name:
                temp_snd = get_asset_path(snd_name)
                if os.path.exists(temp_snd):
                    sound_path = temp_snd

        # 5. FLAG SETZEN: Ist es ein Hitmarker?
        is_hitmarker = (event_type.lower() == "hitmarker")

        # 6. SIGNAL SENDEN
        if img_path or sound_path:
            self.overlay_win.signals.show_image.emit(img_path, sound_path, dur, abs_x, abs_y, scale, is_hitmarker)

    def start_fade_out(self, tag):
        """Lässt ein Canvas-Objekt nach einer Verzögerung verschwinden (ohne Bewegung)"""
        if not hasattr(self, 'ovl_canvas'): return

        # Prüfen, ob das Item existiert
        items = self.ovl_canvas.find_withtag(tag)
        if not items: return

        # Wir machen das Item erst unsichtbar (Zustand 'hidden')
        # Das ist performanter als sofortiges Löschen, falls noch Prozesse darauf zugreifen
        self.ovl_canvas.itemconfig(tag, state='hidden')

        # Nach einer kurzen Sicherheits-Verzögerung löschen wir es endgültig aus dem Speicher
        self.root.after(100, lambda: self.cleanup_item(tag))

    def cleanup_item(self, tag):
        """Endgültiges Löschen aus Canvas und Speicher"""
        self.ovl_canvas.delete(tag)
        # Referenz aus dem Dictionary löschen, damit der RAM nicht voll läuft
        if hasattr(self, 'active_event_photos') and tag in self.active_event_photos:
            del self.active_event_photos[tag]

    def toggle_event_queue_qt(self):
        """Schaltet das Queue-System an oder aus (PyQt6 Portierung)."""
        # 1. Aktuellen Status aus der Config holen (Source of Truth)
        current_state = self.config.get("event_queue_active", True)
        new_state = not current_state

        # 2. Speichern
        self.config["event_queue_active"] = new_state
        self.save_config()

        # 3. GUI aktualisieren (Zugriff auf das Overlay-Config Fenster)
        ui = self.ovl_config_win

        # Button Status synchronisieren
        ui.btn_queue_toggle.setChecked(new_state)

        if new_state:
            ui.btn_queue_toggle.setText("QUEUE: ON")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; padding: 10px;"
            )
            self.add_log("SYS: Event Queue ENABLED (Sequential Playback)")
        else:
            ui.btn_queue_toggle.setText("QUEUE: OFF")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #440000; color: #ffcccc; font-weight: bold; padding: 10px;"
            )
            self.add_log("SYS: Event Queue DISABLED (Instant Overwrite)")

        # 4. Overlay informieren (WICHTIG!)
        if self.overlay_win:
            # Variable im Overlay setzen
            self.overlay_win.queue_enabled = new_state

            # Wenn ausgeschaltet, Warteschlange sofort leeren
            if not new_state:
                if hasattr(self.overlay_win, 'clear_queue_now'):
                    self.overlay_win.clear_queue_now()
                else:
                    # Fallback, falls die Methode im QtOverlay anders heißt
                    # (Löscht die interne Liste von Events)
                    if hasattr(self.overlay_win, 'event_queue'):
                        self.overlay_win.event_queue.clear()

    def browse_file_qt(self, line_edit_widget, type_):
        # HIER HABE ICH *.gif HINZUGEFÜGT:
        ft = "Images (*.png *.jpg *.jpeg *.gif)" if type_ == "png" else "Audio (*.mp3 *.wav *.ogg)"

        from PyQt6.QtWidgets import QFileDialog
        # self.main_hub als Parent nutzen, damit das Fenster zentriert ist
        file_path, _ = QFileDialog.getOpenFileName(self.main_hub, "Datei auswählen", self.BASE_DIR, ft)

        if file_path:
            filename = os.path.basename(file_path)
            target_path = get_asset_path(filename)

            try:
                # Datei in assets kopieren, falls sie woanders herkommt
                if os.path.abspath(file_path) != os.path.abspath(target_path):
                    shutil.copy2(file_path, target_path)
            except Exception as e:
                self.add_log(f"ERR: Kopier-Fehler: {e}")

            # Textfeld setzen
            line_edit_widget.setText(filename)

    def load_event_ui_data(self, event_type):
        """Lädt Config-Daten eines Events in die Qt-UI Felder"""
        if not event_type: return

        data = self.config.get("events", {}).get(event_type, {})
        ui = self.ovl_config_win

        # Felder füllen
        img_name = data.get("img", "")
        ui.ent_evt_img.setText(img_name)

        ui.ent_evt_snd.setText(data.get("snd", ""))
        ui.ent_evt_duration.setText(str(data.get("duration", 3000)))

        # Slider setzen
        raw_scale = data.get("scale", 1.0)
        ui.slider_evt_scale.setValue(int(raw_scale * 100))

        # Label aktualisieren
        ui.lbl_editing.setText(f"EDITING: {event_type}")

        # --- FIX: VORSCHAU IM CONFIG-FENSTER AKTUALISIEREN ---
        # Wir bauen den vollen Pfad, damit das Label das Bild findet
        if img_name:
            full_path = get_asset_path(img_name)
            ui.update_preview_image(full_path)
        else:
            ui.update_preview_image(None)

        # Falls wir im Edit-Modus sind: Preview im Overlay verschieben
        if getattr(self, "is_hud_editing", False) and self.overlay_win:
            ax = int(data.get("x", 100) * self.overlay_win.ui_scale)
            ay = int(data.get("y", 200) * self.overlay_win.ui_scale)
            self.overlay_win.safe_move(self.overlay_win.event_preview_label, ax, ay)

    def save_event_ui_data(self):
        """Speichert das Event, auch wenn Felder leer sind (Reset)."""
        ui = self.ovl_config_win

        # Welches Event bearbeiten wir gerade?
        etype = ui.lbl_editing.text().replace("EDITING: ", "").strip()
        if etype == "NONE" or not etype:
            return

        if "events" not in self.config: self.config["events"] = {}
        existing_data = self.config["events"].get(etype, {})

        # Koordinaten behalten (vom Overlay oder Config)
        if self.overlay_win and getattr(self.overlay_win, 'event_preview_label',
                                        None) and self.overlay_win.event_preview_label.isVisible():
            pos = self.overlay_win.event_preview_label.pos()
            save_x = int(pos.x() / self.overlay_win.ui_scale)
            save_y = int(pos.y() / self.overlay_win.ui_scale)
        else:
            save_x = existing_data.get("x", 100)
            save_y = existing_data.get("y", 100)

        # Daten auslesen (mit .strip() um Leerzeichen zu killen)
        img_val = ui.ent_evt_img.text().strip()
        snd_val = ui.ent_evt_snd.text().strip()

        # Dauer sicherstellen
        try:
            dur_val = int(ui.ent_evt_duration.text())
        except ValueError:
            dur_val = 3000

        # Update (Wir überschreiben alles, auch wenn es leer ist -> so kann man löschen)
        self.config["events"][etype] = {
            "img": img_val,
            "snd": snd_val,
            "scale": ui.slider_evt_scale.value() / 100.0,
            "duration": dur_val,
            "x": save_x,
            "y": save_y
        }

        self.save_config()
        self.add_log(f"UI: Event '{etype}' gespeichert (Img: '{img_val}').")





    def stop_overlay_logic(self):
        """Versteckt alle Overlay-Elemente (Stats, Crosshair, Feed, Streak)"""

        if self.overlay_win:
            # 1. Stats Widget verstecken
            if hasattr(self.overlay_win, 'stats_bg_label'):
                self.overlay_win.stats_bg_label.hide()
                self.overlay_win.stats_text_label.hide()

            # 2. Killfeed verstecken & leeren
            if hasattr(self.overlay_win, 'feed_label'):
                self.overlay_win.feed_label.hide()
                self.overlay_win.feed_label.setText("")

            # 3. Killstreak komplett aufräumen
            if hasattr(self.overlay_win, 'streak_bg_label'):
                self.overlay_win.streak_bg_label.hide()
            if hasattr(self.overlay_win, 'streak_text_label'):
                self.overlay_win.streak_text_label.hide()
            # Alle Messer-Labels verstecken
            if hasattr(self.overlay_win, 'knife_labels'):
                for l in self.overlay_win.knife_labels:
                    l.hide()
                    l._is_active = False

            # --- NEU: Crosshair explizit verstecken ---
            # Das sorgt dafür, dass es sofort weg ist, wenn Overlay gestoppt wird
            if hasattr(self.overlay_win, 'crosshair_label'):
                self.overlay_win.crosshair_label.hide()

        # Zähler  resetten
        self.killstreak_count = 0
        self.kill_counter = 0
        self.streak_factions = []
        self.streak_slot_map = []

        # WICHTIG: Das Overlay über den neuen Stand (0) informieren
        self.update_streak_display()

        # 4. Status im GUI updaten
        if hasattr(self, 'ovl_status_label'):
            self.ovl_status_label.config(text="STATUS: STANDBY", fg="#7a8a9a")

    def refresh_ingame_overlay(self):
        """Der Herzschlag des Overlays: Daten, HTML und Position."""
        if not self.overlay_win: return

        # Loop sofort neu planen (damit er nie stirbt, auch bei Fehlern)
        # Wir speichern die ID, falls wir ihn mal stoppen müssten (optional)
        QTimer.singleShot(1000, self.refresh_ingame_overlay)

        # 1. Status prüfen
        master_switch = self.config.get("overlay_master_active", True)
        game_running = getattr(self, 'ps2_running', False)
        test_active = getattr(self, 'is_stats_test', False)
        edit_active = getattr(self, 'is_hud_editing', False)

        cfg = self.config.get("stats_widget", {})
        active_config = cfg.get("active", True)

        # Soll es sichtbar sein?
        should_be_visible = (master_switch and (game_running or test_active) and active_config) or edit_active

        if should_be_visible:
            # 2. Daten sammeln
            if test_active:
                kills, deaths, hs, hsrkills, start_time = 15, 5, 6, 10, time.time() - 3600
            elif edit_active and not game_running:
                # Dummy Daten für Edit Mode (damit man was sieht)
                kills, deaths, hs, hsrkills, start_time = 42, 12, 20, 45, time.time() - 3600
            else:
                # LIVE DATEN
                my_id = self.current_character_id
                if my_id and my_id in self.session_stats:
                    s = self.session_stats[my_id]
                    kills = s.get("k", 0)
                    deaths = s.get("d", 0)
                    hs = s.get("hs", 0)
                    hsrkills = s.get("hsrkill", 0)
                    start_time = s.get("start", time.time())
                else:
                    kills, deaths, hs, hsrkills, start_time = 0, 0, 0, 0, time.time()

            # 3. Berechnungen
            kd = kills / max(1, deaths)
            hsr = (hs / hsrkills * 100) if hsrkills > 0 else 0
            dur_min = (time.time() - start_time) / 60
            kpm = kills / max(1, dur_min) if dur_min > 0 else 0.0
            hrs = int(dur_min // 60)
            mns = int(dur_min % 60)

            # 4. HTML Bauen
            # Wir nutzen immer denselben Aufbau, damit nichts springt
            kd_col = "#00ff00" if kd >= 2.0 else ("#ffff00" if kd >= 1.0 else "#ff4444")

            # WICHTIG: Nutze exakt diesen String-Aufbau
            html = f"""
            <div style="font-family: 'Black Ops One', sans-serif; font-weight: bold; color: #00f2ff; 
                        text-shadow: 1px 1px 2px #000; text-align: center; font-size: 22px; white-space: nowrap;">
                KD: <span style="color: {kd_col};">{kd:.2f}</span> &nbsp;&nbsp;
                K: <span style="color: white;">{kills}</span> &nbsp;&nbsp;
                D: <span style="color: white;">{deaths}</span> &nbsp;&nbsp;
                HSR: <span style="color: #ffcc00;">{hsr:.0f}%</span> &nbsp;&nbsp;
                KPM: <span style="color: #ffcc00;">{kpm:.1f}</span> &nbsp;&nbsp;
                <span style="color: #aaa;">TIME: {hrs:02d}:{mns:02d}</span>
            </div>
            """

            # Im Edit-Modus nehmen wir die Konstante, falls definiert, sonst den String von oben
            if edit_active and not game_running:
                # Falls du die DUMMY_STATS_HTML Konstante in main.py hast:
                if 'DUMMY_STATS_HTML' in globals():
                    html = DUMMY_STATS_HTML

            # 5. Bild Pfad
            raw_name = cfg.get("img", "").strip()
            final_img_path = ""
            if raw_name:
                asset_path = get_asset_path(raw_name)
                if os.path.exists(asset_path):
                    final_img_path = asset_path
                elif os.path.exists(raw_name):
                    final_img_path = raw_name

            # 6. Overlay Update (Inhalt)
            # Hier wird nur Inhalt gesetzt, keine Position!
            self.overlay_win.set_stats_html(html, final_img_path)

            # 7. Position erzwingen (jedes Mal!)
            # Das verhindert, dass es falsch liegt, wenn es sichtbar wird
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()  # Zwingt Qt zum Neu-Berechnen der Größe

            self.update_stats_position_safe()

        else:
            # Unsichtbar machen
            if hasattr(self.overlay_win, 'stats_bg_label'):
                self.overlay_win.stats_bg_label.hide()
                self.overlay_win.stats_text_label.hide()





    def trigger_auto_voice(self, trigger_key):
        """Drückt V + Zahl basierend auf der Config"""
        # 1. Config prüfen
        cfg = self.config.get("auto_voice", {})
        val = cfg.get(trigger_key, "OFF")

        if val == "OFF": return

        # 2. Cooldown prüfen (damit er nicht spammt, z.B. bei Multi-Kills)
        now = time.time()
        last = getattr(self, "last_voice_time", 0)
        if now - last < 2.5:  # 2.5 Sekunden Pause zwischen Callouts
            return

        self.last_voice_time = now

        # 3. Tastendruck simulieren (Thread damit Mainloop nicht hängt)
        def press():
            try:
                # V drücken
                pydirectinput.press('v')
                time.sleep(0.05)  # Kurze Pause für das Menü
                # Zahl drücken
                pydirectinput.press(val)
                # Loggen für Debug
                print(f"DEBUG: Auto-Voice V-{val} triggered by {trigger_key}")
            except Exception as e:
                print(f"Voice Error: {e}")

        threading.Thread(target=press, daemon=True).start()

    def test_stats_visuals(self):
        """Startet eine Vorschau (Anti-Ghosting Test mit neuem Layout) - PyQt6 Fixed"""
        if not self.overlay_win:
            self.add_log("WARN: Overlay System ist nicht aktiv! Bitte erst starten.")
            return

        self.add_log("UI: Starte visuellen Test (Layout-Check)...")
        self.is_stats_test = True

        # Sofortiges Update des Stats-Balkens (KD, KPM etc.) erzwingen
        self.refresh_ingame_overlay()

        # Test-Szenarien (Typ, Name, Tag, IsHS, KD)
        test_scenarios = [
            ("kill", "SweatyHeavy", "B0SS", True, 3.5),
            ("kill", "RandomBlueberry", "", False, 0.8),
            ("revive", "HelpfulMedic", "SKL", False, 0.0),
            ("death", "SniperMain420", "D34D", True, 2.1),
            ("kill", "AnotherVictim", "TR", True, 1.2),
            ("kill", "GhostTarget_1", "VS", False, 1.5),
            ("death", "GhostTarget_2", "NC", True, 4.0),
            ("revive", "MedicMain", "TR", False, 0.0)
        ]

        def send_fake_feed(t_type, name, tag, is_hs, kd_val):
            # Basis-Style für den Text
            base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

            # Tag Formatierung
            tag_display = f"[{tag}]" if tag else ""

            # Icon Logik
            icon_html = ""
            if is_hs:
                hs_icon = self.config.get("killfeed", {}).get("hs_icon", "headshot.png")
                hs_path = get_asset_path(hs_icon).replace("\\", "/")
                if os.path.exists(hs_path):
                    # Icon ganz links
                    icon_html = f'<img src="{hs_path}" width="40" height="40" style="vertical-align: middle;">&nbsp;'

            # HTML zusammenbauen
            if t_type == "kill":
                msg = f"""<div style="{base_style}">
                        {icon_html}<span style="color: #888;">{tag_display} </span>
                        <span style="color: white;">{name}</span>
                        <span style="color: #aaa; font-size: 16px;"> ({kd_val})</span>
                        </div>"""
            elif t_type == "death":
                msg = f"""<div style="{base_style}">
                        {icon_html}<span style="color: #888;">{tag_display} </span>
                        <span style="color: #ff4444;">{name}</span>
                        <span style="color: #aaa; font-size: 16px;"> ({kd_val})</span>
                        </div>"""
            elif t_type == "revive":
                msg = f"""<div style="{base_style}">
                        <span style="color: #00ff00;">✚ REVIVED BY </span>
                        <span style="color: white;">{name}</span>
                        </div>"""

            # Signal senden
            if self.overlay_win:
                self.overlay_win.signals.killfeed_entry.emit(msg)

        # Die Test-Events nacheinander abfeuern (PyQt6 QTimer statt root.after)
        for i, (t, n, tag, hs, kd) in enumerate(test_scenarios):
            # QTimer.singleShot(Verzögerung_ms, Funktion)
            QTimer.singleShot(i * 500, lambda t=t, n=n, tag=tag, hs=hs, kd=kd: send_fake_feed(t, n, tag, hs, kd))

        # --- AUTO-CLEAR UND AUFRÄUMEN ---
        def end_test():
            self.is_stats_test = False
            if self.overlay_win:
                self.overlay_win.signals.clear_feed.emit()
                # Stats wieder auf echte Werte (oder 0) setzen
                self.refresh_ingame_overlay()
            self.add_log("UI: Test beendet & Feed bereinigt.")

        # Nach 6 Sekunden aufräumen
        QTimer.singleShot(6000, end_test)

    def get_current_tab_targets(self):
        """Ermittelt sicher, welcher Tab gerade offen ist."""
        try:
            ui = self.ovl_config_win
            idx = ui.tabs.currentIndex()
            # .strip() entfernt Leerzeichen am Anfang/Ende
            tab_text = ui.tabs.tabText(idx).strip().upper()

            print(f"DEBUG: Current Tab Index: {idx}, Text: '{tab_text}'")  # Debug Log

            targets = []
            if "CROSSHAIR" in tab_text:
                targets = ["crosshair"]
            # Hier haben wir "Stats_Feed" in "STATS & FEED" geändert im UI,
            # also prüfen wir auf "STATS" oder "FEED"
            elif "STATS" in tab_text or "FEED" in tab_text:
                targets = ["stats", "feed"]
            elif "KILLSTREAK" in tab_text:
                targets = ["streak"]
            elif "EVENTS" in tab_text:
                targets = ["event"]

            return targets
        except Exception as e:
            print(f"DEBUG: Tab Error: {e}")
            return []

    def toggle_hud_edit_mode(self):
        """
        Startet den Edit-Modus, zeigt Rahmen an, füllt Dummy-Daten ein
        und ermöglicht Drag & Drop.
        """
        if not self.overlay_win:
            self.add_log("ERR: Overlay läuft nicht! Bitte erst Overlay starten.")
            # Versuch es zu starten, falls Master-Switch an ist
            if self.config.get("overlay_master_active", True):
                self.create_overlay_window()
            if not self.overlay_win: return

        # Status umschalten
        self.is_hud_editing = not getattr(self, "is_hud_editing", False)
        is_editing = self.is_hud_editing

        ui = self.ovl_config_win
        targets = self.get_current_tab_targets()

        if not targets:
            self.add_log("INFO: Bitte erst einen Tab auswählen.")
            self.is_hud_editing = False
            return

        # Buttons zum Färben
        btn_list = [ui.btn_edit_hud, ui.btn_edit_cross, ui.btn_edit_streak, ui.btn_edit_hud_stats]

        if is_editing:
            # --- START EDIT (An) ---

            # 1. Overlay klickbar machen
            self.overlay_win.set_mouse_passthrough(False, active_targets=targets)

            # 2. Buttons rot färben
            for btn in btn_list:
                btn.setText("STOP EDIT (SAVE)")
                btn.setStyleSheet(
                    "background-color: #ff0000; color: white; border: 1px solid #cc0000; font-weight: bold;")

            # 3. DUMMY DATEN LADEN (Damit man was sieht!)

            # A) STATS WIDGET (KD Anzeige)
            if "stats" in targets:
                cfg = self.config.get("stats_widget", {})
                img_name = clean_path(cfg.get("img", ""))
                img_path = get_asset_path(img_name) if img_name else ""

                # Zwinge sofortiges Update mit dem konstanten Dummy
                # Damit ist es sofort da und sieht bunt aus
                self.overlay_win.set_stats_html(DUMMY_STATS_HTML, img_path)

                self.overlay_win.stats_bg_label.show()

                # Größe erzwingen für Rahmen (falls Bild fehlt)
                if not img_path or not os.path.exists(img_path):
                    w = int(600 * self.overlay_win.ui_scale)  # Etwas breiter machen für den langen Text
                    h = int(60 * self.overlay_win.ui_scale)
                    self.overlay_win.stats_bg_label.setFixedSize(w, h)
                else:
                    self.overlay_win.stats_bg_label.setFixedSize(16777215, 16777215)
                    self.overlay_win.stats_bg_label.adjustSize()

                # Loop anwerfen (der nutzt jetzt auch DUMMY_STATS_HTML, also kein Springen!)
                self.refresh_ingame_overlay()

            # B) KILLFEED (Text einfügen, damit er Größe bekommt und greifbar wird)
            if "feed" in targets:
                # Wir füllen den Feed mit Fake-Zeilen, damit die Box groß genug zum Klicken ist
                fake_feed = []
                base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

                # 3 Zeilen simulieren
                line1 = f'<div style="{base_style}"><span style="color:#00ff00;">YOU</span> <span style="color:white;">[Kill]</span> <span style="color:#ff0000;">ENEMY</span></div>'
                line2 = f'<div style="{base_style}"><span style="color:#00ff00;">ALLY</span> <span style="color:white;">[HS]</span> <span style="color:#ff0000;">TARGET</span></div>'
                line3 = f'<div style="{base_style}"><span style="color:#888;">[SKL]</span> <span style="color:#ff4444;">SWEATY</span> (4.2)</div>'

                self.overlay_win.feed_label.setText(line1 + line2 + line3)
                self.overlay_win.feed_label.adjustSize()
                self.overlay_win.feed_label.show()

            # C) EVENTS (Preview Bild)
            if "event" in targets:
                img_name = clean_path(ui.ent_evt_img.text())
                if not img_name: img_name = "kill.png"  # Fallback

                if hasattr(self.overlay_win, 'event_preview_label'):
                    full_path = get_asset_path(img_name)
                    from PyQt6.QtGui import QPixmap
                    if os.path.exists(full_path):
                        pix = QPixmap(full_path)
                        scale = ui.slider_evt_scale.value() / 100.0
                        w = int(pix.width() * scale * self.overlay_win.ui_scale)
                        h = int(pix.height() * scale * self.overlay_win.ui_scale)
                        pix = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                        self.overlay_win.event_preview_label.setPixmap(pix)
                        self.overlay_win.event_preview_label.resize(w, h)

                        # Position setzen
                        evt_name = ui.lbl_editing.text().replace("EDITING: ", "").strip()
                        data = self.config.get("events", {}).get(evt_name, {})
                        ex = int(data.get("x", 100) * self.overlay_win.ui_scale)
                        ey = int(data.get("y", 100) * self.overlay_win.ui_scale)
                        self.overlay_win.event_preview_label.move(ex, ey)
                        self.overlay_win.event_preview_label.show()
                        self.overlay_win.event_preview_label.raise_()

            self.add_log(f"UI: Edit-Modus aktiviert für {targets}")

        else:
            # --- STOP EDIT (Aus) ---

            # 1. Overlay wieder durchlässig machen
            self.overlay_win.set_mouse_passthrough(True)

            # 2. Buttons zurücksetzen
            for btn in btn_list:
                btn.setText("MOVE UI")
                btn.setStyleSheet("")

                # 3. Dummy Daten aufräumen (Leeren)
            if "feed" in targets:
                self.overlay_win.feed_label.clear()

            if "stats" in targets:
                # Größe Fix aufheben (auf Standard zurücksetzen)
                if hasattr(self.overlay_win, 'stats_bg_label'):
                    # QWIDGETSIZE_MAX (entfernt fixed size constraint)
                    self.overlay_win.stats_bg_label.setFixedSize(16777215, 16777215)

                    # Wenn wir nicht gerade spielen, Text verstecken
                if not getattr(self, 'ps2_running', False):
                    self.overlay_win.stats_text_label.clear()
                    self.overlay_win.stats_bg_label.hide()
                else:
                    # Wenn wir spielen, echte Daten laden
                    self.refresh_ingame_overlay()

            if "event" in targets:
                if hasattr(self.overlay_win, 'event_preview_label'):
                    self.overlay_win.event_preview_label.hide()

            # 4. Speichern
            if "event" in targets:
                self.save_event_ui_data()
            elif "streak" in targets:
                self.save_streak_settings_from_qt()
            elif "stats" in targets or "feed" in targets:
                self.save_stats_config_from_qt()
            elif "crosshair" in targets:
                self.update_crosshair_from_qt()

            self.add_log("UI: Positionen gespeichert & Edit beendet.")


    def on_overlay_tab_change(self, event):
        """Wenn Tab gewechselt wird während Edit an ist -> Edit Bereich anpassen"""
        if getattr(self, "is_hud_editing", False):
            # Wir beenden kurz den Edit Mode und starten ihn neu für den neuen Tab
            self.toggle_hud_edit_mode()  # Aus
            self.root.after(200, self.toggle_hud_edit_mode)  # An (im neuen Tab)

    def update_stats_widget_position(self):
        # Wird vom Loop erledigt, dient nur als Dummy oder Trigger für sofortigen Refresh
        self.refresh_ingame_overlay()



    def _get_random_slot(self):
        import random
        # Falls die Liste noch nicht existiert
        if not hasattr(self, 'streak_slot_map'): self.streak_slot_map = []

        knives_per_ring = 50
        current_ring = len(self.streak_slot_map) // knives_per_ring

        # Welche Plätze in diesem Ring sind schon belegt?
        used_in_ring = [s % knives_per_ring for s in self.streak_slot_map if s // knives_per_ring == current_ring]

        # Alle freien Plätze finden (0 bis 49)
        available = [x for x in range(knives_per_ring) if x not in used_in_ring]

        if not available:
            return len(self.streak_slot_map)  # Fallback (sollte nie passieren)

        # Zufälligen freien Platz wählen
        chosen = random.choice(available)

        # Rückgabe: Ring-Offset + Zufallsplatz
        return (current_ring * knives_per_ring) + chosen

    def update_streak_display(self):
        """Sendet Streak-Daten sicher per Signal an das Overlay-Fenster"""
        if not self.overlay_win: return

        streak_cfg = self.config.get("streak", {})
        img_path = get_asset_path(streak_cfg.get("img", "KS_Counter.png"))

        current_streak = getattr(self, 'killstreak_count', 0)
        factions = getattr(self, 'streak_factions', [])

        slot_map = getattr(self, 'streak_slot_map', [])

        # WICHTIG: Nutze das Signal-System, um Thread-Fehler zu vermeiden
        self.overlay_win.signals.update_streak.emit(
            img_path,
            current_streak,
            factions,
            streak_cfg,
            slot_map
        )

    def test_streak_visuals(self):
        """
        Startet eine Vorschau mit 20 Messern (PyQt6 kompatibel).
        """
        # 1. Vorherige Timer abbrechen
        if self._streak_test_timer:
            self._streak_test_timer.stop()
            self._streak_test_timer = None

        # 2. Backup erstellen (nur wenn nicht schon im Test-Modus)
        if self._streak_backup is None:
            self._streak_backup = {
                'count': getattr(self, 'killstreak_count', 0),
                'factions': getattr(self, 'streak_factions', []),
                'slots': getattr(self, 'streak_slot_map', [])
            }

        self.add_log("UI: Teste Killstreak-Visuals (20 Messer)...")

        # 3. Testwerte setzen
        self.killstreak_count = 20
        # Erzeuge eine bunte Mischung aus Fraktionen
        self.streak_factions = (["TR", "NC", "VS"] * 7)[:20]

        import random
        # Slots zufällig verteilen
        slots = list(range(20))
        random.shuffle(slots)
        self.streak_slot_map = slots

        # 4. Update an Overlay senden
        self.update_streak_display()

        # 5. Reset-Funktion definieren
        def reset_action():
            if self._streak_backup:
                self.killstreak_count = self._streak_backup['count']
                self.streak_factions = self._streak_backup['factions']
                self.streak_slot_map = self._streak_backup['slots']

                # Overlay zurücksetzen
                self.update_streak_display()

                self._streak_backup = None  # Backup löschen

            self._streak_test_timer = None
            self.add_log("UI: Test beendet.")

        # 6. Timer starten (PyQt6 Weg)
        self._streak_test_timer = QTimer()
        self._streak_test_timer.setSingleShot(True)
        self._streak_test_timer.timeout.connect(reset_action)
        self._streak_test_timer.start(4000)  # 4 Sekunden (wie in deinem Kommentar gewünscht, Code hatte 2000)

    def fade_out(self, tag, alpha=255):
        if alpha > 0:
            alpha -= 15  # Geschwindigkeit des Ausblendens (höher = schneller)

            # Alle Items mit diesem Tag finden
            items = self.ovl_canvas.find_withtag(tag)
            for item in items:
                # Bei Texten können wir einfach die Farbe ändern (Graustufen)
                if self.ovl_canvas.type(item) == "text":
                    # Von Weiß zu Schwarz/Transparent
                    color_val = max(0, alpha)
                    hex_color = f'#{color_val:02x}{color_val:02x}{color_val:02x}'
                    self.ovl_canvas.itemconfig(item, fill=hex_color)

                # Bei Bildern ist es komplexer (erfordert PIL Re-Rendering)
                # Einfachere Lösung: Wir verschieben es leicht oder ändern die Position
                # Für echtes Bild-Alpha müssten wir die PIL-Instanz speichern:

            if alpha <= 0:
                self.ovl_canvas.delete(tag)
            else:
                self.root.after(30, lambda: self.fade_out(tag, alpha))
        else:
            self.ovl_canvas.delete(tag)

    def get_kpm_color(self, val):
        if val >= 5.0: return "#e600ff"
        if val >= 3.0: return "#ff0000"
        if val >= 1.0: return "#00ff00"
        return "white"

    def animate_fade_in(self, step=0):
        # Liste von Farbstufen für den "Glow"-Effekt
        colors = ["#050a0f", "#0a141d", "#0f1e2b", "#142839", "#00f2ff"]
        if step < len(colors):
            current_color = colors[step]
            # Rahmenfarbe animieren
            self.sub_menu_frame.config(highlightbackground=current_color)
            # Textfarbe der Buttons animieren
            for btn in self.sub_buttons:
                btn.config(fg=current_color if step < len(colors) - 1 else "#00f2ff")

            self.root.after(50, lambda: self.animate_fade_in(step + 1))

    def handle_sub_click(self, item):
        self.add_log(f"NAV: Switching to {item}...")
        self.current_sub_tab = item  # Setzt den Namen (z.B. "Weapon stats" oder "Overview")
        self.show_characters()  # Baut die Seite neu auf
        if hasattr(self, 'sub_menu_frame'):
            self.sub_menu_frame.place_forget()

    def show_sub_menu(self, event):
        # Menü positionieren
        self.sub_menu_frame.place(x=50, y=140, relwidth=0.88)
        # Animation starten
        self.animate_fade_in()

    # DATEI: Dior Client.py

    def update_live_graph(self):
        """Berechnet jede Sekunde die aktuellen Stats und triggert das Dashboard-Update."""
        try:
            now = time.time()

            # Aktuell ausgewählte Server-ID holen (Standard auf 10/EU)
            current_wid = str(getattr(self, 'current_world_id', '10'))

            # 1. Fraktions-Zahlen berechnen (MIT FILTER)
            counts = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0}
            total_pop = 0

            # Wir iterieren über die Werte. Achtung: Format kann (Zeit, Fac) oder (Zeit, Fac, Wid) sein
            for val in self.active_players.values():

                # Standardwerte
                fac = "NSO"
                p_wid = current_wid  # Wenn keine ID da ist, zählen wir es sicherheitshalber dazu

                if len(val) == 3:
                    _, fac, p_wid = val  # Neues Format mit World ID
                elif len(val) == 2:
                    _, fac = val  # Altes Format (Fallback)

                # FILTER: Nur zählen, wenn Server ID passt!
                if str(p_wid) != current_wid:
                    continue

                # Zählen
                if fac in counts:
                    counts[fac] += 1
                    total_pop += 1

            self.live_stats.update(counts)
            self.live_stats["Total"] = total_pop

            # 2. Graph-Daten füttern
            elapsed = now - getattr(self, 'session_start_time', now)
            graph_interval = 1.0 if elapsed < 60 else 30.0

            if now - getattr(self, 'last_graph_point_time', 0) >= graph_interval:
                self.pop_history.pop(0)
                self.pop_history.append(total_pop)
                self.last_graph_point_time = now

            # 3. UI UPDATE
            if hasattr(self, 'main_hub') and self.main_hub.stack.currentIndex() == 0:
                self.update_dashboard_elements()

        except Exception as e:
            print(f"Stats-Update Error: {e}")

    def hide_sub_menu(self, event):
        self.root.after(1000, self.check_mouse_leave)

    def check_mouse_leave(self):
        x, y = self.root.winfo_pointerxy()
        widget = self.root.winfo_containing(x, y)
        if widget != self.sub_menu_frame and widget not in self.sub_menu_frame.winfo_children():
            self.sub_menu_frame.place_forget()

    def clear_content(self):
        """Löscht alle Inhalte vom Canvas und zerstört die dazugehörigen Widgets"""
        for item_id in self.content_ids:
            try:
                # Wir holen uns den Namen des Widgets, das in diesem Canvas-Fenster steckt
                widget_path = self.canvas.itemcget(item_id, "window")
                if widget_path:
                    # Wir suchen das echte Widget-Objekt anhand des Namens und zerstören es
                    widget = self.root.nametowidget(widget_path)
                    widget.destroy()
            except Exception:
                # Falls das Widget bereits zerstört wurde oder kein Fenster war
                pass

            # Jetzt löschen wir das Element endgültig vom Canvas
            self.canvas.delete(item_id)

        self.content_ids.clear()

    def show_dashboard(self):
        """Zeigt das neue Qt-Fenster und leert den Tkinter-Bereich."""
        self.clear_content()
        self.current_tab = "Dashboard"

        # Zeige das neue Fenster
        if hasattr(self, 'dash_window'):
            self.dash_window.show()
            self.dash_window.raise_()  # In den Vordergrund

        # Info im Hauptfenster (da es jetzt leer ist)
        tk.Label(self.root, text="DASHBOARD IS RUNNING IN SEPARATE WINDOW",
                 font=("Arial", 16), fg="#444").pack(expand=True)


    def animate_api_light(self, canvas, light_id, color_type, step=0):
        import math
        # Pulsieren berechnen (Sinus-Welle)
        brightness = (math.sin(step) + 1) / 4 + 0.5
        if color_type == "green":
            r, g, b = 0, int(255 * brightness), 0
        else:
            r, g, b = int(255 * brightness), 0, 0

        color_hex = f'#{r:02x}{g:02x}{b:02x}'
        try:
            canvas.itemconfig(light_id, fill=color_hex, outline="#333")
            self.root.after(50, lambda: self.animate_api_light(canvas, light_id, color_type, step + 0.1))
        except:
            pass  # Stoppt, wenn Tab gewechselt wird

    def show_launcher(self):
        self.clear_content()
        self.current_tab = "launcher"

        # Überprüfen, ob das Objekt existiert (Sicherheitscheck)
        if hasattr(self, 'launcher_win'):
            # Optional: Pfad-Info im Footer aktualisieren
            path_info = f"TARGET_PATH: {self.ps2_dir if self.ps2_dir else 'NOT_FOUND'}"
            self.launcher_win.lbl_info.setText(f"STATUS: SYSTEM_READY | {path_info}")

            self.launcher_win.show()
            self.launcher_win.activateWindow()
            self.launcher_win.raise_()
        else:
            self.add_log("ERROR: Launcher window not initialized.")



    def show_settings(self):
        self.clear_content()
        self.current_tab = "settings"

        # Aktuelle Daten in das Qt Fenster laden
        self.settings_win.load_config(self.config, self.ps2_dir)

        self.settings_win.show()
        self.settings_win.raise_()


    def show_characters(self):
        self.clear_content()
        self.current_tab = "characters"
        if hasattr(self, 'char_win'):
            self.char_win.show()
            self.char_win.raise_()

    def update_active_char(self, name):
        """Setzt die interne ID basierend auf dem Namen."""
        if not name: return

        # ID aus Dictionary holen
        cid = self.char_data.get(name, "")
        self.current_character_id = cid

        self.add_log(f"SYS: Tracking aktiv für: {name}")

        # --- OPTIONAL: Server-Switch Logik (falls vorhanden) ---
        try:
            conn = sqlite3.connect("ps2_master.db")
            res = conn.execute("SELECT world_id FROM player_cache WHERE character_id=?", (cid,)).fetchone()
            conn.close()

            if res and res[0]:
                new_world_id = str(res[0])
                # Nur wechseln, wenn unterschiedlich
                if new_world_id != str(self.current_world_id):
                    s_name = self.get_server_name_by_id(new_world_id)
                    # Sicherer Aufruf (Server Logik)
                    self.switch_server(s_name, new_world_id)
        except Exception as e:
            print(f"Server Auto-Switch Error: {e}")

    def refresh_char_list_ui(self, select_name=None):
        """
        Aktualisiert die Charakter-Dropdown-Liste im Overlay-Config Fenster.
        Ersetzt die alte 'refresh_char_menus'.
        """
        if not hasattr(self, 'ovl_config_win'): return

        ui = self.ovl_config_win

        # 1. Signale kurzzeitig blockieren
        # (Verhindert, dass beim Leeren der Liste unnötige Events feuern)
        ui.char_combo.blockSignals(True)

        # 2. Liste leeren und neu füllen
        ui.char_combo.clear()

        # Namen aus dem Dictionary holen und sortieren (optional, aber schöner)
        names = sorted(list(self.char_data.keys()))

        if not names:
            ui.char_combo.addItem("No Characters")
        else:
            ui.char_combo.addItems(names)

        # 3. Den richtigen Charakter auswählen
        if select_name and select_name in names:
            # Wenn ein spezifischer Name gewünscht ist (z.B. nach dem Hinzufügen)
            ui.char_combo.setCurrentText(select_name)
            # Logik manuell anstoßen, da Signale blockiert sind
            self.update_active_char(select_name)

        elif names:
            # Sonst einfach den aktuell aktiven beibehalten, falls er noch da ist
            # Oder auf den ersten zurückfallen
            current = getattr(self, "current_selected_char_name", names[0])
            if current in names:
                ui.char_combo.setCurrentText(current)
            else:
                ui.char_combo.setCurrentIndex(0)
                self.update_active_char(names[0])

        # 4. Signale wieder freigeben
        ui.char_combo.blockSignals(False)


    def cache_worker(self):
        while True:
            ids = []
            try:
                # Sammle IDs aus der Warteschlange (wartet max 5 Sekunden auf neue IDs)
                while len(ids) < 30:
                    ids.append(self.id_queue.get(timeout=5))
            except Empty:
                pass

            if ids:
                try:
                    # Abfrage an Census mit allen Details (inklusive Outfit!)
                    url = (f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/"
                           f"?character_id={','.join(ids)}"
                           f"&c:show=character_id,name.first,faction_id,battle_rank"
                           f"&c:resolve=outfit")

                    # Erst prüfen, ob die Antwort gültig ist
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        try:
                            r = response.json()
                            if 'character_list' in r:
                                conn = sqlite3.connect("ps2_master.db")
                                cursor = conn.cursor()

                                # Sicherstellen, dass der RAM-Cache existiert
                                if not hasattr(self, 'outfit_cache'):
                                    self.outfit_cache = {}

                                for char in r['character_list']:
                                    cid = char['character_id']
                                    name = char['name']['first']
                                    fid = char.get('faction_id', 0)
                                    rank = char.get('battle_rank', {}).get('value', 0)

                                    # Hier holen wir den Outfit-Tag (Alias)
                                    tag = char.get('outfit', {}).get('alias', "")

                                    # 1. In Datenbank speichern (Permanent)
                                    cursor.execute('''INSERT OR REPLACE INTO player_cache 
                                                      (character_id, name, faction_id, battle_rank, outfit_tag) 
                                                      VALUES (?, ?, ?, ?, ?)''',
                                                   (cid, name, fid, rank, tag))

                                    # 2. WICHTIG: Im Arbeitsspeicher (RAM) aktualisieren
                                    # Damit der Census-Listener den Tag SOFORT findet
                                    self.name_cache[cid] = name
                                    self.outfit_cache[cid] = tag

                                conn.commit()
                                conn.close()

                                # GUI-Zähler aktualisieren
                                if hasattr(self, 'cache_label') and self.cache_label.winfo_exists():
                                    try:
                                        conn = sqlite3.connect("ps2_master.db")
                                        count = conn.execute("SELECT COUNT(*) FROM player_cache").fetchone()[0]
                                        conn.close()

                                        QTimer.singleShot(0, lambda c=count: self.cache_label.config(
                                            text=f"Characters in db: {c}"))

                                        self.update_db_count_cache()
                                    except Exception as e:
                                        print(f"DEBUG: Cache Label Update skipped: {e}")
                        except ValueError:
                            self.add_log("SYS: Census API sent invalid JSON (Server busy?)")
                    else:
                        self.add_log(f"SYS: Census API Error {response.status_code}")

                except Exception as e:
                    self.add_log(f"DB-ERROR (Cache): {e}")


    def add_log(self, text):

        print(f"LOG: {text}")  # Backup in der Konsole
        # Bestehender Tkinter Log
        if hasattr(self, 'log_area') and self.log_area:
            self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {text}\n")
            self.log_area.see(tk.END)

        # NEU: Auch an das Qt-Fenster senden
        if hasattr(self, 'char_win'):
            self.char_win.add_log(text)


    def change_background_file(self):
        # Filter für statische Bilder (JPG/PNG)
        f = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
        if f:
            self.gif_path = f

            # Den Pfad in das Config-Objekt schreiben
            self.config["main_background_path"] = f

            # Die Config-Datei permanent speichern
            self.save_config()

            # Die GUI sofort aktualisieren
            self.update_background_view(self.root.winfo_width(), self.root.winfo_height())
            self.add_log(f"SYS: Hintergrund dauerhaft auf {os.path.basename(f)} gesetzt.")

    def execute_launch(self, mode):
        # 1. Verzeichnis-Check
        if not self.ps2_dir or not os.path.exists(self.ps2_dir):
            msg = "ERR: PS2 Directory not found! Check Settings."
            self.add_log(msg)
            self.launcher_win.lbl_info.setText(msg)
            return

        # Pfade definieren
        src = self.source_high if mode == "high" else self.source_low
        dest = os.path.join(self.ps2_dir, "UserOptions.ini")
        exe = os.path.join(self.ps2_dir, "LaunchPad.exe")

        if os.path.exists(src):
            try:
                # Datei kopieren
                shutil.copy2(src, dest)
                self.add_log(f"SYS: Applied {mode} configuration.")

                # Spiel starten
                if os.path.exists(exe):
                    subprocess.Popen([exe])
                    self.add_log("SYS: LaunchPad triggered.")

                    # GUI Feedback
                    self.launcher_win.lbl_info.setText(f"SUCCESS: {mode.upper()} INITIALIZED. CLOSING...")



                else:
                    self.add_log("ERR: LaunchPad.exe not found.")
                    self.launcher_win.lbl_info.setText("ERR: LaunchPad.exe missing!")
            except Exception as e:
                # Hier stand vorher der Fehler-Log, weil 'e' oft den root-Crash enthielt
                self.add_log(f"ERR: Launch interaction failed: {e}")
                self.launcher_win.lbl_info.setText(f"ERR: {e}")
        else:
            msg = f"ERR: Source file missing: {src}"
            self.add_log(msg)
            self.launcher_win.lbl_info.setText(msg)

    def run_search(self, name):
        self.add_log(f"UPLINK: Start search for '{name}' (All-in-One Query)...")
        # UI-Status auf "Warten" setzen
        if hasattr(self, 'char_win'):
            self.char_win.btn_search.setEnabled(False)
            self.char_win.btn_search.setText("SYNCING...")

        def worker():
            try:
                # 1. API ABFRAGE
                url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/?name.first_lower={name.lower()}&c:resolve=world,outfit,stat_history,weapon_stat_by_faction"
                r = requests.get(url, timeout=30).json()

                if not r.get('character_list'):
                    self.add_log(f"DEBUG: Character {name} nicht gefunden.")
                    QTimer.singleShot(0, lambda: self.char_win.btn_search.setEnabled(True))
                    return

                char_data = r['character_list'][0]
                all_stats_container = char_data.get('stats', {})

                # --- SCHRITT 2: STATS EXTRAKTION ---
                stats_history = all_stats_container.get('stat_history', [])

                def get_robust_stat(s_name):
                    entry = next((s for s in stats_history if s.get('stat_name') == s_name), None)
                    if not entry: return 0, 0
                    lt = int(entry.get('all_time', 0))
                    recent = 0
                    day_data = entry.get('day')
                    if isinstance(day_data, dict):
                        recent = sum(int(v) for v in day_data.values() if str(v).isdigit())
                    return lt, recent

                lt_kills, m30_kills = get_robust_stat('kills')
                lt_deaths, m30_deaths = get_robust_stat('deaths')
                lt_score, m30_score = get_robust_stat('score')
                lt_time, m30_time = get_robust_stat('time')

                def safe_div(a, b, r=2):
                    return round(a / max(1, b), r)

                # WICHTIG: Keys exakt so benennen, wie dein UI sie erwartet!
                custom_stats = {
                    'name': char_data.get('name', {}).get('first', '-'),
                    'fac_short': {"1": "VS", "2": "NC", "3": "TR"}.get(str(char_data.get('faction_id')), "NSO"),
                    'server': self.get_server_name_by_id(char_data.get('world_id', '0')),
                    'outfit': char_data.get('outfit', {}).get('alias', 'NONE'),
                    'rank': char_data.get('battle_rank', {}).get('value', '-'),
                    'time_played': f"{int(lt_time / 3600)}h",
                    'lt_kills': lt_kills, 'lt_deaths': lt_deaths,
                    'lt_kd': safe_div(lt_kills, lt_deaths),
                    'lt_kpm': safe_div(lt_kills, lt_time / 60),
                    'lt_kph': safe_div(lt_kills, lt_time / 3600, 1),
                    'lt_spm': int(safe_div(lt_score, lt_time / 60, 0)),
                    'lt_score': f"{int(lt_score / 1000)}k",
                    'm30_kills': m30_kills, 'm30_deaths': m30_deaths,
                    'm30_kd': safe_div(m30_kills, m30_deaths),
                    'm30_kpm': safe_div(m30_kills, m30_time / 60),
                    'm30_spm': int(safe_div(m30_score, m30_time / 60, 0)),
                    'm30_score': f"{int(m30_score / 1000)}k"
                }

                # --- SCHRITT 3: WAFFEN-LOGIK ---
                weapon_list = []
                temp_w = {}
                w_stats = all_stats_container.get('weapon_stat_by_faction', [])

                for entry in w_stats:
                    i_id = entry.get('item_id')
                    if not i_id or i_id == "0": continue
                    if i_id not in temp_w:
                        db_info = self.item_db.get(i_id, {"name": f"Unknown ({i_id})"})
                        temp_w[i_id] = {'id': i_id, 'name': db_info['name'], 'kills': 0, 'shots': 0, 'hits': 0, 'hs': 0}

                    total_val = int(entry.get('value_vs', 0)) + int(entry.get('value_nc', 0)) + int(
                        entry.get('value_tr', 0))
                    s_name = entry.get('stat_name')
                    if s_name in ['weapon_kills', 'weapon_vehicle_kills']:
                        temp_w[i_id]['kills'] += total_val
                    elif s_name == 'weapon_fire_count':
                        temp_w[i_id]['shots'] += total_val
                    elif s_name == 'weapon_hit_count':
                        temp_w[i_id]['hits'] += total_val
                    elif s_name == 'weapon_headshots':
                        temp_w[i_id]['hs'] += total_val

                weapon_list = sorted([w for w in temp_w.values() if w['kills'] > 0],
                                     key=lambda x: x['kills'], reverse=True)[:100]

                self.add_log(f"DEBUG: Processing complete. Found {len(weapon_list)} weapons.")

                # --- DER SICHERE TRANSFER VIA SIGNAL ---
                # Wir "feuern" das Signal ab - Qt kümmert sich um den Rest
                self.char_win.signals.search_finished.emit(custom_stats, weapon_list)

            except Exception as e:
                self.add_log(f"WORKER FATAL: {e}")
                # Falls es kracht, Button trotzdem wieder freigeben (via Signal oder direkt)
                QTimer.singleShot(0, lambda: self.char_win.btn_search.setEnabled(True))

                # Thread starten

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    try:

        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Sorgt für ein einheitliches Dark-Design

        # Deine Logik-Klasse initialisieren (sie erstellt intern den MainHub)
        client = DiorClientGUI()
        sys.exit(app.exec())
    except Exception as e:
        import traceback

        with open("error_log.txt", "w") as f:
            f.write(traceback.format_exc())
        print(traceback.format_exc())