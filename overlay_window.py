import sys
import os
import ctypes
import math
import time

# Aus QtCore kommen die Logik- und Animations-Klassen
from PyQt6.QtCore import (Qt, pyqtSignal, QObject, QTimer, QPoint,
                            QSize, QUrl, QRectF, QPropertyAnimation, QEasingCurve)

# Aus QtWidgets kommen alle visuellen Komponenten und Effekte
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QGraphicsDropShadowEffect,
                                 QVBoxLayout, QHBoxLayout, QFrame, QTextBrowser,
                                 QGraphicsOpacityEffect) # <--- Hier gehört er hin!

# Aus QtGui kommen die Grafik-Ressourcen
from PyQt6.QtGui import (QPixmap, QColor, QPainter, QPen, QBrush,
                            QTransform, QMovie, QCursor, QTextCursor, QTextDocument)

# Sound Support (Optional, falls pygame fehlt)
try:
    import pygame

    pygame.mixer.init()
except ImportError:
    pass


# Helper Funktion für Pfade
def get_asset_path(filename):
    if not filename: return ""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", filename)


# --- SIGNALE ---
class OverlaySignals(QObject):
    show_image = pyqtSignal(str, str, int, int, int, float, bool)
    killfeed_entry = pyqtSignal(str)
    update_stats = pyqtSignal(str, str)
    update_streak = pyqtSignal(str, int, list, dict, list)
    path_points_updated = pyqtSignal(list)
    clear_feed = pyqtSignal()
    setting_changed = pyqtSignal(str, object)
    test_trigger = pyqtSignal(str)
    edit_mode_toggled = pyqtSignal(str)
    item_moved = pyqtSignal(str, int, int)





class DraggableChat(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        # WICHTIG: WA_TranslucentBackground auf False, damit Stylesheet-Farben greifen
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        # Das erlaubt uns, den Hintergrund selbst über das Stylesheet zu zeichnen
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.movies = {}
        self._mutex = False

    def add_animated_message(self, html_msg):
        import re
        matches = re.findall(r'src="emote://([^"]+)"', html_msg)
        doc = self.document()

        # Wir suchen das Haupt-Overlay für den globalen Cache
        # Struktur: ChatMessageWidget -> Container -> QtOverlay
        main_ovl = self.parent().parent() if self.parent() else None

        for path in matches:
            clean_path = path.replace('\\', '/')
            if not os.path.exists(clean_path): continue
            url = QUrl(f"emote://{clean_path}")

            if clean_path.lower().endswith((".gif", ".webp")):
                # Globalen Movie-Cache nutzen
                if main_ovl and hasattr(main_ovl, 'movie_cache'):
                    if clean_path not in main_ovl.movie_cache:
                        m = QMovie(clean_path)
                        if m.isValid():
                            #m.setScaledSize(QSize(28, 28))
                            m.setCacheMode(QMovie.CacheMode.CacheAll)
                            m.start()
                            main_ovl.movie_cache[clean_path] = m

                    movie = main_ovl.movie_cache.get(clean_path)
                    if movie:
                        self.movies[clean_path] = movie
                        if main_ovl:
                            main_ovl.cache_usage_timestamps[clean_path] = time.time()
                        # Jede Nachricht hört auf den globalen Taktgeber
                        movie.frameChanged.connect(lambda _, p=clean_path: self.on_frame_changed(p))
                        doc.addResource(QTextDocument.ResourceType.ImageResource, url, movie.currentPixmap())

            else:  # Statische Bilder (PNG)
                pix = QPixmap(clean_path)
                if not pix.isNull():
                    doc.addResource(QTextDocument.ResourceType.ImageResource, url, pix)

        self.append(html_msg)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def on_frame_changed(self, path):
        """Wird vom globalen Movie getriggert."""
        if self._mutex or not self.isVisible(): return

        movie = self.movies.get(path)
        if movie:
            self._mutex = True
            try:
                # Wir holen den aktuellen Frame vom globalen Cache-Objekt
                doc = self.document()
                url = QUrl(f"emote://{path}")
                doc.addResource(QTextDocument.ResourceType.ImageResource, url, movie.currentPixmap())
                doc.documentLayout().update.emit(QRectF(0, 0, self.width(), self.height()))
            except:
                pass
            finally:
                self._mutex = False

    def clear(self):
        self._mutex = True
        # NUR die Verbindung trennen, NICHT das Movie stoppen!
        for path, movie in self.movies.items():
            try:
                movie.frameChanged.disconnect()
            except:
                pass
        self.movies.clear()
        super().clear()
        self._mutex = False


class ChatMessageWidget(DraggableChat):  # Wir erben von deinem Browser
    def __init__(self, parent, html, hold_time, fade_duration=2000):
        super().__init__(parent)
        self.hold_time = hold_time

        self.setStyleSheet("background: transparent; border: none;")

        # Opacity Effekt für die Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)  # <--- Das hier erzwingt volle Schärfe von Anfang an
        self.setGraphicsEffect(self.opacity_effect)

        # Inhalt setzen
        self.add_animated_message(html)
        self.adjust_height()

        # Timer für den Start des Fade-Outs
        if self.hold_time > 0:
            QTimer.singleShot(self.hold_time * 1000, self.start_fade_out)

    def adjust_height(self):
        """Passt die Höhe des Widgets an den Textinhalt an."""
        self.document().setTextWidth(self.width())
        new_h = int(self.document().size().height()) + 5
        self.setFixedHeight(new_h)

    def start_fade_out(self):
        # Animation: Von 1.0 (sichtbar) zu 0.0 (unsichtbar)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(2000)  # 2 Sekunden Fading
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.destroy_message)
        self.anim.start()

    def destroy_message(self):
        self.hide()
        self.deleteLater()  # Sicher aus dem Speicher löschen

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
        self.crosshair_label = QLabel(self)
        self.crosshair_label.hide()

        self.stats_bg_label = QLabel(self)
        self.stats_bg_label.hide()
        self.stats_text_label = QLabel(self)
        self.stats_text_label.hide()

        shadow_stats = QGraphicsDropShadowEffect()
        shadow_stats.setBlurRadius(5 * self.ui_scale)
        shadow_stats.setColor(QColor(0, 0, 0, 240))
        shadow_stats.setXOffset(1 * self.ui_scale)
        shadow_stats.setYOffset(1 * self.ui_scale)
        self.stats_text_label.setGraphicsEffect(shadow_stats)

        self.streak_bg_label = QLabel(self)
        self.streak_bg_label.hide()
        self.streak_text_label = QLabel(self)
        self.streak_text_label.hide()

        # Killfeed
        self.feed_messages = []
        self.feed_label = QLabel(self)
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

        self.hitmarker_label = QLabel(self)
        self.hitmarker_label.setScaledContents(True)
        self.hitmarker_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hitmarker_label.hide()

        self.chat_container = QWidget(self)
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(5)

        # GEÄNDERT: Nachrichten setzen jetzt oben an
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.chat_container.hide()

        self.chat_hold_time = 15  # Standard: 15 Sekunden
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.fade_out_chat)

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

        if self.gui_ref:
            enabled = self.gui_ref.config.get("twitch", {}).get("active", True)
            self.update_twitch_visibility(enabled)

    def add_twitch_message(self, user, html_msg, color="#00f2ff", is_test=False): # <--- is_test hinzugefügt
        # 1. Sichtbarkeit prüfen
        enabled = True
        always_on = False
        game_running = False

        if self.gui_ref:
            enabled = self.gui_ref.config.get("twitch", {}).get("active", True)
            always_on = self.gui_ref.config.get("twitch", {}).get("always_on", False)
            game_running = getattr(self.gui_ref, 'ps2_running', False)

        # Logik: Zeigen wenn (Test) ODER (Aktiv UND (Spiel läuft ODER AlwaysOn)) ODER (Edit-Mode)
        should_process = is_test or (enabled and (game_running or always_on)) or self.edit_mode

        if not should_process:
            return # Nachricht wird ignoriert, da Bedingungen nicht erfüllt

        # Container sicherheitshalber zeigen
        self.chat_container.show()

        safe_color = self.get_readable_color(color)

        # Hol dir die aktuellen Werte (falls sie in update_twitch_style gespeichert wurden)
        f_size = getattr(self, 'current_chat_font_size', 12)
        full_html = f"""
                <div style="font-size: {f_size}pt; line-height: 125%; font-weight: 800;">
                    <span style="color: {safe_color}; font-weight: 900; letter-spacing: 0.5px;
                                 text-shadow: 0px 0px 8px {safe_color}, 1px 1px 0px #000, -1px -1px 0px #000;">
                        {user}:
                    </span>
                    <span style="color: #ffffff; text-shadow: 2px 2px 2px #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000;">
                        {html_msg}
                    </span>
                </div>
                """

        msg_widget = ChatMessageWidget(self.chat_container, full_html, self.chat_hold_time)
        msg_widget.setFixedWidth(self.chat_container.width())
        msg_widget.adjust_height()
        self.chat_layout.addWidget(msg_widget)

        if self.chat_layout.count() > 50:
            item = self.chat_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

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
        """Entfernt alle aktuellen Nachrichten-Widgets aus dem Layout."""
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Falls es ein ChatMessageWidget ist, stoppen wir das Movie
                if hasattr(widget, 'movies'):
                    for m in widget.movies.values():
                        m.stop()
                widget.deleteLater()
        self.add_log("TWITCH: Chat cleared.")

    # --- CACHE LOGIK ---
    def get_cached_pixmap(self, path):
        if not path or not os.path.exists(path):
            return QPixmap()

        if path not in self.pixmap_cache:
            pm = QPixmap(path)
            if not pm.isNull():
                self.pixmap_cache[path] = pm
            else:
                return QPixmap()

        # Zeitstempel aktualisieren
        self.cache_usage_timestamps[path] = time.time()
        return self.pixmap_cache[path]

    def clear_cache(self):
        """Falls man Bilder im Betrieb austauscht (Reload)."""
        self.pixmap_cache.clear()

    # --- QUEUE & DISPLAY LOGIK ---
    def add_event_to_queue(self, img_path, sound_path, duration, x, y, scale=1.0, is_hitmarker=False):

        # --- FALL A: HITMARKER (Sofort & Parallel) ---
        if is_hitmarker:
            if sound_path:
                try:
                    if 'pygame' in sys.modules: pygame.mixer.Sound(sound_path).play()
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
                    if 'pygame' in sys.modules: pygame.mixer.Sound(sound_path).play()
                except:
                    pass

            self.display_image(img_path, duration, x, y, scale)
            return

        self.event_queue.append((img_path, sound_path, duration, x, y, scale))

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
        img_path, sound_path, duration, x, y, scale = self.event_queue.pop(0)

        self.display_image(img_path, duration, x, y, scale)

        if sound_path:
            try:
                if 'pygame' in sys.modules:
                    pygame.mixer.Sound(sound_path).play()
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
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            self.feed_label.setStyleSheet("background: transparent;")
            self.stats_bg_label.setStyleSheet("")
            self.streak_bg_label.setStyleSheet("")
            self.crosshair_label.setStyleSheet("background: transparent;")

            if enabled:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                self.edit_mode = False
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool |
                    Qt.WindowType.WindowTransparentForInput
                )
                self.show()
                if hasattr(self, 'event_preview_label'):
                    self.event_preview_label.hide()
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED)
                self.edit_mode = True
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool
                )
                self.show()
                self.raise_()
                self.activateWindow()

                hl_style = "border: 2px solid #00ff00; background-color: rgba(0, 255, 0, 50);"
                targets = active_targets if active_targets else []

                if "feed" in targets:
                    feed_style = "border: 2px solid #00ff00; background-color: rgba(0, 0, 0, 150);"
                    self.feed_label.setStyleSheet(feed_style)
                    self.feed_label.show()
                    self.feed_label.raise_()
                    if not self.feed_label.text():
                        self.feed_label.setText(
                            "<div style='color:white; font-size:20px; padding:10px;'>KILLFEED DRAG AREA</div>")
                        self.feed_label.adjustSize()

                if "stats" in targets:
                    self.stats_bg_label.setStyleSheet(hl_style)
                    self.stats_bg_label.show()
                    self.stats_text_label.show()
                    self.stats_text_label.raise_()

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

        except Exception as e:
            print(f"Passthrough Error: {e}")

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
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                cx = self.streak_bg_label.x() + (self.streak_bg_label.width() // 2)
                cy = self.streak_bg_label.y() + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label,
                               cx + self.s(cfg.get("tx", 0)) - (self.streak_text_label.width() // 2),
                               cy + self.s(cfg.get("ty", 0)) - (self.streak_text_label.height() // 2))

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
            elif self.dragging_widget == "streak":
                curr = self.streak_bg_label.pos()
                if "streak" not in self.gui_ref.config: self.gui_ref.config["streak"] = {}
                self.gui_ref.config["streak"]["x"] = uns(curr.x())
                self.gui_ref.config["streak"]["y"] = uns(curr.y())
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
        scaled = html_msg
        for size in [19, 16]: scaled = scaled.replace(f"{size}px", f"{(size * self.ui_scale)}px")
        if "style=\"" in scaled: scaled = scaled.replace("style=\"", "style=\"line-height: 100%; ")
        self.feed_messages.insert(0, scaled)
        self.feed_messages = self.feed_messages[:6]
        self.feed_label.setText(
            f'<div style="text-align: right; margin-right: 5px;">{"".join(self.feed_messages)}</div>')
        self.feed_label.show()
        self.repaint()

    def clear_killfeed(self):
        self.feed_messages = []
        self.feed_label.clear()
        self.repaint()

    def update_killfeed_pos(self):
        if not self.gui_ref: return
        conf = self.gui_ref.config.get("killfeed", {})
        self.safe_move(self.feed_label, self.s(conf.get("x", 50)), self.s(conf.get("y", 200)))

    def set_stats_html(self, html, img_path):
        # 1. Bild / Hintergrund
        if os.path.exists(img_path) or self.edit_mode:
            if os.path.exists(img_path):
                cfg = {}
                if self.gui_ref: cfg = self.gui_ref.config.get("stats_widget", {})
                sc = cfg.get("scale", 1.0) * self.ui_scale

                # --- CACHE GENUTZT ---
                pix = self.get_cached_pixmap(img_path)

                if not pix.isNull():
                    pix = pix.scaled(int(pix.width() * sc), int(pix.height() * sc), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    self.stats_bg_label.setPixmap(pix)
                    self.stats_bg_label.adjustSize()
            else:
                self.stats_bg_label.clear()
            self.stats_bg_label.show()
        else:
            self.stats_bg_label.hide()

        # 2. Text HTML skalieren
        scaled_html = html
        for size in [28, 22, 20, 19, 16, 14]:
            scaled_html = scaled_html.replace(f"{size}px", f"{int(size * self.ui_scale)}px")

        self.stats_text_label.setText(scaled_html)
        self.stats_text_label.adjustSize()
        self.stats_text_label.show()
        self.stats_text_label.raise_()

    def draw_streak_ui(self, img_path, count, factions, cfg, slot_map):
        if not cfg.get("active", True) and not self.edit_mode:
            self.streak_bg_label.hide();
            self.streak_text_label.hide()
            for l in self.knife_labels: l.hide()
            return
        if count <= 0 and not self.edit_mode:
            self.streak_bg_label.hide();
            self.streak_text_label.hide()
            for l in self.knife_labels: l.hide(); l._is_active = False
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

                for j in range(len(factions), len(self.knife_labels)): self.knife_labels[j].hide()

                fc, fs, sh = cfg.get("color", "#fff"), cfg.get("size", 26), int(cfg.get("shadow_size", 0))
                stl = [f"font-family: 'Black Ops One';", f"font-size: {int(fs * sc)}px;", f"color: {fc};"]
                if sh > 0: stl.append(f"text-shadow: {sh}px {sh}px 0 #000;")
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
            self.crosshair_label.hide();
            return

        # --- CACHE GENUTZT ---
        pix = self.get_cached_pixmap(path)
        if not pix.isNull():
            pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.crosshair_label.setPixmap(pix);
            self.crosshair_label.adjustSize()
            tx, ty = 0, 0
            if self.gui_ref:
                c = self.gui_ref.config.get("crosshair", {})
                rx, ry = c.get("x", 0), c.get("y", 0)
                if rx == 0 and ry == 0:
                    tx, ty = self.width() // 2, self.height() // 2
                else:
                    tx, ty = self.s(rx), self.s(ry)
            self.safe_move(self.crosshair_label, tx - (self.crosshair_label.width() // 2),
                           ty - (self.crosshair_label.height() // 2))
            self.crosshair_label.show()

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
