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
import asyncio
import websockets
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from queue import Queue, Empty
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import traceback
from PIL import Image, ImageTk, ImageSequence, ImageGrab
import pyautogui
import pydirectinput
from ctypes import wintypes
import sqlite3
import tkinter.ttk as ttk  # Für die Tabs im Menü
import PyQt6
import dashboard_qt  # Die neue Datei muss im gleichen Ordner liegen!
import launcher_qt
import characters_qt
import settings_qt
import overlay_config_qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,  # Neu hinzugefügt
    QMainWindow,  # Neu hinzugefügt
    QListWidget,  # Neu hinzugefügt
    QStackedWidget,  # Neu hinzugefügt
    QGraphicsDropShadowEffect
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QMainWindow, QListWidget, QStackedWidget, QGraphicsDropShadowEffect,
    QColorDialog, QFileDialog # <--- QColorDialog und QFileDialog sicherstellen
)
from PyQt6.QtGui import (
    QPixmap,
    QColor,
    QPainter,  # Neu: Für das Zeichnen der Linie
    QPen,  # Neu: Für die Linien-Dicke und Farbe
    QBrush,  # Neu: Zum Ausfüllen der Kreise/Punkte
    QTransform  # Neu: Zum Rotieren der Messer am Pfad
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QObject,
    QTimer,
    QPoint  # Neu: Für die Koordinaten-Punkte
)

# Ermittelt den Ordner, in dem die EXE oder das Skript liegt
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_asset_path(filename):
    if not filename: return ""
    return os.path.join(BASE_DIR, "assets", filename)


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

    # --- HILFSMETHODE FÜR DEN CONTROLLER ---
    def switch_to_tab(self, index):
        """Wechselt den Tab und aktualisiert die Seitenleiste visuell."""
        self.nav_list.setCurrentRow(index)


class PathDrawingLayer(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        # WICHTIG: Klicks abfangen erlauben
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.parent_ovl = parent

    def mousePressEvent(self, event):
        if self.parent_ovl.path_edit_active:
            pos = event.pos()
            # Wir holen das Zentrum vom Skull-Label
            label_rect = self.parent_ovl.streak_bg_label.geometry()
            center = label_rect.center()

            # Offset berechnen
            off_x = pos.x() - center.x()
            off_y = pos.y() - center.y()

            self.parent_ovl.custom_path.append((off_x, off_y))
            self.parent_ovl.signals.path_points_updated.emit(self.parent_ovl.custom_path)
            self.update()
        else:
            event.ignore()

    def paintEvent(self, event):
        if not self.parent_ovl.path_edit_active: return

        from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
        from PyQt6.QtCore import QPoint

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Klick-Fläche (Unsichtbar, aber nötig für Maus-Events)
        painter.setBrush(QColor(0, 0, 0, 1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        if len(self.parent_ovl.custom_path) == 0: return

        skull_center = self.parent_ovl.streak_bg_label.geometry().center()

        # --- STIFTE DEFINIEREN ---
        # A) Der Schatten-Stift (Dick, Schwarz, halbtransparent)
        shadow_pen = QPen(QColor(0, 0, 0, 180), 5, Qt.PenStyle.SolidLine)

        # B) Der Haupt-Stift (Cyan, Gestrichelt)
        cyan_color = QColor(0, 242, 255)
        line_pen = QPen(cyan_color, 2, Qt.PenStyle.DashLine)

        # C) Punkte Stifte
        shadow_brush = QBrush(QColor(0, 0, 0, 180))
        point_brush = QBrush(cyan_color)
        point_pen = QPen(QColor(255, 255, 255), 1)

        # --- HILFSFUNKTION ZUM ZEICHNEN DER LINIEN ---
        def draw_path_lines(p):
            if len(self.parent_ovl.custom_path) > 1:
                for i in range(len(self.parent_ovl.custom_path) - 1):
                    p1 = skull_center + QPoint(int(self.parent_ovl.custom_path[i][0]),
                                               int(self.parent_ovl.custom_path[i][1]))
                    p2 = skull_center + QPoint(int(self.parent_ovl.custom_path[i + 1][0]),
                                               int(self.parent_ovl.custom_path[i + 1][1]))
                    p.drawLine(p1, p2)
                # Kreis schließen
                p_last = skull_center + QPoint(int(self.parent_ovl.custom_path[-1][0]),
                                               int(self.parent_ovl.custom_path[-1][1]))
                p_first = skull_center + QPoint(int(self.parent_ovl.custom_path[0][0]),
                                                int(self.parent_ovl.custom_path[0][1]))
                p.drawLine(p_last, p_first)

        # 2. SCHATTEN ZEICHNEN (Hintergrund)
        painter.setPen(shadow_pen)
        draw_path_lines(painter)

        # 3. GLOW/HAUPTLINIE ZEICHNEN (Vordergrund)
        painter.setPen(line_pen)
        draw_path_lines(painter)

        # 4. PUNKTE MIT SCHATTEN ZEICHNEN
        for pt_data in self.parent_ovl.custom_path:
            center = skull_center + QPoint(int(pt_data[0]), int(pt_data[1]))

            # Erst der schwarze Klecks dahinter
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow_brush)
            painter.drawEllipse(center, 8, 8)

            # Dann der bunte Punkt davor
            painter.setPen(point_pen)
            painter.setBrush(point_brush)
            painter.drawEllipse(center, 5, 5)


# WICHTIG: Signal-Klasse MUSS außerhalb der GUI stehen
# WICHTIG: Signal-Klasse MUSS außerhalb der GUI stehen
class OverlaySignals(QObject):
    # Bestehende Signale (von dir oben genannt)
    show_image = pyqtSignal(str, str, int, int, int, float, bool)
    killfeed_entry = pyqtSignal(str)
    update_stats = pyqtSignal(str, str)
    update_streak = pyqtSignal(str, int, list, dict, list)
    path_points_updated = pyqtSignal(list)
    clear_feed = pyqtSignal()

    # ZUSÄTZLICH BENÖTIGTE SIGNALE (damit connect_all_qt_signals nicht abstürzt)
    setting_changed = pyqtSignal(str, object)  # Für Grid-Auswahl
    test_trigger = pyqtSignal(str)  # Für Preview-Buttons
    edit_mode_toggled = pyqtSignal(str)  # FIX für den AttributeError!


# --- STABILES QTOVERLAY (SINGLE LABEL METHODE) ---
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
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # AUFLÖSUNGSSKALIERUNG
        self.base_height = 1080.0
        self.ui_scale = screen.height() / self.base_height
        self.ui_scale = max(0.8, self.ui_scale)
        self.event_center_x = screen.width() // 2
        self.event_center_y = (screen.height() // 2)

        # Transparente Ebene für die Pfad-Zeichnung (Ganz oben)

        # Initialisiere die Zeichen-Ebene
        self.path_layer = PathDrawingLayer(self)
        self.path_layer.setGeometry(self.rect())  # Füllt das ganze Fenster
        self.path_layer.show()

        # 3. WIDGETS
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

        # --- KILLFEED: SINGLE LABEL (STABIL GEGEN GHOSTING) ---
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

        # --- ZEICHEN-EBENE (WICHTIG: ALS LETZTES ERSTELLEN) ---
        self.path_edit_active = False
        self.custom_path = []
        self.path_layer = PathDrawingLayer(self)
        self.path_layer.setGeometry(self.rect())  # Einmalig setzen
        self.path_layer.hide()  # Standardmäßig aus

        # 4. SIGNALE
        self.signals = OverlaySignals()
        # Event Queue is the new connect.
        # self.signals.show_image.connect(self.display_image)
        self.signals.show_image.connect(self.add_event_to_queue)
        self.signals.killfeed_entry.connect(self.add_killfeed_row)
        self.signals.update_stats.connect(self.set_stats_html)
        self.signals.update_streak.connect(self.draw_streak_ui)
        self.signals.clear_feed.connect(self.clear_killfeed)

        self.set_mouse_passthrough(True)

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.animate_pulse)
        self.pulse_timer.start(40)

        # Repaint Timer gegen Artefakte (1 Sekunde)
        self.redraw_timer = QTimer(self)
        self.redraw_timer.timeout.connect(self.force_update)
        self.redraw_timer.start(1000)

        # --- QUEUE SYSTEM VARIABLEN ---
        self.event_queue = []  # Hier speichern wir die Events: (path, duration, x, y)
        self.is_showing = False  # Status: Läuft gerade eine Animation?
        self.queue_enabled = True

        # Timer für die Queue-Verarbeitung
        self.queue_timer = QTimer()
        self.queue_timer.setSingleShot(True)
        self.queue_timer.timeout.connect(self.finish_current_event)

        self.img_label = QLabel(self)
        self.img_label.setScaledContents(True)
        self.img_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.img_label.hide()
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            self.queue_enabled = self.gui_ref.config.get("event_queue_active", True)
        else:
            self.queue_enabled = True  # Fallback

    def add_event_to_queue(self, img_path, sound_path, duration, x, y, scale=1.0, is_hitmarker=False):
        """
        Fügt Event hinzu, spielt Hitmarker sofort parallel ab oder beachtet den Queue-Status.
        """

        if is_hitmarker:
            if sound_path:
                try:
                    pygame.mixer.Sound(sound_path).play()
                except:
                    pass

            if img_path and os.path.exists(img_path):
                self.display_image(img_path, duration, x, y, scale)
            return

        # --- NORMALER ABLAUF (Queue oder Instant) ---

        # Falls queue_enabled aus irgendeinem Grund fehlt (sollte durch __init__ fix da sein)
        if not hasattr(self, 'queue_enabled'):
            self.queue_enabled = True

        # MODUS: INSTANT (Queue ist AUSgeschaltet)
        if not self.queue_enabled:
            # Stoppt nur Bilder/Animationen, lässt Sounds weiterlaufen
            self.clear_queue_now()

            # Bild sofort anzeigen
            self.display_image(img_path, duration, x, y, scale)

            # Sound sofort spielen
            if sound_path:
                try:
                    pygame.mixer.Sound(sound_path).play()
                except Exception as e:
                    print(f"Sound Error: {e}")
            return

        # MODUS: QUEUE (Queue ist EINGESCHALTET)
        self.event_queue.append((img_path, sound_path, duration, x, y, scale))

        if not self.is_showing:
            self.process_next_event()

    def process_next_event(self):
        if not self.event_queue:
            self.is_showing = False
            return

        self.is_showing = True
        # Scale mit auspacken
        img_path, sound_path, duration, x, y, scale = self.event_queue.pop(0)

        # An display_image übergeben
        self.display_image(img_path, duration, x, y, scale)

        if sound_path:
            try:
                pygame.mixer.Sound(sound_path).play()
            except:
                pass

        self.queue_timer.start(duration)

    def finish_current_event(self):
        self.process_next_event()

    def clear_queue_now(self):
        """Leert die Warteschlange und stoppt aktuelle Timer."""
        self.event_queue.clear()
        self.queue_timer.stop()
        self.is_showing = False

    def resizeEvent(self, event):
        if hasattr(self, 'path_layer'):
            self.path_layer.setGeometry(self.rect())
        super().resizeEvent(event)

    def force_update(self):
        self.repaint()
        # Falls Edit an ist, Layer immer nach vorne holen
        if self.path_edit_active:
            self.path_layer.raise_()

    def s(self, value):
        return int(float(value) * self.ui_scale)

    def safe_move(self, widget, x, y):
        """Bewegt ein Widget mit Clamping und Magnet-Effekt an den Rändern."""
        screen_w = self.width()
        screen_h = self.height()
        w_w = widget.width()
        w_h = widget.height()

        # Konfigurierbare Magnet-Stärke (in Pixeln)
        snap = 25

        # --- Magnet-Logik (Snapping) ---
        # Horizontales Snapping (Links, Mitte, Rechts)
        if abs(x) < snap:
            x = 0  # Snap an linken Rand
        elif abs(x - (screen_w - w_w)) < snap:
            x = screen_w - w_w  # Snap an rechten Rand
        elif abs(x - (screen_w // 2 - w_w // 2)) < snap:
            x = screen_w // 2 - w_w // 2  # Snap an Mitte

        # Vertikales Snapping (Oben, Mitte, Unten)
        if abs(y) < snap:
            y = 0  # Snap an oberen Rand
        elif abs(y - (screen_h - w_h)) < snap:
            y = screen_h - w_h  # Snap an unteren Rand
        elif abs(y - (screen_h // 2 - w_h // 2)) < snap:
            y = screen_h // 2 - w_h // 2  # Snap an Mitte

        # --- Sicherheits-Clamping (Die "Mauer") ---
        # Dies verhindert, dass Werte jemals außerhalb des gültigen Bereichs landen
        final_x = max(0, min(int(x), screen_w - w_w))
        final_y = max(0, min(int(y), screen_h - w_h))

        widget.move(final_x, final_y)

    def set_mouse_passthrough(self, enabled=True, active_targets=None):
        try:
            hwnd = self.winId().__int__()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            extended_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            self.feed_label.setStyleSheet("background: transparent;")
            self.stats_bg_label.setStyleSheet("background: transparent;")
            self.streak_bg_label.setStyleSheet("background: transparent;")
            self.crosshair_label.setStyleSheet("background: transparent;")

            if enabled:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                                    extended_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                self.edit_mode = False
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                                    (extended_style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED)
                self.edit_mode = True
                style = "border: 2px solid #00ff00; background: rgba(0, 255, 0, 0.1);"
                targets = active_targets if active_targets else []

                # WICHTIG: Hier fügen wir .show() hinzu, damit die Box sichtbar wird
                if "feed" in targets:
                    self.feed_label.setStyleSheet(style)
                    self.feed_label.show()  # Zeigt den Feed-Bereich
                if "stats" in targets:
                    self.stats_bg_label.setStyleSheet(style)
                    self.stats_bg_label.show()  # Zeigt den Stats-Bereich
                if "streak" in targets:
                    self.streak_bg_label.setStyleSheet(style)
                    self.streak_bg_label.show()  # Zeigt den Streak-Bereich
                if "crosshair" in targets:
                    self.crosshair_label.setStyleSheet(style)
                    self.crosshair_label.show()  # Zeigt das Crosshair
        except Exception as e:
            print(f"Passthrough Error: {e}")

    # In der QtOverlay Klasse:
    def mousePressEvent(self, event):
        # Falls wir im Pfad-Edit Modus sind, bricht hier ab (PathDrawingLayer übernimmt)
        if getattr(self, "path_edit_active", False):
            return

        if not self.edit_mode: return
        pos = event.pos()

        # 1. EVENT LABEL CHECK (Das hat gefehlt!)
        # Wir prüfen, ob das Label sichtbar ist UND der Klick innerhalb des Rahmens liegt
        if self.event_preview_label.isVisible() and self.event_preview_label.geometry().contains(pos):
            self.dragging_widget = "event"
            self.drag_offset = pos - self.event_preview_label.pos()

        # 2. FEED CHECK
        elif "border" in self.feed_label.styleSheet() and self.feed_label.geometry().contains(pos):
            self.dragging_widget = "feed"
            self.drag_offset = pos - self.feed_label.pos()

        # 3. STATS CHECK
        elif "border" in self.stats_bg_label.styleSheet() and self.stats_bg_label.geometry().contains(pos):
            self.dragging_widget = "stats"
            self.drag_offset = pos - self.stats_bg_label.pos()

        # 4. STREAK CHECK
        elif "border" in self.streak_bg_label.styleSheet() and self.streak_bg_label.geometry().contains(pos):
            self.dragging_widget = "streak"
            self.drag_offset = pos - self.streak_bg_label.pos()

        # 5. CROSSHAIR CHECK
        elif "border" in self.crosshair_label.styleSheet() and self.crosshair_label.geometry().contains(pos):
            self.dragging_widget = "crosshair"
            self.drag_offset = pos - self.crosshair_label.pos()

    def paintEvent(self, event):
        # Wir nutzen ein internes Zeichnen auf dem path_layer, falls aktiv
        if getattr(self, "path_edit_active", False) and len(self.custom_path) > 0:
            from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
            from PyQt6.QtCore import QPoint

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            cyan_color = QColor(0, 242, 255)
            line_pen = QPen(cyan_color, 2, Qt.PenStyle.DashLine)
            point_brush = QBrush(cyan_color)
            point_pen = QPen(QColor(255, 255, 255), 1)

            # Mitte des Schädels als Nullpunkt für die Offsets
            skull_center = self.streak_bg_label.geometry().center()

            # 1. LINIEN ZEICHNEN
            if len(self.custom_path) > 1:
                painter.setPen(line_pen)
                for i in range(len(self.custom_path) - 1):
                    p1 = skull_center + QPoint(int(self.custom_path[i][0]), int(self.custom_path[i][1]))
                    p2 = skull_center + QPoint(int(self.custom_path[i + 1][0]), int(self.custom_path[i + 1][1]))
                    painter.drawLine(p1, p2)

                # Kreis schließen (letzter zu erstem)
                p_last = skull_center + QPoint(int(self.custom_path[-1][0]), int(self.custom_path[-1][1]))
                p_first = skull_center + QPoint(int(self.custom_path[0][0]), int(self.custom_path[0][1]))
                painter.drawLine(p_last, p_first)

            # 2. PUNKTE ZEICHNEN (Immer ganz oben)
            painter.setPen(point_pen)
            painter.setBrush(point_brush)
            for pt_data in self.custom_path:
                center = skull_center + QPoint(int(pt_data[0]), int(pt_data[1]))
                painter.drawEllipse(center, 5, 5)  # Etwas größere Punkte

    def mouseMoveEvent(self, event):
        if not self.edit_mode or not self.dragging_widget or not self.drag_offset:
            return

        # Position berechnen
        curr_mouse_pos = event.globalPosition().toPoint()
        new_pos = curr_mouse_pos - self.drag_offset

        # 1. EVENT BEWEGEN (Das hat gefehlt!)
        if self.dragging_widget == "event":
            self.safe_move(self.event_preview_label, new_pos.x(), new_pos.y())

        elif self.dragging_widget == "feed":
            self.safe_move(self.feed_label, new_pos.x(), new_pos.y())

        elif self.dragging_widget == "stats":
            self.safe_move(self.stats_bg_label, new_pos.x(), new_pos.y())
            # Text mitbewegen
            if self.gui_ref:
                cfg = self.gui_ref.config.get("stats_widget", {})
                tx, ty = self.s(cfg.get("tx", 0)), self.s(cfg.get("ty", 0))
                cx = self.stats_bg_label.x() + (self.stats_bg_label.width() // 2)
                cy = self.stats_bg_label.y() + (self.stats_bg_label.height() // 2)
                self.safe_move(self.stats_text_label,
                               cx + tx - (self.stats_text_label.width() // 2),
                               cy + ty - (self.stats_text_label.height() // 2))

        elif self.dragging_widget == "streak":
            self.safe_move(self.streak_bg_label, new_pos.x(), new_pos.y())
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                tx, ty = self.s(cfg.get("tx", 0)), self.s(cfg.get("ty", 0))
                cx = self.streak_bg_label.x() + (self.streak_bg_label.width() // 2)
                cy = self.streak_bg_label.y() + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label,
                               cx + tx - (self.streak_text_label.width() // 2),
                               cy + ty - (self.streak_text_label.height() // 2))

        elif self.dragging_widget == "crosshair":
            self.safe_move(self.crosshair_label, new_pos.x(), new_pos.y())

    def mouseReleaseEvent(self, event):
        if not self.edit_mode or not self.dragging_widget:
            return

        def uns(val):
            return int(val / self.ui_scale)

        if self.gui_ref:
            # Aktuellen Event-Namen aus dem Qt-Label der GUI holen
            current_event_name = self.gui_ref.ovl_config_win.lbl_editing.text().replace("EDITING: ", "").strip()

            if self.dragging_widget == "event":
                curr = self.event_preview_label.pos()

                # Config Struktur sichern
                if "events" not in self.gui_ref.config: self.gui_ref.config["events"] = {}
                if current_event_name not in self.gui_ref.config["events"]:
                    self.gui_ref.config["events"][current_event_name] = {}

                # Koordinaten unskaliert speichern
                self.gui_ref.config["events"][current_event_name]["x"] = uns(curr.x())
                self.gui_ref.config["events"][current_event_name]["y"] = uns(curr.y())
                self.gui_ref.save_config()
                print(f"DEBUG: Event '{current_event_name}' moved to {uns(curr.x())}, {uns(curr.y())}")

            elif self.dragging_widget == "crosshair":
                curr = self.crosshair_label.pos()
                center_x = curr.x() + (self.crosshair_label.width() // 2)
                center_y = curr.y() + (self.crosshair_label.height() // 2)
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

    # --- TASTATUR-STEUERUNG (SPACE ZUM STOPPEN) ---
    def keyPressEvent(self, event):
        if self.path_edit_active and event.key() == Qt.Key.Key_Space:
            # Ruft die Toggle-Funktion in der GUI auf -> Stoppt die Aufnahme
            if self.gui_ref:
                print("DEBUG: Space gedrückt -> Beende Path Record")
                self.gui_ref.start_path_record()
            event.accept()
            return
        super().keyPressEvent(event)

    # --- RENDERING LOGIK ---
    def add_killfeed_row(self, html_msg):
        """Aktualisiert den gesamten Killfeed-Block als Paket"""
        scaled_msg = html_msg
        for size in [19, 16]:
            scaled_msg = scaled_msg.replace(f"{size}px", f"{int(size * self.ui_scale)}px")

        if "style=\"" in scaled_msg:
            scaled_msg = scaled_msg.replace("style=\"", "style=\"line-height: 100%; ")

        self.feed_messages.insert(0, scaled_msg)
        self.feed_messages = self.feed_messages[:6]

        full_html = f'<div style="text-align: right; margin-right: 5px;">{"".join(self.feed_messages)}</div>'

        self.feed_label.setText(full_html)
        self.feed_label.show()
        QApplication.processEvents()
        self.repaint()

    def clear_killfeed(self):
        self.feed_messages = []
        self.feed_label.clear()
        self.repaint()

    def update_killfeed_pos(self):
        if not self.gui_ref: return
        kf_conf = self.gui_ref.config.get("killfeed", {})

        # --- NEU: Absolute Position (0,0 = Oben Links) ---
        # Standardwert z.B. 50, 200 (nicht mehr -800)
        abs_x = kf_conf.get("x", 50)
        abs_y = kf_conf.get("y", 200)

        # Nur noch Skalierung anwenden, keine Bildschirmmitte mehr draufrechnen
        self.safe_move(self.feed_label, self.s(abs_x), self.s(abs_y))

    def set_stats_html(self, html_content, img_path):
        cfg = {}
        if self.gui_ref and hasattr(self.gui_ref, 'config'):
            cfg = self.gui_ref.config.get("stats_widget", {})

        # Absolute Position aus Config laden
        base_x = self.s(cfg.get("x", 50))
        base_y = self.s(cfg.get("y", 500))

        has_image = os.path.exists(img_path)

        # --- HINTERGRUND ---
        if has_image or self.edit_mode:
            if has_image:
                pix = QPixmap(img_path);
                final_scale = cfg.get("scale", 1.0) * self.ui_scale
                if not pix.isNull():
                    pix = pix.scaled(int(pix.width() * final_scale), int(pix.height() * final_scale),
                                     Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.stats_bg_label.setPixmap(pix);
                    self.stats_bg_label.adjustSize()
            else:
                self.stats_bg_label.clear();
                self.stats_bg_label.resize(int(400 * self.ui_scale), int(50 * self.ui_scale))

            # WICHTIG: Nur bewegen, wenn wir NICHT im Edit-Modus sind!
            # Im Edit-Modus hat die Maus die Kontrolle.
            if not self.edit_mode:
                self.safe_move(self.stats_bg_label, base_x, base_y);

            self.stats_bg_label.show()
        else:
            self.stats_bg_label.hide()

        # --- TEXT ---
        scaled_html = html_content
        for size in [28, 22, 20, 19, 16, 14]:
            scaled_html = scaled_html.replace(f"{size}px", f"{int(size * self.ui_scale)}px")

        self.stats_text_label.setText(scaled_html);
        self.stats_text_label.adjustSize()

        # Positionierung berechnen
        # Wenn wir im Edit-Modus sind, nehmen wir die AKTUELLE Position des Hintergrunds als Referenz
        if self.edit_mode:
            bg_center_x = self.stats_bg_label.x() + (self.stats_bg_label.width() // 2)
            bg_center_y = self.stats_bg_label.y() + (self.stats_bg_label.height() // 2)
        else:
            # Sonst nehmen wir die Config-Werte (base_x/base_y sind Top-Left)
            bg_center_x = base_x + (self.stats_bg_label.width() // 2)
            bg_center_y = base_y + (self.stats_bg_label.height() // 2)

        # Text Feinjustierung (tx/ty) anwenden
        text_x = bg_center_x + self.s(cfg.get("tx", 0)) - (self.stats_text_label.width() // 2)
        text_y = bg_center_y + self.s(cfg.get("ty", 0)) - (self.stats_text_label.height() // 2)

        # Text immer bewegen (er muss ja dem Hintergrund folgen, auch beim Ziehen)
        # Aber nur wenn wir nicht gerade den Text selbst ziehen würden (was wir aktuell nicht tun, wir ziehen den BG)
        self.safe_move(self.stats_text_label, text_x, text_y);

        self.stats_text_label.show();
        self.stats_text_label.raise_()

    def display_image(self, img_path, duration, abs_x, abs_y, scale=1.0):
        """Zeigt Bild an, nutzt safe_move und versteckt es sicher nach 'duration'."""

        # 1. Altes Bild/Timer aufräumen
        if hasattr(self, 'hide_timer') and self.hide_timer.isActive():
            self.hide_timer.stop()

        # Falls kein Bild da ist -> Verstecken und raus
        if not img_path or not os.path.exists(img_path):
            self.img_label.hide()
            return

        pixmap = QPixmap(img_path)
        if pixmap.isNull(): return

        # 2. SKALIERUNG BERECHNEN (Deine Logik, unverändert)
        final_scale = self.ui_scale * scale

        if final_scale != 1.0:
            w = int(pixmap.width() * final_scale)
            h = int(pixmap.height() * final_scale)
            pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # 3. LABEL UPDATEN
        self.img_label.setPixmap(pixmap)
        self.img_label.adjustSize()

        # 4. POSITIONIEREN (Hier nutzen wir safe_move für korrekten Sitz!)
        x = self.s(abs_x)
        y = self.s(abs_y)

        # self.safe_move statt self.img_label.move nutzen!
        # Falls du safe_move nicht hast, nutze move(x,y), aber safe_move ist präziser.
        if hasattr(self, 'safe_move'):
            self.safe_move(self.img_label, x, y)
        else:
            self.img_label.move(x, y)

        self.img_label.show()
        self.img_label.raise_()

        # 5. TIMER ZUM AUSBLENDEN (WICHTIG!)
        # Wir erstellen einen Timer, der das Bild nach 'duration' ausblendet.
        # Wir speichern ihn in self, damit wir ihn beim nächsten Bild abbrechen können (siehe oben).
        if not hasattr(self, 'hide_timer'):
            self.hide_timer = QTimer(self)
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self.img_label.hide)

        self.hide_timer.start(duration)

    def draw_streak_ui(self, img_path, count, factions, cfg, slot_map):
        """
        Haupt-Anzeige für den Killstreak.
        JETZT MIT ABSOLUTER POSITIONIERUNG (0,0 = Oben Links).
        """
        import math
        import time
        from PyQt6.QtGui import QTransform
        from PyQt6.QtCore import QPoint

        # --- 1. Check Active ---
        if not cfg.get("active", True) and not self.edit_mode:
            self.streak_bg_label.hide()
            self.streak_text_label.hide()
            for l in self.knife_labels: l.hide()
            return

        if count <= 0 and not self.edit_mode:
            self.streak_bg_label.hide()
            self.streak_text_label.hide()
            for l in self.knife_labels:
                l.hide()
                l._is_active = False
            return

        display_count = count if count > 0 else 10
        final_scale = cfg.get("scale", 1.0) * self.ui_scale

        # --- 2. Haupt-Hintergrund (Skull) ---
        if os.path.exists(img_path):
            pix = QPixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(int(pix.width() * final_scale), int(pix.height() * final_scale),
                                 Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.streak_bg_label.setPixmap(pix)
                self.streak_bg_label.adjustSize()

                # --- ÄNDERUNG: Absolute Positionierung ---
                # Wir laden die Werte direkt (Standard z.B. 100, 100)
                # Keine Bildschirmmitte-Berechnung mehr!
                abs_x = self.s(cfg.get("x", 100))
                abs_y = self.s(cfg.get("y", 100))

                # Wir setzen das Label an diese Position (Top-Left)
                self.safe_move(self.streak_bg_label, abs_x, abs_y)
                self.streak_bg_label.show()

                # WICHTIG: Skull Center neu berechnen für die Messer
                skull_center = self.streak_bg_label.geometry().center()
                bx, by = abs_x, abs_y  # Für Text-Referenz

                path_data = cfg.get("custom_path", [])

                # Sicherstellen, dass genug Messer-Labels existieren
                while len(self.knife_labels) < len(factions):
                    lbl = QLabel(self)
                    lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    self.knife_labels.append(lbl)

                # ==========================================
                # MODUS 1: CUSTOM PATH (Messer auf Pfad)
                # ==========================================
                if len(path_data) > 2:
                    segments = []
                    total_l = 0
                    pts = [QPoint(int(p[0]), int(p[1])) for p in path_data]
                    for i in range(len(pts)):
                        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                        d = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
                        segments.append((p1, p2, d, total_l))
                        total_l += d

                    knives_per_ring_path = 50
                    for i in range(len(factions)):
                        label = self.knife_labels[i]
                        is_new_spawn = not label.isVisible()
                        f_tag = factions[i]
                        k_file = cfg.get(f"knife_{f_tag.lower()}", f"knife_{f_tag.lower()}.png")
                        k_path = get_asset_path(k_file)

                        if not os.path.exists(k_path): label.hide(); continue

                        slot_idx = slot_map[i] if slot_map and i < len(slot_map) else i
                        ring_idx = slot_idx // knives_per_ring_path
                        pos_in_ring = slot_idx % knives_per_ring_path
                        ring_scale = 1.0 + (ring_idx * 0.28)
                        target_dist = (pos_in_ring / knives_per_ring_path) * total_l

                        kx_off, ky_off = 0, 0
                        for p1, p2, seg_d, start_l in segments:
                            if start_l <= target_dist <= start_l + seg_d:
                                t = (target_dist - start_l) / seg_d
                                kx_off = (p1.x() + t * (p2.x() - p1.x())) * ring_scale
                                ky_off = (p1.y() + t * (p2.y() - p1.y())) * ring_scale
                                break

                        kx, ky = skull_center.x() + kx_off, skull_center.y() + ky_off
                        angle = math.degrees(math.atan2(ky_off, kx_off)) + 90
                        k_pix = QPixmap(k_path).transformed(QTransform().rotate(angle),
                                                            Qt.TransformationMode.SmoothTransformation)
                        k_pix = k_pix.scaled(self.s(90), self.s(90), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)

                        label.setPixmap(k_pix)
                        label.adjustSize()
                        label._base_off_x, label._base_off_y = kx - skull_center.x(), ky - skull_center.y()
                        label._is_active = True
                        if is_new_spawn: label._spawn_time = time.time()
                        self.safe_move(label, kx - (label.width() // 2), ky - (label.height() // 2))
                        label.show()

                # ==========================================
                # MODUS 2: SCHILD-KRANZ (DEFAULT KREIS)
                # ==========================================
                else:
                    knives_per_circle = 50
                    radius_step = self.s(22)
                    start_radius_x = (self.streak_bg_label.width() // 2) - self.s(15)
                    start_radius_y = (self.streak_bg_label.height() // 2) - self.s(15)

                    for i in range(len(factions)):
                        label = self.knife_labels[i]
                        is_new_spawn = not label.isVisible()
                        f_tag = factions[i]
                        k_file = cfg.get(f"knife_{f_tag.lower()}", f"knife_{f_tag.lower()}.png")
                        k_path = get_asset_path(k_file)
                        if not os.path.exists(k_path): label.hide(); continue

                        slot_idx = slot_map[i] if slot_map and i < len(slot_map) else i
                        ring_idx = slot_idx // knives_per_circle
                        pos_in_ring = slot_idx % knives_per_circle
                        angle = (pos_in_ring * (360 / knives_per_circle)) - 90
                        rad = math.radians(angle)

                        s_val = math.sin(rad)
                        jaw_narrowing = 1.0 - (0.15 * s_val) if s_val > 0 else 1.0
                        curr_rx = (start_radius_x + (ring_idx * radius_step)) * jaw_narrowing
                        curr_ry = (start_radius_y + (ring_idx * radius_step))

                        # Position relativ zum aktuellen Skull-Center berechnen
                        kx = skull_center.x() + int(curr_rx * math.cos(rad))
                        ky = skull_center.y() - self.s(20) + int(curr_ry * math.sin(rad))

                        k_pix = QPixmap(k_path).transformed(QTransform().rotate(angle + 90),
                                                            Qt.TransformationMode.SmoothTransformation)
                        k_pix = k_pix.scaled(self.s(90), self.s(90), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)

                        label.setPixmap(k_pix)
                        label.adjustSize()
                        label._base_off_x, label._base_off_y = kx - skull_center.x(), ky - skull_center.y()
                        label._is_active = True
                        if is_new_spawn: label._spawn_time = time.time()
                        self.safe_move(label, kx - (label.width() // 2), ky - (label.height() // 2))
                        label.show()

                # Cleanup alter Labels
                for j in range(len(factions), len(self.knife_labels)): self.knife_labels[j].hide()

                # --- 3. DIE ZAHL ANZEIGEN ---
                f_color = cfg.get("color", "#ffffff")
                f_size = cfg.get("size", 26)
                sh_size = int(cfg.get("shadow_size", 0))

                style_parts = [
                    f"font-family: 'Black Ops One', sans-serif",
                    f"font-size: {int(f_size * final_scale)}px",
                    f"color: {f_color}"
                ]
                if sh_size > 0:
                    style_parts.append(f"text-shadow: {sh_size}px {sh_size}px 0 #000")
                else:
                    style_parts.append("text-shadow: none")

                if cfg.get("bold", False): style_parts.append("font-weight: bold")
                if cfg.get("underline", False): style_parts.append("text-decoration: underline")

                self.streak_text_label.setText(f'<div style="{"; ".join(style_parts)}">{display_count}</div>')
                self.streak_text_label.adjustSize()

                # Positionierung der Zahl (Relativ zum Skull Center)
                # Skull Center + TextOffset - Halbe Textbreite
                tx = skull_center.x() + self.s(cfg.get("tx", 0))
                ty = skull_center.y() + self.s(cfg.get("ty", 0))

                self.safe_move(self.streak_text_label, tx - (self.streak_text_label.width() // 2),
                               ty - (self.streak_text_label.height() // 2))

                self.streak_text_label.show()
                self.streak_bg_label.raise_()
                self.streak_text_label.raise_()

                if self.path_edit_active:
                    self.path_layer.setGeometry(self.rect())
                    self.path_layer.show()
                    self.path_layer.raise_()

    def animate_pulse(self):
        """Kombiniert Spawn-Animation (Einfliegen) und Pulsieren"""
        if not self.streak_bg_label.isVisible(): return

        s_conf = {}
        if self.gui_ref:
            s_conf = self.gui_ref.config.get("streak", {})

        # 1. MASTER CHECK
        if not s_conf.get("active", True):
            return

        # Basis-Prüfung für Animation
        anim_enabled = s_conf.get("anim_active", True)

        try:
            user_val = int(s_conf.get("speed", 50))
            speed_factor = user_val / 20.0
        except:
            speed_factor = 2.5

        import time, math
        now = time.time()

        # Berechnung für das normale Pulsieren
        pulse_val = math.sin(now * speed_factor) * 0.04
        normal_pulse_scale = 1.0 + pulse_val

        center = self.streak_bg_label.geometry().center()
        cx, cy = center.x(), center.y()

        spawn_duration = 0.4  # Dauer des "Einfliegens" in Sekunden

        for lbl in self.knife_labels:
            if getattr(lbl, "_is_active", False) and lbl.isVisible():
                ox = getattr(lbl, "_base_off_x", 0)
                oy = getattr(lbl, "_base_off_y", 0)

                # Wann wurde dieses Messer gespawnt?
                spawn_time = getattr(lbl, "_spawn_time", 0)
                alive_time = now - spawn_time

                current_scale = 1.0

                # --- PHASE 1: SPAWN ANIMATION (Einfliegen) ---
                if alive_time < spawn_duration:
                    # Fortschritt 0.0 bis 1.0
                    progress = alive_time / spawn_duration

                    # Ease-Out Effekt (schnell starten, langsam landen)
                    # Wir starten bei Faktor 1.8 (weit draußen) und enden bei 1.0
                    start_dist_factor = 1.8
                    current_scale = start_dist_factor - (
                            (start_dist_factor - 1.0) * (math.sin(progress * (math.pi / 2))))

                # --- PHASE 2: NORMALES PULSIEREN ---
                else:
                    if anim_enabled:
                        current_scale = normal_pulse_scale
                    else:
                        current_scale = 1.0  # Stillstand, aber Spawn-Animation ist fertig

                # Neue Position berechnen
                new_x = cx + int(ox * current_scale)
                new_y = cy + int(oy * current_scale)

                lbl.move(new_x - (lbl.width() // 2), new_y - (lbl.height() // 2))

    def update_crosshair(self, path, size, enabled):
        """Aktualisiert das Crosshair: JETZT MIT ABSOLUTER POSITIONIERUNG"""
        # Wenn deaktiviert (und nicht im Edit-Modus) oder Datei fehlt -> Verstecken
        if (not enabled and not self.edit_mode) or not os.path.exists(path):
            self.crosshair_label.hide()
            return

        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # Skalieren
            pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            self.crosshair_label.setPixmap(pixmap)
            self.crosshair_label.adjustSize()

            # --- FIX: Absolute Koordinaten verwenden ---
            target_x = 0
            target_y = 0

            if self.gui_ref:
                c = self.gui_ref.config.get("crosshair", {})

                # Werte aus Config laden (Das sind jetzt absolute Werte, z.B. 960)
                raw_x = c.get("x", 0)
                raw_y = c.get("y", 0)

                # FALLBACK: Wenn X und Y beide 0 sind (z.B. frisch nach Reset oder neu),
                # setzen wir es automatisch in die Bildschirmmitte.
                if raw_x == 0 and raw_y == 0:
                    target_x = self.width() // 2
                    target_y = self.height() // 2
                else:
                    # Skalierung anwenden, falls UI-Scale aktiv ist
                    target_x = self.s(raw_x)
                    target_y = self.s(raw_y)

            # Label so verschieben, dass seine Mitte genau auf target_x/target_y liegt
            final_x = target_x - (self.crosshair_label.width() // 2)
            final_y = target_y - (self.crosshair_label.height() // 2)

            self.safe_move(self.crosshair_label, final_x, final_y)
            self.crosshair_label.show()


try:
    import pygame

    pygame.mixer.init()
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    print("ACHTUNG: 'pygame' fehlt. Sounds werden nicht abgespielt.")


# --- ERROR LOGGER ---
def log_exception(exc_type, exc_value, exc_traceback):
    with open("error_log.txt", "a") as f:
        f.write(f"\n--- CRASH LOG {time.ctime()} ---\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)


def get_short_name(path):
    """Gibt nur den Dateinamen ohne den kompletten Pfad zurück"""
    return os.path.basename(path) if path else "No file selected"


sys.excepthook = log_exception

# 1. Mapping der Item-IDs aus sanction-list.csv
PS2_DETECTION = {
    "CATEGORIES": {
        "Knife": "Knife Kill",
        "Grenade": "Nade Kill",
        "MAX": "Max Kill"
    },

    "NAMES": {
        "SpitFire Turret": "Spitfire Kill",
        "Spitfire Auto-Turret": "Spitfire Kill"
    },

    "SPECIAL_IDS": {
        "802512": "Spitfire Kill",
        "802514": "Spitfire Kill",
        "802515": "Spitfire Kill",
        "802516": "Spitfire Kill",
        "802517": "Spitfire Kill",
        "802518": "Spitfire Kill",
        "6005426": "Spitfire Kill",
        "6005427": "Spitfire Kill",
        "6009294": "Spitfire Kill",
        "6016202": "Spitfire Kill",
        "6016216": "Spitfire Kill",
        "6016217": "Spitfire Kill",
        "6016218": "Spitfire Kill",
        "6016219": "Spitfire Kill",
        "6015075": "Spitfire Kill",
        "6015076": "Spitfire Kill",
        "6015077": "Spitfire Kill",
        "6015078": "Spitfire Kill",
        "6015086": "Spitfire Kill",
        "6015087": "Spitfire Kill",
        "6015088": "Spitfire Kill",
        "6015089": "Spitfire Kill",
        "650": "Tankmine Kill",
        "6005961": "Tankmine Kill",
        "6005962": "Tankmine Kill",
        "6011878": "AP-Mine Kill",
        "6011923": "AP-Mine Kill",
        "6005243": "AP-Mine Kill",
        "6009995": "AP-Mine Kill",
        "6011915": "AP-Mine Kill",
        "6011924": "AP-Mine Kill",
        "1045": "AP-Mine Kill",
        "6005422": "AP-Mine Kill",
        "6005963": "AP-Mine Kill",
        "429": "AP-Mine Kill",
        "1044": "AP-Mine Kill"
    }
}

LOADOUT_MAP = {
    "infil": ["1", "8", "15", "28"],
    "max": ["7", "14", "21", "45"]
}

HSR_WEAPON_CATEGORY = {
    "AI MAX (Left)", "AI MAX (Right)", "Amphibious Rifle", "Anti-Materiel Rifle", "Assault Rifle", "Carbine",
    "Heavy Weapon",
    "Hybrid Rifle", "LMG", "Pistol", "Scout Rifle", "Shotgun", "SMG", "Sniper Rifle", "Amphibious Sidearm", "Knife"
}

# 2. Mapping für Aktionen (Experience IDs)IDs
PS2_EXP_DETECTION = {
    # --- SUPPORT ---
    "Revive": ["7", "53"],  # Normal & Squad Revive
    "Heal": ["4", "51"],  # Heal & Squad Heal
    "Resupply": ["34", "55"],  # Ammo Resupply
    "Repair": ["6", "28", "31", "87", "88", "89", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99", "100",
               "129", "130", "131", "132", "133", "134", "135", "136", "137", "138", "139", "140", "141", "142", "276",
               "302", "303", "358", "359", "438", "439", "503", "505", "581", "584", "605", "606", "617", "618", "629",
               "630", "641", "642", "653", "656", "1375", "1378", "1451", "1452", "1481", "1482", "1545", "1549",
               "1562", "1571", "1638", "1639", "1740", "1743", "1806", "1809", "1871", "1873", "1991", "1994", "2153",
               "2156"],  # MAX, Turret, Flash Repair

    # --- OBJECTIVE ---
    "Point Control": ["15", "16", "272", "556", "557"],  # Attack/Defend/Convert Control Point
    "Sunderer Spawn": ["233"],  # Jemand spawnt an deinem Bus  (Logistics)
    "Base Capture": ["19", "598"],  # Facility Captured
    "Break Construction": ["604", "616", "628"],
    # Construction zerstört# Construction zerstört# Construction zerstört# Construction zerstört
    "Alert End": ["328"],

    # --- COMBAT & SPECIAL ----
    "Road Kill": ["26"],  # Bestätigter Roadkill XP
    "Domination": ["10"],  # Domination Kill
    "Revenge": ["11"],  # Revenge Kill
    "Killstreak Stop": ["8"],  # "Stop the Killing"
    "Gunner Assist": ["373", "314", "146", "148", "149", "150", "154", "155", "515", "681"]  # Assist XP für Piloten
}

# Globale Konstanten
S_ID = "s:1799912354"
CONFIG_FILE = "config.json"



CHEAT_OPTIONS = [
    "Aimbot", "Magic Bullet", "Hitbox Mod", "Triggerbot",
    "Wallhack (ESP)", "Radar Hack", "Speedhack", "Flying",
    "Teleport", "No Recoil/Spread", "Fire Rate Mod", "Unlimited Heat",
    "Instant Hit", "No Collision", "Invincibility", "Stat Padding"
]

CHEAT_DESCRIPTIONS = {
    "Aimbot": "Automated target acquisition that unnaturally snaps the crosshair to critical hit zones.",
    "Magic Bullet": "Manipulation of projectile vectors, allowing shots to hit targets even when not directly aimed at them.",
    "Hitbox Mod": "Artificial enlargement of player hitboxes, resulting in an unnaturally high hit-rate.",
    "Triggerbot": "Automated firing system that triggers the weapon instantly when a target enters the reticle.",
    "Wallhack (ESP)": "Tactical overlay showing player positions, health, and distances through solid terrain.",
    "Radar Hack": "External real-time position tracking of all units far beyond the range of in-game detection tools.",
    "Speedhack": "Illegal modification of movement speed (client-speed) exceeding normal gameplay mechanics.",
    "Flying": "Suspension of gravity constants, allowing the character to move freely through the air without a jetpack.",
    "Teleport": "Instantaneous movement between coordinates or snapping to a target's position.",
    "No Recoil/Spread": "Complete elimination of weapon kick and bullet spread for perfect accuracy at any range.",
    "Fire Rate Mod": "Technical increase of the weapon's rate of fire beyond the server-defined maximum.",
    "Unlimited Heat": "Manipulation of the heat mechanic to allow continuous firing without cooldown or ammo depletion.",
    "Instant Hit": "Removal of projectile travel time (bullet velocity), making shots hit the target instantaneously.",
    "No Collision": "Modification allowing the player to walk through walls and solid objects (NoClip).",
    "Invincibility": "Exploiting game memory to prevent taking damage from any source (God Mode).",
    "Stat Padding": "Coordinated actions to artificially inflate character statistics outside of normal competitive play."
}


class DiorClientGUI:
    def __init__(self):
        # 1. BASIS-DATEN LADEN
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.init_db()
        self.config = self.load_config()
        self.overlay_config = self.config
        self.char_data = self.load_chars_from_db() or {}
        self.name_cache = self.load_cache_from_db() or {}

        # 2. LOGIK-VARIABLEN (Vor der GUI!)
        self.overlay_active_state = self.config.get("overlay_master_active", False)
        self.ps2_dir = self.config.get("ps2_path", "")
        self.current_world_id = self.config.get("world_id", "10")
        self.current_character_id = ""
        self.is_hud_editing = False  # Status für Edit-Modus
        self.overlay_win = None  # Vor-Definition gegen AttributeErrors

        self.server_map = {
            "Wainwright (EU)": "10", "Osprey (US)": "1",
            "SolTech (Asia)": "40", "Jaeger": "19"
        }

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

        # Enforcer / Watchdog / Network
        self.observer = None
        self.last_killer_name = "None"
        self.last_killer_id = "0"
        self.last_evidence_url = ""
        self.item_db = {}
        self.id_queue = Queue()
        self.websocket = None
        self.loop = None

        # Pfade
        self.assets_path = os.path.join("assets", "Planetside 2 ini")
        self.source_high = os.path.join(self.assets_path, "UserOptions_high.ini")
        self.source_low = os.path.join(self.assets_path, "UserOptions_low.ini")

        # 3. QT APP & FENSTER INITIALISIEREN
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setStyle("Fusion")

        # Die Unter-Fenster erstellen
        self.dash_window = dashboard_qt.DashboardWidget(self)  # Widget, nicht Window!
        self.dash_controller = dashboard_qt.DashboardController(self.dash_window)
        self.launcher_win = launcher_qt.LauncherWidget(self)
        self.char_win = characters_qt.CharacterWidget(self)
        self.ovl_config_win = overlay_config_qt.OverlayConfigWindow(self)
        self.settings_win = settings_qt.SettingsWidget(self)

        # WICHTIG: Overlay erstellen, BEVOR wir Signale verbinden
        # from Dior_Client import QtOverlay
        self.overlay_win = QtOverlay(self)

        # 4. MAIN HUB (Die Hülle)
        self.main_hub = DiorMainHub(self)

        # 5. SIGNALE VERBINDEN (Das Herzstück)
        # Jetzt existieren alle Fenster (inkl. Overlay), daher klappt das Routing
        self.connect_all_qt_signals()

        # 6. DATEN IN DIE FENSTER LADEN
        self.load_overlay_config_to_qt()
        self.settings_win.load_config(self.config, self.ps2_dir)

        # Dropdown füllen
        opts = list(self.char_data.keys()) if self.char_data else ["N/A"]
        self.ovl_config_win.char_combo.clear()
        self.ovl_config_win.char_combo.addItems(opts)

        # Positionen initialisieren
        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()

        # 7. ANZEIGEN
        self.main_hub.show()

        # 8. HINTERGRUND-THREADS & TIMER
        self.start_websocket_thread()
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

        threading.Thread(target=self.cache_worker, daemon=True).start()

        # Manuelle connects entfernt! -> Macht connect_all_qt_signals jetzt.

    # --- CROSSHAIR LOGIK (NEU) ---

    def browse_crosshair_qt(self):
        """Öffnet Datei-Dialog für Crosshair und aktualisiert sofort."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self.main_hub, "Wähle Crosshair Bild", self.BASE_DIR, "Images (*.png *.jpg *.jpeg)"
        )

        if file_path:
            # 1. Pfad im UI setzen
            filename = os.path.basename(file_path)
            target_path = get_asset_path(filename)

            # Falls Datei nicht in assets liegt -> kopieren
            if os.path.abspath(file_path) != os.path.abspath(target_path):
                try:
                    shutil.copy2(file_path, target_path)
                except Exception as e:
                    print(f"Copy Error: {e}")

            # UI Update
            self.ovl_config_win.cross_path.setText(filename)

            # 2. Config & Overlay sofort aktualisieren
            self.update_crosshair_from_qt()

    def update_crosshair_from_qt(self):
        """Liest UI-Werte (Checkbox, Pfad) und aktualisiert Config & Overlay."""
        ui = self.ovl_config_win

        # Daten aus UI lesen
        is_active = ui.check_cross.isChecked()
        img_name = ui.cross_path.text()

        # Config Update
        if "crosshair" not in self.config: self.config["crosshair"] = {}

        self.config["crosshair"]["active"] = is_active
        self.config["crosshair"]["file"] = img_name

        # Größe beibehalten (wird aktuell nicht im UI geändert, aber wir wollen es nicht verlieren)
        current_size = self.config["crosshair"].get("size", 32)

        self.save_config()

        # Overlay Live-Update
        if self.overlay_win:
            full_path = get_asset_path(img_name)
            # Nur anzeigen, wenn Checkbox AN ist UND Spiel läuft (oder Edit Mode)
            game_running = getattr(self, 'ps2_running', False)
            should_show = (is_active and game_running) or getattr(self, "is_hud_editing", False)

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
        """Speichert den Status des Master-Switches sofort."""
        self.overlay_active_state = checked  # Lokale Variable aktualisieren
        self.config["overlay_master_active"] = checked
        self.save_config()
        self.add_log(f"SYS: Global Overlay {'ENABLED' if checked else 'DISABLED'}")

    def connect_all_qt_signals(self):
        """Zentrales Management aller PyQt6 Signale (Vollständig & Syntax-Korrigiert)."""
        print("SYS: Connecting GUI signals...")

        # Shortcuts für weniger Schreibarbeit
        hub = self.main_hub  # Das Hauptfenster (Navigation)
        ui = self.ovl_config_win  # Overlay Config Fenster
        dash = self.dash_controller  # Das Dashboard (Buttons)

        # --- 1. DASHBOARD NAVIGATION (Vom Dashboard zum Hub) ---
        if hasattr(dash, 'btn_play'):
            self.safe_connect(dash.btn_play.clicked, lambda: hub.switch_to_tab(1))
        if hasattr(dash, 'btn_chars'):
            self.safe_connect(dash.btn_chars.clicked, lambda: hub.switch_to_tab(2))
        if hasattr(dash, 'btn_overlay'):
            self.safe_connect(dash.btn_overlay.clicked, lambda: hub.switch_to_tab(3))
        if hasattr(dash, 'btn_settings'):
            self.safe_connect(dash.btn_settings.clicked, lambda: hub.switch_to_tab(4))

        # Server-Wechsel im Dashboard
        if hasattr(dash, 'signals') and hasattr(dash.signals, 'server_changed'):
            self.safe_connect(dash.signals.server_changed, self.change_server_logic)

        # --- 2. OVERLAY CONFIG (Buttons im Index 3) ---

        # A) Identität & Master Switch
        self.safe_connect(ui.char_combo.currentTextChanged, self.update_active_char)
        self.safe_connect(ui.check_master.toggled, self.toggle_master_switch_qt)

        # B) Event-Selection (Grid Klick)
        # KORREKTUR: Mehrzeiliges try/except
        try:
            ui.signals.setting_changed.disconnect()
        except:
            pass

        ui.signals.setting_changed.connect(
            lambda key, val: self.load_event_ui_data(val) if key == "event_selection" else None
        )

        # --- FIX: Live-Preview wenn man tippt ---
        # Wenn sich der Text ändert -> Pfad suchen -> Bild im Config-Fenster updaten
        ui.ent_evt_img.textChanged.connect(
            lambda text: ui.update_preview_image(get_asset_path(text))
        )

        # C) Slider Auto-Save (Streak & Stats)
        for slider in [ui.slider_scale, ui.slider_tx, ui.slider_ty]:
            self.safe_connect(slider.valueChanged, self.save_streak_settings_from_qt)

        for slider in [ui.slider_st_scale, ui.slider_st_tx, ui.slider_st_ty]:
            self.safe_connect(slider.valueChanged, self.save_stats_config_from_qt)

        # D) Manuelle Save Buttons
        self.safe_connect(ui.btn_save_streak.clicked, self.save_streak_settings_from_qt)
        self.safe_connect(ui.btn_save_stats.clicked, self.save_stats_config_from_qt)
        self.safe_connect(ui.btn_save_voice.clicked, self.save_voice_config_from_qt)
        self.safe_connect(ui.btn_save_event.clicked, self.save_event_ui_data)

        # E) Voice Macros
        for combo in ui.voice_combos.values():
            self.safe_connect(combo.currentIndexChanged, self.save_voice_config_from_qt)

        # F) Browse Buttons (Image / Sound)
        # KORREKTUR: Mehrzeiliges try/except
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

        # --- KILLSTREAK TAB SIGNALE ---

        # 1. Main Background Image Browse
        try:
            ui.btn_browse_streak_img.clicked.disconnect()
        except:
            pass
        ui.btn_browse_streak_img.clicked.connect(lambda: self.browse_file_qt(ui.ent_streak_img, "png"))

        # 2. Path Recording Controls
        self.safe_connect(ui.btn_path_record.clicked, self.start_path_record)
        self.safe_connect(ui.btn_path_clear.clicked, self.clear_path)

        # 1. Checkboxen (Sofortiges Speichern bei Klick)
        self.safe_connect(ui.check_streak_master.toggled, self.save_streak_settings_from_qt)
        self.safe_connect(ui.check_streak_anim.toggled, self.save_streak_settings_from_qt)

        # 2. Messer-Browse Buttons (Dynamisch verbinden)
        # Wir nutzen eine kleine Helper-Schleife für TR, NC, VS
        for faction, btn in ui.knife_browse_btns.items():
            # Wir holen das passende Textfeld dazu
            line_edit = ui.knife_inputs[faction]
            # Lambda: Wir binden 'line_edit' fest an den Aufruf
            # disconnect ist hier wichtig, falls die Methode mehrfach aufgerufen wird
            try:
                btn.clicked.disconnect()
            except:
                pass
            btn.clicked.connect(lambda _, le=line_edit: self.browse_file_qt(le, "png"))

        # 3. Design: Color Picker & Font Size
        self.safe_connect(ui.btn_pick_color.clicked, self.pick_streak_color_qt)
        self.safe_connect(ui.combo_font_size.currentTextChanged, self.save_streak_settings_from_qt)

        # 4. Slider (Live Update) - Hattest du schon, hier nochmal zur Sicherheit vollständig
        for slider in [ui.slider_tx, ui.slider_ty, ui.slider_scale]:
            self.safe_connect(slider.valueChanged, self.save_streak_settings_from_qt)

        # 5. Action Buttons
        self.safe_connect(ui.btn_save_streak.clicked, self.save_streak_settings_from_qt)
        self.safe_connect(ui.btn_edit_streak.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_test_streak.clicked, self.test_streak_visuals)

        # G) Edit-Mode Buttons (Hud verschieben)
        self.safe_connect(ui.btn_edit_hud.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_edit_streak.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_edit_cross.clicked, self.toggle_hud_edit_mode)
        self.safe_connect(ui.btn_edit_hud_stats.clicked, self.toggle_hud_edit_mode)

        # H) Spezial-Funktionen (Apply All, Queue)
        if hasattr(ui, 'btn_apply_all'):
            self.safe_connect(ui.btn_apply_all.clicked, self.apply_event_layout_to_all)

        if hasattr(ui, 'btn_queue_toggle'):
            # Achtung: clicked sendet einen boolean, den fangen wir mit lambda ab oder ignorieren ihn
            # Am besten direkt verbinden, da unsere Funktion keine Argumente braucht
            self.safe_connect(ui.btn_queue_toggle.clicked, lambda: self.toggle_event_queue_qt())

        # --- 3. CHARACTERS & LAUNCHER (Index 2 & 1) ---
        self.safe_connect(self.char_win.signals.search_requested, self.run_search)
        self.safe_connect(self.char_win.signals.search_finished, self.process_search_results_qt)
        self.safe_connect(self.launcher_win.signals.launch_requested, self.execute_launch)

        # --- 4. SETTINGS (Index 4) ---
        self.safe_connect(self.settings_win.signals.browse_obs_requested, self.browse_folder)
        self.safe_connect(self.settings_win.signals.browse_ps2_requested, self.browse_ps2_folder)
        self.safe_connect(self.settings_win.signals.change_bg_requested, self.change_background_file)
        self.safe_connect(self.settings_win.signals.save_requested, self.save_enforcer_config_qt)

        # --- 5. TEST BUTTONS ---
        self.safe_connect(ui.btn_test_streak.clicked, self.test_streak_visuals)
        self.safe_connect(ui.btn_test_stats.clicked, self.test_stats_visuals)

        # Preview Event Button (KORREKTUR: Mehrzeilig)
        try:
            ui.btn_test_preview.clicked.disconnect()
        except:
            pass

        ui.btn_test_preview.clicked.connect(
            lambda: self.trigger_overlay_event(ui.lbl_editing.text().replace("EDITING: ", ""))
        )

        # --- 6. RÜCKKANAL VOM INGAME OVERLAY ---
        if self.overlay_win:
            self.safe_connect(self.overlay_win.signals.edit_mode_toggled, self.toggle_hud_edit_mode)

        # --- 7. CROSSHAIR TAB SIGNALE ---
        # A) Checkbox "Show Crosshair": Speichert sofort, wenn man klickt
        self.safe_connect(ui.check_cross.toggled, self.save_crosshair_settings_qt)

        # B) Pfad-Textfeld: Speichert, wenn sich der Text ändert
        self.safe_connect(ui.cross_path.textChanged, self.save_crosshair_settings_qt)

        # C) Browse Button: Öffnet den Datei-Browser für PNGs
        try:
            ui.btn_browse_cross.clicked.disconnect()
        except:
            pass
        ui.btn_browse_cross.clicked.connect(lambda: self.browse_file_qt(ui.cross_path, "png"))

        # D) Auto-Center Button: Berechnet die Mitte neu
        self.safe_connect(ui.btn_center_cross.clicked, self.center_crosshair_qt)

        # E) Edit Mode Button (bereits vorhanden, aber zur Sicherheit)
        self.safe_connect(ui.btn_edit_cross.clicked, self.toggle_hud_edit_mode)

        # --- I) CROSSHAIR TAB CONNECTIONS ---
        ui = self.ovl_config_win  # Nur zur Sicherheit, falls 'ui' Variable nicht im Scope ist

        # 1. Checkbox Toggle -> Sofort speichern & updaten
        self.safe_connect(ui.check_cross.toggled, self.update_crosshair_from_qt)

        # 2. Textfeld Änderung -> Sofort speichern & updaten
        self.safe_connect(ui.cross_path.textChanged, self.update_crosshair_from_qt)

        # 3. Browse Button
        # Vorher disconnecten um Mehrfachaufrufe zu vermeiden
        try:
            ui.btn_browse_cross.clicked.disconnect()
        except:
            pass
        ui.btn_browse_cross.clicked.connect(self.browse_crosshair_qt)

        # 4. Center Button
        self.safe_connect(ui.btn_center_cross.clicked, self.center_crosshair_qt)

        # 5. Move UI Button (Edit Mode)
        # Hinweis: toggle_hud_edit_mode prüft automatisch, welcher Tab offen ist.
        # Da wir im Crosshair Tab sind, wird "CROSSHAIR" als Target erkannt.
        self.safe_connect(ui.btn_edit_cross.clicked, self.toggle_hud_edit_mode)

        print("SYS: All signals routed via DiorMainHub.")

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
        """Liest Killstreak-Settings komplett aus Qt und speichert sie."""
        s_ui = self.ovl_config_win

        saved_color = self.config.get("streak", {}).get("color", "#ffffff")

        # Speed validieren
        try:
            speed_val = int(s_ui.ent_streak_speed.text())
        except:
            speed_val = 50

        # Neues Datenpaket schnüren
        new_streak = {
            "active": s_ui.check_streak_master.isChecked(),
            "anim_active": s_ui.check_streak_anim.isChecked(),

            # NEU: Main Image & Speed aus UI lesen
            "img": s_ui.ent_streak_img.text(),
            "speed": speed_val,

            "tx": s_ui.slider_tx.value(),
            "ty": s_ui.slider_ty.value(),
            "scale": s_ui.slider_scale.value() / 100.0,
            "knife_tr": s_ui.knife_inputs["TR"].text(),
            "knife_nc": s_ui.knife_inputs["NC"].text(),
            "knife_vs": s_ui.knife_inputs["VS"].text(),
            "size": int(s_ui.combo_font_size.currentText()),
            "color": saved_color,

            # Pfad bleibt erhalten (wird via Record Button separat gesetzt)
            "custom_path": self.config.get("streak", {}).get("custom_path", [])
        }

        if "streak" not in self.config: self.config["streak"] = {}
        self.config["streak"].update(new_streak)

        self.save_config()
        self.add_log("SYS: Killstreak settings updated.")

        if self.overlay_win:
            self.update_streak_display()

    def save_stats_config_from_qt(self):
        """Liest Stats & Feed Settings aus Qt und speichert sie."""
        s_ui = self.ovl_config_win

        # Stats Widget Daten
        st_data = {
            "active": s_ui.check_stats_active.isChecked(),
            "img": s_ui.ent_stats_img.text(),
            "tx": s_ui.slider_st_tx.value(),
            "ty": s_ui.slider_st_ty.value(),
            "scale": s_ui.slider_st_scale.value() / 100.0
        }

        # Killfeed Daten
        kf_data = {
            "hs_icon": s_ui.ent_hs_icon.text(),
            "show_revives": s_ui.check_show_revives.isChecked()
        }

        self.overlay_config["stats_widget"].update(st_data)
        self.overlay_config["killfeed"].update(kf_data)
        self.save_config()
        self.add_log("SYS: Stats & Killfeed configuration updated.")

    def save_voice_config_from_qt(self):
        """Liest Voice Macros aus Qt und speichert sie."""
        new_v = {}
        for key, combo in self.ovl_config_win.voice_combos.items():
            new_v[key] = combo.currentText()

        self.overlay_config["auto_voice"] = new_v
        self.save_config()
        self.add_log("SYS: Auto-Voice Macros saved.")

    def load_overlay_config_to_qt(self):
        """Überträgt ALLE Config-Werte in die Qt-Oberfläche (Nur Setzen, kein Connecten!)"""
        # 1. DATEN HOLEN
        s_conf = self.config.get("streak", {})
        st_conf = self.config.get("stats_widget", {"active": True})
        kf_conf = self.config.get("killfeed", {})
        v_conf = self.config.get("auto_voice", {})
        ev_conf = self.config.get("events", {})

        ui = self.ovl_config_win

        # --- QUEUE BUTTON INITIALISIEREN ---
        queue_active = self.config.get("event_queue_active", True)
        ui.btn_queue_toggle.setChecked(queue_active)

        if queue_active:
            ui.btn_queue_toggle.setText("QUEUE: ON")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #004400; color: white; font-weight: bold; padding: 10px;"
            )
        else:
            ui.btn_queue_toggle.setText("QUEUE: OFF")
            ui.btn_queue_toggle.setStyleSheet(
                "background-color: #440000; color: #ffcccc; font-weight: bold; padding: 10px;"
            )

        # WICHTIG: Den Status auch direkt ans Overlay senden, falls es schon läuft
        if self.overlay_win:
            self.overlay_win.queue_enabled = queue_active

        # --- 2. TAB 1: IDENTITY ---
        active_char = getattr(self, 'char_var_value', "SELECT_UNIT...")
        idx = ui.char_combo.findText(active_char)
        if idx >= 0: ui.char_combo.setCurrentIndex(idx)
        ui.check_master.setChecked(self.config.get("overlay_master_active", False))

        # --- 3. TAB 3: KILLSTREAK ---
        ui.slider_tx.setValue(s_conf.get("tx", 0))
        ui.slider_ty.setValue(s_conf.get("ty", 0))
        ui.slider_scale.setValue(int(s_conf.get("scale", 1.0) * 100))
        ui.check_streak_master.setChecked(s_conf.get("active", True))
        ui.check_streak_anim.setChecked(s_conf.get("anim_active", True))
        # Font Größe setzen
        current_size = str(s_conf.get("size", 26))
        idx = ui.combo_font_size.findText(current_size)
        if idx >= 0: ui.combo_font_size.setCurrentIndex(idx)

        # NEU: Main Image & Speed laden
        ui.ent_streak_img.setText(s_conf.get("img", "KS_Counter.png"))
        ui.ent_streak_speed.setText(str(s_conf.get("speed", 50)))

        # Bestehendes...
        ui.slider_tx.setValue(s_conf.get("tx", 0))
        ui.slider_ty.setValue(s_conf.get("ty", 0))

        # Button Farbe initialisieren
        c_hex = s_conf.get("color", "#ffffff")
        col = QColor(c_hex)
        text_col = "black" if col.lightness() > 128 else "white"
        ui.btn_pick_color.setStyleSheet(
            f"background-color: {c_hex}; color: {text_col}; font-weight: bold; border: 1px solid #555;"
        )
        for fac in ["TR", "NC", "VS"]:
            if fac in ui.knife_inputs:
                ui.knife_inputs[fac].setText(s_conf.get(f"knife_{fac.lower()}", ""))

        # --- 4. TAB 5: STATS & FEED ---
        ui.check_stats_active.setChecked(st_conf.get("active", True))
        ui.ent_stats_img.setText(st_conf.get("img", "stats_bg.png"))
        ui.slider_st_tx.setValue(st_conf.get("tx", 0))
        ui.slider_st_ty.setValue(st_conf.get("ty", 0))
        ui.slider_st_scale.setValue(int(st_conf.get("scale", 1.0) * 100))
        ui.ent_hs_icon.setText(kf_conf.get("hs_icon", "headshot.png"))
        ui.check_show_revives.setChecked(kf_conf.get("show_revives", True))

        # --- 5. TAB 2: EVENTS (GRID) ---
        if hasattr(ui, 'event_checkboxes'):
            for ev_name, checkbox in ui.event_checkboxes.items():
                entry = ev_conf.get(ev_name, {})
                is_active = entry.get("active", True) if isinstance(entry, dict) else True
                checkbox.setChecked(is_active)

        # --- 6. SIDEBAR REINIGEN (Sicherer Zugriff) ---
        if hasattr(ui, 'lbl_editing'): ui.lbl_editing.setText("EDITING: NONE")
        for attr_name in ['ent_text', 'ent_img', 'ent_sound']:
            field = getattr(ui, attr_name, None)
            if field: field.clear()

        # --- 7. TAB 6: VOICE MACROS ---
        for key, combo in ui.voice_combos.items():
            val = v_conf.get(key, "OFF")
            idx = combo.findText(str(val))
            if idx >= 0: combo.setCurrentIndex(idx)

        # --- TAB CROSSHAIR ---
        c_conf = self.config.get("crosshair", {})

        # 1. Pfad laden
        ui.cross_path.setText(c_conf.get("file", ""))

        # 2. Checkbox Status laden (WICHTIG für deine Anforderung)
        # Standard ist True, falls nichts gespeichert ist
        ui.check_cross.setChecked(c_conf.get("active", True))

        # --- CROSSHAIR DATEN LADEN ---
        c_conf = self.config.get("crosshair", {})

        # 1. Checkbox
        ui.check_cross.setChecked(c_conf.get("active", True))

        # 2. Pfad Textfeld
        ui.cross_path.setText(c_conf.get("file", "crosshair.png"))

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

    def reset_ui_layout(self):
        """Setzt alle HUD-Positionen zurück."""
        if not messagebox.askyesno("HUD Reset", "Möchtest du alle HUD-Positionen auf Standardwerte zurücksetzen?"):
            return

        mid_x = self.root.winfo_screenwidth() // 2
        mid_y = self.root.winfo_screenheight() // 2

        # 1. Standardwerte definieren (ABSOLUT)
        defaults = {
            "stats_widget": {"x": 50, "y": 800, "tx": 0, "ty": 0, "scale": 1.0, "active": True},
            "killfeed": {"x": 1400, "y": 50, "hs_icon": "headshot.png", "show_revives": True},
            # HIER: Streak Standard (z.B. Oben Mitte)
            "streak": {"x": mid_x - 50, "y": 100, "tx": 0, "ty": 0, "scale": 1.0, "active": True},
            "crosshair": {"x": mid_x, "y": mid_y, "size": 32, "active": True}
        }

        # 2. Config aktualisieren
        for key, val in defaults.items():
            if key not in self.config: self.config[key] = {}
            self.config[key].update(val)

        # 3. GUI-Elemente aktualisieren (Nur noch die, die es gibt)
        # Stats und Feed Slider gibt es nicht mehr -> Nichts zu tun hier für die.

        # 4. Speichern und Overlay triggern
        self.save_config()
        self.add_log("HUD: Alle Positionen wurden zurückgesetzt.")

        if self.overlay_win:
            self.overlay_win.update_killfeed_pos()

            c = self.config["crosshair"]
            game_running = getattr(self, 'ps2_running', False)
            should_show = c.get("active", True) and game_running
            path = get_asset_path(c.get("file", "crosshair.png"))
            self.overlay_win.update_crosshair(path, c.get("size", 32), should_show)

            self.refresh_ingame_overlay()

    def ps2_process_monitor(self):
        self.ps2_running = False
        while True:
            try:
                # Tasklist-Abfrage
                output = subprocess.check_output('TASKLIST /FI "IMAGENAME eq PlanetSide2_x64.exe"', shell=True).decode(
                    "cp1252", errors="ignore")
                is_now_running = "PlanetSide2_x64.exe" in output

                if is_now_running != self.ps2_running:
                    self.ps2_running = is_now_running

                    if is_now_running:
                        self.add_log("MONITOR: PlanetSide 2 gestartet.")
                        if self.overlay_active_state:
                            # Wir nutzen die Methode, die wir für Qt gebaut haben
                            # WICHTIG: Aufruf über das Hauptfenster/MainHub sicherstellen
                            from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
                            QMetaObject.invokeMethod(self.overlay_win, "showFullScreen",
                                                     Qt.ConnectionType.QueuedConnection)
                            QMetaObject.invokeMethod(self, "auto_enable_overlay", Qt.ConnectionType.QueuedConnection)

                            # Stats Refresh starten (Falls vorhanden)
                            if hasattr(self, 'refresh_ingame_overlay'):
                                QMetaObject.invokeMethod(self, "refresh_ingame_overlay",
                                                         Qt.ConnectionType.QueuedConnection)
                        else:
                            self.add_log("MONITOR: Master-Switch ist AUS. Overlay bleibt inaktiv.")
                    else:
                        self.add_log("MONITOR: PlanetSide 2 beendet.")
                        # Sicherer Aufruf der Stop-Logik
                        if hasattr(self, 'stop_overlay_logic'):
                            QMetaObject.invokeMethod(self, "stop_overlay_logic", Qt.ConnectionType.QueuedConnection)
                        elif self.overlay_win:
                            QMetaObject.invokeMethod(self.overlay_win, "hide", Qt.ConnectionType.QueuedConnection)

            except Exception as e:
                print(f"Monitor Loop Error: {e}")

            time.sleep(5)

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

    def auto_enable_overlay(self):
        """Wird gerufen, wenn PS2 startet."""
        if not self.overlay_win:
            # Hier musst du deine Overlay-Fenster Klasse importieren (z.B. QtOverlay)
            # self.overlay_win = QtOverlay(self)
            self.add_log("ERR: Overlay Fenster Objekt nicht initialisiert!")
            return

        # Sichtbar machen
        self.overlay_win.showFullScreen()

        # Crosshair laden aus Config
        c = self.config.get("crosshair", {})
        if c.get("active", True) and hasattr(self.overlay_win, 'update_crosshair'):
            self.overlay_win.update_crosshair(
                os.path.join(self.BASE_DIR, "assets", c.get("file", "crosshair.png")),
                c.get("size", 32),
                True
            )
        self.add_log("SYS: Overlay HUD synchronisiert.")

    def auto_disable_overlay(self):
        """Wird aufgerufen, wenn das Spiel geschlossen wird."""
        if self.overlay_win:
            # Wir verstecken nur das Crosshair, das Overlay selbst
            # bleibt für Event-Logs im Hintergrund aktiv (optional)
            self.overlay_win.crosshair_label.hide()
            self.add_log("GAME: PlanetSide 2 beendet. Crosshair ausgeblendet.")

    def start_qt_overlay(self):
        try:
            if self.overlay_win is None:
                self.overlay_win = QtOverlay(self)
                self.overlay_win.gui_ref = self
            self.overlay_win.update_killfeed_pos()
            self.overlay_win.showFullScreen()
            self.add_log("OVERLAY: UI System bereit.")
        except Exception as e:
            self.add_log(f"QT Error: {e}")

    def pump_qt(self):
        if self.qt_app:
            self.qt_app.processEvents()
        self.root.after(10, self.pump_qt)

    def toggle_overlay(self):
        """Startet oder stoppt das Ingame-Overlay Fenster."""
        # Falls das Fenster noch nie erstellt wurde
        if self.overlay_win is None:
            try:
                  # Importiere deine Overlay-Klasse
                self.overlay_win = QtOverlay(self)  # Übergib 'self' für den Datenzugriff
                self.add_log("SYS: Overlay-Instanz erstellt.")
            except Exception as e:
                self.add_log(f"ERR: Overlay konnte nicht erstellt werden: {e}")
                return

        # Umschalten der Sichtbarkeit
        if self.overlay_win.isVisible():
            self.overlay_win.hide()
            self.add_log("SYS: Overlay versteckt.")
        else:
            # Overlay anzeigen und in den Vordergrund bringen
            self.overlay_win.showFullScreen()
            self.overlay_win.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowTransparentForInput  # Wichtig für 'Durchklicken'
            )
            self.overlay_win.show()
            self.add_log("SYS: Overlay aktiviert.")

    def init_db(self):
        conn = sqlite3.connect("ps2_master.db")
        cursor = conn.cursor()

        # 1. Tabelle für alle gesuchten Spieler (Cache)
        cursor.execute('''CREATE TABLE IF NOT EXISTS player_cache 
                          (character_id TEXT PRIMARY KEY, name TEXT, name_lower TEXT, 
                           faction_id INTEGER, world_id INTEGER, outfit_tag TEXT, 
                           battle_rank INTEGER, created_date TEXT, last_login TEXT, 
                           kills INTEGER, deaths INTEGER, score INTEGER, playtime INTEGER,
                           m30_kills INTEGER, m30_deaths INTEGER, m30_score INTEGER, m30_time INTEGER)''')

        # 2. Tabelle für DEINE Charaktere (Diese hat gefehlt!)
        cursor.execute('''CREATE TABLE IF NOT EXISTS my_chars 
                          (character_id TEXT PRIMARY KEY, name TEXT)''')

        conn.commit()
        conn.close()

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

    def load_chars_from_db(self):
        conn = sqlite3.connect("ps2_master.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name, character_id FROM my_chars")
        data = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return data

    def load_cache_from_db(self):
        try:
            conn = sqlite3.connect("ps2_master.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # ÄNDERUNG: Wir laden jetzt auch outfit_tag
            cursor.execute("SELECT character_id, name, outfit_tag FROM player_cache")
            rows = cursor.fetchall()
            conn.close()

            # Wir füllen direkt den Cache für Outfits
            self.outfit_cache = {row['character_id']: row['outfit_tag'] for row in rows}

            return {row['character_id']: row['name'] for row in rows}
        except Exception as e:
            self.add_log(f"DB Error: {e}")
            self.outfit_cache = {}  # Fallback
            return {}

    def load_config(self):
        """Lädt die zentrale Konfiguration aus der config.json"""
        config_path = os.path.join(BASE_DIR, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Fehler beim Laden der config.json: {e}")

        # Falls die Datei nicht existiert, geben wir ein Standard-Skelett zurück
        return {
            "ps2_path": "",
            "watch_folder": "",
            "crosshair": {"file": "", "size": 32, "active": True},
            "events": {},
            "streak": {"img": "KS_Counter.png", "x": 0, "y": 100, "scale": 1.5}
        }

    def toggle_master_switch(self):
        """Speichert den Master-Switch Zustand und aktualisiert sofort"""
        is_active = self.overlay_active.get()
        self.config["overlay_master_active"] = is_active
        self.save_config()

        if is_active:
            self.add_log("MASTER: Overlay aktiviert.")
            if getattr(self, 'ps2_running', False):
                self.auto_enable_overlay()  # Crosshair an
                self.refresh_ingame_overlay()  # Stats an
                if self.overlay_win and hasattr(self.overlay_win, 'feed_label'):
                    self.overlay_win.feed_label.show()
        else:
            self.add_log("MASTER: Overlay deaktiviert.")
            self.stop_overlay_logic()  # Versteckt Stats, Feed & Streak (Zahl + Bild)

            # Crosshair auch explizit verstecken
            if self.overlay_win:
                self.overlay_win.crosshair_label.hide()

    def save_overlay_config(self):
        """Wrapper, damit alte Aufrufe im Code weiterhin funktionieren"""
        self.save_config()
        self.add_log("Einstellungen in config.json gesichert.")

    # --- NSO LOGIC LOOP ---
    def start_nso_teleport(self):
        if not self.nso_running:
            self.nso_running = True
            self.add_log(f"NSO: Starte Teleport-Schleife für {self.frac_var.get()} auf {self.cont_var.get()}...")
            threading.Thread(target=self.nso_logic_loop, daemon=True).start()

    def stop_nso_teleport(self):
        self.nso_running = False
        self.add_log("NSO: Teleport-Schleife GESTOPPT.")

    def nso_logic_loop(self):
        # Koordinaten-Definitionen
        COORDS = {
            "WORLD_MAP_BTN": (950, 37),
            "WORLD_MAP_2": (950, 300),
            "WORLD_MAP_RESET": (930, 260),
            "CONT_LIST": {
                "Indar": (100, 220), "Hossin": (100, 255),
                "Amerish": (100, 300), "Esamir": (100, 340),
                "Oshur": (100, 380), "Sanctuary": (100, 660)
            },
            "WARP_BTN": (240, 870),
            "TR_SYMBOL": (1760, 1016),
            "VS_SYMBOL": (1753, 1025),
            "NC_SYMBOL": (1758, 1007)
        }

        TARGET_COLORS = {
            "TR": (200, 0, 0), "VS": (60, 29, 154), "NC": (0, 50, 144)
        }

        # --- COUNTDOWN ---
        for i in range(5, 0, -1):
            if not self.nso_running: return
            self.add_log(f"NSO: Initialisierung in {i}...")
            time.sleep(1)

        while self.nso_running:
            try:
                # 1. Warp zum Ziel-Kontinent
                self.add_log("NSO: Öffne Karte (M)...")
                pydirectinput.press('m')
                time.sleep(2)

                self.add_log("NSO: Klicke Worldmap Button 1...")
                pydirectinput.click(COORDS["WORLD_MAP_BTN"][0], COORDS["WORLD_MAP_BTN"][1])
                time.sleep(1)

                self.add_log("NSO: Klicke Worldmap Button 2...")
                pydirectinput.click(COORDS["WORLD_MAP_2"][0], COORDS["WORLD_MAP_2"][1])
                time.sleep(1)

                target_cont = self.cont_var.get()
                self.add_log(f"NSO: Wähle {target_cont}...")
                cont_coords = COORDS["CONT_LIST"].get(target_cont)
                pydirectinput.click(cont_coords[0], cont_coords[1])
                time.sleep(1)

                self.add_log("NSO: Klicke Warp...")
                pydirectinput.click(COORDS["WARP_BTN"][0], COORDS["WARP_BTN"][1])

                self.add_log(f"NSO: Warping... Ladebildschirm (25s).")
                time.sleep(8)

                if not self.nso_running:
                    self.add_log("NSO: Abbruch durch Benutzer während Ladebildschirm.")
                    break

                # 2. Pixel-Check (Bleibt bei ImageGrab/PIL)
                faction = self.frac_var.get()
                check_coord = COORDS[f"{faction}_SYMBOL"]
                target_rgb = TARGET_COLORS[faction]

                current_px = ImageGrab.grab().getpixel(check_coord)

                if all(abs(current_px[i] - target_rgb[i]) < 35 for i in range(3)):
                    self.add_log(f"NSO: ERFOLG! {faction} beigetreten.")
                    self.nso_running = False
                    break

                if not self.nso_running: break

                # 3. Falsche Fraktion -> Reset
                self.add_log(f"NSO: Falsche Fraktion. Reset via Sanctuary...")
                pydirectinput.press('m')
                time.sleep(2)
                pydirectinput.click(COORDS["WORLD_MAP_BTN"][0], COORDS["WORLD_MAP_BTN"][1])
                time.sleep(1)
                pydirectinput.click(COORDS["WORLD_MAP_RESET"][0], COORDS["WORLD_MAP_RESET"][1])
                time.sleep(1)
                pydirectinput.click(COORDS["CONT_LIST"]["Sanctuary"][0], COORDS["CONT_LIST"]["Sanctuary"][1])
                time.sleep(1)
                pydirectinput.click(COORDS["WARP_BTN"][0], COORDS["WARP_BTN"][1])

                time.sleep(8)

            except Exception as e:
                self.add_log(f"NSO-FEHLER: {e}")
                self.nso_running = False

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

        # 1. POPULATION & FRAKTIONEN (Direktes Emit)
        total_players = self.live_stats.get("Total", 0)
        self.dash_controller.signals.update_population.emit(total_players)

        faction_data = {
            "TR": self.live_stats.get("TR", 0),
            "NC": self.live_stats.get("NC", 0),
            "VS": self.live_stats.get("VS", 0),
            "NSO": self.live_stats.get("NSO", 0)
        }
        self.dash_controller.signals.update_factions.emit(faction_data)

        # 2. TOP PLAYER LISTE VORBEREITEN
        active_ids = self.active_players.keys()
        now = time.time()
        prepared_players = []

        for p_id, p in self.session_stats.items():
            # Nur Spieler berücksichtigen, die noch als 'aktiv' markiert sind
            if not isinstance(p, dict) or p_id not in active_ids:
                continue

            # --- NAMEN-FIX ---
            # Falls die API noch lädt, nutzen wir den Cache
            p_name = p.get("name")
            if p_name in ["Unknown", "Searching...", None]:
                p_name = self.name_cache.get(p_id, f"ID: {p_id[-4:]}")

            # --- KPM LOGIK ---
            # Wir nutzen die Zeit seit dem ersten Kill dieser Session
            p_start = p.get("start", now)
            active_min = max((now - p_start) / 60, 0.5)

            # Paket schnüren (Wichtig: Nur Basisdaten, die GUI berechnet den Rest)
            prepared_players.append({
                "name": p_name,
                "fac": p.get("faction", "NSO"),
                "k": p.get("k", 0),
                "d": p.get("d", 0),
                "a": p.get("a", 0),
                "active_min": active_min
            })

        # 3. SORTIERUNG (Nach Kills, damit das Dashboard oben die Besten zeigt)
        prepared_players.sort(key=lambda x: x['k'], reverse=True)

        # Signal abfeuern (Top 20 reicht meist für die Anzeige)
        self.dash_controller.signals.update_top_list.emit(prepared_players[:20])

    def open_server_menu(self, event):
        """Öffnet das Popup-Menü zur Serverwahl"""
        menu = tk.Menu(self.root, tearoff=0, bg="#1a1a1a", fg="white", activebackground="#00f2ff",
                       activeforeground="black")

        for name, s_id in self.server_map.items():
            # Wir nutzen lambda, um name und s_id an die Funktion zu übergeben
            menu.add_command(label=name, command=lambda n=name, i=s_id: self.switch_server(n, i))

        # Menü an der Mausposition öffnen
        menu.tk_popup(event.x_root, event.y_root)

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

    def refresh_preview_graphics(self, _=None):
        """Zeigt die Bilder permanent an, damit man sie verschieben kann"""
        if not hasattr(self, 'preview_mode') or not self.preview_mode.get():
            return
        if not hasattr(self, 'ovl_canvas'):
            return

        # 1. Das Crosshair an die aktuelle Slider-Position setzen
        self.apply_crosshair_settings()

        # 2. Das aktuell gewählte Event-Bild (Kill/Death) anzeigen
        etype = self.var_event_sel.get()
        img_path = self.ent_evt_img.get()  # Pfad aus dem Textfeld lesen

        if img_path and os.path.exists(img_path):
            try:
                # Altes Vorschaubild löschen, damit es nicht doppelt da ist
                self.ovl_canvas.delete("preview_event")

                img = Image.open(img_path)
                # Position berechnen: Bildschirmmitte + Slider-Werte
                x = (self.ovl_win.winfo_screenwidth() // 2) + self.scale_ex.get()
                y = (self.ovl_win.winfo_screenheight() // 2) + self.scale_ey.get()

                self.preview_photo = ImageTk.PhotoImage(img)
                # Hier wird das Bild mit dem Tag 'preview_event' gezeichnet
                self.ovl_canvas.create_image(x, y, image=self.preview_photo, tags="preview_event")
            except Exception as e:
                print(f"Preview Draw Error: {e}")

    def toggle_preview(self):
        if not hasattr(self, 'ovl_win'): return

        hwnd = ctypes.windll.user32.GetParent(self.ovl_win.winfo_id())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000

        if self.preview_mode.get():
            # EDIT-MODUS AN: Click-Through AUS (damit Maus greifen kann)
            style = WS_EX_LAYERED | WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            # Maus-Events an das Canvas binden
            self.ovl_canvas.bind("<Button-1>", self.start_drag)
            self.ovl_canvas.bind("<B1-Motion>", self.do_drag)
            self.ovl_canvas.bind("<ButtonRelease-1>", self.stop_drag)

            self.refresh_preview_graphics()
            self.add_log("Edit-Modus: Du kannst Bilder jetzt mit der Maus verschieben!")
        else:
            # SPIEL-MODUS: Click-Through AN
            style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            # Events lösen
            self.ovl_canvas.unbind("<Button-1>")
            self.ovl_canvas.unbind("<B1-Motion>")
            self.ovl_canvas.unbind("<ButtonRelease-1>")

            if hasattr(self, 'ovl_canvas'):
                self.ovl_canvas.delete("preview_event")
            self.add_log("Edit-Modus AUS: Klicks gehen wieder ins Spiel.")

    def start_drag(self, event):
        """Merkt sich die Startposition beim Anklicken"""
        item = self.ovl_canvas.find_closest(event.x, event.y)
        if item:
            self.dragging_item = item
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y

    def stop_drag(self, event):
        """Speichert die neue Position in die Config, wenn man loslässt"""
        if self.dragging_item:
            # Berechne Offset zur Mitte
            mid_x = self.ovl_win.winfo_screenwidth() // 2
            mid_y = self.ovl_win.winfo_screenheight() // 2

            new_x = event.x - mid_x
            new_y = event.y - mid_y

            # Prüfen, was verschoben wurde (Crosshair oder Event)
            tags = self.ovl_canvas.gettags(self.dragging_item)
            if "crosshair" in tags:
                self.scale_cx.set(new_x)
                self.scale_cy.set(new_y)
            elif "preview_event" in tags:
                self.scale_ex.set(new_x)
                self.scale_ey.set(new_y)

            self.dragging_item = None
            self.save_event_ui_data()  # Automatisch speichern

    def do_drag(self, event):
        """Verschiebt das Bild live mit der Maus"""
        if self.dragging_item:
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            self.ovl_canvas.move(self.dragging_item, dx, dy)
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y

    def trigger_overlay_event(self, event_type):
        """Triggert Bild/Sound im Overlay. Findet Config-Eintrag robust & erlaubt Sound-Only."""
        if not hasattr(self, 'overlay_win') or not self.overlay_win:
            return

        # 1. CONFIG-DATEN SUCHEN (ROBUST & CASE-INSENSITIVE)
        events_dict = self.config.get("events", {})
        # Erst exakt suchen ("Hitmarker")
        event_data = events_dict.get(event_type)

        # Falls nicht gefunden, Case-Insensitive suchen ("hitmarker" -> "Hitmarker")
        if not event_data:
            for key, val in events_dict.items():
                if key.lower() == event_type.lower():
                    event_data = val
                    break

        # Wenn immer noch nichts da ist, abbrechen
        if not event_data:
            return

        # 2. KOORDINATEN & DAUER LADEN
        try:
            abs_x = int(event_data.get("x", event_data.get("x_offset", 0)))
            abs_y = int(event_data.get("y", event_data.get("y_offset", 0)))
            dur = int(event_data.get("duration", 3000))
            # NEU: Scale laden (Standard 1.0)
            scale = float(event_data.get("scale", 1.0))
        except (ValueError, TypeError):
            abs_x, abs_y, dur, scale = 0, 0, 3000, 1.0

        # 3. BILD-PFAD ERMITTELN (Auch leere Pfade sind ok)
        img_path = ""
        img_name = event_data.get("img")
        if img_name:
            temp_path = get_asset_path(img_name)
            if os.path.exists(temp_path):
                img_path = temp_path

        # 4. SOUND-PFAD ERMITTELN
        sound_path = ""
        # Prüfen auf Sound-System (Global oder Class-Attribut)
        has_sound = globals().get("HAS_SOUND", False)
        if has_sound:
            snd_name = event_data.get("snd")
            if snd_name:
                temp_snd = get_asset_path(snd_name)
                if os.path.exists(temp_snd):
                    sound_path = temp_snd

        # 5. FLAG SETZEN: Ist es ein Hitmarker?
        is_hitmarker = (event_type.lower() == "hitmarker")

        # 6. SIGNAL SENDEN (Wenn Bild ODER Sound existiert)
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
        # Filter für PyQt6 QFileDialog
        ft = "Images (*.png *.jpg)" if type_ == "png" else "Audio (*.mp3 *.wav *.ogg)"

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

            # Textfeld setzen (Das löst automatisch das textChanged Signal aus Schritt 2 aus!)
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
        """Speichert die UI-Eingaben für das aktuell gewählte Event in die Config"""
        ui = self.ovl_config_win
        etype = ui.lbl_editing.text().replace("EDITING: ", "").strip()

        if etype == "NONE" or not etype:
            return

        if "events" not in self.config: self.config["events"] = {}
        existing_data = self.config["events"].get(etype, {})

        # Koordinaten vom Overlay holen, falls es gerade sichtbar ist (Edit Mode)
        if self.overlay_win and self.overlay_win.event_preview_label.isVisible():
            pos = self.overlay_win.event_preview_label.pos()
            save_x = int(pos.x() / self.overlay_win.ui_scale)
            save_y = int(pos.y() / self.overlay_win.ui_scale)
        else:
            save_x = existing_data.get("x", 100)
            save_y = existing_data.get("y", 100)

        # Neue Daten zusammenstellen (Feldnamen korrigiert)
        self.config["events"][etype].update({
            "img": ui.ent_evt_img.text().strip(),
            "snd": ui.ent_evt_snd.text().strip(),
            "scale": ui.slider_evt_scale.value() / 100.0,
            "duration": int(ui.ent_evt_duration.text() if ui.ent_evt_duration.text().isdigit() else 3000),
            "x": save_x,
            "y": save_y
        })

        self.save_config()
        self.add_log(f"UI: '{etype}' gespeichert ({save_x}/{save_y}).")

    def save_overlay_ui_data(self):
        """Speichert Crosshair Settings"""
        self.overlay_config["crosshair"] = {
            "file": self.ent_cross_path.get(),
            "x": self.scale_cx.get(),
            "y": self.scale_cy.get()
        }
        self.save_overlay_config()
        self.add_log("Crosshair Settings gespeichert.")

    def start_overlay_logic(self):
        """Aktiviert das Statistik-Overlay im PyQt-Fenster"""
        if not self.overlay_win:
            self.add_log("ERROR: Overlay-System nicht initialisiert!")
            return

        # In der Config als aktiv markieren
        if "stats_widget" not in self.config:
            self.config["stats_widget"] = {"active": True}
        self.config["stats_widget"]["active"] = True

        # Status-Anzeige im Hauptmenü (Tkinter UI)
        if hasattr(self, 'ovl_status_label'):
            self.ovl_status_label.config(text="STATUS: AKTIV", fg="#00ff00")

        self.add_log("SYSTEM: Live-Stats Overlay aktiviert.")
        # Erste Aktualisierung triggern
        self.refresh_ingame_overlay()

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

        # Zähler resetten
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
        if not self.overlay_win: return

        master_switch = self.overlay_active.get()
        game_running = getattr(self, 'ps2_running', False)
        test_active = getattr(self, 'is_stats_test', False)
        cfg = self.config.get("stats_widget", {})

        # Prüfen ob Overlay aktiv sein soll
        if master_switch and (game_running or test_active) and cfg.get("active", True):

            # --- 1. DATEN VORBEREITEN ---
            if test_active:
                # HIER FEHLTE 'hsrkills' -> Wir fügen es hinzu (z.B. 10)
                kills, deaths, hs, hsrkills, start_time = 15, 5, 6, 10, time.time() - 3600
            else:
                my_id = self.current_character_id
                if my_id and my_id in self.session_stats:
                    s = self.session_stats[my_id]
                    # Hier ist es bereits korrekt definiert
                    kills, deaths, hs, hsrkills = s.get("k", 0), s.get("d", 0), s.get("hs", 0), s.get("hsrkill", 0)
                    start_time = s.get("start", time.time())
                else:
                    kills, deaths, hs, hsrkills, start_time = 0, 0, 0, 0, time.time()

            kd = kills / max(1, deaths)
            hsr = (hs / hsrkills * 100) if hsrkills > 0 else 0
            dur_min = (time.time() - start_time) / 60
            kpm = kills / max(1, dur_min) if dur_min > 0 else 0.0
            hrs = int(dur_min // 60);
            mns = int(dur_min % 60)

            # --- 3. HTML DESIGN (ALLES IN EI NER ZEILE) ---
            kd_col = "#00ff00" if kd >= 2.0 else ("#ffff00" if kd >= 1.0 else "#ff4444")

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

            # --- 3. BILD PFAD LOGIK (HIER WAR DAS PROBLEM) ---
            raw_name = cfg.get("img", "").strip()
            final_img_path = ""

            if raw_name:
                # A: Wir bauen den Pfad zum assets Ordner
                asset_path = get_asset_path(raw_name)

                # B: Wir prüfen, was existiert
                if os.path.exists(asset_path):
                    final_img_path = asset_path  # Treffer im Assets Ordner!
                elif os.path.exists(raw_name):
                    final_img_path = raw_name  # Treffer als direkter Pfad

                # Debugging Ausgabe in die Konsole (damit wir sehen was passiert)
                # print(f"DEBUG: Suche Bild '{raw_name}' -> Gefunden: '{final_img_path}'")

            # Daten an das Overlay senden (Signal nimmt jetzt den korrekten vollen Pfad)
            self.overlay_win.signals.update_stats.emit(html, final_img_path)

            self.root.after(1000, self.refresh_ingame_overlay)
        else:
            self.stop_overlay_logic()

    def save_stats_config(self):
        """Speichert Einstellungen (Position wird nur noch durch Maus geändert)"""
        raw_path = self.ent_stats_img.get()
        clean_name = get_short_name(raw_path)

        # 1. Stats Config Update
        if "stats_widget" not in self.config: self.config["stats_widget"] = {}

        # WICHTIG: Wir updaten NICHT MEHR 'x' und 'y' von Sliders!
        self.config["stats_widget"].update({
            "active": self.var_stats_active.get(),
            "img": clean_name,
            "tx": self.scale_st_tx.get(),  # Das existiert noch (Text-Intern)
            "ty": self.scale_st_ty.get(),
            "scale": self.scale_st_scale.get()
        })

        # 2. Killfeed Config Update
        if "killfeed" not in self.config: self.config["killfeed"] = {}
        self.config["killfeed"].update({
            # Auch hier kein X/Y Update mehr aus Sliders
            "hs_icon": get_short_name(self.ent_hs_icon.get()),
            "show_revives": self.var_show_revives.get()
        })

        self.save_config()
        self.add_log("SYSTEM: UI Settings saved.")

        # --- UPDATE ERZWINGEN ---
        if self.overlay_win:
            # Killfeed Position updaten (nutzt jetzt gespeicherte Werte aus Config)
            if hasattr(self.overlay_win, 'update_killfeed_pos'):
                self.overlay_win.update_killfeed_pos()

            # Session Stats Visuals updaten
            if self.var_stats_active.get():
                was_testing = getattr(self, 'is_stats_test', False)
                self.is_stats_test = True  # Erzwingt Refresh
                self.refresh_ingame_overlay()
                self.is_stats_test = was_testing
            else:
                self.stop_overlay_logic()

    def save_voice_config(self):
        """Speichert die Voice-Macro Einstellungen"""
        new_conf = {}
        for key, var in self.voice_vars.items():
            new_conf[key] = var.get()

        self.overlay_config["auto_voice"] = new_conf
        self.save_overlay_config()
        self.add_log("Voice Macros saved.")

    def trigger_auto_voice(self, trigger_key):
        """Drückt V + Zahl basierend auf der Config"""
        # 1. Config prüfen
        cfg = self.overlay_config.get("auto_voice", {})
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
        """Startet eine Vorschau (Anti-Ghosting Test mit neuem Layout)"""
        if not self.overlay_win:
            messagebox.showwarning("Warnung", "Overlay System ist nicht aktiv!")
            return

        self.add_log("UI: Starte visuellen Test (Layout-Check)...")
        self.is_stats_test = True
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
            base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

            # NEUES LAYOUT LOGIK
            tag_display = f"[{tag}]"  # Immer Klammern, auch wenn tag leer ist

            icon_html = ""
            if is_hs:
                hs_icon = self.config.get("killfeed", {}).get("hs_icon", "headshot.png")
                hs_path = get_asset_path(hs_icon).replace("\\", "/")
                if os.path.exists(hs_path):
                    # Icon ganz links
                    icon_html = f'<img src="{hs_path}" width="40" height="40" style="vertical-align: middle;">&nbsp;'

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

            if self.overlay_win: self.overlay_win.signals.killfeed_entry.emit(msg)

        # Die Test-Events nacheinander abfeuern
        for i, (t, n, tag, hs, kd) in enumerate(test_scenarios):
            self.root.after(i * 500, lambda t=t, n=n, tag=tag, hs=hs, kd=kd: send_fake_feed(t, n, tag, hs, kd))

        # --- AUTO-CLEAR UND AUFRÄUMEN ---
        def end_test():
            self.is_stats_test = False
            if self.overlay_win:
                self.overlay_win.signals.clear_feed.emit()
            self.add_log("UI: Test beendet & Feed bereinigt.")

        self.root.after(6000, end_test)

    def get_current_tab_targets(self):
        """Ermittelt sicher, welcher Tab gerade offen ist."""
        try:
            ui = self.ovl_config_win
            idx = ui.tabs.currentIndex()
            # .strip() ist entscheidend, da deine Tabs " EVENTS " heißen (mit Leerzeichen)
            tab_text = ui.tabs.tabText(idx).strip().upper()

            targets = []
            if "CROSSHAIR" in tab_text:
                targets = ["crosshair"]
            elif "STATS" in tab_text:
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
        """Startet den Edit-Modus und zeigt das aktive Element mit grünem Rahmen an."""
        if not self.overlay_win:
            self.add_log("ERR: Overlay läuft nicht! Bitte erst Overlay starten.")
            return

        # Prüfen, ob wir schon im Edit-Modus sind
        is_editing = getattr(self, "is_hud_editing", False)
        ui = self.ovl_config_win

        # Alle Edit-Buttons aus allen Tabs sammeln, um sie synchron zu schalten
        btn_list = [ui.btn_edit_hud, ui.btn_edit_cross, ui.btn_edit_streak, ui.btn_edit_hud_stats]

        # --- START EDIT MODE ---
        if not is_editing:
            targets = self.get_current_tab_targets()

            # WICHTIG: Wenn targets leer ist (User ist in falschem Tab), Abbruch
            if not targets:
                self.add_log("INFO: Bitte wählen Sie einen Tab (Events, Streak, etc.) aus.")
                return

            self.is_hud_editing = True

            # 1. Buttons ROT färben & Text ändern
            for btn in btn_list:
                btn.setText("STOP EDIT (SAVE)")
                # Explizites Rot für den aktiven Modus
                btn.setStyleSheet(
                    "background-color: #ff0000; color: white; border: 1px solid #cc0000; font-weight: bold;")

            # 2. Overlay für Maus klickbar machen
            self.overlay_win.set_mouse_passthrough(False, active_targets=targets)

            # 3. EVENT HIGHLIGHTING (Das Bild laden & grün umranden)
            if "event" in targets:
                # Name und Bildpfad aus den Feldern holen
                img_name = ui.ent_evt_img.text().strip()

                # Falls Feld leer, aus Config laden
                evt_name = ui.lbl_editing.text().replace("EDITING: ", "").strip()
                evt_data = self.config.get("events", {}).get(evt_name, {})

                if not img_name:
                    img_name = evt_data.get("img", "kill.png")  # Fallback

                img_path = get_asset_path(img_name)

                # Koordinaten & Scale laden
                pos_x = evt_data.get("x", 100)
                pos_y = evt_data.get("y", 200)
                scale_val = ui.slider_evt_scale.value() / 100.0

                # Bild im Overlay anzeigen (Dauer unendlich = 999999)
                self.overlay_win.display_image(img_path, 9999999, pos_x, pos_y, scale_val)

                # GRÜNER RAHMEN & SICHTBAR MACHEN
                if self.overlay_win.img_label.isVisible():
                    # Wir nutzen das img_label als "Preview Label"
                    self.overlay_win.event_preview_label = self.overlay_win.img_label
                    self.overlay_win.event_preview_label.setStyleSheet(
                        "border: 3px solid #00ff00; background: rgba(0, 255, 0, 0.2);")
                    self.overlay_win.event_preview_label.raise_()
                else:
                    self.add_log(f"WARN: Bild '{img_name}' konnte nicht geladen werden.")

            self.add_log(f"UI: Edit-Modus gestartet für: {targets}")

        # --- STOP EDIT MODE ---
        else:
            self.is_hud_editing = False
            targets = self.get_current_tab_targets()

            # 1. Buttons zurücksetzen (Blau/Standard)
            for btn in btn_list:
                btn.setText("MOVE UI")
                # Stylesheet leeren -> Fällt zurück auf die CSS-ID #EditBtn (Blau)
                btn.setStyleSheet("")

                # 2. Overlay wieder durchlässig machen
            if self.overlay_win:
                self.overlay_win.set_mouse_passthrough(True)

                # Rahmen entfernen und Bild ausblenden
                if hasattr(self.overlay_win, 'event_preview_label'):
                    self.overlay_win.event_preview_label.setStyleSheet("background: transparent;")
                    self.overlay_win.event_preview_label.hide()

                # Zur Sicherheit auch das img_label verstecken
                self.overlay_win.img_label.hide()

            # 3. Speichern je nach aktivem Tab
            if "event" in targets: self.save_event_ui_data()
            if "streak" in targets: self.save_streak_settings_from_qt()
            if "stats" in targets or "feed" in targets: self.save_stats_config_from_qt()
            if "crosshair" in targets: self.save_config()

            self.save_config()
            self.add_log("UI: Positionen gespeichert & Edit-Modus beendet.")


    def on_overlay_tab_change(self, event):
        """Wenn Tab gewechselt wird während Edit an ist -> Edit Bereich anpassen"""
        if getattr(self, "is_hud_editing", False):
            # Wir beenden kurz den Edit Mode und starten ihn neu für den neuen Tab
            self.toggle_hud_edit_mode()  # Aus
            self.root.after(200, self.toggle_hud_edit_mode)  # An (im neuen Tab)

    def update_stats_widget_position(self):
        # Wird vom Loop erledigt, dient nur als Dummy oder Trigger für sofortigen Refresh
        self.refresh_ingame_overlay()

    def pick_streak_color(self):
        """Öffnet den Windows-Farbdialog und aktualisiert das HUD."""
        from tkinter import colorchooser
        color = colorchooser.askcolor(title="Wähle Farbe für die Streak-Zahl", color=self.streak_color_var.get())

        if color[1]:  # Wenn User nicht abgebrochen hat
            self.streak_color_var.set(color[1])
            # Button-Farbe anpassen
            self.btn_streak_color.config(bg=color[1])
            # Textfarbe auf Button lesbar halten (schwarz bei hellen Farben)
            self.btn_streak_color.config(fg="black" if color[1].lower() in ["#ffffff", "#ffff00"] else "white")
            # Speichern & Vorschau triggern
            self.save_streak_settings(preview=True)

    def streak_font_debounce(self, *args):
        """Wartet 500ms nach der letzten Eingabe, bevor der Test gestartet wird."""
        if self._streak_debounce_timer:
            self.root.after_cancel(self._streak_debounce_timer)

        # Starte den Test erst nach 500ms Inaktivität
        self._streak_debounce_timer = self.root.after(500, lambda: self.save_streak_settings(preview=True))

    def save_streak_settings(self, preview=False):
        """Speichert Messer-Bilder, das GLOBALE Design der Zahl und den aufgenommenen Pfad."""
        if "streak" not in self.config:
            self.config["streak"] = {}

        # --- NEU: PFAD AUS DEM OVERLAY SICHERN (WICHTIG: Damit Aufnahmen nicht verloren gehen) ---
        if self.overlay_win and hasattr(self.overlay_win, 'custom_path'):
            # Wir übertragen die Koordinaten aus dem Live-Overlay in die Konfiguration
            self.config["streak"]["custom_path"] = self.overlay_win.custom_path

        # --- 1. WERTE AUS UI-FELDERN LESEN (Mit Fallback) ---
        try:
            # Puls-Geschwindigkeit validieren
            raw_speed = int(self.ent_streak_speed.get()) if hasattr(self, 'ent_streak_speed') else 50
        except:
            raw_speed = 50

        # Design-Werte sicher auslesen (Farbe, Größe, Schatten)
        global_color = self.streak_color_var.get() if hasattr(self, 'streak_color_var') else "#ffffff"
        try:
            global_size = int(self.streak_fontsize_var.get()) if hasattr(self, 'streak_fontsize_var') else 26
        except:
            global_size = 26

        try:
            sh_size = int(self.streak_shadow_size_var.get()) if hasattr(self, 'streak_shadow_size_var') else 2
        except:
            sh_size = 2

        # Style-Checkboxen (Fett & Unterstrichen)
        is_bold = self.var_streak_bold.get() if hasattr(self, 'var_streak_bold') else False
        is_underline = self.var_streak_underline.get() if hasattr(self, 'var_streak_underline') else False

        if hasattr(self, 'temp_streak_backup'):
            self.killstreak_count = self.temp_streak_backup
            self.streak_factions = getattr(self, 'temp_factions_backup', [])
            # Backups nach Wiederherstellung löschen
            del self.temp_streak_backup
            if hasattr(self, 'temp_factions_backup'):
                del self.temp_factions_backup
        else:
            # Falls kein Backup da ist, sicherstellen dass Variablen existieren
            if not hasattr(self, 'killstreak_count'):
                self.killstreak_count = 0

        # --- 2. CONFIG AKTUALISIEREN ---
        # .update() stellt sicher, dass bestehende Werte (wie x/y vom Drag&Drop) erhalten bleiben
        self.config["streak"].update({
            "active": self.var_streak_master.get() if hasattr(self, 'var_streak_master') else True,
            "anim_active": self.var_streak_anim.get() if hasattr(self, 'var_streak_anim') else True,
            "speed": raw_speed,
            "img": get_short_name(self.ent_streak_img.get()) if hasattr(self, 'ent_streak_img') else "KS_Counter.png",
            "color": global_color,
            "size": global_size,
            "shadow_size": sh_size,
            "shadow_active": sh_size > 0,  # Schatten ist nur aktiv, wenn Größe > 0
            "bold": is_bold,
            "underline": is_underline,
            "tx": self.scale_tx.get() if hasattr(self, 'scale_tx') else 0,
            "ty": self.scale_ty.get() if hasattr(self, 'scale_ty') else 0,
            "scale": self.scale_s_size.get() if hasattr(self, 'scale_s_size') else 1.0
        })

        # Messer-Bilder pro Fraktion speichern
        if hasattr(self, 'knife_entries'):
            for f_tag, ent in self.knife_entries.items():
                self.config["streak"][f"knife_{f_tag}"] = get_short_name(ent.get())

        # Daten permanent in config.json schreiben
        self.save_config()
        # Das Live-Overlay über die Änderungen informieren
        self.update_streak_display()

        # Optionalen Test-Lauf starten (bei manuellem Save oder Checkbox-Klick)
        if preview:
            self.test_streak_visuals()

        # Erfolgsmeldung im Log (FIX: nutzt jetzt korrekt 'global_color')
        self.add_log(f"STREAK: Gespeichert (Farbe: {global_color}, Schatten: {sh_size})")

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
        Startet eine Vorschau mit 20 Messern.
        Verhindert Abstürze durch Spamming und schützt echte Statistiken.
        """
        # 1. Vorherige Timer abbrechen, damit die GUI nicht "hängt"
        if self._streak_test_timer:
            self.root.after_cancel(self._streak_test_timer)
            self._streak_test_timer = None

        # 2. Echte Daten nur sichern, wenn wir noch NICHT im Test-Modus sind.
        # Das verhindert, dass die Test-Zahl (20) als "echter" Wert gespeichert wird.
        if self._streak_backup is None:
            self._streak_backup = {
                'count': getattr(self, 'killstreak_count', 0),
                'factions': getattr(self, 'streak_factions', []),
                'slots': getattr(self, 'streak_slot_map', [])
            }

        self.add_log("UI: Teste Killstreak-Visuals (20 Messer)...")

        # 3. Testwerte setzen (Begrenzt auf 20 für Performance)
        self.killstreak_count = 20
        self.streak_factions = (["TR", "NC", "VS"] * 7)[:20]

        import random
        slots = list(range(20))
        random.shuffle(slots)
        self.streak_slot_map = slots

        # 4. Sofortiges Update an das Overlay senden
        self.update_streak_display()

        # 5. Reset-Funktion: Stellt die echten Daten wieder her
        def reset_action():
            if self._streak_backup:
                self.killstreak_count = self._streak_backup['count']
                self.streak_factions = self._streak_backup['factions']
                self.streak_slot_map = self._streak_backup['slots']
                self.update_streak_display()
                self._streak_backup = None  # Backup löschen
            self._streak_test_timer = None
            self.add_log("UI: Test beendet.")

        # 6. Timer für das automatische Ende starten (4 Sekunden)
        self._streak_test_timer = self.root.after(2000, reset_action)

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

    def update_live_graph(self):
        """Berechnet jede Sekunde die aktuellen Stats und triggert das Dashboard-Update."""
        try:
            now = time.time()

            # 1. Fraktions-Zahlen aus den aktiven Spielern berechnen
            counts = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0}
            for _, fac in self.active_players.values():
                if fac in counts:
                    counts[fac] += 1

            total_pop = len(self.active_players)
            self.live_stats.update(counts)
            self.live_stats["Total"] = total_pop

            # 2. Graph-Daten füttern (nur alle X Sekunden für eine schöne Kurve)
            elapsed = now - getattr(self, 'session_start_time', now)
            graph_interval = 1.0 if elapsed < 60 else 30.0

            if now - getattr(self, 'last_graph_point_time', 0) >= graph_interval:
                self.pop_history.pop(0)
                self.pop_history.append(total_pop)
                self.last_graph_point_time = now

            # 3. UI UPDATE (Nur wenn wir im Dashboard-Tab sind)
            # Wir prüfen, ob im Stack das erste Fenster (Index 0 = Dashboard) aktiv ist
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


    def show_nso_teleporter(self):
        self.current_tab = "nso_teleporter"
        self.clear_content()
        mid = self.root.winfo_width() // 2
        CYAN = "#00f2ff"

        nso_frame = tk.LabelFrame(self.root, text=" > NSO_FRACTION_TELEPORTER ", bg="#1e1e1e", fg=CYAN,
                                  font=("Consolas", 10), bd=1, padx=20, pady=20)

        # Fraction Selection (FIX: self.frac_var wird hier nur noch benutzt, nicht neu erstellt)
        tk.Label(nso_frame, text="SELECT FRACTION:", bg="#1e1e1e", fg="#4a6a7a", font=("Consolas", 9)).pack(pady=(0, 5))
        frac_menu = tk.OptionMenu(nso_frame, self.frac_var, "TR", "VS", "NC")
        frac_menu.config(bg="#0a141d", fg=CYAN, font=("Consolas", 10), width=20, bd=0, highlightthickness=0,
                         activebackground="#1a2b3c", activeforeground=CYAN)
        frac_menu["menu"].config(bg="#0a141d", fg=CYAN, font=("Consolas", 10))
        frac_menu.pack(pady=5)

        # Continent Selection
        tk.Label(nso_frame, text="SELECT CONTINENT:", bg="#1e1e1e", fg="#4a6a7a", font=("Consolas", 9)).pack(
            pady=(10, 5))
        cont_menu = tk.OptionMenu(nso_frame, self.cont_var, "Indar", "Hossin", "Amerish", "Esamir", "Oshur")
        cont_menu.config(bg="#0a141d", fg=CYAN, font=("Consolas", 10), width=20, bd=0, highlightthickness=0,
                         activebackground="#1a2b3c", activeforeground=CYAN)
        cont_menu["menu"].config(bg="#0a141d", fg=CYAN, font=("Consolas", 10))
        cont_menu.pack(pady=5)

        # Controls
        btn_container = tk.Frame(nso_frame, bg="#1e1e1e")
        btn_container.pack(pady=20)
        tk.Button(btn_container, text="START", width=12, bg="#004400", fg="white", font=("Consolas", 10, "bold"),
                  command=self.start_nso_teleport).pack(side="left", padx=10)
        tk.Button(btn_container, text="STOP", width=12, bg="#440000", fg="white", font=("Consolas", 10, "bold"),
                  command=self.stop_nso_teleport).pack(side="left", padx=10)

        id1 = self.canvas.create_window(mid, 350, window=nso_frame, width=450)

        # Log area für NSO
        self.log_area = scrolledtext.ScrolledText(self.root, width=85, height=15, bg="#020508", fg="#00f2ff",
                                                  font=("Consolas", 9))
        id2 = self.canvas.create_window(mid, 700, window=self.log_area)

        self.content_ids.extend([id1, id2])

    def show_enforcer(self):
        self.current_tab = "enforcer"
        self.clear_content()
        mid = self.root.winfo_width() // 2

        unit_frame = tk.LabelFrame(self.root, text=" > UNIT_TRACKING ", bg="#1e1e1e", fg="#00f2ff",
                                   font=("Consolas", 10), bd=1, padx=10, pady=10)
        opts = list(self.char_data.keys()) if self.char_data else ["N/A"]
        self.char_menu = tk.OptionMenu(unit_frame, self.char_var, *opts, command=self.update_active_char)
        self.char_option_menus.append(self.char_menu)
        self.char_menu.config(bg="#0a141d", fg="#00f2ff", bd=0, highlightthickness=0)
        self.char_menu["menu"].config(bg="#0a141d", fg="#00f2ff")
        self.char_menu.pack(side="left", padx=5)
        self.new_char_entry = tk.Entry(unit_frame, bg="#0a141d", fg="#00f2ff", width=12)
        self.new_char_entry.pack(side="left", padx=5)
        tk.Button(unit_frame, text="ADD", command=self.add_char, bg="#1a2b3c", fg="#00f2ff").pack(side="left")
        id1 = self.canvas.create_window(mid, 220, window=unit_frame)

        self.cache_label = tk.Label(self.root, text=f"Characters in db: {len(self.name_cache)}", fg="#4a6a7a",
                                    bg="#1e1e1e", font=("Consolas", 14, "bold"))
        id_counter = self.canvas.create_window(mid, 270, window=self.cache_label)

        self.live_killer_label = tk.Label(self.root, text=f"[ TARGET: {self.last_killer_name} ]", fg="#ff4444",
                                          bg="#1e1e1e", font=("Consolas", 16, "bold"))
        id3 = self.canvas.create_window(mid, 320, window=self.live_killer_label)

        rep_frame = tk.LabelFrame(self.root, text=" > INCIDENT_CLASSIFICATION ", bg="#1e1e1e", fg="#ff8c00",
                                  font=("Consolas", 10), bd=1, padx=10, pady=5)
        cb_grid = tk.Frame(rep_frame, bg="#1e1e1e")
        for i, opt in enumerate(CHEAT_OPTIONS):
            var = tk.BooleanVar();
            self.check_vars[opt] = var
            tk.Checkbutton(cb_grid, text=opt, variable=var, bg="#1e1e1e", fg="#7a8a9a", selectcolor="black",
                           font=("Consolas", 8)).grid(row=i // 4, column=i % 4, sticky="w")
        cb_grid.pack()
        self.btn_report = tk.Button(rep_frame, text="GENERATE REPORT", command=self.manual_save_report, bg="#1a1a1a",
                                    fg="#444", font=("Consolas", 11, "bold"), width=40, state="disabled")
        self.btn_report.pack(pady=5)
        id4 = self.canvas.create_window(mid, 450, window=rep_frame)

        self.log_area = scrolledtext.ScrolledText(self.root, width=85, height=15, bg="#020508", fg="#00f2ff",
                                                  font=("Consolas", 9))
        id5 = self.canvas.create_window(mid, 700, window=self.log_area)
        self.content_ids.extend([id1, id3, id4, id5, id_counter])

    def show_settings(self):
        self.clear_content()
        self.current_tab = "settings"

        # Aktuelle Daten in das Qt Fenster laden
        self.settings_win.load_config(self.config, self.ps2_dir)

        self.settings_win.show()
        self.settings_win.raise_()

    def save_enforcer_config_qt(self, data):
        # Wir aktualisieren das interne config dictionary
        self.config.update(data)
        # Dann rufen wir deine originale Speicherfunktion auf
        self.save_enforcer_config()
        self.add_log("SYS: Configuration locked and saved.")

    def refresh_tab_content_base(self, tab_name):
        self.current_tab = tab_name
        # Alle registrierten IDs vom Canvas löschen
        for oid in self.content_ids:
            self.canvas.delete(oid)
        # Liste leeren für den nächsten Tab
        self.content_ids = []

        if hasattr(self, 'sub_menu_frame'):
            self.sub_menu_frame.place_forget()

    def switch_sub_tab(self, name):
        # Wir speichern es immer gleich ab, um Fehler zu vermeiden
        if name.lower() == "weapon stats":
            self.current_sub_tab = "Weapon Stats"
        else:
            self.current_sub_tab = name

        self.show_characters()

    def show_characters(self):
        self.clear_content()
        self.current_tab = "characters"
        if hasattr(self, 'char_win'):
            self.char_win.show()
            self.char_win.raise_()

    def load_enforcer_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        return {}

    def save_enforcer_config(self):
        # Wir aktualisieren nur die spezifischen Werte, anstatt alles zu löschen
        self.config["watch_folder"] = self.folder_entry.get() if hasattr(self, 'folder_entry') else self.config.get(
            "watch_folder", "")
        self.config["email"] = self.email_entry.get() if hasattr(self, 'email_entry') else self.config.get("email", "")
        self.config["pw"] = self.pw_entry.get() if hasattr(self, 'pw_entry') else self.config.get("pw", "")
        self.config["ps2_path"] = self.ps2_dir

        # Jetzt die saubere Speicherfunktion nutzen
        self.save_config()
        self.add_log("SYS: Configuration updated (Background & Overlay preserved).")
        self.restart_observer()

        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f)
        self.add_log("SYS: Configuration updated.")
        self.restart_observer()

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.folder_entry.delete(0, tk.END); self.folder_entry.insert(0, path)

    def browse_ps2_folder(self):
        path = filedialog.askdirectory(title="PlanetSide 2 Installationsordner wählen")
        if path:
            self.ps2_dir = path
            if hasattr(self, 'ps2_path_label'):
                self.ps2_path_label.config(text=path)
            self.add_log(f"SYS: PS2 Path set to {path}")
            self.save_enforcer_config()

    def load_chars(self):
        chars = {}
        return chars

    def refresh_char_menus(self):
        """Aktualisiert ALLE Dropdown-Menüs (Enforcer UND Overlay) gleichzeitig"""
        # Liste der Namen holen
        options = list(self.char_data.keys()) if self.char_data else ["N/A"]

        # Durch alle registrierten Menüs gehen
        # Wir filtern vorher zerstörte Widgets heraus (falls man Tabs gewechselt hat)
        self.char_option_menus = [m for m in self.char_option_menus if m.winfo_exists()]

        for menu_widget in self.char_option_menus:
            menu = menu_widget["menu"]
            menu.delete(0, "end")

            for name in options:
                # Lambda Fix: x=name bindet den aktuellen Wert
                menu.add_command(label=name, command=lambda x=name: self.update_active_char(x))

    def add_char(self):
        """Fügt einen Charakter hinzu (funktioniert aus beiden Tabs)"""
        name = ""

        # 1. Prüfen, ob im ENFORCER Tab etwas steht
        if hasattr(self, 'new_char_entry') and self.new_char_entry.winfo_exists():
            val = self.new_char_entry.get().strip()
            if val: name = val

        # 2. Falls nicht, prüfen ob im OVERLAY Tab (Identity) etwas steht
        # (Nur wenn wir noch keinen Namen gefunden haben)
        if not name and hasattr(self, 'ovl_char_entry') and self.ovl_char_entry.winfo_exists():
            val = self.ovl_char_entry.get().strip()
            if val: name = val

        if name:
            try:
                # API Abfrage
                url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/?name.first_lower={name.lower()}"
                r = requests.get(url, timeout=10).json()

                if r['returned'] > 0:
                    c_list = r['character_list'][0]
                    cid = c_list['character_id']
                    real_name = c_list['name']['first']
                    world_id = c_list.get('world_id', '0')  # World ID mitnehmen

                    # In Cache speichern, damit Auto-Switch sofort funktioniert
                    conn = sqlite3.connect("ps2_master.db")
                    conn.execute("INSERT OR REPLACE INTO player_cache (character_id, name, world_id) VALUES (?, ?, ?)",
                                 (cid, real_name, world_id))
                    conn.execute("INSERT OR REPLACE INTO my_chars (name, character_id) VALUES (?, ?)", (real_name, cid))
                    conn.commit()
                    conn.close()

                    self.char_data[real_name] = cid
                    self.add_log(f"SYS: {real_name} added to tracking.")

                    # Sofort auswählen
                    self.update_active_char(real_name)

                    # Alle Menüs updaten
                    self.refresh_char_menus()

                    # Textfelder leeren (beide, sicherheitshalber)
                    if hasattr(self, 'new_char_entry') and self.new_char_entry.winfo_exists():
                        self.new_char_entry.delete(0, tk.END)
                    if hasattr(self, 'ovl_char_entry') and self.ovl_char_entry.winfo_exists():
                        self.ovl_char_entry.delete(0, tk.END)
                else:
                    self.add_log(f"ERR: Character '{name}' not found via API.")
            except Exception as e:
                self.add_log(f"ERR: Add failed: {e}")
        else:
            self.add_log("INFO: Bitte einen Namen eingeben.")

    def delete_char(self):
        """Löscht den aktuell ausgewählten Charakter"""
        name = self.char_var.get()
        if name in self.char_data:
            try:
                # Aus DB löschen
                conn = sqlite3.connect("ps2_master.db")
                conn.execute("DELETE FROM my_chars WHERE name=?", (name,))
                conn.commit()
                conn.close()

                # Aus internem Speicher löschen
                del self.char_data[name]
                self.add_log(f"SYS: {name} deleted.")

                # Variable zurücksetzen
                self.char_var.set("Select Character...")
                self.current_character_id = ""

                # Alle Menüs updaten
                self.refresh_char_menus()

            except Exception as e:
                self.add_log(f"ERR: Delete failed: {e}")

    def update_active_char(self, name):
        # UI-Check
        if hasattr(self, 'char_var'):
            self.char_var.set(name)

        cid = self.char_data.get(name, "")
        self.current_character_id = cid
        self.add_log(f"SYS: Tracking {name}")  # Nutzt jetzt das neue sichere add_log

        try:
            conn = sqlite3.connect("ps2_master.db")
            res = conn.execute("SELECT world_id FROM player_cache WHERE character_id=?", (cid,)).fetchone()
            conn.close()

            if res and res[0]:
                new_world_id = str(res[0])
                if new_world_id != str(self.current_world_id):
                    s_name = self.get_server_name_by_id(new_world_id)
                    # Sicherer Aufruf des Serverwechsels
                    QTimer.singleShot(0, lambda n=s_name, i=new_world_id: self.switch_server(n, i))
        except Exception as e:
            self.add_log(f"Auto-Switch Error: {e}")


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
                                    except Exception as e:
                                        print(f"DEBUG: Cache Label Update skipped: {e}")
                        except ValueError:
                            self.add_log("SYS: Census API sent invalid JSON (Server busy?)")
                    else:
                        self.add_log(f"SYS: Census API Error {response.status_code}")

                except Exception as e:
                    self.add_log(f"DB-ERROR (Cache): {e}")

    def on_closing(self):
        if self.observer:
            self.observer.stop()
        self.root.destroy()

    def start_websocket_thread(self):
        """Startet den Census-Listener in einem eigenen Hintergrund-Thread"""

        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.census_listener())

        # Startet den Thread genau EINMAL
        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    async def census_listener(self):
        self.loop = asyncio.get_running_loop()
        sid = S_ID
        uri = f"wss://push.planetside2.com/streaming?environment=ps2&service-id={sid}"
        print("debugtest")
        # Initialisiere den Duplikat-Filter
        self.event_cache = set()
        self.event_history = []

        while True:
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20, close_timeout=10) as websocket:
                    self.websocket = websocket

                    # GLOBAL SUBSCRIPTION
                    msg = {
                        "service": "event",
                        "action": "subscribe",
                        "characters": ["all"],
                        "worlds": ["all"],
                        "eventNames": ["Death", "GainExperience", "PlayerLogin", "PlayerLogout", "MetagameEvent"]
                    }
                    await websocket.send(json.dumps(msg))
                    self.add_log("Websocket: GLOBAL MONITORING ACTIVE (All Servers)")

                    # --- OPTIMIERUNG: HIER DEFINIERT (Einmal pro Verbindung) ---
                    def get_stat_obj(cid, tid):
                        if cid not in self.session_stats:
                            faction_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                            self.session_stats[cid] = {
                                "id": cid,
                                "name": self.name_cache.get(cid, "Searching..."),
                                "faction": faction_name,
                                "k": 0, "d": 0, "a": 0, "hs": 0, "hsrkill": 0,
                                "start": time.time(),
                                "last_kill_time": time.time()
                            }
                        return self.session_stats[cid]

                    async for message in websocket:
                        if getattr(self, "needs_reconnect", False):
                            self.needs_reconnect = False
                            await websocket.close()
                            break

                        data = json.loads(message)
                        if "payload" in data:
                            p = data["payload"]
                            e_name = p.get("event_name")
                            payload_world = str(p.get("world_id", "0"))
                            ts = p.get("timestamp")
                            char_id = p.get("character_id", "0")
                            attacker_id = p.get("attacker_character_id", "0")
                            exp_id = p.get("experience_id", "0")

                            # ROBUSTER DUPLIKAT-FILTER
                            uid = f"{e_name}_{ts}_{char_id}_{attacker_id}_{exp_id}_{payload_world}"
                            if uid in self.event_cache:
                                continue

                            self.event_cache.add(uid)
                            self.event_history.append(uid)
                            if len(self.event_history) > 500:
                                old_uid = self.event_history.pop(0)
                                self.event_cache.discard(old_uid)

                            # =========================================================
                            # 1. PLAYER LOGIN / LOGOUT (Globaler Check)
                            # =========================================================
                            if e_name == "PlayerLogin":
                                c_id = p.get("character_id")

                                def sync_faction_and_play(char_id, char_name):
                                    try:
                                        # 1. Aktuelle Faction von Census abfragen
                                        url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/?character_id={char_id}&c:show=faction_id"
                                        r = requests.get(url, timeout=5).json()

                                        f_id = "0"
                                        if r.get('returned', 0) > 0:
                                            character_list = r.get('character_list')
                                            if character_list and len(character_list) > 0:
                                                f_id = character_list[0].get('faction_id', "0")
                                            else:
                                                f_id = "0"  # Fallback

                                            # 2. Datenbank mit der richtigen Faction aktualisieren
                                            conn = sqlite3.connect("ps2_master.db")
                                            conn.execute("UPDATE player_cache SET faction_id=? WHERE character_id=?",
                                                         (f_id, char_id))
                                            conn.commit()
                                            conn.close()

                                        f_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(f_id), "NSO")

                                        # 3. QT-ÄNDERUNG: Direktaufruf (trigger_overlay_event sollte thread-sicher sein)
                                        self.trigger_overlay_event(f"Login {f_tag}")
                                        self.add_log(f"AUTO-TRACK: {char_name} eingeloggt ({f_tag}).")

                                    except Exception as e:
                                        print(f"Login-Sync Error: {e}")

                                for name, saved_id in self.char_data.items():
                                    if saved_id == c_id:
                                        self.current_character_id = c_id

                                        # QT-ÄNDERUNG: Einfache Zuweisung statt .set()
                                        self.current_selected_char_name = name

                                        # NEU: Wir müssen das Label im Dashboard/Overlay-Fenster aktualisieren
                                        # Falls du ein Dropdown hast:
                                        if hasattr(self, 'ovl_config_win'):
                                            # Wir nutzen das Signal-System, falls wir aus einem Thread kommen,
                                            # oder wir rufen eine Methode auf, die das UI sicher updatet.
                                            self.ovl_config_win.char_combo.setCurrentText(name)

                                        threading.Thread(target=sync_faction_and_play, args=(c_id, name),
                                                         daemon=True).start()

                                        if payload_world != "0" and payload_world != str(self.current_world_id):
                                            s_name = self.get_server_name_by_id(payload_world)
                                            self.add_log(f"AUTO-SWITCH: Wechsel zu {s_name}...")
                                            # QT-ÄNDERUNG: Direkter Aufruf statt after()
                                            self.switch_server(s_name, payload_world)
                                        break



                            elif e_name == "PlayerLogout":
                                logout_id = p.get("character_id")
                                if logout_id == self.current_character_id:
                                    self.current_character_id = ""
                                    self.current_selected_char_name = "WAITING FOR LOGIN..."
                                    # UI Update für das Dropdown
                                    if hasattr(self, 'ovl_config_win'):
                                        self.ovl_config_win.char_combo.setPlaceholderText("WAITING FOR LOGIN...")
                                    self.add_log("AUTO-TRACK: Eigener Charakter ausgeloggt.")
                                # 2. JEDEN Spieler sofort aus der Live-Anzeige entfernen
                                if logout_id in self.active_players:
                                    del self.active_players[logout_id]
                                if logout_id in self.session_stats:
                                    # Wir löschen die Stats nicht (Session!), aber markieren sie als inaktiv
                                    self.session_stats[logout_id]["last_kill_time"] = 0

                            # =========================================================
                            # 2. DER SERVER-FILTER
                            # =========================================================
                            if payload_world != "0" and payload_world != str(self.current_world_id):
                                continue

                            # -------------------------------------------------
                            # ALLGEMEINES TRACKING (Population Dashboard)
                            # -------------------------------------------------
                            track_id = p.get("character_id") or p.get("attacker_character_id")
                            if track_id and track_id != "0":
                                tid = p.get("team_id") or p.get("attacker_team_id")
                                f_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")

                                # Speichern in der Logik-Variable (DiorClientGUI)
                                self.active_players[track_id] = (time.time(), f_name)

                                # Namens-Abfrage in die Queue werfen (falls unbekannt)
                                if track_id not in self.name_cache:
                                    self.id_queue.put(track_id)

                                # --- NEU FÜR QT: DASHBOARD UPDATE TRIGGER ---
                                # Wir rufen hier keine GUI-Befehle direkt auf, aber wir stellen sicher,
                                # dass das Dashboard-Fenster Zugriff auf die frischen Stats hat.
                                # Da das Dashboard meist über einen QTimer aktualisiert wird,
                                # müssen wir hier meistens gar nichts aktiv "pushen".

                                # =========================================================
                                # EVENT: DEATH (PyQt6 Optimized)
                                # =========================================================
                            if e_name == "Death":
                                killer_id = p.get("attacker_character_id")
                                victim_id = p.get("character_id")
                                my_id = self.current_character_id
                                is_hs = (p.get("is_headshot") == "1")
                                weapon_id = p.get("attacker_weapon_id")
                                w_info = self.item_db.get(weapon_id, {})
                                category = w_info.get("type", "Unknown")

                                # --- GLOBALE STATISTIKEN ---
                                if p.get("attacker_team_id") != p.get("team_id"):
                                    if killer_id and killer_id != "0" and killer_id != victim_id:
                                        k_obj = get_stat_obj(killer_id, p.get("attacker_team_id"))
                                        k_obj["k"] += 1
                                        k_obj["last_kill_time"] = time.time()
                                        if category in HSR_WEAPON_CATEGORY:
                                            k_obj["hsrkill"] += 1
                                            if is_hs: k_obj["hs"] += 1
                                    if victim_id and victim_id != "0":
                                        v_obj = get_stat_obj(victim_id, p.get("team_id"))
                                        v_obj["d"] += 1

                                if my_id:
                                    # Icon Vorbereitung (HS Icon)
                                    icon_html = ""
                                    if is_hs:
                                        # Pfad-Handling bleibt gleich, aber wir nutzen BASE_DIR
                                        hs_icon = self.config.get("killfeed", {}).get("hs_icon", "headshot.png")
                                        hs_path = get_asset_path(hs_icon).replace("\\", "/")
                                        if os.path.exists(hs_path):
                                            icon_html = f'<img src="{hs_path}" width="40" height="40" style="vertical-align: middle;">&nbsp;'

                                    # --- FALL A: ICH BIN DER KILLER ---
                                    if killer_id == my_id and victim_id != my_id:

                                        # [LOGIK] Check: Ist Killstreak aktiviert?
                                        if not self.config.get("streak", {}).get("active", True):
                                            continue

                                        curr_time = time.time()
                                        # Dubletten-Schutz
                                        if getattr(self, "last_victim_id", None) == victim_id and (
                                                curr_time - getattr(self, "last_victim_time", 0)) < 0.5:
                                            continue
                                        self.last_victim_id = victim_id
                                        self.last_victim_time = curr_time

                                        if p.get("attacker_team_id") == p.get("team_id"):
                                            self.trigger_auto_voice("tk")
                                            self.trigger_overlay_event("Team Kill")  # Kein .after() mehr
                                        else:
                                            # Killstreak Logik (Messer-System)
                                            if self.killstreak_count == 0:
                                                self.killstreak_count = 1
                                                self.streak_factions = []
                                                self.streak_slot_map = []
                                            else:
                                                self.killstreak_count += 1

                                            v_team = p.get("team_id")
                                            v_faction = {"1": "VS", "2": "NC", "3": "TR"}.get(str(v_team),
                                                                                              "NSO")
                                            self.streak_factions.append(v_faction)

                                            # Slot-Vergabe
                                            new_slot = self._get_random_slot()
                                            self.streak_slot_map.append(new_slot)

                                            self.is_dead = False
                                            self.was_revived = False

                                            # Messer-Anzeige im Qt-Overlay aktualisieren
                                            self.update_streak_display()

                                            # Multi-Kill Zeitfenster
                                            if curr_time - getattr(self, "last_kill_time",
                                                                   0) <= self.streak_timeout:
                                                self.kill_counter += 1
                                            else:
                                                self.kill_counter = 1
                                            self.last_kill_time = curr_time

                                            # --- Spezial-Event Erkennung ---
                                            weapon_name = w_info.get("name", "Unknown")
                                            special_event = None

                                            if weapon_id in PS2_DETECTION["SPECIAL_IDS"]:
                                                special_event = PS2_DETECTION["SPECIAL_IDS"][weapon_id]
                                            elif category in PS2_DETECTION["CATEGORIES"]:
                                                special_event = PS2_DETECTION["CATEGORIES"][category]
                                            elif weapon_name in PS2_DETECTION["NAMES"]:
                                                special_event = PS2_DETECTION["NAMES"][weapon_name]

                                            if is_hs and not special_event:
                                                special_event = "Headshot"

                                            # Streak-Meilensteine (Squad Wipe etc.)
                                            streak_map = {12: "Squad Wiper", 24: "Double Squad Wipe",
                                                          36: "Squad Lead's Nightmare", 48: "One Man Platoon"}
                                            if self.killstreak_count in streak_map:
                                                special_event = streak_map[self.killstreak_count]
                                            elif self.kill_counter > 1:
                                                multi_map = {2: "Double Kill", 3: "Multi Kill", 4: "Mega Kill",
                                                             5: "Ultra Kill", 6: "Monster Kill",
                                                             7: "Ludicrous Kill",
                                                             9: "Holy Shit"}
                                                if self.kill_counter in multi_map:
                                                    special_event = multi_map[self.kill_counter]

                                            # Overlay triggern (Bilder/Sounds)
                                            if special_event:
                                                self.trigger_overlay_event(special_event)

                                            # Hitmarker immer kurz verzögert (direkt aufrufen ist in Qt ok)
                                            self.trigger_overlay_event("Hitmarker")

                                            # --- Auto Voice Logic (V-Macros) ---
                                            kd_triggered = False
                                            v_loadout = p.get("character_loadout_id")
                                            if victim_id in self.session_stats:
                                                v_stat = self.session_stats[victim_id]
                                                if (v_stat.get("k", 0) / max(1, v_stat.get("d", 1))) >= 2.0:
                                                    self.trigger_auto_voice("kill_high_kd")
                                                    kd_triggered = True

                                            if not kd_triggered:
                                                if v_loadout in LOADOUT_MAP["max"]:
                                                    self.trigger_auto_voice("kill_max")
                                                elif v_loadout in LOADOUT_MAP["infil"]:
                                                    self.trigger_auto_voice("kill_infil")
                                                elif is_hs:
                                                    self.trigger_auto_voice("kill_hs")

                                            # --- Killfeed Eintrag senden ---
                                            v_name = self.name_cache.get(victim_id, "Unknown")
                                            v_tag = getattr(self, "outfit_cache", {}).get(victim_id, "")
                                            s_vic = self.session_stats.get(victim_id, {})
                                            v_kd = f"{(s_vic.get('k', 0) / max(1, s_vic.get('d', 1))):.1f}"

                                            # HTML String für das Qt-Overlay Killfeed
                                            msg = f'<div style="font-family: \'Black Ops One\'; font-size: 19px; color: white; text-align: right;">{icon_html}<span style="color: #888;">[{"".join(v_tag)}] </span>{v_name} <span style="color: #aaa; font-size: 19px;">({v_kd})</span></div>'

                                            if self.overlay_win:
                                                self.overlay_win.signals.killfeed_entry.emit(msg)

                                    # --- FALL B: ICH BIN DAS OPFER ---
                                    elif victim_id == my_id:
                                        # 1. STREAK SICHERN (Wichtig für Revive-Logik)
                                        if self.killstreak_count > 0:
                                            self.saved_streak = self.killstreak_count
                                            self.saved_factions = getattr(self, 'streak_factions', [])
                                            self.saved_slots = getattr(self, 'streak_slot_map', [])

                                        # 2. STATUS RESET
                                        self.killstreak_count = 0
                                        self.streak_factions = []
                                        self.streak_slot_map = []
                                        self.is_dead = True

                                        # Direktes UI-Update statt root.after
                                        self.update_streak_display()

                                        # 3. KILLER-INFOS FÜR DEN FEED
                                        if killer_id and killer_id != "0":
                                            k_name = self.name_cache.get(killer_id, "Unknown")
                                            k_tag = getattr(self, "outfit_cache", {}).get(killer_id, "")
                                            k_vic = self.session_stats.get(killer_id, {})
                                            k_kd = f"{(k_vic.get('k', 0) / max(1, k_vic.get('d', 1))):.1f}"

                                            # HTML-Formatierung für den roten "Death-Eintrag" im Killfeed
                                            msg = f"""<div style="font-family: 'Black Ops One', sans-serif; font-size: 19px; 
                                                                                         text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;">
                                                                                         {icon_html}
                                                                                         <span style="color: #888;">[{"".join(k_tag)}]</span>
                                                                                         <span style="color: #ff4444;">{k_name}</span>
                                                                                         <span style="color: #aaa; font-size: 19px;"> ({k_kd})</span></div>"""

                                            # Signal an das Qt-Overlay senden
                                            if self.overlay_win:
                                                self.overlay_win.signals.killfeed_entry.emit(msg)

                                        # 4. DEATH-EVENT TRIGGERN (Sound & Bild "You Died")
                                        self.trigger_overlay_event("Death")

                            # =========================================================
                            # EVENT: EXPERIENCE (Revive, Assists)
                            # =========================================================
                            elif e_name == "GainExperience":
                                exp_id = str(p.get("experience_id", "0"))
                                other_id = p.get("other_id")
                                char_id = p.get("character_id")
                                my_id = self.current_character_id

                                # 1. Globale Statistik-Updates (Assists)
                                if exp_id in ["2", "3", "371", "372"]:
                                    a_obj = get_stat_obj(char_id, p.get("team_id"))
                                    a_obj["a"] += 1

                                # 2. Globale Statistik-Updates (Revives korrigieren Deaths)
                                if exp_id in ["7", "53"]:
                                    r_obj = get_stat_obj(other_id, p.get("team_id"))
                                    if r_obj["d"] > 0:
                                        r_obj["d"] -= 1

                                # 3. LOGIK: ICH WURDE WIEDERBELEBT
                                if my_id and other_id == my_id:
                                    if exp_id in ["7", "53"]:
                                        self.was_revived = True
                                        self.is_dead = False

                                        # Killstreak aus dem "Sicherungs-Speicher" wiederherstellen
                                        self.killstreak_count = getattr(self, 'saved_streak', 0)
                                        self.streak_factions = getattr(self, 'saved_factions', [])
                                        self.streak_slot_map = getattr(self, 'saved_slots', [])

                                        # UI-Updates (Direktaufruf statt .after)
                                        self.update_streak_display()
                                        self.trigger_overlay_event("Revive Taken")
                                        self.trigger_auto_voice("revived")

                                        # Killfeed-Eintrag für Revive
                                        if self.config.get("killfeed", {}).get("show_revives", True):
                                            m_name = self.name_cache.get(char_id, "Medic")
                                            msg = f'<div style="font-family: \'Black Ops One\'; font-size: 19px; color: white; text-align: right;"><span style="color: #00ff00;">✚ REVIVED BY </span>{m_name}</div>'
                                            if self.overlay_win:
                                                self.overlay_win.signals.killfeed_entry.emit(msg)

                                # 4. LOGIK: ICH GEBE SUPPORT ODER ERHALTE EXP
                                if my_id and char_id == my_id:
                                    try:
                                        # Standort-Daten für Alerts/Metagame synchronisieren
                                        self.myTeamId = int(p.get("team_id", 0))
                                        self.myWorldID = int(p.get("world_id", 0))
                                        self.currentZone = int(p.get("zone_id", 0))
                                    except:
                                        pass

                                    if exp_id in ["7", "53"]:
                                        self.trigger_overlay_event("Revive Given")
                                    else:
                                        # Spezial-Erkennung (z.B. Resupply, Repair, Point Control)
                                        # PS2_EXP_DETECTION muss in Dior Client.py definiert sein
                                        for event_name, id_list in PS2_EXP_DETECTION.items():
                                            if exp_id in id_list:
                                                self.trigger_overlay_event(event_name)
                                                break

                            # =========================================================
                            # EVENT: METAGAME (Alerts)
                            # =========================================================
                            elif e_name == "MetagameEvent":
                                state = p.get("metagame_event_state_name")

                                # Typenumwandlung sicherstellen
                                try:
                                    world = int(p.get("world_id", 0))
                                    zone = int(p.get("zone_id", 0))
                                    # Scores kommen oft als String ("33.5")
                                    VS = float(p.get("faction_vs", 0))
                                    TR = float(p.get("faction_tr", 0))
                                    NC = float(p.get("faction_nc", 0))
                                except (ValueError, TypeError):
                                    continue

                                    # Debugging (Konsole)
                                print(
                                    f"DEBUG ALERT: State={state}, World={world}/{self.myWorldID}, Zone={zone}/{self.currentZone}")

                                # Prüfen, ob der Alert auf deinem Server & deiner Zone geendet ist
                                if state == "ended" and world == getattr(self, 'myWorldID', 0) and zone == getattr(self,
                                                                                                                   'currentZone',
                                                                                                                   0):
                                    print("ALERT ENDED - CHECKING WINNER...")

                                    # Gewinner-Logik basierend auf deiner Team-ID (1=VS, 2=NC, 3=TR)
                                    won = False
                                    if VS > TR and VS > NC and self.myTeamId == 1:
                                        won = True
                                    elif NC > TR and NC > VS and self.myTeamId == 2:
                                        won = True
                                    elif TR > VS and TR > NC and self.myTeamId == 3:
                                        won = True

                                    if won:
                                        # QT-ÄNDERUNG: Direktaufruf (Bilder & Victory-Sound)
                                        self.trigger_overlay_event("Alert Win")
                                        self.add_log(f"EVENT: Alert Win for Faction {self.myTeamId}")
                                    else:
                                        # Entweder verloren oder Unentschieden
                                        self.trigger_overlay_event("Alert End")
                                        self.add_log("EVENT: Alert Ended (No Win recorded)")

            except Exception as e:
                self.add_log(f"Websocket Error: {e}")
                await asyncio.sleep(5)

    def get_top_5(self, faction):
        # Alle Spieler dieser Fraktion filtern
        f_players = [p for p in self.session_stats.values() if p["faction"] == faction]

        # Sortieren nach Kills (primär)
        f_players.sort(key=lambda x: x["k"], reverse=True)

        return f_players[:5]

    def manual_save_report(self):
        if not os.path.exists("Reports"): os.makedirs("Reports")
        fn = f"Reports/Report_{self.last_killer_name}_{int(time.time())}.txt"
        selected = [o for o, v in self.check_vars.items() if v.get()]
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"SUSPECT: {self.last_killer_name}\nEVIDENCE: {self.last_evidence_url}\nVIOLATIONS:\n")
            for c in selected: f.write(f"* {c}: {CHEAT_DESCRIPTIONS.get(c)}\n")
        os.startfile(fn);
        self.add_log("SYS: Report generated.")

    def add_log(self, text):

        print(f"LOG: {text}")  # Backup in der Konsole
        # Bestehender Tkinter Log
        if hasattr(self, 'log_area') and self.log_area:
            self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {text}\n")
            self.log_area.see(tk.END)

        # NEU: Auch an das Qt-Fenster senden
        if hasattr(self, 'char_win'):
            self.char_win.add_log(text)

    def _safe_log_insert(self, msg):
        """Interne Hilfsfunktion für sicheres Schreiben"""
        if hasattr(self, 'log_area') and self.log_area.winfo_exists():
            self.log_area.insert(tk.END, f"> {time.strftime('%H:%M:%S')} | {msg}\n")
            self.log_area.see(tk.END)

    def restart_observer(self):
        path = self.config.get("watch_folder")
        if path and os.path.exists(path):
            if self.observer: self.observer.stop()
            self.observer = Observer();
            self.observer.schedule(EnforcerHandler(self), path, recursive=False);
            self.observer.start()

    def load_ps2_path(self):
        s = r"C:\Program Files (x86)\Steam\steamapps\common\PlanetSide 2"
        return s if os.path.exists(s) else ""

    def on_resize(self, event):
        if not hasattr(self, 'last_size'):
            return

        w, h = self.root.winfo_width(), self.root.winfo_height()
        if abs(w - self.last_size[0]) > 20 or abs(h - self.last_size[1]) > 20:
            self.last_size = (w, h)
            mid = w // 2
            self.canvas.coords(self.title_id, mid, 50)
            self.canvas.coords(self.nav_id, mid, 110)
            self.update_background_view(w, h)
            self.refresh_tab_content()

    def on_closing(self):
        # FIX: Sicherer Shutdown durch Prüfung, ob observer existiert
        try:
            if hasattr(self, 'observer') and self.observer:
                self.observer.stop()
                self.observer.join()
        except:
            pass
        self.root.destroy()

    def refresh_tab_content(self):
        if hasattr(self, 'sub_menu_frame'): self.sub_menu_frame.place_forget()

        if self.current_tab == "Dashboard":  # Groß/Kleinschreibung beachten!
            self.show_dashboard()
        elif self.current_tab == "launcher":
            self.show_launcher()
        elif self.current_tab == "enforcer":
            self.show_enforcer()
        # elif self.current_tab == "nso_teleporter":
        #    self.show_nso_teleporter()
        elif self.current_tab == "characters":
            self.show_characters()
        else:
            self.show_settings()

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

                    # --- KORREKTUR: PyQt6 Weg statt self.root.after ---
                    # Wir nutzen QTimer.singleShot für die Verzögerung
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(2000, self.launcher_win.hide)

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


class EnforcerHandler(FileSystemEventHandler):
    def __init__(self, gui):
        self.gui = gui

    def on_created(self, event):
        if event.src_path.lower().endswith(".mp4"):
            threading.Thread(target=self.safe_process, args=(event.src_path,), daemon=True).start()

    def safe_process(self, path):
        time.sleep(5)
        # Dateinamen bereinigen
        killer_name = getattr(self.gui, 'last_killer_name', "Unknown")
        new_path = os.path.join(os.path.dirname(path), f"REPORT_{killer_name}.mp4")

        try:
            os.rename(path, new_path)
            self.gui.add_log("UPLINK: Transmitting to Streamable...")

            # Prüfen ob Credentials da sind
            email = self.gui.config.get('email', '')
            pw = self.gui.config.get('pw', '')

            if email and pw:
                with open(new_path, 'rb') as f:
                    r = requests.post('https://api.streamable.com/upload',
                                      auth=(email, pw), files={'file': f})
                    if r.status_code == 200:
                        shortcode = r.json()['shortcode']
                        self.gui.last_evidence_url = f"https://streamable.com/{shortcode}"
                        self.gui.add_log(f"LINK: {self.gui.last_evidence_url}")

                        # --- HIER WAR DER TKINTER CODE ---
                        # Da wir noch kein Qt-Fenster für den Enforcer haben,
                        # loggen wir den Erfolg nur.
                        self.gui.add_log("SUCCESS: Evidence uploaded.")
            else:
                self.gui.add_log("ERR: Keine Streamable-Daten in Config.")

        except Exception as e:
            self.gui.add_log(f"ERR: {e}")


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