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

# Aus QtCore kommen die Logik- und Animations-Klassen
from PyQt6.QtCore import (Qt, pyqtSignal, QObject, QTimer, QPoint,
                            QSize, QUrl, QRectF, QPropertyAnimation, QEasingCurve)

# Aus QtWidgets kommen alle visuellen Komponenten und Effekte
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QGraphicsOpacityEffect,
)  # <--- Hier gehört er hin!

# Aus QtGui kommen die Grafik-Ressourcen
from PyQt6.QtGui import (QPixmap, QColor, QPainter, QPen, QBrush,
                            QTransform, QMovie, QCursor, QTextCursor, QTextDocument, QRegion)

# Sound Support (Optional, falls pygame fehlt)
try:
    import pygame

    pygame.mixer.init()
except ImportError:
    pass


# Helper Funktion für Pfade
def get_asset_path(filename):
    if not filename: return ""

    # 1. Basis-Pfad ermitteln (Skript vs. EXE/_internal)
    if hasattr(sys, '_MEIPASS'):
        base_dir = os.path.join(sys._MEIPASS, "assets")
    else:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    full_path = os.path.join(base_dir, filename)

    # Debugging-Hilfe (wird im CMD Fenster angezeigt, falls console=True)
    # print(f"DEBUG ASSET: {full_path} | Exists: {os.path.exists(full_path)}")

    return full_path


# --- SIGNALE ---
class OverlaySignals(QObject):
    show_image = pyqtSignal(str, str, int, int, int, float, float, bool)
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

    # Diese Methode wird nicht mehr benötigt, da wir setHtml() im Widget nutzen.
    # Wir lassen sie leer, damit Aufrufe nicht abstürzen.
    def add_animated_message(self, html_msg):
        pass

    def clear(self):
        self.page().runJavaScript("clearChat()")


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

        # --- DER FIX: Base URL mitgeben ---
        # Wir geben den Pfad des aktuellen Ordners als "Heimat" an.
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.browser.setHtml(html, base_url)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

    def _prepare_height(self):
        """Ersatz für das alte adjust_height."""
        # Wir fragen JavaScript nach der scrollHeight (tatsächliche Höhe des Inhalts)
        self.browser.page().runJavaScript(
            "document.documentElement.scrollHeight",
            self._apply_height_callback
        )

    def _apply_height_callback(self, height):
        """Wird aufgerufen, sobald JavaScript die Höhe berechnet hat."""
        if height:
            new_h = int(height) + 10  # Kleiner Puffer
            self.setFixedHeight(new_h)
            self.browser.setFixedHeight(new_h)

            # Erst JETZT starten wir den Timer für das Verschwinden
            if self.hold_time > 0:
                QTimer.singleShot(self.hold_time * 1000, self.start_fade_out)

    def start_fade_out(self):
        """Bleibt fast gleich, nutzt aber QPropertyAnimation auf den Container."""
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(2000)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.destroy_message)
        self.anim.start()

    def destroy_message(self):
        """Bleibt genau gleich."""
        self.hide()
        self.deleteLater()

# --- ZEICHEN-LAYER (Für Pfad-Aufnahme) ---
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

        # Klick-Fläche
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


# --- HAUPT OVERLAY KLASSE ---
class QtOverlay(QWidget):
    def __init__(self, gui_ref=None):
        super().__init__()
        self.gui_ref = gui_ref
        self.edit_mode = False
        self.dragging_widget = None
        self.drag_offset = None
        self.knife_labels = []

        # --- CACHE DICTIONARY (NEU) ---
        # Hier speichern wir alle geladenen Bilder
        self.pixmap_cache = {}
        self.movie_cache = {}

        self.cache_usage_timestamps = {}  # NEU: Speichert {pfad: zeitstempel}

        # GC-Timer: Alle 2 Minuten prüfen wir auf "Müll"
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self.run_garbage_collection)
        self.gc_timer.start(120000)  # 120.000 ms = 2 Minuten

        # 1. FENSTER-KONFIGURATION
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # Skalierung
        self.base_height = 1080.0
        self.ui_scale = screen.height() / self.base_height
        self.ui_scale = max(0.8, self.ui_scale)

        # Zeichen-Ebene
        self.path_edit_active = False
        self.custom_path = []
        self.path_layer = PathDrawingLayer(self)
        self.path_layer.setGeometry(self.rect())
        self.path_layer.hide()

        # 2. WIDGETS
        self.crosshair_container = QWidget(self)
        self.crosshair_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.crosshair_container.hide()

        self.crosshair_browser = DraggableChat(self.crosshair_container)
        self.crosshair_browser.hide()

        self.stats_container = QWidget(self)
        self.stats_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.stats_container.hide()

        self.stats_browser = DraggableChat(self.stats_container)
        self.stats_browser.hide()

        self.streak_bg_label = QLabel(self)
        self.streak_bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.streak_bg_label.hide()
        self.streak_text_label = QLabel(self)
        self.streak_text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.streak_text_label.hide()

        # Killfeed
        self.feed_messages = []
        self.feed_container = QWidget(self)
        self.feed_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.feed_container.hide()
        self.feed_w = int(600 * self.ui_scale)
        self.feed_h = int(550 * self.ui_scale)
        self.feed_container.setFixedSize(self.feed_w, self.feed_h)

        self.feed_browser = DraggableChat(self.feed_container)
        self.feed_browser.hide()

        self.event_preview_label = QLabel(self)
        self.event_preview_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.event_preview_label.hide()

        self.img_label = QLabel(self)
        self.img_label.setScaledContents(True)
        self.img_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.img_label.hide()

        # 3. SIGNALE VERBINDEN
        self.signals = OverlaySignals()
        self.signals.show_image.connect(self.add_event_to_queue)
        self.signals.killfeed_entry.connect(self.add_killfeed_row)
        self.signals.update_stats.connect(self.set_stats_html)
        self.signals.update_streak.connect(self.draw_streak_ui)
        self.signals.clear_feed.connect(self.clear_killfeed)

        # Maus-Transparenz aktivieren
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
        self.queue_timer = QTimer()
        self.queue_timer.setSingleShot(True)
        self.queue_timer.timeout.connect(self.finish_current_event)

        # Initiale Queue Einstellung (Fallback)
        self.queue_enabled = True
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            self.queue_enabled = self.gui_ref.config.get("event_queue_active", True)

        self.last_stats_html = ""
        self.last_stats_bg = ""
        self.last_stats_size = (int(600 * self.ui_scale), int(60 * self.ui_scale))
        self.last_stats_render = {
            "html": "",
            "bg": "",
            "offset_x": None,
            "offset_y": None,
        }

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

        # Initialen Inhalt setzen
        self.chat_hold_time = 15
        self.update_twitch_browser_content()
        self.update_feed_browser_content()
        self.update_stats_browser_content()
        self.update_crosshair_browser_content()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.fade_out_chat)

        # --- TWITCH DRAG COVER (Fix für WebEngine Click-Interferenz) ---
        self.twitch_drag_cover = QWidget(self)
        self.twitch_drag_cover.setObjectName("twitch_drag_cover")
        self.twitch_drag_cover.hide()
        # WICHTIG: Kein WA_TransparentForMouseEvents hier, damit es Klicks fängt!

        self.server = OverlayServer()
        self.active_edit_targets = []

    def get_master_volume(self):
        """Holt das Master-Volume aus der Config (0-100) und gibt float (0.0-1.0) zurück."""
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            # Standard ist 50%, falls noch nichts gespeichert wurde
            vol_percent = self.gui_ref.config.get("audio_volume", 50)
            # Sicherstellen, dass es float ist und zwischen 0.0 und 1.0 liegt
            return max(0.0, min(1.0, float(vol_percent) / 100.0))
        return 0.5  # Fallback

    def run_garbage_collection(self):
        """Löscht Ressourcen, die länger als 20 Minuten nicht genutzt wurden."""
        now = time.time()
        max_idle_time = 20 * 60  # 20 Minuten in Sekunden

        # Listen für zu löschende Pfade
        to_remove = []

        for path, last_used in self.cache_usage_timestamps.items():
            if now - last_used > max_idle_time:
                to_remove.append(path)

        if not to_remove:
            return

        for path in to_remove:
            # 1. Aus Movie-Cache entfernen (falls vorhanden)
            if path in self.movie_cache:
                movie = self.movie_cache.pop(path)
                movie.stop()  # WICHTIG: Animation stoppen
                movie.deleteLater()  # Ressourcen freigeben

            # 2. Aus Pixmap-Cache entfernen
            if path in self.pixmap_cache:
                self.pixmap_cache.pop(path)

            # 3. Zeitstempel-Eintrag löschen
            if path in self.cache_usage_timestamps:
                del self.cache_usage_timestamps[path]

        self.gui_ref.add_log(f"GC: {len(to_remove)} ungenutzte Ressourcen aus RAM gelöscht.")

    def notify_chat_moved(self, x, y):
        # Signal an Controller senden
        self.signals.item_moved.emit("twitch", x, y)

    def update_twitch_style(self, x, y, w, h, opacity, font_size):
        self.chat_container.setGeometry(int(x), int(y), int(w), int(h))
        self.current_chat_font_size = font_size

        alpha = int((opacity / 100) * 255)

        # Hintergrund komplett auf transparent setzen
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
        """Initialisiert oder resettet den Browser-Inhalt."""
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

    def update_feed_browser_content(self):
        """Initialisiert oder resettet den Killfeed-Browser."""
        template = """
        <html>
        <head>
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateX(20px); }
                    to { opacity: 1; transform: translateX(0); }
                }
                body {
                    margin: 0;
                    padding: 5px;
                    overflow: hidden;
                    background: transparent;
                    font-family: 'Segoe UI', Arial;
                    color: white;
                    display: flex;
                    flex-direction: column;
                    align-items: flex-end;
                }
                #feed-log { width: 100%; }
                .feed-item {
                    animation: fadeIn 0.5s ease-out forwards;
                    margin-bottom: 2px;
                    text-align: right;
                    font-weight: 800;
                    text-shadow: 2px 2px 2px #000, 0px 0px 4px #000;
                }
            </style>
        </head>
        <body>
            <div id="feed-log"></div>
            <script>
                function setFeed(html) {
                    document.getElementById('feed-log').innerHTML = html;
                }
                function clearFeed() {
                    document.getElementById('feed-log').innerHTML = '';
                }
                function addFeedMessage(html, maxItems) {
                    const container = document.getElementById('feed-log');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'feed-item';
                    msgDiv.innerHTML = html;
                    container.prepend(msgDiv);
                    if (maxItems && container.children.length > maxItems) {
                        container.removeChild(container.lastChild);
                    }
                }
            </script>
        </body>
        </html>
        """
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.feed_browser.setHtml(template, base_url)
        self.feed_browser.show()

    def update_stats_browser_content(self):
        """Initialisiert oder resettet den Stats-Browser."""
        template = """
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background: transparent;
                    font-family: 'Segoe UI', Arial;
                    color: white;
                }
                #stats-container {
                    width: 100%;
                    height: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background-size: 100% 100%;
                    background-repeat: no-repeat;
                }
                #stats-content {
                    text-shadow: 2px 2px 2px #000, 0px 0px 4px #000;
                    font-weight: 800;
                }
            </style>
        </head>
        <body>
            <div id="stats-container">
                <div id="stats-content"></div>
            </div>
            <script>
                function updateStats(html, bgUrl, offsetX, offsetY) {
                    const container = document.getElementById('stats-container');
                    const content = document.getElementById('stats-content');
                    content.innerHTML = html || '';
                    content.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
                    if (bgUrl) {
                        container.style.backgroundImage = `url('${bgUrl}')`;
                    } else {
                        container.style.backgroundImage = 'none';
                    }
                }
            </script>
        </body>
        </html>
        """
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.stats_browser.setHtml(template, base_url)
        self.stats_browser.show()

    def update_crosshair_browser_content(self):
        """Initialisiert oder resettet den Crosshair-Browser."""
        template = """
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background: transparent;
                }
                #crosshair-img {
                    width: 100%;
                    height: 100%;
                    object-fit: contain;
                    display: block;
                }
            </style>
        </head>
        <body>
            <img id="crosshair-img" src="" />
            <script>
                function setCrosshair(src) {
                    const img = document.getElementById('crosshair-img');
                    img.src = src || '';
                }
            </script>
        </body>
        </html>
        """
        base_url = QUrl.fromLocalFile(os.path.abspath("."))
        self.crosshair_browser.setHtml(template, base_url)
        self.crosshair_browser.show()

    def add_twitch_message(self, user, html_msg, color="#00f2ff", is_test=False):
        # 1. Sichtbarkeit prüfen
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

        # PFAD-FIX für WebEngine
        html_msg = html_msg.replace('src="emote://', 'src="file:///')
        html_msg = html_msg.replace('\\', '/')

        safe_color = self.get_readable_color(color)
        f_size = getattr(self, 'current_chat_font_size', 12)

        # In JS injecten
        js = f"addMessage({json.dumps(user)}, {json.dumps(html_msg)}, {json.dumps(safe_color)}, {json.dumps(f_size)}, {json.dumps(self.chat_hold_time)})"
        self.twitch_browser.page().runJavaScript(js)

        # Auto-Hide Timer resetten (für den ganzen Container)
        if self.chat_hold_time > 0:
            self.auto_hide_timer.start((self.chat_hold_time + 2) * 1000)

    def get_readable_color(self, hex_color):
        """Prüft die Helligkeit und hellt dunkle Farben auf."""
        hex_color = hex_color.lstrip('#')
        # Von Hex zu RGB
        r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

        # Perzeptive Helligkeit berechnen
        luminance = (0.299 * r + 0.587 * g + 0.114 * b)

        # Schwellenwert: Alles unter 120 (von 255) wird aufgehellt
        if luminance < 120:
            # Wir addieren einen festen Wert, um die Farbe "pastelliger"
            # und leuchtender zu machen, ohne den Farbton zu verlieren
            r = min(255, r + 80)
            g = min(255, g + 80)
            b = min(255, b + 80)
            return f"#{r:02x}{g:02x}{b:02x}"

        return f"#{hex_color}"

    def fade_out_chat(self):
        """Versteckt den Chat oder leert ihn."""
        # Variante 1: Einfach verstecken (empfohlen für Performance)
        self.chat_container.hide()
        # Variante 2: Chat leeren (falls du willst, dass er beim nächsten Mal leer startet)
        # self.twitch_browser.clear()

    def set_chat_hold_time(self, seconds):
        """Wird vom GUI aufgerufen, wenn der User den Wert ändert."""
        self.chat_hold_time = int(seconds)
        if self.chat_hold_time == 0:
            self.auto_hide_timer.stop()
            self.chat_container.show()

    def clear_twitch_chat(self):
        """Leert den Browser-Inhalt."""
        self.twitch_browser.clear()
        self.add_log("TWITCH: Chat cleared.")

    # --- CACHE LOGIK ---
    def get_cached_pixmap(self, path):
        if not path:
            return QPixmap()

        # --- FIX: Selbstheilung für relative Pfade ---
        # 1. Ist der Pfad so wie er ist gültig?
        if not os.path.exists(path):
            # 2. Nein? Dann versuchen wir, ihn im Assets-Ordner zu finden
            resolved_path = get_asset_path(path)
            if os.path.exists(resolved_path):
                path = resolved_path # Gefunden! Wir nutzen den korrigierten Pfad
            else:
                # Weder direkt noch in Assets gefunden -> Abbruch
                # print(f"DEBUG: Bild nicht gefunden: {path}")
                return QPixmap()

        # Ab hier normale Cache-Logik
        if path not in self.pixmap_cache:
            pm = QPixmap(path)
            if not pm.isNull():
                self.pixmap_cache[path] = pm
            else:
                return QPixmap()

        self.cache_usage_timestamps[path] = time.time()
        return self.pixmap_cache[path]


    def clear_cache(self):
        """Falls man Bilder im Betrieb austauscht (Reload)."""
        self.pixmap_cache.clear()

    # --- QUEUE & DISPLAY LOGIK ---
    def add_event_to_queue(self, img_path, sound_path, duration, x, y, scale=1.0, volume=1.0, is_hitmarker=False):
        # --- FALL A: HITMARKER (Sofort & Parallel) ---

        master_vol = self.get_master_volume()

        if is_hitmarker:
            if sound_path:
                try:
                    if 'pygame' in sys.modules:
                        snd = pygame.mixer.Sound(sound_path)
                        snd.set_volume(volume * master_vol) # <--- Volume setzen
                        snd.play()
                except:
                    pass

            if img_path and os.path.exists(img_path):
                self.show_hitmarker(img_path, duration, x, y, scale)
            return

        # --- FALL B: NORMALE EVENTS (Queue) ---
        if not hasattr(self, 'queue_enabled'): self.queue_enabled = True

        if not self.queue_enabled:
            # Queue aus: Alles abbrechen, sofort zeigen
            self.clear_queue_now()

            if sound_path:
                try:
                    if 'pygame' in sys.modules:
                        snd = pygame.mixer.Sound(sound_path)
                        snd.set_volume(volume * master_vol) # <--- Volume setzen
                        snd.play()
                except:
                    pass

            self.display_image(img_path, duration, x, y, scale)
            return

        # Queue AN: Volume mit speichern
        self.event_queue.append((img_path, sound_path, duration, x, y, scale, volume))

        if not self.is_showing:
            self.process_next_event()

    def show_hitmarker(self, img_path, duration, abs_x, abs_y, scale=1.0):
        if hasattr(self, 'hitmarker_timer') and self.hitmarker_timer.isActive():
            self.hitmarker_timer.stop()

        # --- CACHE GENUTZT ---
        pixmap = self.get_cached_pixmap(img_path)
        if pixmap.isNull():
            self.hitmarker_label.hide()
            return

        # Skalierung (nutzt das gecachte Bild als Basis)
        final_scale = self.ui_scale * scale
        if final_scale != 1.0:
            w = int(pixmap.width() * final_scale)
            h = int(pixmap.height() * final_scale)
            pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        self.hitmarker_label.setPixmap(pixmap)
        self.hitmarker_label.adjustSize()

        if abs_x == 0 and abs_y == 0:
            center_x = (self.width() // 2) - (self.hitmarker_label.width() // 2)
            center_y = (self.height() // 2) - (self.hitmarker_label.height() // 2)
            self.safe_move(self.hitmarker_label, center_x, center_y)
        else:
            self.safe_move(self.hitmarker_label, self.s(abs_x), self.s(abs_y))

        self.hitmarker_label.show()
        self.hitmarker_label.raise_()

        if not hasattr(self, 'hitmarker_timer'):
            self.hitmarker_timer = QTimer(self)
            self.hitmarker_timer.setSingleShot(True)
            self.hitmarker_timer.timeout.connect(self.hitmarker_label.hide)

        self.hitmarker_timer.start(duration if duration > 0 else 150)

    def process_next_event(self):
        if not self.event_queue:
            self.is_showing = False
            return

        self.is_showing = True
        # Volume aus dem Tupel entpacken
        img_path, sound_path, duration, x, y, scale, event_vol = self.event_queue.pop(0)

        self.display_image(img_path, duration, x, y, scale)
        filename = os.path.basename(img_path)

        if img_path:
            filename = os.path.basename(img_path)
            self.server.broadcast("event", {
                "filename": filename,
                "duration": duration,
                "x": int(x),  # Position senden
                "y": int(y),  # Position senden
                "scale": scale  # Scale senden
            })

        if sound_path:
            try:
                if 'pygame' in sys.modules:
                    # Master Volume frisch holen (falls User während der Queue den Regler bewegt hat)
                    master_vol = self.get_master_volume()

                    snd = pygame.mixer.Sound(sound_path)
                    # HIER WIRD VERRECHNET
                    snd.set_volume(event_vol * master_vol)
                    snd.play()
            except:
                pass

        self.queue_timer.start(duration)

    def finish_current_event(self):
        self.process_next_event()

    def clear_queue_now(self):
        self.event_queue.clear()
        self.queue_timer.stop()
        self.is_showing = False

    def display_image(self, img_path, duration, abs_x, abs_y, scale=1.0):
        if hasattr(self, 'hide_timer') and self.hide_timer.isActive():
            self.hide_timer.stop()

        if self.img_label.movie():
            self.img_label.movie().stop()
            self.img_label.setMovie(None)

        if not img_path or not os.path.exists(img_path):
            self.img_label.hide()
            return

        if img_path.lower().endswith(".gif"):
            # GIFs cachen wir NICHT als Pixmap, da sie animiert sind (QMovie).
            # Das ist okay, da GIFs selten sind im Vergleich zu Hitmarkern.
            if img_path not in self.movie_cache:
                m = QMovie(img_path)
                m.setCacheMode(QMovie.CacheMode.CacheAll)
                m.start()
                self.movie_cache[img_path] = m

            movie = self.movie_cache[img_path]
            self.img_label.setMovie(movie)
            # Wichtig: Das Movie muss für das neue Label ggf. neu gestartet/gezeigt werden
            movie.jumpToFrame(0)
            movie.start()
        else:
            # --- CACHE GENUTZT (Statische Bilder) ---
            pixmap = self.get_cached_pixmap(img_path)
            if pixmap.isNull(): return

            final_scale = self.ui_scale * scale
            if final_scale != 1.0:
                w = int(pixmap.width() * final_scale)
                h = int(pixmap.height() * final_scale)
                pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)

            self.img_label.setPixmap(pixmap)

        self.img_label.adjustSize()
        self.safe_move(self.img_label, self.s(abs_x), self.s(abs_y))
        self.img_label.show()
        self.img_label.raise_()

        if not hasattr(self, 'hide_timer'):
            self.hide_timer = QTimer(self)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self._hide_image_safe)

        self.hide_timer.start(duration)

    def _hide_image_safe(self):
        if self.img_label.movie():
            self.img_label.movie().stop()
        self.img_label.hide()

    # --- CORE FUNCTIONS ---
    def resizeEvent(self, event):
        if hasattr(self, 'path_layer'): self.path_layer.setGeometry(self.rect())
        super().resizeEvent(event)

    def force_update(self):
        self.repaint()
        if self.path_edit_active: self.path_layer.raise_()

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
        Aktiviert oder deaktiviert die Klick-Durchlässigkeit.
        WICHTIG: Erst Qt-Flags setzen, DANN show(), DANN ctypes Styles!
        """
        # 1. Qt Flags setzen (Dies kann das Fenster zerstören und neu erstellen!)
        if enabled:
            # 0. Erst Visuals säubern
            self.clear_edit_visuals()
            self.active_edit_targets = []

            # Normaler Overlay-Modus (Klicks gehen durch)
            self.edit_mode = False
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool |
                Qt.WindowType.WindowTransparentForInput  # Qt-Level Transparenz
            )
        else:
            # Edit-Modus (Fenster fängt Klicks ab)
            self.edit_mode = True
            self.active_edit_targets = active_targets if active_targets else []
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
                # KEIN WindowTransparentForInput hier!
            )

        # 2. Fenster (wieder) anzeigen, damit es ein gültiges Handle bekommt
        self.show()

        # Falls Edit-Modus: Fokus erzwingen, sonst landen Klicks im Spiel
        if not enabled:
            self.activateWindow()
            self.raise_()
            # IMMER den echten Chat verstecken, wenn Edit Mode - beugt Blocking vor!
            self.chat_container.hide()
        else:
            self.clearMask()

        # 3. Windows API Styles anwenden (Auf das NEUE Handle!)
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20

            # Aktuellen Style holen
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            if enabled:
                # Durchlässig machen (Layered + Transparent)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                if hasattr(self, 'event_preview_label'):
                    self.event_preview_label.hide()
            else:
                # Greifbar machen (Transparent-Bit entfernen)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED)

                # --- VISUALS FÜR EDIT MODE ---
                hl_style = "border: 2px solid #00ff00; background-color: rgba(0, 255, 0, 50);"
                targets = active_targets if active_targets else []

                if "feed" in targets:
                    feed_style = "border: 2px solid #00ff00; background-color: rgba(0, 0, 0, 150);"
                    self.feed_container.setStyleSheet(feed_style)
                    self.feed_container.show()
                    self.feed_container.raise_()
                    if not self.feed_messages:
                        placeholder = "<div style='color:white; font-size:20px; padding:10px;'>KILLFEED DRAG AREA</div>"
                        self.feed_browser.page().runJavaScript(f"setFeed({json.dumps(placeholder)})")

                if "stats" in targets:
                    self.stats_container.setStyleSheet(hl_style)
                    if self.stats_container.width() == 0 or self.stats_container.height() == 0:
                        self.stats_container.resize(*self.last_stats_size)
                    self.stats_container.show()
                    self.stats_container.raise_()
                    if not self.last_stats_html:
                        placeholder = "<div style='color:white; font-size:20px; padding:10px;'>STATS AREA</div>"
                        self.stats_browser.page().runJavaScript(
                            f"updateStats({json.dumps(placeholder)}, '', 0, 0)"
                        )

                if "streak" in targets:
                    self.streak_bg_label.setStyleSheet(hl_style)
                    self.streak_bg_label.show()
                    if not self.streak_bg_label.pixmap() or self.streak_bg_label.pixmap().isNull():
                        self.streak_bg_label.setText("STREAK AREA")
                        self.streak_bg_label.setStyleSheet(f"{hl_style} color: white; font-weight: bold;")
                        self.streak_bg_label.adjustSize()

                if "crosshair" in targets:
                    self.crosshair_container.setStyleSheet(hl_style)
                    if self.crosshair_container.width() == 0 or self.crosshair_container.height() == 0:
                        self.crosshair_container.resize(int(64 * self.ui_scale), int(64 * self.ui_scale))
                    self.crosshair_container.show()

                if "event" in targets:
                    if hasattr(self, 'event_preview_label'):
                        self.event_preview_label.setStyleSheet(hl_style)
                        self.event_preview_label.show()
                        self.event_preview_label.raise_()

                if "twitch" in targets:
                    # Wir zeigen NICHT das echte Layout mit WebEngines (Click-Zicken!),
                    # sondern das Drag-Cover, das Klicks zuverlässig an QtOverlay weitergibt.
                    self.twitch_drag_cover.setStyleSheet(hl_style)
                    self.twitch_drag_cover.show()
                    self.twitch_drag_cover.raise_()
                    # Den echten Chat verstecken wir, damit er nicht stört
                    self.chat_container.hide()
                self.update_edit_mask(targets)

        except Exception as e:
            print(f"Passthrough Error: {e}")

    def update_edit_mask(self, targets):
        """Limitiert Klicks auf das aktive Element, der Rest wird klick-through."""
        if not targets:
            self.clearMask()
            return

        regions = QRegion()
        for target in targets:
            widget = None
            if target == "event":
                widget = self.event_preview_label
            elif target == "feed":
                widget = self.feed_container
            elif target == "stats":
                widget = self.stats_container
            elif target == "streak":
                widget = self.streak_bg_label
            elif target == "crosshair":
                widget = self.crosshair_container
            elif target == "twitch":
                widget = self.twitch_drag_cover

            if widget and widget.isVisible():
                regions = regions.united(QRegion(widget.geometry()))

        if regions.isEmpty():
            self.clearMask()
        else:
            self.setMask(regions)

    def clear_edit_visuals(self):
        """Entfernt alle Edit-Rahmen und setzt Labels in den Normalzustand."""
        # Stats
        if hasattr(self, 'stats_container'):
            self.stats_container.setStyleSheet("background: transparent;")
        
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
        if hasattr(self, 'feed_container'):
            self.feed_container.setStyleSheet("background: transparent;")
            if not self.feed_messages:
                self.feed_browser.page().runJavaScript("clearFeed()")
        
        # Streak
        if hasattr(self, 'streak_bg_label'):
            self.streak_bg_label.setStyleSheet("background: transparent;")
            if "STREAK AREA" in self.streak_bg_label.text():
                self.streak_bg_label.setText("")

        # Crosshair
        if hasattr(self, 'crosshair_container'):
            self.crosshair_container.setStyleSheet("background: transparent;")

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
        elif "border" in self.feed_container.styleSheet() and self.feed_container.geometry().contains(pos):
            self.dragging_widget = "feed"
            self.drag_offset = pos - self.feed_container.pos()
        elif "border" in self.stats_container.styleSheet() and self.stats_container.geometry().contains(pos):
            self.dragging_widget = "stats"
            self.drag_offset = pos - self.stats_container.pos()
        elif "border" in self.streak_bg_label.styleSheet() and self.streak_bg_label.geometry().contains(pos):
            self.dragging_widget = "streak"
            self.drag_offset = pos - self.streak_bg_label.pos()
        elif "border" in self.crosshair_container.styleSheet() and self.crosshair_container.geometry().contains(pos):
            self.dragging_widget = "crosshair"
            self.drag_offset = pos - self.crosshair_container.pos()
        elif self.twitch_drag_cover.isVisible() and self.twitch_drag_cover.geometry().contains(pos):
            self.dragging_widget = "twitch"
            self.drag_offset = pos - self.twitch_drag_cover.pos()

    def mouseMoveEvent(self, event):
        if not self.edit_mode or not self.dragging_widget or not self.drag_offset: return
        new_pos = event.pos() - self.drag_offset

        if self.dragging_widget == "event":
            self.safe_move(self.event_preview_label, new_pos.x(), new_pos.y())
            self.update_edit_mask(["event"])
        elif self.dragging_widget == "feed":
            self.safe_move(self.feed_container, new_pos.x(), new_pos.y())
            self.update_edit_mask(["feed"])
        elif self.dragging_widget == "crosshair":
            self.safe_move(self.crosshair_container, new_pos.x(), new_pos.y())
            self.update_edit_mask(["crosshair"])
        elif self.dragging_widget == "stats":
            self.safe_move(self.stats_container, new_pos.x(), new_pos.y())
            self.update_edit_mask(["stats"])
        elif self.dragging_widget == "streak":
            self.safe_move(self.streak_bg_label, new_pos.x(), new_pos.y())
            self.update_edit_mask(["streak"])
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                cx = self.streak_bg_label.x() + (self.streak_bg_label.width() // 2)
                cy = self.streak_bg_label.y() + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label,
                               cx + self.s(cfg.get("tx", 0)) - (self.streak_text_label.width() // 2),
                               cy + self.s(cfg.get("ty", 0)) - (self.streak_text_label.height() // 2))
        elif self.dragging_widget == "twitch":
            self.safe_move(self.twitch_drag_cover, new_pos.x(), new_pos.y())
            self.update_edit_mask(["twitch"])
            # Das eigentliche Container-Objekt ziehen wir mit
            self.chat_container.move(self.twitch_drag_cover.pos())
            # Update GUI Sliders via Signal
            self.notify_chat_moved(new_pos.x(), new_pos.y())

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
                curr = self.crosshair_container.pos()
                center_x = curr.x() + (self.crosshair_container.width() / 2)
                center_y = curr.y() + (self.crosshair_container.height() / 2)
                if "crosshair" not in self.gui_ref.config: self.gui_ref.config["crosshair"] = {}
                self.gui_ref.config["crosshair"]["x"] = uns(center_x)
                self.gui_ref.config["crosshair"]["y"] = uns(center_y)
                self.gui_ref.save_config()
            elif self.dragging_widget == "feed":
                curr = self.feed_container.pos()
                if "killfeed" not in self.gui_ref.config: self.gui_ref.config["killfeed"] = {}
                self.gui_ref.config["killfeed"]["x"] = uns(curr.x())
                self.gui_ref.config["killfeed"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
            elif self.dragging_widget == "stats":
                curr = self.stats_container.pos()
                if "stats_widget" not in self.gui_ref.config: self.gui_ref.config["stats_widget"] = {}
                self.gui_ref.config["stats_widget"]["x"] = uns(curr.x())
                self.gui_ref.config["stats_widget"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
            elif self.dragging_widget == "streak":
                curr = self.streak_bg_label.pos()
                if "streak" not in self.gui_ref.config: self.gui_ref.config["streak"] = {}
                self.gui_ref.config["streak"]["x"] = uns(curr.x())
                self.gui_ref.config["streak"]["y"] = uns(curr.y())
                self.gui_ref.save_config()
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
        # Wir speichern jetzt die UN-SKALIERTE Nachricht
        self.feed_messages.insert(0, html_msg)
        self.feed_messages = self.feed_messages[:6]
        self.add_killfeed_message(html_msg)
        
        # Broadcast (unskaliert für Server)
        kf_x, kf_y = 50, 200  # Defaults
        if self.gui_ref:
            conf = self.gui_ref.config.get("killfeed", {})
            kf_x = conf.get("x", 50)
            kf_y = conf.get("y", 200)

        self.server.broadcast("feed", {
            "html": html_msg,
            "x": int(kf_x),
            "y": int(kf_y)
        })

    def add_killfeed_message(self, html_msg):
        """Fügt eine einzelne Killfeed-Nachricht hinzu (Twitch-like)."""
        scaled = re.sub(r'(\d+)px', lambda m: f"{int(int(m.group(1)) * self.ui_scale)}px", html_msg)
        scaled = re.sub(
            r'(width|height)="(\d+)"',
            lambda m: f'{m.group(1)}="{int(int(m.group(2)) * self.ui_scale)}"',
            scaled,
        )
        if "style=\"" in scaled:
            scaled = scaled.replace("style=\"", "style=\"line-height: 100%; ")

        if hasattr(self, 'feed_browser'):
            self.feed_browser.page().runJavaScript(
                f"addFeedMessage({json.dumps(scaled)}, {json.dumps(6)})"
            )
        self.feed_container.show()

    def update_killfeed_ui(self):
        """Skaliert alle Nachrichten im Feed und setzt den Browser-Text."""
        scaled_msgs = []
        for msg in self.feed_messages:
            # On-the-fly Skalierung via Regex
            # 1. Font-Größen (XXpx)
            scaled = re.sub(r'(\d+)px', lambda m: f"{int(int(m.group(1)) * self.ui_scale)}px", msg)
            # 2. Bild-Dimensionen (width="XX" height="XX")
            scaled = re.sub(r'(width|height)="(\d+)"',
                            lambda m: f'{m.group(1)}="{int(int(m.group(2)) * self.ui_scale)}"', scaled)

            if "style=\"" in scaled:
                scaled = scaled.replace("style=\"", "style=\"line-height: 100%; ")
            scaled_msgs.append(f"<div class='feed-item'>{scaled}</div>")

        html = f'<div style="text-align: right; margin-right: 5px;">{"".join(scaled_msgs)}</div>'
        if hasattr(self, 'feed_browser'):
            self.feed_browser.page().runJavaScript(f"setFeed({json.dumps(html)})")
        self.feed_container.show()
        self.repaint()

    def clear_killfeed(self):
        self.feed_messages = []
        if hasattr(self, 'feed_browser'):
            self.feed_browser.page().runJavaScript("clearFeed()")
        self.repaint()

    def update_killfeed_pos(self):
        if not self.gui_ref: return
        conf = self.gui_ref.config.get("killfeed", {})
        x = self.s(conf.get("x", 50))
        y = self.s(conf.get("y", 200))
        self.feed_container.setGeometry(x, y, self.feed_w, self.feed_h)
        self.feed_browser.setGeometry(self.feed_container.rect())

    def set_stats_html(self, html, img_path):
        # 1. Bild / Hintergrund Größe bestimmen
        bg_name = os.path.basename(img_path) if img_path else ""
        cfg = {}
        if self.gui_ref:
            cfg = self.gui_ref.config.get("stats_widget", {})
        sc = cfg.get("scale", 1.0) * self.ui_scale

        width = int(600 * self.ui_scale)
        height = int(60 * self.ui_scale)
        bg_url = ""
        if (img_path and os.path.exists(img_path)) or self.edit_mode:
            if img_path and os.path.exists(img_path):
                pix = self.get_cached_pixmap(img_path)
                if not pix.isNull():
                    width = int(pix.width() * sc)
                    height = int(pix.height() * sc)
                    bg_url = f"assets/{bg_name}"
            self.stats_container.show()
        else:
            self.stats_container.hide()

        # 2. Text HTML skalieren
        scaled_html = re.sub(r'(\d+)px', lambda m: f"{int(int(m.group(1)) * self.ui_scale)}px", html)

        # Position holen & Anwenden
        st_x, st_y = 50, 500
        tx_off, ty_off = 0, 0
        st_scale = 1.0
        if self.gui_ref:
            conf = self.gui_ref.config.get("stats_widget", {})
            st_x = conf.get("x", 50)
            st_y = conf.get("y", 500)
            tx_off = conf.get("tx", 0)
            ty_off = conf.get("ty", 0)
            st_scale = conf.get("scale", 1.0)
        self.last_stats_html = html
        self.last_stats_bg = bg_name
        self.last_stats_size = (width, height)

        # Background positionieren
        x = self.s(st_x)
        y = self.s(st_y)
        self.stats_container.setGeometry(x, y, width, height)
        self.stats_browser.setGeometry(self.stats_container.rect())

        self.stats_container.show()
        offset_x = self.s(tx_off)
        offset_y = self.s(ty_off)
        render_changed = (
            scaled_html != self.last_stats_render["html"]
            or bg_url != self.last_stats_render["bg"]
            or offset_x != self.last_stats_render["offset_x"]
            or offset_y != self.last_stats_render["offset_y"]
        )
        if hasattr(self, 'stats_browser') and render_changed:
            self.stats_browser.page().runJavaScript(
                f"updateStats({json.dumps(scaled_html)}, {json.dumps(bg_url)}, "
                f"{json.dumps(offset_x)}, {json.dumps(offset_y)})"
            )
            self.last_stats_render.update(
                {"html": scaled_html, "bg": bg_url, "offset_x": offset_x, "offset_y": offset_y}
            )

        self.server.broadcast("stats", {
            "html": html,
            "bg_filename": bg_name,
            "x": int(st_x),
            "y": int(st_y),
            "scale": st_scale
        })

    def draw_streak_ui(self, img_path, count, factions, cfg, slot_map):
        if not cfg.get("active", True) and not self.edit_mode:
            self.streak_bg_label.hide();
            self.streak_text_label.hide()
            for l in self.knife_labels: l.hide()
            self.repaint()  # Force update
            return
        if count <= 0 and not self.edit_mode:
            self.streak_bg_label.hide();
            self.streak_text_label.hide()
            for l in self.knife_labels: l.hide(); l._is_active = False
            self.repaint()  # Force update
            return

        cnt = count if count > 0 else 10
        sc = cfg.get("scale", 1.0) * self.ui_scale

        if os.path.exists(img_path):
            # --- CACHE GENUTZT ---
            pix = self.get_cached_pixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(int(pix.width() * sc), int(pix.height() * sc), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                self.streak_bg_label.setPixmap(pix);
                self.streak_bg_label.adjustSize()
                self.safe_move(self.streak_bg_label, self.s(cfg.get("x", 100)), self.s(cfg.get("y", 100)))
                self.streak_bg_label.show()

                skull_center = self.streak_bg_label.geometry().center()
                path_data = cfg.get("custom_path", [])

                # >>> KNIFE TOGGLE LOGIK START <<<
                if cfg.get("show_knives", True):
                    # Zuerst Labels erstellen falls nötig
                    while len(self.knife_labels) < len(factions):
                        l = QLabel(self);
                        l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);
                        self.knife_labels.append(l)

                    if len(path_data) > 2:
                        segments = []
                        total_l = 0
                        pts = [QPoint(int(p[0]), int(p[1])) for p in path_data]
                        for i in range(len(pts)):
                            p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                            d = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
                            segments.append((p1, p2, d, total_l));
                            total_l += d

                        k_per_ring = 50
                        for i in range(len(factions)):
                            lbl = self.knife_labels[i]
                            is_new = not lbl.isVisible()
                            ftag = factions[i]
                            kfile = cfg.get(f"knife_{ftag.lower()}", f"knife_{ftag.lower()}.png")
                            kpath = get_asset_path(kfile)

                            if not os.path.exists(kpath): lbl.hide(); continue  # Nur Pfad checken

                            sidx = slot_map[i] if slot_map and i < len(slot_map) else i
                            ridx = sidx // k_per_ring
                            posring = sidx % k_per_ring
                            rscale = 1.0 + (ridx * 0.28)
                            tdist = (posring / k_per_ring) * total_l
                            kx_off, ky_off = 0, 0
                            for p1, p2, seg_d, start_l in segments:
                                if start_l <= tdist <= start_l + seg_d:
                                    t = (tdist - start_l) / seg_d
                                    kx_off = (p1.x() + t * (p2.x() - p1.x())) * rscale
                                    ky_off = (p1.y() + t * (p2.y() - p1.y())) * rscale
                                    break
                            angle = math.degrees(math.atan2(ky_off, kx_off)) + 90
                            kx, ky = skull_center.x() + kx_off, skull_center.y() + ky_off
                            self._place_knife(lbl, kpath, kx, ky, angle, is_new, skull_center)
                    else:
                        k_per_circle = 50
                        rad_step = self.s(22)
                        sx = (self.streak_bg_label.width() // 2) - self.s(15)
                        sy = (self.streak_bg_label.height() // 2) - self.s(15)
                        for i in range(len(factions)):
                            lbl = self.knife_labels[i]
                            is_new = not lbl.isVisible()
                            ftag = factions[i]
                            kfile = cfg.get(f"knife_{ftag.lower()}", f"knife_{ftag.lower()}.png")
                            kpath = get_asset_path(kfile)
                            if not os.path.exists(kpath): lbl.hide(); continue

                            sidx = slot_map[i] if slot_map and i < len(slot_map) else i
                            ridx = sidx // k_per_circle
                            posring = sidx % k_per_circle
                            angle = (posring * (360 / k_per_circle)) - 90
                            rad = math.radians(angle)
                            s_val = math.sin(rad)
                            narrow = 1.0 - (0.15 * s_val) if s_val > 0 else 1.0
                            kx = skull_center.x() + int((sx + (ridx * rad_step)) * narrow * math.cos(rad))
                            ky = skull_center.y() - self.s(20) + int((sy + (ridx * rad_step)) * math.sin(rad))
                            self._place_knife(lbl, kpath, kx, ky, angle + 90, is_new, skull_center)

                    # Überschüssige Messer verstecken
                    for j in range(len(factions), len(self.knife_labels)): self.knife_labels[j].hide()

                else:
                    # FALLS AUSGESCHALTET: Alle Messer verstecken
                    for l in self.knife_labels:
                        l.hide()
                # >>> KNIFE TOGGLE LOGIK ENDE <<<

                # Text/Zahl wird IMMER gezeichnet (außerhalb des if-Blocks)
                fc, fs, sh = cfg.get("color", "#fff"), cfg.get("size", 26), int(cfg.get("shadow_size", 0))
                stl = [f"font-family: 'Black Ops One';", f"font-size: {int(fs * sc)}px;", f"color: {fc};"]
                if sh > 0: stl.append(f"text-shadow: {int(sh * sc)}px {int(sh * sc)}px 0 #000;")
                if cfg.get("bold"): stl.append("font-weight: bold;")
                if cfg.get("underline"): stl.append("text-decoration: underline;")
                self.streak_text_label.setText(f'<div style="{" ".join(stl)}">{cnt}</div>')
                self.streak_text_label.adjustSize()
                tx = skull_center.x() + self.s(cfg.get("tx", 0))
                ty = skull_center.y() + self.s(cfg.get("ty", 0))
                self.safe_move(self.streak_text_label, tx - (self.streak_text_label.width() // 2),
                               ty - (self.streak_text_label.height() // 2))
                self.streak_text_label.show()
                self.streak_bg_label.raise_();
                self.streak_text_label.raise_()

                # Fix Z-Order: Wenn Path-Edit aktiv ist, muss der Path-Layer (Marker) über dem Bild liegen
                if getattr(self, "path_edit_active", False):
                    self.path_layer.raise_()

    def _place_knife(self, lbl, path, kx, ky, angle, is_new, center):
        # --- CACHE GENUTZT (WICHTIG!) ---
        base_pix = self.get_cached_pixmap(path)
        if base_pix.isNull(): return

        # Transformation vom RAM-Bild erstellen (Kopie)
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
        if not self.streak_bg_label.isVisible(): return
        scfg = {}
        if self.gui_ref: scfg = self.gui_ref.config.get("streak", {})
        if not scfg.get("active", True): return
        now = time.time()
        try:
            speed = int(scfg.get("speed", 50)) / 20.0
        except:
            speed = 2.5
        pulse = 1.0 + (math.sin(now * speed) * 0.04) if scfg.get("anim_active", True) else 1.0
        cx, cy = self.streak_bg_label.geometry().center().x(), self.streak_bg_label.geometry().center().y()

        for lbl in self.knife_labels:
            if getattr(lbl, "_is_active", False) and lbl.isVisible():
                alive = now - getattr(lbl, "_spawn_time", 0)
                cur_s = 1.0
                if alive < 0.4:
                    prog = alive / 0.4
                    start_f = 1.8
                    cur_s = start_f - ((start_f - 1.0) * math.sin(prog * (math.pi / 2)))
                else:
                    cur_s = pulse
                nx = cx + int(getattr(lbl, "_base_off_x") * cur_s)
                ny = cy + int(getattr(lbl, "_base_off_y") * cur_s)
                lbl.move(nx - (lbl.width() // 2), ny - (lbl.height() // 2))

    def update_crosshair(self, path, size, enabled):
        if (not enabled and not self.edit_mode) or not os.path.exists(path):
            self.crosshair_container.hide();
            return

        tx, ty = 0, 0
        if self.gui_ref:
            c = self.gui_ref.config.get("crosshair", {})
            rx, ry = c.get("x", 0), c.get("y", 0)
            if rx == 0 and ry == 0:
                tx, ty = self.width() // 2, self.height() // 2
            else:
                tx, ty = self.s(rx), self.s(ry)

        self.crosshair_container.setGeometry(
            int(tx - (size // 2)),
            int(ty - (size // 2)),
            int(size),
            int(size),
        )
        self.crosshair_browser.setGeometry(self.crosshair_container.rect())
        src = QUrl.fromLocalFile(path).toString()
        self.crosshair_browser.page().runJavaScript(f"setCrosshair({json.dumps(src)})")
        self.crosshair_container.show()

    def update_twitch_visibility(self, enabled):
        """Entscheidet, ob der Chat-Container wirklich sichtbar sein darf."""
        game_running = False
        always_on = False

        if self.gui_ref:
            game_running = getattr(self.gui_ref, 'ps2_running', False)
            always_on = self.gui_ref.config.get("twitch", {}).get("always_on", False)

        # Die goldene Regel:
        # Sichtbar wenn (Aktiviert UND (Spiel läuft ODER Always-On)) ODER (Wir editieren gerade)
        should_show = (enabled and (game_running or always_on)) or self.edit_mode

        if should_show:
            self.chat_container.show()
        else:
            self.chat_container.hide()
