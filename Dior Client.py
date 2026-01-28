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
# ... deine anderen Imports (os, sys, tkinter etc.) ...
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer

# Ermittelt den Ordner, in dem die EXE oder das Skript liegt
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_asset_path(filename):
    if not filename: return ""
    return os.path.join(BASE_DIR, "assets", filename)


# WICHTIG: Signal-Klasse MUSS außerhalb der GUI stehen
# WICHTIG: Signal-Klasse MUSS außerhalb der GUI stehen
class OverlaySignals(QObject):
    show_image = pyqtSignal(str, int, int, int)
    killfeed_entry = pyqtSignal(str)
    update_stats = pyqtSignal(str, str)
    update_streak = pyqtSignal(str, int, dict)
    clear_feed = pyqtSignal()


# --- STABILES QTOVERLAY (SINGLE LABEL METHODE) ---
class QtOverlay(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.gui_ref = None

        self.edit_mode = False
        self.dragging_widget = None
        self.drag_offset = None

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

        # 3. WIDGETS
        self.crosshair_label = QLabel(self)
        self.crosshair_label.hide()
        self.stats_bg_label = QLabel(self)
        self.stats_bg_label.hide()
        self.stats_text_label = QLabel(self)
        self.stats_text_label.hide()

        shadow_stats = QGraphicsDropShadowEffect()
        shadow_stats.setBlurRadius(5 * self.ui_scale)
        shadow_stats.setXOffset(1 * self.ui_scale)
        shadow_stats.setYOffset(1 * self.ui_scale)
        shadow_stats.setColor(QColor(0, 0, 0, 240))
        self.stats_text_label.setGraphicsEffect(shadow_stats)

        self.streak_bg_label = QLabel(self)
        self.streak_bg_label.hide()
        self.streak_text_label = QLabel(self)
        self.streak_text_label.hide()

        shadow_streak = QGraphicsDropShadowEffect()
        shadow_streak.setBlurRadius(5 * self.ui_scale)
        shadow_streak.setColor(QColor(0, 0, 0, 255))
        self.streak_text_label.setGraphicsEffect(shadow_streak)

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

        # 4. SIGNALE
        self.signals = OverlaySignals()
        self.signals.show_image.connect(self.display_image)
        self.signals.killfeed_entry.connect(self.add_killfeed_row)
        self.signals.update_stats.connect(self.set_stats_html)
        self.signals.update_streak.connect(self.draw_streak_ui)
        self.signals.clear_feed.connect(self.clear_killfeed)

        self.set_mouse_passthrough(True)

        # Repaint Timer gegen Artefakte (1 Sekunde)
        self.redraw_timer = QTimer(self)
        self.redraw_timer.timeout.connect(self.force_update)
        self.redraw_timer.start(1000)

    def force_update(self):
        self.repaint()

    def s(self, value):
        return int(float(value) * self.ui_scale)

    def safe_move(self, widget, x, y):
        safe_y = max(0, int(y))
        widget.move(int(x), safe_y)

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
                if "feed" in targets: self.feed_label.setStyleSheet(style)
                if "stats" in targets: self.stats_bg_label.setStyleSheet(style)
                if "streak" in targets: self.streak_bg_label.setStyleSheet(style)
                if "crosshair" in targets: self.crosshair_label.setStyleSheet(style)
        except Exception as e:
            print(f"Passthrough Error: {e}")

    # --- DRAG & DROP LOGIK ---
    def mousePressEvent(self, event):
        if not self.edit_mode: return
        pos = event.pos()
        if "border" in self.feed_label.styleSheet() and self.feed_label.geometry().contains(pos):
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
        raw_pos = event.pos() - self.drag_offset
        new_x = raw_pos.x();
        new_y = max(0, raw_pos.y())
        if self.dragging_widget == "feed":
            self.feed_label.move(new_x, new_y)
        elif self.dragging_widget == "stats":
            self.stats_bg_label.move(new_x, new_y)
            if self.gui_ref:
                cfg = self.gui_ref.config.get("stats_widget", {})
                tx, ty = self.s(cfg.get("tx", 0)), self.s(cfg.get("ty", 0))
                cx = new_x + (self.stats_bg_label.width() // 2);
                cy = new_y + (self.stats_bg_label.height() // 2)
                self.safe_move(self.stats_text_label, cx + tx - (self.stats_text_label.width() // 2),
                               cy + ty - (self.stats_text_label.height() // 2))
        elif self.dragging_widget == "streak":
            self.streak_bg_label.move(new_x, new_y)
            if self.gui_ref:
                cfg = self.gui_ref.config.get("streak", {})
                tx, ty = self.s(cfg.get("tx", 0)), self.s(cfg.get("ty", 0))
                cx = new_x + (self.streak_bg_label.width() // 2)
                cy = new_y + (self.streak_bg_label.height() // 2)
                self.safe_move(self.streak_text_label, cx + tx - (self.streak_text_label.width() // 2),
                               cy + ty - (self.streak_text_label.height() // 2))
        elif self.dragging_widget == "crosshair":
            self.crosshair_label.move(new_x, new_y)

    def mouseReleaseEvent(self, event):
        if not self.edit_mode or not self.dragging_widget: return
        mid_x = self.width() // 2;
        mid_y = self.height() // 2

        def uns(val):
            return int(val / self.ui_scale)

        if self.dragging_widget == "feed":
            curr = self.feed_label.pos();
            off_x = curr.x() - mid_x;
            off_y = curr.y() - mid_y
            if self.gui_ref:
                self.gui_ref.scale_kfx.set(uns(off_x))
                self.gui_ref.scale_kfy.set(uns(off_y))
                self.gui_ref.save_stats_config()
        elif self.dragging_widget == "stats":
            curr = self.stats_bg_label.pos();
            cx = curr.x() + (self.stats_bg_label.width() // 2);
            cy = curr.y() + (self.stats_bg_label.height() // 2)
            if self.gui_ref:
                self.gui_ref.scale_stx.set(uns(cx - mid_x))
                self.gui_ref.scale_sty.set(uns(cy - mid_y))
                self.gui_ref.save_stats_config()
        elif self.dragging_widget == "streak":
            curr = self.streak_bg_label.pos();
            cx = curr.x() + (self.streak_bg_label.width() // 2);
            cy = curr.y() + (self.streak_bg_label.height() // 2)
            if self.gui_ref:
                self.gui_ref.scale_sx.set(uns(cx - mid_x))
                self.gui_ref.scale_sy.set(uns(cy - mid_y))
                self.gui_ref.save_streak_settings()
        elif self.dragging_widget == "crosshair":
            curr = self.crosshair_label.pos();
            cx = curr.x() + (self.crosshair_label.width() // 2);
            cy = curr.y() + (self.crosshair_label.height() // 2)
            if self.gui_ref:
                self.gui_ref.scale_cx.set(uns(cx - mid_x))
                self.gui_ref.scale_cy.set(uns(cy - mid_y))
                self.gui_ref.apply_crosshair_settings()
        self.dragging_widget = None;
        self.drag_offset = None

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
        off_x = self.s(kf_conf.get("x", -800));
        off_y = self.s(kf_conf.get("y", 200))
        self.safe_move(self.feed_label, (self.width() // 2) + off_x, (self.height() // 2) + off_y)

    def set_stats_html(self, html_content, img_path):
        cfg = {}
        if self.gui_ref and hasattr(self.gui_ref, 'config'): cfg = self.gui_ref.config.get("stats_widget", {})
        base_x = (self.width() // 2) + self.s(cfg.get("x", -500));
        base_y = (self.height() // 2) + self.s(cfg.get("y", -300))
        ref_x, ref_y = base_x, base_y
        has_image = os.path.exists(img_path)
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
                self.stats_bg_label.resize(int(400 * self.ui_scale), int(100 * self.ui_scale))
            bg_x = base_x - (self.stats_bg_label.width() // 2);
            bg_y = base_y - (self.stats_bg_label.height() // 2)
            self.safe_move(self.stats_bg_label, bg_x, bg_y);
            self.stats_bg_label.show()
        else:
            self.stats_bg_label.hide()

        scaled_html = html_content
        for size in [28, 22, 20, 19, 16, 14]:
            scaled_html = scaled_html.replace(f"{size}px", f"{int(size * self.ui_scale)}px")
        self.stats_text_label.setText(scaled_html);
        self.stats_text_label.adjustSize()
        text_x = ref_x + self.s(cfg.get("tx", 0)) - (self.stats_text_label.width() // 2);
        text_y = ref_y + self.s(cfg.get("ty", 0)) - (self.stats_text_label.height() // 2)
        self.safe_move(self.stats_text_label, text_x, text_y);
        self.stats_text_label.show();
        self.stats_text_label.raise_()

    def display_image(self, img_path, duration, off_x, off_y):
        if not os.path.exists(img_path): return
        pixmap = QPixmap(img_path)
        if pixmap.isNull(): return
        temp_label = QLabel(self);
        temp_label.setPixmap(pixmap);
        temp_label.adjustSize()
        x = self.event_center_x + self.s(off_x) - (temp_label.width() // 2)
        y = self.event_center_y + self.s(off_y) - (temp_label.height() // 2)
        self.safe_move(temp_label, x, y);
        temp_label.raise_();
        temp_label.show()
        QTimer.singleShot(duration, temp_label.deleteLater)

    def draw_streak_ui(self, img_path, count, cfg):
        if count <= 0 and not self.edit_mode:
            self.streak_bg_label.hide();
            self.streak_text_label.hide();
            return
        if count <= 0: count = 5
        if os.path.exists(img_path):
            pix = QPixmap(img_path);
            final_scale = cfg.get("scale", 1.0) * self.ui_scale
            if not pix.isNull():
                pix = pix.scaled(int(pix.width() * final_scale), int(pix.height() * final_scale),
                                 Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.streak_bg_label.setPixmap(pix);
                self.streak_bg_label.adjustSize()
                bx = (self.width() // 2) + self.s(cfg.get("x", 0));
                by = (self.height() // 2) + self.s(cfg.get("y", 100))
                self.safe_move(self.streak_bg_label, bx - (self.streak_bg_label.width() // 2),
                               by - (self.streak_bg_label.height() // 2))
                self.streak_bg_label.show();
                tx = bx + self.s(cfg.get("tx", 0));
                ty = by + self.s(cfg.get("ty", 0))
                self.streak_text_label.setText(
                    f"<span style='font-size: {int(24 * final_scale)}pt; font-family: Impact; color: #ff0000; text-shadow: 2px 2px 0 #000;'>{count}</span>")
                self.streak_text_label.adjustSize();
                self.safe_move(self.streak_text_label, tx - (self.streak_text_label.width() // 2),
                               ty - (self.streak_text_label.height() // 2))
                self.streak_text_label.show();
                self.streak_text_label.raise_()

    def update_crosshair(self, path, size, enabled):
        if (not enabled and not self.edit_mode) or not os.path.exists(path):
            self.crosshair_label.hide();
            return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            self.crosshair_label.setPixmap(pixmap);
            self.crosshair_label.adjustSize()
            off_x, off_y = 0, 0
            if self.gui_ref:
                c = self.gui_ref.config.get("crosshair", {})
                off_x, off_y = self.s(c.get("x", 0)), self.s(c.get("y", 0))
            cx = (self.width() // 2) - (self.crosshair_label.width() // 2) + off_x
            cy = (self.height() // 2) - (self.crosshair_label.height() // 2) + off_y
            self.safe_move(self.crosshair_label, cx, cy);
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
        "MAX": "Max Kill",
        "Spitfire Kill": "Spitfire Auto-Turret"
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
CHAR_FILE = "characters.txt"
PLAYER_BACKUP = "player_cache_backup.txt"

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
    def __init__(self, root):
        self.root = root
        try:
            self.REFERENCE_WIDTH = 1920
            curr_width = self.root.winfo_screenwidth()
            self.ui_scale = curr_width / self.REFERENCE_WIDTH

            self.root.title("PS2 Master Client")
            self.root.geometry("1200x900")
            self.root.configure(bg="#1e1e1e")


            self.init_db()
            self.char_data = self.load_chars_from_db() or {}
            self.outfit_cache = {}
            self.name_cache = self.load_cache_from_db() or {}

            # 1. Zuerst die Config laden
            self.config = self.load_config()
            self.overlay_config = self.config

            # 2. Prüfen, ob ein Pfad gespeichert ist, sonst Standard-JPG
            saved_bg = self.config.get("main_background_path", "")
            if saved_bg and os.path.exists(saved_bg):
                self.gif_path = saved_bg
            else:
                self.gif_path = get_asset_path("background.jpg")

            #Server list
            self.server_map = {
                "Wainwright (EU)": "10",
                "Osprey (US)": "1",
                "SolTech (Asia)": "40",
                "Jaeger": "19"
            }

            # Standard ist 10 (Wainwright), falls nichts gespeichert ist
            self.current_world_id = self.config.get("world_id", "10")

            # Namen für die ID finden (für die Anzeige)
            self.current_server_name = "Wainwright (EU)"  # Default
            for name, sid in self.server_map.items():
                if sid == self.current_world_id:
                    self.current_server_name = name
                    break


            # Pfade
            self.ps2_dir = self.config.get("ps2_path", "")

            # Variablen
            saved_state = self.config.get("overlay_master_active", False)
            self.overlay_active = tk.BooleanVar(value=saved_state)
            self.char_option_menus = []
            self.current_tab = "Dashboard"
            self.current_sub_tab = "Overview"
            self.content_ids = []
            self.killstreak_count = 0
            self.kill_counter = 0
            self.is_dead = False
            self.was_revived = False
            self.streak_timeout = 12.0
            self.pop_history = [0] * 100
            self.myTeamId = 0
            self.currentZone = 0
            self.myWorldID = 0

            self.bg_photo = None
            self.last_size = (1200, 900)
            self.char_entries = []

            self.observer = None
            self.last_killer_name = "None"  # <--- Hier wurde der Crash verursacht
            self.last_killer_id = "0"  # <--- Sicherung für Enforcer-Logik
            self.last_evidence_url = ""  # <--- Sicherung für Link-Anzeige

            self.live_stats = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0, "Total": 0}
            self.session_stats = {}
            self.active_players = {}
            self.char_var = tk.StringVar(value="SELECT_UNIT...")
            self.websocket = None
            self.loop = None
            self.frac_var = tk.StringVar(value="TR")
            self.cont_var = tk.StringVar(value="Indar")
            self.current_character_id = ""
            self.check_vars = {}
            self.id_queue = Queue()
            self.item_db = {}
            self.last_kill_time = 0

            # UI Aufbau
            self.canvas = tk.Canvas(root, highlightthickness=0, bg="#1e1e1e")
            self.canvas.pack(fill="both", expand=True)
            self.bg_image_id = self.canvas.create_image(0, 0, anchor="nw")
            self.setup_ui_elements()
            self.setup_char_sub_menu()

            # Item DB laden
            csv_path = get_asset_path("sanction-list.csv")
            if os.path.exists(csv_path): self.load_item_db(csv_path)

            # Threads
            threading.Thread(target=self.cache_worker, daemon=True).start()
            self.start_websocket_thread()
            threading.Thread(target=self.ps2_process_monitor, daemon=True).start()

            # Qt Overlay im Mainthread
            self.overlay_win = None
            self.qt_app = QApplication.instance() or QApplication(sys.argv)
            self.start_qt_overlay()

            # Start-Logik
            self.root.after(500, self.show_dashboard)
            self.root.after(1000, self.update_live_graph)
            self.root.bind("<Configure>", self.on_resize)
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.after(100, lambda: self.update_background_view(self.root.winfo_width(), self.root.winfo_height()))

        except Exception as e:
            with open("crash_log.txt", "w") as f:
                f.write(traceback.format_exc())
            messagebox.showerror("Startup Error", f"Fehler:\n{str(e)}")
            self.root.destroy()

    def ps2_process_monitor(self):
        self.ps2_running = False
        while True:
            try:
                output = subprocess.check_output('TASKLIST /FI "IMAGENAME eq PlanetSide2_x64.exe"', shell=True).decode(
                    "cp1252", errors="ignore")
                is_now_running = "PlanetSide2_x64.exe" in output

                if is_now_running != self.ps2_running:
                    self.ps2_running = is_now_running

                    if is_now_running:
                        self.add_log("MONITOR: PlanetSide 2 gestartet.")

                        # Prüfen ob Master-Switch AN ist
                        if self.overlay_active.get():
                            # 1. Crosshair an
                            self.root.after(0, self.auto_enable_overlay)
                            # 2. Stats-Loop starten
                            self.root.after(0, self.refresh_ingame_overlay)
                            # 3. Killfeed einschalten
                            if self.overlay_win and hasattr(self.overlay_win, 'feed_label'):
                                self.root.after(0, self.overlay_win.feed_label.show)
                                self.root.after(0, lambda: self.overlay_win.feed_label.setText(""))
                        else:
                            self.add_log("MONITOR: Master-Switch ist AUS. Overlay bleibt inaktiv.")

                    else:
                        self.add_log("MONITOR: PlanetSide 2 beendet.")
                        # Ruft unsere neue stop_overlay_logic auf -> Versteckt Stats, Feed UND Zahl
                        self.root.after(0, self.stop_overlay_logic)

                        # Zur Sicherheit Crosshair explizit verstecken
                        if self.overlay_win:
                            self.root.after(0, self.overlay_win.crosshair_label.hide)

            except:
                pass
            time.sleep(5)

    def auto_enable_overlay(self):
        """Wird aufgerufen, wenn PlanetSide2_x64.exe gefunden wird."""
        if self.overlay_win:
            # Falls das Fenster minimiert oder versteckt war:
            self.overlay_win.showFullScreen()

            # Jetzt laden wir die Crosshair-Daten und machen es sichtbar
            c_conf = self.config.get("crosshair", {})
            path = get_asset_path(c_conf.get("file", "crosshair.png"))
            size = c_conf.get("size", 32)
            active = c_conf.get("active", True)

            # Dieser Aufruf zeigt das Crosshair nun aktiv an
            self.overlay_win.update_crosshair(path, size, active)
            self.add_log("GAME: PlanetSide 2 erkannt. Crosshair aktiviert.")

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
                self.overlay_win = QtOverlay()
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
        self.overlay_enabled = not self.overlay_enabled

        if self.overlay_enabled:
            self.btn_overlay_toggle.config(text="OVERLAY SYSTEM DEAKTIVIEREN", bg="#28a745")
            self.add_log("OVERLAY: Aktiviere System...")

            if self.overlay_win is None:
                # KEIN THREAD! Einfach direkt aufrufen
                self.start_qt_overlay()
            else:
                self.overlay_win.showFullScreen()
        else:
            self.btn_overlay_toggle.config(text="OVERLAY SYSTEM AKTIVIEREN", bg="#dc3545")
            self.add_log("OVERLAY: System Deaktiviert")
            if self.overlay_win:
                self.overlay_win.hide()

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

    def apply_crosshair_settings(self):
        try:
            # Werte aus GUI auslesen
            new_file = self.ent_cross_path.get()

            # Fehler abfangen, falls Größe leer oder Text ist
            try:
                new_size = int(self.crosshair_size_entry.get())
            except ValueError:
                new_size = 32  # Fallback

            new_x = self.scale_cx.get()
            new_y = self.scale_cy.get()

            # WICHTIG: Prüfen ob Variable existiert, sonst Default True
            if hasattr(self, 'crosshair_active_var'):
                is_active = self.crosshair_active_var.get()
            else:
                is_active = True

            # In die Haupt-Config schreiben
            if "crosshair" not in self.config:
                self.config["crosshair"] = {}

            self.config["crosshair"]["file"] = new_file
            self.config["crosshair"]["size"] = new_size
            self.config["crosshair"]["x"] = new_x
            self.config["crosshair"]["y"] = new_y
            self.config["crosshair"]["active"] = is_active

            # Permanent speichern
            self.save_config()
            self.add_log(f"SYSTEM: Crosshair-Konfiguration aktualisiert.")

            # Live-Update an das Qt-Fenster senden
            if self.overlay_win:
                full_path = get_asset_path(new_file)
                self.overlay_win.update_crosshair(full_path, new_size, is_active)

        except Exception as e:
            self.add_log(f"Error saving crosshair: {e}")
            traceback.print_exc()  # Hilft beim Debuggen in der Konsole

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
    def update_background_view(self, w, h):
        if not self.gif_path or not os.path.exists(self.gif_path): return
        w, h = max(w, 100), max(h, 100)
        try:
            img_obj = Image.open(self.gif_path)
            resized_img = img_obj.resize((w, h), Image.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(resized_img)
            self.canvas.itemconfig(self.bg_image_id, image=self.bg_photo)
        except Exception as e:
            print(f"Fehler beim Laden des Hintergrunds: {e}")

    def setup_ui_elements(self):
        w = self.root.winfo_width() if self.root.winfo_width() > 10 else 850
        mid = w // 2
        self.title_id = self.canvas.create_text(mid, 50, text="PLANETSIDE 2 MASTER CONTROL", fill="#00f2ff",
                                                font=("Arial", 22, "bold"))

        btn_nav_frame = tk.Frame(self.root, bg="#111")
        btn_style = {"bg": "#111", "fg": "white", "relief": "flat", "width": 14, "font": ("Arial", 10, "bold")}

        tk.Button(btn_nav_frame, text="DASHBOARD", command=self.show_dashboard, **btn_style).pack(side="left", padx=2)
        tk.Button(btn_nav_frame, text="LAUNCHER", command=self.show_launcher, **btn_style).pack(side="left", padx=2)
        tk.Button(btn_nav_frame, text="ENFORCER", command=self.show_enforcer, **btn_style).pack(side="left", padx=2)
        # tk.Button(btn_nav_frame, text="NSO TELEPORTER", command=self.show_nso_teleporter, **btn_style).pack(side="left", padx=2)
        tk.Button(btn_nav_frame, text="Ingame Overlay", command=self.show_ingame_overlay_tab, **btn_style).pack(
            side="left", padx=2)

        # --- CHARACTERS BUTTON MIT HOVER BINDING (KORRIGIERT) ---
        char_btn = tk.Button(btn_nav_frame, text="CHARACTERS",
                             command=lambda: [setattr(self, 'current_sub_tab', 'Overview'), self.show_characters()],
                             **btn_style)
        char_btn.pack(side="left", padx=2)
        char_btn.bind("<Enter>", self.show_sub_menu)
        char_btn.bind("<Leave>", self.hide_sub_menu)

        tk.Button(btn_nav_frame, text="SETTINGS", command=self.show_settings, **btn_style).pack(side="left", padx=2)

        self.nav_id = self.canvas.create_window(mid, 110, window=btn_nav_frame)
        self.content_ids = []
        self.show_launcher()

    def setup_char_sub_menu(self):
        # Das Frame für das Untermenü
        self.sub_menu_frame = tk.Frame(self.root, bg="#0a141d", bd=1, relief="solid", highlightbackground="#00f2ff",
                                       highlightthickness=1)

        self.sub_items = [
            "Overview", "Weapon stats", "Vehicle stats", "Sessions",
            "Unlocks", "Friends", "Directives", "Achievements",
            "Outfit history", "Killboard", "Alerts"
        ]
        self.sub_buttons = []

        for item in self.sub_items:
            btn = tk.Button(self.sub_menu_frame, text=item.upper(),
                            bg="#0a141d", fg="#00f2ff",
                            font=("Consolas", 8, "bold"),
                            activebackground="#00f2ff", activeforeground="black",
                            bd=0, padx=8, pady=5,
                            command=lambda i=item: self.handle_sub_click(i))
            btn.pack(side="left")
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#1a2b3c"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#0a141d"))
            self.sub_buttons.append(btn)

    def animate_api_light(self, canvas, light_id, color_type, step=0):
        import math
        brightness = (math.sin(step) + 1) / 4 + 0.5
        color_hex = f'#{0 if color_type == "green" else int(255 * brightness):02x}{int(255 * brightness) if color_type == "green" else 0:02x}00'
        try:
            canvas.itemconfig(light_id, fill=color_hex, outline="#333")
            self.root.after(50, lambda: self.animate_api_light(canvas, light_id, color_type, step + 0.1))
        except:
            pass

    def show_dashboard(self):
        # 1. Zuerst IMMER aufräumen
        self.clear_content()
        self.current_tab = "Dashboard"

        # WICHTIG: Alte Graphen-Referenzen löschen
        if hasattr(self, 'graph_line'): del self.graph_line
        if hasattr(self, 'graph_glow'): del self.graph_glow

        # Fenstergröße setzen
        self.root.geometry("1600x1000")
        mid = self.root.winfo_width() // 2

        # 2. Haupt-Frame erstellen
        dash_frame = tk.Frame(self.root, bg="#1a1a1a", bd=1, relief="solid", highlightbackground="#00f2ff")
        self.dash_widgets = {"frame": dash_frame, "factions": {}}

        tk.Label(dash_frame, text="WAINWRIGHT LIVE TELEMETRY", font=("Arial", 24, "bold"), bg="#1a1a1a",
                 fg="#00f2ff").pack(pady=15)

        # 3. Größeres Canvas für den Graphen
        g_canvas = tk.Canvas(dash_frame, width=800, height=200, bg="#050505", highlightthickness=0)
        g_canvas.pack(pady=10, padx=20)
        self.dash_widgets["canvas"] = g_canvas

        self.total_players_label = tk.Label(dash_frame, text="Total Players: 0", font=("Consolas", 22, "bold"),
                                            bg="#1a1a1a", fg="#00f2ff")
        self.total_players_label.pack(pady=10)

        # 4. Fraktionen Grid
        f_frame = tk.Frame(dash_frame, bg="#111", pady=10)
        f_frame.pack(fill="x", padx=10)

        for name, color in [("TR", "#ff0000"), ("NC", "#0066ff"), ("VS", "#9900ff")]:
            f_box = tk.Frame(f_frame, bg="#1a1a1a", bd=1, relief="flat")
            f_box.pack(side="left", expand=True, fill="both", padx=5)

            tk.Label(f_box, text=name, font=("Arial", 16, "bold"), bg="#1a1a1a", fg=color).pack(pady=(5, 0))
            p_lab = tk.Label(f_box, text="0.0%", font=("Consolas", 20, "bold"), bg="#1a1a1a", fg="white")
            p_lab.pack()

            # Balken
            bar_bg = tk.Frame(f_box, bg="#333", height=8, width=180)
            bar_bg.pack(pady=10);
            bar_bg.pack_propagate(False)
            bar = tk.Frame(bar_bg, bg=color, height=8)
            bar.place(x=0, y=0, width=0)

            tk.Label(f_box, text="TOP PERFORMERS", font=("Arial", 10, "bold"), bg="#1a1a1a", fg="#555").pack(
                pady=(15, 0))

            # --- TABELLEN-HEADER ---
            list_frame = tk.Frame(f_box, bg="#1a1a1a")
            list_frame.pack(fill="x", padx=5, pady=5)

            headers = [("PLAYER", 0, 32), ("K", 1, 4), ("KPM", 2, 5), ("D", 3, 4), ("A", 4, 4), ("K/D", 5, 5),
                       ("KDA", 6, 5)]
            for text, col, width in headers:
                h_lbl = tk.Label(list_frame, text=text, font=("Consolas", 8, "bold"),
                                 bg="#141414", fg="#00f2ff", anchor="w" if col == 0 else "center", width=width)
                h_lbl.grid(row=0, column=col, sticky="nsew", padx=1)

            self.dash_widgets["factions"][name] = {
                "label": p_lab,
                "bar": bar,
                "list_frame": list_frame
            }

        # Footer
        self.dash_widgets["footer"] = tk.Label(dash_frame, text="", font=("Arial", 10), bg="#1a1a1a", fg="#00f2ff")
        self.dash_widgets["footer"].pack(pady=10)

        id_dash = self.canvas.create_window(mid, 480, window=dash_frame, width=1450, height=850)
        self.content_ids.append(id_dash)
        self.update_dashboard_elements()

    def update_dashboard_elements(self):
        # 1. Sicherheitscheck
        if not hasattr(self, 'dash_widgets') or self.current_tab != "Dashboard":
            return

        if not hasattr(self, 'session_stats'): self.session_stats = {}

        # Zeitstempel für Berechnungen
        now = time.time()

        # WICHTIG: Session-Startzeit tracken, falls noch nicht geschehen
        if not hasattr(self, 'session_start_time'):
            self.session_start_time = now

        canvas = self.dash_widgets.get("canvas")
        if not canvas or not canvas.winfo_exists():
            return

        try:
            # --- GRAPH DATEN ZEICHNEN ---
            total_w, total_h = 800, 180
            off_l, off_r, off_t, off_b = 40, 10, 25, 20
            draw_w, draw_h = total_w - off_l - off_r, total_h - off_t - off_b
            max_pop = 1500
            points = []
            if len(self.pop_history) > 1:
                for idx, val in enumerate(self.pop_history):
                    x = off_l + (idx * (draw_w / (len(self.pop_history) - 1)))
                    y = (total_h - off_b) - (val * (draw_h / max_pop))
                    y = max(off_t, min(y, total_h - off_b))
                    points.extend([x, y])
                canvas.delete("all")
                for i in range(0, max_pop + 1, 300):
                    y_p = (total_h - off_b) - (i * (draw_h / max_pop))
                    canvas.create_line(off_l, y_p, total_w - off_r, y_p, fill="#151515")
                    canvas.create_text(off_l - 8, y_p, text=str(i), fill="#777", font=("Arial", 7), anchor="e")
                for i in range(0, 101, 20):
                    x_p = off_l + (i * (draw_w / 100))
                    sec_display = 100 - i
                    time_text = "NOW" if sec_display == 0 else f"-{sec_display}s"
                    canvas.create_text(x_p, off_t - 5, text=time_text, fill="#00f2ff", font=("Arial", 7, "bold"),
                                       anchor="s")
                canvas.create_polygon([off_l, total_h - off_b] + points + [total_w - off_r, total_h - off_b],
                                      fill="#001a1a")
                canvas.create_line(points, fill="#00f2ff", width=2, smooth=True)
                canvas.create_line(off_l, off_t, off_l, total_h - off_b, fill="#333")
                canvas.create_line(off_l, total_h - off_b, total_w - off_r, total_h - off_b, fill="#333")

            # --- STATS AKTUALISIEREN ---
            total = self.live_stats.get("Total", 0)
            now = time.time()

            # WICHTIG: Session Startzeit sicherstellen
            if not hasattr(self, 'session_start_time'): self.session_start_time = now
            session_duration_min = (now - self.session_start_time) / 60

            # 1. Total Label aktualisieren
            if hasattr(self, 'total_players_label'):
                self.total_players_label.config(text=f"Total Players: {total}")

            # 2. Filter: Wer soll in die Liste? (10 Min Inaktivitäts-Check)
            active_players = []
            for p in self.session_stats.values():
                if isinstance(p, dict):  # NUR wenn es ein Dictionary ist (kein int!)
                    last_active = p.get("last_kill_time")
                    if last_active is None or (now - last_active) < 600:
                        active_players.append(p)

            # 3. Die Fraktions-Listen befüllen
            for name, w in self.dash_widgets.get("factions", {}).items():
                # Balken & Prozente
                count = self.live_stats.get(name, 0)
                perc = (count / total * 100) if total > 0 else 0
                if "label" in w: w["label"].config(text=f"{perc:.1f}%")
                if "count" in w: w["count"].config(text=f"{count} Players")
                if "bar" in w: w["bar"].place(width=int(perc * 1.8))

                list_frame = w.get("list_frame")
                if not list_frame: continue

                # ALTE ZEILEN LÖSCHEN (Wichtig für Refresh)
                for child in list_frame.winfo_children():
                    # Wir behalten nur Reihe 0 (den Header)
                    try:
                        if int(child.grid_info()["row"]) > 0: child.destroy()
                    except:
                        pass

                # Spieler dieser Fraktion sortieren
                f_players = [p for p in active_players if p.get("faction") == name]
                f_players.sort(key=lambda x: x.get("k", 0), reverse=True)

                # Top 5 zeichnen
                for i, p in enumerate(f_players[:5]):
                    row_idx = i + 1

                    # 1. ID holen
                    p_id = p.get("id")

                    # 2. CHECK: Ist der Name inzwischen im Cache bekannt?
                    # Wenn im Stats-Objekt noch "Searching..." steht, aber der Cache den Namen hat -> UPDATE!
                    if p.get("name") in ["Unknown", "Searching...", None] and p_id in self.name_cache:
                        p["name"] = self.name_cache[p_id]

                    # 3. Den Namen für die Anzeige setzen
                    display_name = p.get("name", "Searching...")

                    # Rest der Berechnung wie vorher...
                    k, a, d = p.get("k", 0), p.get("a", 0), p.get("d", 0)

                    p_start = p.get("first_kill_time", now)
                    p_dur = (now - p_start) / 60
                    stable_min = max(session_duration_min, p_dur, 1.0)

                    kpm = k / stable_min
                    kd = k / max(1, d)
                    kda = (k + a) / max(1, d)

                    bg_col = "#1d1d1d" if row_idx % 2 == 0 else "#1a1a1a"

                    # Die Liste der Daten für die Labels
                    row_data = [
                        (display_name[:32], 32, "w", "#ccc"),  # Hier nutzen wir den geupdateten Namen
                        (k, 4, "center", "white"),
                        (f"{kpm:.1f}", 5, "center", self.get_kpm_color(kpm)),
                        (d, 4, "center", "white"),
                        (a, 4, "center", "white"),
                        (f"{kd:.1f}", 5, "center", self.get_kpm_color(kd)),
                        (f"{kda:.1f}", 5, "center", "#00f2ff")
                    ]

                    # Labels zeichnen
                    for col_idx, (val, width, anchor, fg) in enumerate(row_data):
                        tk.Label(list_frame, text=val, font=("Consolas", 10),
                                 bg=bg_col, fg=fg, anchor=anchor, width=width).grid(row=row_idx, column=col_idx,
                                                                                    sticky="nsew", padx=1)

        except Exception as e:
            print(f"DEBUG: Dashboard Update failed: {e}")

        if "footer" in self.dash_widgets:
            self.dash_widgets["footer"].config(text=f"Last Update: {time.strftime('%H:%M:%S')}")

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
        for name, wid in self.server_map.items():
            if str(wid) == str(world_id):
                return name
        return "Unknown Server"

    def save_config(self):
        """Speichert die gesamte Konfiguration in die config.json"""
        try:
            # Pfad zur config.json im Hauptverzeichnis
            config_path = os.path.join(BASE_DIR, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                # indent=4 macht die Datei für Menschen lesbar (schön formatiert)
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Fehler beim Speichern der config.json: {e}")

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
        """Triggert das Bild im Qt-Overlay mit Offsets und Dauer"""
        if not hasattr(self, 'overlay_win') or not self.overlay_win:
            return

        # Daten aus der Config laden
        event_data = self.config.get("events", {}).get(event_type, {})
        if not event_data:
            return

        # Offsets und Dauer auslesen
        try:
            ox = int(event_data.get("x_offset", 0))
            oy = int(event_data.get("y_offset", 0))
            # Nutzt gespeicherte Dauer, Fallback auf 3000ms
            dur = int(event_data.get("duration", 3000))
        except (ValueError, TypeError):
            ox, oy, dur = 0, 0, 3000

        img_name = event_data.get("img")
        if img_name:
            img_path = get_asset_path(img_name)
            if os.path.exists(img_path):
                # Signal senden: (Pfad, Dauer, X, Y)
                self.overlay_win.signals.show_image.emit(img_path, dur, ox, oy)

        # Sound abspielen (unverändert)
        if HAS_SOUND:
            snd_name = event_data.get("snd")
            if snd_name:
                sound_path = get_asset_path(snd_name)
                if os.path.exists(sound_path):
                    try:
                        pygame.mixer.Sound(sound_path).play()
                    except:
                        pass

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

    def show_ingame_overlay_tab(self):
        self.clear_content()
        self.current_tab = "Ingame Overlay"
        mid = self.root.winfo_width() // 2

        # Styles für die Tabs
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#333", foreground="white", font=('Consolas', 10, 'bold'),
                        padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#00f2ff")], foreground=[("selected", "black")])

        # Notebook erstellen und binden
        self.ovl_notebook = ttk.Notebook(self.root)
        self.ovl_notebook.bind("<<NotebookTabChanged>>", self.on_overlay_tab_change)

        # =========================================================
        # TAB 1: IDENTITY (Verschoben von Pos 4 auf Pos 1)
        # =========================================================
        tab_ident = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_ident, text=" IDENTITY ")

        tk.Label(tab_ident, text="ACTIVE TRACKING IDENTITY", font=("Consolas", 14, "bold"), bg="#1a1a1a",
                 fg="#00f2ff").pack(pady=(20, 10))
        tk.Label(tab_ident,
                 text="Select the character you are currently playing.\nOnly events for this ID will trigger overlay effects.",
                 bg="#1a1a1a", fg="#888", font=("Consolas", 9)).pack(pady=(0, 20))

        opts = list(self.char_data.keys()) if self.char_data else ["N/A"]
        self.ovl_char_menu = tk.OptionMenu(tab_ident, self.char_var, *opts, command=self.update_active_char)
        self.ovl_char_menu.config(bg="#333", fg="white", font=("Consolas", 11, "bold"), width=25, bd=0,
                                  highlightthickness=0)
        self.ovl_char_menu["menu"].config(bg="#333", fg="white", font=("Consolas", 11))
        self.ovl_char_menu.pack(pady=5)
        self.char_option_menus.append(self.ovl_char_menu)

        tk.Button(tab_ident, text="DELETE SELECTED", bg="#440000", fg="#ff4444", font=("Consolas", 9),
                  command=self.delete_char).pack(pady=5)

        tk.Frame(tab_ident, height=2, bd=1, relief="sunken", bg="#333").pack(fill="x", padx=40, pady=20)

        tk.Label(tab_ident, text="ADD NEW CHARACTER", font=("Consolas", 11, "bold"), bg="#1a1a1a", fg="#00ff00").pack(
            pady=(10, 5))
        add_frame = tk.Frame(tab_ident, bg="#1a1a1a");
        add_frame.pack()
        self.ovl_char_entry = tk.Entry(add_frame, bg="#111", fg="#00f2ff", font=("Consolas", 11), width=20)
        self.ovl_char_entry.pack(side="left", padx=5)
        self.ovl_char_entry.bind("<Return>", lambda e: self.add_char())
        tk.Button(add_frame, text="ADD", bg="#004400", fg="white", font=("Consolas", 10, "bold"),
                  command=self.add_char).pack(side="left")

        # --- MASTER SCHALTER (Verschoben von Crosshair Tab hierher) ---
        sep_master = tk.Frame(tab_ident, height=2, bd=1, relief="sunken", bg="#333")
        sep_master.pack(fill="x", padx=40, pady=20)

        check_btn = tk.Checkbutton(tab_ident, text="SYSTEM OVERLAY MASTER-SWITCH", variable=self.overlay_active,
                                   bg="#1a1a1a", fg="#00ff00", selectcolor="black", font=("Consolas", 12, "bold"),
                                   command=self.toggle_master_switch)  # <--- Hier rufen wir jetzt die Speicher-Funktion auf
        check_btn.pack(pady=10)

        # =========================================================
        # TAB 2: EVENTS (WIEDER EINGEFÜGT, DAMIT DER FEHLER WEG GEHT)
        # =========================================================
        tab_events = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_events, text=" EVENTS (Kills/Deaths) ")

        event_categories = {
            "STANDARD KILLS": ["Kill", "Headshot", "Death", "Hitmarker", "Team Kill", "Team Kill Victim"],
            "STREAK MEILENSTEINE": ["Squad Wiper", "Double Squad Wipe", "Squad Lead's Nightmare", "One Man Platoon"],
            "MULTI KILL RUSH": ["Double Kill", "Multi Kill", "Mega Kill", "Ultra Kill", "Monster Kill",
                                "Ludicrous Kill", "Holy Shit"],
            "SPEZIAL EVENTS": ["Domination", "Revenge", "Killstreak Stop", "Nade Kill", "Knife Kill", "Max Kill",
                               "Road Kill", "Roadkill Victim", "Spitfire Kill", "Gunner Kill", "Tankmine Kill",
                               "AP-Mine Kill"],
            "SUPPORT & TEAM": ["Revive Given", "Revive Taken", "Heal", "Resupply", "Repair", "Break Construction"],
            "OBJECTIVES": ["Point Control", "Sunderer Spawn", "Base Capture", "Gunner Assist", "Alert End",
                           "Alert Win"],
            "SYSTEM / LOGIN": ["Login TR", "Login NC", "Login VS", "Login NSO"]
        }

        grid_frame = tk.Frame(tab_events, bg="#1a1a1a");
        grid_frame.pack(fill="both", expand=True, pady=10, padx=5)
        self.var_event_sel = tk.StringVar(value="Kill")
        self.lbl_current_edit = tk.Label(tab_events, text="EDITING: Kill", font=("Consolas", 14, "bold"), bg="#1a1a1a",
                                         fg="#00ff00");
        self.lbl_current_edit.pack(pady=(0, 5))

        for cat_name, items in event_categories.items():
            col_frame = tk.Frame(grid_frame, bg="#222", bd=1, relief="solid");
            col_frame.pack(side="left", fill="both", padx=2, expand=True)
            tk.Label(col_frame, text=cat_name, bg="#333", fg="#00f2ff", font=("Arial", 7, "bold")).pack(fill="x",
                                                                                                        pady=(0, 2))
            for item in items:
                tk.Button(col_frame, text=item, bg="#1a1a1a", fg="#ccc", font=("Arial", 8), bd=0,
                          activebackground="#00f2ff", activeforeground="black",
                          command=lambda x=item: self.select_event_from_grid(x)).pack(fill="x", pady=0)

        # Settings Bereich (Hier fehlten die widgets!)
        settings_frame = tk.Frame(tab_events, bg="#1a1a1a");
        settings_frame.pack(fill="x", pady=10)

        tk.Label(settings_frame, text="Image (PNG):", bg="#1a1a1a", fg="white").grid(row=0, column=0, sticky="e",
                                                                                     padx=5)
        self.ent_evt_img = tk.Entry(settings_frame, width=30, bg="#111", fg="#00f2ff")  # <--- DAS HAT GEFEHLT
        self.ent_evt_img.grid(row=0, column=1, sticky="w")
        tk.Button(settings_frame, text="Browse", command=lambda: self.browse_file(self.ent_evt_img, "png"), bg="#333",
                  fg="white", font=("Arial", 8)).grid(row=0, column=2, padx=5)

        tk.Label(settings_frame, text="Sound:", bg="#1a1a1a", fg="white").grid(row=1, column=0, sticky="e", padx=5)
        self.ent_evt_snd = tk.Entry(settings_frame, width=30, bg="#111", fg="#00f2ff")
        self.ent_evt_snd.grid(row=1, column=1, sticky="w")
        tk.Button(settings_frame, text="Browse", command=lambda: self.browse_file(self.ent_evt_snd, "audio"), bg="#333",
                  fg="white", font=("Arial", 8)).grid(row=1, column=2, padx=5)

        sl_frame = tk.Frame(tab_events, bg="#1a1a1a");
        sl_frame.pack(fill="x", padx=20)
        self.scale_ex = tk.Scale(sl_frame, from_=-900, to=900, orient="horizontal", bg="#1a1a1a", fg="#00f2ff",
                                 label="X Offset");
        self.scale_ex.pack(side="left", fill="x", expand=True, padx=5)
        self.scale_ey = tk.Scale(sl_frame, from_=-500, to=500, orient="horizontal", bg="#1a1a1a", fg="#00f2ff",
                                 label="Y Offset");
        self.scale_ey.pack(side="left", fill="x", expand=True, padx=5)
        self.scale_png_size = tk.Scale(sl_frame, from_=0.1, to=2.0, resolution=0.05, orient="horizontal", bg="#1a1a1a",
                                       fg="#00f2ff", label="Scale");
        self.scale_png_size.set(1.0);
        self.scale_png_size.pack(side="left", fill="x", expand=True, padx=5)

        dur_frame = tk.Frame(tab_events, bg="#1a1a1a")
        dur_frame.pack(pady=5)

        tk.Label(dur_frame, text="Display Duration (ms):", bg="#1a1a1a", fg="#aaaaaa", font=("Arial", 9)).pack(
            side="left", padx=5)
        vcmd_num = (self.root.register(lambda P: P.isdigit() or P == ""), '%P')
        self.ent_evt_duration = tk.Entry(dur_frame, width=8, bg="#111111", fg="white", insertbackground="white",
                                         validate='key', validatecommand=vcmd_num)
        # Standardwert setzen (wird beim Wechseln des Events normalerweise überschrieben)
        self.ent_evt_duration.insert(0, "3000")
        self.ent_evt_duration.pack(side="left", padx=5)

        btn_box = tk.Frame(tab_events, bg="#1a1a1a");
        btn_box.pack(pady=15)
        tk.Button(btn_box, text="SAVE THIS EVENT", bg="#004400", fg="white", width=20,
                  command=self.save_event_ui_data).pack(side="left", padx=10)
        tk.Button(btn_box, text="TEST PREVIEW", bg="#444", fg="white", width=20,
                  command=lambda: self.trigger_overlay_event(self.var_event_sel.get())).pack(side="left", padx=10)

        # =========================================================
        # TAB 3: KILLSTREAK
        # =========================================================
        tab_streak = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_streak, text=" KILLSTREAK ")
        s_conf = self.overlay_config.get("streak", {})

        tk.Label(tab_streak, text="Streak Hintergrund (PNG):", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        strk_img_f = tk.Frame(tab_streak, bg="#1a1a1a");
        strk_img_f.pack()
        self.ent_streak_img = tk.Entry(strk_img_f, width=40, bg="#111", fg="#00f2ff")
        self.ent_streak_img.pack(side="left")
        self.ent_streak_img.insert(0, get_short_name(s_conf.get("img", "KS_Counter.png")))
        tk.Button(strk_img_f, text="Browse", command=lambda: self.browse_file(self.ent_streak_img, "png"), bg="#333",
                  fg="white").pack(side="left")

        tk.Label(tab_streak, text="Position BILD (Offset):", bg="#1a1a1a", fg="#00f2ff").pack(pady=(15, 0))
        img_pos_f = tk.Frame(tab_streak, bg="#1a1a1a");
        img_pos_f.pack(fill="x", padx=50)
        self.scale_sx = tk.Scale(img_pos_f, from_=-1000, to=1000, orient="horizontal", bg="#1a1a1a", fg="white",
                                 label="Bild X")
        self.scale_sx.set(s_conf.get("x", 0));
        self.scale_sx.pack(side="left", fill="x", expand=True)
        self.scale_sy = tk.Scale(img_pos_f, from_=-700, to=700, orient="horizontal", bg="#1a1a1a", fg="white",
                                 label="Bild Y")
        self.scale_sy.set(s_conf.get("y", 100));
        self.scale_sy.pack(side="left", fill="x", expand=True)

        tk.Label(tab_streak, text="Position ZAHL (Relativ zum Bild):", bg="#1a1a1a", fg="#ffcc00").pack(pady=(15, 0))
        txt_pos_f = tk.Frame(tab_streak, bg="#1a1a1a");
        txt_pos_f.pack(fill="x", padx=50)
        self.scale_tx = tk.Scale(txt_pos_f, from_=-200, to=200, orient="horizontal", bg="#1a1a1a", fg="white",
                                 label="Zahl X Offset")
        self.scale_tx.set(s_conf.get("tx", 0));
        self.scale_tx.pack(side="left", fill="x", expand=True)
        self.scale_ty = tk.Scale(txt_pos_f, from_=-200, to=200, orient="horizontal", bg="#1a1a1a", fg="white",
                                 label="Zahl Y Offset")
        self.scale_ty.set(s_conf.get("ty", 0));
        self.scale_ty.pack(side="left", fill="x", expand=True)

        tk.Label(tab_streak, text="Skalierung:", bg="#1a1a1a", fg="#4a6a7a").pack(pady=(15, 0))
        self.scale_s_size = tk.Scale(tab_streak, from_=0.1, to=3.0, resolution=0.05, orient="horizontal", bg="#1a1a1a",
                                     fg="white")
        self.scale_s_size.set(s_conf.get("scale", 1.0));
        self.scale_s_size.pack(fill="x", padx=50)

        s_btn_box = tk.Frame(tab_streak, bg="#1a1a1a");
        s_btn_box.pack(pady=20)
        tk.Button(s_btn_box, text="SAVE STREAK", bg="#004400", fg="white", width=15, height=2,
                  command=self.save_streak_settings).pack(side="left", padx=10)

        # NEU: Drag & Drop Button für Killstreak
        self.btn_edit_streak = tk.Button(s_btn_box, text="LAYOUT PER MAUS VERSCHIEBEN", bg="#0066ff", fg="white",
                                         width=25, command=self.toggle_hud_edit_mode)
        self.btn_edit_streak.pack(side="left", padx=10)

        tk.Button(s_btn_box, text="TEST (5 KILLS)", bg="#444", fg="white", width=15, height=2,
                  command=self.test_streak_visuals).pack(side="left", padx=10)

        # Daten laden (JETZT erst aufrufen, wo ent_evt_img existiert!)
        self.load_event_ui_data("Kill")

        # =========================================================
        # TAB 4: CROSSHAIR
        # =========================================================
        tab_cross = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_cross, text=" CROSSHAIR ")

        if "crosshair" not in self.config:
            self.config["crosshair"] = {"file": "crosshair.png", "size": 32, "x": 0, "y": 0, "active": True}
        c_conf = self.config["crosshair"]

        # --- NEU: AKTIVIERUNGS-CHECKBOX (Das hat gefehlt!) ---
        self.crosshair_active_var = tk.BooleanVar(value=c_conf.get("active", True))
        tk.Checkbutton(tab_cross, text="CROSSHAIR ANZEIGEN", variable=self.crosshair_active_var,
                       bg="#1a1a1a", fg="#00ff00", selectcolor="black", font=("Consolas", 12, "bold")).pack(
            pady=(15, 5))

        # 1. Bild
        tk.Label(tab_cross, text="Crosshair Image (PNG):", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        f_frame = tk.Frame(tab_cross, bg="#1a1a1a");
        f_frame.pack(pady=5)
        self.ent_cross_path = tk.Entry(f_frame, width=40, bg="#111", fg="#00f2ff", bd=1)
        self.ent_cross_path.pack(side="left", padx=5)
        self.ent_cross_path.insert(0, c_conf.get("file", "crosshair.png"))
        tk.Button(f_frame, text="Browse", command=lambda: self.browse_file(self.ent_cross_path, "png"), bg="#333",
                  fg="white").pack(side="left")

        # 2. Größe
        s_frame = tk.Frame(tab_cross, bg="#1a1a1a");
        s_frame.pack(pady=10)
        tk.Label(s_frame, text="Größe (px):", bg="#1a1a1a", fg="white").pack(side="left", padx=5)
        self.crosshair_size_entry = tk.Entry(s_frame, width=8, bg="#111", fg="#00f2ff", bd=1)
        self.crosshair_size_entry.insert(0, str(c_conf.get("size", 32)))
        self.crosshair_size_entry.pack(side="left")

        # 3. Position Sliders
        tk.Label(tab_cross, text="Position X / Y Offset:", bg="#1a1a1a", fg="#4a6a7a").pack(pady=(15, 0))
        self.scale_cx = tk.Scale(tab_cross, from_=-500, to=500, orient="horizontal", bg="#1a1a1a", fg="#00f2ff",
                                 label="X Offset")
        self.scale_cx.set(c_conf.get("x", 0));
        self.scale_cx.pack(fill="x", padx=100)
        self.scale_cy = tk.Scale(tab_cross, from_=-500, to=500, orient="horizontal", bg="#1a1a1a", fg="#00f2ff",
                                 label="Y Offset")
        self.scale_cy.set(c_conf.get("y", 0));
        self.scale_cy.pack(fill="x", padx=100)

        # 4. Buttons (Save + DragDrop)
        tk.Button(tab_cross, text="SAVE & APPLY CROSSHAIR", bg="#00f2ff", fg="black", font=("Consolas", 11, "bold"),
                  command=self.apply_crosshair_settings).pack(pady=15)

        # =========================================================
        # TAB 5: SESSION STATS & KILLFEED
        # =========================================================
        tab_stats = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_stats, text=" SESSION STATS & FEED ")

        st_conf = self.overlay_config.get("stats_widget", {"active": True, "x": -500, "y": -300})

        tk.Label(tab_stats, text="--- SESSION STATS WIDGET ---", font=("Consolas", 12, "bold"), bg="#1a1a1a",
                 fg="#00f2ff").pack(pady=(10, 5))
        self.var_stats_active = tk.BooleanVar(value=st_conf.get("active", True))
        tk.Checkbutton(tab_stats, text="SHOW LIVE STATS", variable=self.var_stats_active, bg="#1a1a1a", fg="#00ff00",
                       selectcolor="black", font=("Consolas", 10), command=self.save_stats_config).pack()

        tk.Label(tab_stats, text="Hintergrund (PNG):", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        st_img_f = tk.Frame(tab_stats, bg="#1a1a1a");
        st_img_f.pack()
        self.ent_stats_img = tk.Entry(st_img_f, width=30, bg="#111", fg="#00f2ff");
        self.ent_stats_img.pack(side="left")
        self.ent_stats_img.insert(0, get_short_name(st_conf.get("img", "")))
        tk.Button(st_img_f, text="...", command=lambda: self.browse_file(self.ent_stats_img, "png"), bg="#333",
                  fg="white", width=3).pack(side="left")

        tk.Label(tab_stats, text="Widget Position (X / Y Offset):", bg="#1a1a1a", fg="#ccc").pack(pady=(10, 0))
        st_pos_f = tk.Frame(tab_stats, bg="#1a1a1a");
        st_pos_f.pack(fill="x", padx=20)
        self.scale_stx = tk.Scale(st_pos_f, from_=-900, to=900, orient="horizontal", bg="#1a1a1a", fg="white",
                                  label="X Offset");
        self.scale_stx.set(st_conf.get("x", -500));
        self.scale_stx.pack(side="left", fill="x", expand=True)
        self.scale_sty = tk.Scale(st_pos_f, from_=-500, to=500, orient="horizontal", bg="#1a1a1a", fg="white",
                                  label="Y Offset");
        self.scale_sty.set(st_conf.get("y", -300));
        self.scale_sty.pack(side="left", fill="x", expand=True)

        tk.Label(tab_stats, text="Text Feinjustierung (Relativ zum Bild):", bg="#1a1a1a", fg="#ffcc00").pack(
            pady=(10, 0))
        st_adj_f = tk.Frame(tab_stats, bg="#1a1a1a");
        st_adj_f.pack(fill="x", padx=20)
        self.scale_st_tx = tk.Scale(st_adj_f, from_=-200, to=200, orient="horizontal", bg="#1a1a1a", fg="white",
                                    label="Text X");
        self.scale_st_tx.set(st_conf.get("tx", 0));
        self.scale_st_tx.pack(side="left", fill="x", expand=True)
        self.scale_st_ty = tk.Scale(st_adj_f, from_=-200, to=200, orient="horizontal", bg="#1a1a1a", fg="white",
                                    label="Text Y");
        self.scale_st_ty.set(st_conf.get("ty", 0));
        self.scale_st_ty.pack(side="left", fill="x", expand=True)

        tk.Label(tab_stats, text="Bild Skalierung:", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.scale_st_scale = tk.Scale(tab_stats, from_=0.1, to=2.0, resolution=0.05, orient="horizontal", bg="#1a1a1a",
                                       fg="#00f2ff");
        self.scale_st_scale.set(st_conf.get("scale", 1.0));
        self.scale_st_scale.pack(fill="x", padx=100)

        kf_conf = self.overlay_config.get("killfeed", {"x": -800, "y": 200})
        tk.Label(tab_stats, text="--- KILLFEED POSITION (OFFSET) ---", font=("Consolas", 12, "bold"), bg="#1a1a1a",
                 fg="#ff4444").pack(pady=(20, 5))
        kf_pos_f = tk.Frame(tab_stats, bg="#1a1a1a");
        kf_pos_f.pack(fill="x", padx=20)
        self.scale_kfx = tk.Scale(kf_pos_f, from_=-960, to=960, orient="horizontal", bg="#1a1a1a", fg="white",
                                  label="Feed X Offset");
        self.scale_kfx.set(kf_conf.get("x", -800));
        self.scale_kfx.pack(side="left", fill="x", expand=True)
        self.scale_kfy = tk.Scale(kf_pos_f, from_=-540, to=540, orient="horizontal", bg="#1a1a1a", fg="white",
                                  label="Feed Y Offset");
        self.scale_kfy.set(kf_conf.get("y", 200));
        self.scale_kfy.pack(side="left", fill="x", expand=True)

        tk.Label(tab_stats, text="Headshot Icon (PNG):", bg="#1a1a1a", fg="white").pack(pady=(15, 0))
        hs_img_f = tk.Frame(tab_stats, bg="#1a1a1a");
        hs_img_f.pack()
        self.ent_hs_icon = tk.Entry(hs_img_f, width=30, bg="#111", fg="#00f2ff");
        self.ent_hs_icon.pack(side="left");
        self.ent_hs_icon.insert(0, get_short_name(kf_conf.get("hs_icon", "headshot.png")))
        tk.Button(hs_img_f, text="...", command=lambda: self.browse_file(self.ent_hs_icon, "png"), bg="#333",
                  fg="white", width=3).pack(side="left")

        self.var_show_revives = tk.BooleanVar(value=kf_conf.get("show_revives", True))
        tk.Checkbutton(tab_stats, text="Revives im Killfeed anzeigen", variable=self.var_show_revives, bg="#1a1a1a",
                       fg="#00ff00", selectcolor="black", font=("Consolas", 10), command=self.save_stats_config).pack(
            pady=5)

        btn_box = tk.Frame(tab_stats, bg="#1a1a1a");
        btn_box.pack(pady=20)
        tk.Button(btn_box, text="SAVE ALL SETTINGS", bg="#004400", fg="white", width=20, height=2,
                  command=self.save_stats_config).pack(side="left", padx=10)

        # NEU: Drag & Drop Button für Stats/Feed
        self.btn_edit_hud = tk.Button(btn_box, text="LAYOUT PER MAUS VERSCHIEBEN", bg="#0066ff", fg="white", width=25,
                                      height=2, command=self.toggle_hud_edit_mode)
        self.btn_edit_hud.pack(side="left", padx=10)

        tk.Button(btn_box, text="TEST UI", bg="#444", fg="white", width=15, height=2,
                  command=self.test_stats_visuals).pack(side="left", padx=10)
        self.scale_st_font = tk.Scale(self.root, from_=0, to=1)

        # =========================================================
        # TAB 6: VOICE
        # =========================================================
        tab_voice = tk.Frame(self.ovl_notebook, bg="#1a1a1a")
        self.ovl_notebook.add(tab_voice, text=" AUTO V0-9 ")
        v_conf = self.overlay_config.get("auto_voice", {})
        tk.Label(tab_voice, text="AUTO VOICE MACRO CONFIG", font=("Consolas", 14, "bold"), bg="#1a1a1a",
                 fg="#00f2ff").pack(pady=15)
        tk.Label(tab_voice,
                 text="Automatically presses 'V' + Number when events occur.\nKeep 'OFF' to disable specific triggers.",
                 bg="#1a1a1a", fg="#888", font=("Consolas", 9)).pack(pady=(0, 20))
        v_grid = tk.Frame(tab_voice, bg="#1a1a1a");
        v_grid.pack()
        self.voice_vars = {}
        triggers = [("I was Revived", "revived", "Use '1' for Thanks"),
                    ("I Teamkilled someone", "tk", "Use '8' for Sorry"),
                    ("Killed Infiltrator", "kill_infil", "Tactical Callout?"),
                    ("Killed MAX Unit", "kill_max", "Taunt?"),
                    ("Killed High KD Player (>2.0)", "kill_high_kd", "V6 recommended"),
                    ("Headshot Kill", "kill_hs", "Nice Shot?")]
        opts = ["OFF"] + [str(i) for i in range(10)]
        for i, (label_text, key, hint) in enumerate(triggers):
            tk.Label(v_grid, text=label_text, font=("Consolas", 11), bg="#1a1a1a", fg="white", anchor="w",
                     width=25).grid(row=i, column=0, pady=8, padx=5)
            var = tk.StringVar(value=v_conf.get(key, "OFF"));
            self.voice_vars[key] = var
            om = tk.OptionMenu(v_grid, var, *opts);
            om.config(bg="#333", fg="#00f2ff", width=5, highlightthickness=0, bd=0);
            om["menu"].config(bg="#333", fg="white");
            om.grid(row=i, column=1, padx=10)
            tk.Label(v_grid, text=hint, font=("Arial", 8), bg="#1a1a1a", fg="#555", anchor="w").grid(row=i, column=2,
                                                                                                     padx=5)
        tk.Button(tab_voice, text="SAVE VOICE MACROS", bg="#004400", fg="white", width=20, height=2,
                  command=self.save_voice_config).pack(pady=30)

        # Notebook Packen
        self.content_ids.append(self.canvas.create_window(mid, 525, window=self.ovl_notebook, width=1100, height=700))

    def select_event_from_grid(self, event_name):
        """Wird aufgerufen, wenn man im Grid auf einen Button klickt"""
        # 1. Variable setzen (damit save_event_ui_data weiß, für wen es speichert)
        self.var_event_sel.set(event_name)

        # 2. Anzeige im UI aktualisieren (Label über den Eingabefeldern)
        if hasattr(self, 'lbl_current_edit'):
            self.lbl_current_edit.config(text=f"EDITING: {event_name.upper()}")

        # 3. Alle Daten (Pfade, Slider, Duration) in die UI-Elemente füllen
        self.load_event_ui_data(event_name)

        # Visuelles Feedback im Log
        self.add_log(f"UI: Switch Edit-Mode to '{event_name}'")

    def browse_file(self, entry_widget, type_):
        # Filter: Audio oder Bilder
        ft = [("PNG Images", "*.png")] if type_ == "png" else [("Audio Files", "*.mp3 *.wav *.ogg")]

        # 1. Datei auswählen
        file_path = filedialog.askopenfilename(filetypes=ft)

        if file_path:
            # 2. Dateinamen extrahieren
            filename = os.path.basename(file_path)

            # 3. Zielpfad im assets-Ordner bestimmen
            target_path = get_asset_path(filename)

            # 4. Datei kopieren, falls sie von woanders kommt (z.B. Desktop)
            try:
                # Prüfen ob Quelle und Ziel unterschiedlich sind, um Fehler zu vermeiden
                if os.path.abspath(file_path) != os.path.abspath(target_path):
                    shutil.copy2(file_path, target_path)
            except Exception as e:
                print(f"Kopier-Fehler: {e}")

            # 5. Nur den Dateinamen ins Textfeld eintragen!
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def load_event_ui_data(self, event_type):
        """Lädt die gespeicherten Daten in die Eingabefelder inklusive Duration"""
        if not event_type or event_type.startswith("---"):
            return

        # Daten aus der Config holen
        data = self.overlay_config.get("events", {}).get(event_type, {})

        # 1. Bildpfad laden
        self.ent_evt_img.delete(0, tk.END)
        img_val = data.get("img", "")
        self.ent_evt_img.insert(0, get_short_name(img_val))

        # 2. Soundpfad laden
        self.ent_evt_snd.delete(0, tk.END)
        snd_val = data.get("snd", "")
        self.ent_evt_snd.insert(0, get_short_name(snd_val))

        # 3. Offsets laden
        off_x = data.get("x_offset", data.get("x", 0))
        off_y = data.get("y_offset", data.get("y", 0))
        self.scale_ex.set(int(off_x))
        self.scale_ey.set(int(off_y))

        # 4. Skalierung laden
        raw_scale = data.get("scale", 1.0)
        if isinstance(raw_scale, (float, int)) and raw_scale <= 5.0:
            display_scale = int(raw_scale * 100)
        else:
            display_scale = int(raw_scale)
        self.scale_png_size.set(display_scale)

        # 5. NEU: Dauer (Duration) laden
        if hasattr(self, 'ent_evt_duration'):
            self.ent_evt_duration.delete(0, tk.END)
            # Standardwert 3000ms falls nichts gespeichert ist
            dur_val = data.get("duration", 3000)
            self.ent_evt_duration.insert(0, str(dur_val))

    def save_event_ui_data(self):
        """Speichert die Eingabefelder in die Config und stellt sicher, dass die Keys passen"""
        etype = self.var_event_sel.get()

        # Sicherstellen, dass die Struktur existiert
        if "events" not in self.overlay_config:
            self.overlay_config["events"] = {}

        # Dauer auslesen (Default 3000ms falls leer)
        try:
            raw_dur = self.ent_evt_duration.get()
            final_dur = int(raw_dur) if raw_dur else 3000
        except ValueError:
            final_dur = 3000

        # Speichern in der Overlay-Config
        self.overlay_config["events"][etype] = {
            "img": self.ent_evt_img.get(),
            "snd": self.ent_evt_snd.get(),
            "x_offset": int(self.scale_ex.get()),
            "y_offset": int(self.scale_ey.get()),
            "scale": float(self.scale_png_size.get()) / 100.0,
            "duration": final_dur  # NEU: Speichert die Millisekunden
        }

        # Synchronisiere mit der Haupt-Config
        self.config["events"] = self.overlay_config["events"]

        self.save_overlay_config()
        self.add_log(f"EVENT-SYSTEM: '{etype}' ({final_dur}ms) erfolgreich konfiguriert.")

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

        # 1. Stats Widget verstecken
        if self.overlay_win and hasattr(self.overlay_win, 'stats_bg_label'):
            self.overlay_win.stats_bg_label.hide()
            self.overlay_win.stats_text_label.hide()

        # 2. Killfeed verstecken & leeren
        if self.overlay_win and hasattr(self.overlay_win, 'feed_label'):
            self.overlay_win.feed_label.hide()
            self.overlay_win.feed_label.setText("")

        # 3. Killstreak verstecken (Bild UND Zahl) - NEU
        if self.overlay_win:
            if hasattr(self.overlay_win, 'streak_bg_label'):
                self.overlay_win.streak_bg_label.hide()
            if hasattr(self.overlay_win, 'streak_text_label'):
                self.overlay_win.streak_text_label.hide()  # <-- Das ist die Zahl!

        # Interne Zähler resetten, damit beim Neustart nicht kurz "5" aufblitzt
        self.killstreak_count = 0
        self.kill_counter = 0

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

            # --- 1. DATEN VORBEREITEN (Unverändert) ---
            if test_active:
                kills, deaths, hs, start_time = 15, 5, 6, time.time() - 3600
            else:
                my_id = self.current_character_id
                if my_id and my_id in self.session_stats:
                    s = self.session_stats[my_id]
                    kills, deaths, hs = s.get("k", 0), s.get("d", 0), s.get("hs", 0)
                    start_time = s.get("start", time.time())
                else:
                    kills, deaths, hs, start_time = 0, 0, 0, time.time()

            kd = kills / max(1, deaths)
            hsr = (hs / kills * 100) if kills > 0 else 0
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
        """Speichert und aktualisiert sofort (Fix für Positionen)"""
        raw_path = self.ent_stats_img.get()
        clean_name = get_short_name(raw_path)

        # 1. Stats Config Update
        if "stats_widget" not in self.config: self.config["stats_widget"] = {}
        self.config["stats_widget"].update({
            "active": self.var_stats_active.get(),
            "x": self.scale_stx.get(),  # Globale Position X
            "y": self.scale_sty.get(),  # Globale Position Y
            "img": clean_name,
            "tx": self.scale_st_tx.get(),  # Text Feinjustierung X
            "ty": self.scale_st_ty.get(),  # Text Feinjustierung Y (NEU)
            "scale": self.scale_st_scale.get()
        })

        # 2. Killfeed Config Update
        if "killfeed" not in self.config: self.config["killfeed"] = {}
        self.config["killfeed"].update({
            "x": self.scale_kfx.get(),
            "y": self.scale_kfy.get(),
            "hs_icon": get_short_name(self.ent_hs_icon.get()),
            "show_revives": self.var_show_revives.get()
        })

        self.save_config()
        self.add_log("SYSTEM: UI Settings saved.")

        # --- UPDATE ERZWINGEN ---
        if self.overlay_win:
            # Killfeed Position updaten (Methode muss in QtOverlay existieren!)
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
        """Ermittelt anhand des Tabs, was editiert werden soll"""
        try:
            # Hole den Index des aktuellen Tabs
            idx = self.ovl_notebook.index(self.ovl_notebook.select())
            # Hole den Text des Tabs
            tab_text = self.ovl_notebook.tab(idx, "text").strip()

            targets = []
            if "CROSSHAIR" in tab_text:
                targets = ["crosshair"]
            elif "SESSION STATS" in tab_text:
                targets = ["stats", "feed"]
            elif "KILLSTREAK" in tab_text:
                targets = ["streak"]

            return targets
        except:
            return []

    def toggle_hud_edit_mode(self):
        """Schaltet das Overlay in den Bearbeitungsmodus und aktiviert Dummys"""
        if not self.overlay_win:
            messagebox.showwarning("Fehler", "Overlay läuft nicht!")
            return

        is_editing = getattr(self, "is_hud_editing", False)

        if not is_editing:
            # --- AKTIVIEREN (Bleibt gleich) ---
            targets = self.get_current_tab_targets()
            if not targets:
                self.add_log("INFO: In diesem Tab gibt es nichts zu verschieben.")
                return

            self.is_hud_editing = True

            # Buttons Rot färben
            if hasattr(self, 'btn_edit_hud'): self.btn_edit_hud.config(text="STOP EDIT (SPEICHERN)", bg="#ff0000")
            if hasattr(self, 'btn_edit_cross'): self.btn_edit_cross.config(text="STOP EDIT (SPEICHERN)", bg="#ff0000")
            if hasattr(self, 'btn_edit_streak'): self.btn_edit_streak.config(text="STOP EDIT (SPEICHERN)", bg="#ff0000")

            # Edit-Modus im Overlay einschalten
            self.overlay_win.set_mouse_passthrough(False, active_targets=targets)
            self.add_log(f"UI: Edit-Modus für {targets} gestartet.")

            # Dummys anzeigen
            if "streak" in targets:
                self.temp_streak_backup = getattr(self, 'killstreak_count', 0)
                self.killstreak_count = 5
                self.update_streak_display()

            if "stats" in targets or "feed" in targets:
                self.is_stats_test = True
                self.refresh_ingame_overlay()

            if "crosshair" in targets:
                c_conf = self.config.get("crosshair", {})
                path = get_asset_path(c_conf.get("file", "crosshair.png"))
                self.overlay_win.update_crosshair(path, c_conf.get("size", 32), True)

        else:
            # --- DEAKTIVIEREN (Hier war der Fehler) ---
            self.is_hud_editing = False

            # 1. WICHTIG: ZUERST den Edit-Modus im Overlay beenden!
            # Damit verschwinden die grünen Rahmen und das Overlay weiß "Aha, keine Editierung mehr"
            if self.overlay_win:
                self.overlay_win.set_mouse_passthrough(True)

            # Buttons Blau färben
            if hasattr(self, 'btn_edit_hud'): self.btn_edit_hud.config(text="LAYOUT PER MAUS VERSCHIEBEN", bg="#0066ff")
            if hasattr(self, 'btn_edit_cross'): self.btn_edit_cross.config(text="LAYOUT PER MAUS VERSCHIEBEN",
                                                                           bg="#0066ff")
            if hasattr(self, 'btn_edit_streak'): self.btn_edit_streak.config(text="LAYOUT PER MAUS VERSCHIEBEN",
                                                                             bg="#0066ff")

            # 2. JETZT erst die Werte zurücksetzen
            # Da der Edit-Mode oben schon ausgeschaltet wurde, versteckt sich die Streak-Anzeige jetzt korrekt
            if hasattr(self, 'temp_streak_backup'):
                self.killstreak_count = self.temp_streak_backup
                del self.temp_streak_backup
            else:
                self.killstreak_count = 0
            self.update_streak_display()

            self.is_stats_test = False
            self.stop_overlay_logic()

            c_conf = self.config.get("crosshair", {})
            if self.overlay_win:
                self.overlay_win.update_crosshair(get_asset_path(c_conf.get("file", "")), c_conf.get("size", 32),
                                                  c_conf.get("active", True))

            self.add_log("UI: Edit-Modus AUS. Positionen gespeichert.")
            self.save_config()

    def on_overlay_tab_change(self, event):
        """Wenn Tab gewechselt wird während Edit an ist -> Edit Bereich anpassen"""
        if getattr(self, "is_hud_editing", False):
            # Wir beenden kurz den Edit Mode und starten ihn neu für den neuen Tab
            self.toggle_hud_edit_mode()  # Aus
            self.root.after(200, self.toggle_hud_edit_mode)  # An (im neuen Tab)

    def update_stats_widget_position(self):
        # Wird vom Loop erledigt, dient nur als Dummy oder Trigger für sofortigen Refresh
        self.refresh_ingame_overlay()

    def save_streak_settings(self):
        # Wir holen den Pfad aus dem Eingabefeld und kürzen ihn
        raw_path = self.ent_streak_img.get()
        clean_name = get_short_name(raw_path)

        # Speichern in der Haupt-Config
        if "streak" not in self.config:
            self.config["streak"] = {}

        self.config["streak"].update({
            "img": clean_name,
            "x": self.scale_sx.get(),
            "y": self.scale_sy.get(),
            "tx": self.scale_tx.get(),
            "ty": self.scale_ty.get(),
            "scale": self.scale_s_size.get()
        })

        self.save_config()  # Nutzt deine bestehende Speicher-Funktion
        self.add_log(f"Killstreak Design gespeichert: {clean_name}")

        # Sofortige Vorschau im PyQt-Overlay
        self.update_streak_display()

    def draw_streak_ui(self, img_path, count, config):
        """Zeichnet das Killstreak-Bild und die Zahl basierend auf der Config"""

        # 1. Wenn Count 0 ist, alles verstecken
        if count <= 0:
            self.streak_label.hide()
            self.streak_text_label.hide()
            return

        # 2. Bild laden und skalieren
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            scale = config.get("scale", 1.0)
            if not pixmap.isNull():
                # Skalieren
                w = int(pixmap.width() * scale)
                h = int(pixmap.height() * scale)
                pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)

                self.streak_label.setPixmap(pixmap)
                self.streak_label.adjustSize()

                # Position Bild (Mitte + Offset)
                scr_w = self.width()
                scr_h = self.height()

                x_off = config.get("x", 0)
                y_off = config.get("y", 100)

                img_x = (scr_w // 2) - (w // 2) + int(x_off)
                img_y = (scr_h // 2) - (h // 2) + int(y_off)

                self.streak_label.move(img_x, img_y)
                self.streak_label.show()

                # 3. Zahl positionieren (Relativ zum Bild)
                # HTML Styling für die Zahl
                self.streak_text_label.setText(
                    f"<span style='font-size: {int(40 * scale)}pt; font-family: Black Ops One; color: #ff0000; "
                    f"text-shadow: 2px 2px 0 #000;'>{count}</span>"
                )
                self.streak_text_label.adjustSize()

                tx_off = config.get("tx", 0)
                ty_off = config.get("ty", 0)

                # Mitte des Bildes berechnen
                center_img_x = img_x + (w // 2)
                center_img_y = img_y + (h // 2)

                # Zahl platzieren
                num_x = center_img_x - (self.streak_text_label.width() // 2) + int(tx_off)
                num_y = center_img_y - (self.streak_text_label.height() // 2) + int(ty_off)

                self.streak_text_label.move(num_x, num_y)
                self.streak_text_label.show()

    def update_streak_display(self):
        # Sicherheitscheck: Läuft das PyQt-Overlay?
        if not self.overlay_win:
            return

        # 1. Daten aus der Config holen
        streak_cfg = self.config.get("streak", {})
        img_name = streak_cfg.get("img", "KS_Counter.png")
        img_path = get_asset_path(img_name)

        # 2. Aktuellen Streak-Wert holen
        current_streak = getattr(self, 'killstreak_count', 0)

        # 3. Parameter für das PyQt-Fenster vorbereiten
        # Wir übergeben das komplette Config-Dict und den aktuellen Counter
        try:
            # Wir rufen eine neue Methode im Qt-Overlay auf (siehe unten)
            # Falls du die Methode noch nicht im Qt-Overlay hast, wird sie hier getriggert
            if hasattr(self.overlay_win, 'draw_streak_ui'):
                self.overlay_win.draw_streak_ui(
                    img_path,
                    current_streak,
                    streak_cfg
                )
        except Exception as e:
            self.add_log(f"Fehler beim Killstreak-Update: {e}")

    def test_streak_visuals(self):
        # Alten Wert merken
        old_c = getattr(self, 'killstreak_count', 0)

        # Test-Streak setzen
        self.killstreak_count = 5
        self.update_streak_display()

        # Nach 3 Sekunden zurücksetzen und ausblenden
        def reset_test():
            # Wert zurücksetzen
            self.killstreak_count = old_c

            if self.overlay_win:
                # KORREKTUR: Hier hieß es vorher 'streak_label', muss aber 'streak_bg_label' sein
                if hasattr(self.overlay_win, 'streak_bg_label'):
                    self.overlay_win.streak_bg_label.hide()

                if hasattr(self.overlay_win, 'streak_text_label'):
                    self.overlay_win.streak_text_label.hide()

        self.root.after(3000, reset_test)

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
        try:
            now = time.time()
            # Dein neues 5-Minuten Fenster
            timeout = 300

            # 1. Bereinigen: Nur Spieler behalten, die in den letzten 5 Min aktiv waren
            temp_active = {}
            for uid, info in self.active_players.items():
                if isinstance(info, tuple):
                    ts, fac = info
                    if now - ts < timeout:
                        temp_active[uid] = (ts, fac)

            # WICHTIG: Überschreibe die Liste mit den wirklich Aktiven
            self.active_players = temp_active

            # 2. Fraktionen neu zählen (basierend auf den 5-Minuten-Daten)
            counts = {"VS": 0, "NC": 0, "TR": 0, "NSO": 0}
            for _, fac in self.active_players.values():
                if fac in counts:
                    counts[fac] += 1

            total_pop = len(self.active_players)

            # 3. Stats für die UI aktualisieren
            self.live_stats.update(counts)
            self.live_stats["Total"] = total_pop

            # 4. Graph-Punkt setzen
            self.pop_history.pop(0)
            self.pop_history.append(total_pop)

            # 5. UI sofort erneuern
            if self.current_tab == "Dashboard":
                self.update_dashboard_elements()

        except Exception as e:
            print(f"Graph-Error: {e}")

        # Update alle 1-2 Sekunden für ein flüssiges Gefühl
        self.root.after(1000, self.update_live_graph)

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
        # 1. Zuerst das UI komplett leeren und Widgets zerstören
        self.clear_content()
        self.current_tab = "Dashboard"

        # Alte Graphen-Referenzen löschen
        if hasattr(self, 'graph_line'): del self.graph_line
        if hasattr(self, 'graph_glow'): del self.graph_glow

        # Fenstergröße setzen und Berechnung erzwingen, damit 'mid' stimmt
        self.root.geometry("1600x1000")
        self.root.update_idletasks()
        mid = self.root.winfo_width() // 2

        # 2. Haupt-Frame erstellen (WICHTIG: Er wird in clear_content jetzt mit-zerstört)
        dash_frame = tk.Frame(self.root, bg="#1a1a1a", bd=1, relief="solid", highlightbackground="#00f2ff")
        self.dash_widgets = {"frame": dash_frame, "factions": {}}

        # ================= HEADER =================
        head_frame = tk.Frame(dash_frame, bg="#1a1a1a")
        head_frame.pack(pady=15)

        header_text = f"{self.current_server_name.upper()} LIVE TELEMETRY ▾"
        self.lbl_server_title = tk.Label(head_frame, text=header_text,
                                         font=("Arial", 24, "bold"),
                                         bg="#1a1a1a", fg="#00f2ff",
                                         cursor="hand2")
        self.lbl_server_title.pack(side="left")
        self.lbl_server_title.bind("<Button-1>", self.open_server_menu)

        # 3. Canvas für den Graphen
        g_canvas = tk.Canvas(dash_frame, width=800, height=200, bg="#050505", highlightthickness=0)
        g_canvas.pack(pady=10, padx=20)
        self.dash_widgets["canvas"] = g_canvas

        self.total_players_label = tk.Label(dash_frame, text="Total Players: 0", font=("Consolas", 22, "bold"),
                                            bg="#1a1a1a", fg="#00f2ff")
        self.total_players_label.pack(pady=10)

        # 4. Fraktionen Grid
        f_frame = tk.Frame(dash_frame, bg="#111", pady=10)
        f_frame.pack(fill="x", padx=10)

        for name, color in [("TR", "#ff0000"), ("NC", "#0066ff"), ("VS", "#9900ff")]:
            f_box = tk.Frame(f_frame, bg="#1a1a1a", bd=1, relief="flat")
            f_box.pack(side="left", expand=True, fill="both", padx=5)

            tk.Label(f_box, text=name, font=("Arial", 16, "bold"), bg="#1a1a1a", fg=color).pack(pady=(5, 0))
            p_lab = tk.Label(f_box, text="0.0%", font=("Consolas", 20, "bold"), bg="#1a1a1a", fg="white")
            p_lab.pack()

            bar_bg = tk.Frame(f_box, bg="#333", height=8, width=180)
            bar_bg.pack(pady=10);
            bar_bg.pack_propagate(False)
            bar = tk.Frame(bar_bg, bg=color, height=8)
            bar.place(x=0, y=0, width=0)

            tk.Label(f_box, text="TOP PERFORMERS", font=("Arial", 10, "bold"), bg="#1a1a1a", fg="#555").pack(
                pady=(15, 0))

            list_frame = tk.Frame(f_box, bg="#1a1a1a")
            list_frame.pack(fill="x", padx=5, pady=5)

            headers = [("PLAYER", 0, 32), ("K", 1, 4), ("KPM", 2, 5), ("D", 3, 4), ("A", 4, 4), ("K/D", 5, 5),
                       ("KDA", 6, 5)]
            for text, col, width in headers:
                h_lbl = tk.Label(list_frame, text=text, font=("Consolas", 8, "bold"),
                                 bg="#141414", fg="#00f2ff", anchor="w" if col == 0 else "center", width=width)
                h_lbl.grid(row=0, column=col, sticky="nsew", padx=1)

            self.dash_widgets["factions"][name] = {"label": p_lab, "bar": bar, "list_frame": list_frame}

        # Footer
        self.dash_widgets["footer"] = tk.Label(dash_frame, text="", font=("Arial", 10), bg="#1a1a1a", fg="#00f2ff")
        self.dash_widgets["footer"].pack(pady=10)

        # Canvas-Fenster erstellen
        id_dash = self.canvas.create_window(mid, 620, window=dash_frame, width=1450, height=850)
        self.content_ids.append(id_dash)

        # Dashboard-Werte befüllen
        self.update_dashboard_elements()

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
        self.current_tab = "launcher"
        self.clear_content()
        mid = self.root.winfo_width() // 2
        CYAN = "#00f2ff"

        launcher_frame = tk.LabelFrame(self.root, text=" > GAME_START_DASHBOARD ", bg="#1e1e1e", fg=CYAN,
                                       font=("Consolas", 10), bd=1, padx=20, pady=20)

        high_box = tk.LabelFrame(launcher_frame, text=" [ Vehicle  ] ", bg="#1e1e1e", fg="#00ff00",
                                 font=("Consolas", 9), bd=1, padx=10, pady=10)
        high_box.pack(fill="x", pady=10)
        tk.Label(high_box, text="Load High Fidelity Assets & Maximum Visual Range", bg="#1e1e1e", fg="#4a6a7a",
                 font=("Consolas", 8)).pack()
        btn_high = tk.Button(high_box, text="INITIALIZE: High Settings", width=30, height=2, bg="#004400", fg="white",
                             font=("Consolas", 10, "bold"), command=lambda: self.execute_launch("high"))
        btn_high.pack(pady=5)

        low_box = tk.LabelFrame(launcher_frame, text=" [ Infantry ] ", bg="#1e1e1e", fg="#ff4444", font=("Consolas", 9),
                                bd=1, padx=10, pady=10)
        low_box.pack(fill="x", pady=10)
        tk.Label(low_box, text="Disable Shadows & Particles for Peak Framerates & Potato", bg="#1e1e1e", fg="#4a6a7a",
                 font=("Consolas", 8)).pack()
        btn_low = tk.Button(low_box, text="INITIALIZE: Low Settings", width=30, height=2, bg="#440000", fg="white",
                            font=("Consolas", 10, "bold"), command=lambda: self.execute_launch("low"))
        btn_low.pack(pady=5)

        info_text = "STATUS: SYSTEM_READY\nINTEGRITY: OPTIMAL\nTARGET_PATH: " + (
            self.ps2_dir if self.ps2_dir else "NOT_FOUND")
        tk.Label(launcher_frame, text=info_text, bg="#1e1e1e", fg="#4a6a7a", font=("Consolas", 8), justify="left").pack(
            fill="x", pady=10)

        id1 = self.canvas.create_window(mid, 350, window=launcher_frame, width=450)
        self.content_ids.append(id1)

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
        self.current_tab = "settings"
        self.clear_content()
        mid = self.root.winfo_width() // 2
        CYAN = "#00f2ff"

        conf_frame = tk.LabelFrame(self.root, text=" > SOURCE_CONFIG ", bg="#1e1e1e", fg=CYAN, font=("Consolas", 10),
                                   bd=1, padx=15, pady=15)

        tk.Label(conf_frame, text="OBS_VIDEO_DIR:", bg="#1e1e1e", fg="#4a6a7a").grid(row=0, column=0, sticky="w")
        self.folder_entry = tk.Entry(conf_frame, bg="#0a141d", fg=CYAN, width=35, bd=1, relief="flat")
        self.folder_entry.insert(0, self.config.get("watch_folder", ""))
        self.folder_entry.grid(row=0, column=1, padx=10)
        tk.Button(conf_frame, text="BROWSE", command=self.browse_folder, bg="#1a2b3c", fg=CYAN, bd=0).grid(row=0,
                                                                                                           column=2)

        tk.Label(conf_frame, text="STREAMABLE.IO EMAIL:", bg="#1e1e1e", fg="#4a6a7a").grid(row=1, column=0, sticky="w")
        self.email_entry = tk.Entry(conf_frame, bg="#0a141d", fg=CYAN, bd=1, relief="flat")
        self.email_entry.insert(0, self.config.get("email", ""))
        self.email_entry.grid(row=1, column=1, sticky="ew", pady=5, padx=10)

        tk.Label(conf_frame, text="STREAMABLE.IO PW:", bg="#1e1e1e", fg="#4a6a7a").grid(row=2, column=0, sticky="w")
        self.pw_entry = tk.Entry(conf_frame, bg="#0a141d", fg=CYAN, show="*", bd=1, relief="flat")
        self.pw_entry.insert(0, self.config.get("pw", ""))
        self.pw_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=10)

        tk.Button(conf_frame, text="LOCK SETTINGS", command=self.save_enforcer_config, bg=CYAN, fg="black",
                  font=("Consolas", 10, "bold")).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)

        id1 = self.canvas.create_window(mid, 250, window=conf_frame)

        path_box = tk.LabelFrame(self.root, text=" > GAME_DIRECTORY ", bg="#1e1e1e", fg=CYAN, font=("Consolas", 10),
                                 bd=1, padx=15, pady=15)
        path_info_frame = tk.Frame(path_box, bg="#1e1e1e")
        path_info_frame.pack(fill="x")
        tk.Label(path_info_frame, text="Pfad:", bg="#1e1e1e", fg=CYAN, font=("Consolas", 9)).pack(side="left")
        self.ps2_path_label = tk.Label(path_info_frame, text=self.ps2_dir, bg="#1e1e1e", fg="#4a6a7a",
                                       font=("Consolas", 8), wraplength=350)
        self.ps2_path_label.pack(side="left", padx=5)
        tk.Button(path_box, text="ORDNER WÄHLEN", command=self.browse_ps2_folder, bg="#1a2b3c", fg=CYAN,
                  font=("Consolas", 9, "bold")).pack(fill="x", pady=(10, 0))

        id2 = self.canvas.create_window(mid, 450, window=path_box, width=450)

        bg_box = tk.LabelFrame(self.root, text=" > UI_VISUALS ", bg="#1e1e1e", fg=CYAN, font=("Consolas", 10), bd=1,
                               padx=15, pady=15)
        tk.Button(bg_box, text="HINTERGRUND ÄNDERN", command=self.change_background_file, bg="#1a2b3c", fg=CYAN,
                  font=("Consolas", 9)).pack(fill="x")
        id3 = self.canvas.create_window(mid, 580, window=bg_box, width=450)

        self.content_ids.extend([id1, id2, id3])

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
        # Debugging
        print(f"DEBUG: Zeige Tab {getattr(self, 'current_sub_tab', 'No Tab Set')}")

        self.refresh_tab_content_base("characters")

        if not hasattr(self, 'current_sub_tab'):
            self.current_sub_tab = "Overview"

        w = self.root.winfo_width() if self.root.winfo_width() > 10 else 850
        mid = w // 2

        # --- DYNAMISCHE ÜBERSCHRIFT ---
        header = self.canvas.create_text(mid, 170, text=self.current_sub_tab.upper(),
                                         fill="#00f2ff", font=("Consolas", 18, "bold"), tags="content")
        self.content_ids.append(header)

        # --- LOG BEREICH (Ganz unten) ---
        self.log_area = scrolledtext.ScrolledText(self.root, width=85, height=8, bg="#020508", fg="#00f2ff",
                                                  font=("Consolas", 9), bd=1, relief="solid")
        log_win = self.canvas.create_window(mid, 820, window=self.log_area, tags="content")
        self.content_ids.append(log_win)

        # Daten mit Fallback abrufen
        char_info = getattr(self, 'last_char_data', {})
        if not char_info:
            print("DEBUG: Keine Charakterdaten im Speicher gefunden!")
            c_stats = {}
        else:
            c_stats = char_info.get('custom_stats', {})
            print(f"DEBUG: Gefundene Stats: {list(c_stats.keys())}")  # Zeigt in der Konsole an, was da ist

        # --- DIE WEICHE FÜR DIE INHALTE ---
        if self.current_sub_tab == "Overview":
            # 1. Charakter Suche
            search_frame = tk.Frame(self.root, bg="#111")
            self.char_search_entry = tk.Entry(search_frame, bg="#222", fg="white", width=25)
            self.char_search_entry.pack(side="left", padx=5)
            self.char_search_entry.bind("<Return>", lambda e: self.run_search(self.char_search_entry.get()))
            tk.Button(search_frame, text="SEARCH", command=lambda: self.run_search(self.char_search_entry.get()),
                      bg="#333", fg="#00f2ff").pack(side="left")
            self.content_ids.append(self.canvas.create_window(mid, 210, window=search_frame, tags="content"))

            # 2. Main Stats Container
            main_container = tk.Frame(self.root, bg="#121212", bd=1, relief="solid")

            # LINKS: GENERAL INFORMATION
            gen_col = tk.Frame(main_container, bg="#1a1a1a", padx=10, pady=10)
            gen_col.pack(side="left", fill="both", expand=True, padx=2)
            tk.Label(gen_col, text="GENERAL INFORMATION", fg="#00f2ff", bg="#1a1a1a",
                     font=("Consolas", 10, "bold")).pack(anchor="w")

            # Alle General-Felder inklusive Outfit und Time Played
            fields = [
                ("Name:", c_stats.get('name', '-')),
                ("Faction:", {"1": "VS", "2": "NC", "3": "TR", "4": "NSO"}.get(char_info.get('faction_id'), "-")),
                ("Server:", c_stats.get('server', '-')),
                ("Outfit:", c_stats.get('outfit', '-')),
                ("Rank:", c_stats.get('rank', '-')),
                ("Time Played:", c_stats.get('time_played', '-'))
            ]

            for label_text, val in fields:
                f = tk.Frame(gen_col, bg="#1a1a1a");
                f.pack(fill="x", pady=2)
                tk.Label(f, text=label_text, fg="#4a6a7a", bg="#1a1a1a", font=("Consolas", 9)).pack(side="left")
                tk.Label(f, text=val, fg="white", bg="#1a1a1a", font=("Consolas", 9, "bold")).pack(side="right")

            # --- RECHTS: STATISTICS (Lifetime & Last 30D) ---
            stats_container = tk.Frame(main_container, bg="#121212", padx=20)
            stats_container.pack(side="left", fill="both", expand=True)

            # Diese Liste steuert, welche Werte aus deinem Datenpaket angezeigt werden
            stat_groups = [
                ("LIFETIME performance", [
                    ("Kills", c_stats.get('lt_kills', '-')),
                    ("Deaths", c_stats.get('lt_deaths', '-')),
                    ("K/D", c_stats.get('lt_kd', '-')),
                    ("KPM", c_stats.get('lt_kpm', '-')),
                    ("KPH", c_stats.get('lt_kph', '-')),
                    ("SPM", c_stats.get('lt_spm', '-')),
                    ("Score", c_stats.get('lt_score', '-'))
                ]),
                ("LAST 30 DAYS", [
                    ("Kills", c_stats.get('m30_kills', '-')),
                    ("Deaths", c_stats.get('m30_deaths', '-')),
                    ("K/D", c_stats.get('m30_kd', '-')),
                    ("KPM", c_stats.get('m30_kpm', '-')),
                    ("KPH", c_stats.get('m30_kph', '-')),
                    ("SPM", c_stats.get('m30_spm', '-')),
                    ("Score", c_stats.get('m30_score', '-'))
                ])
            ]

            for title, rows in stat_groups:
                col = tk.Frame(stats_container, bg="#121212")
                col.pack(side="left", padx=20, fill="y")
                tk.Label(col, text=title, fg="#00f2ff", bg="#121212", font=("Consolas", 10, "bold")).pack(pady=(0, 10))
                for s_name, s_val in rows:
                    tk.Label(col, text=f"{s_name}:", fg="#4a6a7a", bg="#121212", font=("Consolas", 9)).pack(anchor="w")
                    # Hier wird der Wert aus c_stats (unserem Paket) ins Label geschrieben
                    tk.Label(col, text=str(s_val), fg="white", bg="#121212", font=("Consolas", 11, "bold")).pack(
                        anchor="w", pady=(0, 5))

            self.content_ids.append(
                self.canvas.create_window(mid, 460, window=main_container, width=720, height=450, tags="content"))

        elif self.current_sub_tab.lower() == "weapon stats":
            table_frame = tk.Frame(self.root, bg="#121212", bd=0)
            head_bar = tk.Frame(table_frame, bg="#1a1a1a");
            head_bar.pack(side="top", fill="x")

            cols = [("WEAPON", 30), ("KILLS", 12), ("ACC %", 10), ("HSR %", 10)]
            for text, w_val in cols:
                tk.Label(head_bar, text=text, fg="#00f2ff", bg="#1a1a1a", font=("Consolas", 10, "bold"), width=w_val,
                         anchor="w", padx=10).pack(side="left")

            canvas_area = tk.Canvas(table_frame, bg="#121212", highlightthickness=0)
            scrollbar = tk.Scrollbar(table_frame, orient="vertical", command=canvas_area.yview)
            scroll_content = tk.Frame(canvas_area, bg="#121212")
            canvas_area.create_window((0, 0), window=scroll_content, anchor="nw", width=730)
            canvas_area.configure(yscrollcommand=scrollbar.set)

            stats_to_show = getattr(self, 'last_weapon_stats', [])
            if stats_to_show:
                for i, w in enumerate(sorted(stats_to_show, key=lambda x: x.get('kills', 0), reverse=True)):
                    row_bg = "#121212" if i % 2 == 0 else "#181818"
                    row = tk.Frame(scroll_content, bg=row_bg);
                    row.pack(fill="x", expand=True)

                    kills = w.get('kills', 0)
                    acc = (w.get('hits', 0) / w.get('shots', 1) * 100) if w.get('shots', 0) > 0 else 0
                    hsr = (w.get('hs', 0) / kills * 100) if kills > 0 else 0

                    tk.Label(row, text=w.get('name', '?')[:28], fg="white", bg=row_bg, font=("Consolas", 10), width=30,
                             anchor="w", padx=10).pack(side="left")
                    tk.Label(row, text=f"{kills:,}", fg="#00f2ff", bg=row_bg, font=("Consolas", 10, "bold"), width=12,
                             anchor="w", padx=10).pack(side="left")
                    tk.Label(row, text=f"{acc:.1f}%", fg="#ffcc00", bg=row_bg, font=("Consolas", 10), width=10).pack(
                        side="left")
                    tk.Label(row, text=f"{hsr:.1f}%", fg="#ff4444", bg=row_bg, font=("Consolas", 10), width=10).pack(
                        side="left")
            else:
                tk.Label(scroll_content, text="NO DATA FOUND. SEARCH AGAIN.", fg="#4a6a7a", bg="#121212",
                         pady=50).pack()

            scroll_content.update_idletasks()
            canvas_area.config(scrollregion=canvas_area.bbox("all"))
            canvas_area.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            self.content_ids.append(
                self.canvas.create_window(mid, 450, window=table_frame, width=750, height=430, tags="content"))

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
        if os.path.exists(CHAR_FILE):
            with open(CHAR_FILE, "r") as f:
                for l in f:
                    if ":" in l: n, c = l.strip().split(":", 1); chars[n] = c
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
        self.char_var.set(name)
        cid = self.char_data.get(name, "")
        self.current_character_id = cid
        self.add_log(f"SYS: Tracking {name}")

        # --- AUTOMATISCHER SERVER-WECHSEL ---
        try:
            conn = sqlite3.connect("ps2_master.db")
            res = conn.execute("SELECT world_id FROM player_cache WHERE character_id=?", (cid,)).fetchone()
            conn.close()

            if res and res[0]:
                new_world_id = str(res[0])
                if new_world_id != str(self.current_world_id):
                    s_name = self.get_server_name_by_id(new_world_id)
                    # Wir nutzen switch_server, um Daten zu löschen und neu zu verbinden
                    self.root.after(0, lambda n=s_name, i=new_world_id: self.switch_server(n, i))
        except Exception as e:
            print(f"Auto-Switch Error: {e}")

    def load_player_backup(self):
        c = {}
        if os.path.exists(PLAYER_BACKUP):
            with open(PLAYER_BACKUP, "r", encoding="utf-8") as f:
                for l in f:
                    if ":" in l:
                        p = l.strip().split(":", 1)
                        if len(p) == 2: c[p[0]] = p[1]
        return c

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
                                if hasattr(self, 'cache_label'):
                                    conn = sqlite3.connect("ps2_master.db")
                                    count = conn.execute("SELECT COUNT(*) FROM player_cache").fetchone()[0]
                                    conn.close()
                                    self.root.after(0, lambda c=count: self.cache_label.config(
                                        text=f"Characters in db: {c}"))
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

        while True:
            try:
                # Verbindung herstellen
                async with websockets.connect(
                        uri,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=10
                ) as websocket:

                    self.websocket = websocket

                    # --- GLOBAL SUBSCRIPTION ---
                    # Wir abonnieren ALLES für ALLE Server gleichzeitig
                    msg = {
                        "service": "event",
                        "action": "subscribe",
                        "characters": ["all"],
                        "worlds": ["all"],
                        "eventNames": ["Death", "GainExperience", "PlayerLogin", "PlayerLogout", "MetagameEvent"]
                    }
                    await websocket.send(json.dumps(msg))
                    self.add_log("Websocket: GLOBAL MONITORING ACTIVE (All Servers)")

                    self.last_raw_message = None

                    async for message in websocket:
                        # Reconnect nur ausführen, wenn explizit gefordert (z.B. nach Error)
                        if getattr(self, "needs_reconnect", False):
                            self.needs_reconnect = False
                            await websocket.close()
                            break

                        if message == self.last_raw_message:
                            continue
                        self.last_raw_message = message
                        data = json.loads(message)

                        if "payload" in data:
                            p = data["payload"]
                            e_name = p.get("event_name")
                            payload_world = str(p.get("world_id", "0"))

                            ts = p.get("timestamp")
                            char_id = p.get("character_id", "0")
                            attacker_id = p.get("attacker_character_id", "0")
                            exp_id = p.get("experience_id", "0")

                            # UID gegen Duplikate (Global über alle Server hinweg)
                            uid = f"{e_name}{ts}_{char_id}{attacker_id}{exp_id}{payload_world}"
                            if hasattr(self, 'last_event_uid') and self.last_event_uid == uid:
                                continue
                            self.last_event_uid = uid

                            # =========================================================
                            # 1. PLAYER LOGIN / LOGOUT (Globaler Check)
                            # =========================================================
                            if e_name == "PlayerLogin":
                                c_id = p.get("character_id")
                                for name, saved_id in self.char_data.items():
                                    if saved_id == c_id:
                                        self.current_character_id = c_id
                                        self.root.after(0, lambda n=name: self.char_var.set(n))
                                        self.add_log(f"AUTO-TRACK: {name} eingeloggt.")

                                        # AUTO SERVER WECHSEL BEI LOGIN
                                        if payload_world != "0" and payload_world != str(self.current_world_id):
                                            s_name = self.get_server_name_by_id(payload_world)
                                            self.add_log(
                                                f"AUTO-SWITCH: Detektiert auf {s_name}. Sortiere Dashboard um...")
                                            # switch_server setzt die Filter-ID um und leert die Listen
                                            self.root.after(0,
                                                            lambda n=s_name, i=payload_world: self.switch_server(n, i))

                                        # Fraktion für Login-Overlay bestimmen
                                        faction_tag = "NSO"
                                        try:
                                            conn = sqlite3.connect("ps2_master.db")
                                            res = conn.execute(
                                                "SELECT faction_id FROM player_cache WHERE character_id=?",
                                                (c_id,)).fetchone()
                                            conn.close()
                                            if res: faction_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(res[0]),
                                                                                                        "NSO")
                                        except:
                                            pass
                                        self.root.after(0,
                                                        lambda e=f"Login {faction_tag}": self.trigger_overlay_event(e))
                                        break

                            elif e_name == "PlayerLogout":
                                if p.get("character_id") == self.current_character_id:
                                    self.current_character_id = ""
                                    self.root.after(0, lambda: self.char_var.set("WAITING FOR LOGIN..."))
                                    self.add_log("AUTO-TRACK: Charakter ausgeloggt. Warte auf Login...")

                            # =========================================================
                            # 2. DER SERVER-FILTER (Sortiert Daten für das Dashboard aus)
                            # =========================================================
                            # Alle Kampf-Daten (Kills, XP etc.) werden hier gefiltert
                            if payload_world != "0" and payload_world != str(self.current_world_id):
                                continue

                            # --- AB HIER: NUR NOCH LOGIK FÜR DEN AKTIVEN SERVER ---

                            # Stats Helper
                            def get_stat_obj(cid, tid):
                                if cid not in self.session_stats:
                                    faction_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                                    self.session_stats[cid] = {
                                        "id": cid, "name": self.name_cache.get(cid, "Searching..."),
                                        "faction": faction_name, "k": 0, "d": 0, "a": 0, "hs": 0,
                                        "start": time.time(), "last_kill_time": time.time()
                                    }
                                return self.session_stats[cid]

                            # -------------------------------------------------
                            # ALLGEMEINES TRACKING (Population Dashboard)
                            # -------------------------------------------------
                            track_id = p.get("character_id") or p.get("attacker_character_id")
                            if track_id and track_id != "0":
                                tid = p.get("team_id") or p.get("attacker_team_id")
                                f_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                                self.active_players[track_id] = (time.time(), f_name)
                                if track_id not in self.name_cache:
                                    self.id_queue.put(track_id)

                            # =========================================================
                            # EVENT: DEATH
                            # =========================================================
                            if e_name == "Death":
                                killer_id = p.get("attacker_character_id")
                                victim_id = p.get("character_id")
                                my_id = self.current_character_id
                                is_hs = (p.get("is_headshot") == "1")

                                if killer_id and killer_id != "0" and killer_id != victim_id:
                                    k_obj = get_stat_obj(killer_id, p.get("attacker_team_id"))
                                    k_obj["k"] += 1
                                    k_obj["last_kill_time"] = time.time()
                                    if is_hs: k_obj["hs"] += 1

                                if victim_id and victim_id != "0":
                                    v_obj = get_stat_obj(victim_id, p.get("team_id"))
                                    v_obj["d"] += 1

                                if my_id:
                                    # Icon Vorbereitung
                                    icon_html = ""
                                    if is_hs:
                                        hs_icon = self.config.get("killfeed", {}).get("hs_icon", "headshot.png")
                                        hs_path = get_asset_path(hs_icon).replace("\\", "/")
                                        if os.path.exists(hs_path):
                                            icon_html = f'<img src="{hs_path}" width="40" height="40" style="vertical-align: middle;">&nbsp;'

                                    # --- FALL A: ICH BIN DER KILLER ---
                                    if killer_id == my_id and victim_id != my_id:
                                        curr_time = time.time()
                                        if getattr(self, "last_victim_id", None) == victim_id and (
                                                curr_time - getattr(self, "last_victim_time", 0)) < 0.5:
                                            continue

                                        self.last_victim_id = victim_id
                                        self.last_victim_time = curr_time

                                        if p.get("attacker_team_id") == p.get("team_id"):
                                            self.trigger_auto_voice("tk")
                                            self.root.after(0, lambda: self.trigger_overlay_event("Team Kill"))
                                        else:
                                            if self.killstreak_count == 0:
                                                self.killstreak_count = 1
                                            else:
                                                self.killstreak_count += 1

                                            self.is_dead = False
                                            self.was_revived = False
                                            self.root.after(0, self.update_streak_display)

                                            if curr_time - getattr(self, "last_kill_time", 0) <= self.streak_timeout:
                                                self.kill_counter += 1
                                            else:
                                                self.kill_counter = 1
                                            self.last_kill_time = curr_time

                                            v_loadout = p.get("character_loadout_id")
                                            if is_hs: self.trigger_auto_voice("kill_hs")
                                            if v_loadout in LOADOUT_MAP["max"]: self.trigger_auto_voice("kill_max")

                                            v_name = self.name_cache.get(victim_id, "Unknown")
                                            v_tag = getattr(self, "outfit_cache", {}).get(victim_id, "")
                                            tag_display = f"[{v_tag}]"
                                            s_vic = self.session_stats.get(victim_id, {})
                                            v_kd = f"{(s_vic.get('k', 0) / max(1, s_vic.get('d', 1))):.1f}"

                                            msg = f"""<div style="font-family: 'Black Ops One', sans-serif; font-size: 19px; color: white; text-align: right;">
                                                      {icon_html}<span style="color: #888;">{tag_display} </span>{v_name} 
                                                      <span style="color: #aaa; font-size: 16px;"> ({v_kd})</span></div>"""
                                            if self.overlay_win: self.overlay_win.signals.killfeed_entry.emit(msg)
                                            self.root.after(0, lambda: self.trigger_overlay_event("Kill"))

                                    # --- FALL B: ICH BIN DAS OPFER ---
                                    elif victim_id == my_id:
                                        if self.killstreak_count > 0: self.saved_streak = self.killstreak_count
                                        self.killstreak_count = 0
                                        self.kill_counter = 0
                                        self.is_dead = True
                                        self.was_revived = False
                                        self.root.after(0, self.update_streak_display)

                                        if killer_id and killer_id != "0":
                                            k_name = self.name_cache.get(killer_id, "Unknown")
                                            k_tag = getattr(self, "outfit_cache", {}).get(killer_id, "")
                                            msg = f"""<div style="font-family: 'Black Ops One'; font-size: 19px; color: #ff4444; text-align: right;">
                                                      {icon_html}<span style="color: #888;">[{k_tag}] </span>KILLED BY {k_name}</div>"""
                                            if self.overlay_win: self.overlay_win.signals.killfeed_entry.emit(msg)

                                        self.root.after(0, lambda: self.trigger_overlay_event("Death"))

                            # =========================================================
                            # EVENT: EXPERIENCE
                            # =========================================================
                            elif e_name == "GainExperience":
                                other_id = p.get("other_id")
                                char_id = p.get("character_id")
                                my_id = self.current_character_id

                                if exp_id in ["2", "3", "371", "372"]:
                                    a_obj = get_stat_obj(char_id, p.get("team_id"))
                                    a_obj["a"] += 1

                                if exp_id in ["7", "53"]:
                                    r_obj = get_stat_obj(other_id, p.get("team_id"))
                                    if r_obj["d"] > 0: r_obj["d"] -= 1

                                if my_id and other_id == my_id:
                                    if exp_id in ["7", "53"]:
                                        self.was_revived = True
                                        self.is_dead = False
                                        if my_id in self.session_stats and self.session_stats[my_id]["d"] > 0:
                                            self.session_stats[my_id]["d"] -= 1

                                        self.killstreak_count = getattr(self, 'saved_streak', 0)
                                        self.root.after(0, self.update_streak_display)
                                        self.root.after(0, lambda: self.trigger_overlay_event("Revive Taken"))
                                        self.trigger_auto_voice("revived")

                                        if self.config.get("killfeed", {}).get("show_revives", True):
                                            m_name = self.name_cache.get(char_id, "Medic")
                                            msg = f'<div style="font-family: \'Black Ops One\'; font-size: 19px; color: white; text-align: right;"><span style="color: #00ff00;">✚ REVIVED BY </span>{m_name}</div>'
                                            if self.overlay_win: self.overlay_win.signals.killfeed_entry.emit(msg)

                                if my_id and char_id == my_id:
                                    self.myTeamId = p.get("team_id")
                                    self.myWorldID = p.get("world_id")
                                    if exp_id in ["7", "53"]:
                                        self.root.after(0, lambda: self.trigger_overlay_event("Revive Given"))
                                    else:
                                        for event_name, id_list in PS2_EXP_DETECTION.items():
                                            if exp_id in id_list:
                                                self.root.after(0, lambda e=event_name: self.trigger_overlay_event(e))
                                                break

                            # =========================================================
                            # EVENT: METAGAME
                            # =========================================================
                            elif e_name == "MetagameEvent":
                                state = p.get("metagame_event_state_name")
                                world = p.get("world_id")
                                zone = p.get("zone_id")
                                if state == "ended" and world == self.myWorldID and zone == self.currentZone:
                                    self.root.after(0, lambda: self.trigger_overlay_event("Alert End"))

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

    def add_log(self, msg):
        if hasattr(self, 'log_area'):
            self.root.after(0, lambda: [self.log_area.insert(tk.END, f"> {time.strftime('%H:%M:%S')} | {msg}\n"),
                                        self.log_area.see(tk.END)])

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
        if not self.ps2_dir or not os.path.exists(self.ps2_dir):
            self.add_log("ERR: PS2 Directory not found! Please set it in Settings.")
            return

        src = self.source_high if mode == "high" else self.source_low
        dest = os.path.join(self.ps2_dir, "UserOptions.ini")
        exe = os.path.join(self.ps2_dir, "LaunchPad.exe")

        if os.path.exists(src):
            try:
                shutil.copy2(src, dest)
                self.add_log(f"SYS: Applied {mode} configuration.")
                if os.path.exists(exe):
                    subprocess.Popen([exe])
                    self.add_log("SYS: LaunchPad triggered.")
                else:
                    self.add_log("ERR: LaunchPad.exe not found in PS2 folder.")
            except Exception as e:
                self.add_log(f"ERR: Copy failed: {e}")
        else:
            self.add_log(f"ERR: Missing {src} in app directory!")

    def run_search(self, name):
        def worker():  # Wir definieren einen internen Worker für den Thread
            try:
                self.add_log(f"SYNC: Initializing search for {name}...")

                # 1. URL definieren
                url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/character/?name.first_lower={name.lower()}&c:resolve=outfit,world,stat_history,stat"

                # 2. Basis-Abfrage
                try:
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    r = response.json()
                except requests.exceptions.Timeout:
                    self.add_log("ERROR: Census API Timeout.")
                    return
                except Exception as e:
                    self.add_log(f"ERROR: API failed: {e}")
                    return

                if not r.get('character_list'):
                    self.add_log(f"ERROR: Character '{name}' not found.")
                    return

                char_data = r['character_list'][0]
                char_id = char_data['character_id']

                # --- STATS EXTRAKTION --
                stats_history = char_data.get('stats', {}).get('stat_history', [])

                def get_robust_stat(stat_name):
                    entry = next((s for s in stats_history if s.get('stat_name') == stat_name), None)
                    if not entry: return 0, 0

                    try:
                        lt = int(entry.get('all_time', 0))
                    except:
                        lt = 0

                    recent = 0
                    raw_m = entry.get('month')
                    if raw_m and str(raw_m).strip() != "":
                        try:
                            recent = int(raw_m)
                        except:
                            pass

                    if recent == 0:
                        raw_w = entry.get('week')
                        if raw_w and str(raw_w).strip() != "":
                            try:
                                recent = int(raw_w)
                            except:
                                pass

                    if recent == 0:
                        day_data = entry.get('day')
                        if isinstance(day_data, dict):
                            recent = sum(int(v) for v in day_data.values() if str(v).isdigit())
                    return lt, recent

                # Stats berechnen
                lt_kills, m30_kills = get_robust_stat('kills')
                lt_deaths, m30_deaths = get_robust_stat('deaths')
                lt_score, m30_score = get_robust_stat('score')
                lt_time, m30_time = get_robust_stat('time')

                lt_min = lt_time / 60 if lt_time > 0 else 1
                lt_hrs = lt_time / 3600 if lt_time > 0 else 1
                m30_min = m30_time / 60 if m30_time > 0 else 1
                m30_hrs = m30_time / 3600 if m30_time > 0 else 1

                char_data['custom_stats'] = {
                    'name': char_data.get('name', {}).get('first', '-'),
                    'outfit': char_data.get('outfit', {}).get('alias', 'NONE'),
                    'server': char_data.get('world_id', '-'),
                    'rank': char_data.get('battle_rank', {}).get('value', '-'),
                    'time_played': f"{int(lt_hrs)}h",
                    'lt_kills': f"{lt_kills:,}",
                    'lt_deaths': f"{lt_deaths:,}",
                    'lt_kd': f"{(lt_kills / lt_deaths):.2f}" if lt_deaths > 0 else "0.00",
                    'lt_kpm': f"{(lt_kills / lt_min):.2f}",
                    'lt_kph': f"{(lt_kills / lt_hrs):.1f}",
                    'lt_spm': f"{int(lt_score / lt_min):,}",
                    'lt_score': f"{lt_score:,}",
                    'm30_kills': f"{m30_kills:,}",
                    'm30_deaths': f"{m30_deaths:,}",
                    'm30_kd': f"{(m30_kills / m30_deaths):.2f}" if m30_deaths > 0 else "0.00",
                    'm30_kpm': f"{(m30_kills / m30_min):.2f}",
                    'm30_kph': f"{(m30_kills / m30_hrs):.1f}",
                    'm30_spm': f"{int(m30_score / m30_min):,}",
                    'm30_score': f"{m30_score:,}"
                }

                # --- WAFFENDATEN ---
                w_url = f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/characters_weapon_stat/?character_id={char_id}&c:limit=5000"
                weapon_list = []
                temp_w = {}

                try:
                    w_r = requests.get(w_url, timeout=15)
                    w_data = w_r.json()
                    if 'characters_weapon_stat_list' in w_data:
                        for item in w_data['characters_weapon_stat_list']:
                            i_id = item.get('item_id')
                            if not i_id or i_id == "0": continue
                            if i_id not in temp_w:
                                temp_w[i_id] = {'id': i_id, 'name': f"Item {i_id}", 'kills': 0, 'vehicle_kills': 0,
                                                'shots': 0, 'hits': 0, 'hs': 0}

                            val = int(item.get('value', 0))
                            s_name = item.get('stat_name')
                            if s_name == 'weapon_kills':
                                temp_w[i_id]['kills'] += val
                            elif s_name == 'weapon_vehicle_kills':
                                temp_w[i_id]['vehicle_kills'] += val
                            elif s_name == 'weapon_fire_count':
                                temp_w[i_id]['shots'] += val
                            elif s_name == 'weapon_hit_count':
                                temp_w[i_id]['hits'] += val
                            elif s_name == 'weapon_headshots':
                                temp_w[i_id]['hs'] += val

                        relevant_items = [w for w in temp_w.values() if (w['kills'] + w['vehicle_kills']) >= 2]
                        relevant_items.sort(key=lambda x: x['kills'], reverse=True)

                        top_items = relevant_items[:100]
                        if top_items:
                            id_list = ",".join([w['id'] for w in top_items])
                            n_r = requests.get(
                                f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/item/?item_id={id_list}&c:show=item_id,name.en",
                                timeout=15)
                            name_map = {i['item_id']: i.get('name', {}).get('en', 'Unknown') for i in
                                        n_r.json().get('item_list', [])}
                            for w in top_items:
                                if w['id'] in name_map: w['name'] = name_map[w['id']]

                        ignore = ["Nano-Armor", "Repair Tool", "Medical Applicator", "Recon Device", "Shield Capacitor",
                                  "Spawn Beacon"]
                        weapon_list = [w for w in relevant_items if
                                       not any(bad.lower() in w['name'].lower() for bad in ignore)]
                except Exception as e:
                    self.add_log(f"WARN: Weapons failed: {e}")

                self.last_char_data = char_data
                self.last_weapon_stats = weapon_list
                self.root.after(0, self.show_characters)
                self.add_log("Sync completed.")

            except Exception as e:
                self.add_log(f"ERROR: {e}")
                traceback.print_exc()

        # Startet den Worker-Thread
        threading.Thread(target=worker, daemon=True).start()

    def load_weapon_data_worker(self, char_id):
        """Holt die Waffendaten im Hintergrund und speichert sie."""
        try:
            data = self.fetch_weapon_stats(char_id)
            self.last_weapon_stats = data if data else []
            self.add_log(f"SYS: {len(self.last_weapon_stats)} weapons synchronized.")
        except Exception as e:
            self.add_log(f"ERR: Worker failed: {e}")

    def fetch_weapon_stats(self, char_id):
        url = (f"https://census.daybreakgames.com/{S_ID}/get/ps2:v2/characters_weapon_stat?"
               f"character_id={char_id}&c:join=item^on:item_id^to:item_id^show:name.en&c:limit=500")
        try:
            r = requests.get(url, timeout=30)
            data = r.json()
            if 'characters_weapon_stat_list' in data:
                raw_stats = data['characters_weapon_stat_list']
                weapon_map = {}
                for s in raw_stats:
                    wid = s.get('item_id')
                    if not wid: continue
                    if wid not in weapon_map:
                        w_name = s.get('item', {}).get('name', {}).get('en', f"ID: {wid}")
                        weapon_map[wid] = {"name": w_name, "kills": 0, "hits": 0, "shots": 0, "hs": 0}

                    st_name = s.get('stat_name')
                    val = int(s.get('value', 0))
                    if st_name == 'weapon_kills':
                        weapon_map[wid]['kills'] += val
                    elif st_name == 'weapon_hit_count':
                        weapon_map[wid]['hits'] += val
                    elif st_name == 'weapon_fire_count':
                        weapon_map[wid]['shots'] += val
                    elif st_name == 'weapon_headshots':
                        weapon_map[wid]['hs'] += val

                return [v for v in weapon_map.values() if v['kills'] > 0]
        except Exception as e:
            print(f"Fetch Error: {e}")
        return []

        # --- HELFERFUNKTION FÜR METRIKEN ---
        def update_col(prefix, data):
            k = data['kills']
            d = data['deaths']
            s = data['score']
            t = data['time']  # in Sekunden

            # Berechnungen
            kd = round(k / d, 2) if d > 0 else k
            play_minutes = t / 60
            play_hours = t / 3600

            kpm = round(k / play_minutes, 2) if play_minutes > 0 else 0.0
            kph = round(k / play_hours, 2) if play_hours > 0 else 0.0
            spm = round(s / play_minutes, 2) if play_minutes > 0 else 0.0  # SPM Berechnung

            # Labels befüllen
            self.life_labels[f'{prefix}_kills'].config(text=f"{k:,}")
            self.life_labels[f'{prefix}_deaths'].config(text=f"{d:,}")
            self.life_labels[f'{prefix}_kd'].config(text=f"{kd:.2f}", fg="#00ff00" if kd >= 1.0 else "#ff4444")
            self.life_labels[f'{prefix}_kpm'].config(text=f"{kpm:.2f}")
            self.life_labels[f'{prefix}_kph'].config(text=f"{kph:.2f}")
            self.life_labels[f'{prefix}_spm'].config(text=f"{spm:.2f}")  # SPM Anzeige
            self.life_labels[f'{prefix}_score'].config(text=f"{s:,}")

        # --- UI UPDATE: RECHTE SPALTEN ---
        # Lifetime Spalte aktualisieren
        update_col("lifetime", stats_package['lt'])

        # Last 30 Days Spalte aktualisieren
        update_col("m30", stats_package['m30'])


class EnforcerHandler(FileSystemEventHandler):
    def __init__(self, gui):
        self.gui = gui

    def on_created(self, event):
        if event.src_path.lower().endswith(".mp4"):
            threading.Thread(target=self.safe_process, args=(event.src_path,), daemon=True).start()

    def safe_process(self, path):
        time.sleep(5)
        new_path = os.path.join(os.path.dirname(path), f"REPORT_{self.gui.last_killer_name}.mp4")
        try:
            os.rename(path, new_path)
            self.gui.add_log("UPLINK: Transmitting to Streamable...")
            with open(new_path, 'rb') as f:
                r = requests.post('https://api.streamable.com/upload',
                                  auth=(self.gui.config['email'], self.gui.config['pw']), files={'file': f})
                if r.status_code == 200:
                    self.gui.last_evidence_url = f"https://streamable.com/{r.json()['shortcode']}"
                    self.gui.add_log(f"LINK: {self.gui.last_evidence_url}")
                    if hasattr(self.gui, 'btn_report'):
                        self.gui.root.after(0, lambda: self.gui.btn_report.config(state="normal", bg="#ff8c00",
                                                                                  fg="black"))
        except Exception as e:
            self.gui.add_log(f"ERR: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DiorClientGUI(root)
    root.mainloop()