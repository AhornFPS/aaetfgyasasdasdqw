import sys
import os
import ctypes
import math
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QGraphicsDropShadowEffect)
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPen, QBrush, QTransform, QMovie
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QPoint, QSize

# Sound Support (Optional, falls pygame fehlt)
try:
    import pygame

    pygame.mixer.init()
except ImportError:
    pass


# Helper Funktion für Pfade (lokal definiert, damit wir keine Abhängigkeiten haben)
def get_asset_path(filename):
    if not filename: return ""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", filename)


def set_animated_background(label: QLabel, path: str):
    """
    Hilfsfunktion: Lädt ein Bild auf ein Label.
    Wenn es ein GIF ist, wird es animiert (QMovie).
    Wenn es ein statisches Bild ist, wird es normal angezeigt (QPixmap).
    """
    # 1. Eventuell laufenden alten Film stoppen
    if label.movie() is not None:
        label.movie().stop()
        label.setMovie(None)

    # 2. Prüfen, ob Pfad existiert
    if not path or not os.path.exists(path):
        label.clear()
        return

    # 3. Prüfen, ob es ein GIF ist
    if path.lower().endswith(".gif"):
        movie = QMovie(path)
        # Größe anpassen (optional, aber gut für Hintergründe)
        # Hinweis: label.size() kann 0 sein, wenn das Fenster noch nicht sichtbar ist.
        # Besser ist oft: movie.setScaledSize(QSize(width, height)) wenn bekannt.
        if label.width() > 0 and label.height() > 0:
            movie.setScaledSize(label.size())

        label.setMovie(movie)
        movie.start()
        label.setScaledContents(True)
    else:
        # 4. Es ist ein normales Bild
        pixmap = QPixmap(path)
        label.setPixmap(pixmap)
        label.setScaledContents(True)


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

    # --- QUEUE & DISPLAY LOGIK ---
    def add_event_to_queue(self, img_path, sound_path, duration, x, y, scale=1.0, is_hitmarker=False):

        # --- FALL A: HITMARKER (Sofort & Parallel) ---
        if is_hitmarker:
            # Sound sofort
            if sound_path:
                try:
                    if 'pygame' in sys.modules: pygame.mixer.Sound(sound_path).play()
                except:
                    pass

            # Bild sofort (auf extra Layer)
            if img_path and os.path.exists(img_path):
                self.show_hitmarker(img_path, duration, x, y, scale)
            return

        # --- FALL B: NORMALE EVENTS (Queue) ---
        if not hasattr(self, 'queue_enabled'): self.queue_enabled = True

        if not self.queue_enabled:
            # Queue aus: Alles abbrechen, sofort zeigen
            self.clear_queue_now()

            # Sound sofort
            if sound_path:
                try:
                    if 'pygame' in sys.modules: pygame.mixer.Sound(sound_path).play()
                except:
                    pass

            self.display_image(img_path, duration, x, y, scale)
            return

        # Queue an: Hinten anstellen (INKLUSIVE SOUND!)
        self.event_queue.append((img_path, sound_path, duration, x, y, scale))

        if not self.is_showing:
            self.process_next_event()

    def show_hitmarker(self, img_path, duration, abs_x, abs_y, scale=1.0):
        """Zeigt den Hitmarker auf einem unabhängigen Layer (Logik analog zu display_image)."""
        if hasattr(self, 'hitmarker_timer') and self.hitmarker_timer.isActive():
            self.hitmarker_timer.stop()

        if not img_path or not os.path.exists(img_path):
            self.hitmarker_label.hide()
            return

        pixmap = QPixmap(img_path)
        if pixmap.isNull(): return

        # Skalierung (Exakt wie in display_image)
        final_scale = self.ui_scale * scale
        if final_scale != 1.0:
            w = int(pixmap.width() * final_scale)
            h = int(pixmap.height() * final_scale)
            pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        self.hitmarker_label.setPixmap(pixmap)
        self.hitmarker_label.adjustSize()

        # Positionierung
        if abs_x == 0 and abs_y == 0:
            # Spezialfall: Wenn 0,0 übergeben wird, zentrieren wir es auf dem Bildschirm.
            # (Das ist der einzige Unterschied zu display_image, da Hitmarker per Default mittig sein sollen)
            center_x = (self.width() // 2) - (self.hitmarker_label.width() // 2)
            center_y = (self.height() // 2) - (self.hitmarker_label.height() // 2)
            self.safe_move(self.hitmarker_label, center_x, center_y)
        else:
            # Sonst nutzen wir die Koordinaten wie in display_image (s() rechnet Skalierung ein)
            self.safe_move(self.hitmarker_label, self.s(abs_x), self.s(abs_y))

        self.hitmarker_label.show()
        self.hitmarker_label.raise_()

        # Timer
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

        # Jetzt wieder mit 6 Werten (Sound ist zurück!)
        img_path, sound_path, duration, x, y, scale = self.event_queue.pop(0)

        # 1. Bild anzeigen
        self.display_image(img_path, duration, x, y, scale)

        # 2. Sound abspielen (Synchron zum Bild)
        if sound_path:
            try:
                if 'pygame' in sys.modules:
                    pygame.mixer.Sound(sound_path).play()
            except:
                pass

        # Timer starten für das nächste Event
        self.queue_timer.start(duration)

    def finish_current_event(self):
        self.process_next_event()

    def clear_queue_now(self):
        self.event_queue.clear()
        self.queue_timer.stop()
        self.is_showing = False

    def display_image(self, img_path, duration, abs_x, abs_y, scale=1.0):
        # 1. Aufräumen (Timer und alte Movies stoppen)
        if hasattr(self, 'hide_timer') and self.hide_timer.isActive():
            self.hide_timer.stop()

        if self.img_label.movie():
            self.img_label.movie().stop()
            self.img_label.setMovie(None)

        # 2. Prüfen ob Datei existiert
        if not img_path or not os.path.exists(img_path):
            self.img_label.hide()
            return

        # 3. Entscheidung: GIF oder Bild?
        if img_path.lower().endswith(".gif"):
            # --- GIF LOGIK (FIXED) ---
            movie = QMovie(img_path)
            if movie.isValid():
                # WICHTIG: Wir springen manuell zu Frame 0.
                # Das zwingt Qt, die Metadaten (Größe) sofort zu laden.
                movie.jumpToFrame(0)

                # Jetzt bekommen wir die korrekte Größe
                base_size = movie.currentImage().size()

                final_scale = self.ui_scale * scale

                # Nur skalieren, wenn wir eine gültige Größe haben
                if final_scale != 1.0 and not base_size.isEmpty():
                    w = int(base_size.width() * final_scale)
                    h = int(base_size.height() * final_scale)
                    movie.setScaledSize(QSize(w, h))

                self.img_label.setMovie(movie)
                movie.start()
        else:
            # --- NORMALE BILD LOGIK ---
            pixmap = QPixmap(img_path)
            if pixmap.isNull(): return

            final_scale = self.ui_scale * scale
            if final_scale != 1.0:
                w = int(pixmap.width() * final_scale)
                h = int(pixmap.height() * final_scale)
                pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)

            self.img_label.setPixmap(pixmap)

        # 4. Anzeigen & Positionieren
        self.img_label.adjustSize()
        self.safe_move(self.img_label, self.s(abs_x), self.s(abs_y))
        self.img_label.show()
        self.img_label.raise_()

        # 5. Timer zum Ausblenden
        if not hasattr(self, 'hide_timer'):
            self.hide_timer = QTimer(self)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self._hide_image_safe)

        self.hide_timer.start(duration)

    def _hide_image_safe(self):
        """Hilfsmethode: Stoppt das GIF sauber, um CPU zu sparen."""
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
        # Runden ist wichtig für Pixel-Perfektion bei Skalierung
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

            # Hole aktuellen Stil
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            # Stylesheets zurücksetzen (Rahmen entfernen)
            self.feed_label.setStyleSheet("background: transparent;")
            self.stats_bg_label.setStyleSheet("")
            self.streak_bg_label.setStyleSheet("")
            self.crosshair_label.setStyleSheet("background: transparent;")

            if enabled:
                # --- SPIEL-MODUS (Klicks gehen durch) ---
                # Wir setzen das TRANSPARENT Flag
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)

                self.edit_mode = False
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool |
                    Qt.WindowType.WindowTransparentForInput  # Wichtig: Qt sagen, dass es transparent ist
                )
                self.show()  # Neu zeichnen

                # Preview Label verstecken, wenn Edit aus ist
                if hasattr(self, 'event_preview_label'):
                    self.event_preview_label.hide()

            else:
                # --- EDIT-MODUS (Klicks werden abgefangen) ---
                # Wir entfernen das TRANSPARENT Flag
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED)

                self.edit_mode = True

                # Qt Flags aktualisieren: KEIN WindowTransparentForInput mehr!
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Tool
                )
                self.show()
                self.raise_()
                self.activateWindow()  # Fokus erzwingen

                # --- RAHMEN ZEICHNEN ---
                # Wir nutzen einen sichtbaren Rahmen und einen halb-transparenten Hintergrund
                hl_style = "border: 2px solid #00ff00; background-color: rgba(0, 255, 0, 50);"

                targets = active_targets if active_targets else []
                # Debugging Log
                print(f"DEBUG: Activating Edit Mode for targets: {targets}")

                if "feed" in targets:
                    # HIER IST DER FIX: Ein sichtbarer Hintergrund ist zwingend nötig zum Greifen!
                    # rgba(0, 0, 0, 150) macht es dunkelgrau und greifbar.
                    # border: 2px solid #00ff00 macht den grünen Rand.
                    feed_style = "border: 2px solid #00ff00; background-color: rgba(0, 0, 0, 150);"

                    self.feed_label.setStyleSheet(feed_style)
                    self.feed_label.show()
                    self.feed_label.raise_()  # Nach ganz vorne holen

                    # Fallback Text anzeigen, falls Feed leer ist (WICHTIG!)
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
                    # Dummy Streak anzeigen, damit man was zum Greifen hat
                    if not self.streak_bg_label.pixmap() or self.streak_bg_label.pixmap().isNull():
                        self.streak_bg_label.setText("STREAK AREA")
                        self.streak_bg_label.setStyleSheet(f"{hl_style} color: white; font-weight: bold;")
                        self.streak_bg_label.adjustSize()

                if "crosshair" in targets:
                    self.crosshair_label.setStyleSheet(hl_style)
                    self.crosshair_label.show()

                if "event" in targets:
                    # Das Event Preview Label muss existieren und sichtbar sein
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
            # 1. Hintergrund bewegen
            self.safe_move(self.stats_bg_label, new_pos.x(), new_pos.y())

            # 2. Text mitziehen (Live Berechnung)
            if self.gui_ref:
                cfg = self.gui_ref.config.get("stats_widget", {})

                # Aktuelle Geometrie
                bg_w = self.stats_bg_label.width()
                bg_h = self.stats_bg_label.height()
                txt_w = self.stats_text_label.width()
                txt_h = self.stats_text_label.height()

                # Offsets
                tx_off = self.s(cfg.get("tx", 0))
                ty_off = self.s(cfg.get("ty", 0))

                # Mitte berechnen basierend auf NEUER Position (new_pos)
                cx = new_pos.x() + (bg_w / 2)
                cy = new_pos.y() + (bg_h / 2)

                final_tx = cx - (txt_w / 2) + tx_off
                final_ty = cy - (txt_h / 2) + ty_off

                self.safe_move(self.stats_text_label, int(final_tx), int(final_ty))
        elif self.dragging_widget == "streak":
            self.safe_move(self.streak_bg_label, new_pos.x(), new_pos.y())
            # Text follows bg
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                cx = self.streak_bg_label.x() + (self.streak_bg_label.width() // 2)
                cy = self.streak_bg_label.y() + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label,
                               cx + self.s(cfg.get("tx", 0)) - (self.streak_text_label.width() // 2),
                               cy + self.s(cfg.get("ty", 0)) - (self.streak_text_label.height() // 2))

    def mouseReleaseEvent(self, event):
        if not self.edit_mode or not self.dragging_widget: return

        # Hilfsfunktion: Rundet mathematisch korrekt statt abzuschneiden
        def uns(val):
            return int(round(val / self.ui_scale))

        if self.gui_ref:
            # 1. EVENT BILDER
            if self.dragging_widget == "event":
                curr = self.event_preview_label.pos()
                ename = self.gui_ref.ovl_config_win.lbl_editing.text().replace("EDITING: ", "").strip()

                if "events" not in self.gui_ref.config: self.gui_ref.config["events"] = {}
                if ename not in self.gui_ref.config["events"]: self.gui_ref.config["events"][ename] = {}

                # Exakte Position speichern
                self.gui_ref.config["events"][ename]["x"] = uns(curr.x())
                self.gui_ref.config["events"][ename]["y"] = uns(curr.y())
                self.gui_ref.save_config()

            # 2. CROSSHAIR (Zentriert gespeichert)
            elif self.dragging_widget == "crosshair":
                # Wir wollen die Mitte des Crosshairs speichern, nicht die Ecke oben links
                curr = self.crosshair_label.pos()
                center_x = curr.x() + (self.crosshair_label.width() / 2)
                center_y = curr.y() + (self.crosshair_label.height() / 2)

                if "crosshair" not in self.gui_ref.config: self.gui_ref.config["crosshair"] = {}

                # Rückrechnung auf Basis-Auflösung (1080p)
                self.gui_ref.config["crosshair"]["x"] = uns(center_x)
                self.gui_ref.config["crosshair"]["y"] = uns(center_y)
                self.gui_ref.save_config()

            # 3. KILLFEED
            elif self.dragging_widget == "feed":
                curr = self.feed_label.pos()
                if "killfeed" not in self.gui_ref.config: self.gui_ref.config["killfeed"] = {}
                self.gui_ref.config["killfeed"]["x"] = uns(curr.x())
                self.gui_ref.config["killfeed"]["y"] = uns(curr.y())
                self.gui_ref.save_config()

            # 4. STATS WIDGET (Zentriert gespeichert via tx/ty Offset)
            elif self.dragging_widget == "stats":
                curr = self.stats_bg_label.pos()

                if "stats_widget" not in self.gui_ref.config:
                    self.gui_ref.config["stats_widget"] = {}

                # Nur Position updaten
                self.gui_ref.config["stats_widget"]["x"] = uns(curr.x())
                self.gui_ref.config["stats_widget"]["y"] = uns(curr.y())

                self.gui_ref.save_config()

            # 5. KILLSTREAK (Zentriert gespeichert)
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
        for size in [19, 16]: scaled = scaled.replace(f"{size}px", f"{int(size * self.ui_scale)}px")
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
                # Config laden um Scale zu bekommen
                cfg = {}
                if self.gui_ref: cfg = self.gui_ref.config.get("stats_widget", {})
                sc = cfg.get("scale", 1.0) * self.ui_scale

                pix = QPixmap(img_path)
                if not pix.isNull():
                    pix = pix.scaled(int(pix.width() * sc), int(pix.height() * sc), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    self.stats_bg_label.setPixmap(pix)
                    self.stats_bg_label.adjustSize()
            else:
                # Kein Bild, aber Edit Mode oder Placeholder
                self.stats_bg_label.clear()
                # Größe nicht hier setzen, das macht die main.py Logik

            self.stats_bg_label.show()
        else:
            self.stats_bg_label.hide()

        # 2. Text HTML skalieren
        scaled_html = html
        for size in [28, 22, 20, 19, 16, 14]:
            scaled_html = scaled_html.replace(f"{size}px", f"{int(size * self.ui_scale)}px")

        self.stats_text_label.setText(scaled_html)
        self.stats_text_label.adjustSize()

        # Text immer anzeigen (Sichtbarkeit wird über Main Loop gesteuert via hide/show)
        self.stats_text_label.show()
        self.stats_text_label.raise_()

        # WICHTIG: KEINE safe_move() AUFRUFE HIER!
        # Die Positionierung übernimmt jetzt exklusiv update_stats_position_safe in main.py

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
            pix = QPixmap(img_path)
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

                # PATH or CIRCLE
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
                        if not os.path.exists(kpath): lbl.hide(); continue

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

                # Text Update
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
        pix = QPixmap(path).transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
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
        # Pulse
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
                if alive < 0.4:  # Spawn anim
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

        pix = QPixmap(path)
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