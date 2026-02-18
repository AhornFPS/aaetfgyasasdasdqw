
import os
import sys
import ctypes
import copy
import atexit
from version import VERSION


# 2. Path logic for PyInstaller 6+ (_internal Support)
def resource_path(relative_path):
    """
    Finds resources, whether in script or EXE (_internal).
    """
    if hasattr(sys, '_MEIPASS'):
        # In EXE, _MEIPASS is the path to the '_internal' folder
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

# 3. Environment Variables
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

# Linux-specific: Force XWayland for better overlay independence
# On Wayland, ToolTip windows become "transient" children of the main window
# XWayland gives us true independent overlay positioning
if not sys.platform.startswith("win"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# IMPORTANT: If WebEngine has graphics glitches (black bars), uncomment this:
# os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PyQt6.QtCore import QCoreApplication

# 4. Set plugin path (Most important fix for missing images!)
# Qt must know that the DLLs are now in '_internal'.
# sys._MEIPASS points directly to this '_internal' folder.
if hasattr(sys, '_MEIPASS'):
    QCoreApplication.addLibraryPath(sys._MEIPASS)

# Fix Qt Scaling
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

import shutil
import subprocess
import time
import requests
import threading
import json
import random
from queue import Queue, Empty
try:
    import pydirectinput
except Exception:
    pydirectinput = None

XDO_TOOL = shutil.which("xdotool") if not sys.platform.startswith("win") else None
import sqlite3
import dashboard_qt  # New file must be in the same folder!
import launcher_qt
import characters_qt
import settings_qt
import overlay_config_qt
from discord_presence import DiscordPresenceManager
from census_worker import CensusWorker
from overlay_window import QtOverlay
from dior_utils import BASE_DIR, ASSETS_DIR, IMAGES_DIR, SOUNDS_DIR, CROSSHAIR_DIR, DB_PATH, get_asset_path, log_exception, clean_path, IS_WINDOWS, get_user_data_dir
from dior_db import DatabaseHandler
from twitch_worker import TwitchWorker
from release_updater import ReleaseUpdater

from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout,
    QMainWindow, QListWidget, QStackedWidget,
    QColorDialog, QFileDialog, QMessageBox, QProgressDialog # <--- Added QMessageBox
)
from PyQt6.QtGui import (
    QPixmap,
    QColor,
    QFontDatabase,
    QIcon
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QObject,
    QTimer,
    QThread
)


# Determine path to the current directory
basedir = os.path.dirname(os.path.abspath(__file__))

# Instruct Qt to look in the subfolder for plugins
QCoreApplication.addLibraryPath(os.path.join(basedir, 'imageformats'))

class WorkerSignals(QObject):
    # Signal: Success (True/False), Name, Error Message
    add_char_finished = pyqtSignal(bool, str, str)
    # NEW SIGNAL for the Monitor
    game_status_changed = pyqtSignal(bool)  # True = Start, False = Stop
    # SIGNAL for Server Switch (Thread-Safe)
    request_server_switch = pyqtSignal(str, str)
    # Updater callbacks (Thread-Safe)
    update_check_finished = pyqtSignal(object, str)
    update_download_progress = pyqtSignal(object)
    update_download_finished = pyqtSignal(object, object, str)


class DiorMainHub(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle(f"Better Planetside v{VERSION}")
        self.setWindowIcon(QIcon(get_asset_path("BetterPlannetsideIcon.png")))
        # Default size
        default_w, default_h = 1500, 850
        
        # Load last size from config
        saved_size = self.controller.config.get("window_size", {})
        w = saved_size.get("width", default_w)
        h = saved_size.get("height", default_h)
        self.resize(w, h)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SIDEBAR (Navigation) ---
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(200)
        self.nav_list.setObjectName("NavBar")
        # IMPORTANT: Order must match the stack!
        self.nav_list.addItems(["DASHBOARD", "LAUNCHER", "CHARACTERS", "OVERLAY", "SETTINGS"])

        self.nav_list.setStyleSheet("""
            QListWidget { 
                background-color: #111; 
                border-right: 1px solid #333; 
                outline: none; 
            }
            QListWidget::item { 
                padding: 20px; 
                color: #888; 
                font-family: 'Black Ops One', sans-serif; 
                font-size: 13px;
                text-transform: uppercase;
                border-bottom: 1px solid #1a1a1a;
            }
            QListWidget::item:hover {
                background-color: #1a1a1a;
                color: #bbb;
            }
            QListWidget::item:selected { 
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1a1a, stop:1 #252525); 
                color: #00f2ff; 
                border-left: 4px solid #00f2ff; 
            }
        """)

        # --- CONTENT AREA (Stacked Widget) ---
        self.stack = QStackedWidget()

        # Load windows from controller (DiorClientGUI)
        self.stack.addWidget(self.controller.dash_window)  # Index 0
        self.stack.addWidget(self.controller.launcher_win)  # Index 1
        self.stack.addWidget(self.controller.char_win)  # Index 2
        self.stack.addWidget(self.controller.ovl_config_win)  # Index 3
        self.stack.addWidget(self.controller.settings_win)  # Index 4

        main_layout.addWidget(self.nav_list)
        main_layout.addWidget(self.stack)

        # Internal connection: Click on list -> Check logic -> Stack changes
        self.nav_list.currentRowChanged.connect(self.on_nav_change)

        # Set start page
        self.nav_list.setCurrentRow(0)

    def closeEvent(self, event):
        """Save window size on close."""
        try:
            if hasattr(self.controller, "shutdown_runtime_workers"):
                self.controller.shutdown_runtime_workers()
        except Exception:
            pass

        size = self.size()
        if "window_size" not in self.controller.config:
            self.controller.config["window_size"] = {}
        
        self.controller.config["window_size"]["width"] = size.width()
        self.controller.config["window_size"]["height"] = size.height()
        
        # Persist to disk
        try:
             self.controller.save_config()
        except Exception as e:
             print(f"Error saving window size: {e}")
             
        # Call super closeEvent
        super().closeEvent(event)
        
    def on_nav_change(self, index):
        # Index 1 = LAUNCHER
        if index == 1:
            # Check if path is valid
            path = self.controller.ps2_dir
            if not path or not os.path.exists(path):
                QMessageBox.warning(self, "Missing Path", 
                                    "To use the Launcher feature, you must set the Planetside 2 path in Settings.")
                
                # Revert selection (block signals to avoid recursion)
                self.nav_list.blockSignals(True)
                current_stack_idx = self.stack.currentIndex()
                # If we were already on Launcher (shouldn't happen but safety), go to Dashboard (0)
                if current_stack_idx == 1: 
                    self.nav_list.setCurrentRow(0)
                    self.stack.setCurrentIndex(0)
                else:
                    self.nav_list.setCurrentRow(current_stack_idx)
                self.nav_list.blockSignals(False)
                return

        # If allowed, switch stack
        self.stack.setCurrentIndex(index)

try:
    import pygame

    pygame.mixer.init()
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    print("WARNING: 'pygame' missing. Sounds will not be played.")

sys.excepthook = log_exception

# Global Constants
CONFIG_FILE = "config.json"
CONFIG_SCHEMA_VERSION = 4
LEGACY_UPDATE_REPO = "AhornFPS/Better-Planetside"
DEFAULT_UPDATE_REPO = "cedric12354/Better-Planetside"

class DiorClientGUI:
    def __init__(self):
        # 1. BASE & DB INITIALIZATION
        self.BASE_DIR = BASE_DIR  # Now comes from 'dior_utils' import
        self.db = DatabaseHandler()  # Comes from 'dior_db'
        self.s_id = os.getenv("CENSUS_S_ID", "s:example")

        # 2. LOAD DATA
        self.config = self.load_config()
        self.release_updater = None
        self._update_check_in_progress = False
        self._update_download_in_progress = False
        self._latest_update_info = None
        self._update_download_progress_dialog = None
        self._update_apply_progress_dialog = None
        self.release_updater = self._build_release_updater()
        self.char_data = self.db.load_my_chars()

        # Load cache (Returns 2 dictionaries: Names and Outfits)
        self.name_cache, self.outfit_cache = self.db.load_player_cache()

        # 2. LOGIC VARIABLES
        self.ps2_dir = self.config.get("ps2_path", "")
        self.current_world_id = self.config.get("world_id", "10")
        self.current_character_id = ""
        self.last_tracked_id = ""
        self.is_hud_editing = False
        self.overlay_win = None
        self.discord_presence = None

        self.server_map = {
            "Wainwright (EU)": "10", "Osprey (US)": "1",
            "SolTech (Asia)": "40", "Jaeger (Events)": "19"
        }

        # Signals for Worker
        self.worker_signals = WorkerSignals()
        self.worker_signals.add_char_finished.connect(self.finalize_add_char_slot)
        self.worker_signals.game_status_changed.connect(self.handle_game_status_change)
        self.worker_signals.request_server_switch.connect(self.switch_server)
        self.worker_signals.update_check_finished.connect(self._finish_update_check_qt)
        self.worker_signals.update_download_progress.connect(self._update_download_progress_qt)
        self.worker_signals.update_download_finished.connect(self._finish_update_download_qt)

        # Tracking Variables
        self.killstreak_count = 0
        self.kill_counter = 0
        self.is_dead = False
        self.was_revived = False
        self.is_tk_death = False
        self.debug_overlay_active = False
        self.streak_timeout = 12.0
        self.pop_history = [0] * 100
        self.myTeamId = 0
        self.currentZone = 0
        self.myWorldID = self.current_world_id
        self.last_kill_time = 0
        self.last_voice_time = time.time()
        self.last_session_update = 0
        self.stats_last_refresh_time = 0  # To throttle stats updates
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
        self.id_queue = Queue()  # IMPORTANT: Initialize here for Cache Worker
        self.websocket = None
        self.loop = None

        # --- KD MODE TOGGLE ---
        # True = Revive KD (Deaths - Revives), False = Real KD (Total Deaths)
        self.kd_mode_revive = True

        # Paths
        self.source_high = get_asset_path(os.path.join("Planetside 2 ini", "UserOptions_high.ini"))
        self.source_low = get_asset_path(os.path.join("Planetside 2 ini", "UserOptions_low.ini"))

        # 3. QT APP & WINDOW INITIALIZATION
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setStyle("Fusion")

        # Create sub-windows
        self.dash_window = dashboard_qt.DashboardWidget(self)
        self.dash_controller = dashboard_qt.DashboardController(self.dash_window)

        # --- FIX START: Sync dropdown with config ---
        # Search for name of the loaded ID (e.g. "10" -> "Wainwright (EU)")
        init_server_name = self.get_server_name_by_id(self.current_world_id)

        # Set dropdown to this name without firing the signal (blockSignals)
        if hasattr(self.dash_window, 'server_combo'):
            self.dash_window.server_combo.blockSignals(True)
            idx = self.dash_window.server_combo.findText(init_server_name)
            if idx >= 0:
                self.dash_window.server_combo.setCurrentIndex(idx)
            self.dash_window.server_combo.blockSignals(False)
        # --- FIX END ---

        self.launcher_win = launcher_qt.LauncherWidget(self)
        self.char_win = characters_qt.CharacterWidget(self)
        self.ovl_config_win = overlay_config_qt.OverlayConfigWindow(self)
        self.populate_overlay_assets()
        self.init_event_slots()
        self.settings_win = settings_qt.SettingsWidget(self)

        # Create overlay
        self.overlay_win = QtOverlay(self)

        # 4. MAIN HUB (The Shell)
        self.main_hub = DiorMainHub(self)

        # 5. CONNECT SIGNALS
        self.connect_all_qt_signals()

        self.refresh_char_list_ui()

        # 6. LOAD DATA TO WINDOWS
        # IMPORTANT: This loads the checkboxes AND forces config values
        self.load_settings_to_ui()
        self.settings_win.load_config(self.config, self.ps2_dir)
        
        # Apply background from config
        bg_val = self.config.get("main_background_path", "")
        if bg_val:
            if os.path.isabs(bg_val):
                self.apply_main_background(bg_val)
            else:
                self.apply_main_background(get_asset_path(bg_val))
        

        # Initialize positions
        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()

        # --- CONFIG STATUS MESSAGE ---
        if hasattr(self, '_startup_config_status'):
            status = self._startup_config_status
            if status == "BACKUP":
                self.add_log("WARNING: Main Config was corrupt. Backup loaded!")
                # Show popup warning
                QMessageBox.warning(self.main_hub, "Config Restored",
                                          "Your configuration file was corrupt.\nA backup was successfully loaded.")
            elif status == "RESET":
                self.add_log("ERROR: Config corrupt & no backup. Settings reset.")
                QMessageBox.critical(self.main_hub, "Config Reset",
                                        "Your configuration was unreadable and no backup present.\nSettings were reset.")
            else:
                self.add_log("SYS: Configuration successfully loaded.")

        if getattr(self, "_startup_legacy_config_imported", False):
            self.add_log("SYS: Imported legacy config into user profile directory.")

        if getattr(self, "_startup_config_schema_migrated", False):
            frm = getattr(self, "_startup_config_schema_from", 1)
            to = getattr(self, "_startup_config_schema_to", CONFIG_SCHEMA_VERSION)
            self.add_log(f"SYS: Config schema migrated v{frm} -> v{to}.")

        # 7. SHOW
        self.main_hub.show()
        self.discord_presence = DiscordPresenceManager(log_func=self.add_log)
        if bool(self.config.get("discord_presence_active", False)):
            self.discord_presence.start()
        self.qt_app.aboutToQuit.connect(self.shutdown_runtime_workers)
        atexit.register(self.shutdown_runtime_workers)
        if getattr(sys, "frozen", False):
            QTimer.singleShot(900, self._prompt_update_success_if_available)
            QTimer.singleShot(1200, self._prompt_apply_staged_update_if_available)

        # 8. BACKGROUND THREADS
        threading.Thread(target=self.cache_worker, daemon=True).start()
        print("SYS: Cache Worker Thread started.")

        self.census = CensusWorker(self, self.s_id)
        self.census.start()

        threading.Thread(target=self.ps2_process_monitor, daemon=True).start()

        # Item DB
        csv_path = get_asset_path("sanction-list.csv")
        if os.path.exists(csv_path):
            self.load_item_db(csv_path)

        # Stats Timer
        self.stats_timer = QTimer(self.main_hub)
        self.stats_timer.timeout.connect(self.update_live_graph)
        self.stats_timer.start(1000)

        # Session starting time
        self.session_start_time = time.time()
        self.last_graph_point_time = time.time()

        self._streak_test_timer = None
        self._streak_backup = None
        self._event_test_token = 0
        self.is_event_test = False
        self.is_stats_test = False
        self.is_feed_test = False
        self.is_streak_test = False
        self.is_crosshair_test = False
        self._crosshair_recoil_level = 0.0
        self._crosshair_lmb_hold_started = None
        self._crosshair_rmb_primed = False
        self._crosshair_recoil_supported = bool(IS_WINDOWS and hasattr(ctypes, "windll"))
        self._crosshair_input_timer = None
        if self._crosshair_recoil_supported:
            self._crosshair_input_timer = QTimer(self.main_hub)
            self._crosshair_input_timer.timeout.connect(self.poll_crosshair_recoil_input)
            self._crosshair_input_timer.start(35)


        self.twitch_worker = None
        self.twitch_thread = None
        self.last_twitch_msg_time = time.time() # Start tracking from now

        # 9. CHECK VOICE MACRO PERMISSIONS (LINUX)
        # If Voice Macros are active, trigger 'xdotool' once for the Permission Popup.
        if sys.platform.startswith("linux"):
            v_active = self.config.get("auto_voice", {}).get("active", False)
            if v_active and XDO_TOOL:
                self.add_log("SYS: Auto-Voice active -> Triggering initial permission check...")
                threading.Thread(target=self._linux_permission_check, daemon=True).start()
                # Start keepaline loop
                threading.Thread(target=self._linux_voice_keepalive, daemon=True).start()

    def populate_overlay_assets(self):
        """Populates the overlay config comboboxes with all available assets."""
        if not self.ovl_config_win:
            return

        images = []
        sounds = []

        # 1. SCAN IMAGES SUBFOLDER
        if os.path.exists(IMAGES_DIR):
            try:
                for f in os.listdir(IMAGES_DIR):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        images.append(f)
            except Exception as e:
                self.add_log(f"ERROR: Failed to scan Images subfolder: {e}")

        # 2. SCAN SOUNDS SUBFOLDER
        if os.path.exists(SOUNDS_DIR):
            try:
                for f in os.listdir(SOUNDS_DIR):
                    if f.lower().endswith(('.mp3', '.ogg', '.wav')):
                        sounds.append(f)
            except Exception as e:
                self.add_log(f"ERROR: Failed to scan Sounds subfolder: {e}")

        # 3. SCAN CROSSHAIR SUBFOLDER
        if os.path.exists(CROSSHAIR_DIR):
            try:
                for f in os.listdir(CROSSHAIR_DIR):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        # Add to images if wanted, or just scan
                        if f not in images: images.append(f)
            except Exception as e:
                self.add_log(f"ERROR: Failed to scan Crosshair subfolder: {e}")

        # 4. SCAN ROOT ASSETS FOLDER (Legacy / Other files)
        try:
            for f in os.listdir(ASSETS_DIR):
                lower_f = f.lower()
                # Skip subdirectories
                if os.path.isdir(os.path.join(ASSETS_DIR, f)):
                    continue
                
                if lower_f.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    if f not in images: images.append(f)
                elif lower_f.endswith(('.mp3', '.ogg', '.wav')):
                    if f not in sounds: sounds.append(f)
        except Exception as e:
            self.add_log(f"ERROR: Failed to scan root assets dir: {e}")

        # Fill UI
        self.ovl_config_win.combo_evt_img.clear()
        self.ovl_config_win.combo_evt_img.addItems(sorted(images))
        self.ovl_config_win.combo_evt_snd.clear()
        self.ovl_config_win.combo_evt_snd.addItems(sorted(sounds))

        # Store base assets for later use
        self.base_images = sorted(images)
        self.base_sounds = sorted(sounds)

        # Populate Image Combo
        if hasattr(self.ovl_config_win, 'combo_evt_img'):
            self.ovl_config_win.combo_evt_img.blockSignals(True)
            self.ovl_config_win.combo_evt_img.clear()
            self.ovl_config_win.combo_evt_img.addItems(self.base_images)
            self.ovl_config_win.combo_evt_img.blockSignals(False)

        # Populate Sound Combo
        if hasattr(self.ovl_config_win, 'combo_evt_snd'):
            self.ovl_config_win.combo_evt_snd.blockSignals(True)
            self.ovl_config_win.combo_evt_snd.clear()
            self.ovl_config_win.combo_evt_snd.addItems(self.base_sounds)
            self.ovl_config_win.combo_evt_snd.blockSignals(False)

        # Store base assets for later use
        self.base_images = sorted(images)
        self.base_sounds = sorted(sounds)

    def _linux_permission_check(self):
        """Simulates a few harmless keypresses to ensure the OS requests input permissions."""
        if not XDO_TOOL: return
        try:
            # Shift key press/release (harmless)
            # We do it 3 times with small delays to ensure the OS notices the input attempt
            for _ in range(3):
                subprocess.run([XDO_TOOL, "key", "Shift_L"], check=False)
                time.sleep(0.2)
            self.add_log("SYS: Sent permission trigger (Shift_L). Check for OS popups!")
        except Exception as e:
            print(f"Permission Check Fail: {e}")

    def _linux_voice_keepalive(self):
        """
        Background loop for Linux: If no voice macro was played for 10 minutes,
        simulate a F16 keypress once to 'refresh' the OS permission timeout.
        """
        if not XDO_TOOL: return
        
        while True:
            time.sleep(60)  # Check every minute
            now = time.time()
            # 600 seconds = 10 minutes
            if now - self.last_voice_time > 600:
                try:
                    # F16 is usually harmless and unrecognized by games
                    subprocess.run([XDO_TOOL, "key", "F16"], check=False)
                    self.last_voice_time = now # Reset timer
                    print("DEBUG: Linux Voice Keepalive triggered (F16).")
                except:
                    pass

    def save_global_event_duration(self):
        """Saves the global event duration."""
        try:
            val = int(self.ovl_config_win.ent_global_duration.text())
        except ValueError:
            val = 3000
            self.ovl_config_win.ent_global_duration.setText("3000")

        self.config["event_global_duration"] = val
        self.save_config()
        self.add_log(f"SYS: Global event duration set to {val}ms.")

    def toggle_killfeed_visibility(self):
        """Toggles the killfeed on/off."""
        ui = self.ovl_config_win

        # 1. Get config & toggle
        if "killfeed" not in self.config: self.config["killfeed"] = {}
        current_state = self.config["killfeed"].get("active", True)
        new_state = not current_state

        self.config["killfeed"]["active"] = new_state
        self.save_config()

        # 2. Button Visuals
        if new_state:
            ui.btn_toggle_feed.setText("KILLFEED: ON")
            ui.btn_toggle_feed.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_feed.setText("KILLFEED: OFF")
            ui.btn_toggle_feed.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

            # Clear/Hide immediately when turned off
            if self.overlay_win:
                self.overlay_win.feed_label.hide()
                self.overlay_win.feed_label.clear()

        state_str = "ENABLED" if new_state else "DISABLED"
        self.add_log(f"UI: Killfeed {state_str}")

    def toggle_voice_macros(self, checked):
        """Toggles Voice Macros globally on/off."""
        ui = self.ovl_config_win

        if "auto_voice" not in self.config: self.config["auto_voice"] = {}
        self.config["auto_voice"]["active"] = checked
        self.save_config()

        if checked:
            ui.btn_toggle_voice.setText("VOICE MACROS: ON")
            ui.btn_toggle_voice.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_voice.setText("VOICE MACROS: OFF")
            ui.btn_toggle_voice.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        # Trigger permission check on Linux if turned ON
        if checked and sys.platform.startswith("linux") and XDO_TOOL:
            threading.Thread(target=self._linux_permission_check, daemon=True).start()


    def toggle_stats_visibility(self):
        """Toggles the Stats widget on/off."""
        ui = self.ovl_config_win

        if "stats_widget" not in self.config: self.config["stats_widget"] = {}
        new_state = not self.config["stats_widget"].get("active", True)

        self.config["stats_widget"]["active"] = new_state
        self.save_config()

        # Button Visuals
        if new_state:
            ui.btn_toggle_stats.setText("STATS WIDGET: ON")
            ui.btn_toggle_stats.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_stats.setText("STATS WIDGET: OFF")
            ui.btn_toggle_stats.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        # Immediate Refresh
        self.refresh_ingame_overlay()


    def update_db_count_cache(self):
        """Reads the number of unique players from the DB."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            count = cursor.execute("SELECT COUNT(*) FROM player_cache").fetchone()[0]
            conn.close()
            self.db_player_count = count
        except Exception as e:
            print(f"DB Count Error: {e}")

    def _resolve_overlay_stats_payload(self, force_placeholder=False):
        """
        Returns (stats_obj, is_dummy) for overlay rendering.
        Priority: real stats if available, otherwise shared placeholder.
        """
        if force_placeholder:
            return {}, True

        my_id = str(getattr(self, "current_character_id", "") or "").strip()
        if my_id:
            stats_obj = self.session_stats.get(my_id)
            if isinstance(stats_obj, dict) and len(stats_obj) > 0:
                return stats_obj, False

        return {}, True

    def _ensure_session_stats_entry(self, cid, name=None):
        """Ensure an active character always has a concrete stats object (not debug placeholder)."""
        cid = str(cid or "").strip()
        if not cid:
            return {}

        existing = self.session_stats.get(cid)
        if isinstance(existing, dict) and len(existing) > 0:
            if name and (not existing.get("name") or existing.get("name") == "Searching..."):
                existing["name"] = name
            if "last_seen_base" not in existing:
                existing["last_seen_base"] = ""
            return existing

        resolved_name = name
        if not resolved_name:
            resolved_name = self.name_cache.get(cid, "")
        if not resolved_name:
            for n, saved_id in getattr(self, "char_data", {}).items():
                if str(saved_id) == cid:
                    resolved_name = n
                    break
        if not resolved_name:
            resolved_name = "Searching..."

        now = time.time()
        base_world = str(getattr(self, "current_world_id", "0") or "0")
        obj = {
            "id": cid,
            "name": resolved_name,
            "faction": "NSO",
            "k": 0, "d": 0, "a": 0, "hs": 0, "hsrkill": 0,
            "dhs": 0, "dhs_eligible": 0,
            "revives_received": 0,
            "start": now,
            "acc_t": 0,
            "last_kill_time": now,
            "world_id": base_world,
            "last_seen_base": ""
        }
        self.session_stats[cid] = obj
        return obj

    def update_stats_position_safe(self):
        """Calculates the position of the Stats widget safely and consistently."""
        if not self.overlay_win: return
        
        # Guard: If we are currently dragging, the loop MUST NOT overwrite the position!
        if getattr(self.overlay_win, "dragging_widget", None) == "stats":
            return

        # 1. Load config
        cfg = self.config.get("stats_widget", {})

        # Saved coordinates (Top left corner of the background)
        x_conf = cfg.get("x", 50)
        y_conf = cfg.get("y", 500)

        # Recalculate to current screen scaling
        bg_x = self.overlay_win.s(x_conf)
        bg_y = self.overlay_win.s(y_conf)

        # 2. Move background
        self.overlay_win.safe_move(self.overlay_win.stats_bg_label, bg_x, bg_y)

        # 3. Calculate text position relative to it

        # Force sizes (Important!)
        self.overlay_win.stats_bg_label.adjustSize()
        self.overlay_win.stats_text_label.adjustSize()

        bg_w = self.overlay_win.stats_bg_label.width()
        bg_h = self.overlay_win.stats_bg_label.height()

        # Fallback sizes (if image is still loading or missing)
        # This is important for "empty" Edit Mode
        if bg_w < 10: bg_w = int(450 * self.overlay_win.ui_scale)
        if bg_h < 10: bg_h = int(60 * self.overlay_win.ui_scale)

        txt_w = self.overlay_win.stats_text_label.width()
        txt_h = self.overlay_win.stats_text_label.height()

        # Offsets from Config (Sliders)
        tx_offset = self.overlay_win.s(cfg.get("tx", 0))
        ty_offset = self.overlay_win.s(cfg.get("ty", 0))

        # --- MATHE FIX ---

        # 1. Find center of background (Absolute screen coordinates)
        center_bg_x = bg_x + (bg_w / 2)
        center_bg_y = bg_y + (bg_h / 2)

        # 2. Calculate text start point:
        # Center - half text width + user offset
        final_text_x = center_bg_x - (txt_w / 2) + tx_offset
        final_text_y = center_bg_y - (txt_h / 2) + ty_offset

        self.overlay_win.safe_move(self.overlay_win.stats_text_label, int(final_text_x), int(final_text_y))

        # Ensure text label is always IN FRONT of the background
        self.overlay_win.stats_text_label.raise_()

    def update_main_config_from_settings(self, data):
        """Receives cleaned data from settings_qt."""

        # Save Audio Volume
        if "audio_volume" in data:
            vol = data["audio_volume"]
            self.config["audio_volume"] = vol

            # OPTIONAL: Send live update to overlay (if sound is currently playing)
            # This is usually not necessary as the overlay gets the value anyway.

        # Save Audio Device
        if "audio_device" in data:
            dev = data["audio_device"]
            self.config["audio_device"] = dev
            
            # Update Overlay Audio Device
            if self.overlay_win:
                if hasattr(self.overlay_win, 'set_audio_device'):
                    self.overlay_win.set_audio_device(dev)

        # Save Background Path
        if "main_background_path" in data:
            # We assume it's already in assets or we just keep what the UI has.
            # Usually handled by immediate signals, but for the Save button:
            self.config["main_background_path"] = data["main_background_path"]

        # Save Discord Presence setting
        if "discord_presence_active" in data:
            desired = bool(data["discord_presence_active"])
            previous = bool(self.config.get("discord_presence_active", False))
            self.config["discord_presence_active"] = desired

            if self.discord_presence is None:
                self.discord_presence = DiscordPresenceManager(log_func=self.add_log)

            if desired:
                self.discord_presence.start()
                self.update_discord_presence()
            else:
                self.discord_presence.close()

            if desired != previous:
                self.add_log(f"DISCORD: Rich Presence {'enabled' if desired else 'disabled'}.")

        # Save to disk
        self.save_config()
        self.add_log(
            f"SYS: Global settings saved (Vol: {data.get('audio_volume', 'N/A')}%, Dev: {data.get('audio_device', 'N/A')}, "
            f"BG: {data.get('main_background_path', 'N/A')}, Discord RPC: {'ON' if bool(data.get('discord_presence_active', self.config.get('discord_presence_active', False))) else 'OFF'})"
        )

    def clean_path(self, path_str):
        """Removes 'No file selected' and empty paths."""
        if not path_str or "No file selected" in path_str:
            return ""
        return os.path.basename(path_str)  # Save only filename

    def handle_game_status_change(self, is_running):
        """This slot is guaranteed to run in the Main thread!"""
        # We set the status immediately here in the Main thread,
        # so that all UI functions (like refresh_ingame_overlay) have the same state.
        self.ps2_running = is_running

        if is_running:
            self.on_game_started()
        else:
            self.on_game_stopped()

    # --- HELPER METHOD FOR THE CONTROLLER ---
    def switch_to_tab(self, index):
        """Changes the tab and updates the sidebar visually."""
        self.nav_list.setCurrentRow(index)

    def on_game_started(self):
        """Called when PS2 was started (runs in the Main thread)."""
        self.add_log("MONITOR: PlanetSide 2 detected. Checking settings...")

        master_active = self.config.get("overlay_master_active", True)

        if master_active:
            self.add_log("MONITOR: Master Switch is ON -> Starting Overlay.")

            if self.overlay_win:
                # Show window
                self.overlay_win.showFullScreen()
                self.overlay_win.raise_()

                # Crosshair
                self.update_crosshair_from_qt()

                # Killfeed (clear)
                if hasattr(self.overlay_win, 'feed_label'):
                    self.overlay_win.feed_label.show()
                    self.overlay_win.feed_label.setText("")
                    self.overlay_win.update_killfeed_pos()

                # Streak
                streak_active = self.config.get("streak", {}).get("active", True)
                if streak_active:
                    self.update_streak_display()

                # IMPORTANT: No manual .show() for Stats here!
                # We leave that entirely to the loop.

                # Trigger loop immediately
                self.refresh_ingame_overlay()

    def on_game_stopped(self):
        """Called when PS2 has been terminated."""
        self.add_log("MONITOR: PlanetSide 2 geschlossen.")
        self.clear_discord_presence()

        # Stop logic
        self.stop_overlay_logic()

        if self.overlay_win:
            # Only hide if we are not currently editing
            if not getattr(self, "is_hud_editing", False):
                # 1. Crosshair gone
                self.overlay_win.crosshair_label.hide()

                # 2. Stats gone (NEW)
                self.overlay_win.stats_bg_label.hide()
                self.overlay_win.stats_text_label.hide()

                # 3. Killfeed gone (NEW)
                self.overlay_win.feed_label.hide()
                self.overlay_win.feed_label.clear()

                # 4. Streak gone
                self.overlay_win.streak_bg_label.hide()
                self.overlay_win.streak_text_label.hide()
                for k in self.overlay_win.knife_labels:
                    k.hide()

                active = self.config.get("twitch", {}).get("active", True)
                self.overlay_win.update_twitch_visibility(active)

                # Optional: Hide overlay completely (saves resources)
                # self.overlay_win.hide()

    def is_game_focused(self):
        """Checks if the active window is PlanetSide 2 (robust against variants)."""
        if IS_WINDOWS:
            try:
                # 1. Get handle of current foreground window
                hwnd = ctypes.windll.user32.GetForegroundWindow()

                # 2. Determine title length
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return False

                # 3. Create buffer and read title
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)

                # 4. Normalize title (lowercase everything)
                window_title = buff.value.lower()

                # We search for "planetside", this covers:
                # "PlanetSide 2", "Planetside2", "PlanetSide 2 Test".
                if "planetside2" in window_title:
                    return True

                return False
            except Exception:
                return False
        else:
            # Linux: Use xprop to get the active window title
            try:
                import subprocess
                # Get the active window ID
                result = subprocess.run(
                    ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                
                if result.returncode != 0:
                    return True  # Fallback if xprop fails
                
                # Extract window ID from output like: "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3400003"
                window_id = result.stdout.strip().split()[-1]
                
                # Get the window name/title
                result = subprocess.run(
                    ["xprop", "-id", window_id, "WM_NAME", "_NET_WM_NAME"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                
                if result.returncode != 0:
                    return True  # Fallback if xprop fails
                
                # Check if "planetside" is in the window title (case insensitive)
                window_info = result.stdout.lower()
                return "planetside" in window_info
                
            except Exception:
                # If xprop is not available or fails, assume game is focused
                return True

    def toggle_twitch_always(self, checked):
        ui = self.ovl_config_win
        if "twitch" not in self.config: self.config["twitch"] = {}
        self.config["twitch"]["always_on"] = checked
        self.save_config()

        if checked:
            ui.btn_twitch_always.setText("ALWAYS ON")
            ui.btn_twitch_always.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_twitch_always.setText("PLANETSIDE")
            ui.btn_twitch_always.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        # Immediate update in overlay
        if self.overlay_win:
            active = self.config["twitch"].get("active", True)
            self.overlay_win.update_twitch_visibility(active)

    def toggle_twitch_ignore_special(self, checked):
        ui = self.ovl_config_win
        if "twitch" not in self.config: self.config["twitch"] = {}
        self.config["twitch"]["ignore_special"] = checked
        self.save_config()

        if checked:
            ui.btn_twitch_ignore_special.setText("IGNORE SPECIAL CHARS (!): ON")
            ui.btn_twitch_ignore_special.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_twitch_ignore_special.setText("IGNORE SPECIAL CHARS (!): OFF")
            ui.btn_twitch_ignore_special.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        # Pass to worker immediately
        if hasattr(self, 'twitch_worker') and self.twitch_worker:
            self.twitch_worker.ignore_special = checked

    # --- CROSSHAIR LOGIC (NEW) ---
    def browse_crosshair_qt(self):
        """Select file, copy and set text field."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self.main_hub, "Select Crosshair Image", CROSSHAIR_DIR, "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            filename = os.path.basename(file_path)
            target_path = get_asset_path(filename)

            # Copy to Assets/Crosshair if necessary
            if os.path.abspath(file_path) != os.path.abspath(target_path):
                try:
                    shutil.copy2(file_path, target_path)
                except Exception as e:
                    print(f"Copy Error: {e}")

            # IMPORTANT: Block signals briefly, so update_crosshair_from_qt
            # is not called twice (once by setText, once manually)
            self.ovl_config_win.cross_path.blockSignals(True)
            self.ovl_config_win.cross_path.setText(filename)
            self.ovl_config_win.cross_path.blockSignals(False)

            # Now save properly once
            self.update_crosshair_from_qt()

    def update_crosshair_from_qt(self):
        """Reads UI values, cleans the path and saves."""
        ui = self.ovl_config_win

        # 1. Raw data from UI
        is_active = ui.check_cross.isChecked()
        raw_text = ui.cross_path.text().strip()
        shadow_enabled = ui.btn_toggle_cross_shadow.isChecked()
        expand_enabled = ui.btn_toggle_cross_expand.isChecked() if hasattr(ui, "btn_toggle_cross_expand") else True

        # 2. Cleaning: We only want to save the filename!
        # If the user copied a full path, we cut it off.
        filename = os.path.basename(raw_text)

        # Empty path -> Standard
        if not filename:
            filename = "crosshair.png"

        # 3. Config Update
        if "crosshair" not in self.config:
            self.config["crosshair"] = {}

        self.config["crosshair"]["active"] = is_active
        self.config["crosshair"]["file"] = filename  # Only the name!
        self.config["crosshair"]["shadow"] = shadow_enabled
        self.config["crosshair"]["ads_fire_expand"] = bool(expand_enabled)
        self.update_crosshair_shadow_button(shadow_enabled)
        self.update_crosshair_expand_button(expand_enabled)
        if not expand_enabled:
            self._set_crosshair_recoil_level(0.0)

        # Save
        self.save_config()
        # print(f"DEBUG: Crosshair saved -> Active: {is_active}, File: {filename}")

        # 4. Live Update (Here we need the full path for Qt)
        if self.overlay_win:
            full_path = get_asset_path(filename)

            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, "is_hud_editing", False)
            should_show = (is_active and game_running) or edit_mode

            current_size = self.config["crosshair"].get("size", 32)
            self.overlay_win.update_crosshair(full_path, current_size, should_show)

    def update_crosshair_shadow_button(self, enabled):
        ui = self.ovl_config_win
        if enabled:
            ui.btn_toggle_cross_shadow.setText("CROSSHAIR SHADOW: ON")
            ui.btn_toggle_cross_shadow.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_toggle_cross_shadow.setText("CROSSHAIR SHADOW: OFF")
            ui.btn_toggle_cross_shadow.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ccc; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def update_crosshair_expand_button(self, enabled):
        ui = self.ovl_config_win
        if not hasattr(ui, "btn_toggle_cross_expand"):
            return
        if enabled:
            ui.btn_toggle_cross_expand.setText("ADS+FIRE EXPANSION: ON")
            ui.btn_toggle_cross_expand.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_toggle_cross_expand.setText("ADS+FIRE EXPANSION: OFF")
            ui.btn_toggle_cross_expand.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ccc; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def center_crosshair_qt(self):
        """Re-centers the crosshair on the current screen."""
        # 1. Execute logic
        self.center_crosshair()  # This method already exists in part 3 of your code

        # 2. Feedback
        self.add_log("CROSSHAIR: Reset to screen center.")

    def apply_event_layout_to_all(self):
        """Copies Position & Size of current Event to ALL others."""
        from PyQt6.QtWidgets import QMessageBox

        # Which event is currently open?
        ui = self.ovl_config_win
        source_name = ui.lbl_editing.text().replace("EDITING: ", "").strip()

        if source_name == "NONE" or not source_name:
            return

        # Security prompt
        reply = QMessageBox.question(ui, "Apply Layout?",
                                     f"Should the layout of '{source_name}' (Position & Size) be applied to ALL other events (including sub-events)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Determine values
        # Either from overlay (if Edit Mode is on) or from config
        if self.overlay_win and self.overlay_win.event_preview_label.isVisible():
            pos = self.overlay_win.event_preview_label.pos()
            new_x = int(pos.x() / self.overlay_win.ui_scale)
            new_y = int(pos.y() / self.overlay_win.ui_scale)
        else:
            src_data = self.config.get("events", {}).get(source_name, {})
            new_x = src_data.get("x", 100)
            new_y = src_data.get("y", 200)

        new_scale = ui.slider_evt_scale.value() / 100.0

        # Apply to all - NEW LOGIC: Collect ALL possible events
        count = 0
        if "events" not in self.config: self.config["events"] = {}

        # 1. Collect all names
        all_events = set()
        
        # From Categories (Standard, Multi Kill, etc.)
        if hasattr(ui, "event_categories"):
            for cat_list in ui.event_categories.values():
                all_events.update(cat_list)
        
        # From Expandables (Heal 50, Kill Infil, etc.)
        if hasattr(ui, "EXPANDABLE_EVENTS"):
            for sub_list in ui.EXPANDABLE_EVENTS.values():
                all_events.update(sub_list)

        # 2. Iterate and apply
        for evt_key in all_events:
            if evt_key == source_name: continue
            
            # EXCLUSIONS
            if evt_key.lower() == "hitmarker" or evt_key.lower() == "headshot hitmarker": 
                continue

            # Create entry if missing
            if evt_key not in self.config["events"]:
                self.config["events"][evt_key] = {}

            # Only change layout, keep images/sounds!
            self.config["events"][evt_key]["x"] = new_x
            self.config["events"][evt_key]["y"] = new_y
            self.config["events"][evt_key]["scale"] = new_scale
            count += 1

        self.save_config()

        # Sync to active slot
        import copy
        active_slot = self.config.get("active_event_slot", "")
        if active_slot and "event_slots" in self.config:
            self.config["event_slots"][active_slot] = copy.deepcopy(self.config["events"])

        self.add_log(f"SYS: Layout applied to {count} Events.")
        QMessageBox.information(ui, "Success", f"Layout successfully applied to {count} events!")

    def process_search_results_qt(self, stats, weapons):
        """Called in the main thread when the worker is finished."""
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
        """Saves the Master Switch status."""
        self.config["overlay_master_active"] = checked
        self.save_config()

        state = "ENABLED" if checked else "DISABLED"
        self.add_log(f"SYS: Master Switch {state}")

        # React immediately if game is already running
        if getattr(self, 'ps2_running', False):
            if checked:
                self.on_game_started()
            else:
                self.on_game_stopped()

    def toggle_debug_overlay(self, checked):
        """Force overlay rendering without the game running."""
        ui = self.ovl_config_win
        self.debug_overlay_active = checked

        if checked:
            ui.btn_debug_overlay.setText("DEBUG OVERLAY: ON")
            ui.btn_debug_overlay.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
            if self.overlay_win:
                self.overlay_win.showFullScreen()
                self.overlay_win.raise_()
                # Force first-frame stats render in debug mode.
                # Without this, normal throttle can skip the initial push.
                self.stats_last_refresh_time = 0
                try:
                    stats_obj, is_dummy = self._resolve_overlay_stats_payload()
                    self.overlay_win.update_stats_display(stats_obj, is_dummy=is_dummy)
                    self.update_stats_position_safe()
                except Exception:
                    pass
        else:
            ui.btn_debug_overlay.setText("DEBUG OVERLAY: OFF")
            ui.btn_debug_overlay.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        self.refresh_ingame_overlay()

    def _set_scifi_toggle_visual(self, enabled):
        ui = self.ovl_config_win
        if not hasattr(ui, "btn_toggle_scifi"):
            return
        if enabled:
            ui.btn_toggle_scifi.setText("SCI-FI HUD: ON")
            ui.btn_toggle_scifi.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_toggle_scifi.setText("SCI-FI HUD: OFF")
            ui.btn_toggle_scifi.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def toggle_scifi_overlay(self, checked):
        """Enable or disable the experimental sci-fi HUD style."""
        enabled = bool(checked)
        self.config["scifi_overlay_active"] = enabled
        self.save_config()
        self._set_scifi_toggle_visual(enabled)

        if self.overlay_win and hasattr(self.overlay_win, "set_scifi_mode_enabled"):
            self.overlay_win.set_scifi_mode_enabled(enabled)

        self.add_log(f"SYS: Sci-Fi HUD {'ENABLED' if enabled else 'DISABLED'}")

    def connect_all_qt_signals(self):
        """Central management of all PyQt6 signals (Structured & Clean)."""
        print("SYS: Connecting GUI signals...")

        # Shortcuts
        hub = self.main_hub
        ui = self.ovl_config_win
        dash = self.dash_controller

        # ---------------------------------------------------------
        # 1. NAVIGATION & MAIN WINDOW
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
            
        # --- EVENT AUTO-SAVE SIGNALS ---
        ui.slider_evt_scale.valueChanged.connect(self.save_event_config_from_qt)
        ui.slider_evt_vol.valueChanged.connect(self.save_event_config_from_qt)
        ui.ent_evt_duration.textChanged.connect(self.save_event_config_from_qt)
        ui.combo_evt_img.currentIndexChanged.connect(self.save_event_config_from_qt)
        ui.combo_evt_snd.currentIndexChanged.connect(self.save_event_config_from_qt)
        ui.combo_evt_img.editTextChanged.connect(self.save_event_config_from_qt)
        ui.combo_evt_snd.editTextChanged.connect(self.save_event_config_from_qt)
        ui.check_play_duplicate.toggled.connect(self.save_event_config_from_qt)
        ui.check_evt_impact.toggled.connect(self.save_event_config_from_qt)

        # --- EVENT SLOT SIGNALS ---
        ui.combo_event_slot.currentIndexChanged.connect(self.switch_event_slot)
        ui.btn_slot_new.clicked.connect(self.create_event_slot)
        ui.btn_slot_rename.clicked.connect(self.rename_event_slot)
        ui.btn_slot_delete.clicked.connect(self.delete_event_slot)
        ui.btn_slot_export.clicked.connect(self.export_event_slot)
        ui.btn_slot_import.clicked.connect(self.import_event_slot)


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
        # Debug Overlay
        if hasattr(ui, "btn_debug_overlay"):
            self.safe_connect(ui.btn_debug_overlay.toggled, self.toggle_debug_overlay)
        if hasattr(ui, "btn_toggle_scifi"):
            self.safe_connect(ui.btn_toggle_scifi.toggled, self.toggle_scifi_overlay)

        # ---------------------------------------------------------
        # 3. OVERLAY TAB: EVENTS
        # ---------------------------------------------------------
        # Event Selection in Grid
        ui.signals.setting_changed.connect(self.handle_overlay_setting_changes)
        if hasattr(ui, 'ent_global_duration'):
            ui.ent_global_duration.editingFinished.connect(self.save_global_event_duration)
        
        # New global event settings
        if hasattr(ui, "check_events_active"):
            self.safe_connect(ui.check_events_active.toggled, self.save_global_event_config_qt)
        if hasattr(ui, "check_evt_glow"):
            self.safe_connect(ui.check_evt_glow.toggled, self.save_global_event_config_qt)
        if hasattr(ui, "btn_evt_glow_color"):
            self.safe_connect(ui.btn_evt_glow_color.clicked, lambda: self.pick_glow_color_qt("events"))

        # Live preview on text input
        ui.combo_evt_img.currentTextChanged.connect(lambda text: ui.update_preview_image(get_asset_path(text)))

        # Browse Buttons
        try:
            ui.btn_browse_evt_img.clicked.disconnect()
        except:
            pass
        ui.btn_browse_evt_img.clicked.connect(lambda: self.browse_file_qt(ui.combo_evt_img, "png"))

        try:
            ui.btn_browse_evt_snd.clicked.disconnect()
        except:
            pass
        ui.btn_browse_evt_snd.clicked.connect(lambda: self.browse_file_qt(ui.combo_evt_snd, "audio"))

        # Save Button
        self.safe_connect(ui.btn_save_event.clicked, self.save_event_ui_data)

        # Test / Edit / Special Buttons
        self.safe_connect(ui.btn_test_preview.clicked,
                          lambda: self.test_event_visuals(ui.lbl_editing.text().replace("EDITING: ", "")))
        self.safe_connect(ui.btn_edit_hud.clicked, self.toggle_hud_edit_mode)

        if hasattr(ui, 'btn_apply_all'):
            self.safe_connect(ui.btn_apply_all.clicked, self.apply_event_layout_to_all)
        if hasattr(ui, 'btn_queue_toggle'):
            self.safe_connect(ui.btn_queue_toggle.clicked, lambda: self.toggle_event_queue_qt())

        # NEW: Play Duplicate Checkbox should save
        if hasattr(ui, 'check_play_duplicate'):
             # We use 'clicked' instead of toggled to be safe, or toggled. 
             # Since save_event_config_from_qt reads all data, that's enough.
             self.safe_connect(ui.check_play_duplicate.toggled, self.save_event_config_from_qt)

        # ---------------------------------------------------------
        # 5. OVERLAY TAB: TWITCH
        # ---------------------------------------------------------
        if hasattr(ui, 'btn_browse_twitch_silence_snd'):
             ui.btn_browse_twitch_silence_snd.clicked.connect(lambda: self.browse_file_qt(ui.combo_twitch_silence_snd, "audio"))
        
        if hasattr(ui, 'btn_del_twitch_silence_snd'):
             ui.btn_del_twitch_silence_snd.clicked.disconnect() # Remove the lambda from UI file
             ui.btn_del_twitch_silence_snd.clicked.connect(self.del_twitch_silence_snd)
        
        if hasattr(ui, 'btn_save_twitch'):
            self.safe_connect(ui.btn_save_twitch.clicked, self.save_twitch_config)

        if hasattr(ui, 'btn_test_twitch_silence_snd'):
             ui.btn_test_twitch_silence_snd.clicked.connect(self.test_twitch_silence_snd)

        # ---------------------------------------------------------
        # 6. OVERLAY TAB: KILLSTREAK
        # ---------------------------------------------------------
        # Main Image Browse
        try:
            ui.btn_browse_streak_img.clicked.disconnect()
        except:
            pass
        ui.btn_browse_streak_img.clicked.connect(lambda: self.browse_file_qt(ui.ent_streak_img, "png"))

        # Knife Icons Browse (Dynamic)
        for faction, btn in ui.knife_browse_btns.items():
            target_field = ui.knife_inputs[faction]
            try:
                btn.clicked.disconnect()
            except:
                pass
            btn.clicked.connect(lambda _, tf=target_field: self.browse_file_qt(tf, "png"))

        # Auto-Save for Checkboxes & Sliders
        self.safe_connect(ui.check_streak_master.toggled, self.save_streak_settings_from_qt)
        self.safe_connect(ui.check_streak_anim.toggled, self.save_streak_settings_from_qt)
        if hasattr(ui, "check_streak_glow"):
            self.safe_connect(ui.check_streak_glow.toggled, self.save_streak_settings_from_qt)

        for slider in [ui.slider_tx, ui.slider_ty, ui.slider_scale]:
            self.safe_connect(slider.valueChanged, self.save_streak_settings_from_qt)

        # Design (Color/Size)
        self.safe_connect(ui.btn_pick_color.clicked, self.pick_streak_color_qt)
        if hasattr(ui, "btn_streak_glow_color"):
            self.safe_connect(ui.btn_streak_glow_color.clicked, lambda: self.pick_glow_color_qt("streak"))
        self.safe_connect(ui.slider_font_size.valueChanged, self.save_streak_settings_from_qt)

        # Path Recording
        self.safe_connect(ui.btn_path_record.clicked, self.start_path_record)
        self.safe_connect(ui.btn_path_clear.clicked, self.clear_path)

        # Action Buttons
        self.safe_connect(ui.btn_save_streak.clicked, self.save_streak_settings_from_qt)
        self.safe_connect(ui.btn_edit_streak.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_streak.clicked, self.test_streak_visuals)

        # Knife On/Off
        self.safe_connect(ui.btn_toggle_knives.clicked, self.toggle_knife_visibility)

        # ---------------------------------------------------------
        # 5. OVERLAY TAB: CROSSHAIR
        # ---------------------------------------------------------
        # Checkbox & TextField change -> Save immediately
        self.safe_connect(ui.check_cross.toggled, self.update_crosshair_from_qt)
        self.safe_connect(ui.cross_path.textChanged, self.update_crosshair_from_qt)
        self.safe_connect(ui.btn_toggle_cross_shadow.toggled, self.update_crosshair_from_qt)
        if hasattr(ui, "btn_toggle_cross_expand"):
            self.safe_connect(ui.btn_toggle_cross_expand.toggled, self.update_crosshair_from_qt)

        # Browse
        try:
            ui.btn_browse_cross.clicked.disconnect()
        except:
            pass
        ui.btn_browse_cross.clicked.connect(self.browse_crosshair_qt)

        # Center & Edit
        self.safe_connect(ui.btn_center_cross.clicked, self.center_crosshair_qt)
        self.safe_connect(ui.btn_edit_cross.clicked, self.toggle_hud_edit_mode)
        if hasattr(ui, "btn_test_cross"):
            self.safe_connect(ui.btn_test_cross.clicked, self.test_crosshair_visuals)

        # ---------------------------------------------------------
        # 6. OVERLAY TAB: STATS & FEED
        # ---------------------------------------------------------
        # Sliders
        for slider in [ui.slider_st_tx, ui.slider_st_ty]:
            self.safe_connect(slider.valueChanged, self.save_stats_config_from_qt)

        # Color Buttons for Stats
        if hasattr(ui, 'btn_stats_label_color'):
            self.safe_connect(ui.btn_stats_label_color.clicked, lambda: self.pick_stats_color("labels"))
        if hasattr(ui, 'btn_stats_value_color'):
            self.safe_connect(ui.btn_stats_value_color.clicked, lambda: self.pick_stats_color("values"))
        if hasattr(ui, 'btn_stats_glow_color'):
            self.safe_connect(ui.btn_stats_glow_color.clicked, lambda: self.pick_glow_color_qt("stats"))

        try:
            ui.btn_browse_hs_icon.clicked.disconnect()
        except:
            pass
        ui.btn_browse_hs_icon.clicked.connect(lambda: self.browse_file_qt(ui.ent_hs_icon, "png"))

        # Save & Edit Actions (Stats)
        self.safe_connect(ui.btn_save_stats.clicked, self.save_stats_config_from_qt)
        self.safe_connect(ui.btn_edit_hud_stats.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_stats.clicked, self.test_stats_visuals)
        self.safe_connect(ui.btn_toggle_stats.clicked, self.toggle_stats_visibility)
        
        # LIVE-AUTO-SAVE (Stats)
        self.safe_connect(ui.combo_st_font.currentTextChanged, self.save_stats_config_from_qt)
        if hasattr(ui, "check_stats_glow"):
            self.safe_connect(ui.check_stats_glow.toggled, self.save_stats_config_from_qt)

        # STATS TOGGLES
        if hasattr(ui, "check_show_k"):
             self.safe_connect(ui.check_show_k.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_d.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_hsr.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_kpm.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_kph.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_time.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_dhsr.toggled, self.save_stats_config_from_qt)
             self.safe_connect(ui.check_show_kd.toggled, self.save_stats_config_from_qt)


        # ---------------------------------------------------------
        # 7. OVERLAY TAB: KILLFEED
        # ---------------------------------------------------------
        
        self.safe_connect(ui.btn_toggle_feed.clicked, self.toggle_killfeed_visibility)

        # Actions (Feed)
        self.safe_connect(ui.btn_save_feed.clicked, self.save_feed_config_from_qt)
        self.safe_connect(ui.btn_edit_hud_feed.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_feed.clicked, self.test_killfeed_visuals)

        # Live Save Feed
        self.safe_connect(ui.check_show_revives.toggled, self.save_feed_config_from_qt)
        if hasattr(ui, "check_show_gunner"):
            self.safe_connect(ui.check_show_gunner.toggled, self.save_feed_config_from_qt)
        if hasattr(ui, "check_show_vehicle"):
            self.safe_connect(ui.check_show_vehicle.toggled, self.save_feed_config_from_qt)
        if hasattr(ui, "check_feed_auto_remove"):
            self.safe_connect(ui.check_feed_auto_remove.toggled, self.save_feed_config_from_qt)
        if hasattr(ui, "spin_feed_stay_sec"):
            self.safe_connect(ui.spin_feed_stay_sec.valueChanged, self.save_feed_config_from_qt)

        self.safe_connect(ui.ent_hs_icon.textChanged, self.save_feed_config_from_qt)
        self.safe_connect(ui.combo_feed_font.currentTextChanged, self.save_feed_config_from_qt)
        self.safe_connect(ui.combo_hs_scale.currentTextChanged, self.save_feed_config_from_qt)

        # Browse Button Feed
        try:
            ui.btn_browse_hs_icon.clicked.disconnect()
        except:
            pass
        ui.btn_browse_hs_icon.clicked.connect(lambda: self.browse_file_qt(ui.ent_hs_icon, "png"))

        # ---------------------------------------------------------
        # 7. OVERLAY TAB: VOICE MACROS
        # ---------------------------------------------------------
        self.safe_connect(ui.btn_toggle_voice.toggled, self.toggle_voice_macros)
        self.safe_connect(ui.btn_save_voice.clicked, self.save_voice_config_from_qt)
        if hasattr(ui, 'btn_request_voice_permission'):
            self.safe_connect(ui.btn_request_voice_permission.clicked, lambda: threading.Thread(target=self._linux_permission_check, daemon=True).start())
        for combo in ui.voice_combos.values():
            self.safe_connect(combo.currentIndexChanged, self.save_voice_config_from_qt)

        # ---------------------------------------------------------
        # 8. SUB-WINDOWS (CHARACTERS, LAUNCHER, SETTINGS)
        # ---------------------------------------------------------
        # Character Search
        self.safe_connect(self.char_win.signals.search_requested, self.run_search)
        self.safe_connect(self.char_win.signals.search_finished, self.process_search_results_qt)

        # Launcher
        self.safe_connect(self.launcher_win.signals.launch_requested, self.execute_launch)

        # Settings (CHANGES WERE HERE)
        self.safe_connect(self.settings_win.signals.browse_ps2_requested, self.browse_ps2_folder)
        self.safe_connect(self.settings_win.signals.browse_bg_requested, self.change_background_file)
        self.safe_connect(self.settings_win.signals.clear_bg_requested, self.clear_background_file)
        if hasattr(self.settings_win.signals, "check_updates_requested"):
            self.safe_connect(self.settings_win.signals.check_updates_requested, self.check_for_updates_qt)

        # IMPORTANT: Connect the save signal!
        self.safe_connect(self.settings_win.signals.save_requested, self.update_main_config_from_settings)

        # ---------------------------------------------------------
        # 9. Twitch chat
        # ---------------------------------------------------------
        # Button Toggle (ON/OFF)
        self.safe_connect(ui.btn_toggle_twitch.toggled, self.toggle_twitch_active)

        # Button Connect
        self.safe_connect(ui.btn_connect_twitch.clicked, self.start_twitch_connection)

        # Sliders (Live Update Position)
        for s in [ui.slider_twitch_x, ui.slider_twitch_y, ui.slider_twitch_w, ui.slider_twitch_h,
                  ui.slider_twitch_opacity]:
            self.safe_connect(s.valueChanged, self.update_twitch_visuals)
        self.safe_connect(ui.combo_twitch_font.currentTextChanged, self.update_twitch_visuals)

        # TEST MSG Button
        self.safe_connect(ui.btn_test_twitch.clicked, self.trigger_twitch_test)
        # Always on
        self.safe_connect(ui.btn_twitch_always.toggled, self.toggle_twitch_always)

        # Ignore special (!)
        self.safe_connect(ui.btn_twitch_ignore_special.toggled, self.toggle_twitch_ignore_special)

        # MOVE UI Button
        # We make this a toggle: One click = make visible, another = normal
        self.safe_connect(ui.btn_edit_twitch.clicked, self.toggle_hud_edit_mode)
        if self.overlay_win:
            self.overlay_win.signals.item_moved.connect(self.on_overlay_item_moved)
        self.ovl_config_win.spin_twitch_hold.valueChanged.connect(self.overlay_win.set_chat_hold_time)

        # Save
        self.safe_connect(ui.btn_save_twitch.clicked, self.save_twitch_config)

        print("SYS: All signals routed successfully.")

    def handle_overlay_setting_changes(self, key, val):
        """Dispatches dynamic setting changes from the Overlay Config Window."""
        if key == "event_selection":
            self.on_event_clicked(val)
        
        elif key == "obs_service_toggle":
            try:
                obs_cfg = self.config.get("obs_service", {})
                obs_cfg["enabled"] = bool(val)
                self.config["obs_service"] = obs_cfg
                self.save_config()

                if not self.overlay_win:
                    self.add_log("WARN: Overlay window is not active; OBS service toggle deferred.")
                    return

                if bool(val):
                    # Ensure server is running (used by both OBS and internal web HUD).
                    self.overlay_win.start_server()
                    self.add_log("SYS: OBS Service enabled.")
                else:
                    # Do NOT stop here: internal HUD rendering depends on the same local service.
                    # We only mark OBS integration as disabled in config.
                    self.add_log("SYS: OBS Service disabled (internal HUD service stays running).")
            except Exception as e:
                self.add_log(f"ERR: OBS Service toggle failed: {e}")
            
        elif key == "obs_service_ports":
            try:
                obs_cfg = self.config.get("obs_service", {})
                
                # NO-OP: Avoid restarting if values haven't changed
                if obs_cfg.get("port") == val.get("port") and obs_cfg.get("ws_port") == val.get("ws_port"):
                    return

                obs_cfg.update(val)
                self.config["obs_service"] = obs_cfg
                self.save_config()

                # Always restart if overlay is active, as internal HUD depends on it
                if self.overlay_win:
                    self.add_log(f"SYS: Applying new ports: Http:{val['port']} WS:{val['ws_port']}...")
                    self.overlay_win.start_server()
                else:
                    self.add_log(f"SYS: OBS Ports saved (Http:{val['port']} WS:{val['ws_port']}).")
            except Exception as e:
                self.add_log(f"ERR: OBS port update failed: {e}")

    def on_overlay_item_moved(self, item_name, x, y):
        """Called when an item in the overlay was moved with the mouse."""
        if item_name == "twitch":
            # Update slider without updating the overlay again (prevent loop)
            ui = self.ovl_config_win
            ui.slider_twitch_x.blockSignals(True)
            ui.slider_twitch_y.blockSignals(True)

            # Back-calculation of scaling (if you used s())
            # Since we move absolute pixels in the overlay, we set raw values here.
            # Caution: If your overlay is scaled, you must divide by the factor here!
            # Let's assume 1:1 mapping for now:
            ui.slider_twitch_x.setValue(x)
            ui.slider_twitch_y.setValue(y)

            ui.slider_twitch_x.blockSignals(False)
            ui.slider_twitch_y.blockSignals(False)
        elif item_name == "stats":
            ui = self.ovl_config_win
            if hasattr(ui, "slider_st_x") and hasattr(ui, "slider_st_y"):
                ui.slider_st_x.blockSignals(True)
                ui.slider_st_y.blockSignals(True)
                ui.slider_st_x.setValue(int(x))
                ui.slider_st_y.setValue(int(y))
                ui.slider_st_x.blockSignals(False)
                ui.slider_st_y.blockSignals(False)

    def trigger_twitch_test(self):
        """Triggers a standard test message to check layout and position."""
        if not self.overlay_win:
            self.add_log("ERR: Overlay not active.")
            return

        # We directly use the overlay's add_twitch_message method.
        # This ensures that timer, visibility, and styling are identical.
        test_user = "SystemTest"
        test_msg = "This is a test message to adjust the chat position, size, and font settings."

        # Calling the existing method in the overlay
        self.overlay_win.add_twitch_message(test_user, test_msg, color="#ffaa00", is_test=True)

        self.add_log("TWITCH: Standard test message sent to overlay.")



    def toggle_twitch_active(self, active):
        ui = self.ovl_config_win
        if active:
            ui.btn_toggle_twitch.setText("TWITCH CHAT: ON")
            ui.btn_toggle_twitch.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
            if self.overlay_win: self.overlay_win.chat_container.show()
        else:
            ui.btn_toggle_twitch.setText("TWITCH CHAT: OFF")
            ui.btn_toggle_twitch.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )
            if self.overlay_win: self.overlay_win.chat_container.hide()

        # Optional: Save Config
        if "twitch" not in self.config: self.config["twitch"] = {}
        self.config["twitch"]["active"] = active
        self.save_config()

    def start_twitch_connection(self):
        ui = self.ovl_config_win
        channel = ui.ent_twitch_channel.text().strip()

        # --- PREPARE IGNORE LIST ---
        # We read the field and make a clean list out of it
        raw_ignore = ui.ent_twitch_ignore.text().strip().lower()
        ignore_list = [n.strip() for n in raw_ignore.split(",") if n.strip()]

        if not channel:
            self.add_log("TWITCH: No channel specified.")
            return

        # 1. Gracefully stop old worker
        if hasattr(self, 'twitch_worker') and self.twitch_worker:
            self.twitch_worker.stop()

        self.add_log(f"TWITCH: Connecting to {channel}...")
        ui.btn_connect_twitch.setEnabled(False)

        # 2. Create the NEW worker
        # IMPORTANT: The ignore_list is passed as an argument here!
        self.twitch_worker = TwitchWorker(channel, ignore_list=ignore_list, ignore_special=ui.btn_twitch_ignore_special.isChecked())

        # 3. Connect signals (In Main thread!)
        # We use the on_new_twitch_msg method we corrected earlier
        self.twitch_worker.new_message.connect(
            self.on_new_twitch_msg,
            Qt.ConnectionType.QueuedConnection
        )

        # Status updates (on_twitch_status takes care of logs and button reset)
        self.twitch_worker.status_changed.connect(
            self.on_twitch_status,
            Qt.ConnectionType.QueuedConnection
        )

        # 4. Start the Python thread
        self.twitch_thread = threading.Thread(
            target=self.twitch_worker.run,
            daemon=True
        )
        self.twitch_thread.start()

    def on_new_twitch_msg(self, display_name, html_content, color_code):
        now = time.time()
        
        # 1. Check for Silence Break (Wake-up call)
        t_conf = self.config.get("twitch", {})
        if t_conf.get("active", False) and t_conf.get("silence_active", False):
            timeout_sec = t_conf.get("silence_timeout", 600)
            diff = now - self.last_twitch_msg_time
            
            if diff > timeout_sec:
                snd_list = t_conf.get("silence_snd", [])
                if snd_list:
                    snd_name = random.choice(snd_list) if isinstance(snd_list, list) else snd_list
                    try:
                        if globals().get("HAS_SOUND", True):
                            path = get_asset_path(snd_name)
                            if os.path.exists(path):
                                silence_vol = t_conf.get("silence_vol", 100) / 100.0
                                master_vol = self.config.get("audio_volume", 50) / 100.0
                                s = pygame.mixer.Sound(path)
                                s.set_volume(silence_vol * master_vol)
                                s.play()
                                self.add_log(f"TWITCH: Wake-up call! (Silence was {int(diff)}s)")
                    except Exception as e:
                        print(f"Twitch Silence Play Error: {e}")

        # 2. Update time and show message
        self.last_twitch_msg_time = now
        if self.overlay_win:
            self.overlay_win.add_twitch_message(display_name, html_content, color_code)

    def on_twitch_status(self, status):
        self.add_log(f"TWITCH: {status}")
        if "CONNECTED" in status or "ERROR" in status or "DISCONNECTED" in status:
            self.ovl_config_win.btn_connect_twitch.setEnabled(True)

    def update_twitch_visuals(self):
        """Sends the slider values to the overlay"""
        if not self.overlay_win: return
        ui = self.ovl_config_win

        x = ui.slider_twitch_x.value()
        y = ui.slider_twitch_y.value()
        w = ui.slider_twitch_w.value()
        h = ui.slider_twitch_h.value()
        op = ui.slider_twitch_opacity.value()
        fs = int(ui.combo_twitch_font.currentText())

        # Note scaling!
        x_scaled = self.overlay_win.s(x)
        y_scaled = self.overlay_win.s(y)
        w_scaled = self.overlay_win.s(w)
        h_scaled = self.overlay_win.s(h)

        self.overlay_win.update_twitch_style(x_scaled, y_scaled, w_scaled, h_scaled, op, fs)

    def save_twitch_config(self):
        ui = self.ovl_config_win

        # Collect data from UI
        data = {
            "active": ui.btn_toggle_twitch.isChecked(),
            "channel": ui.ent_twitch_channel.text().strip(),
            "ignore_list": ui.ent_twitch_ignore.text().strip(),
            "ignore_special": ui.btn_twitch_ignore_special.isChecked(), # NEW
            "always_on": ui.btn_twitch_always.isChecked(),
            "x": ui.slider_twitch_x.value(),
            "y": ui.slider_twitch_y.value(),
            "w": ui.slider_twitch_w.value(),
            "h": ui.slider_twitch_h.value(),
            "opacity": ui.slider_twitch_opacity.value(),
            "font_size": int(ui.combo_twitch_font.currentText()),
            "hold_time": ui.spin_twitch_hold.value(),
            "silence_active": ui.check_twitch_silence_active.isChecked(),
            "silence_timeout": ui.spin_twitch_silence_seconds.value(),
            "silence_snd": [ui.combo_twitch_silence_snd.itemText(i) for i in range(ui.combo_twitch_silence_snd.count())],
            "silence_snd_active": ui.combo_twitch_silence_snd.currentText(),
            "silence_vol": ui.slider_twitch_silence_vol.value()
        }

        # Save in global config
        self.config["twitch"] = data
        self.save_config()

        # --- IMMEDIATE UPDATE ---
        # 1. Set Hold Time in overlay
        if hasattr(self.overlay_win, 'set_chat_hold_time'):
            self.overlay_win.set_chat_hold_time(data["hold_time"])
            
        # 2. If a worker is running, update it immediately
        if hasattr(self, 'twitch_worker') and self.twitch_worker:
            self.twitch_worker.ignore_special = data["ignore_special"]

        # 3. Update visual representation (Position, Opacity, Font)
        # This triggers the new update_twitch_style method in the overlay
        self.update_twitch_visuals()
        
        self.add_log("TWITCH: Settings saved.")

    def del_twitch_silence_snd(self):
        """Removes the currently selected sound from the Twitch silence list."""
        ui = self.ovl_config_win
        idx = ui.combo_twitch_silence_snd.currentIndex()
        if idx >= 0:
            ui.combo_twitch_silence_snd.removeItem(idx)
            self.save_twitch_config()
            self.add_log("TWITCH: Sound removed from silence list.")

    def test_twitch_silence_snd(self):
        """Plays the currently selected sound in the Twitch tab."""
        ui = self.ovl_config_win
        snd_name = ui.combo_twitch_silence_snd.currentText()
        if not snd_name: return
        
        try:
            if globals().get("HAS_SOUND", True):
                path = get_asset_path(snd_name)
                if os.path.exists(path):
                    silence_vol = ui.slider_twitch_silence_vol.value() / 100.0
                    master_vol = self.config.get("audio_volume", 50) / 100.0
                    s = pygame.mixer.Sound(path)
                    s.set_volume(silence_vol * master_vol)
                    s.play()
                    self.add_log(f"TEST: Playing '{snd_name}' (Twitch Silence)")
        except Exception as e:
            self.add_log(f"ERR: Test Sound Play failed: {e}")


    def browse_ps2_folder(self):
        """Selects the PS2 folder and saves it immediately permanently."""
        path = QFileDialog.getExistingDirectory(self.main_hub, "Select PlanetSide 2 Installation Folder")
        if path:
            self.ps2_dir = path

            # IMPORTANT: Write into the Config dictionary!
            self.config["ps2_path"] = path

            # Update in Settings window (visual feedback)
            if hasattr(self, 'settings_win'):
                self.settings_win.lbl_ps2_path.setText(path)

            self.save_config()  # Call correct save function
            self.add_log(f"SYS: PS2 Path set and saved to {path}")

    def add_char_qt(self):
        """Starts the thread."""
        ui = self.ovl_config_win
        name = ui.char_input.text().strip()

        if not name:
            self.add_log("INFO: Please enter a name.")
            return

        self.add_log(f"SYS: Searching '{name}' in API...")

        # Lock UI
        ui.btn_add_char.setEnabled(False)
        ui.btn_add_char.setText("...")
        ui.char_input.setEnabled(False)

        # Start thread
        threading.Thread(target=self._add_char_worker, args=(name,), daemon=True).start()

    def _add_char_worker(self, name):
        """Background thread: Searches for character and saves it via DB-Handler."""
        success = False
        real_name = ""
        error_msg = ""

        try:
            url = f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/character/?name.first_lower={name.lower()}"
            response = requests.get(url, timeout=10)
            r = response.json()

            if r.get('returned', 0) > 0:
                c_list = r['character_list'][0]
                cid = c_list['character_id']
                real_name = c_list['name']['first']
                world_id = c_list.get('world_id', '0')

                # --- DB OPERATION (NEW & CLEAN) ---
                # We use the method from dior_db.py
                self.db.save_char_to_db(cid, real_name, world_id)

                # Dictionary Update (RAM)
                self.char_data[real_name] = cid
                success = True
            else:
                error_msg = f"Character '{name}' not found."

        except Exception as e:
            error_msg = f"API Error: {e}"

        # Send signal
        self.worker_signals.add_char_finished.emit(success, real_name, error_msg)

    def finalize_add_char_slot(self, success, real_name, error_msg):
        """
        This slot is AUTOMATICALLY executed in the Main thread
        when the signal is received.
        """
        ui = self.ovl_config_win

        # Unlock UI
        ui.btn_add_char.setEnabled(True)
        ui.btn_add_char.setText("ADD")
        ui.char_input.setEnabled(True)
        ui.char_input.setFocus()

        if success:
            self.add_log(f"SYS: '{real_name}' added.")
            ui.char_input.clear()

            # Now update must work
            self.refresh_char_list_ui(select_name=real_name)
        else:
            self.add_log(f"ERR: {error_msg}")
            ui.char_input.selectAll()

    def delete_char_qt(self):
        """Deletes the currently selected character."""
        ui = self.ovl_config_win
        name = ui.char_combo.currentText()

        if name in self.char_data:
            try:
                # --- DB OPERATION (NEW) ---
                self.db.remove_my_char(name)

                del self.char_data[name]
                self.add_log(f"SYS: {name} deleted.")

                # GUI Update
                self.refresh_char_list_ui()

            except Exception as e:
                self.add_log(f"ERR: Delete failed: {e}")

    def update_active_char(self, name):
        """Sets the internal ID based on the name."""
        if not name: return

        # Get ID from dictionary
        cid = self.char_data.get(name, "")
        
        # RESET logic if character actually changed
        if cid and self.last_tracked_id and cid != self.last_tracked_id:
            self.reset_streak_state()
            
        self.current_character_id = cid
        self.last_tracked_id = cid
        self.current_selected_char_name = name
        if cid:
            # Force immediate repaint so active-session data (if present) is shown right away.
            self.stats_last_refresh_time = 0
            self.update_session_time()
            self.refresh_ingame_overlay()
            self.update_discord_presence()

        self.add_log(f"SYS: Tracking active for: {name}")

        # --- OPTIONAL: Server-Switch logic (if present) ---
        try:
            conn = sqlite3.connect(DB_PATH)
            res = conn.execute("SELECT world_id FROM player_cache WHERE character_id=?", (cid,)).fetchone()
            conn.close()

            if res and res[0]:
                new_world_id = str(res[0])
                # Only switch if different
                if new_world_id != str(self.current_world_id):
                    s_name = self.get_server_name_by_id(new_world_id)
                    # Safe call (Server Logic)
                    self.switch_server(s_name, new_world_id)
        except Exception as e:
            print(f"Server Auto-Switch Error: {e}")

    def refresh_char_list_ui(self, select_name=None):
        """Updates the dropdown and sets the active character."""
        if not hasattr(self, 'ovl_config_win'): return
        ui = self.ovl_config_win

        # 1. Block signals
        ui.char_combo.blockSignals(True)
        ui.char_combo.clear()

        # 2. Rebuild list
        names = sorted(list(self.char_data.keys()))

        if not names:
            ui.char_combo.addItem("No Characters")
            # --- FIX: Stop Tracking ---
            self.current_character_id = ""
            self.current_selected_char_name = ""
            self.clear_discord_presence()
            self.add_log("SYS: No characters remaining. Tracking stopped.")
        else:
            ui.char_combo.addItems(names)
            
            # Selection Logic
            target = names[0] # Default fallback
            
            if select_name and select_name in names:
                target = select_name
            else:
                # Try to keep current
                current = getattr(self, "current_selected_char_name", "")
                if current in names:
                    target = current
            
            ui.char_combo.setCurrentText(target)
            self.update_active_char(target)

        # 4. Release signals again
        ui.char_combo.blockSignals(False)

    def pick_streak_color_qt(self):
        """Opens a Qt color picker for the killstreak number."""
        # Get current color from config (as start value)
        current_hex = self.config.get("streak", {}).get("color", "#ffffff")
        initial = QColor(current_hex)

        # Open dialog
        color = QColorDialog.getColor(initial, self.main_hub, "Select HUD Color")

        if color.isValid():
            hex_color = color.name()  # Returns e.g. "#ff0000"

            # 1. Write to config
            if "streak" not in self.config: self.config["streak"] = {}
            self.config["streak"]["color"] = hex_color

            # 2. Update button color in UI (visual feedback)
            # We set the background of the button to the chosen color
            # and the text color to black or white depending on lightness
            self._update_color_button_style(self.ovl_config_win.btn_pick_color, hex_color)

            # 3. Save and update overlay
            self.save_streak_settings_from_qt()

    def pick_stats_color(self, type_):
        """Opens a color picker for stats (Label or Value)."""
        st_conf = self.config.get("stats_widget", {})
        conf_key = "label_color" if type_ == "labels" else "value_color"
        default_hex = "#00f2ff" if type_ == "labels" else "#ffffff"
        
        current_hex = st_conf.get(conf_key, default_hex)
        initial = QColor(current_hex)
        
        color = QColorDialog.getColor(initial, self.main_hub, f"Select {type_.capitalize()} Color")
        
        if color.isValid():
            hex_color = color.name()
            
            if "stats_widget" not in self.config: self.config["stats_widget"] = {}
            self.config["stats_widget"][conf_key] = hex_color
            
            # Style button
            btn = self.ovl_config_win.btn_stats_label_color if type_ == "labels" else self.ovl_config_win.btn_stats_value_color
            self._update_color_button_style(btn, hex_color)
            
            # Save & Update
            self.save_stats_config_from_qt()

    def pick_glow_color_qt(self, section):
        """Generic glow color picker for different sections."""
        ui = self.ovl_config_win
        
        # Determine config key and button
        if section == "events":
            conf_obj = self.config.get("events_global", {})
            conf_key = "glow_color"
            btn = ui.btn_evt_glow_color
            save_fn = self.save_global_event_config_qt
            default_hex = "#00f2ff"
        elif section == "streak":
            conf_obj = self.config.get("streak", {})
            conf_key = "glow_color"
            btn = ui.btn_streak_glow_color
            save_fn = self.save_streak_settings_from_qt
            default_hex = "#00f2ff"
        elif section == "stats":
            conf_obj = self.config.get("stats_widget", {})
            conf_key = "glow_color"
            btn = ui.btn_stats_glow_color
            save_fn = self.save_stats_config_from_qt
            default_hex = "#00f2ff"
        else: return

        current_hex = conf_obj.get(conf_key, default_hex)
        initial = QColor(current_hex)
        
        color = QColorDialog.getColor(initial, self.main_hub, f"Select {section.capitalize()} Glow Color")
        
        if color.isValid():
            hex_color = color.name()
            
            # Save to correct config section
            if section == "events":
                if "events_global" not in self.config: self.config["events_global"] = {}
                self.config["events_global"][conf_key] = hex_color
            elif section == "streak":
                if "streak" not in self.config: self.config["streak"] = {}
                self.config["streak"][conf_key] = hex_color
            elif section == "stats":
                if "stats_widget" not in self.config: self.config["stats_widget"] = {}
                self.config["stats_widget"][conf_key] = hex_color
                
            self._update_color_button_style(btn, hex_color)
            save_fn()

    def _update_color_button_style(self, btn, hex_color):
        """Helper method for styling the color buttons."""
        color = QColor(hex_color)
        text_col = "black" if color.lightness() > 128 else "white"
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {hex_color}; color: {text_col}; font-weight: bold; border: 1px solid #555; padding: 3px; border-radius: 3px; outline: none; }} "
            "QPushButton:focus { border: 1px solid #555; }"
            "QPushButton:hover { border: 1px solid #00f2ff; }"
        )

    def safe_connect(self, signal, slot):
        """Disconnects a signal safely before setting it again."""
        try:
            signal.disconnect(slot)
        except TypeError:
            pass  # Was not connected yet, all good
        signal.connect(slot)

    def on_event_clicked(self, event_name):
        """Called when an event is clicked in the grid."""
        ui = self.ovl_config_win
        # Get data from config (section 'events')
        ev_conf = self.config.get("events", {})
        # Use copy() to prevent mutations during loading
        data = ev_conf.get(event_name, {}).copy()

        # 1. Update label
        ui.lbl_editing.setText(f"EDITING: {event_name}")
        ui.current_event = event_name

        # BLOCK ALL SIGNALS during loading to avoid recursive auto-saves
        ui.combo_evt_img.blockSignals(True)
        ui.combo_evt_snd.blockSignals(True)
        ui.slider_evt_scale.blockSignals(True)
        ui.slider_evt_vol.blockSignals(True)
        ui.ent_evt_duration.blockSignals(True)
        ui.check_play_duplicate.blockSignals(True)
        ui.check_evt_impact.blockSignals(True)

        try:
            # 2. Fill fields (with fallback values if empty)
            
            # IMAGE
            img_val = data.get("img", "")
            ui.combo_evt_img.clear()
            
            # Only add specific items from config
            def is_valid_asset(name):
                return name and isinstance(name, str) and "No file selected" not in name

            if isinstance(img_val, list):
                for x in img_val:
                    if is_valid_asset(str(x)):
                        ui.combo_evt_img.addItem(str(x))
                if ui.combo_evt_img.count() > 0:
                    ui.combo_evt_img.setCurrentIndex(0)
            elif is_valid_asset(str(img_val)):
                ui.combo_evt_img.addItem(str(img_val))
                ui.combo_evt_img.setCurrentIndex(0)
            
            # Manual update of image preview
            current_img_text = ui.combo_evt_img.currentText()
            if hasattr(ui, 'update_preview_image'):
                 ui.update_preview_image(get_asset_path(current_img_text))

            # SOUND
            snd_val = data.get("snd", data.get("sound", ""))
            ui.combo_evt_snd.clear()
            
            # Only add specific items from config
            if isinstance(snd_val, list):
                for x in snd_val:
                    if is_valid_asset(str(x)):
                        ui.combo_evt_snd.addItem(str(x))
                if ui.combo_evt_snd.count() > 0:
                    ui.combo_evt_snd.setCurrentIndex(0)
            elif is_valid_asset(str(snd_val)):
                ui.combo_evt_snd.addItem(str(snd_val))
                ui.combo_evt_snd.setCurrentIndex(0)

            # Scale Slider (Config value * 100 for slider range)
            v_scale = data.get("scale", 1.0)
            if v_scale > 5.0: v_scale = 1.0 # Safety for old or invalid values
            scale_val = int(v_scale * 100)
            ui.slider_evt_scale.setValue(scale_val)
            if hasattr(ui, 'lbl_scale_val'):
                ui.lbl_scale_val.setText(f"{v_scale:.2f}")

            # Volume Slider
            v_vol = data.get("volume", 1.0)
            if v_vol > 1.0: v_vol /= 100.0 # Handle old 0-100 format
            vol_val = int(v_vol * 100)
            ui.slider_evt_vol.setValue(vol_val)
            if hasattr(ui, 'lbl_vol_val'):
                ui.lbl_vol_val.setText(f"{vol_val}%")


            # Duration
            ui.ent_evt_duration.setText(str(data.get("duration", 3000)))

            # Play Duplicate
            ui.check_play_duplicate.setChecked(data.get("play_duplicate", True))
            ui.check_evt_impact.setChecked(bool(data.get("impact", False)))

        finally:
            # UNBLOCK ALL SIGNALS
            ui.combo_evt_img.blockSignals(False)
            ui.combo_evt_snd.blockSignals(False)
            ui.slider_evt_scale.blockSignals(False)
            ui.slider_evt_vol.blockSignals(False)
            ui.ent_evt_duration.blockSignals(False)
            ui.check_play_duplicate.blockSignals(False)
            ui.check_evt_impact.blockSignals(False)

        self.add_log(f"UI: Settings for '{event_name}' loaded.")


    def save_event_config_from_qt(self):
        """Saves currently edited event data to config."""
        ui = self.ovl_config_win
        event_name = getattr(ui, "current_event", None)
        if not event_name:
            return

        # Read data from UI (NEW COMBOBOX LOGIC)
        def clean_txt(t):
            t = t.strip()
            if not t or "No file selected" in t: return ""
            return t

        # 1. Image Data
        img_items = []
        for i in range(ui.combo_evt_img.count()):
            txt = clean_txt(ui.combo_evt_img.itemText(i))
            if txt and txt not in img_items:
                img_items.append(txt)
        
        # Also check current text (it might not be in the list yet if typed)
        curr_img = clean_txt(ui.combo_evt_img.currentText())
        if curr_img and curr_img not in img_items:
            img_items.append(curr_img)

        if not img_items: img_val = ""
        elif len(img_items) == 1: img_val = img_items[0]
        else: img_val = img_items

        # 2. Sound Data
        snd_items = []
        for i in range(ui.combo_evt_snd.count()):
            txt = clean_txt(ui.combo_evt_snd.itemText(i))
            if txt and txt not in snd_items:
                snd_items.append(txt)

        curr_snd = clean_txt(ui.combo_evt_snd.currentText())
        if curr_snd and curr_snd not in snd_items:
            snd_items.append(curr_snd)

        if not snd_items: snd_val = ""
        elif len(snd_items) == 1: snd_val = snd_items[0]
        else: snd_val = snd_items
        
        scale_val = ui.slider_evt_scale.value() / 100.0
        vol_val = ui.slider_evt_vol.value() / 100.0 # Standardize to 0.0-1.0
        dur_val = int(ui.ent_evt_duration.text()) if ui.ent_evt_duration.text() else 0
        play_dup = ui.check_play_duplicate.isChecked()
        impact_enabled = ui.check_evt_impact.isChecked()

        # Update Config
        if "events" not in self.config: self.config["events"] = {}
        if event_name not in self.config["events"]: self.config["events"][event_name] = {}

        self.config["events"][event_name].update({
            "img": img_val,
            "snd": snd_val,
            "scale": scale_val,
            "volume": vol_val,
            "duration": dur_val,
            "play_duplicate": play_dup,
            "impact": impact_enabled
        })

        self.save_config()

        # Sync to active slot
        import copy
        active_slot = self.config.get("active_event_slot", "")
        if active_slot and "event_slots" in self.config:
            self.config["event_slots"][active_slot] = copy.deepcopy(self.config["events"])

        self.add_log(f"EVENT: Settings for '{event_name}' auto-saved.")

    def save_global_event_config_qt(self):
        """Saves global event settings like active toggle and glow."""
        ui = self.ovl_config_win
        if "events_global" not in self.config: self.config["events_global"] = {}
        
        self.config["events_global"].update({
            "active": ui.check_events_active.isChecked(),
            "glow": ui.check_evt_glow.isChecked(),
            "glow_color": self.config.get("events_global", {}).get("glow_color", "#00f2ff")
        })
        self.save_config()
        self.add_log("SYS: Global event configuration saved.")

        # Optional: Direct Feedback in Overlay (Test)
        # self.trigger_overlay_event(event_name)

    # =========================================================
    # EVENT SAVE SLOT SYSTEM
    # =========================================================
    @staticmethod
    def _migrate_heal_event_names_in_event_map(event_map):
        rename_map = {
            "Heal 2": "Heal 50",
            "Heal 10000": "Heal 5000",
        }
        if not isinstance(event_map, dict):
            return False

        changed_local = False
        for old_name, new_name in rename_map.items():
            if old_name not in event_map:
                continue
            old_obj = event_map.pop(old_name)
            if new_name not in event_map:
                event_map[new_name] = old_obj
            elif isinstance(event_map.get(new_name), dict) and isinstance(old_obj, dict):
                # Preserve destination values, only fill missing keys.
                for k, v in old_obj.items():
                    if k not in event_map[new_name]:
                        event_map[new_name][k] = v
            changed_local = True
        return changed_local

    @classmethod
    def _migrate_heal_event_names_in_config(cls, config_obj):
        changed = False
        if not isinstance(config_obj, dict):
            return False

        changed = cls._migrate_heal_event_names_in_event_map(config_obj.get("events", {})) or changed

        slots = config_obj.get("event_slots", {})
        if isinstance(slots, dict):
            for slot_data in slots.values():
                changed = cls._migrate_heal_event_names_in_event_map(slot_data) or changed
        return changed

    def _migrate_heal_event_names(self):
        """
        Backward-compatible wrapper for legacy call sites.
        """
        return self._migrate_heal_event_names_in_config(self.config)

    def _apply_config_schema_migrations(self, config_obj):
        """
        Runs in-place config migrations up to CONFIG_SCHEMA_VERSION.
        Returns (changed, from_version, to_version).
        """
        if not isinstance(config_obj, dict):
            return False, 1, CONFIG_SCHEMA_VERSION

        raw_ver = config_obj.get("config_schema_version", 1)
        try:
            from_version = max(1, int(raw_ver))
        except Exception:
            from_version = 1

        current = from_version
        changed = False

        # v1 -> v2: rename legacy Heal milestones.
        if current < 2:
            changed = self._migrate_heal_event_names_in_config(config_obj) or changed
            current = 2

        # v2 -> v3: ensure updates section has required defaults.
        if current < 3:
            updates_cfg = config_obj.get("updates")
            if not isinstance(updates_cfg, dict):
                updates_cfg = {}
                config_obj["updates"] = updates_cfg
                changed = True

            repo_raw = str(updates_cfg.get("repo", "")).strip()
            if (not repo_raw) or (repo_raw.lower() == LEGACY_UPDATE_REPO.lower()):
                updates_cfg["repo"] = DEFAULT_UPDATE_REPO
                changed = True

            channel_raw = str(updates_cfg.get("channel", "")).strip().lower()
            if not channel_raw:
                updates_cfg["channel"] = "stable"
                changed = True

            current = 3

        # v3 -> v4: move updater checks back to the release repository.
        if current < 4:
            updates_cfg = config_obj.get("updates")
            if not isinstance(updates_cfg, dict):
                updates_cfg = {}
                config_obj["updates"] = updates_cfg
                changed = True

            repo_raw = str(updates_cfg.get("repo", "")).strip()
            if (not repo_raw) or (repo_raw.lower() == LEGACY_UPDATE_REPO.lower()):
                updates_cfg["repo"] = DEFAULT_UPDATE_REPO
                changed = True

            current = 4

        if current != int(config_obj.get("config_schema_version", 0) or 0):
            config_obj["config_schema_version"] = current
            changed = True

        # Ensure final target schema in case constants advance.
        if current < CONFIG_SCHEMA_VERSION:
            config_obj["config_schema_version"] = CONFIG_SCHEMA_VERSION
            current = CONFIG_SCHEMA_VERSION
            changed = True

        return changed, from_version, current

    def init_event_slots(self):
        """Initialize the event slot system. Migrate legacy config if needed."""
        import copy

        # 1. MIGRATION: If event_slots doesn't exist yet, create it from current events
        if "event_slots" not in self.config:
            existing_events = self.config.get("events", {})
            self.config["event_slots"] = {
                "Default": copy.deepcopy(existing_events)
            }
            self.config["active_event_slot"] = "Default"
            self.save_config()
            self.add_log("SYS: Migrated existing events into 'Default' preset slot.")

        # 2. Safety: Ensure at least one slot exists
        if not self.config["event_slots"]:
            self.config["event_slots"]["Default"] = {}
            self.config["active_event_slot"] = "Default"

        # 2b. Heal event name migration for legacy configs/slots.
        if self._migrate_heal_event_names():
            self.save_config()
            self.add_log("SYS: Migrated legacy Heal event names to new milestones.")

        # 3. Populate the combo box
        ui = self.ovl_config_win
        ui.combo_event_slot.blockSignals(True)
        ui.combo_event_slot.clear()

        slot_names = list(self.config["event_slots"].keys())
        ui.combo_event_slot.addItems(slot_names)

        # 4. Select the active slot
        active_slot = self.config.get("active_event_slot", slot_names[0])
        if active_slot not in slot_names:
            active_slot = slot_names[0]
            self.config["active_event_slot"] = active_slot

        idx = ui.combo_event_slot.findText(active_slot)
        if idx >= 0:
            ui.combo_event_slot.setCurrentIndex(idx)

        ui.combo_event_slot.blockSignals(False)

        # 5. Load active slot into self.config["events"]
        import copy as copy2
        self.config["events"] = copy2.deepcopy(self.config["event_slots"].get(active_slot, {}))

    def switch_event_slot(self, index):
        """Switch to a different event slot."""
        import copy
        ui = self.ovl_config_win
        slot_name = ui.combo_event_slot.currentText()
        if not slot_name:
            return

        # 1. Save current events back to the PREVIOUS slot
        prev_slot = self.config.get("active_event_slot", "")
        if prev_slot and prev_slot in self.config.get("event_slots", {}):
            self.config["event_slots"][prev_slot] = copy.deepcopy(self.config.get("events", {}))

        # 2. Load new slot into active events
        new_events = self.config.get("event_slots", {}).get(slot_name, {})
        self.config["events"] = copy.deepcopy(new_events)
        self.config["active_event_slot"] = slot_name

        # 3. Save & refresh UI
        self.save_config()

        # Reset the editing state
        ui.lbl_editing.setText("EDITING: NONE")
        ui.combo_evt_img.clear()
        ui.combo_evt_snd.clear()
        ui.ent_evt_duration.setText("3000")
        ui.slider_evt_scale.setValue(100)
        ui.slider_evt_vol.setValue(100)
        if hasattr(ui, "check_play_duplicate"):
            ui.check_play_duplicate.setChecked(True)
        if hasattr(ui, "check_evt_impact"):
            ui.check_evt_impact.setChecked(False)

        self.add_log(f"EVENT: Switched to preset '{slot_name}'.")

    @staticmethod
    def _validate_slot_name(name):
        """Returns (cleaned_name, error_msg). error_msg is None if valid."""
        INVALID_CHARS = r'\/:*?"<>|'
        RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL',
                          'COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9',
                          'LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9'}

        name = name.strip()
        if not name:
            return name, "Name cannot be empty."

        # Check for invalid characters
        found = [c for c in name if c in INVALID_CHARS]
        if found:
            chars = ' '.join(set(found))
            return name, f"Name contains invalid characters: {chars}\n\nThese are not allowed: {INVALID_CHARS}"

        # Check for reserved Windows names
        if name.upper().split('.')[0] in RESERVED_NAMES:
            return name, f"'{name}' is a reserved system name and cannot be used."

        # Check length
        if len(name) > 100:
            return name, "Name is too long (max 100 characters)."

        return name, None

    def create_event_slot(self):
        """Create a new event slot, optionally copying the current one."""
        import copy
        from PyQt6.QtWidgets import QInputDialog, QMessageBox

        ui = self.ovl_config_win

        # Ask for name
        name, ok = QInputDialog.getText(
            self.main_hub, "New Event Preset",
            "Enter a name for the new preset:",
        )
        if not ok or not name.strip():
            return

        name, err = self._validate_slot_name(name)
        if err:
            QMessageBox.warning(self.main_hub, "Invalid Name", err)
            return

        # Check for duplicates
        if name in self.config.get("event_slots", {}):
            QMessageBox.warning(self.main_hub, "Duplicate Name",
                                f"A preset named '{name}' already exists.")
            return

        # Ask if they want to copy current slot
        current_slot = self.config.get("active_event_slot", "Default")
        reply = QMessageBox.question(
            self.main_hub, "Copy Existing?",
            f"Copy all events from the current preset '{current_slot}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Save current state first
            self.config["event_slots"][current_slot] = copy.deepcopy(self.config.get("events", {}))
            new_events = copy.deepcopy(self.config.get("events", {}))
        else:
            new_events = {}

        # Create the slot
        self.config["event_slots"][name] = new_events

        # Add to combo and switch to it
        ui.combo_event_slot.blockSignals(True)
        ui.combo_event_slot.addItem(name)
        ui.combo_event_slot.blockSignals(False)

        # Switch to the new slot
        idx = ui.combo_event_slot.findText(name)
        ui.combo_event_slot.setCurrentIndex(idx)  # This triggers switch_event_slot

        self.add_log(f"EVENT: Created new preset '{name}'.")

    def rename_event_slot(self):
        """Rename the currently active event slot."""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox

        ui = self.ovl_config_win
        current_name = ui.combo_event_slot.currentText()
        if not current_name:
            return

        new_name, ok = QInputDialog.getText(
            self.main_hub, "Rename Preset",
            f"New name for '{current_name}':",
            text=current_name
        )
        if not ok or not new_name.strip():
            return

        new_name, err = self._validate_slot_name(new_name)
        if err:
            QMessageBox.warning(self.main_hub, "Invalid Name", err)
            return

        if new_name == current_name:
            return

        # Check for duplicates
        if new_name in self.config.get("event_slots", {}):
            QMessageBox.warning(self.main_hub, "Duplicate Name",
                                f"A preset named '{new_name}' already exists.")
            return

        # Rename in config
        slots = self.config["event_slots"]
        slots[new_name] = slots.pop(current_name)
        self.config["active_event_slot"] = new_name

        # Update combo
        ui.combo_event_slot.blockSignals(True)
        idx = ui.combo_event_slot.currentIndex()
        ui.combo_event_slot.setItemText(idx, new_name)
        ui.combo_event_slot.blockSignals(False)

        self.save_config()
        self.add_log(f"EVENT: Renamed preset '{current_name}' → '{new_name}'.")

    def delete_event_slot(self):
        """Delete the currently active event slot."""
        from PyQt6.QtWidgets import QMessageBox

        ui = self.ovl_config_win
        current_name = ui.combo_event_slot.currentText()
        if not current_name:
            return

        slots = self.config.get("event_slots", {})

        # Prevent deleting the last slot
        if len(slots) <= 1:
            QMessageBox.warning(self.main_hub, "Cannot Delete",
                                "You must have at least one preset. Create a new one first.")
            return

        # Confirm
        reply = QMessageBox.question(
            self.main_hub, "Delete Preset",
            f"Are you sure you want to delete '{current_name}'?\n\nThis will permanently remove all event settings in this preset.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Remove from config
        del slots[current_name]

        # Remove from combo and switch to first available
        ui.combo_event_slot.blockSignals(True)
        idx = ui.combo_event_slot.currentIndex()
        ui.combo_event_slot.removeItem(idx)

        # Switch to the first remaining slot
        first_slot = list(slots.keys())[0]
        self.config["active_event_slot"] = first_slot

        switch_idx = ui.combo_event_slot.findText(first_slot)
        ui.combo_event_slot.setCurrentIndex(max(switch_idx, 0))
        ui.combo_event_slot.blockSignals(False)

        # Explicitly load the new slot's events (don't rely on signal)
        import copy
        self.config["events"] = copy.deepcopy(slots.get(first_slot, {}))

        # Reset the editing state
        ui.lbl_editing.setText("EDITING: NONE")
        ui.combo_evt_img.clear()
        ui.combo_evt_snd.clear()
        ui.ent_evt_duration.setText("3000")
        ui.slider_evt_scale.setValue(100)
        ui.slider_evt_vol.setValue(100)

        self.save_config()
        self.add_log(f"EVENT: Deleted preset '{current_name}'. Switched to '{first_slot}'.")

    def export_event_slot(self):
        """Export the current event slot as a .zip file with all assets."""
        import zipfile
        import copy
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        ui = self.ovl_config_win
        slot_name = self.config.get("active_event_slot", "Default")

        # Sync current state to slot first
        self.config["event_slots"][slot_name] = copy.deepcopy(self.config.get("events", {}))

        events_data = copy.deepcopy(self.config.get("events", {}))
        if not events_data:
            QMessageBox.information(self.main_hub, "Nothing to Export",
                                    "The current preset has no events configured.")
            return

        # Ask for save location
        default_name = f"{slot_name}.zip"
        save_path, _ = QFileDialog.getSaveFileName(
            self.main_hub, "Export Event Preset",
            os.path.join(os.path.expanduser("~"), "Desktop", default_name),
            "ZIP Files (*.zip)"
        )
        if not save_path:
            return

        # Collect all referenced asset filenames
        asset_files = set()
        for evt_name, evt_data in events_data.items():
            # Images
            img = evt_data.get("img", "")
            if isinstance(img, list):
                for i in img:
                    if i: asset_files.add(str(i))
            elif img:
                asset_files.add(str(img))

            # Sounds
            snd = evt_data.get("snd", "")
            if isinstance(snd, list):
                for s in snd:
                    if s: asset_files.add(str(s))
            elif snd:
                asset_files.add(str(snd))

        # Build the ZIP
        try:
            packed_count = 0
            missing = []

            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. Write the event settings JSON
                settings_json = json.dumps({
                    "preset_name": slot_name,
                    "events": events_data
                }, indent=4)
                zf.writestr("preset_settings.json", settings_json)

                # 2. Pack each asset file
                for asset_name in sorted(asset_files):
                    # Try to find the file in all asset locations
                    found_path = None

                    # Check via get_asset_path first
                    candidate = get_asset_path(asset_name)
                    if os.path.isfile(candidate):
                        found_path = candidate
                    else:
                        # Fallback: search all asset dirs
                        for search_dir in [ASSETS_DIR, IMAGES_DIR, SOUNDS_DIR, CROSSHAIR_DIR]:
                            test = os.path.join(search_dir, asset_name)
                            if os.path.isfile(test):
                                found_path = test
                                break

                    if found_path:
                        # Store in zip under "assets/" prefix
                        zf.write(found_path, f"assets/{asset_name}")
                        packed_count += 1
                    else:
                        missing.append(asset_name)

            # Report
            msg = f"Preset '{slot_name}' exported successfully!\n\n"
            msg += f"• {len(events_data)} events\n"
            msg += f"• {packed_count} asset files packed"
            if missing:
                msg += f"\n\n⚠ {len(missing)} asset(s) not found (skipped):\n"
                msg += "\n".join(f"  - {m}" for m in missing[:10])
                if len(missing) > 10:
                    msg += f"\n  ... and {len(missing) - 10} more"

            QMessageBox.information(self.main_hub, "Export Complete", msg)
            self.add_log(f"EVENT: Exported preset '{slot_name}' → {save_path} ({packed_count} assets)")

        except Exception as e:
            QMessageBox.critical(self.main_hub, "Export Error", f"Failed to export:\n{e}")
            self.add_log(f"ERROR: Export failed: {e}")

    def import_event_slot(self):
        """Import an event preset from a .zip file."""
        import zipfile
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        ui = self.ovl_config_win

        # Ask for file
        zip_path, _ = QFileDialog.getOpenFileName(
            self.main_hub, "Import Event Preset",
            os.path.expanduser("~"),
            "ZIP Files (*.zip)"
        )
        if not zip_path:
            return

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # 1. Read settings JSON
                if "preset_settings.json" not in zf.namelist():
                    QMessageBox.critical(self.main_hub, "Invalid File",
                                         "This ZIP doesn't contain a valid event preset.\n(Missing preset_settings.json)")
                    return

                settings_raw = zf.read("preset_settings.json").decode("utf-8")
                settings = json.loads(settings_raw)
                imported_events = settings.get("events", {})
                imported_name = settings.get("preset_name", "Imported")

                # SECURITY: Sanitize imported preset name
                imported_name, name_err = self._validate_slot_name(imported_name)
                if name_err:
                    imported_name = "Imported"

                if not imported_events:
                    QMessageBox.information(self.main_hub, "Empty Preset",
                                            "The imported preset contains no events.")
                    return

                # 2. Ask user: New Slot or Merge?
                dlg = QMessageBox(self.main_hub)
                dlg.setWindowTitle("Import Mode")
                dlg.setText(
                    f"Preset: '{imported_name}' ({len(imported_events)} events)\n\n"
                    f"How would you like to import?"
                )
                btn_save = dlg.addButton("Save", QMessageBox.ButtonRole.YesRole)
                btn_merge = dlg.addButton("Merge", QMessageBox.ButtonRole.NoRole)
                btn_cancel = dlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                dlg.setDefaultButton(btn_save)
                dlg.exec()

                clicked = dlg.clickedButton()
                if clicked == btn_cancel:
                    return

                create_new = (clicked == btn_save)

                # 3. Extract asset files to correct folders (HARDENED)
                ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp',
                                      '.mp3', '.ogg', '.wav', '.flac'}
                asset_count = 0
                skipped = []
                for entry in zf.namelist():
                    if entry.startswith("assets/") and not entry.endswith("/"):
                        filename = entry.replace("assets/", "", 1)
                        if not filename:
                            continue

                        # SECURITY: Strip any path components — only allow bare filenames
                        filename = os.path.basename(filename)

                        # SECURITY: Reject path traversal attempts
                        if '..' in filename or filename.startswith(('/', '\\')):
                            skipped.append(filename)
                            continue

                        # SECURITY: Whitelist file extensions
                        _, ext = os.path.splitext(filename)
                        if ext.lower() not in ALLOWED_EXTENSIONS:
                            skipped.append(f"{filename} (blocked extension)")
                            continue

                        # Determine target path via get_asset_path
                        target_path = get_asset_path(filename)

                        # SECURITY: Verify resolved path is inside ASSETS_DIR
                        real_target = os.path.realpath(target_path)
                        real_assets = os.path.realpath(ASSETS_DIR)
                        if not real_target.startswith(real_assets + os.sep) and real_target != real_assets:
                            skipped.append(f"{filename} (path escape blocked)")
                            continue

                        target_dir = os.path.dirname(target_path)
                        os.makedirs(target_dir, exist_ok=True)

                        # Extract (skip if already exists — don't overwrite user's files)
                        if not os.path.isfile(target_path):
                            with open(target_path, 'wb') as f:
                                f.write(zf.read(entry))
                            asset_count += 1
                        else:
                            asset_count += 1  # Still count it as available

                if skipped:
                    self.add_log(f"SECURITY: Blocked {len(skipped)} suspicious file(s) during import.")

                # 4. Apply
                # BLOCK signals to prevent auto-save triggering during batch update
                ui.combo_evt_img.blockSignals(True)
                ui.combo_evt_snd.blockSignals(True)
                ui.slider_evt_scale.blockSignals(True)
                ui.slider_evt_vol.blockSignals(True)
                ui.ent_evt_duration.blockSignals(True)
                ui.check_play_duplicate.blockSignals(True)
                ui.check_evt_impact.blockSignals(True)

                try:
                    if create_new:
                        # Find a unique name
                        final_name = imported_name
                        counter = 2
                        while final_name in self.config.get("event_slots", {}):
                            final_name = f"{imported_name} ({counter})"
                            counter += 1

                        # Create new slot
                        self.config["event_slots"][final_name] = copy.deepcopy(imported_events)

                        # Add to combo and switch to it
                        ui.combo_event_slot.blockSignals(True)
                        ui.combo_event_slot.addItem(final_name)
                        ui.combo_event_slot.blockSignals(False)

                        idx = ui.combo_event_slot.findText(final_name)
                        ui.combo_event_slot.setCurrentIndex(idx)  # triggers switch_event_slot

                        msg = f"Imported as new preset '{final_name}'!"
                    else:
                        # Merge into current slot
                        current_slot = self.config.get("active_event_slot", "Default")
                        new_count = 0
                        skip_count = 0
                        known_events = set(ui.event_buttons.keys())

                        for evt_name, evt_data in imported_events.items():
                            # 1. Skip unknown event types
                            if evt_name not in known_events:
                                skip_count += 1
                                continue

                            # 2. Skip if already exists (as requested: "instead of being discarded")
                            # If the user has "Kill", we don't overwrite it with the one from the zip.
                            if evt_name in self.config["events"]:
                                skip_count += 1
                                continue

                            # 3. Apply
                            self.config["events"][evt_name] = copy.deepcopy(evt_data)
                            new_count += 1

                        # Sync to slot storage
                        self.config["event_slots"][current_slot] = copy.deepcopy(self.config["events"])

                        # Selection Reset
                        ui.current_event = None
                        ui.lbl_editing.setText("EDITING: NONE")
                        final_name = current_slot
                        msg = f"Merged into '{current_slot}':\n• {new_count} new events added\n• {skip_count} existing/unknown events skipped"
                finally:
                    # UNBLOCK signals
                    ui.combo_evt_img.blockSignals(False)
                    ui.combo_evt_snd.blockSignals(False)
                    ui.slider_evt_scale.blockSignals(False)
                    ui.slider_evt_vol.blockSignals(False)
                    ui.ent_evt_duration.blockSignals(False)
                    ui.check_play_duplicate.blockSignals(False)
                    ui.check_evt_impact.blockSignals(False)

                self.save_config()

                # Refresh asset dropdowns (new files may have been added)
                self.populate_overlay_assets()

                msg += f"\n\n• {len(imported_events)} total events in file\n• {asset_count} asset files"
                QMessageBox.information(self.main_hub, "Import Complete", msg)
                self.add_log(f"EVENT: Imported preset from {os.path.basename(zip_path)} → '{final_name}'")

        except zipfile.BadZipFile:
            QMessageBox.critical(self.main_hub, "Invalid File",
                                 "The selected file is not a valid ZIP archive.")
        except Exception as e:
            QMessageBox.critical(self.main_hub, "Import Error", f"Failed to import:\n{e}")
            self.add_log(f"ERROR: Import failed: {e}")


    def toggle_knife_visibility(self):
        """Toggles the knife icons on/off and updates the UI."""
        ui = self.ovl_config_win
        is_on = ui.btn_toggle_knives.isChecked()

        if is_on:
            ui.btn_toggle_knives.setText("KNIFE ICONS: ON")
            ui.btn_toggle_knives.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_toggle_knives.setText("KNIFE ICONS: OFF")
            ui.btn_toggle_knives.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ccc; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

        # Save & Update Overlay
        self.save_streak_settings_from_qt()

    def save_streak_settings_from_qt(self):
        """
        Reads killstreak settings from the GUI, saves the live path
        and preserves hidden settings (bold/shadow).
        """
        s_ui = self.ovl_config_win

        # 1. Initialize Config
        if "streak" not in self.config: self.config["streak"] = {}
        current_conf = self.config["streak"]

        def clean_path(text):
            if not text or "No file selected" in text:
                return ""
            return os.path.basename(text.strip())

        # --- A) GET DATA FROM LIVE OVERLAY ---
        final_path_data = current_conf.get("custom_path", [])
        if self.overlay_win and hasattr(self.overlay_win, 'custom_path'):
            final_path_data = self.overlay_win.custom_path

        # --- B) READ DATA FROM GUI ---
        is_active = s_ui.check_streak_master.isChecked()
        anim_active = s_ui.check_streak_anim.isChecked()
        streak_glow = s_ui.check_streak_glow.isChecked() if hasattr(s_ui, "check_streak_glow") else current_conf.get("streak_glow", current_conf.get("knife_glow", True))
        show_knives = s_ui.btn_toggle_knives.isChecked()

        main_img = clean_path(s_ui.ent_streak_img.text())
        if not main_img: main_img = "KS_Counter.png"

        try:
            speed = int(s_ui.ent_streak_speed.text())
        except ValueError:
            speed = 50

        tx = s_ui.slider_tx.value()
        ty = s_ui.slider_ty.value()
        scale = s_ui.slider_scale.value() / 100.0

        size_val = s_ui.slider_font_size.value()

        knife_tr = clean_path(s_ui.knife_inputs["TR"].text())
        knife_nc = clean_path(s_ui.knife_inputs["NC"].text())
        knife_vs = clean_path(s_ui.knife_inputs["VS"].text())

        # --- C) COLOR (SPECIAL CASE) ---
        # The color is written directly to the config by the color picker.
        # So we reload it here so it's not overwritten with an old value when saving.
        current_color = current_conf.get("color", "#ffffff")

        # --- D) PRESERVE LEGACY VALUES (NOT PRESENT IN GUI) ---
        # These values no longer exist in the Qt-GUI (no checkboxes for them),
        # so we must not null/delete them, but keep the old ones.
        keep_shadow = current_conf.get("shadow_size", 0)
        keep_bold = current_conf.get("bold", False)
        keep_underline = current_conf.get("underline", False)

        # --- E) FINAL UPDATE ---
        self.config["streak"].update({
            "active": is_active,
            "anim_active": anim_active,
            "streak_glow": streak_glow,
            "knife_glow": streak_glow,  # Backward-compat mirror for older builds.
            "show_knives": show_knives,
            "img": main_img,
            "speed": speed,
            "tx": tx,
            "ty": ty,
            "scale": scale,
            "size": size_val,

            # The current color (set by picker)
            "color": current_color,

            # The preserved legacy values
            "shadow_size": keep_shadow,
            "bold": keep_bold,
            "underline": keep_underline,

            # Paths
            "knife_tr": knife_tr,
            "knife_nc": knife_nc,
            "knife_vs": knife_vs,

            # Path Data
            "custom_path": final_path_data,
            "glow_color": current_conf.get("glow_color", "#00f2ff")
        })

        self.save_config()
        self.update_streak_display()

        self.add_log("SYS: Killstreak settings saved.")

    def save_stats_config_from_qt(self):
        """Reads ONLY Stats settings from Qt and saves them."""
        s_ui = self.ovl_config_win
        
        current_st_conf = self.config.get("stats_widget", {})
        saved_active_state = current_st_conf.get("active", True)
        
        st_data = {
            "active": saved_active_state,
            "tx": s_ui.slider_st_tx.value(),
            "ty": s_ui.slider_st_ty.value(),
            
            # Keep position
            "x": current_st_conf.get("x", 50),
            "y": current_st_conf.get("y", 500),

            "font_size": int(s_ui.combo_st_font.currentText()),
            
            # NEW: Save colors separately (in case they are missing in config_backup)
            "label_color": current_st_conf.get("label_color", "#00f2ff"),
            "value_color": current_st_conf.get("value_color", "#ffffff"),
            "glow": s_ui.check_stats_glow.isChecked() if hasattr(s_ui, "check_stats_glow") else current_st_conf.get("glow", True),
            "glow_color": current_st_conf.get("glow_color", "#00f2ff"),

            # Toggle Stats
            "show_k": s_ui.check_show_k.isChecked(),
            "show_d": s_ui.check_show_d.isChecked(),
            "show_hsr": s_ui.check_show_hsr.isChecked(),
            "show_kpm": s_ui.check_show_kpm.isChecked(),
            "show_kph": s_ui.check_show_kph.isChecked(),
            "show_time": s_ui.check_show_time.isChecked(),
            "show_dhsr": s_ui.check_show_dhsr.isChecked(),
            "show_kd": s_ui.check_show_kd.isChecked()
        }

        if "stats_widget" not in self.config: self.config["stats_widget"] = {}
        self.config["stats_widget"].update(st_data)
        
        self.save_config()
        self.update_stats_position_safe()
        self.add_log("SYS: Stats configuration updated.")

        # Immediate web HUD update for slider tweaks (no loop delay / no stale position).
        if self.overlay_win and hasattr(self.overlay_win, "reapply_stats_from_config"):
            self.overlay_win.reapply_stats_from_config()
        
        # Force redraw to apply visibility changes immediately
        self.update_session_time()

    def save_feed_config_from_qt(self):
        """Reads ONLY Feed settings from Qt and saves them."""
        s_ui = self.ovl_config_win
        
        current_kf_conf = self.config.get("killfeed", {})
        kf_active_state = current_kf_conf.get("active", True)

        kf_data = {
            "active": kf_active_state,
            "hs_icon": s_ui.ent_hs_icon.text(),
            "show_revives": s_ui.check_show_revives.isChecked(),
            "show_gunner": s_ui.check_show_gunner.isChecked() if hasattr(s_ui, "check_show_gunner") else True,
            "show_vehicle": s_ui.check_show_vehicle.isChecked() if hasattr(s_ui, "check_show_vehicle") else True,
            "auto_remove": s_ui.check_feed_auto_remove.isChecked() if hasattr(s_ui, "check_feed_auto_remove") else current_kf_conf.get("auto_remove", True),
            "stay_seconds": int(s_ui.spin_feed_stay_sec.value()) if hasattr(s_ui, "spin_feed_stay_sec") else int(current_kf_conf.get("stay_seconds", 10)),
            
            # Keep position
            "x": current_kf_conf.get("x", 50),
            "y": current_kf_conf.get("y", 200),

            "font_size": int(s_ui.combo_feed_font.currentText()),
            "hs_icon_size": int(s_ui.combo_hs_scale.currentText())
        }

        if "killfeed" not in self.config: self.config["killfeed"] = {}
        self.config["killfeed"].update(kf_data)
        
        self.save_config()
        # Feed position update if needed
        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()
            
        self.add_log("SYS: Killfeed configuration updated.")

    # (Duplicate removed - see line 3832)

    def _set_overlay_test_mode(self, mode=None):
        """Activates exactly one overlay element test mode at a time."""
        normalized = (mode or "").strip().lower()
        self.is_event_test = (normalized == "event")
        self.is_stats_test = (normalized == "stats")
        self.is_feed_test = (normalized == "feed")
        self.is_streak_test = (normalized == "streak")
        self.is_crosshair_test = (normalized == "crosshair")

    def _get_event_duration_ms(self, event_type):
        """Resolves final event duration using queue/global/specific rules."""
        events_dict = self.config.get("events", {})
        event_data = events_dict.get(event_type)
        if not event_data:
            for key, val in events_dict.items():
                if key.lower() == str(event_type).lower():
                    event_data = val
                    break

        event_data = event_data if isinstance(event_data, dict) else {}
        queue_active = self.config.get("event_queue_active", True)
        global_dur = int(self.config.get("event_global_duration", 3000))
        specific_dur = int(event_data.get("duration", 0))

        if not queue_active:
            dur = global_dur
        else:
            dur = specific_dur if specific_dur > 0 else global_dur

        etype = str(event_type).lower()
        if etype in ["hitmarker", "headshot hitmarker"]:
            dur = specific_dur if specific_dur > 0 else global_dur

        return max(100, int(dur))

    def test_event_visuals(self, event_type):
        """Runs an isolated event preview that is not cut off by gameplay checks."""
        if not self.overlay_win:
            self.add_log("WARN: Overlay not active!")
            return

        etype = str(event_type or "").strip()
        if not etype:
            self.add_log("WARN: No event selected for test.")
            return

        self._set_overlay_test_mode("event")
        duration_ms = self._get_event_duration_ms(etype)
        self._event_test_token += 1
        token = self._event_test_token

        self.add_log(f"SYS: Testing event '{etype}' ({duration_ms}ms).")
        self.trigger_overlay_event(etype)
        self.refresh_ingame_overlay()

        def end_event_test():
            if token != self._event_test_token:
                return
            if self.is_event_test:
                self._set_overlay_test_mode(None)
                self.refresh_ingame_overlay()
            self.add_log(f"SYS: Event test finished ({etype}).")

        QTimer.singleShot(duration_ms + 200, end_event_test)

    def test_killfeed_visuals(self):
        """Starts a robust multi-entry preview for the killfeed."""
        if not self.overlay_win:
            self.add_log("WARN: Overlay not active!")
            return

        self.add_log("SYS: Starting Killfeed visual test...")
        self._set_overlay_test_mode("feed")
        # Start from a clean feed so test output is deterministic.
        self.overlay_win.signals.clear_feed.emit()

        # 1. Config & Style
        kf_cfg_raw = self.config.get("killfeed", {})
        kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
        kf_font = kf_cfg.get("font_size", 19)
        base_style = (
            f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; "
            "margin-bottom: 2px; text-align: right;"
        )

        hs_icon = kf_cfg.get("hs_icon", "headshot.png")
        hs_size = kf_cfg.get("hs_icon_size", 19)
        icon_html = f'<img src="{get_asset_path(hs_icon)}" width="{hs_size}" height="{hs_size}" style="vertical-align: middle;"> '

        # 2. Test Cases
        test_entries = [
            f'<div style="{base_style}"><span style="color: #00ff00;">YOU </span>{icon_html}<span style="color: #ffffff;">TargetDummy</span></div>',
            f'<div style="{base_style}"><span style="color: #ff0000;">DEATH </span><span style="color: #ffffff;">SweatyPro77</span></div>',
            f'<div style="{base_style}"><span style="color: #00f2ff;">KILL </span><span style="color: #ffffff;">RandomPleb</span></div>',
            f'<div style="{base_style}"><span style="color: #ff8c00;">GUNNER </span>{icon_html}<span style="color: #ffffff;">Victim123</span></div>',
            f'<div style="{base_style}"><span style="color: #00ff00;">YOU </span><span style="color: white;">AnotherOne</span></div>'
        ]
        
        # Fire test events sequentially
        for i, msg in enumerate(test_entries):
             QTimer.singleShot(i * 600, lambda m=msg: self.overlay_win.signals.killfeed_entry.emit(m))

        # Apply positions & style live
        self.overlay_win.update_killfeed_pos()
        self.overlay_win.update_killfeed_ui()
        self.refresh_ingame_overlay()

        # Cleanup after 7 seconds
        def end_feed_test():
            if self.is_feed_test:
                self._set_overlay_test_mode(None)
            if self.overlay_win:
                self.overlay_win.signals.clear_feed.emit()
            self.add_log("SYS: Killfeed test finished.")
        
        QTimer.singleShot(7000, end_feed_test)

    def save_voice_config_from_qt(self):
        """Reads voice macros from Qt and saves them."""
        # Keep active status
        current_active = self.config.get("auto_voice", {}).get("active", True)

        new_v = {"active": current_active}
        for key, combo in self.ovl_config_win.voice_combos.items():
            new_v[key] = combo.currentText()

        self.config["auto_voice"] = new_v
        self.save_config()
        self.add_log("SYS: Auto-Voice Macros saved.")

    def load_settings_to_ui(self):
        """Transfers ALL config values to the Qt interface (Safe Loading)"""

        # 1. GET REFERENCES
        ui = self.ovl_config_win

        s_conf = self.config.get("streak", {})
        # Compatibility migration: old configs used `knife_glow`.
        if "streak_glow" not in s_conf and "knife_glow" in s_conf:
            s_conf["streak_glow"] = bool(s_conf.get("knife_glow", True))
            self.config["streak"] = s_conf
            self.save_config()
        st_conf = self.config.get("stats_widget", {"active": True})
        kf_conf = self.config.get("killfeed", {})
        v_conf = self.config.get("auto_voice", {})
        c_conf = self.config.get("crosshair", {})
        ev_conf = self.config.get("events", {})

        # --- QUEUE BUTTON ---
        queue_active = self.config.get("event_queue_active", True)

        # Load global timer (Default 3000ms)
        g_dur = self.config.get("event_global_duration", 3000)
        ui.ent_global_duration.setText(str(g_dur))

        ui.btn_queue_toggle.setChecked(queue_active)

        if queue_active:
            ui.btn_queue_toggle.setText("QUEUE: ON")
            ui.btn_queue_toggle.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; padding: 10px; outline: none; border: 1px solid #006600; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_queue_toggle.setText("QUEUE: OFF")
            ui.btn_queue_toggle.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; padding: 10px; outline: none; border: 1px solid #660000; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

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

            scifi_state = bool(self.config.get("scifi_overlay_active", False))
            if hasattr(ui, "btn_toggle_scifi"):
                ui.btn_toggle_scifi.blockSignals(True)
                ui.btn_toggle_scifi.setChecked(scifi_state)
                ui.btn_toggle_scifi.blockSignals(False)
                self._set_scifi_toggle_visual(scifi_state)
            if self.overlay_win and hasattr(self.overlay_win, "set_scifi_mode_enabled"):
                self.overlay_win.set_scifi_mode_enabled(scifi_state)

        # --- TAB 2: EVENTS ---
        eg_conf = self.config.get("events_global", {})
        if hasattr(ui, "check_events_active"):
            ui.check_events_active.blockSignals(True)
            ui.check_events_active.setChecked(eg_conf.get("active", True))
            ui.check_events_active.blockSignals(False)
        if hasattr(ui, "check_evt_glow"):
            ui.check_evt_glow.blockSignals(True)
            ui.check_evt_glow.setChecked(eg_conf.get("glow", True))
            ui.check_evt_glow.blockSignals(False)
        if hasattr(ui, "btn_evt_glow_color"):
            eg_col = eg_conf.get("glow_color", "#00f2ff")
            self._update_color_button_style(ui.btn_evt_glow_color, eg_col)

        if hasattr(ui, 'event_checkboxes'):
            for ev_name, checkbox in ui.event_checkboxes.items():
                entry = ev_conf.get(ev_name, {})
                is_active = entry.get("active", True) if isinstance(entry, dict) else True
                checkbox.setChecked(is_active)

        if hasattr(ui, 'lbl_editing'): ui.lbl_editing.setText("EDITING: NONE")
        ui.combo_evt_img.clear()
        ui.combo_evt_snd.clear()

        # --- TAB 3: KILLSTREAK ---
        # A) TEXT FIELDS
        saved_img = s_conf.get("img", "")
        ui.ent_streak_img.setText(saved_img if saved_img else "KS_Counter.png")
        ui.ent_streak_speed.setText(str(s_conf.get("speed", 50)))

        for fac in ["TR", "NC", "VS"]:
            if fac in ui.knife_inputs:
                config_key = f"knife_{fac.lower()}"
                saved_val = s_conf.get(config_key, "")
                ui.knife_inputs[fac].setText(saved_val)

        # B) ELEMENTS WITH SIGNALS
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
        if hasattr(ui, "check_streak_glow"):
            ui.check_streak_glow.blockSignals(True)
            ui.check_streak_glow.setChecked(s_conf.get("streak_glow", s_conf.get("knife_glow", True)))
            ui.check_streak_glow.blockSignals(False)
        
        if hasattr(ui, 'btn_streak_glow_color'):
            sg_col = s_conf.get("glow_color", "#00f2ff")
            self._update_color_button_style(ui.btn_streak_glow_color, sg_col)

        # >>> NEW: LOAD KNIFE BUTTON STATUS (Part C) <<<
        knives_active = s_conf.get("show_knives", True)
        # Block signals briefly if necessary (usually not critical here, but safe is safe)
        ui.btn_toggle_knives.blockSignals(True)
        ui.btn_toggle_knives.setChecked(knives_active)

        if knives_active:
            ui.btn_toggle_knives.setText("KNIFE ICONS: ON")
            ui.btn_toggle_knives.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_toggle_knives.setText("KNIFE ICONS: OFF")
            ui.btn_toggle_knives.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ccc; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )
        ui.btn_toggle_knives.blockSignals(False)
        # >>> END NEW <<<

        ui.slider_font_size.blockSignals(True)
        current_size = int(s_conf.get("size", 26))
        ui.slider_font_size.setValue(current_size)
        ui.slider_font_size.blockSignals(False)

        c_hex = s_conf.get("color", "#ffffff")
        text_col = "black" if QColor(c_hex).lightness() > 128 else "white"
        ui.btn_pick_color.setStyleSheet(
            f"QPushButton {{ background-color: {c_hex}; color: {text_col}; font-weight: bold; border: 1px solid #555; padding: 3px; border-radius: 3px; outline: none; }} "
            "QPushButton:focus { border: 1px solid #555; }"
            "QPushButton:hover { border: 1px solid #00f2ff; }"
        )

        # --- TAB 4: CROSSHAIR ---
        ui.check_cross.blockSignals(True)
        ui.cross_path.blockSignals(True)
        ui.check_cross.setChecked(c_conf.get("active", True))
        saved_file = c_conf.get("file", "")
        if not saved_file: saved_file = "crosshair.png"
        ui.cross_path.setText(saved_file)
        shadow_enabled = c_conf.get("shadow", False)
        ui.btn_toggle_cross_shadow.blockSignals(True)
        ui.btn_toggle_cross_shadow.setChecked(shadow_enabled)
        self.update_crosshair_shadow_button(shadow_enabled)
        ui.btn_toggle_cross_shadow.blockSignals(False)
        if hasattr(ui, "btn_toggle_cross_expand"):
            expand_enabled = bool(c_conf.get("ads_fire_expand", True))
            ui.btn_toggle_cross_expand.blockSignals(True)
            ui.btn_toggle_cross_expand.setChecked(expand_enabled)
            self.update_crosshair_expand_button(expand_enabled)
            ui.btn_toggle_cross_expand.blockSignals(False)
        ui.check_cross.blockSignals(False)
        ui.cross_path.blockSignals(False)

        # --- TAB 5: STATS & FEED ---
        st_active = st_conf.get("active", True)
        if st_active:
            ui.btn_toggle_stats.setText("STATS WIDGET: ON")
            ui.btn_toggle_stats.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_stats.setText("STATS WIDGET: OFF")
            ui.btn_toggle_stats.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        # Sliders (as before)
        ui.slider_st_tx.blockSignals(True)
        ui.slider_st_tx.setValue(st_conf.get("tx", 0))
        ui.slider_st_tx.blockSignals(False)
        ui.slider_st_ty.blockSignals(True)
        ui.slider_st_ty.setValue(st_conf.get("ty", 0))
        ui.slider_st_ty.blockSignals(False)
        if hasattr(ui, "lbl_st_tx_val"):
            ui.lbl_st_tx_val.setText(str(int(st_conf.get("tx", 0))))
        if hasattr(ui, "lbl_st_ty_val"):
            ui.lbl_st_ty_val.setText(str(int(st_conf.get("ty", 0))))

        # NEW: Font Size (Stats) - Dropdown Support
        ui.combo_st_font.blockSignals(True)
        ui.combo_st_font.setCurrentText(str(int(st_conf.get("font_size", 22))))
        ui.combo_st_font.blockSignals(False)

        # COLORS (Stats)
        if hasattr(ui, 'btn_stats_label_color'):
            l_col = st_conf.get("label_color", "#00f2ff")
            self._update_color_button_style(ui.btn_stats_label_color, l_col)
        if hasattr(ui, 'btn_stats_value_color'):
            v_col = st_conf.get("value_color", "#ffffff")
            self._update_color_button_style(ui.btn_stats_value_color, v_col)
        
        if hasattr(ui, 'btn_stats_glow_color'):
            stg_col = st_conf.get("glow_color", "#00f2ff")
            self._update_color_button_style(ui.btn_stats_glow_color, stg_col)

        # New Toggles - Read from config, default True
        if hasattr(ui, "check_show_k"):
            ui.check_show_k.blockSignals(True)
            ui.check_show_k.setChecked(st_conf.get("show_k", True))
            ui.check_show_k.blockSignals(False)
            
            ui.check_show_d.blockSignals(True)
            ui.check_show_d.setChecked(st_conf.get("show_d", True))
            ui.check_show_d.blockSignals(False)
            
            ui.check_show_hsr.blockSignals(True)
            ui.check_show_hsr.setChecked(st_conf.get("show_hsr", True))
            ui.check_show_hsr.blockSignals(False)
            
            ui.check_show_kpm.blockSignals(True)
            ui.check_show_kpm.setChecked(st_conf.get("show_kpm", True))
            ui.check_show_kpm.blockSignals(False)

            ui.check_show_kph.blockSignals(True)
            ui.check_show_kph.setChecked(st_conf.get("show_kph", True))
            ui.check_show_kph.blockSignals(False)
            
            ui.check_show_time.blockSignals(True)
            ui.check_show_time.setChecked(st_conf.get("show_time", True))
            ui.check_show_time.blockSignals(False)

            ui.check_show_dhsr.blockSignals(True)
            ui.check_show_dhsr.setChecked(st_conf.get("show_dhsr", True))
            ui.check_show_dhsr.blockSignals(False)
            
            ui.check_show_kd.blockSignals(True)
            ui.check_show_kd.setChecked(st_conf.get("show_kd", True))
            ui.check_show_kd.blockSignals(False)

        if hasattr(ui, "check_stats_glow"):
            ui.check_stats_glow.blockSignals(True)
            ui.check_stats_glow.setChecked(st_conf.get("glow", True))
            ui.check_stats_glow.blockSignals(False)

        # 2. Killfeed Button Status
        kf_active = kf_conf.get("active", True)
        if kf_active:
            ui.btn_toggle_feed.setText("KILLFEED: ON")
            ui.btn_toggle_feed.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_feed.setText("KILLFEED: OFF")
            ui.btn_toggle_feed.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )

        ui.ent_hs_icon.blockSignals(True)
        ui.ent_hs_icon.setText(kf_conf.get("hs_icon", "Headshot.png"))
        ui.ent_hs_icon.blockSignals(False)

        ui.check_show_revives.blockSignals(True)
        ui.check_show_revives.setChecked(kf_conf.get("show_revives", True))
        ui.check_show_revives.blockSignals(False)
        if hasattr(ui, "check_show_gunner"):
            ui.check_show_gunner.blockSignals(True)
            ui.check_show_gunner.setChecked(kf_conf.get("show_gunner", True))
            ui.check_show_gunner.blockSignals(False)

        if hasattr(ui, "check_show_vehicle"):
            ui.check_show_vehicle.blockSignals(True)
            ui.check_show_vehicle.setChecked(kf_conf.get("show_vehicle", True))
            ui.check_show_vehicle.blockSignals(False)
        if hasattr(ui, "check_feed_auto_remove"):
            ui.check_feed_auto_remove.blockSignals(True)
            ui.check_feed_auto_remove.setChecked(kf_conf.get("auto_remove", True))
            ui.check_feed_auto_remove.blockSignals(False)
        if hasattr(ui, "spin_feed_stay_sec"):
            ui.spin_feed_stay_sec.blockSignals(True)
            ui.spin_feed_stay_sec.setValue(int(kf_conf.get("stay_seconds", 10)))
            ui.spin_feed_stay_sec.blockSignals(False)

        # NEW: Font Size (Feed) - Dropdown Support / HS Icon Size
        ui.combo_feed_font.blockSignals(True)
        ui.combo_feed_font.setCurrentText(str(int(kf_conf.get("font_size", 19))))
        ui.combo_feed_font.blockSignals(False)
        ui.combo_hs_scale.blockSignals(True)
        ui.combo_hs_scale.setCurrentText(str(int(kf_conf.get("hs_icon_size", 19))))
        ui.combo_hs_scale.blockSignals(False)

        # --- TAB 6: VOICE MACROS ---
        vm_active = v_conf.get("active", True)
        ui.btn_toggle_voice.blockSignals(True)
        ui.btn_toggle_voice.setChecked(vm_active)
        # Style update
        if vm_active:
            ui.btn_toggle_voice.setText("VOICE MACROS: ON")
            ui.btn_toggle_voice.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
        else:
            ui.btn_toggle_voice.setText("VOICE MACROS: OFF")
            ui.btn_toggle_voice.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )
        ui.btn_toggle_voice.blockSignals(False)

        for key, combo in ui.voice_combos.items():
            val = v_conf.get(key, "OFF")
            idx = combo.findText(str(val))
            if idx >= 0: combo.setCurrentIndex(idx)

        # --- OVERLAY INIT ---
        if self.overlay_win:
            # 1. Initialize crosshair
            ch_active = c_conf.get("active", True)
            ch_file = c_conf.get("file", "crosshair.png")
            if not ch_file: ch_file = "crosshair.png"
            full_path = get_asset_path(ch_file)
            current_size = c_conf.get("size", 32)

            # Crosshair logic
            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, "is_hud_editing", False)
            should_show = (ch_active and game_running) or edit_mode
            self.overlay_win.update_crosshair(full_path, current_size, should_show)

            # 2. Killstreak Init
            self.update_streak_display()

            # 3. Killfeed Position Init
            if hasattr(self.overlay_win, 'update_killfeed_pos'):
                self.overlay_win.update_killfeed_pos()

            # 4. START LOOP (Delayed)
            # We NO LONGER do manual positioning here.
            # The loop (refresh_ingame_overlay) takes care of everything.
            QTimer.singleShot(500, self.refresh_ingame_overlay)

        # --- TWITCH LOAD ---
        twitch_conf = self.config.get("twitch", {})

        # 1. Text Fields & Toggle
        ui.ent_twitch_channel.setText(twitch_conf.get("channel", ""))
        active = twitch_conf.get("active", False)
        ui.btn_toggle_twitch.setChecked(active)
        self.toggle_twitch_active(active)  # Update UI & Overlay immediately

        # 2. Widgets (Sliders & SpinBox)
        # Block signals briefly to avoid firing an update on every SetValue
        ui.slider_twitch_opacity.blockSignals(True)
        ui.slider_twitch_x.blockSignals(True)
        ui.slider_twitch_y.blockSignals(True)
        ui.slider_twitch_w.blockSignals(True)
        ui.slider_twitch_h.blockSignals(True)
        ui.spin_twitch_hold.blockSignals(True)  # NEW: Block Hold Time signals

        ui.slider_twitch_opacity.setValue(twitch_conf.get("opacity", 30))
        ui.slider_twitch_x.setValue(twitch_conf.get("x", 50))
        ui.slider_twitch_y.setValue(twitch_conf.get("y", 300))
        ui.slider_twitch_w.setValue(twitch_conf.get("w", 350))
        ui.slider_twitch_h.setValue(twitch_conf.get("h", 400))
        ui.spin_twitch_hold.setValue(twitch_conf.get("hold_time", 15))  # NEW

        ui.slider_twitch_opacity.blockSignals(False)
        ui.slider_twitch_x.blockSignals(False)
        ui.slider_twitch_y.blockSignals(False)
        ui.slider_twitch_w.blockSignals(False)
        ui.slider_twitch_h.blockSignals(False)
        ui.spin_twitch_hold.blockSignals(False)  # NEW

        is_always = twitch_conf.get("always_on", False)
        ui.btn_twitch_always.setChecked(is_always)

        # Adjust UI visuals to the loaded state
        if is_always:
            ui.btn_twitch_always.setText("ALWAYS ON")
            ui.btn_twitch_always.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; outline: none; border: 1px solid #006600; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_twitch_always.setText("PLANETSIDE")
            ui.btn_twitch_always.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; outline: none; border: 1px solid #660000; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

        # IGNORE SPECIAL
        is_ignore_special = twitch_conf.get("ignore_special", False)
        ui.btn_twitch_ignore_special.blockSignals(True)
        ui.btn_twitch_ignore_special.setChecked(is_ignore_special)
        ui.btn_twitch_ignore_special.blockSignals(False)

        if is_ignore_special:
            ui.btn_twitch_ignore_special.setText("IGNORE SPECIAL CHARS (!): ON")
            ui.btn_twitch_ignore_special.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
                "QPushButton:focus { border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            ui.btn_twitch_ignore_special.setText("IGNORE SPECIAL CHARS (!): OFF")
            ui.btn_twitch_ignore_special.setStyleSheet(
                "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
                "QPushButton:focus { border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

        # 3. Font
        current_font = str(twitch_conf.get("font_size", 12))
        ui.combo_twitch_font.setCurrentText(current_font)
        # Ignore List
        ui.ent_twitch_ignore.setText(twitch_conf.get("ignore_list", ""))

        # Silence Alert settings
        ui.check_twitch_silence_active.setChecked(twitch_conf.get("silence_active", False))
        ui.spin_twitch_silence_seconds.setValue(twitch_conf.get("silence_timeout", 600))
        
        # Populate combobox with saved sounds
        ui.combo_twitch_silence_snd.blockSignals(True)
        ui.combo_twitch_silence_snd.clear()
        saved_snds = twitch_conf.get("silence_snd", [])
        if isinstance(saved_snds, list):
            ui.combo_twitch_silence_snd.addItems(saved_snds)
        elif saved_snds: # Backward compat for single string
            ui.combo_twitch_silence_snd.addItem(saved_snds)
        
        # Restore active selection
        ui.combo_twitch_silence_snd.setCurrentText(twitch_conf.get("silence_snd_active", ""))
        ui.combo_twitch_silence_snd.blockSignals(False)
        
        ui.slider_twitch_silence_vol.setValue(twitch_conf.get("silence_vol", 100))

        # 4. Immediate application to overlay (Sync)
        self.overlay_win.set_chat_hold_time(twitch_conf.get("hold_time", 15))
        self.update_twitch_visuals()

        if self.overlay_win:
            active = twitch_conf.get("active", False)
            # Check now (Game-Running OR Always-On)
            self.overlay_win.update_twitch_visibility(active)
        if active and twitch_conf.get("channel"):
            # We give the system a second to load stably
            # before starting the thread for Twitch chat.
            QTimer.singleShot(1000, self.start_twitch_connection)
            self.add_log(f"TWITCH: Auto-connecting to #{twitch_conf.get('channel')}...")

        # 10. OBS / STREAMING SERVICE
        obs_conf = self.config.get("obs_service", {"enabled": False, "port": 8000, "ws_port": 6789})
        if hasattr(ui, 'tab_streaming'):
            s_tab = ui.tab_streaming
            s_tab.btn_toggle_service.blockSignals(True)
            enabled = obs_conf.get("enabled", False)
            s_tab.btn_toggle_service.setChecked(enabled)
            s_tab.update_button_style(enabled)
            s_tab.btn_toggle_service.blockSignals(False)
            
            s_tab.ent_port.blockSignals(True)
            s_tab.ent_port.setText(str(obs_conf.get("port", 8000)))
            s_tab.ent_port.blockSignals(False)

            s_tab.ent_ws_port.blockSignals(True)
            s_tab.ent_ws_port.setText(str(obs_conf.get("ws_port", 6789)))
            s_tab.ent_ws_port.blockSignals(False)
            
            s_tab.lbl_url.setText(f"http://localhost:{obs_conf.get('port', 8000)}/")

        self.add_log("SYS: Overlay configuration synchronized.")

    def change_server_logic(self, world_id):
        self.current_world_id = world_id
        self.add_log(f"FILTER UPDATE: Now showing World ID {world_id}")
        
        # Save new preference
        self.config["world_id"] = world_id
        self.save_config()
        
        # No websocket restart needed - we monitor all servers globally.
        # This function just updates the visual filter ID.

    def ps2_process_monitor(self):
        """Monitors process and uses signals."""
        self.ps2_running = None
        import subprocess
        import time

        print("MONITOR: Thread waiting for GUI...")
        time.sleep(2.0)
        print("MONITOR: Thread started.")

        while True:
            try:
                # Tasklist query (Windows) vs pgrep (Linux)
                if IS_WINDOWS:
                    output = subprocess.check_output('TASKLIST /FI "IMAGENAME eq PlanetSide2_x64.exe"', shell=True).decode(
                        "cp1252", errors="ignore")
                    is_now_running = "PlanetSide2_x64.exe" in output
                else:
                    # Linux check via pgrep
                    try:
                        subprocess.check_output(["pgrep", "-f", "PlanetSide2_x64.exe"])
                        is_now_running = True
                    except subprocess.CalledProcessError:
                        is_now_running = False

                if self.ps2_running is None or is_now_running != self.ps2_running:
                    self.ps2_running = is_now_running

                    if is_now_running:
                        print("MONITOR: Game detected -> Sending START signal")
                        # INSTEAD OF QTIMER: Send signal!
                        self.worker_signals.game_status_changed.emit(True)
                    else:
                        if self.ps2_running is not None:
                            print("MONITOR: Game gone -> Sending STOP signal")
                        # INSTEAD OF QTIMER: Send signal!
                        self.worker_signals.game_status_changed.emit(False)

            except Exception as e:
                print(f"Monitor Error: {e}")

            time.sleep(4)

    def start_path_record(self):
        if not self.overlay_win: return
        ui = self.ovl_config_win

        is_recording = getattr(self.overlay_win, "path_edit_active", False)

        if not is_recording:
            # --- START ---
            self.overlay_win.path_edit_active = True
            self.overlay_win.set_mouse_passthrough(False)
            self.overlay_win.custom_path = []

            # Activate layer & get focus
            self.overlay_win.path_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.overlay_win.path_layer.setGeometry(self.overlay_win.rect())
            self.overlay_win.path_layer.show()
            self.overlay_win.path_layer.raise_()
            self.overlay_win.activateWindow()
            self.overlay_win.setFocus()

            # --- CLICK-THROUGH FIX ---
            # We make images "invisible" to mouse so click lands on path layer
            if hasattr(self.overlay_win, 'streak_bg_label'):
                self.overlay_win.streak_bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if hasattr(self.overlay_win, 'streak_text_label'):
                self.overlay_win.streak_text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


            # QT BUTTON UPDATE
            ui.btn_path_record.setText("STOP RECORDING (SPACE)")
            ui.btn_path_record.setProperty("recording", "true")
            ui.btn_path_record.style().unpolish(ui.btn_path_record)
            ui.btn_path_record.style().polish(ui.btn_path_record)
            ui.btn_path_record.update()

            # Show dummy streak
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

            # --- CLICK-THROUGH RESTORE ---
            # Make clickable again for Move UI
            if hasattr(self.overlay_win, 'streak_bg_label'):
                self.overlay_win.streak_bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            if hasattr(self.overlay_win, 'streak_text_label'):
                self.overlay_win.streak_text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

            # QT BUTTON RESET
            ui.btn_path_record.setText("REC PATH")
            ui.btn_path_record.setProperty("recording", "false")
            ui.btn_path_record.style().unpolish(ui.btn_path_record)
            ui.btn_path_record.style().polish(ui.btn_path_record)
            ui.btn_path_record.update()

            # Save path (takes custom_path automatically from overlay)
            self.save_streak_settings_from_qt()
            self.add_log("PATH: Recording stopped and saved.")

    def clear_path(self):
        if "streak" in self.config:
            self.config["streak"]["custom_path"] = []
            if self.overlay_win: self.overlay_win.custom_path = []
            self.save_config()
            self.update_streak_display()
            self.add_log("PATH: Path deleted.")



    def center_crosshair(self):
        """Centers global crosshair based on current overlay size."""
        if not self.overlay_win: 
            return

        # Save true CENTER coordinates (config stores center point, not top-left).
        center_x_px = int(self.overlay_win.width() / 2)
        center_y_px = int(self.overlay_win.height() / 2)
        logic_x = int(round(center_x_px / self.overlay_win.ui_scale))
        logic_y = int(round(center_y_px / self.overlay_win.ui_scale))

        if "crosshair" not in self.config:
            self.config["crosshair"] = {}
        self.config["crosshair"]["x"] = logic_x
        self.config["crosshair"]["y"] = logic_y
        self.save_config()

        # Force immediate live update so UI and web overlay match right away.
        self.update_crosshair_from_qt()

    def save_crosshair_settings_qt(self):
        """Reads UI values from crosshair tab, saves to config and updates overlay."""
        ui = self.ovl_config_win

        # 1. Read values from GUI
        is_active = ui.check_cross.isChecked()
        file_path = ui.cross_path.text().strip()
        shadow_enabled = ui.btn_toggle_cross_shadow.isChecked() if hasattr(ui, "btn_toggle_cross_shadow") else False
        expand_enabled = ui.btn_toggle_cross_expand.isChecked() if hasattr(ui, "btn_toggle_cross_expand") else True

        # 2. Prepare config dictionary if not existent
        if "crosshair" not in self.config:
            self.config["crosshair"] = {}

        # 3. Update values
        self.config["crosshair"]["active"] = is_active
        self.config["crosshair"]["file"] = file_path
        self.config["crosshair"]["shadow"] = shadow_enabled
        self.config["crosshair"]["ads_fire_expand"] = bool(expand_enabled)
        self.update_crosshair_expand_button(expand_enabled)
        if not expand_enabled:
            self._set_crosshair_recoil_level(0.0)

        # Fallback for size if not set
        if "size" not in self.config["crosshair"]:
            self.config["crosshair"]["size"] = 32

        # NEW: Read size slider (IMPORTANT: Restored)
        size_val = self.config["crosshair"]["size"]
        if hasattr(ui, 'slider_cross_size'):
            size_val = ui.slider_cross_size.value()
            self.config["crosshair"]["size"] = size_val

        # 4. Save to file
        self.save_config()

        # 5. Update overlay live
        if self.overlay_win:
            full_path = get_asset_path(file_path)
            game_running = getattr(self, 'ps2_running', False)
            edit_mode = getattr(self, 'is_hud_editing', False)
            should_show = is_active and (game_running or edit_mode)

            # Send update command to overlay
            self.overlay_win.update_crosshair(full_path, size_val, should_show)

    def load_item_db(self, filepath):
        """Loads the weapon database from assets folder"""
        self.item_db = {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                next(f)  # Skip: Item ID, Item Category, Is Vehicle Weapon...
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 6:
                        item_id = parts[0]
                        item_name = parts[3]
                        weapon_class = parts[1]  # 'none', 'max', 'infantry', 'vehicle'

                        # Save so you can easily access it later
                        self.item_db[item_id] = {
                            "name": item_name,
                            "type": weapon_class
                        }
            print(f"Database loaded: {len(self.item_db)} items found.")
        except Exception as e:
            print(f"Error loading item DB: {e}")

    def load_config(self):
        """
        Loads configuration with intelligent backup strategy.
        Order:
        1. config.json (Main file)
        2. config_backup.json (If main file corrupt/empty)
        3. Default values (If all else fails)
        """
        def deep_merge(base, update):
            for k, v in update.items():
                if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
            return base

        # 1. Define paths
        # Script/dev mode should use local config next to the script.
        # Frozen release builds should keep using per-user config storage.
        if getattr(sys, "frozen", False):
            self.user_data_dir = get_user_data_dir()
        else:
            self.user_data_dir = self.BASE_DIR
        user_config_path = os.path.join(self.user_data_dir, "config.json")
        backup_config_path = user_config_path.replace("config.json", "config_backup.json")
        template_path = resource_path("config.json")
        legacy_config_path = os.path.join(self.BASE_DIR, "config.json")
        legacy_backup_path = legacy_config_path.replace("config.json", "config_backup.json")

        # 2. Standard values (Fallback)
        default_conf = {
            "config_schema_version": CONFIG_SCHEMA_VERSION,
            "ps2_path": "",
            "overlay_master_active": True,
            "scifi_overlay_active": False,
            "crosshair": {"file": "crosshair.png", "size": 32, "active": True, "shadow": False, "ads_fire_expand": True},
            "events": {},
            "streak": {"img": "KS_Counter.png", "active": True},
            "stats_widget": {"active": True},
            "killfeed": {"active": True},
            "discord_presence_active": False,
            "updates": {
                "repo": DEFAULT_UPDATE_REPO,
                "channel": "stable",
            },
        }

        # 3. FIRST-START LOGIC: Migrate legacy local config into user profile location.
        same_dir = os.path.abspath(self.user_data_dir) == os.path.abspath(self.BASE_DIR)
        if (not same_dir) and (not os.path.exists(user_config_path)) and os.path.exists(legacy_config_path):
            try:
                shutil.copy2(legacy_config_path, user_config_path)
                if os.path.exists(legacy_backup_path):
                    shutil.copy2(legacy_backup_path, backup_config_path)
                self._startup_legacy_config_imported = True
            except Exception as e:
                print(f"WARNING: Legacy config import failed: {e}")

        # 4. FIRST-START LOGIC: Extract template
        if not os.path.exists(user_config_path) and not os.path.exists(backup_config_path) and os.path.exists(
                template_path):
            try:
                shutil.copy2(template_path, user_config_path)
                print("SYS: Default configuration created.")
            except Exception as e:
                print(f"Config Template Copy Error: {e}")

        # 5. LOADING WITH ERROR HANDLING
        loaded_conf = {}
        load_source = "DEFAULT"

        # Attempt 1: Main file
        if os.path.exists(user_config_path):
            try:
                with open(user_config_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        raise ValueError("File is empty")
                    loaded_conf = json.loads(content)
                    load_source = "MAIN"
            except (json.JSONDecodeError, ValueError, Exception) as e:
                print(f"WARNING: config.json is corrupt ({e}). Trying backup...")

                # Attempt 2: Backup file
                if os.path.exists(backup_config_path):
                    try:
                        with open(backup_config_path, "r", encoding="utf-8") as f:
                            loaded_conf = json.load(f)
                        print("SUCCESS: Configuration restored from backup!")
                        load_source = "BACKUP"

                        # Immediately repair broken main file
                        try:
                            shutil.copy2(backup_config_path, user_config_path)
                            print("SYS: Main config repaired by backup.")
                        except:
                            pass

                    except Exception as e2:
                        print(f"ERROR: Backup also corrupt: {e2}. Using defaults.")
                        load_source = "RESET"
                else:
                    print("ERROR: No backup found. Using defaults.")
                    load_source = "RESET"
        # 6. MERGING (Deep Mix defaults with loaded)
        deep_merge(default_conf, loaded_conf)

        # 7. Run config schema migrations.
        schema_changed, schema_from, schema_to = self._apply_config_schema_migrations(default_conf)
        self._startup_config_schema_migrated = schema_changed
        self._startup_config_schema_from = schema_from
        self._startup_config_schema_to = schema_to

        # Save path for save_config
        self.config_path = user_config_path

        # Save status to display later in log (since add_log might not work here yet)
        self._startup_config_status = load_source

        # Persist schema-migrated config immediately for deterministic next startup.
        if schema_changed:
            try:
                os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
                with open(user_config_path, "w", encoding="utf-8") as f:
                    json.dump(default_conf, f, indent=4)
                with open(backup_config_path, "w", encoding="utf-8") as f:
                    json.dump(default_conf, f, indent=4)
            except Exception as e:
                print(f"WARNING: Failed to persist schema-migrated config: {e}")

        return default_conf


    # --- UI & NAVIGATION ---

    def show_dashboard(self):
        """Switches to the Dashboard tab in the Qt interface"""
        self.current_tab = "Dashboard"
        # If your MainHub uses a QStackedWidget for tabs:
        if hasattr(self.main_hub, 'stacked_widget'):
            # Index 0 is usually dashboard
            self.main_hub.stacked_widget.setCurrentIndex(0)

        self.add_log("DASHBOARD: View active.")
        # Initial trigger for data update
        self.update_live_graph()


    def toggle_kd_mode(self):
        """Switches between 'Real KD' and 'Revive KD'."""
        self.kd_mode_revive = not self.kd_mode_revive

        mode_str = "REVIVE KD" if self.kd_mode_revive else "REAL KD"
        self.add_log(f"MODE: Switched to {mode_str}")

        # Update dashboard button text (via signal or directly)
        if hasattr(self, 'dash_window') and hasattr(self.dash_window, 'btn_toggle_kd'):
            txt = "KD MODE: REVIVE" if self.kd_mode_revive else "KD MODE: REAL"
            self.dash_window.btn_toggle_kd.setText(txt)
            # Adjust color
            col = "#00ff00" if self.kd_mode_revive else "#ff0000"
            self.dash_window.btn_toggle_kd.setStyleSheet(f"""
                QPushButton {{ 
                    background-color: #2b2b2b; color: {col}; border: 1px solid #333; 
                    font-size: 10px; font-weight: bold; padding: 4px; 
                }}
                QPushButton:hover {{ border: 1px solid {col}; }}
            """)
        
        # Calculate and send all data immediately
        self.update_dashboard_elements()

    def update_dashboard_elements(self):
        """Sends real live data to new PyQt6 dashboard via signals."""
        if not hasattr(self, 'dash_window') or not hasattr(self, 'dash_controller'):
            return

        # Get currently selected server ID (Default: 10/EU)
        current_wid = str(getattr(self, 'current_world_id', '10'))

        # 1. PREPARE DATA
        # Total incl. NSO/Unknown
        total_players = self.live_stats.get("Total", 0)

        # Factions (TR, NC, VS) - NSO deliberately left out for balance display
        faction_data = {
            "TR": self.live_stats.get("TR", 0),
            "NC": self.live_stats.get("NC", 0),
            "VS": self.live_stats.get("VS", 0)
        }

        # 2. SEND UPDATES
        # A) Update Text-Label (Total Players)
        self.dash_controller.signals.update_population.emit(total_players)

        # B) Update Faction Bars
        self.dash_controller.signals.update_factions.emit(faction_data)

        # C) Update Graph (NEW: Transfer Total AND Faction data)
        # We access the graph object directly as it is the most efficient way
        # to transfer complex data (Dicts + Ints) without signal modification.
        if hasattr(self.dash_window, 'graph'):
            self.dash_window.graph.update_history(total_players, faction_data)

        # 3. PREPARE PLAYER LIST
        active_ids = self.active_players.keys()
        now = time.time()
        prepared_players = []

        for p_id, p in self.session_stats.items():
            # Only consider players still marked as 'active'
            if not isinstance(p, dict) or p_id not in active_ids:
                continue

            # --- SERVER FILTER ---
            if str(p.get("world_id", "0")) != current_wid:
                continue

            # --- NAME FIX ---
            p_name = p.get("name")
            if p_name in ["Unknown", "Searching...", None]:
                p_name = self.name_cache.get(p_id, f"ID: {p_id[-4:]}")

            # --- KPM LOGIC ---
            p_start = p.get("start", now)
            active_min = max((now - p_start) / 60, 0.5)

            # --- KD CALCULATION (Real vs Revive) ---
            raw_deaths = p.get("d", 0)
            revives = p.get("revives_received", 0)

            if self.kd_mode_revive:
                # Revive Mode: Deaths reduced by revives (min 0)
                eff_deaths = max(0, raw_deaths - revives)
            else:
                # Real Mode: All deaths count
                eff_deaths = raw_deaths

            # Assemble package
            # IMPORTANT: We send 'eff_deaths' as 'd' so dashboard (table + graph)
            # automatically shows correct values without needing logic changes there.
            prepared_players.append({
                "name": p_name,
                "fac": p.get("faction", "NSO"),  # NSO is okay here so you see who it is
                "k": p.get("k", 0),
                "d": eff_deaths,
                "a": p.get("a", 0),
                "active_min": active_min
            })

        # 4. SORT & SEND
        prepared_players.sort(key=lambda x: x['k'], reverse=True)

        self.dash_controller.signals.update_top_list.emit(prepared_players)
        self.dash_controller.signals.update_db_count.emit(self.db_player_count)


    def switch_server(self, name, new_id):
        """Switches display ID and clears local stats (Thread-Safe)"""
        # THREAD-SAFETY CHECK
        if QThread.currentThread() != QApplication.instance().thread():
            self.worker_signals.request_server_switch.emit(name, str(new_id))
            return

        if str(new_id) == str(self.current_world_id) and getattr(self, "needs_reconnect", False) == False:
            return

        self.add_log(f"SYSTEM: Dashboard filter set to {name} (ID: {new_id}).")

        # Preserve the currently tracked character session so auto world-switch on login
        # does not blank the stats overlay.
        active_char_id = str(getattr(self, "current_character_id", "") or "").strip()
        preserved_active_session = None
        if active_char_id:
            candidate = self.session_stats.get(active_char_id)
            if isinstance(candidate, dict) and len(candidate) > 0:
                preserved_active_session = dict(candidate)

        # 1. Update variables
        self.current_server_name = name
        self.current_world_id = str(new_id)

        # 2. Save config
        self.config["world_id"] = self.current_world_id
        self.save_config()

        # 3. Update label
        if hasattr(self, 'lbl_server_title'):
             # Tkinter .config() removed, using setText for PyQt
             try:
                 self.lbl_server_title.setText(f"{name.upper()} LIVE TELEMETRY ▾")
             except AttributeError:
                 pass # Might be wrong type or already deleted

        # 4. DATA RESET (So new server starts at 0)
        self.pop_history = [0] * 100
        self.session_stats = {}
        if preserved_active_session and active_char_id:
            preserved_active_session["world_id"] = self.current_world_id
            self.session_stats[active_char_id] = preserved_active_session
        self.active_players = {}
        self.live_stats = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0, "Total": 0}

        if hasattr(self, 'main_hub') and self.main_hub.stack.currentIndex() == 0:
            self.update_dashboard_elements()

        # 5. UI SYNC (Now safe in Main Thread)
        if hasattr(self, 'dash_window') and hasattr(self.dash_window, 'server_combo'):
            cb = self.dash_window.server_combo
            cb.blockSignals(True)
            idx = cb.findText(name)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            else:
                # Fallback if name differs slightly
                cb.setCurrentText(name)
            cb.blockSignals(False)

        # Push preserved active stats back into the overlay immediately.
        self.stats_last_refresh_time = 0
        self.update_session_time()
        self.refresh_ingame_overlay()
        self.update_discord_presence()

    def get_server_name_by_id(self, world_id):
        """Searches for the display name of the server based on the World ID"""
        world_id = str(world_id)
        for name, wid in self.server_map.items():
            if str(wid) == world_id:
                return name
        return f"Unknown ({world_id})"

    def save_config(self):
        """
        Saves the configuration to config.json AND config_backup.json.
        """
        try:
            # 1. Get path
            fallback_base = getattr(self, "user_data_dir", get_user_data_dir())
            target_path = getattr(self, 'config_path', os.path.join(fallback_base, "config.json"))
            backup_path = target_path.replace("config.json", "config_backup.json")
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # 2. Clean data (Only serializable data)
            clean_config = {}
            for k, v in self.config.items():
                if isinstance(v, (str, int, float, bool, dict, list, type(None))):
                    clean_config[k] = v

            # 3. Save main file
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(clean_config, f, indent=4)

            # 4. Save backup file (Security copy)
            try:
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(clean_config, f, indent=4)
            except Exception as e:
                print(f"ERR: Backup could not be written: {e}")

            # Optional: Only log if GUI is already running
            if hasattr(self, 'log_area'):
                # Only "System" logs, don't spam on every slider move
                # self.add_log(f"SYS: Config & Backup saved.")
                pass

        except Exception as e:
            if hasattr(self, 'add_log'):
                self.add_log(f"ERR: Critical Save Error: {e}")
            else:
                print(f"ERR: Critical Save Error: {e}")

    def _build_release_updater(self):
        updates_cfg = self.config.get("updates", {})
        repo_raw = str(updates_cfg.get("repo", DEFAULT_UPDATE_REPO)).strip()
        if repo_raw.lower() == LEGACY_UPDATE_REPO.lower():
            repo_raw = DEFAULT_UPDATE_REPO
            try:
                if isinstance(updates_cfg, dict):
                    updates_cfg["repo"] = repo_raw
                    self.config["updates"] = updates_cfg
                    self.save_config()
            except Exception:
                pass
        if "/" not in repo_raw:
            repo_raw = DEFAULT_UPDATE_REPO

        owner, repo = repo_raw.split("/", 1)
        channel = str(updates_cfg.get("channel", "stable")).strip().lower() or "stable"
        token = os.getenv("GITHUB_TOKEN", "")
        user_data_dir = getattr(self, "user_data_dir", get_user_data_dir())

        return ReleaseUpdater(
            owner=owner,
            repo=repo,
            current_version=VERSION,
            user_data_dir=user_data_dir,
            channel=channel,
            token=token,
        )

    def _show_update_download_progress_dialog(self, update_info):
        self._close_update_download_progress_dialog()
        label = "Downloading update package..."
        if update_info and getattr(update_info, "asset", None):
            label = f"Downloading {update_info.asset.name}..."

        dlg = QProgressDialog(label, None, 0, 100, self.main_hub)
        dlg.setWindowTitle("Updating Better Planetside")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        dlg.setCancelButton(None)
        dlg.show()
        self._update_download_progress_dialog = dlg

    def _close_update_download_progress_dialog(self):
        dlg = getattr(self, "_update_download_progress_dialog", None)
        if not dlg:
            return
        try:
            dlg.close()
            dlg.deleteLater()
        except Exception:
            pass
        self._update_download_progress_dialog = None

    def _update_download_progress_qt(self, payload):
        dlg = getattr(self, "_update_download_progress_dialog", None)
        if not dlg:
            return
        if not isinstance(payload, dict):
            return

        phase = str(payload.get("phase", "download")).strip().lower()
        if phase == "verify":
            dlg.setRange(0, 0)
            dlg.setLabelText("Verifying update package integrity...")
            return

        downloaded = int(payload.get("downloaded", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        downloaded_mb = downloaded / (1024.0 * 1024.0)
        if total > 0:
            total_mb = total / (1024.0 * 1024.0)
            percent = max(0, min(100, int((downloaded * 100) / max(total, 1))))
            dlg.setRange(0, 100)
            dlg.setValue(percent)
            dlg.setLabelText(f"Downloading update... {percent}% ({downloaded_mb:.1f} / {total_mb:.1f} MB)")
        else:
            dlg.setRange(0, 0)
            dlg.setLabelText(f"Downloading update... ({downloaded_mb:.1f} MB)")

    def _show_apply_progress_dialog(self, version):
        try:
            if self._update_apply_progress_dialog:
                self._update_apply_progress_dialog.close()
                self._update_apply_progress_dialog.deleteLater()
        except Exception:
            pass
        self._update_apply_progress_dialog = QProgressDialog(
            f"Installing update {version} and restarting...",
            None,
            0,
            0,
            self.main_hub,
        )
        self._update_apply_progress_dialog.setWindowTitle("Updating Better Planetside")
        self._update_apply_progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._update_apply_progress_dialog.setAutoClose(False)
        self._update_apply_progress_dialog.setAutoReset(False)
        self._update_apply_progress_dialog.setCancelButton(None)
        self._update_apply_progress_dialog.show()

    def check_for_updates_qt(self):
        """Manual updater entry point from Settings UI."""
        if not getattr(sys, "frozen", False):
            self.add_log("UPDATE: Update check disabled in development mode.")
            QMessageBox.information(
                self.main_hub,
                "Development Mode",
                "Update checks are disabled when running from source code to prevent overwriting your files."
            )
            return

        if self._update_check_in_progress:
            self.add_log("UPDATE: Check already in progress.")
            return
        if not self.release_updater:
            self.release_updater = self._build_release_updater()

        self._update_check_in_progress = True
        self.add_log("UPDATE: Checking GitHub release manifest...")

        def worker():
            update_info = None
            error = ""
            try:
                update_info = self.release_updater.check_for_update()
            except Exception as e:
                error = str(e)
            self.worker_signals.update_check_finished.emit(update_info, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check_qt(self, update_info, error_msg):
        self._update_check_in_progress = False

        if error_msg:
            self.add_log(f"UPDATE ERROR: {error_msg}")
            QMessageBox.warning(
                self.main_hub,
                "Update Check Failed",
                f"Could not check for updates.\n\n{error_msg}",
            )
            return

        if not update_info:
            self.add_log(f"UPDATE: You are on the latest version ({VERSION}).")
            QMessageBox.information(
                self.main_hub,
                "No Updates",
                f"You are up to date.\nCurrent version: {VERSION}",
            )
            return

        if not getattr(update_info, "has_update", False):
            self.add_log(
                f"UPDATE: Release {update_info.latest_version} found, but no compatible asset for {update_info.platform}."
            )
            QMessageBox.information(
                self.main_hub,
                "Update Not Compatible",
                (
                    f"Found release {update_info.latest_version}, but no compatible package was found for this platform "
                    f"({update_info.platform})."
                ),
            )
            return

        self._latest_update_info = update_info
        asset = update_info.asset
        kind = str(getattr(asset, "kind", "full")).upper() if asset else "UNKNOWN"
        self.add_log(f"UPDATE: Found {update_info.latest_version} ({kind}).")

        ask = QMessageBox.question(
            self.main_hub,
            "Update Available",
            (
                f"New version available: {update_info.latest_version}\n"
                f"Current version: {update_info.current_version}\n"
                f"Package: {asset.name if asset else 'N/A'}\n\n"
                "Download and stage this update now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes:
            self._download_update_asset_qt(update_info)

    def _download_update_asset_qt(self, update_info):
        if self._update_download_in_progress:
            self.add_log("UPDATE: Download already in progress.")
            return
        if not self.release_updater:
            self.release_updater = self._build_release_updater()

        self._update_download_in_progress = True
        self.add_log("UPDATE: Downloading update package...")
        self._show_update_download_progress_dialog(update_info)

        def worker():
            result = None
            error = ""
            try:
                def progress_cb(payload):
                    self.worker_signals.update_download_progress.emit(payload)

                result = self.release_updater.stage_update(update_info, progress_cb=progress_cb)
            except Exception as e:
                error = str(e)
            self.worker_signals.update_download_finished.emit(update_info, result, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_download_qt(self, update_info, result, error_msg):
        self._update_download_in_progress = False
        self._close_update_download_progress_dialog()

        if error_msg:
            self.add_log(f"UPDATE ERROR: {error_msg}")
            QMessageBox.warning(
                self.main_hub,
                "Update Download Failed",
                f"Could not download/stage update.\n\n{error_msg}",
            )
            return

        asset_path = (result or {}).get("asset_path", "")
        pending_path = (result or {}).get("pending_path", "")
        self.add_log(f"UPDATE: Staged {update_info.latest_version} at {asset_path}")
        ask_apply = QMessageBox.question(
            self.main_hub,
            "Update Staged",
            (
                f"Update {update_info.latest_version} downloaded successfully.\n\n"
                f"Package: {asset_path}\n"
                f"Metadata: {pending_path}\n\n"
                "Apply this staged update on restart now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask_apply == QMessageBox.StandardButton.Yes:
            pending_data = self._read_pending_update()
            if pending_data:
                self._start_apply_staged_update_on_restart(pending_data)

    def _get_pending_update_path(self):
        base = getattr(self, "user_data_dir", get_user_data_dir())
        return os.path.join(base, "updates", "pending_update.json")

    def _get_update_success_path(self):
        base = getattr(self, "user_data_dir", get_user_data_dir())
        return os.path.join(base, "updates", "last_update_success.json")

    def _read_update_success_marker(self):
        success_path = self._get_update_success_path()
        if not os.path.exists(success_path):
            return None
        try:
            with open(success_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    def _prompt_update_success_if_available(self):
        success_path = self._get_update_success_path()
        data = self._read_update_success_marker()
        if not data:
            return

        ver = str(data.get("version", "")).strip() or VERSION
        self.add_log(f"UPDATE: Apply completed successfully -> {ver}")
        QMessageBox.information(
            self.main_hub,
            "Update Complete",
            f"Congratulations, update to version {ver} finished.",
        )
        try:
            os.remove(success_path)
        except Exception:
            pass

    def _read_pending_update(self):
        pending_path = self._get_pending_update_path()
        if not os.path.exists(pending_path):
            return None
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            asset = data.get("asset", {})
            local_path = str(asset.get("local_path", "")).strip() if isinstance(asset, dict) else ""
            if not local_path or not os.path.exists(local_path):
                return None
            return data
        except Exception:
            return None

    def _prompt_apply_staged_update_if_available(self):
        if not getattr(sys, "frozen", False):
            return

        pending_data = self._read_pending_update()
        if not pending_data:
            return
        if self._update_check_in_progress or self._update_download_in_progress:
            return

        ver = str(pending_data.get("latest_version", "unknown"))
        ask = QMessageBox.question(
            self.main_hub,
            "Staged Update Found",
            (
                f"A staged update ({ver}) is available.\n\n"
                "Apply it now and restart the app?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes:
            self._start_apply_staged_update_on_restart(pending_data)

    def _get_install_root_and_relaunch(self):
        is_frozen = bool(getattr(sys, "frozen", False))
        if is_frozen:
            # Check for AppImage
            appimage_path = os.environ.get("APPIMAGE")
            if appimage_path and os.path.exists(appimage_path):
                launch_exe = os.path.abspath(appimage_path)
                # For AppImage, we only replace the AppImage file itself
                # So we tell the script the target is the file, and it should handle it.
                return launch_exe, launch_exe, ""

            launch_exe = os.path.abspath(sys.executable)
            launch_arg0 = ""
            
            # Detect if we are in a 'onedir' vs 'onefile' bundle
            # In onefile, sys._MEIPASS is a temp dir. In onedir, it's the app dir.
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                meipass = os.path.abspath(meipass)
                exe_dir = os.path.dirname(launch_exe)
                if meipass == exe_dir:
                    # Generic onedir: replace the whole folder
                    return exe_dir, launch_exe, ""
                else:
                    # Generic onefile: only replace the EXE
                    return launch_exe, launch_exe, ""
            
            # Fallback: assume the directory containing the exe is the install root
            # BUT avoid dangerous roots like home or Desktop
            install_root = os.path.dirname(launch_exe)
            basename = os.path.basename(install_root).lower()
            
            # More robust check for known app directory names
            allowed_names = ("bin", "betterplanetside", "better planetside", "diorclient", "app")
            if basename in allowed_names:
                return install_root, launch_exe, launch_arg0
            
            # Heuristic: If there is an 'assets' folder here, it's very likely our install root
            if os.path.isdir(os.path.join(install_root, "assets")):
                return install_root, launch_exe, launch_arg0
            
            # Default to just replacing the executable if root looks generic
            return launch_exe, launch_exe, launch_arg0

        script_path = os.path.abspath(__file__)
        launch_exe = os.path.abspath(sys.executable)
        launch_arg0 = script_path
        install_root = os.path.dirname(script_path)
        return install_root, launch_exe, launch_arg0

    def _write_windows_apply_script(self, script_path):
        script = r'''param(
    [string]$PidToWait,
    [string]$AssetPath,
    [string]$TargetDir,
    [string]$PendingPath,
    [string]$LaunchExe,
    [string]$LaunchArg0,
    [string]$SuccessPath,
    [string]$UpdatedVersion,
    [string]$StatusPath = "",
    [string]$WaitTimeoutSec = "120"
    )

    $ErrorActionPreference = "Stop"
    $baseDir = Split-Path -Parent $PendingPath
    if (-not $baseDir) { $baseDir = $env:TEMP }
    New-Item -ItemType Directory -Path $baseDir -Force | Out-Null

    $logPath = Join-Path $baseDir "apply_update.log"
    function Write-UpdateLog([string]$msg) {
        try {
            $line = "{0} {1}" -f (Get-Date).ToString("o"), $msg
            Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
        } catch {}
    }
    function Set-UpdateState([string]$phase, [int]$percent, [string]$message, [bool]$done = $false, [string]$error = "") {
        if (-not $StatusPath) { return }
        try {
            $obj = @{
                phase = $phase
                percent = [Math]::Max(0, [Math]::Min(100, $percent))
                message = $message
                done = $done
                error = $error
                timestamp = (Get-Date).ToString("o")
            }
            $json = $obj | ConvertTo-Json -Depth 4
            Set-Content -LiteralPath $StatusPath -Value $json -Encoding UTF8
        } catch {}
    }
    try {
        if ($Host -and $Host.UI -and $Host.UI.RawUI) {
            $Host.UI.RawUI.WindowTitle = "Better Planetside Updater"
        }
    } catch {}
    trap {
        try {
            $errMsg = ""
            if ($PSItem -and $PSItem.Exception) {
                $errMsg = $PSItem.Exception.Message
            } elseif ($_ -and $_.Exception) {
                $errMsg = $_.Exception.Message
            } else {
                $errMsg = "Unhandled PowerShell error in updater script."
            }
            $line = "{0} ERROR: {1}" -f (Get-Date).ToString("o"), $errMsg
            Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
            Set-UpdateState "error" 100 "Update failed." $true $errMsg
        } catch {}
        exit 1
    }

    $timeoutSec = 120
    try {
        $timeoutSec = [Math]::Max(15, [int]$WaitTimeoutSec)
    } catch {}

    Write-UpdateLog ("START asset=" + $AssetPath + " target=" + $TargetDir + " timeout=" + $timeoutSec)
    Set-UpdateState "start" 5 "Starting updater..."

    function Test-IsAdmin {
        try {
            $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
            $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
            return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        } catch {
            return $false
        }
    }

    function Is-ProtectedTarget([string]$path) {
        if (-not $path) { return $false }
        try {
            $full = [System.IO.Path]::GetFullPath($path)
        } catch {
            $full = $path
        }
        $prefixes = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramW6432) | Where-Object { $_ }
        foreach ($prefix in $prefixes) {
            if ($full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
        return $false
    }

    if ((Is-ProtectedTarget $TargetDir) -and (-not (Test-IsAdmin))) {
        Write-UpdateLog "INFO: Target is in Program Files. Relaunching elevated updater."
        Set-UpdateState "elevating" 10 "Requesting administrator permission..."
        try {
            function Quote-Arg([string]$value) {
                if ($null -eq $value) { return '""' }
                $escaped = $value.Replace('"', '`"')
                return '"' + $escaped + '"'
            }

            $argParts = @()
            $argParts += "-NoProfile"
            $argParts += "-NonInteractive"
            $argParts += "-ExecutionPolicy Bypass"
            $argParts += "-File " + (Quote-Arg $PSCommandPath)
            $argParts += "-PidToWait " + (Quote-Arg $PidToWait)
            $argParts += "-AssetPath " + (Quote-Arg $AssetPath)
            $argParts += "-TargetDir " + (Quote-Arg $TargetDir)
            $argParts += "-PendingPath " + (Quote-Arg $PendingPath)
            $argParts += "-LaunchExe " + (Quote-Arg $LaunchExe)
            $argParts += "-SuccessPath " + (Quote-Arg $SuccessPath)
            $argParts += "-UpdatedVersion " + (Quote-Arg $UpdatedVersion)
            $argParts += "-StatusPath " + (Quote-Arg $StatusPath)
            $argParts += "-WaitTimeoutSec " + (Quote-Arg $WaitTimeoutSec)
            if ($LaunchArg0) {
                $argParts += "-LaunchArg0 " + (Quote-Arg $LaunchArg0)
            }
            $argLine = [string]::Join(" ", $argParts)
            Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argLine -WindowStyle Hidden | Out-Null
            Write-UpdateLog "INFO: Elevated updater started."
            exit 0
        } catch {
            Write-UpdateLog ("ERROR: Elevation failed: " + $_.Exception.Message)
            throw
        }
    }

    if ($PidToWait) {
        Set-UpdateState "waiting" 15 "Waiting for app to close..."
        $deadline = (Get-Date).AddSeconds($timeoutSec)
        while (Get-Process -Id ([int]$PidToWait) -ErrorAction SilentlyContinue) {
            if ((Get-Date) -ge $deadline) {
                Write-UpdateLog ("WARN: Timeout waiting for pid " + $PidToWait + ". Forcing stop.")
                try { Stop-Process -Id ([int]$PidToWait) -Force -ErrorAction SilentlyContinue } catch {}
                Start-Sleep -Milliseconds 800
                break
            }
            Start-Sleep -Milliseconds 350
        }
    }

    if (!(Test-Path -LiteralPath $AssetPath)) {
        throw "Asset not found: $AssetPath"
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Set-Location -LiteralPath $baseDir
    $workDir = Join-Path $baseDir ("apply_" + $timestamp)
    $extractDir = Join-Path $workDir "extract"
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

    $assetLower = $AssetPath.ToLowerInvariant()
    Set-UpdateState "extract" 35 "Extracting update package..."
    if ($assetLower.EndsWith(".zip")) {
        Expand-Archive -Path $AssetPath -DestinationPath $extractDir -Force
    } elseif ($assetLower.EndsWith(".exe")) {
        # Asset is the executable itself
        $newFile = Join-Path $extractDir (Split-Path -Leaf $TargetDir)
        Copy-Item -Path $AssetPath -Destination $newFile -Force
    } else {
        throw "Unsupported staged asset format: $AssetPath"
    }

    $entries = Get-ChildItem -Path $extractDir -Force
    $sourceDir = $extractDir
    if (!( $assetLower.EndsWith(".exe") )) {
        if ($entries.Count -eq 1 -and $entries[0].PSIsContainer) {
            $sourceDir = $entries[0].FullName
        }
    }

    # Determine if TARGET_DIR is a file or directory
    if (Test-Path -Path $TargetDir -PathType Leaf) {
        Set-UpdateState "replace" 70 "Replacing application files..."
        # File replacement (onefile)
        $backupFile = "$TargetDir._backup_$timestamp"
        $targetName = Split-Path -Leaf $TargetDir
        $newFile = Join-Path $sourceDir $targetName
        if (!(Test-Path -LiteralPath $newFile)) {
            $match = Get-ChildItem -Path $extractDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq $targetName } | Select-Object -First 1
            if ($match) { $newFile = $match.FullName }
        }
        if (!(Test-Path -LiteralPath $newFile)) {
            throw "Updated file not found in package: $targetName"
        }

        Move-Item -LiteralPath $TargetDir -Destination $backupFile -Force
        try {
            Copy-Item -LiteralPath $newFile -Destination $TargetDir -Force
            if (Test-Path -LiteralPath $PendingPath) { Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue }
            # Success: Clean up backup
            Remove-Item -LiteralPath $backupFile -Force -ErrorAction SilentlyContinue
        } catch {
            if (Test-Path -LiteralPath $TargetDir) { Remove-Item -LiteralPath $TargetDir -Force }
            if (Test-Path -LiteralPath $backupFile) { Move-Item -LiteralPath $backupFile -Destination $TargetDir -Force }
            throw
        }
    } else {
        Set-UpdateState "replace" 70 "Replacing application files..."
        # Directory replacement (onedir)
        $newDir = "$TargetDir._new_$timestamp"
        $backupDir = "$TargetDir._backup_$timestamp"
        New-Item -ItemType Directory -Path $newDir -Force | Out-Null
        Get-ChildItem -Path $sourceDir -Force | ForEach-Object {
            Copy-Item -Path $_.FullName -Destination $newDir -Recurse -Force
        }

        $hadBackup = $false
        if (Test-Path -LiteralPath $TargetDir) {
            Move-Item -LiteralPath $TargetDir -Destination $backupDir -Force
            $hadBackup = $true
        }
        try {
            Move-Item -LiteralPath $newDir -Destination $TargetDir -Force
            if (Test-Path -LiteralPath $PendingPath) { Remove-Item -LiteralPath $PendingPath -Force -ErrorAction SilentlyContinue }
            # Success: Clean up backup
            if ($hadBackup) {
                Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        } catch {
            if (Test-Path -LiteralPath $TargetDir) { Remove-Item -LiteralPath $TargetDir -Recurse -Force }
            if ($hadBackup -and (Test-Path -LiteralPath $backupDir)) {
                Move-Item -LiteralPath $backupDir -Destination $TargetDir -Force
            }
            throw
        }
    }

    # General cleanup
    Set-UpdateState "cleanup" 90 "Cleaning temporary files..."
    if (Test-Path -Path $workDir) { Remove-Item -Path $workDir -Recurse -Force -ErrorAction SilentlyContinue }
    $oneDayAgo = (Get-Date).AddDays(-1)
    Get-ChildItem -Path $baseDir -Filter "apply_*" -Directory | Where-Object { $_.CreationTime -lt $oneDayAgo } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $stagingRoot = Join-Path $baseDir "staging"
    if (Test-Path -Path $stagingRoot) {
        Get-ChildItem -Path $stagingRoot -Force -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if ($SuccessPath) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $SuccessPath) -Force | Out-Null
        $successObj = @{
            version = $UpdatedVersion
            timestamp = (Get-Date).ToString("o")
        }
        $successObj | ConvertTo-Json | Set-Content -Path $SuccessPath -Encoding UTF8
    }

    if ($LaunchExe) {
        Set-UpdateState "restart" 98 "Restarting Better Planetside..."
        if ($LaunchArg0) {
            Start-Process -FilePath $LaunchExe -ArgumentList @($LaunchArg0)
        } else {
            Start-Process -FilePath $LaunchExe
        }
    }
    Set-UpdateState "done" 100 "Update completed." $true ""
    Write-UpdateLog "DONE"
    '''
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

    def _write_windows_progress_ui_script(self, script_path):
        script = r'''param(
    [string]$StatusPath
    )

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Better Planetside Update"
    $form.StartPosition = "CenterScreen"
    $form.Width = 540
    $form.Height = 180
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $label = New-Object System.Windows.Forms.Label
    $label.Left = 20
    $label.Top = 20
    $label.Width = 495
    $label.Height = 24
    $label.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $label.Text = "Preparing update..."
    [void]$form.Controls.Add($label)

    $bar = New-Object System.Windows.Forms.ProgressBar
    $bar.Left = 20
    $bar.Top = 56
    $bar.Width = 495
    $bar.Height = 24
    $bar.Style = "Continuous"
    $bar.Minimum = 0
    $bar.Maximum = 100
    $bar.Value = 0
    [void]$form.Controls.Add($bar)

    $detail = New-Object System.Windows.Forms.Label
    $detail.Left = 20
    $detail.Top = 94
    $detail.Width = 495
    $detail.Height = 40
    $detail.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $detail.ForeColor = [System.Drawing.Color]::FromArgb(200, 200, 200)
    $detail.Text = "Please keep this window open. The app will restart automatically."
    [void]$form.Controls.Add($detail)

    $script:started = Get-Date
    $script:lastMessage = ""
    $script:lastPhase = ""

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 250
    $timer.Add_Tick({
        if ($StatusPath -and (Test-Path -LiteralPath $StatusPath)) {
            try {
                $raw = Get-Content -LiteralPath $StatusPath -Raw -ErrorAction Stop
                if ($raw) {
                    $state = $raw | ConvertFrom-Json
                    $msg = [string]$state.message
                    if (-not $msg) { $msg = "Updating..." }
                    if ($msg -ne $script:lastMessage) {
                        $label.Text = $msg
                        $script:lastMessage = $msg
                    }

                    $pct = -1
                    try { $pct = [int]$state.percent } catch { $pct = -1 }
                    if ($pct -ge 0) {
                        if ($bar.Style -ne "Continuous") { $bar.Style = "Continuous" }
                        $bar.Value = [Math]::Max(0, [Math]::Min(100, $pct))
                    } else {
                        if ($bar.Style -ne "Marquee") { $bar.Style = "Marquee" }
                    }

                    $phase = [string]$state.phase
                    if ($state.error) {
                        $detail.Text = [string]$state.error
                    } elseif ($phase -and $phase -ne $script:lastPhase) {
                        $detail.Text = ("Phase: " + $phase)
                        $script:lastPhase = $phase
                    }

                    if ($state.done -eq $true) {
                        if ($bar.Style -ne "Continuous") { $bar.Style = "Continuous" }
                        $bar.Value = 100
                        Start-Sleep -Milliseconds 650
                        $form.Close()
                    }
                }
            } catch {}
        }

        if (((Get-Date) - $script:started).TotalMinutes -ge 30) {
            $form.Close()
        }
    })

    $form.Add_Shown({
        try { $timer.Start() } catch {}
    })
    $form.Add_FormClosing({
        try { $timer.Stop() } catch {}
    })

    [void]$form.ShowDialog()
'''
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

    def _write_linux_apply_script(self, script_path):
        script = r'''#!/usr/bin/env bash
set -euo pipefail

PID_TO_WAIT="${1:-}"
ASSET_PATH="${2:-}"
TARGET_DIR="${3:-}"
PENDING_PATH="${4:-}"
LAUNCH_EXE="${5:-}"
LAUNCH_ARG0="${6:-}"
SUCCESS_PATH="${7:-}"
UPDATED_VERSION="${8:-}"
WAIT_TIMEOUT_SEC="${9:-120}"

base_dir="$(dirname "$PENDING_PATH")"
if [[ -z "$base_dir" || "$base_dir" == "." ]]; then
  base_dir="/tmp"
fi
mkdir -p "$base_dir" || true
log_path="${base_dir}/apply_update.log"
log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$log_path"
}
on_err() {
  log "ERROR line=$1 cmd=$2"
  exit 1
}
trap 'on_err "$LINENO" "$BASH_COMMAND"' ERR

if ! [[ "$WAIT_TIMEOUT_SEC" =~ ^[0-9]+$ ]]; then
  WAIT_TIMEOUT_SEC=120
fi
if (( WAIT_TIMEOUT_SEC < 15 )); then
  WAIT_TIMEOUT_SEC=15
fi
log "START asset=$ASSET_PATH target=$TARGET_DIR timeout=$WAIT_TIMEOUT_SEC"

if [[ -n "$PID_TO_WAIT" ]]; then
  end_ts=$(( $(date +%s) + WAIT_TIMEOUT_SEC ))
  while kill -0 "$PID_TO_WAIT" 2>/dev/null; do
    if (( $(date +%s) >= end_ts )); then
      log "WARN timeout waiting for pid $PID_TO_WAIT; forcing stop"
      kill "$PID_TO_WAIT" 2>/dev/null || true
      sleep 1
      kill -9 "$PID_TO_WAIT" 2>/dev/null || true
      break
    fi
    sleep 0.35
  done
fi

if [[ ! -f "$ASSET_PATH" ]]; then
  log "ERROR asset not found: $ASSET_PATH"
  exit 2
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
work_dir="${base_dir}/apply_${timestamp}"
extract_dir="${work_dir}/extract"
mkdir -p "$extract_dir"

case "${ASSET_PATH,,}" in
  *.zip)
    if command -v unzip >/dev/null 2>&1; then
      unzip -oq "$ASSET_PATH" -d "$extract_dir"
    else
      log "ERROR unzip required for zip updates"
      exit 3
    fi
    ;;
  *.tar.gz|*.tgz)
    tar -xzf "$ASSET_PATH" -C "$extract_dir"
    ;;
  *.appimage|*.exe)
    # Asset is the executable itself
    cp -a "$ASSET_PATH" "$extract_dir/$(basename "$TARGET_DIR")"
    chmod +x "$extract_dir/$(basename "$TARGET_DIR")"
    ;;
  *)
    log "ERROR unsupported staged asset format: $ASSET_PATH"
    exit 4
    ;;
esac

source_dir="$extract_dir"
if [[ ! "${ASSET_PATH,,}" =~ \.(appimage|exe)$ ]]; then
    shopt -s nullglob dotglob
    entries=("$extract_dir"/*)
    # If there is only one directory, go into it
    if [[ ${#entries[@]} -eq 1 && -d "${entries[0]}" ]]; then
      source_dir="${entries[0]}"
    fi
    # Specialized check: if there is a 'Better Planetside' folder, favor it
    for entry in "${entries[@]}"; do
        if [[ -d "$entry" && "$(basename "$entry")" == "Better Planetside" ]]; then
            source_dir="$entry"
            break
        fi
    done
fi

# Determine if TARGET_DIR is a file or directory
if [[ -f "$TARGET_DIR" ]]; then
    # File replacement (onefile / AppImage)
    backup_file="${TARGET_DIR}._backup_${timestamp}"
    target_name="$(basename "$TARGET_DIR")"
    new_file="$source_dir/$target_name"

    # Safety: if new_file is somehow a directory (e.g. faulty source_dir),
    # look for the binary inside it if it has the same name.
    if [[ -d "$new_file" && -f "$new_file/$target_name" ]]; then
        new_file="$new_file/$target_name"
    fi
    if [[ ! -f "$new_file" ]]; then
        found_file="$(find "$extract_dir" -type f -name "$target_name" | head -n 1 || true)"
        if [[ -n "$found_file" ]]; then
            new_file="$found_file"
        fi
    fi
    if [[ ! -f "$new_file" ]]; then
        log "ERROR new binary not found for target: $target_name"
        exit 7
    fi

    mv "$TARGET_DIR" "$backup_file"
    if cp -a "$new_file" "$TARGET_DIR"; then
        rm -f "$PENDING_PATH" || true
        # Success: clean up this backup immediately
        rm -f "$backup_file" || true
    else
        mv "$backup_file" "$TARGET_DIR"
        exit 6
    fi
else
    # Directory replacement (onedir)
    new_dir="${TARGET_DIR}._new_${timestamp}"
    backup_dir="${TARGET_DIR}._backup_${timestamp}"
    mkdir -p "$new_dir"

    cp -a "$source_dir"/. "$new_dir"/

    had_backup=0
    if [[ -d "$TARGET_DIR" ]]; then
      mv "$TARGET_DIR" "$backup_dir"
      had_backup=1
    fi
    if mv "$new_dir" "$TARGET_DIR"; then
      rm -f "$PENDING_PATH" || true
      if (( had_backup == 1 )); then
        rm -rf "$backup_dir" || true
      fi
    else
      rm -rf "$new_dir" || true
      if (( had_backup == 1 )) && [[ -d "$backup_dir" ]]; then
        mv "$backup_dir" "$TARGET_DIR"
      fi
      exit 5
    fi
fi

# General cleanup of working directories
rm -rf "$work_dir" || true
find "$base_dir" -maxdepth 1 -name "apply_*" -type d -mtime +1 -exec rm -rf {} + || true
if [[ -d "$base_dir/staging" ]]; then
    find "$base_dir/staging" -mindepth 1 -maxdepth 1 -exec rm -rf {} + || true
fi

if [[ -n "$SUCCESS_PATH" ]]; then
    mkdir -p "$(dirname "$SUCCESS_PATH")" || true
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{\n  "version": "%s",\n  "timestamp": "%s"\n}\n' "$UPDATED_VERSION" "$ts" > "$SUCCESS_PATH" || true
fi

if [[ -n "$LAUNCH_EXE" ]]; then
  if [[ -n "$LAUNCH_ARG0" ]]; then
    nohup "$LAUNCH_EXE" "$LAUNCH_ARG0" >/dev/null 2>&1 &
  else
    nohup "$LAUNCH_EXE" >/dev/null 2>&1 &
  fi
fi

log "DONE"
'''
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(script_path, 0o755)

    def _start_apply_staged_update_on_restart(self, pending_data):
        asset = pending_data.get("asset", {}) if isinstance(pending_data, dict) else {}
        asset_path = str(asset.get("local_path", "")).strip() if isinstance(asset, dict) else ""
        pending_path = self._get_pending_update_path()
        success_path = self._get_update_success_path()
        updated_version = str(pending_data.get("latest_version", "")).strip() if isinstance(pending_data, dict) else ""
        if not asset_path or not os.path.exists(asset_path):
            QMessageBox.warning(
                self.main_hub,
                "Staged Update Missing",
                "The staged update package could not be found.",
            )
            return

        install_root, launch_exe, launch_arg0 = self._get_install_root_and_relaunch()
        updates_dir = os.path.join(getattr(self, "user_data_dir", get_user_data_dir()), "updates")
        scripts_dir = os.path.join(updates_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        launcher_log_path = os.path.join(updates_dir, "apply_launcher.log")

        def _write_launcher_log(msg):
            try:
                os.makedirs(updates_dir, exist_ok=True)
                with open(launcher_log_path, "a", encoding="utf-8") as lf:
                    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
                    lf.write(f"{ts} {msg}\n")
            except Exception:
                pass

        updates_cfg = self.config.get("updates", {}) if isinstance(self.config, dict) else {}
        try:
            wait_timeout_sec = int(updates_cfg.get("apply_wait_timeout_sec", 120) or 120)
        except Exception:
            wait_timeout_sec = 120
        wait_timeout_sec = max(15, min(wait_timeout_sec, 1800))
        apply_log_path = os.path.join(updates_dir, "apply_update.log")
        host_log_path = os.path.join(updates_dir, "apply_host.log")
        status_path = os.path.join(updates_dir, "apply_status.json")

        try:
            with open(status_path, "w", encoding="utf-8") as sf:
                json.dump(
                    {
                        "phase": "schedule",
                        "percent": 1,
                        "message": "Preparing updater...",
                        "done": False,
                        "error": "",
                    },
                    sf,
                    indent=2,
                )
        except Exception:
            pass

        _write_launcher_log(
            f"schedule_start asset={asset_path} target={install_root} pending={pending_path} timeout={wait_timeout_sec}"
        )

        try:
            if IS_WINDOWS:
                script_path = os.path.join(scripts_dir, "apply_update.ps1")
                self._write_windows_apply_script(script_path)
                powershell_exe = os.path.join(
                    os.environ.get("SystemRoot", r"C:\Windows"),
                    "System32",
                    "WindowsPowerShell",
                    "v1.0",
                    "powershell.exe",
                )
                if not os.path.exists(powershell_exe):
                    powershell_exe = "powershell.exe"
                progress_script_path = os.path.join(scripts_dir, "apply_progress_ui.ps1")
                self._write_windows_progress_ui_script(progress_script_path)
                ui_cmd = [
                    powershell_exe,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-STA",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    progress_script_path,
                    status_path,
                ]
                try:
                    subprocess.Popen(
                        ui_cmd,
                        creationflags=0x08000000,
                        cwd=scripts_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    _write_launcher_log(f"schedule_ui script={progress_script_path}")
                except Exception as ui_e:
                    _write_launcher_log(f"schedule_ui_error {ui_e}")
                cmd = [
                    powershell_exe,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                    str(os.getpid()),
                    asset_path,
                    install_root,
                    pending_path,
                    launch_exe,
                    launch_arg0,
                    success_path,
                    updated_version,
                    status_path,
                    str(wait_timeout_sec),
                ]
                # CREATE_NO_WINDOW keeps the updater headless; UI feedback is shown in-app.
                creation_flags = 0x08000000
                host_log_file = open(host_log_path, "ab")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        creationflags=creation_flags,
                        cwd=scripts_dir,
                        stdout=host_log_file,
                        stderr=host_log_file,
                    )
                finally:
                    host_log_file.close()
                time.sleep(0.6)
                early_rc = proc.poll()
                _write_launcher_log(f"schedule_probe pid={getattr(proc, 'pid', '')} rc={early_rc}")
            else:
                script_path = os.path.join(scripts_dir, "apply_update.sh")
                self._write_linux_apply_script(script_path)
                cmd = [
                    "/bin/bash",
                    script_path,
                    str(os.getpid()),
                    asset_path,
                    install_root,
                    pending_path,
                    launch_exe,
                    launch_arg0,
                    success_path,
                    updated_version,
                    str(wait_timeout_sec),
                ]
                host_log_file = open(host_log_path, "ab")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        start_new_session=True,
                        stdout=host_log_file,
                        stderr=host_log_file,
                    )
                finally:
                    host_log_file.close()
            _write_launcher_log(f"schedule_ok pid={getattr(proc, 'pid', '')} script={script_path} cmd={cmd}")
        except Exception as e:
            _write_launcher_log(f"schedule_error {e}")
            self.add_log(f"UPDATE ERROR: Failed to schedule apply-on-restart: {e}")
            QMessageBox.warning(
                self.main_hub,
                "Update Apply Failed",
                f"Could not schedule apply-on-restart.\n\n{e}",
            )
            return

        self.add_log(f"UPDATE: External updater script: {script_path}")
        self.add_log(f"UPDATE: External updater UI script: {os.path.join(scripts_dir, 'apply_progress_ui.ps1')}")
        self.add_log(f"UPDATE: Apply log path: {apply_log_path}")
        self.add_log(f"UPDATE: Host log path: {host_log_path}")
        self.add_log(f"UPDATE: Status path: {status_path}")
        self._show_apply_progress_dialog(updated_version)
        self.add_log("UPDATE: Applying update in background...")
        self.add_log("UPDATE: Apply-on-restart scheduled. Closing now...")
        QTimer.singleShot(700, self.qt_app.quit)

    def create_overlay_window(self):
        if self.overlay_win:
            self.overlay_win.show()
            self.overlay_win.raise_()
            self.overlay_running = True
            self.overlay_enabled = True
            self.add_log("Overlay: activated.")


    def trigger_overlay_event(self, event_type):
        """
        Triggers image/sound in the overlay.
        Now called finished and ready by CensusWorker (including milestones).
        """
        if not hasattr(self, 'overlay_win') or not self.overlay_win:
            return

        # During isolated tests, events should only render in dedicated event test mode.
        isolated_non_event_test = (
            getattr(self, "is_stats_test", False)
            or getattr(self, "is_feed_test", False)
            or getattr(self, "is_streak_test", False)
            or getattr(self, "is_crosshair_test", False)
        )
        if isolated_non_event_test:
            return

        # 1. SEARCH CONFIG DATA
        events_dict = self.config.get("events", {})
        event_data = events_dict.get(event_type)

        # Fallback (Case-Insensitive)
        if not event_data:
            for key, val in events_dict.items():
                if key.lower() == event_type.lower():
                    event_data = val
                    break

        if not event_data:
            return

        # 2. LOAD PARAMETERS
        try:
            abs_x = int(event_data.get("x", 0))
            abs_y = int(event_data.get("y", 0))
            scale = float(event_data.get("scale", 1.0))
            volume = float(event_data.get("volume", 1.0))
        except (ValueError, TypeError):
            abs_x, abs_y, scale, volume = 0, 0, 1.0, 1.0

        # 3. DURATION LOGIC
        queue_active = self.config.get("event_queue_active", True)
        global_dur = int(self.config.get("event_global_duration", 3000))
        specific_dur = int(event_data.get("duration", 0))

        if not queue_active:
            dur = global_dur
        else:
            dur = specific_dur if specific_dur > 0 else global_dur

        if event_type.lower() in ["hitmarker", "headshot hitmarker"]:
            dur = specific_dur

        # 4. DETERMINE PATHS
        img_path = ""
        img_name = event_data.get("img")
        
        # If list -> Random Pick
        if isinstance(img_name, list) and len(img_name) > 0:
            img_name = random.choice(img_name)
        elif isinstance(img_name, list) and len(img_name) == 0:
            img_name = ""
            
        if img_name:
            path_candidate = get_asset_path(img_name)
            if os.path.exists(path_candidate):
                img_path = path_candidate
            elif os.path.exists(img_name):
                img_path = img_name

        sound_path = ""
        if globals().get("HAS_SOUND", True):
            snd_name = event_data.get("snd")
            
            # If list -> Random Pick
            if isinstance(snd_name, list) and len(snd_name) > 0:
                snd_name = random.choice(snd_name)
            elif isinstance(snd_name, list) and len(snd_name) == 0:
                snd_name = ""
                
            if snd_name:
                path_candidate = get_asset_path(snd_name)
                if os.path.exists(path_candidate):
                    sound_path = path_candidate
                elif os.path.exists(snd_name):
                    sound_path = snd_name

        # 5. TRIGGER
        is_hitmarker = (event_type.lower() in ["hitmarker", "headshot hitmarker"])
        play_duplicate = event_data.get("play_duplicate", True)

        if img_path or sound_path:
            self.overlay_win.signals.show_image.emit(
                img_path, sound_path, dur, abs_x, abs_y, scale, volume, is_hitmarker, play_duplicate, event_type
            )

    def start_fade_out(self, tag):
        """Makes a canvas object disappear after a delay (without movement)"""
        if not hasattr(self, 'ovl_canvas'): return

        # Check if item exists
        items = self.ovl_canvas.find_withtag(tag)
        if not items: return

        # We first make the item invisible (state 'hidden')
        # This is more performant than immediate deletion if processes are still accessing it
        self.ovl_canvas.itemconfig(tag, state='hidden')

        # After a short safety delay we delete it finally from memory
        self.root.after(100, lambda: self.cleanup_item(tag))

    def cleanup_item(self, tag):
        """Final deletion from Canvas and memory"""
        self.ovl_canvas.delete(tag)
        # Delete reference from dictionary so RAM doesn't fill up
        if hasattr(self, 'active_event_photos') and tag in self.active_event_photos:
            del self.active_event_photos[tag]

    def toggle_event_queue_qt(self):
        """Toggles the queue system on or off (PyQt6 port)."""
        # 1. Get current status from config (Source of Truth)
        current_state = self.config.get("event_queue_active", True)
        new_state = not current_state

        # 2. Save
        self.config["event_queue_active"] = new_state
        self.save_config()

        # 3. Update GUI (Access to Overlay-Config window)
        ui = self.ovl_config_win

        # Sync button status
        ui.btn_queue_toggle.setChecked(new_state)

        if new_state:
            ui.btn_queue_toggle.setText("QUEUE: ON")
            ui.btn_queue_toggle.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; padding: 10px; outline: none; border: 1px solid #006600; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
                "QPushButton:focus { border: 1px solid #006600; }"
            )
            self.add_log("SYS: Event Queue ENABLED (Sequential Playback)")
        else:
            ui.btn_queue_toggle.setText("QUEUE: OFF")
            ui.btn_queue_toggle.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; padding: 10px; outline: none; border: 1px solid #660000; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
                "QPushButton:focus { border: 1px solid #660000; }"
            )
            self.add_log("SYS: Event Queue DISABLED (Instant Overwrite)")

        # 4. Inform overlay (IMPORTANT!)
        if self.overlay_win:
            # Set variable in overlay
            self.overlay_win.queue_enabled = new_state

            # If turned off, clear queue immediately
            if not new_state:
                if hasattr(self.overlay_win, 'clear_queue_now'):
                    self.overlay_win.clear_queue_now()
                else:
                    # Fallback if the method in QtOverlay has a different name
                    # (Deletes the internal list of events)
                    if hasattr(self.overlay_win, 'event_queue'):
                        self.overlay_win.event_queue.clear()

    def browse_file_qt(self, widget, type_):
        # ADDED *.gif HERE:
        ft = "Images (*.png *.jpg *.jpeg *.gif)" if type_ == "png" else "Audio (*.mp3 *.wav *.ogg)"
        
        # Decide start directory based on type
        start_dir = IMAGES_DIR if type_ == "png" else SOUNDS_DIR
        
        # Fallback to BASE_DIR if directory doesn't exist
        if not os.path.exists(start_dir):
            start_dir = self.BASE_DIR

        from PyQt6.QtWidgets import QFileDialog, QComboBox
        # Use self.main_hub as parent so the window is centered
        file_path, _ = QFileDialog.getOpenFileName(self.main_hub, "Select File", start_dir, ft)

        if file_path:
            filename = os.path.basename(file_path)
            target_path = get_asset_path(filename)

            try:
                # Copy file to assets if it comes from somewhere else
                if os.path.abspath(file_path) != os.path.abspath(target_path):
                    shutil.copy2(file_path, target_path)
            except Exception as e:
                self.add_log(f"ERR: Copy Error: {e}")

            # Set text field or ComboBox
            if isinstance(widget, QComboBox):
                # Prevent duplicates
                found = False
                for i in range(widget.count()):
                    if widget.itemText(i) == filename:
                        widget.setCurrentIndex(i)
                        found = True
                        break
                
                if not found:
                    widget.addItem(filename)
                    widget.setCurrentIndex(widget.count() - 1)
            else:
                widget.setText(filename)

            # AUTO SAVE
            if widget == self.ovl_config_win.combo_twitch_silence_snd:
                self.save_twitch_config()
            else:
                self.save_event_config_from_qt()

    def save_event_ui_data(self):
        """Saves the event, even if fields are empty (Reset)."""
        ui = self.ovl_config_win

        # Which event are we editing right now?
        etype = ui.lbl_editing.text().replace("EDITING: ", "").strip()
        if etype == "NONE" or not etype:
            return

        if "events" not in self.config: self.config["events"] = {}
        existing_data = self.config["events"].get(etype, {})

        # Keep coordinates (from overlay or config)
        if self.overlay_win and getattr(self.overlay_win, 'event_preview_label',
                                        None) and self.overlay_win.event_preview_label.isVisible():
            pos = self.overlay_win.event_preview_label.pos()
            save_x = int(pos.x() / self.overlay_win.ui_scale)
            save_y = int(pos.y() / self.overlay_win.ui_scale)
        else:
            save_x = existing_data.get("x", 100)
            save_y = existing_data.get("y", 100)

        # Read data (with cleaning)
        def clean_txt(t):
            t = t.strip()
            if not t or "No file selected" in t: return ""
            return t

        # 1. Image Data
        img_items = []
        # Add all items from list
        for i in range(ui.combo_evt_img.count()):
            txt = clean_txt(ui.combo_evt_img.itemText(i))
            if txt and txt not in img_items:
                img_items.append(txt)
        
        # Add current text if manually typed and not in list
        curr_img = clean_txt(ui.combo_evt_img.currentText())
        if curr_img and curr_img not in img_items:
            img_items.append(curr_img)
            
        if not img_items: img_val = ""
        elif len(img_items) == 1: img_val = img_items[0]
        else: img_val = img_items
            
        # 2. Sound Data
        snd_items = []
        for i in range(ui.combo_evt_snd.count()):
            txt = clean_txt(ui.combo_evt_snd.itemText(i))
            if txt and txt not in snd_items:
                snd_items.append(txt)
        
        # Add current text if manually typed
        curr_snd = clean_txt(ui.combo_evt_snd.currentText())
        if curr_snd and curr_snd not in snd_items:
            snd_items.append(curr_snd)

        if not snd_items: snd_val = ""
        elif len(snd_items) == 1: snd_val = snd_items[0]
        else: snd_val = snd_items

        # Ensure duration
        try:
            dur_val = int(ui.ent_evt_duration.text())
        except ValueError:
            dur_val = 3000

        # Update (We overwrite everything, even if empty -> this is how you delete)
        self.config["events"][etype] = {
            "img": img_val,
            "snd": snd_val,
            "scale": ui.slider_evt_scale.value() / 100.0,
            "volume": ui.slider_evt_vol.value() / 100.0,
            "duration": dur_val,
            "x": save_x,
            "y": save_y,
            "play_duplicate": ui.check_play_duplicate.isChecked(),
            "impact": ui.check_evt_impact.isChecked() if hasattr(ui, "check_evt_impact") else False
        }

        self.save_config()

        # Sync to active slot
        import copy
        active_slot = self.config.get("active_event_slot", "")
        if active_slot and "event_slots" in self.config:
            self.config["event_slots"][active_slot] = copy.deepcopy(self.config["events"])

        self.add_log(f"UI: Event '{etype}' saved (Img: '{img_val}').")





    def hide_overlay_temporary(self, clear_feed=False):
        """Hides all overlay elements; optionally clears killfeed for hard resets."""
        if not self.overlay_win: return

        # 1. Stats Widget
        if hasattr(self.overlay_win, 'stats_bg_label'):
            self.overlay_win.stats_bg_label.hide()
            self.overlay_win.stats_text_label.hide()
            if hasattr(self.overlay_win, 'clear_stats_web'):
                self.overlay_win.clear_stats_web()

        # 2. Killfeed
        if hasattr(self.overlay_win, 'feed_label'):
            self.overlay_win.feed_label.hide()
        if clear_feed and hasattr(self.overlay_win, 'clear_killfeed'):
            self.overlay_win.clear_killfeed()

        # 3. Killstreak
        if hasattr(self.overlay_win, 'streak_bg_label'):
            self.overlay_win.streak_bg_label.hide()
        if hasattr(self.overlay_win, 'streak_text_label'):
            self.overlay_win.streak_text_label.hide()
        if hasattr(self.overlay_win, 'clear_streak_web'):
            self.overlay_win.clear_streak_web()
        if hasattr(self.overlay_win, 'knife_labels'):
            for l in self.overlay_win.knife_labels:
                l.hide()

        # 4. Crosshair
        if hasattr(self.overlay_win, 'crosshair_label'):
            self.overlay_win.crosshair_label.hide()
        self._set_crosshair_recoil_level(0.0)
        if hasattr(self.overlay_win, 'clear_crosshair_web'):
            self.overlay_win.clear_crosshair_web()
        
        # 5. Events / Effects
        if hasattr(self.overlay_win, 'hide_all_events'):
            self.overlay_win.hide_all_events()
        
        # 6. Hitmarker (Qt specific part if any)
        if hasattr(self.overlay_win, 'hitmarker_label'):
            self.overlay_win.hitmarker_label.hide()

    def stop_overlay_logic(self):
        """Hides all overlay elements and RESETS all data/counters (e.g. at game exit)"""

        # Hide everything first
        self.hide_overlay_temporary(clear_feed=True)
        self._set_crosshair_recoil_level(0.0)

        # Then clear killfeed text (hard reset)
        if self.overlay_win and hasattr(self.overlay_win, 'feed_label'):
            self.overlay_win.feed_label.setText("")

        # Reset counters
        self.killstreak_count = 0
        self.kill_counter = 0
        self.streak_factions = []
        self.streak_slot_map = []

        # Reset knife status in overlay
        if self.overlay_win and hasattr(self.overlay_win, 'knife_labels'):
            for l in self.overlay_win.knife_labels:
                l._is_active = False

        # IMPORTANT: Inform the overlay about the new state (0)
        self.update_streak_display()

        # 4. Update status in GUI
        if hasattr(self, 'ovl_status_label'):
            try:
                self.ovl_status_label.config(text="STATUS: STANDBY", fg="#7a8a9a")
            except:
                pass

    def _crosshair_context_allows_recoil(self):
        """True when crosshair recoil animation is allowed to react to mouse input."""
        if not self.overlay_win:
            return False

        if getattr(self, "is_hud_editing", False):
            return False

        cross_conf_raw = self.config.get("crosshair", {})
        cross_conf = cross_conf_raw if isinstance(cross_conf_raw, dict) else {}
        if not cross_conf.get("active", True):
            return False
        if not cross_conf.get("ads_fire_expand", True):
            return False

        event_test_active = getattr(self, "is_event_test", False)
        stats_test_active = getattr(self, "is_stats_test", False)
        feed_test_active = getattr(self, "is_feed_test", False)
        streak_test_active = getattr(self, "is_streak_test", False)
        crosshair_test_active = getattr(self, "is_crosshair_test", False)
        any_test_active = (
            event_test_active
            or stats_test_active
            or feed_test_active
            or streak_test_active
            or crosshair_test_active
        )

        if any_test_active and not crosshair_test_active:
            return False

        if crosshair_test_active:
            return True

        if bool(getattr(self, "debug_overlay_active", False)):
            return True

        if not self.config.get("overlay_master_active", True):
            return False
        if not bool(getattr(self, "ps2_running", False)):
            return False

        return self.is_game_focused()

    def _set_crosshair_recoil_level(self, level):
        level = max(0.0, min(1.0, float(level)))
        if abs(level - float(getattr(self, "_crosshair_recoil_level", 0.0))) < 0.003:
            return

        self._crosshair_recoil_level = level
        if self.overlay_win and hasattr(self.overlay_win, "set_crosshair_recoil_level"):
            self.overlay_win.set_crosshair_recoil_level(level)

    def poll_crosshair_recoil_input(self):
        """Polls LMB hold duration and updates crosshair recoil level (0..1)."""
        if not self._crosshair_recoil_supported:
            self._crosshair_lmb_hold_started = None
            self._crosshair_rmb_primed = False
            self._set_crosshair_recoil_level(0.0)
            return

        recoil_level = 0.0
        if self._crosshair_context_allows_recoil():
            try:
                user32 = ctypes.windll.user32
                lmb_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
                rmb_down = bool(user32.GetAsyncKeyState(0x02) & 0x8000)

                # Gate by input order:
                # 1) Hold RMB first (prime), 2) then press/hold LMB to grow recoil.
                if not rmb_down:
                    self._crosshair_rmb_primed = False
                    self._crosshair_lmb_hold_started = None
                elif not lmb_down:
                    self._crosshair_rmb_primed = True
                    self._crosshair_lmb_hold_started = None
                else:
                    if self._crosshair_rmb_primed:
                        now = time.time()
                        if self._crosshair_lmb_hold_started is None:
                            self._crosshair_lmb_hold_started = now
                        held_s = max(0.0, now - self._crosshair_lmb_hold_started)
                        recoil_level = min(1.0, held_s / 1.0)
                    else:
                        self._crosshair_lmb_hold_started = None
                        recoil_level = 0.0
            except Exception:
                self._crosshair_lmb_hold_started = None
                self._crosshair_rmb_primed = False
                recoil_level = 0.0
        else:
            self._crosshair_lmb_hold_started = None
            self._crosshair_rmb_primed = False

        self._set_crosshair_recoil_level(recoil_level)

    def refresh_ingame_overlay(self):
        """The heartbeat of the overlay: controls visibility with priority for test/edit."""
        if not self.overlay_win: return

        # Keep loop alive
        QTimer.singleShot(500, self.refresh_ingame_overlay)

        # 1. Status variables
        master_switch = self.config.get("overlay_master_active", True)
        game_running = getattr(self, 'ps2_running', False)

        # --- FIX: SEPARATE TEST MODES ---
        event_test_active = getattr(self, 'is_event_test', False)
        stats_test_active = getattr(self, 'is_stats_test', False)
        feed_test_active = getattr(self, 'is_feed_test', False)
        streak_test_active = getattr(self, 'is_streak_test', False)
        crosshair_test_active = getattr(self, 'is_crosshair_test', False)
        any_test_active = (
            event_test_active
            or stats_test_active
            or feed_test_active
            or streak_test_active
            or crosshair_test_active
        )

        edit_active = getattr(self, 'is_hud_editing', False)
        debug_active = bool(getattr(self, "debug_overlay_active", False))
        game_focused = self.is_game_focused()

        # Detect debug overlay edge transitions for first-frame initialization.
        prev_debug_active = bool(getattr(self, "_last_debug_overlay_active", False))
        debug_just_enabled = debug_active and not prev_debug_active
        self._last_debug_overlay_active = debug_active

        # --- NEW: Detect focus change for automatic refresh ---
        was_focused = getattr(self, "_last_focus_state", True)
        self._last_focus_state = game_focused
        focus_regained = game_focused and not was_focused
        focus_lost = not game_focused and was_focused

        # ---------------------------------------------------------
        # DECISION: Master Visibility (Priority Chain)
        # ---------------------------------------------------------
        path_recording = bool(self.overlay_win and getattr(self.overlay_win, "path_edit_active", False))
        should_render = False
        mode_gameplay = False  # Separation between "Allowed to render" and "Game is actually running"

        # Render if any test or edit is running
        if edit_active or any_test_active or path_recording:
            should_render = True
        elif debug_active:
            should_render = True
            mode_gameplay = True
        elif master_switch and game_running and game_focused:
            should_render = True
            mode_gameplay = True

        # Linux Fix: On Wayland/Linux, we need to periodically raise the window
        if should_render and not IS_WINDOWS and self.overlay_win:
            self.overlay_win.raise_()
        if self.overlay_win and hasattr(self.overlay_win, "set_web_overlay_visibility"):
            self.overlay_win.set_web_overlay_visibility(should_render)

        # ELEMENT CONTROL
        # ---------------------------------------------------------
        if should_render:
            # If we just regained focus: Refresh positions
            if focus_regained:
                if self.overlay_win:
                    # FIX: If we are in game, edit boxes must go!
                    if edit_active:
                        self.overlay_win.set_mouse_passthrough(True)
                    self.overlay_win.update_killfeed_pos()
                self.update_streak_display()

            # If we are in edit mode and LOSE focus (back to client), turn edit back on
            if focus_lost and edit_active:
                if self.overlay_win:
                    self.overlay_win.set_mouse_passthrough(False, active_targets=getattr(self, "current_edit_targets", []))
            if any_test_active and not event_test_active and hasattr(self.overlay_win, "hide_all_events"):
                self.overlay_win.hide_all_events()
            # === A) STATS WIDGET ===
            stats_cfg_raw = self.config.get("stats_widget", {})
            stats_cfg = stats_cfg_raw if isinstance(stats_cfg_raw, dict) else {}
            stats_editing = edit_active and ("stats" in getattr(self, "current_edit_targets", []))

            if any_test_active:
                show_stats = stats_test_active
            else:
                show_stats = (stats_cfg.get("active", True) and mode_gameplay) or stats_editing or debug_active

            if show_stats:
                # THROTTLE LOGIC: Only update once per second, except in Edit/Test mode
                now = time.time()
                should_update_stats = True

                # Keep stats static while moving in edit mode to avoid visual flicker.
                if stats_editing:
                    should_update_stats = False
                
                if mode_gameplay and not (stats_editing or stats_test_active or debug_active):
                    if (now - self.stats_last_refresh_time) < 1.0:
                        should_update_stats = False
                
                if should_update_stats:
                    if debug_just_enabled:
                        self.stats_last_refresh_time = 0
                    self.stats_last_refresh_time = now
                    stats_obj, is_dummy = self._resolve_overlay_stats_payload(
                        force_placeholder=stats_test_active
                    )
                    self.overlay_win.update_stats_display(stats_obj, is_dummy=is_dummy)
                    
                    self.overlay_win.stats_bg_label.show()
                    self.overlay_win.stats_text_label.show()
                    self.update_stats_position_safe()
            else:
                self.overlay_win.stats_bg_label.hide()
                self.overlay_win.stats_text_label.hide()
                if hasattr(self.overlay_win, "clear_stats_web"):
                    self.overlay_win.clear_stats_web()

            # === B) CROSSHAIR ===
            cross_conf = self.config.get("crosshair", {})
            cross_editing = edit_active and ("crosshair" in getattr(self, "current_edit_targets", []))
            ch_file = clean_path(cross_conf.get("file", "crosshair.png"))
            if not ch_file:
                ch_file = "crosshair.png"
            ch_path = get_asset_path(ch_file)
            ch_size = int(cross_conf.get("size", 32))

            if any_test_active:
                should_show_crosshair = crosshair_test_active
            else:
                should_show_crosshair = (cross_conf.get("active", True) and mode_gameplay) or cross_editing
            self.overlay_win.update_crosshair(ch_path, ch_size, should_show_crosshair)

            # === C) KILLFEED ===
            feed_conf = self.config.get("killfeed", {})
            feed_editing = edit_active and ("feed" in getattr(self, "current_edit_targets", []))

            if any_test_active:
                show_feed = feed_test_active
            else:
                show_feed = (feed_conf.get("active", True) and mode_gameplay) or feed_editing

            if show_feed:
                self.overlay_win.feed_label.show()
            else:
                self.overlay_win.feed_label.hide()

            # === D) KILLSTREAK ===
            streak_conf = self.config.get("streak", {})
            streak_editing = edit_active and ("streak" in getattr(self, "current_edit_targets", []))

            if any_test_active:
                show_streak_section = streak_test_active
            else:
                show_streak_section = (streak_conf.get("active", True) and mode_gameplay) or streak_editing or path_recording

            if show_streak_section:
                
                # FIX: Only show if we are alive! (is_dead check added)
                # Exception: Edit mode or streak test
                # FIX: Only show if we are alive AND logged in!
                show_condition = (self.killstreak_count > 0 and not getattr(self, "is_dead", False) and self.current_character_id)
                
                if show_condition or streak_editing or streak_test_active or path_recording:
                    # Qt streak widgets are preview-only now; runtime streak is rendered by web HUD.
                    if streak_editing or path_recording:
                        self.overlay_win.streak_bg_label.show()
                        self.overlay_win.streak_text_label.show()
                        for k in self.overlay_win.knife_labels:
                            if getattr(k, '_is_active', False) or streak_editing:
                                k.show()
                    else:
                        self.overlay_win.streak_bg_label.hide()
                        self.overlay_win.streak_text_label.hide()
                        for k in self.overlay_win.knife_labels:
                            k.hide()
                else:
                    self.overlay_win.streak_bg_label.hide()
                    self.overlay_win.streak_text_label.hide()
                    for k in self.overlay_win.knife_labels: k.hide()
                    self.hide_streak_display()
            else:
                self.overlay_win.streak_bg_label.hide()
                self.overlay_win.streak_text_label.hide()
                for k in self.overlay_win.knife_labels: k.hide()
                self.hide_streak_display()

        else:
            # HIDE ALL (Game off / no focus / no test)
            if not game_running or not master_switch:
                self.stop_overlay_logic()
            else:
                # Only hide temporarily (e.g. Alt-Tab), but keep data
                self.hide_overlay_temporary()





    def trigger_auto_voice(self, trigger_key):
        """Presses V + number based on config"""
        if not self.is_game_focused():
            return
        # 1. Check config
        cfg = self.config.get("auto_voice", {})
        
        # Master Switch Check
        if not cfg.get("active", True):
            return

        val = cfg.get(trigger_key, "OFF")

        if val == "OFF": return

        # 2. Check cooldown (so it doesn't spam, e.g. on multi-kills)
        now = time.time()
        last = getattr(self, "last_voice_time", 0)
        if now - last < 2.5:  # 2.5 seconds pause between callouts
            return

        self.last_voice_time = now

        # 3. Simulate key press (Thread so mainloop doesn't hang)
        def press():
            try:
                if IS_WINDOWS:
                    if not pydirectinput:
                        print("Voice Error: pydirectinput is unavailable on this platform.")
                        return
                    # Press V
                    pydirectinput.press('v')
                    time.sleep(0.05)  # Short pause for the menu
                    # Press number
                    pydirectinput.press(val)
                else:
                    if not XDO_TOOL:
                        print("Voice Error: xdotool is not installed (required on Linux for voice macros).")
                        return

                    subprocess.run([XDO_TOOL, "key", "v"], check=False)
                    time.sleep(0.05)
                    subprocess.run([XDO_TOOL, "key", str(val)], check=False)

                # Log for debug
                print(f"DEBUG: Auto-Voice V-{val} triggered by {trigger_key}")
            except Exception as e:
                print(f"Voice Error: {e}")

        threading.Thread(target=press, daemon=True).start()

    def test_stats_visuals(self):
        """Starts a preview (Anti-Ghosting Test with new layout) - PyQt6 Fixed"""
        if not self.overlay_win:
            self.add_log("WARN: Overlay system is not active! Please start first.")
            return

        self.add_log("UI: Starting visual test (Layout Check)...")
        self._set_overlay_test_mode("stats")

        # Force immediate update of stats bar (KD, KPM etc.)
        self.refresh_ingame_overlay()

        # Fire test events sequentially (Stats only)
        # Note: Killfeed dummy entries removed here to decouple tests.
        
        # --- AUTO-CLEAR AND CLEANUP ---
        def end_test():
            if self.is_stats_test:
                self._set_overlay_test_mode(None)
            if self.overlay_win:
                self.overlay_win.signals.clear_feed.emit()
                # Set stats back to real values (or 0)
                self.refresh_ingame_overlay()
            self.add_log("UI: Test finished & feed cleaned.")

        # Cleanup after 6 seconds
        QTimer.singleShot(6000, end_test)

    def get_current_tab_targets(self):
        """Safely determines which tab is currently open."""
        try:
            ui = self.ovl_config_win
            idx = ui.tabs.currentIndex()
            # .strip() removes spaces at beginning/end
            tab_text = ui.tabs.tabText(idx).strip().upper()

            print(f"DEBUG: Current Tab Index: {idx}, Text: '{tab_text}'")  # Debug Log

            if "CROSSHAIR" in tab_text:
                targets = ["crosshair"]
            elif "STATS" in tab_text:
                targets = ["stats"]
            elif "KILLFEED" in tab_text:
                targets = ["feed"]
            elif "KILLSTREAK" in tab_text:
                targets = ["streak"]
            elif "EVENTS" in tab_text:
                targets = ["event"]
            elif "TWITCH" in tab_text:
                targets = ["twitch"]

            return targets
        except Exception as e:
            print(f"DEBUG: Tab Error: {e}")
            return []

    def toggle_hud_edit_mode(self):
        """
        Starts edit mode, shows borders, fills dummy data
        and enables Drag & Drop.
        """
        if not self.overlay_win:
            self.add_log("ERR: Overlay is not running! Please start overlay first.")
            # Try to start it if master switch is on
            if self.config.get("overlay_master_active", True):
                self.create_overlay_window()
            if not self.overlay_win: return

        # Toggle status
        self.is_hud_editing = not getattr(self, "is_hud_editing", False)
        is_editing = self.is_hud_editing

        ui = self.ovl_config_win
        targets = self.get_current_tab_targets()
        self.current_edit_targets = targets # Store targets for visibility logic

        if not targets:
            self.add_log("INFO: Please select a tab first.")
            self.is_hud_editing = False
            return

        # Buttons for coloring
        btn_list = [ui.btn_edit_hud, ui.btn_edit_cross, ui.btn_edit_streak, ui.btn_edit_hud_stats, ui.btn_edit_hud_feed, ui.btn_edit_twitch]

        if is_editing:
            # --- START EDIT (On) ---

            # 1. Make overlay clickable
            self.overlay_win.set_mouse_passthrough(False, active_targets=targets)

            # FORCE config window to top so "Stop Edit" button can always be clicked!
            # We do this AFTER overlay handle was recreated
            self.ovl_config_win.raise_()
            self.ovl_config_win.activateWindow()

            # 2. Color buttons red
            for btn in btn_list:
                btn.setText("STOP EDIT (SAVE)")
                btn.setStyleSheet(
                    "background-color: #ff0000; color: white; border: 1px solid #cc0000; font-weight: bold;")

            # 3. LOAD DUMMY DATA (So you see something!)

            # A) STATS WIDGET (KD display)
            if "stats" in targets:
                # Keep stats source identical to normal/debug mode:
                # real stats if available, otherwise shared placeholder.
                stats_obj, is_dummy = self._resolve_overlay_stats_payload()
                self.overlay_win.update_stats_display(stats_obj, is_dummy=is_dummy)

                self.overlay_win.stats_bg_label.show()

                # Keep drag frame close to actual stats footprint for consistent edge behavior.
                w = int(450 * self.overlay_win.ui_scale)
                h = int(60 * self.overlay_win.ui_scale)
                self.overlay_win.stats_bg_label.setFixedSize(w, h)
                self.update_stats_position_safe()

                # Start loop (uses DUMMY_STATS_HTML now, so no jumping!)
                self.refresh_ingame_overlay()

            # B) KILLFEED (Insert text to give it size and make it grabbable)
            if "feed" in targets:
                # Fill feed with fake lines so box is large enough to click
                fake_feed = []
                # Killfeed Font Size (Robust)
                kf_cfg_raw = self.config.get("killfeed", {})
                kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
                kf_f = kf_cfg.get("font_size", 19)
                base_style = f"font-family: 'Black Ops One', sans-serif; font-size: {kf_f}px; margin-bottom: 2px; text-align: right;"

                # Simulate 3 lines
                line1 = f'<div style="{base_style}"><span style="color:#00ff00;">YOU</span> <span style="color:white;">[Kill]</span> <span style="color:#ff0000;">ENEMY</span></div>'
                line2 = f'<div style="{base_style}"><span style="color:#00ff00;">ALLY</span> <span style="color:white;">[HS]</span> <span style="color:#ff0000;">TARGET</span></div>'
                line3 = f'<div style="{base_style}"><span style="color:#888;">[SKL]</span> <span style="color:#ff4444;">SWEATY</span> (4.2)</div>'

                self.overlay_win.feed_label.setText(line1 + line2 + line3)
                self.overlay_win.feed_label.adjustSize()
                self.overlay_win.feed_label.show()

            # C) EVENTS (Preview image)
            if "event" in targets:
                # NEW COMBOBOX LOGIC
                img_name = clean_path(ui.combo_evt_img.currentText())
                
                # If nothing selected, take first item
                if not img_name and ui.combo_evt_img.count() > 0:
                    img_name = clean_path(ui.combo_evt_img.itemText(0))
                    
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

                        # Set position
                        evt_name = ui.lbl_editing.text().replace("EDITING: ", "").strip()
                        data = self.config.get("events", {}).get(evt_name, {})
                        ex = int(data.get("x", 100) * self.overlay_win.ui_scale)
                        ey = int(data.get("y", 100) * self.overlay_win.ui_scale)
                        self.overlay_win.event_preview_label.move(ex, ey)

                        self.overlay_win.event_preview_label.show()
                        self.overlay_win.event_preview_label.raise_()

            # D) KILLSTREAK (Fill dummy data)
            if "streak" in targets:
                streak_cfg = self.config.get("streak", {})
                img_name = clean_path(streak_cfg.get("img", "KS_Counter.png"))
                img_path = get_asset_path(img_name)

                # Simulate active streak
                self.overlay_win.draw_streak_ui(
                    img_path,
                    10,  # Dummy Count
                    ["TR", "NC", "VS"], # Dummy Factions
                    streak_cfg,
                    [0, 1, 2] # Dummy Slots
                )

            # E) CROSSHAIR (Show immediately)
            if "crosshair" in targets:
                # Ensure current settings are loaded
                self.update_crosshair_from_qt()
                if hasattr(self.overlay_win, 'crosshair_label'):
                    self.overlay_win.crosshair_label.show()
                    self.overlay_win.crosshair_label.raise_()

            # Refresh mask one last time after all dummy data is set
            self.overlay_win.update_edit_mask(targets)
            self.add_log(f"UI: Edit mode activated for {targets}")

        else:
            # --- STOP EDIT (Off) ---

            # FORCE config window back (OnTop off)
            self.ovl_config_win.setWindowFlags(self.ovl_config_win.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.ovl_config_win.show()

            # 1. Make overlay passthrough again
            self.overlay_win.set_mouse_passthrough(True)

            # 2. Reset buttons
            for btn in btn_list:
                btn.setText("MOVE UI")
                btn.setStyleSheet("")

                # 3. Cleanup dummy data (Empty)
            # 4. Save
            if "event" in targets:
                self.save_event_ui_data()
            elif "streak" in targets:
                self.save_streak_settings_from_qt()
            elif "stats" in targets:
                self.save_stats_config_from_qt()
            elif "feed" in targets:
                self.save_feed_config_from_qt()
            elif "crosshair" in targets:
                self.update_crosshair_from_qt()

            # --- CLEANUP (Global Cleanup) ---
            # If game is NOT running, hide EVERYTHING to avoid hanging elements.
            if not getattr(self, 'ps2_running', False):
                self.stop_overlay_logic()

                # Event Preview needs extra handling (not part of standard logic)
                if hasattr(self.overlay_win, 'event_preview_label'):
                    self.overlay_win.event_preview_label.hide()

            self.add_log("UI: Positions saved & edit finished.")


    def _get_random_slot(self):
        import random
        # If list doesn't exist yet
        if not hasattr(self, 'streak_slot_map'): self.streak_slot_map = []

        knives_per_ring = 50
        current_ring = len(self.streak_slot_map) // knives_per_ring

        # Which slots in this ring are already occupied?
        used_in_ring = [s % knives_per_ring for s in self.streak_slot_map if s // knives_per_ring == current_ring]

        # Find all free slots (0 to 49)
        available = [x for x in range(knives_per_ring) if x not in used_in_ring]

        if not available:
            return len(self.streak_slot_map)  # Fallback (should never happen)

        # Choose random free slot
        chosen = random.choice(available)

        # Return: Ring-Offset + Random slot
        return (current_ring * knives_per_ring) + chosen

    def update_streak_display(self):
        """Sends streak data safely via signal to the overlay window"""
        if not self.overlay_win: return

        streak_cfg = self.config.get("streak", {})
        img_path = get_asset_path(streak_cfg.get("img", "KS_Counter.png"))

        current_streak = getattr(self, 'killstreak_count', 0)
        
        # THREAD-SAFE COPY: Copy the list while holding reference, to avoid race conditions with worker
        raw_factions = getattr(self, 'streak_factions', [])
        factions = list(raw_factions) if isinstance(raw_factions, list) else []
        
        # DEBUG: Trace unwanted updates
        # if current_streak > 0:
        #    print(f"DEBUG: update_streak_display called! Count: {current_streak}, Factions: {len(factions)}")

        raw_slots = getattr(self, 'streak_slot_map', [])
        slot_map = list(raw_slots) if isinstance(raw_slots, list) else []

        # IMPORTANT: Use signal system to avoid thread errors
        self.overlay_win.signals.update_streak.emit(
            img_path,
            current_streak,
            factions,
            streak_cfg,
            slot_map
        )

    def hide_streak_display(self):
        """Hides the streak display without resetting the counter."""
        if not self.overlay_win: return
        self.overlay_win.signals.update_streak.emit("", 0, [], {}, [])

    def reset_streak_state(self):
        """Resets all streak-related flags and counters."""
        self.killstreak_count = 0
        self.kill_counter = 0
        self.is_dead = False
        self.was_revived = False
        self.is_tk_death = False
        self.last_kill_time = 0
        self.add_log("STREAK: Status reset (New character/session).")

    def test_streak_visuals(self):
        """
        Starts a preview with 20 knives (PyQt6 compatible).
        """
        self._set_overlay_test_mode("streak")
        # 1. Cancel previous timers
        if self._streak_test_timer:
            self._streak_test_timer.stop()
            self._streak_test_timer = None

        # 2. Create backup (only if not already in test mode)
        if self._streak_backup is None:
            self._streak_backup = {
                'count': getattr(self, 'killstreak_count', 0),
                'factions': getattr(self, 'streak_factions', []),
                'slots': getattr(self, 'streak_slot_map', [])
            }

        self.add_log("UI: Testing Killstreak visuals (20 knives)...")

        # 3. Set test values
        self.killstreak_count = 20
        # Create a colorful mix of factions
        self.streak_factions = (["TR", "NC", "VS"] * 7)[:20]

        import random
        # Distribute slots randomly
        slots = list(range(20))
        random.shuffle(slots)
        self.streak_slot_map = slots

        # 4. Send update to overlay
        self.update_streak_display()

        # 5. Define reset function
        def reset_action():
            try:
                if self._streak_backup:
                    self.killstreak_count = self._streak_backup['count']
                    self.streak_factions = self._streak_backup['factions']
                    self.streak_slot_map = self._streak_backup['slots']

                    # Reset overlay
                    self.update_streak_display()

                    self._streak_backup = None  # Delete backup
            except Exception as e:
                self.add_log(f"ERR: Streak Test Reset failed: {e}")
            finally:
                self._streak_test_timer = None
                if self.is_streak_test:
                    self._set_overlay_test_mode(None)
                self.add_log("UI: Test finished.")

        # 6. Start timer (PyQt6 way)
        self._streak_test_timer = QTimer(self.main_hub)
        self._streak_test_timer.setSingleShot(True)
        self._streak_test_timer.timeout.connect(reset_action)
        self._streak_test_timer.start(4000)  # 4 seconds

    def test_crosshair_visuals(self):
        """Runs an isolated crosshair preview."""
        if not self.overlay_win:
            self.add_log("WARN: Overlay not active!")
            return

        self._set_overlay_test_mode("crosshair")
        self.add_log("UI: Starting Crosshair test...")

        # Apply latest UI/config values immediately so preview matches current settings.
        self.update_crosshair_from_qt()
        self.refresh_ingame_overlay()

        def end_crosshair_test():
            if self.is_crosshair_test:
                self._set_overlay_test_mode(None)
                self.refresh_ingame_overlay()
            self.add_log("UI: Crosshair test finished.")

        QTimer.singleShot(6000, end_crosshair_test)

    def fade_out(self, tag, alpha=255):
        if alpha > 0:
            alpha -= 15  # Fade speed (higher = faster)

            # Find all items with this tag
            items = self.ovl_canvas.find_withtag(tag)
            for item in items:
                # For text, we can simply change the color (grayscale)
                if self.ovl_canvas.type(item) == "text":
                    # From white to black/transparent
                    color_val = max(0, alpha)
                    hex_color = f'#{color_val:02x}{color_val:02x}{color_val:02x}'
                    self.ovl_canvas.itemconfig(item, fill=hex_color)

                # For images it's more complex (requires PIL re-rendering)
                # Simpler solution: We move it slightly or change the position
                # For real image alpha we would need to save the PIL instance:

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
        # List of color levels for the "glow" effect
        colors = ["#050a0f", "#0a141d", "#0f1e2b", "#142839", "#00f2ff"]
        if step < len(colors):
            current_color = colors[step]
            # Animate border color
            self.sub_menu_frame.config(highlightbackground=current_color)
            # Animate text color of buttons
            for btn in self.sub_buttons:
                btn.config(fg=current_color if step < len(colors) - 1 else "#00f2ff")

            self.root.after(50, lambda: self.animate_fade_in(step + 1))

    def update_live_graph(self):
        """Calculates current stats every second and triggers dashboard update."""
        try:
            now = time.time()

            # Get currently selected server ID (Default to 10/EU)
            current_wid = str(getattr(self, 'current_world_id', '10'))

            # 1. Calculate faction numbers (WITH CLEANUP)
            counts = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0}
            total_pop = 0

            # Cleanup Time: Players inactive for > 10 Minutes are removed
            cutoff = now - 600
            
            # IMPORTANT: create list(...) for thread safety, as worker writes in parallel
            snapshot = list(self.active_players.items())
            to_remove = []

            for pid, val in snapshot:
                # Default values
                t = 0
                fac = "NSO"
                p_wid = current_wid 

                if len(val) == 3:
                     t, fac, p_wid = val
                elif len(val) == 2:
                     t, fac = val
                
                # A) CLEANUP CHECK
                # Exclude current user from cleanup (AFK protection)
                if t < cutoff and pid != self.current_character_id:
                    to_remove.append(pid)
                    continue

                # B) FILTER: Only count if server ID matches!
                if str(p_wid) != current_wid:
                    continue

                # C) Count
                if fac in counts:
                    counts[fac] += 1
                    total_pop += 1
            
            # Remove old entries
            for pid in to_remove:
                # Safety check (might be already gone)
                if pid in self.active_players:
                    del self.active_players[pid]

            self.live_stats.update(counts)
            self.live_stats["Total"] = total_pop

            # 2. Feed graph data
            elapsed = now - getattr(self, 'session_start_time', now)
            graph_interval = 1.0 if elapsed < 60 else 30.0

            if now - getattr(self, 'last_graph_point_time', 0) >= graph_interval:
                self.pop_history.pop(0)
                self.pop_history.append(total_pop)
                self.last_graph_point_time = now

            # 2b. Session Time Update (Every 10s)
            if now - getattr(self, 'last_session_update', 0) >= 10:
                self.update_session_time()
                self.last_session_update = now
            
            self.update_discord_presence()

            # 3. UI UPDATE
            if hasattr(self, 'main_hub') and self.main_hub.stack.currentIndex() == 0:
                self.update_dashboard_elements()

        except Exception as e:
            print(f"Stats-Update Error: {e}")

    def update_session_time(self):
        """Updates displayed session time in overlay (independent of kills)."""
        if not self.current_character_id: return
        
        # We need the session object
        s_obj = self.session_stats.get(self.current_character_id)
        if not s_obj: return

        # If overlay is running, update display
        if self.overlay_win and hasattr(self.overlay_win, "update_stats_display"):
            # FIX: Only update if widget should be visible!
            # (Prevents "flashing" every 10s when alt-tabbed)
            is_test = getattr(self, "is_stats_test", False) or getattr(self, "debug_overlay_active", False)
            is_editing = self.is_hud_editing and ("stats" in getattr(self, "current_edit_targets", []))
            
            if (self.is_game_focused() or is_test) and not is_editing:
                self.overlay_win.update_stats_display(s_obj)

    def update_discord_presence(self):
        manager = getattr(self, "discord_presence", None)
        if manager is None:
            return
        if not bool(getattr(self, "ps2_running", False)):
            self.clear_discord_presence()
            return
        if not bool(self.config.get("discord_presence_active", False)):
            self.clear_discord_presence()
            return

        char_id = str(getattr(self, "current_character_id", "") or "").strip()
        if not char_id:
            self.clear_discord_presence()
            return

        stats_obj = self.session_stats.get(char_id)
        if not isinstance(stats_obj, dict) or not stats_obj:
            self.clear_discord_presence()
            return

        if float(stats_obj.get("start", 0) or 0) <= 0:
            self.clear_discord_presence()
            return

        char_name = (stats_obj.get("name") or "").strip()
        if not char_name or char_name == "Searching...":
            char_name = str(getattr(self, "current_selected_char_name", "") or "").strip()
        if not char_name:
            char_name = self.name_cache.get(char_id, "Unknown")

        world_id = str(stats_obj.get("world_id", self.current_world_id))
        server_name = self.get_server_name_by_id(world_id)

        base_name = (stats_obj.get("last_seen_base") or "").strip()
        manager.update_presence(char_name, server_name, base_name)

    def clear_discord_presence(self):
        manager = getattr(self, "discord_presence", None)
        if manager is not None:
            manager.clear_presence()

    def shutdown_runtime_workers(self):
        manager = getattr(self, "discord_presence", None)
        if manager is not None:
            manager.close()

    def check_mouse_leave(self):
        x, y = self.root.winfo_pointerxy()
        widget = self.root.winfo_containing(x, y)
        if widget != self.sub_menu_frame and widget not in self.sub_menu_frame.winfo_children():
            self.sub_menu_frame.place_forget()

    def clear_content(self):
        """Deletes all content from Canvas and destroys associated widgets"""
        for item_id in self.content_ids:
            try:
                # Get name of widget inside this canvas window
                widget_path = self.canvas.itemcget(item_id, "window")
                if widget_path:
                    # Search real widget object by name and destroy it
                    widget = self.root.nametowidget(widget_path)
                    widget.destroy()
            except Exception:
                # If the widget was already destroyed or was not a window
                pass

            # Now we delete the element permanently from the Canvas
            self.canvas.delete(item_id)

        self.content_ids.clear()

    def show_dashboard(self):
        """Shows the new Qt window and clears the Tkinter area."""
        self.clear_content()
        self.current_tab = "Dashboard"

        # Show the new window
        if hasattr(self, 'dash_window'):
            self.dash_window.show()
            self.dash_window.raise_()  # To the foreground

        # Info in main window (since it is now empty)
        # Removed tk.Label usage


    def animate_api_light(self, canvas, light_id, color_type, step=0):
        import math
        # Calculate pulse (Sine wave)
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
            pass  # Stops when tab is changed

    def show_characters(self):
        self.clear_content()
        self.current_tab = "characters"
        if hasattr(self, 'char_win'):
            self.char_win.show()
            self.char_win.raise_()



    def cache_worker(self):
        while True:
            ids = []
            try:
                # Collect IDs from queue (waits max 5 seconds for new IDs)
                while len(ids) < 30:
                    ids.append(self.id_queue.get(timeout=5))
            except Empty:
                pass

            if ids:
                try:
                    # Query Census with all details (including outfit!)
                    url = (f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/character/"
                           f"?character_id={','.join(ids)}"
                           f"&c:show=character_id,name.first,faction_id,battle_rank"
                           f"&c:resolve=outfit")

                    # First check if response is valid
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        try:
                            r = response.json()
                            if 'character_list' in r:
                                conn = sqlite3.connect(DB_PATH)
                                cursor = conn.cursor()

                                # Ensure RAM cache exists
                                if not hasattr(self, 'outfit_cache'):
                                    self.outfit_cache = {}

                                for char in r['character_list']:
                                    cid = char['character_id']
                                    name = char['name']['first']
                                    fid = char.get('faction_id', 0)
                                    rank = char.get('battle_rank', {}).get('value', 0)

                                    # Get outfit tag (alias)
                                    tag = char.get('outfit', {}).get('alias', "")

                                    # 1. Save in database (Permanent)
                                    cursor.execute('''INSERT OR REPLACE INTO player_cache 
                                                      (character_id, name, faction_id, battle_rank, outfit_tag) 
                                                      VALUES (?, ?, ?, ?, ?)''',
                                                   (cid, name, fid, rank, tag))

                                    # 2. IMPORTANT: Update in RAM
                                    # So Census listener finds the tag IMMEDIATELY
                                    self.name_cache[cid] = name
                                    self.outfit_cache[cid] = tag

                                conn.commit()
                                conn.close()

                                # Update GUI counter
                                if hasattr(self, 'cache_label') and self.cache_label.winfo_exists():
                                    try:
                                        conn = sqlite3.connect(DB_PATH)
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
        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
        print(f"LOG: {text}")  # Backup in der Konsole
        # Removed Tkinter Log logic as log_area doesn't exist

        # NEW: Also send to Qt window
        if hasattr(self, 'char_win'):
            # Thread-safe update via InvokeMethod
            QMetaObject.invokeMethod(self.char_win, "add_log",
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, text))

    def apply_main_background(self, path):
        """Sets the background image via stylesheet for the main window."""
        if not path:
            # RESET to default or empty
            self.main_hub.setStyleSheet("QMainWindow { border-image: none; background-color: #0b0b0b; }")
            return

        # Windows paths must be converted to slashes for CSS
        clean_path = path.replace("\\", "/")

        # Set stylesheet: border-image scales the image to window size
        style = f"""
        QMainWindow {{
            border-image: url("{clean_path}") 0 0 0 0 stretch stretch;
        }}
        """
        self.main_hub.setStyleSheet(style)

    def clear_background_file(self):
        """Resets the background image to default."""
        self.config["main_background_path"] = ""
        self.save_config()
        self.apply_main_background(None)
        
        if hasattr(self, 'settings_win') and hasattr(self.settings_win, 'lbl_bg_name'):
            self.settings_win.lbl_bg_name.setText("None")
            
        self.add_log("SYS: Background cleared.")

    def change_background_file(self):
        """Opens the file dialog, copies the file to assets, and saves the background."""
        from PyQt6.QtWidgets import QFileDialog
        import shutil

        # 1. Select file
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_hub,
            "Choose background image",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            try:
                # 2. Determine target path
                filename = os.path.basename(file_path)
                dest_path = os.path.join(ASSETS_DIR, filename)
                
                # Check if it is already the current one
                current_bg = self.config.get("main_background_path", "")
                if current_bg == filename or current_bg == file_path:
                    # It's already set, just refresh the view to be sure
                    self.apply_main_background(file_path if os.path.isabs(file_path) else get_asset_path(file_path))
                    self.add_log(f"SYS: Background '{filename}' is already active.")
                    return

                # 3. Copy to assets folder ONLY if it's not already there
                if os.path.abspath(file_path) != os.path.abspath(dest_path):
                    try:
                        shutil.copy2(file_path, dest_path)
                    except OSError as e:
                        # WinError 32: File in use -> This happens if the file exists and is active
                        if os.path.exists(dest_path):
                            self.add_log(f"SYS: Asset '{filename}' already exists and is locked. Using existing file.")
                        else:
                            raise e # Rethrow if it's a real error
                
                # 4. Save filename in config
                self.config["main_background_path"] = filename
                self.save_config()

                # 5. Apply immediately
                self.apply_main_background(dest_path)
                
                # 6. Update UI Label
                if hasattr(self, 'settings_win') and hasattr(self.settings_win, 'lbl_bg_name'):
                    self.settings_win.lbl_bg_name.setText(filename)

                self.add_log(f"SYS: Background changed to {filename}")
            except Exception as e:
                self.add_log(f"ERR: Failed to set background: {e}")

    def execute_launch(self, mode):
        # 1. Directory Check
        if not self.ps2_dir or not os.path.exists(self.ps2_dir):
            msg = "ERR: PS2 Directory not found! Check Settings."
            self.add_log(msg)
            self.launcher_win.lbl_info.setText(msg)
            return

        # Define paths
        src = self.source_high if mode == "high" else self.source_low
        dest = os.path.join(self.ps2_dir, "UserOptions.ini")
        exe = os.path.join(self.ps2_dir, "LaunchPad.exe")

        if os.path.exists(src):
            try:
                # Copy file
                shutil.copy2(src, dest)
                self.add_log(f"SYS: Applied {mode} configuration.")

                # Start game
                if os.path.exists(exe):
                    subprocess.Popen([exe])
                    self.add_log("SYS: LaunchPad triggered.")

                    # GUI Feedback
                    self.launcher_win.lbl_info.setText(f"SUCCESS: {mode.upper()} INITIALIZED. CLOSING...")



                else:
                    self.add_log("ERR: LaunchPad.exe not found.")
                    self.launcher_win.lbl_info.setText("ERR: LaunchPad.exe missing!")
            except Exception as e:
                # Error log was here previously because 'e' often contained root crash
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
                # 1. ERSTE API ABFRAGE (Basis-Daten & History)
                # IMPORTANT: No 'weapon_stat_by_faction' here as it exceeds limit!
                url = f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/character/?name.first_lower={name.lower()}&c:resolve=world,outfit,stat_history"
                r = requests.get(url, timeout=30).json()

                if not r.get('character_list'):
                    self.add_log(f"DEBUG: Character {name} not found.")
                    # UI FEEDBACK: "Character doesnt exist"
                    QTimer.singleShot(0, lambda: self.char_win.search_input.setText("Character doesnt exist."))
                    # Reset button text!
                    QTimer.singleShot(0, lambda: self.char_win.btn_search.setText("SEARCH"))
                    QTimer.singleShot(0, lambda: self.char_win.btn_search.setEnabled(True))
                    return

                char_data = r['character_list'][0]
                char_id = char_data['character_id']
                all_stats_container = char_data.get('stats', {})

                # --- STEP 2: STATS EXTRACTION ---
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

                # IMPORTANT: Name keys exactly as your UI expects them!
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

                # --- STEP 3: SECOND API QUERY (WEAPONS) ---
                # We get ONLY weapon stats, but up to 5000 entries
                # This bypasses the default resolve limit
                url_wep = f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/characters_weapon_stat_by_faction?character_id={char_id}&c:limit=5000"
                r_wep = requests.get(url_wep, timeout=30).json()
                
                w_stats_list = r_wep.get('characters_weapon_stat_by_faction_list', [])

                weapon_list = []
                temp_w = {}

                for entry in w_stats_list:
                    i_id = entry.get('item_id')
                    if not i_id or i_id == "0": continue
                    
                    if i_id not in temp_w:
                        db_info = self.item_db.get(i_id, {"name": f"Unknown ({i_id})"})
                        temp_w[i_id] = {
                            'id': i_id, 'name': db_info['name'], 
                            'kills': 0, 'deaths': 0, 
                            'shots': 0, 'hits': 0, 'hs': 0, 
                            'vkills': 0, 'time': 0
                        }

                    total_val = int(entry.get('value_vs', 0)) + int(entry.get('value_nc', 0)) + int(entry.get('value_tr', 0))
                    s_name = entry.get('stat_name')
                    
                    if s_name == 'weapon_kills':
                        temp_w[i_id]['kills'] += total_val
                    elif s_name == 'weapon_vehicle_kills':
                        temp_w[i_id]['vkills'] += total_val
                    elif s_name == 'weapon_deaths':
                        temp_w[i_id]['deaths'] += total_val
                    elif s_name == 'weapon_fire_count':
                        temp_w[i_id]['shots'] += total_val
                    elif s_name == 'weapon_hit_count':
                        temp_w[i_id]['hits'] += total_val
                    elif s_name == 'weapon_headshots':
                        temp_w[i_id]['hs'] += total_val
                    elif s_name == 'weapon_play_time':
                        temp_w[i_id]['time'] += total_val

                # Only show weapons with at least 1 kill OR 1 death (optional)
                weapon_list = sorted([w for w in temp_w.values() if w['kills'] > 0 or w['deaths'] > 0],
                                     key=lambda x: x['kills'], reverse=True)

                self.add_log(f"DEBUG: Processing complete. Found {len(weapon_list)} weapons (API Limit Bypass).")

                # --- SAFE TRANSFER VIA SIGNAL ---
                self.char_win.signals.search_finished.emit(custom_stats, weapon_list)

            except Exception as e:
                self.add_log(f"WORKER FATAL: {e}")
                # If it crashes, still release button (via signal or direct)
                QTimer.singleShot(0, lambda: self.char_win.btn_search.setEnabled(True))

                # Start thread

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    try:

        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Ensures uniform dark design

        # Load "Black Ops One" font
        font_path = resource_path(os.path.join("assets", "BlackOpsOne-Regular.ttf"))
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                print(f"Error: Font could not be loaded from {font_path}")
            else:
                family = QFontDatabase.applicationFontFamilies(font_id)[0]
                print(f"Font loaded: {family}")
        else:
            print(f"Warning: Font file not found at {font_path}")

        # Initialize your logic class (creates MainHub internally)
        client = DiorClientGUI()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        from dior_utils import BASE_DIR
        
        error_file = os.path.join(BASE_DIR, "error_log.txt")
        try:
            with open(error_file, "w") as f:
                f.write(traceback.format_exc())
        except:
            pass
        print(traceback.format_exc())
