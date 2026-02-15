import sys
import os
import ctypes
import math
import time
import re
import json
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from overlay_server import OverlayServer
from dior_utils import get_asset_path


IS_WINDOWS = sys.platform.startswith("win")

# Logic and animation classes come from QtCore
from PyQt6.QtCore import (Qt, pyqtSignal, QObject, QTimer, QPoint,
                            QSize, QUrl, QRectF, QPropertyAnimation, QEasingCurve)

# All visual components and effects come from QtWidgets
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QGraphicsDropShadowEffect,
                                 QVBoxLayout, QHBoxLayout, QFrame, QTextBrowser,
                                 QGraphicsOpacityEffect)

# Graphics resources come from QtGui
from PyQt6.QtGui import (QPixmap, QColor, QPainter, QPen, QBrush,
                            QTransform, QMovie, QCursor, QTextCursor, QTextDocument, QRegion, QImageReader)

# Sound Support (Optional, if pygame is missing)
try:
    import pygame

    pygame.mixer.init()
except ImportError:
    pass




# --- SIGNALS ---
class OverlaySignals(QObject):
    # img_path, sound_path, duration, x, y, scale, volume, is_hitmarker, play_duplicate, event_name
    show_image = pyqtSignal(str, str, int, int, int, float, float, bool, bool, str)
    killfeed_entry = pyqtSignal(str)
    update_stats = pyqtSignal(str, str)
    update_streak = pyqtSignal(str, int, list, dict, list)
    path_points_updated = pyqtSignal(list)
    clear_feed = pyqtSignal()
    setting_changed = pyqtSignal(str, object)
    test_trigger = pyqtSignal(str)
    edit_mode_toggled = pyqtSignal(str)
    item_moved = pyqtSignal(str, int, int)


class DraggableChat(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    # This method is no longer needed as we use setHtml() in the widget.
    # We leave it empty so calls don't crash.
    def add_animated_message(self, html_msg):
        pass

    def clear(self):
        self.page().runJavaScript("clearChat()")


class EffectBrowser(QWebEngineView):
    """
    A specialized WebEngineView for rendering effects (Images/GIFs).
    Solves issues with typical QLabel GIF rendering by using Chromium's engine.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        
        # Optimization: Disable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def set_effect(self, img_path):
        if not img_path:
            self.setHtml("")
            return
            
        # Clean path for cross-platform compatibility
        abs_path = os.path.abspath(img_path).replace("\\", "/")
        filename = os.path.basename(abs_path)
        base_dir = os.path.dirname(abs_path)
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}
                img {{ width: 100vw; height: 100vh; object-fit: contain; }}
            </style>
        </head>
        <body>
            <img src="{filename}">
        </body>
        </html>
        """
        
        # Providing the directory as the base URL allows simple relative "src" resolution
        base_url = QUrl.fromLocalFile(base_dir + "/")
        self.setHtml(html, base_url)

    def clear(self):
        self.setHtml("")


class ChatMessageWidget(QWidget):
    def __init__(self, parent, html, hold_time):
        super().__init__(parent)
        self.hold_time = hold_time
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.browser = DraggableChat(self)
        layout.addWidget(self.browser)

        self.browser.loadFinished.connect(self._prepare_height)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # --- THE FIX: Provide Base URL ---
        # We specify the path of the current folder as "home".
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.browser.setHtml(html, base_url)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

    def _prepare_height(self):
        """Replacement for the old adjust_height."""
        # We ask JavaScript for the scrollHeight (actual height of the content)
        self.browser.page().runJavaScript(
            "document.documentElement.scrollHeight",
            self._apply_height_callback
        )

    def _apply_height_callback(self, height):
        """Wird aufgerufen, sobald JavaScript die Höhe berechnet hat."""
        if height:
            new_h = int(height) + 10  # Small buffer
            self.setFixedHeight(new_h)
            self.browser.setFixedHeight(new_h)

            # ONLY NOW we start the timer for disappearance
            if self.hold_time > 0:
                QTimer.singleShot(self.hold_time * 1000, self.start_fade_out)

    def start_fade_out(self):
        """Remains almost the same, but uses QPropertyAnimation on the container."""
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(2000)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.destroy_message)
        self.anim.start()

    def destroy_message(self):
        """Remains exactly the same."""
        self.hide()
        self.deleteLater()

# --- DRAWING LAYER (For path recording) ---
class PathDrawingLayer(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.parent_ovl = parent

    def mousePressEvent(self, event):
        if self.parent_ovl.path_edit_active:
            pos = event.pos()
            label_rect = self.parent_ovl.streak_bg_label.geometry()
            center = label_rect.center()
            off_x = pos.x() - center.x()
            off_y = pos.y() - center.y()

            self.parent_ovl.custom_path.append((off_x, off_y))
            self.parent_ovl.signals.path_points_updated.emit(self.parent_ovl.custom_path)
            self.update()
        else:
            event.ignore()

    def paintEvent(self, event):
        if not self.parent_ovl.path_edit_active: return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Click area
        painter.setBrush(QColor(0, 0, 0, 1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        if len(self.parent_ovl.custom_path) == 0: return

        skull_center = self.parent_ovl.streak_bg_label.geometry().center()

        shadow_pen = QPen(QColor(0, 0, 0, 180), 5, Qt.PenStyle.SolidLine)
        cyan_color = QColor(0, 242, 255)
        line_pen = QPen(cyan_color, 2, Qt.PenStyle.DashLine)
        shadow_brush = QBrush(QColor(0, 0, 0, 180))
        point_brush = QBrush(cyan_color)
        point_pen = QPen(QColor(255, 255, 255), 1)

        def draw_lines(p):
            if len(self.parent_ovl.custom_path) > 1:
                for i in range(len(self.parent_ovl.custom_path) - 1):
                    p1 = skull_center + QPoint(int(self.parent_ovl.custom_path[i][0]),
                                               int(self.parent_ovl.custom_path[i][1]))
                    p2 = skull_center + QPoint(int(self.parent_ovl.custom_path[i + 1][0]),
                                               int(self.parent_ovl.custom_path[i + 1][1]))
                    p.drawLine(p1, p2)
                p_last = skull_center + QPoint(int(self.parent_ovl.custom_path[-1][0]),
                                               int(self.parent_ovl.custom_path[-1][1]))
                p_first = skull_center + QPoint(int(self.parent_ovl.custom_path[0][0]),
                                                int(self.parent_ovl.custom_path[0][1]))
                p.drawLine(p_last, p_first)

        painter.setPen(shadow_pen)
        draw_lines(painter)
        painter.setPen(line_pen)
        draw_lines(painter)

        for pt_data in self.parent_ovl.custom_path:
            center = skull_center + QPoint(int(pt_data[0]), int(pt_data[1]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow_brush)
            painter.drawEllipse(center, 8, 8)
            painter.setPen(point_pen)
            painter.setBrush(point_brush)
            painter.drawEllipse(center, 5, 5)


# --- MAIN OVERLAY CLASS ---
class QtOverlay(QWidget):
    def __init__(self, gui_ref=None):
        super().__init__()
        self.gui_ref = gui_ref
        self.edit_mode = False
        self.dragging_widget = None
        self.drag_offset = None
        self.knife_labels = []
        
        # --- STATS CACHE (NEW to avoid flickering) ---
        self._last_stats_html = ""
        self._last_stats_img = ""
        self._last_stats_payload = None
        self._stats_web_visible = False
        self._last_streak_payload = None

        # --- CACHE DICTIONARY (NEW) ---
        # Here we store all loaded images
        self.pixmap_cache = {}
        self.movie_cache = {}

        self.cache_usage_timestamps = {}  # NEW: Stores {path: timestamp}

        # GC-Timer: Every 2 minutes we check for "garbage"
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self.run_garbage_collection)
        self.gc_timer.start(120000)  # 120.000 ms = 2 Minuten

        # 1. WINDOW CONFIGURATION
        # On Linux/Proton, ToolTip windows have the highest priority
        if IS_WINDOWS:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool |
                Qt.WindowType.WindowTransparentForInput
            )
        else:
            # Linux: Use ToolTip for maximum overlay priority over Proton games
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.ToolTip |  # ToolTip has highest priority on Linux
                Qt.WindowType.WindowTransparentForInput |
                Qt.WindowType.X11BypassWindowManagerHint
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # Scaling
        self.base_height = 1080.0
        self.ui_scale = screen.height() / self.base_height
        self.ui_scale = max(0.8, self.ui_scale)

        # Drawing layer
        self.path_edit_active = False
        self.custom_path = []
        self.path_layer = PathDrawingLayer(self)
        self.path_layer.setGeometry(self.rect())
        self.path_layer.hide()

        # Web HUD (Chromium frontend)
        self.hud_view = QWebEngineView(self)
        self.hud_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hud_view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hud_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        hud_settings = self.hud_view.settings()
        hud_settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        hud_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        hud_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.hud_view.setGeometry(self.rect())
        self.hud_view.show()

        # 2. WIDGETS
        self.crosshair_label = QLabel(self)
        self.crosshair_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.crosshair_label.hide()

        self.stats_bg_label = QLabel(self)
        self.stats_bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.stats_bg_label.hide()
        self.stats_text_label = QLabel(self)
        self.stats_text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.stats_text_label.hide()

        shadow_stats = QGraphicsDropShadowEffect()
        shadow_stats.setBlurRadius(5 * self.ui_scale)
        shadow_stats.setColor(QColor(0, 0, 0, 240))
        shadow_stats.setXOffset(1 * self.ui_scale)
        shadow_stats.setYOffset(1 * self.ui_scale)
        self.stats_text_label.setGraphicsEffect(shadow_stats)

        self.streak_bg_label = QLabel(self)
        self.streak_bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.streak_bg_label.hide()
        self.streak_text_label = QLabel(self)
        self.streak_text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.streak_text_label.hide()

        # Killfeed
        self.feed_messages = []
        self.feed_label = QLabel(self)
        self.feed_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.feed_w = int(600 * self.ui_scale)
        self.feed_h = int(550 * self.ui_scale)
        self.feed_label.setFixedSize(self.feed_w, self.feed_h)
        self.feed_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.feed_label.setStyleSheet("background: transparent;")

        shadow_feed = QGraphicsDropShadowEffect()
        shadow_feed.setBlurRadius(4 * self.ui_scale)
        shadow_feed.setXOffset(1 * self.ui_scale)
        shadow_feed.setYOffset(1 * self.ui_scale)
        shadow_feed.setColor(QColor(0, 0, 0, 255))
        self.feed_label.setGraphicsEffect(shadow_feed)

        self.event_preview_label = QLabel(self)
        self.event_preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.event_preview_label.hide()

        # --- MULTI-EVENT POOL ---
        self.img_pool = []
        for _ in range(10): # Support up to 10 simultaneous events
            lbl = EffectBrowser(self)
            lbl.hide()
            lbl._is_busy = False
            self.img_pool.append(lbl)
            
        # Compatibility reference for code that still expects self.img_label
        self.img_label = self.img_pool[0]

        # 3. CONNECT SIGNALS
        self.signals = OverlaySignals()
        self.signals.show_image.connect(self.add_event_to_queue)
        self.signals.killfeed_entry.connect(self.add_killfeed_row)
        self.signals.update_stats.connect(self.set_stats_html)
        self.signals.update_streak.connect(self.draw_streak_ui)
        self.signals.clear_feed.connect(self.clear_killfeed)

        # Activate mouse passthrough
        self.set_mouse_passthrough(True)

        # Timers
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.animate_pulse)
        self.pulse_timer.start(40)

        self.redraw_timer = QTimer(self)
        self.redraw_timer.timeout.connect(self.force_update)
        self.redraw_timer.start(1000)

        # Queue Logic
        self.event_queue = []
        self.is_showing = False
        self.current_event_key = None # (img, snd)
        self.queue_timer = QTimer()
        self.queue_timer.setSingleShot(True)
        self.queue_timer.timeout.connect(self.finish_current_event)

        # Initial queue setting (fallback)
        self._target_pw_sink = None  # PipeWire sink name for audio routing
        self.queue_enabled = True
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            self.queue_enabled = self.gui_ref.config.get("event_queue_active", True)
            
            # Init Audio Device
            dev_name = self.gui_ref.config.get("audio_device", "Default")
            self.set_audio_device(dev_name)

        self.hitmarker_label = QLabel(self)
        self.hitmarker_label.setScaledContents(True)
        self.hitmarker_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hitmarker_label.hide()

        self.chat_container = QWidget(self)
        self.chat_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.chat_container.hide()

        # --- SINGLE TWITCH BROWSER ---
        self.twitch_browser = DraggableChat(self.chat_container)
        self.twitch_browser.hide()

        # Set initial content
        self.chat_hold_time = 15
        self.update_twitch_browser_content()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.fade_out_chat)

        # --- TWITCH DRAG COVER (Fix for WebEngine click interference) ---
        self.twitch_drag_cover = QWidget(self)
        self.twitch_drag_cover.setObjectName("twitch_drag_cover")
        self.twitch_drag_cover.hide()
        # WICHTIG: Kein WA_TransparentForMouseEvents hier, damit es Klicks fängt!

        self.server = None
        self.start_server()

        self.active_edit_targets = []

        # --- PRELOAD ASSETS (NEW) ---
        QTimer.singleShot(1000, self.preload_config_assets)

    def preload_config_assets(self):
        """Preloads all images defined in the config into RAM cache to avoid disk hitching."""
        if not self.gui_ref or not hasattr(self.gui_ref, 'config'):
            return

        conf = self.gui_ref.config
        paths_to_load = []

        # 1. Events
        events = conf.get("events", {})
        for ev in events.values():
            img = ev.get("img")
            if img:
                if isinstance(img, list): paths_to_load.extend(img)
                else: paths_to_load.append(img)

        # 2. Crosshair
        ch = conf.get("crosshair", {})
        if ch.get("path"): paths_to_load.append(ch["path"])

        # 3. Streak
        stk = conf.get("streak", {})
        if stk.get("img"): paths_to_load.append(stk["img"])
        for fac in ["tr", "nc", "vs"]:
            k = stk.get(f"knife_{fac.lower()}") 
            if k: paths_to_load.append(k)

        # 4. Stats
        stats = conf.get("stats_widget", {})
        if stats.get("img"): paths_to_load.append(stats["img"])

        # 5. Feed
        feed = conf.get("killfeed", {})
        if feed.get("hs_icon"): paths_to_load.append(feed["hs_icon"])

        # 6. Main Background
        bg = conf.get("main_background_path")
        if bg:
            if isinstance(bg, list): paths_to_load.extend(bg)
            else: paths_to_load.append(bg)

        # Process all paths
        count = 0
        for p in set(paths_to_load): # Unique only
            if not p: continue
            
            # Resolve relative paths
            full_path = p
            if not os.path.isabs(p):
                full_path = get_asset_path(p)
            
            if os.path.exists(full_path):
                # We "touch" the cache logic to load the pixmap
                if not p.lower().endswith(".gif"):
                    self.get_cached_pixmap(full_path)
                    count += 1
        
        if hasattr(self.gui_ref, 'add_log'):
            self.gui_ref.add_log(f"SYS: Preloaded {count} assets into RAM.")

    @staticmethod
    def _get_pulse_sink_map():
        """Build a mapping from PulseAudio sink description -> sink name.
        On PipeWire, the description (e.g. 'UMC1820 Pro') often differs
        from the internal sink name (e.g. 'alsa_output.usb-BEHRINGER_...').
        SDL/pygame shows descriptions, but PULSE_SINK needs the real name."""
        sink_map = {}  # description -> name, and name -> name
        try:
            import subprocess
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True, text=True, timeout=5
            )
            current_name = None
            for line in result.stdout.split('\n'):
                stripped = line.strip()
                if stripped.startswith('Name:'):
                    current_name = stripped.split(':', 1)[1].strip()
                    sink_map[current_name] = current_name  # name -> name (identity)
                elif stripped.startswith('Description:') and current_name:
                    desc = stripped.split(':', 1)[1].strip()
                    sink_map[desc] = current_name  # description -> name
        except Exception:
            pass
        return sink_map

    def _get_default_sink_name(self):
        """Get the default PipeWire/PulseAudio sink name."""
        try:
            import subprocess
            result = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return None

    def _relink_sdl_to_sink(self, target_sink, log=None):
        """Use pw-link to disconnect SDL Application from its current sink
        and reconnect it to the target sink. This is needed because SDL/pygame
        connects via PipeWire natively (not PulseAudio compat), so pactl
        move-sink-input can't see the streams. pw-link works at the port level."""
        if not log:
            log = lambda m: None
        try:
            import subprocess
            
            # 1. Get all current links to find where SDL is connected
            result = subprocess.run(
                ["pw-link", "-l"],
                capture_output=True, text=True, timeout=5
            )
            
            # Parse SDL Application output ports and their current connections
            sdl_links = []  # [(output_port, connected_input_port), ...]
            sdl_outputs = []  # [output_port, ...]
            current_output = None
            
            for line in result.stdout.split('\n'):
                stripped = line.strip()
                if stripped.startswith('SDL Application:output_'):
                    current_output = stripped
                    sdl_outputs.append(stripped)
                elif current_output and stripped.startswith('|->'):
                    connected_to = stripped.replace('|->', '').strip()
                    sdl_links.append((current_output, connected_to))
                    current_output = None
                elif not stripped.startswith('|'):
                    current_output = None
            
            if not sdl_outputs:
                log("AUDIO: No SDL Application outputs found in pw-link")
                return False
            
            # 2. Disconnect existing connections
            for out_port, in_port in sdl_links:
                r = subprocess.run(
                    ["pw-link", "-d", out_port, in_port],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode != 0:
                    log(f"AUDIO: pw-link disconnect failed: {r.stderr.strip()}")
            
            # 3. Connect to target sink
            # Map SDL output channels to sink input channels
            channel_map = {
                'output_FL': 'playback_FL',
                'output_FR': 'playback_FR',
                'output_RL': 'playback_RL',
                'output_RR': 'playback_RR',
                'output_FC': 'playback_FC',
                'output_LFE': 'playback_LFE',
            }
            
            connected = 0
            for out_port in sdl_outputs:
                # Extract channel name (e.g., 'output_FL' from 'SDL Application:output_FL')
                channel = out_port.split(':')[1] if ':' in out_port else None
                if channel and channel in channel_map:
                    target_port = f"{target_sink}:{channel_map[channel]}"
                    r = subprocess.run(
                        ["pw-link", out_port, target_port],
                        capture_output=True, text=True, timeout=5
                    )
                    if r.returncode == 0:
                        connected += 1
                    else:
                        log(f"AUDIO: pw-link connect failed: {out_port} -> {target_port}: {r.stderr.strip()}")
            
            if connected > 0:
                log(f"AUDIO: ✓ Linked {connected} port(s) to '{target_sink}'")
                return True
            else:
                log(f"AUDIO: Failed to link any ports to '{target_sink}'")
                return False
                
        except Exception as e:
            log(f"AUDIO: pw-link error: {e}")
            return False

    def set_audio_device(self, device_name):
        """Re-initializes the mixer with the selected device."""
        if 'pygame' not in sys.modules:
            return

        log = self.gui_ref.add_log if self.gui_ref else lambda m: print(m)

        try:
            log(f"AUDIO: set_audio_device('{device_name}') called")
            
            # 1. Stop all playback to prevent double-free/segfaults
            if pygame.mixer.get_init():
                pygame.mixer.stop()
            
            # Quit existing mixer to switch devices
            attempts = 0
            while pygame.mixer.get_init() and attempts < 3:
                pygame.mixer.quit()
                attempts += 1
            
            # Short pause to let OS release the device
            pygame.time.wait(100)

            # 2. Clean any leftover env vars
            for env_key in ('PULSE_SINK', 'SDL_AUDIO_DEVICE_NAME'):
                if env_key in os.environ:
                    del os.environ[env_key]

            # 3. Determine target sink (Linux) or device name (Windows)
            target_sdl_device = None

            if device_name and device_name != "Default":
                if not IS_WINDOWS:
                    self._target_pw_sink = device_name  # PipeWire sink name (e.g., "Quad Channel")
                else:
                    # Windows: Use SDL2 native device switching via devicename arg
                    target_sdl_device = device_name
                    self._target_pw_sink = None
            else:
                self._target_pw_sink = None
            
            # 4. Init mixer
            if target_sdl_device:
                try:
                    # Try to init with specific device
                    pygame.mixer.init(devicename=target_sdl_device)
                    log(f"AUDIO: Initialized with specific device: {target_sdl_device}")
                except Exception as e:
                    log(f"AUDIO: Failed to init '{target_sdl_device}' ({e}), falling back to default")
                    # Fallback
                    if pygame.mixer.get_init():
                        pygame.mixer.quit()
                    pygame.mixer.init()
            else:
                # Default device
                pygame.mixer.init()
            
            if not pygame.mixer.get_init():
                log("AUDIO FATAL: mixer.init() failed")
                return
            
            log(f"AUDIO: Mixer initialized")
            
            # 5. On Linux, play a silent sound to create the PipeWire stream,
            #    then use pw-link to reroute it to the target sink
            if not IS_WINDOWS and self._target_pw_sink:
                try:
                    import array
                    buf = array.array('h', [0] * 4410)  # 100ms silence
                    snd = pygame.mixer.Sound(buffer=buf)
                    snd.set_volume(0.0)
                    snd.play()
                    pygame.time.wait(200)  # Give PipeWire time to register
                    
                    self._relink_sdl_to_sink(self._target_pw_sink, log)
                except Exception as e:
                    log(f"AUDIO: Routing setup error: {e}")
            elif not IS_WINDOWS and not self._target_pw_sink:
                # "Default" selected — route to default sink
                default_sink = self._get_default_sink_name()
                if default_sink:
                    try:
                        import array
                        buf = array.array('h', [0] * 4410)
                        snd = pygame.mixer.Sound(buffer=buf)
                        snd.set_volume(0.0)
                        snd.play()
                        pygame.time.wait(200)
                        self._relink_sdl_to_sink(default_sink, log)
                    except Exception:
                        pass
                log(f"AUDIO: Using default device")
            else:
                log(f"AUDIO: ✓ Switched to '{device_name}'")
                
        except Exception as e:
            if self.gui_ref:
                self.gui_ref.add_log(f"AUDIO FATAL: {e}")
            try:
                if not pygame.mixer.get_init(): pygame.mixer.init()
            except: pass

    def get_master_volume(self):
        """Gets the master volume from the config (0-100) and returns float (0.0-1.0)."""
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            # Default is 50% if nothing has been saved yet
            vol_percent = self.gui_ref.config.get("audio_volume", 50)
            # Ensure it is float and between 0.0 and 1.0
            return max(0.0, min(1.0, float(vol_percent) / 100.0))
        return 0.5  # Fallback

    def run_garbage_collection(self):
        """Deletes resources that haven't been used for more than 20 minutes."""
        now = time.time()
        max_idle_time = 20 * 60  # 20 minutes in seconds

        # Lists for paths to be deleted
        to_remove = []

        for path, last_used in self.cache_usage_timestamps.items():
            if now - last_used > max_idle_time:
                to_remove.append(path)

        if not to_remove:
            return

        for path in to_remove:
            # 1. Remove from movie cache (if present)
            if path in self.movie_cache:
                movie = self.movie_cache.pop(path)
                movie.stop()  # IMPORTANT: Stop animation
                movie.deleteLater()  # Release resources

            # 2. Remove from pixmap cache
            if path in self.pixmap_cache:
                self.pixmap_cache.pop(path)

            # 3. Delete timestamp entry
            if path in self.cache_usage_timestamps:
                del self.cache_usage_timestamps[path]

        self.gui_ref.add_log(f"GC: {len(to_remove)} ungenutzte Ressourcen aus RAM gelöscht.")

    def notify_chat_moved(self, x, y):
        # Send signal to controller
        self.signals.item_moved.emit("twitch", x, y)

    def notify_item_moved_unscaled(self, item_name, x, y):
        """Emit move updates in unscaled config coordinates."""
        ux = int(round(float(x) / self.ui_scale))
        uy = int(round(float(y) / self.ui_scale))
        self.signals.item_moved.emit(item_name, ux, uy)

    def update_twitch_style(self, x, y, w, h, opacity, font_size):
        self.chat_container.setGeometry(int(x), int(y), int(w), int(h))
        self.current_chat_font_size = font_size

        alpha = int((opacity / 100) * 255)

        # Set background completely to transparent
        self.chat_container.setStyleSheet(f"""
            QWidget {{ 
                background-color: rgba(0, 0, 0, {alpha}); 
                border-radius: 5px; 
            }}
        """)
        
        if hasattr(self, 'twitch_browser'):
            self.twitch_browser.setGeometry(self.chat_container.rect())
        if hasattr(self, 'twitch_drag_cover'):
            self.twitch_drag_cover.setGeometry(self.chat_container.geometry())

        if self.gui_ref:
            enabled = self.gui_ref.config.get("twitch", {}).get("active", True)
            self.update_twitch_visibility(enabled)

    def update_twitch_browser_content(self):
        """Initializes or resets the browser content."""
        template = """
        <html>
        <head>
            <style>
                @keyframes slideIn {
                    from { transform: translateX(-30px); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes fadeOut {
                    from { opacity: 1; }
                    to { opacity: 0; }
                }
                body { 
                    margin: 0; padding: 5px; 
                    overflow: hidden; 
                    background: transparent;
                    font-family: 'Segoe UI', Arial;
                    color: white;
                    display: flex;
                    flex-direction: column;
                    justify-content: flex-start;
                }
                #chat-log { width: 100%; }
                .message-container {
                    padding: 2px 0;
                    margin-bottom: 4px;
                    animation: slideIn 0.4s ease-out forwards;
                    font-weight: 800;
                    text-shadow: 2px 2px 2px #000, 0px 0px 4px #000;
                }
                .fade-out {
                    animation: fadeOut 1.0s forwards;
                }
                .user { font-weight: 900; text-shadow: 0px 0px 8px #000, 1px 1px 1px #000; }
                img { vertical-align: middle; max-height: 2em; }
            </style>
        </head>
        <body>
            <div id="chat-log"></div>
            <script>
                function addMessage(user, msg, userColor, fontSize, duration) {
                    const container = document.getElementById('chat-log');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message-container';
                    msgDiv.style.fontSize = fontSize + 'pt';
                    
                    msgDiv.innerHTML = `<span class="user" style="color: ${userColor}">${user}:</span> ${msg}`;
                    container.appendChild(msgDiv);
                    
                    if (container.children.length > 50) {
                        container.removeChild(container.firstChild);
                    }
                    
                    if (duration > 0) {
                        setTimeout(() => {
                            msgDiv.classList.add('fade-out');
                            setTimeout(() => msgDiv.remove(), 1000);
                        }, duration * 1000);
                    }
                }
                function clearChat() {
                    document.getElementById('chat-log').innerHTML = '';
                }
            </script>
        </body>
        </html>
        """
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.twitch_browser.setHtml(template, base_url)
        self.twitch_browser.show()

    def add_twitch_message(self, user, html_msg, color="#00f2ff", is_test=False):
        # 1. Check visibility
        enabled = True
        always_on = False
        game_running = False
        if self.gui_ref:
            enabled = self.gui_ref.config.get("twitch", {}).get("active", True)
            always_on = self.gui_ref.config.get("twitch", {}).get("always_on", False)
            game_running = getattr(self.gui_ref, 'ps2_running', False)

        should_process = is_test or (enabled and (game_running or always_on)) or self.edit_mode
        if not should_process: return

        self.chat_container.show()
        if not self.twitch_browser.isVisible():
            self.twitch_browser.show()

        # PATH FIX for WebEngine
        html_msg = html_msg.replace('src="emote://', 'src="file:///')
        html_msg = html_msg.replace('\\', '/')

        safe_color = self.get_readable_color(color)
        f_size = getattr(self, 'current_chat_font_size', 12)

        # Inject into JS
        js = f"addMessage({json.dumps(user)}, {json.dumps(html_msg)}, {json.dumps(safe_color)}, {json.dumps(f_size)}, {json.dumps(self.chat_hold_time)})"
        self.twitch_browser.page().runJavaScript(js)

        # Reset Auto-Hide timer (for the entire container)
        if self.chat_hold_time > 0:
            self.auto_hide_timer.start((self.chat_hold_time + 2) * 1000)

    def get_readable_color(self, hex_color):
        """Checks brightness and brightens dark colors."""
        hex_color = hex_color.lstrip('#')
        # From Hex to RGB
        r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

        # Calculate perceptive brightness
        luminance = (0.299 * r + 0.587 * g + 0.114 * b)

        # Threshold: Everything below 120 (of 255) is brightened
        if luminance < 120:
            # We add a fixed value to make the color more "pastel-like"
            # and vibrant without losing the hue
            r = min(255, r + 80)
            g = min(255, g + 80)
            b = min(255, b + 80)
            return f"#{r:02x}{g:02x}{b:02x}"

        return f"#{hex_color}"

    def fade_out_chat(self):
        """Hides the chat or clears it."""
        # Variant 1: Simply hide (recommended for performance)
        self.chat_container.hide()
        # Variant 2: Clear chat (if you want it to start empty next time)
        # self.twitch_browser.clear()

    def set_chat_hold_time(self, seconds):
        """Called by the GUI when the user changes the value."""
        self.chat_hold_time = int(seconds)
        if self.chat_hold_time == 0:
            self.auto_hide_timer.stop()
            self.chat_container.show()

    def clear_twitch_chat(self):
        """Clears the browser content."""
        self.twitch_browser.clear()
        self.add_log("TWITCH: Chat cleared.")

    # --- CACHE LOGIC ---
    def get_cached_pixmap(self, path):
        if not path:
            return QPixmap()

        # --- FIX: Self-healing for relative paths ---
        if not os.path.exists(path):
            resolved_path = get_asset_path(path)
            if os.path.exists(resolved_path):
                path = resolved_path
            else:
                return QPixmap()

        # --- MTIME CHECK (Hot-Reload fix) ---
        # We check if the file has changed
        try:
            current_mtime = os.path.getmtime(path)
        except OSError:
            return QPixmap()

        if not hasattr(self, 'pixmap_mtimes'):
            self.pixmap_mtimes = {}

        cached_mtime = self.pixmap_mtimes.get(path, 0)

        # If not in cache OR file is newer than cache -> Load new
        if path not in self.pixmap_cache or current_mtime > cached_mtime:
            pm = QPixmap(path)
            if not pm.isNull():
                self.pixmap_cache[path] = pm
                self.pixmap_mtimes[path] = current_mtime
                # print(f"DEBUG: Cache updated for {path}")
            else:
                return QPixmap()

        self.cache_usage_timestamps[path] = time.time()
        return self.pixmap_cache[path]


    def clear_cache(self):
        """In case images are swapped during operation (Reload)."""
        self.pixmap_cache.clear()

    def _asset_filename(self, path):
        if not path:
            return ""
        return os.path.basename(path).replace("\\", "/")

    def _broadcast_overlay(self, category, payload):
        if hasattr(self, "server") and self.server:
            self.server.broadcast(category, payload)

    def _resolve_event_cfg(self, event_name):
        if not self.gui_ref or not event_name:
            return {}
        events = self.gui_ref.config.get("events", {})
        cfg = events.get(event_name)
        if isinstance(cfg, dict):
            return cfg
        for key, val in events.items():
            if str(key).lower() == str(event_name).lower() and isinstance(val, dict):
                return val
        return {}

    def _event_impact_enabled(self, event_name):
        cfg = self._resolve_event_cfg(event_name)
        if "impact" in cfg:
            return bool(cfg.get("impact"))
        # Backward-compatible default behavior.
        return str(event_name).lower() in {"headshot", "death"}

    def _broadcast_stats_position_px(self, x_px, y_px):
        if not self._last_stats_payload:
            return
        payload = dict(self._last_stats_payload)
        payload["x"] = int(x_px)
        payload["y"] = int(y_px)
        self._last_stats_payload = payload
        self._broadcast_overlay("stats", payload)

    def reapply_stats_from_config(self):
        """Re-broadcast current stats with latest config offsets immediately."""
        if not self._last_stats_payload:
            return
        if not self.gui_ref:
            return

        conf = self.gui_ref.config.get("stats_widget", {})
        payload = dict(self._last_stats_payload)
        payload["x"] = int(self.s(conf.get("x", 50)))
        payload["y"] = int(self.s(conf.get("y", 500)))
        payload["tx"] = int(self.s(conf.get("tx", 0)))
        payload["ty"] = int(self.s(conf.get("ty", 0)))
        payload["scale"] = 1.0
        payload["padding"] = int(self.s(15))
        self._last_stats_payload = payload
        self._stats_web_visible = True
        self._broadcast_overlay("stats", payload)

    def clear_stats_web(self, force=False):
        if not force and not self._stats_web_visible:
            return
        self._stats_web_visible = False
        self._broadcast_overlay("stats_clear", {"ts": int(time.time() * 1000)})

    def clear_crosshair_web(self):
        self._broadcast_overlay("crosshair", {"enabled": False, "x": 0, "y": 0})

    def clear_streak_web(self):
        """Specifically hides the streak on the web HUD."""
        self._last_streak_payload = None
        self._broadcast_overlay("streak", {"visible": False})

    def _broadcast_streak_position_px(self, x_px, y_px):
        if not self._last_streak_payload:
            return
        payload = dict(self._last_streak_payload)
        payload["x"] = int(x_px)
        payload["y"] = int(y_px)
        self._last_streak_payload = payload
        self._broadcast_overlay("streak", payload)

    # --- QUEUE & DISPLAY LOGIC ---
    def _ensure_audio_routing(self):
        """After a sound plays, ensure PipeWire routes our stream to the correct sink.
        PipeWire's module-stream-restore remembers old routing, so new streams
        may get routed to the wrong sink. We fix this asynchronously via pw-link."""
        if IS_WINDOWS:
            return
        target = getattr(self, '_target_pw_sink', None)
        if not target:
            return
        
        # Run in a thread to avoid blocking the UI
        import threading
        def _do_move():
            try:
                import time as _time
                _time.sleep(0.1)  # Let PipeWire register the stream
                self._relink_sdl_to_sink(target)
            except Exception:
                pass
        
        threading.Thread(target=_do_move, daemon=True).start()

    def add_event_to_queue(self, img_path, sound_path, duration, x, y, scale=1.0, volume=1.0, is_hitmarker=False, play_duplicate=True, event_name=""):
        # --- CASE A: HITMARKER (Immediate & Parallel) ---

        master_vol = self.get_master_volume()

        if is_hitmarker:
            if sound_path:
                try:
                    if 'pygame' in sys.modules:
                        snd = pygame.mixer.Sound(sound_path)
                        snd.set_volume(volume * master_vol) # <--- Set volume
                        snd.play()
                        self._ensure_audio_routing()
                except:
                    pass

            if img_path and os.path.exists(img_path):
                self.show_hitmarker(img_path, duration, x, y, scale, event_name=event_name)

            return

        # --- CASE B: NORMAL EVENTS (Queue) ---
        if not hasattr(self, 'queue_enabled'): self.queue_enabled = True

        if not self.queue_enabled:
            # Queue off: show immediately in parallel (pooled)
            if sound_path:
                try:
                    if 'pygame' in sys.modules:
                        snd = pygame.mixer.Sound(sound_path)
                        snd.set_volume(volume * master_vol)
                        snd.play()
                        self._ensure_audio_routing()
                except:
                    pass

            self.display_image(img_path, duration, x, y, scale, event_name=event_name)
            return

        # Queue ON: Save with volume
        
        # --- PLAY DUPLICATE LOGIC ---
        if not play_duplicate:
            # Helper for robust comparison
            def is_same(p1, p2):
                if not p1 and not p2: return True
                if not p1 or not p2: return False
                try:
                    return os.path.normpath(p1) == os.path.normpath(p2)
                except:
                    return p1 == p2

            # Determine key for duplicate checking: Prefer event_name, fallback to (img, snd)
            check_key = event_name if event_name else (img_path, sound_path)

            # 1. Check currently showing event
            if self.is_showing and self.current_event_key:
                if event_name:
                    # Comparison by name
                    if self.current_event_key == event_name:
                        print(f"DEBUG: Skipped duplicate (active)")
                        return
                else:
                    # Legacy comparison by paths
                    curr_img, curr_snd = self.current_event_key
                    if is_same(curr_img, img_path) and is_same(curr_snd, sound_path):
                        return
            
            # 2. Check for existing duplicates in queue
            for item in self.event_queue:
                # item structure: (img_path, sound_path, duration, x, y, scale, volume, event_name)
                queued_name = item[7]
                
                if event_name and queued_name == event_name:
                    print(f"DEBUG: Skipped duplicate ({event_name})")
                    return
                elif not event_name:
                    # Legacy fallback
                    if is_same(item[0], img_path) and is_same(item[1], sound_path):
                        print(f"DEBUG: Skipped duplicate (legacy)")
                        return

        self.event_queue.append((img_path, sound_path, duration, x, y, scale, volume, event_name))

        if not self.is_showing:
            self.process_next_event()

    def show_hitmarker(self, img_path, duration, abs_x, abs_y, scale=1.0, event_name=""):
        if not img_path or not os.path.exists(img_path):
            return

        reader = QImageReader(img_path)
        size = reader.size()
        if size.isValid():
            w = int(size.width() * self.ui_scale * scale)
            h = int(size.height() * self.ui_scale * scale)
        else:
            w = self.s(180)
            h = self.s(180)

        if abs_x == 0 and abs_y == 0:
            px = int((self.width() // 2) - (w // 2))
            py = int((self.height() // 2) - (h // 2))
        else:
            px = int(self.s(abs_x))
            py = int(self.s(abs_y))

        self._broadcast_overlay("hitmarker", {
            "filename": self._asset_filename(img_path),
            "duration": int(duration if duration > 0 else 150),
            "x": px,
            "y": py,
            "scale": 1.0,
            "width": int(w),
            "height": int(h),
            "centered": False,
            "event_type": (event_name or "hitmarker").lower(),
            "impact": bool(self._event_impact_enabled(event_name or "hitmarker")),
        })

    def process_next_event(self):
        if not self.event_queue:
            self.is_showing = False
            return

        self.is_showing = True
        # Unpack volume from the tuple
        img_path, sound_path, duration, x, y, scale, event_vol, event_name = self.event_queue.pop(0)
        
        # Store key for duplicate checking (prefer name if set)
        self.current_event_key = event_name if event_name else (img_path, sound_path)

        self.display_image(img_path, duration, x, y, scale, event_name=event_name)

        if sound_path:
            try:
                if 'pygame' in sys.modules:
                    # Get fresh master volume (in case user moved slider during queue)
                    master_vol = self.get_master_volume()

                    snd = pygame.mixer.Sound(sound_path)
                    # CALCULATION HAPPENS HERE
                    snd.set_volume(event_vol * master_vol)
                    snd.play()
                    self._ensure_audio_routing()
            except:
                pass

        # Trigger the next one immediately (Parallel/Pooled)
        # Use singleShot to avoid infinite recursion / stack overflow
        QTimer.singleShot(0, self.process_next_event)

    def finish_current_event(self):
        self.current_event_key = None
        self.process_next_event()

    def clear_queue_now(self):
        self.event_queue.clear()
        self.queue_timer.stop()
        self.is_showing = False
        self.hide_all_events()

    def display_image(self, img_path, duration, abs_x, abs_y, scale=1.0, event_name=""):
        if not img_path or not os.path.exists(img_path):
            return
        reader = QImageReader(img_path)
        orig_size = reader.size()
        if orig_size.isValid():
            w = int(orig_size.width() * self.ui_scale * scale)
            h = int(orig_size.height() * self.ui_scale * scale)
        else:
            w = self.s(400)
            h = self.s(400)

        self._broadcast_overlay("event", {
            "filename": self._asset_filename(img_path),
            "duration": int(duration),
            "x": int(self.s(abs_x)),
            "y": int(self.s(abs_y)),
            "scale": 1.0,
            "width": int(w),
            "height": int(h),
            "event_type": (event_name or "event").lower(),
            "centered": False,
            "impact": bool(self._event_impact_enabled(event_name or "event")),
        })

    def _hide_image_specific(self, label):
        """Hides a single specific label from the pool."""
        label.clear()
        label.hide()
        label._is_busy = False # Free it up
        # If it was the 'main' event tracking name, we might want to clear it?
        if label == self.img_pool[0]:
            self.current_event_key = None

    def hide_all_events(self):
        """Clears queued/active visual events for the web HUD."""
        self.current_event_key = None
        self._broadcast_overlay("events_clear", {"ts": int(time.time() * 1000)})

    def _hide_image_safe(self):
        """Legacy helper for a single hide call (now targets all)."""
        self.hide_all_events()

    # --- CORE FUNCTIONS ---
    def resizeEvent(self, event):
        if hasattr(self, 'path_layer'):
            self.path_layer.setGeometry(self.rect())
        if hasattr(self, 'hud_view'):
            self.hud_view.setGeometry(self.rect())
        super().resizeEvent(event)

    def force_update(self):
        self.repaint()
        if self.path_edit_active: 
            self.path_layer.raise_()
        
        # Linux Fix: Periodically raise the window to stay on top
        if not IS_WINDOWS and self.isVisible() and not self.edit_mode:
            self.raise_()

    def s(self, value):
        return int(round(float(value) * self.ui_scale))

    def safe_move(self, widget, x, y):
        screen_w, screen_h = self.width(), self.height()
        w_w, w_h = widget.width(), widget.height()
        snap = 25

        if abs(x) < snap:
            x = 0
        elif abs(x - (screen_w - w_w)) < snap:
            x = screen_w - w_w
        elif abs(x - (screen_w // 2 - w_w // 2)) < snap:
            x = screen_w // 2 - w_w // 2

        if abs(y) < snap:
            y = 0
        elif abs(y - (screen_h - w_h)) < snap:
            y = screen_h - w_h
        elif abs(y - (screen_h // 2 - w_h // 2)) < snap:
            y = screen_h // 2 - w_h // 2

        final_x = max(0, min(int(x), screen_w - w_w))
        final_y = max(0, min(int(y), screen_h - w_h))
        widget.move(final_x, final_y)

    def set_mouse_passthrough(self, enabled=True, active_targets=None):
        """
        Activates or deactivates click-through transparency.
        IMPORTANT: Set Qt flags first, THEN show(), THEN ctypes styles!
        """
        # 1. Set Qt flags (Only if flags have changed, to avoid flickering)
        if IS_WINDOWS:
            new_flags = (Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        else:
            # Linux: ToolTip for maximum priority
            new_flags = (Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.ToolTip)
        
        if enabled:
            # 0. Clean visuals first
            self.clear_edit_visuals()
            self.active_edit_targets = []
            self.edit_mode = False
            new_flags |= Qt.WindowType.WindowTransparentForInput
            if not IS_WINDOWS:
                new_flags |= Qt.WindowType.X11BypassWindowManagerHint # <--- Persistent Linux Fix
        else:
            self.edit_mode = True
            self.active_edit_targets = active_targets if active_targets else []

        # Only switch if the flags actually change
        if self.windowFlags() != new_flags:
            self.setWindowFlags(new_flags)
            self.show()  # show() must be called after setWindowFlags

        # 2. Show (again) so it gets a valid handle
        self.show()

        # If edit mode: Force focus, otherwise clicks land in-game
        if not enabled:
            self.activateWindow()
            self.raise_()
            # ALWAYS hide real chat when in edit mode - prevents blocking!
            self.chat_container.hide()
        else:
            self.clearMask()

        # 3. Apply Windows API styles (to the NEW handle!)
        if IS_WINDOWS:
            try:
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x80000
                WS_EX_TRANSPARENT = 0x20

                # Get current style
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

                if enabled:
                    # Make transparent (layered + transparent)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                    if hasattr(self, 'event_preview_label'):
                        self.event_preview_label.hide()
                else:
                    # Make interactable (remove transparent bit)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED)

                    # --- VISUALS FOR EDIT MODE ---
                    hl_style = "border: 2px solid #00ff00; background-color: rgba(0, 255, 0, 50);"
                    targets = active_targets if active_targets else []

                    if "feed" in targets:
                        feed_style = "border: 2px solid #00ff00; background-color: rgba(0, 0, 0, 150);"
                        self.feed_label.setStyleSheet(feed_style)
                        self.feed_label.show()
                        self.feed_label.raise_()
                        
                        # Ensure minimum size for dragging even if text is empty
                        if not self.feed_label.text().strip():
                            self.feed_label.setText(
                                "<div style='color:white; font-size:20px; padding:10px;'>KILLFEED DRAG AREA</div>")
                            self.feed_label.adjustSize()
                        
                        # Prevent it from being 0-height if adjustSize was called elsewhere
                        if self.feed_label.height() < 50:
                            self.feed_label.setFixedHeight(100)

                    if "stats" in targets:
                        self.stats_bg_label.setStyleSheet(hl_style)
                        self.stats_bg_label.show()
                        self.stats_text_label.hide()

                    if "streak" in targets:
                        self.streak_bg_label.setStyleSheet(hl_style)
                        self.streak_bg_label.show()
                        if not self.streak_bg_label.pixmap() or self.streak_bg_label.pixmap().isNull():
                            self.streak_bg_label.setText("STREAK AREA")
                            self.streak_bg_label.setStyleSheet(f"{hl_style} color: white; font-weight: bold;")
                            self.streak_bg_label.adjustSize()

                    if "crosshair" in targets:
                        self.crosshair_label.setStyleSheet(hl_style)
                        self.crosshair_label.show()

                    if "event" in targets:
                        if hasattr(self, 'event_preview_label'):
                            self.event_preview_label.setStyleSheet(hl_style)
                            self.event_preview_label.show()
                            self.event_preview_label.raise_()

                    if "twitch" in targets:
                        # We do NOT show the real layout with WebEngines (click issues!),
                        # but the drag-cover, which reliably passes clicks to QtOverlay.
                        self.twitch_drag_cover.setStyleSheet(hl_style)
                        self.twitch_drag_cover.show()
                        self.twitch_drag_cover.raise_()
                        # We hide the real chat so it doesn't interfere
                        self.chat_container.hide()
                    self.update_edit_mask(targets)

            except Exception as e:
                print(f"Passthrough Error: {e}")
        elif not enabled:
            hl_style = "border: 2px solid #00ff00; background-color: rgba(0, 255, 0, 50);"
            targets = active_targets if active_targets else []

            if "feed" in targets:
                feed_style = "border: 2px solid #00ff00; background-color: rgba(0, 0, 0, 150);"
                self.feed_label.setStyleSheet(feed_style)
                self.feed_label.show()
                self.feed_label.raise_()

                # Ensure minimum size for dragging even if text is empty
                if not self.feed_label.text().strip():
                    self.feed_label.setText(
                        "<div style='color:white; font-size:20px; padding:10px;'>KILLFEED DRAG AREA</div>")
                    self.feed_label.adjustSize()

                # Prevent it from being 0-height if adjustSize was called elsewhere
                if self.feed_label.height() < 50:
                    self.feed_label.setFixedHeight(100)

            if "stats" in targets:
                self.stats_bg_label.setStyleSheet(hl_style)
                self.stats_bg_label.show()
                self.stats_text_label.hide()

            if "streak" in targets:
                self.streak_bg_label.setStyleSheet(hl_style)
                self.streak_bg_label.show()
                if not self.streak_bg_label.pixmap() or self.streak_bg_label.pixmap().isNull():
                    self.streak_bg_label.setText("STREAK AREA")
                    self.streak_bg_label.setStyleSheet(f"{hl_style} color: white; font-weight: bold;")
                    self.streak_bg_label.adjustSize()

            if "crosshair" in targets:
                self.crosshair_label.setStyleSheet(hl_style)
                self.crosshair_label.show()

            if "event" in targets:
                if hasattr(self, 'event_preview_label'):
                    self.event_preview_label.setStyleSheet(hl_style)
                    self.event_preview_label.show()
                    self.event_preview_label.raise_()

            if "twitch" in targets:
                # We do NOT show the real layout with WebEngines (click issues!),
                # but the drag-cover, which reliably passes clicks to QtOverlay.
                self.twitch_drag_cover.setStyleSheet(hl_style)
                self.twitch_drag_cover.show()
                self.twitch_drag_cover.raise_()
                # We hide the real chat so it doesn't interfere
                self.chat_container.hide()
            self.update_edit_mask(targets)
        elif hasattr(self, 'event_preview_label'):
            self.event_preview_label.hide()

    def update_edit_mask(self, targets):
        """Limits clicks to all active elements, the rest becomes click-through."""
        if not targets:
            self.clearMask()
            return

        combined_region = QRegion()
        
        for target in targets:
            widget = None
            if target == "event":
                widget = self.event_preview_label
            elif target == "feed":
                widget = self.feed_label
            elif target == "stats":
                widget = self.stats_bg_label
            elif target == "streak":
                widget = self.streak_bg_label
            elif target == "crosshair":
                widget = self.crosshair_label
            elif target == "twitch":
                widget = self.twitch_drag_cover
                
            if widget and widget.isVisible():
                combined_region = combined_region.united(QRegion(widget.geometry()))

        if not combined_region.isEmpty():
            self.setMask(combined_region)
        else:
            self.clearMask()

    def clear_edit_visuals(self):
        """Removes all edit frames and resets labels to normal state."""
        # Stats
        if hasattr(self, 'stats_bg_label'):
            self.stats_bg_label.setStyleSheet("background: transparent;")
        if hasattr(self, 'stats_text_label'):
            self.stats_text_label.hide()
        
        # Twitch
        if hasattr(self, 'chat_container'):
            # Reset style to what update_twitch_style would set
            enabled = True
            if self.gui_ref:
                enabled = self.gui_ref.config.get("twitch", {}).get("active", True)
                self.update_twitch_style(
                    self.chat_container.x(), self.chat_container.y(),
                    self.chat_container.width(), self.chat_container.height(),
                    self.gui_ref.config.get("twitch", {}).get("opacity", 30),
                    self.gui_ref.config.get("twitch", {}).get("font_size", 12)
                )
            if not enabled:
                self.chat_container.hide()
            else:
                self.chat_container.show()
        
        # Twitch Drag Cover verstecken
        if hasattr(self, 'twitch_drag_cover'):
            self.twitch_drag_cover.hide()
        
        # Killfeed
        if hasattr(self, 'feed_label'):
            self.feed_label.setStyleSheet("background: transparent;")
            # If there was only dummy text, clear (optional, but cleaner)
            if "DRAG AREA" in self.feed_label.text():
                self.feed_label.setText("")
        
        # Streak
        if hasattr(self, 'streak_bg_label'):
            self.streak_bg_label.setStyleSheet("background: transparent;")
            if "STREAK AREA" in self.streak_bg_label.text():
                self.streak_bg_label.setText("")

        # Crosshair
        if hasattr(self, 'crosshair_label'):
            self.crosshair_label.setStyleSheet("background: transparent;")

        # Event Preview
        if hasattr(self, 'event_preview_label'):
            self.event_preview_label.setStyleSheet("background: transparent;")
            self.event_preview_label.hide()

    # --- MOUSE EVENTS (DRAG & DROP) ---
    def mousePressEvent(self, event):
        if getattr(self, "path_edit_active", False): return
        if not self.edit_mode: return
        pos = event.pos()
        if self.event_preview_label.isVisible() and self.event_preview_label.geometry().contains(pos):
            self.dragging_widget = "event"
            self.drag_offset = pos - self.event_preview_label.pos()
        elif "border" in self.feed_label.styleSheet() and self.feed_label.geometry().contains(pos):
            self.dragging_widget = "feed"
            self.drag_offset = pos - self.feed_label.pos()
        elif "border" in self.stats_bg_label.styleSheet() and self.stats_bg_label.geometry().contains(pos):
            self.dragging_widget = "stats"
            self.drag_offset = pos - self.stats_bg_label.pos()
        elif "border" in self.streak_bg_label.styleSheet() and self.streak_bg_label.geometry().contains(pos):
            self.dragging_widget = "streak"
            self.drag_offset = pos - self.streak_bg_label.pos()
        elif "border" in self.crosshair_label.styleSheet() and self.crosshair_label.geometry().contains(pos):
            self.dragging_widget = "crosshair"
            self.drag_offset = pos - self.crosshair_label.pos()
        elif self.twitch_drag_cover.isVisible() and self.twitch_drag_cover.geometry().contains(pos):
            self.dragging_widget = "twitch"
            self.drag_offset = pos - self.twitch_drag_cover.pos()

    def mouseMoveEvent(self, event):
        if not self.edit_mode or not self.dragging_widget or not self.drag_offset: return
        new_pos = event.pos() - self.drag_offset

        if self.dragging_widget == "event":
            self.safe_move(self.event_preview_label, new_pos.x(), new_pos.y())
        elif self.dragging_widget == "feed":
            self.safe_move(self.feed_label, new_pos.x(), new_pos.y())
        elif self.dragging_widget == "crosshair":
            self.safe_move(self.crosshair_label, new_pos.x(), new_pos.y())
        elif self.dragging_widget == "stats":
            self.safe_move(self.stats_bg_label, new_pos.x(), new_pos.y())
            self._broadcast_stats_position_px(self.stats_bg_label.x(), self.stats_bg_label.y())
            self.notify_item_moved_unscaled("stats", self.stats_bg_label.x(), self.stats_bg_label.y())
            if self.gui_ref:
                cfg = self.gui_ref.config.get("stats_widget", {})
                bg_w, bg_h = self.stats_bg_label.width(), self.stats_bg_label.height()
                txt_w, txt_h = self.stats_text_label.width(), self.stats_text_label.height()
                tx_off, ty_off = self.s(cfg.get("tx", 0)), self.s(cfg.get("ty", 0))
                cx, cy = new_pos.x() + (bg_w / 2), new_pos.y() + (bg_h / 2)
                final_tx = cx - (txt_w / 2) + tx_off
                final_ty = cy - (txt_h / 2) + ty_off
                self.safe_move(self.stats_text_label, int(final_tx), int(final_ty))
        elif self.dragging_widget == "streak":
            self.safe_move(self.streak_bg_label, new_pos.x(), new_pos.y())
            self._broadcast_streak_position_px(self.streak_bg_label.x(), self.streak_bg_label.y())
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                cx = self.streak_bg_label.x() + (self.streak_bg_label.width() // 2)
                cy = self.streak_bg_label.y() + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label,
                               cx + self.s(cfg.get("tx", 0)) - (self.streak_text_label.width() // 2),
                               cy + self.s(cfg.get("ty", 0)) - (self.streak_text_label.height() // 2))
        elif self.dragging_widget == "twitch":
            self.safe_move(self.twitch_drag_cover, new_pos.x(), new_pos.y())
            # We drag the actual container object along
            self.chat_container.move(self.twitch_drag_cover.pos())
            # Update GUI Sliders via Signal
            self.notify_chat_moved(new_pos.x(), new_pos.y())
            
        # Refresh the mask for ALL active targets so nothing disappears
        self.update_edit_mask(self.active_edit_targets)

    def mouseReleaseEvent(self, event):
        if not self.edit_mode or not self.dragging_widget: return

        def uns(val):
            return int(round(val / self.ui_scale))

        if self.gui_ref:
            if self.dragging_widget == "event":
                curr = self.event_preview_label.pos()
                ename = self.gui_ref.ovl_config_win.lbl_editing.text().replace("EDITING: ", "").strip()
                if "events" not in self.gui_ref.config: self.gui_ref.config["events"] = {}
                if ename not in self.gui_ref.config["events"]: self.gui_ref.config["events"][ename] = {}
                self.gui_ref.config["events"][ename]["x"] = uns(curr.x())
                self.gui_ref.config["events"][ename]["y"] = uns(curr.y())
                self.gui_ref.save_config()
            elif self.dragging_widget == "crosshair":
                curr = self.crosshair_label.pos()
                center_x = curr.x() + (self.crosshair_label.width() / 2)
                center_y = curr.y() + (self.crosshair_label.height() / 2)
                if "crosshair" not in self.gui_ref.config: self.gui_ref.config["crosshair"] = {}
                self.gui_ref.config["crosshair"]["x"] = uns(center_x)
                self.gui_ref.config["crosshair"]["y"] = uns(center_y)
                self.gui_ref.save_config()
            elif self.dragging_widget == "feed":
                curr = self.feed_label.pos()
                if "killfeed" not in self.gui_ref.config: self.gui_ref.config["killfeed"] = {}
                self.gui_ref.config["killfeed"]["x"] = uns(curr.x())
                self.gui_ref.config["killfeed"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
            elif self.dragging_widget == "stats":
                curr = self.stats_bg_label.pos()
                if "stats_widget" not in self.gui_ref.config: self.gui_ref.config["stats_widget"] = {}
                self.gui_ref.config["stats_widget"]["x"] = uns(curr.x())
                self.gui_ref.config["stats_widget"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
                self._broadcast_stats_position_px(curr.x(), curr.y())
                self.notify_item_moved_unscaled("stats", curr.x(), curr.y())
            elif self.dragging_widget == "streak":
                curr = self.streak_bg_label.pos()
                if "streak" not in self.gui_ref.config: self.gui_ref.config["streak"] = {}
                self.gui_ref.config["streak"]["x"] = uns(curr.x())
                self.gui_ref.config["streak"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
                self._broadcast_streak_position_px(curr.x(), curr.y())
            elif self.dragging_widget == "twitch":
                curr = self.twitch_drag_cover.pos()
                if "twitch" not in self.gui_ref.config: self.gui_ref.config["twitch"] = {}
                self.gui_ref.config["twitch"]["x"] = uns(curr.x())
                self.gui_ref.config["twitch"]["y"] = uns(curr.y())
                self.gui_ref.save_config()

        self.dragging_widget = None
        self.drag_offset = None

    def keyPressEvent(self, event):
        if self.path_edit_active and event.key() == Qt.Key.Key_Space:
            if self.gui_ref: self.gui_ref.start_path_record()
            event.accept()
            return
        super().keyPressEvent(event)

    # --- ELEMENT UPDATES ---
    def add_killfeed_row(self, html_msg):
        # We now store the UN-SCALED message
        self.feed_messages.insert(0, html_msg)
        self.feed_messages = self.feed_messages[:6]
        self.update_killfeed_ui()
        
        # Broadcast (unscaled for server)
        kf_x, kf_y = 50, 200  # Defaults
        if self.gui_ref:
            conf = self.gui_ref.config.get("killfeed", {})
            kf_x = conf.get("x", 50)
            kf_y = conf.get("y", 200)
            auto_remove = bool(conf.get("auto_remove", True))
            stay_seconds = int(conf.get("stay_seconds", 10))
        else:
            auto_remove = True
            stay_seconds = 10
        hold_ms = max(0, stay_seconds * 1000)

        self._broadcast_overlay("feed", {
            "html": html_msg,
            "x": int(self.s(kf_x)),
            "y": int(self.s(kf_y)),
            "width": int(self.feed_w),
            "height": int(self.feed_h),
            "max_items": 6,
            "hold_ms": int(hold_ms),
            "auto_remove": bool(auto_remove),
            "ui_scale": float(self.ui_scale),
        })

    def update_killfeed_ui(self):
        if not self.gui_ref:
            return
        conf = self.gui_ref.config.get("killfeed", {})
        self._broadcast_overlay("feed_config", {
            "x": int(self.s(conf.get("x", 50))),
            "y": int(self.s(conf.get("y", 200))),
            "width": int(self.feed_w),
            "height": int(self.feed_h),
            "ui_scale": float(self.ui_scale),
        })

    def clear_killfeed(self):
        self.feed_messages = []
        self._broadcast_overlay("feed_clear", {"ts": int(time.time() * 1000)})

    def update_killfeed_pos(self):
        if not self.gui_ref: return
        conf = self.gui_ref.config.get("killfeed", {})
        self._broadcast_overlay("feed_config", {
            "x": int(self.s(conf.get("x", 50))),
            "y": int(self.s(conf.get("y", 200))),
            "width": int(self.feed_w),
            "height": int(self.feed_h),
            "ui_scale": float(self.ui_scale),
        })

    def update_stats_display(self, stats_data, is_dummy=False):
        if not self.gui_ref: return
        
        cfg = self.gui_ref.config.get("stats_widget", {})
        
        # 1. READ VALUES
        if is_dummy:
            kills, deaths, hs, hsrkill, dhs = 1337, 12, 600, 1337, 3
            dhs_eligible = 10
            start_t = time.time() - 5000
            revives = 0 # Dummy check handles this below
        else:
            kills = stats_data.get("k", 0)
            deaths = stats_data.get("d", 0)
            hs = stats_data.get("hs", 0)
            hsrkills = stats_data.get("hsrkill", 0)
            dhs = stats_data.get("dhs", 0) # Death Headshots
            dhs_eligible = stats_data.get("dhs_eligible", 0) # Headshot-eligible Deaths
            start_t = stats_data.get("start", time.time())
            revives = stats_data.get("revives_received", 0)

        # KD Logic (Revive vs Real)
        kd_mode_revive = getattr(self.gui_ref, 'kd_mode_revive', True)
        eff_deaths = max(0, deaths - revives) if kd_mode_revive else deaths
        kd = kills / max(1, eff_deaths)
        
        # HSR Logic
        calc_base = hsrkills if not is_dummy and hsrkills > 0 else kills
        hsr = (hs / calc_base * 100) if calc_base > 0 else 0.0

        # DHSR Logic (Death Headshot Ratio)
        # We only look at weapons that CAN headshot (matching HSR logic)
        d_calc_base = dhs_eligible if not is_dummy and dhs_eligible > 0 else (dhs_eligible if is_dummy else deaths)
        dhsr = (dhs / max(1, d_calc_base) * 100)
        
        # Total Session Time Logic (with Pause/Resume support)
        acc_t = stats_data.get("acc_t", 0)
        now = time.time()
        
        if start_t > 0:
            total_sec = acc_t + (now - start_t)
        else:
            total_sec = acc_t

        # Session Time String
        ts = int(total_sec)
        m, s = divmod(ts, 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        # KPM/KPH Logic (Using total_sec)
        duration_min = total_sec / 60
        kpm = kills / duration_min if duration_min > 0 else 0.0
        kph = kpm * 60

        # 2. BUILD HTML PARTS
        parts = []
        f_size = int(cfg.get("font_size", 22))
        
        # Colors from Config
        label_col = cfg.get("label_color", "#00f2ff")
        val_col = cfg.get("value_color", "#ffffff")
        
        # Base Style
        # Match killfeed text styling for consistent sharpness.
        if bool(cfg.get("glow", True)):
            shadow_css = "text-shadow: 1px 1px 2px #000, 0 0 6px rgba(0, 242, 255, 0.72), 0 0 12px rgba(0, 242, 255, 0.38);"
        else:
            shadow_css = "text-shadow: 1px 1px 2px #000;"
        style_base = (
            f"font-family: 'Black Ops One', sans-serif; "
            f"font-size: {f_size}px; "
            f"color: {label_col}; "
            f"{shadow_css} "
            f"white-space: nowrap;"
        )
        
        def wrap(label, val, color=None):
            # If no color is provided, use the value color from config
            if color is None: color = val_col
            return f'{label}: <span style="color: {color};">{val}</span>'

        # KD
        if cfg.get("show_kd", True):
            # Dynamic KD color based on performance
            kd_col = "#00ff00" if kd >= 2.0 else ("#ffff00" if kd >= 1.0 else "#ff4444")
            parts.append(wrap("KD", f"{kd:.2f}", kd_col))

        # Toggles
        if cfg.get("show_k", True):
            parts.append(wrap("K", kills))
        if cfg.get("show_d", True):
            parts.append(wrap("D", eff_deaths))
        if cfg.get("show_hsr", True):
            parts.append(wrap("HSR", f"{hsr:.0f}%"))
        if cfg.get("show_kpm", True):
            parts.append(wrap("KPM", f"{kpm:.1f}"))
        if cfg.get("show_kph", True):
            parts.append(wrap("KPH", f"{int(kph)}"))
        if cfg.get("show_dhsr", True):
            # DHSR color should ideally match standard values unless very high/problematic
            parts.append(wrap("DHSR", f"{dhsr:.0f}%"))
        if cfg.get("show_time", True):
            parts.append(f'<span style="color: #aaa;">TIME: {time_str}</span>')

        # 3. COMBINE
        # Use div/span instead of table to keep text rendering as sharp as killfeed in Chromium.
        cells = [f'<span style="display:inline-block; margin: 0 10px;">{p}</span>' for p in parts]
        full_html = f'<div style="{style_base} display:inline-block; white-space: nowrap;">{"".join(cells)}</div>'


        # 4. SEND TO RENDERER
        self.set_stats_html(full_html)

    def set_stats_html(self, html, img_path=""):
        # Change Detection: Only update when necessary
        scaled_html = html

        # Get position & Apply
        st_x, st_y = 50, 500
        tx_off, ty_off = 0, 0
        st_glow = True
        box_w, box_h = int(self.s(600)), int(self.s(60))
        if self.gui_ref:
            conf = self.gui_ref.config.get("stats_widget", {})
            st_x = conf.get("x", 50)
            st_y = conf.get("y", 500)
            tx_off = conf.get("tx", 0)
            ty_off = conf.get("ty", 0)
            st_glow = bool(conf.get("glow", True))

        payload = {
            "html": scaled_html,
            "bg_filename": "",
            "x": int(self.s(st_x)),
            "y": int(self.s(st_y)),
            "tx": int(self.s(tx_off)),
            "ty": int(self.s(ty_off)),
            "scale": 1.0,
            "padding": int(self.s(15)),
            "box_width": int(box_w),
            "box_height": int(box_h),
            "glow": bool(st_glow),
            "ui_scale": float(self.ui_scale),
        }

        # If stats were cleared meanwhile, force a rebroadcast even for identical payload.
        if payload == self._last_stats_payload and img_path == self._last_stats_img and self._stats_web_visible:
            return

        self._last_stats_html = scaled_html
        self._last_stats_img = img_path
        self._last_stats_payload = payload
        self._stats_web_visible = True
        self._broadcast_overlay("stats", payload)

    def draw_streak_ui(self, img_path, count, factions, cfg, slot_map):
        if (not cfg.get("active", True) and not self.edit_mode) or (count <= 0 and not self.edit_mode):
            # Throttle: Only broadcast 'hidden' once.
            if self._last_streak_payload is not None:
                self._last_streak_payload = None
                self._broadcast_overlay("streak", {"visible": False})
            return

        if not img_path or not os.path.exists(img_path):
            self._last_streak_payload = None
            self._broadcast_overlay("streak", {"visible": False})
            return

        cnt = count if count > 0 else 10
        base_scale = float(cfg.get("scale", 1.0))
        sc = base_scale * self.ui_scale

        reader = QImageReader(img_path)
        size = reader.size()
        if size.isValid():
            bg_w = int(size.width() * sc)
            bg_h = int(size.height() * sc)
        else:
            bg_w = self.s(220)
            bg_h = self.s(220)

        # Keep a synchronized Qt preview anchor for Move UI and path recording.
        show_qt_preview = bool(getattr(self, "path_edit_active", False) or
                               (self.edit_mode and "streak" in getattr(self, "active_edit_targets", [])))
        try:
            pix = self.get_cached_pixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(bg_w, bg_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.streak_bg_label.setPixmap(pix)
                self.streak_bg_label.setText("")
                self.streak_bg_label.setFixedSize(bg_w, bg_h)
                self.streak_bg_label.adjustSize()
                self.safe_move(self.streak_bg_label, self.s(cfg.get("x", 100)), self.s(cfg.get("y", 100)))
                if show_qt_preview:
                    self.streak_bg_label.show()
                else:
                    self.streak_bg_label.hide()
                    self.streak_text_label.hide()
        except Exception:
            pass

        knives = []
        if cfg.get("show_knives", True):
            k_per_circle = 50
            rad_step = self.s(22)
            knife_size = self.s(90)
            path_data = cfg.get("custom_path", []) or []

            if len(path_data) > 2:
                segments = []
                total_l = 0.0
                pts = [QPoint(int(p[0]), int(p[1])) for p in path_data]
                for i in range(len(pts)):
                    p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                    d = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
                    segments.append((p1, p2, d, total_l))
                    total_l += d

                if total_l > 0:
                    k_per_ring = 50
                    for i, ftag in enumerate(factions):
                        kfile = cfg.get(f"knife_{ftag.lower()}", f"knife_{ftag.lower()}.png")
                        kpath = get_asset_path(kfile)
                        if not os.path.exists(kpath):
                            continue

                        sidx = slot_map[i] if slot_map and i < len(slot_map) else i
                        ridx = sidx // k_per_ring
                        posring = sidx % k_per_ring
                        rscale = 1.0 + (ridx * 0.28)
                        tdist = (posring / k_per_ring) * total_l
                        kx_off, ky_off = 0.0, 0.0
                        for p1, p2, seg_d, start_l in segments:
                            if start_l <= tdist <= start_l + seg_d and seg_d > 0:
                                t = (tdist - start_l) / seg_d
                                kx_off = (p1.x() + t * (p2.x() - p1.x())) * rscale
                                ky_off = (p1.y() + t * (p2.y() - p1.y())) * rscale
                                break
                        angle = math.degrees(math.atan2(ky_off, kx_off)) + 90.0
                        knives.append({
                            "filename": self._asset_filename(kpath),
                            "x_off": float(kx_off),
                            "y_off": float(ky_off),
                            "rotation": float(angle),
                            "size": int(knife_size),
                            "faction": str(ftag),
                        })
            else:
                sx = (bg_w // 2) - self.s(15)
                sy = (bg_h // 2) - self.s(15)
                for i, ftag in enumerate(factions):
                    kfile = cfg.get(f"knife_{ftag.lower()}", f"knife_{ftag.lower()}.png")
                    kpath = get_asset_path(kfile)
                    if not os.path.exists(kpath):
                        continue

                    sidx = slot_map[i] if slot_map and i < len(slot_map) else i
                    ridx = sidx // k_per_circle
                    posring = sidx % k_per_circle
                    angle = (posring * (360.0 / k_per_circle)) - 90.0
                    rad = math.radians(angle)
                    s_val = math.sin(rad)
                    narrow = 1.0 - (0.15 * s_val) if s_val > 0 else 1.0
                    kx_off = (sx + (ridx * rad_step)) * narrow * math.cos(rad)
                    ky_off = -self.s(20) + (sy + (ridx * rad_step)) * math.sin(rad)
                    knives.append({
                        "filename": self._asset_filename(kpath),
                        "x_off": float(kx_off),
                        "y_off": float(ky_off),
                        "rotation": float(angle + 90.0),
                        "size": int(knife_size),
                        "faction": str(ftag),
                    })

        payload = {
            "visible": True,
            "bg_filename": self._asset_filename(img_path),
            "bg_width": int(bg_w),
            "bg_height": int(bg_h),
            "x": int(self.s(cfg.get("x", 100))),
            "y": int(self.s(cfg.get("y", 100))),
            "scale": 1.0,
            "count": int(cnt),
            "tx": int(self.s(cfg.get("tx", 0))),
            "ty": int(self.s(cfg.get("ty", 0))),
            "font_size": int(cfg.get("size", 26) * sc),
            "color": cfg.get("color", "#ffffff"),
            "bold": bool(cfg.get("bold")),
            "anim_active": bool(cfg.get("anim_active", True)),
            "anim_speed": int(cfg.get("speed", 50)),
            "streak_glow": bool(cfg.get("streak_glow", cfg.get("knife_glow", True))),
            "knives": knives,
            "ui_scale": float(self.ui_scale),
        }
        if getattr(self, "path_edit_active", False):
            self._last_streak_payload = payload
            self._broadcast_overlay("streak", {"visible": False})
            self.path_layer.raise_()
            return

        self._last_streak_payload = payload
        self._broadcast_overlay("streak", payload)
        if getattr(self, "path_edit_active", False):
            self.path_layer.raise_()

    def _place_knife(self, lbl, path, kx, ky, angle, is_new, center):
        # --- CACHE USED (IMPORTANT!) ---
        base_pix = self.get_cached_pixmap(path)
        if base_pix.isNull(): return

        # Create transformation from RAM image (copy)
        pix = base_pix.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        pix = pix.scaled(self.s(90), self.s(90), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)

        lbl.setPixmap(pix);
        lbl.adjustSize()
        lbl._base_off_x, lbl._base_off_y = kx - center.x(), ky - center.y()
        lbl._is_active = True
        if is_new: lbl._spawn_time = time.time()
        self.safe_move(lbl, kx - (lbl.width() // 2), ky - (lbl.height() // 2))
        lbl.show()

    def animate_pulse(self):
        # Legacy timer kept to avoid touching external signal wiring.
        # Streak pulse animation is now handled via CSS keyframes on the web HUD.
        return

    def update_crosshair(self, path, size, enabled):
        crosshair_cfg = {}
        if self.gui_ref:
            crosshair_cfg = self.gui_ref.config.get("crosshair", {})
        editing_crosshair = bool(self.edit_mode and "crosshair" in getattr(self, "active_edit_targets", []))

        rx, ry = crosshair_cfg.get("x", 0), crosshair_cfg.get("y", 0)
        if rx == 0 and ry == 0:
            tx = self.width() // 2
            ty = self.height() // 2
        else:
            tx = self.s(rx)
            ty = self.s(ry)

        # Keep a synchronized Qt preview for Move UI/edit mode.
        # Runtime rendering is done by the web HUD.
        try:
            preview_size = max(8, int(round(float(size) * self.ui_scale)))
            pix = self.get_cached_pixmap(path) if path else QPixmap()
            if not pix.isNull():
                pix = pix.scaled(preview_size, preview_size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                self.crosshair_label.setPixmap(pix)
                self.crosshair_label.setFixedSize(pix.size())
                self.crosshair_label.adjustSize()
                if bool(crosshair_cfg.get("shadow", False)):
                    sh = QGraphicsDropShadowEffect()
                    sh.setBlurRadius(max(1.5, 3.0 * self.ui_scale))
                    sh.setColor(QColor(0, 0, 0, 190))
                    sh.setXOffset(0)
                    sh.setYOffset(0)
                    self.crosshair_label.setGraphicsEffect(sh)
                else:
                    self.crosshair_label.setGraphicsEffect(None)
                self.safe_move(
                    self.crosshair_label,
                    int(tx - (self.crosshair_label.width() / 2)),
                    int(ty - (self.crosshair_label.height() / 2))
                )
            else:
                self.crosshair_label.setPixmap(QPixmap())
                self.crosshair_label.setText("CROSSHAIR")
                self.crosshair_label.setGraphicsEffect(None)
                self.crosshair_label.adjustSize()
                self.safe_move(
                    self.crosshair_label,
                    int(tx - (self.crosshair_label.width() / 2)),
                    int(ty - (self.crosshair_label.height() / 2))
                )
        except Exception:
            pass

        # Preview label should only be visible while editing.
        if self.edit_mode and "crosshair" in getattr(self, "active_edit_targets", []):
            self.crosshair_label.show()
            self.crosshair_label.raise_()
        else:
            self.crosshair_label.hide()

        if editing_crosshair:
            self._broadcast_overlay("crosshair", {
                "enabled": False,
                "x": int(tx),
                "y": int(ty),
            })
            return

        if (not enabled and not self.edit_mode) or not path or not os.path.exists(path):
            self._broadcast_overlay("crosshair", {
                "enabled": False,
                "x": int(tx),
                "y": int(ty),
            })
            return

        self._broadcast_overlay("crosshair", {
            "enabled": True,
            "filename": self._asset_filename(path),
            "x": int(tx),
            "y": int(ty),
            "size": int(size),
            "scale": float(self.ui_scale),
            "shadow": bool(crosshair_cfg.get("shadow", False)),
            "ui_scale": float(self.ui_scale),
        })

    def update_twitch_visibility(self, enabled):
        """Decides whether the chat container is allowed to be actually visible."""
        game_running = False
        always_on = False

        if self.gui_ref:
            game_running = getattr(self.gui_ref, 'ps2_running', False)
            always_on = self.gui_ref.config.get("twitch", {}).get("always_on", False)

        # The golden rule:
        # Visible if (Activated AND (Game is running OR Always-On)) OR (We are editing)
        should_show = (enabled and (game_running or always_on)) or self.edit_mode

        if should_show:
            self.chat_container.show()
        else:
            self.chat_container.hide()
    # --- SERVER MANAGEMENT ---
    def start_server(self):
        """Starts the local web server for OBS integration."""
        if self.gui_ref:
            obs_cfg = self.gui_ref.config.get("obs_service", {
                "enabled": True,
                "port": 8000,
                "ws_port": 6789
            })
            h_port = obs_cfg.get("port", 8000)
            w_port = obs_cfg.get("ws_port", 6789)
        else:
            h_port = 8000
            w_port = 6789

        if self.server and self.server.is_running:
            same_ports = (self.server.http_port == h_port and self.server.ws_port == w_port)
            if same_ports:
                self.load_web_overlay(h_port)
                return
            self.stop_server()

        try:
            self.server = OverlayServer(http_port=h_port, ws_port=w_port)
            self.server.start()
            print(f"OBS SERVICE: Started on port {h_port} (WS: {w_port})")
            self.load_web_overlay(h_port)
        except Exception as e:
            print(f"OBS SERVICE ERROR: Could not start server: {e}")

    def load_web_overlay(self, http_port):
        if not hasattr(self, 'hud_view'):
            return
        self.hud_view.load(QUrl(f"http://127.0.0.1:{int(http_port)}/"))
        self.hud_view.raise_()
        if hasattr(self, 'path_layer') and self.path_edit_active:
            self.path_layer.raise_()

    def stop_server(self):
        """Stops the local web server."""
        if self.server:
            self.server.stop()
            self.server = None
            print("OBS SERVICE: Stopped.")
