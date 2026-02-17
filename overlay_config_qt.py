import sys
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame, QTabWidget,
                             QCheckBox, QComboBox, QSlider, QScrollArea, QGridLayout,
                             QSizePolicy,QSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtGui import QClipboard
# NEW IMPORT
from crosshair_editor import CrosshairEditorWindow


# --- SIGNALS ---
class OverlaySignals(QObject):
    setting_changed = pyqtSignal(str, object)  # Key, Value
    test_trigger = pyqtSignal(str)  # Event Name for Test
    edit_mode_toggled = pyqtSignal(str)  # Which HUD element is being moved


# --- STYLESHEET ---
OVERLAY_STYLE = """
/* --- MAIN WINDOW & TABS --- */
QWidget#Overlay { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a1a, stop:1 #121212); 
}
QWidget#StreakContent { background-color: transparent; }

QTabWidget::pane { 
    border: 1px solid #333; 
    background-color: rgba(26, 26, 26, 0.9); 
    top: -1px; 
    border-radius: 5px;
}

QTabBar::tab { 
    background-color: #252525; 
    color: #888; 
    padding: 12px 20px; 
    min-width: 100px; 
    border: 1px solid #333; 
    border-bottom: none; 
    border-top-left-radius: 6px; 
    border-top-right-radius: 6px; 
    margin-right: 2px;
}

QTabBar::tab:selected { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2a2a, stop:1 #1a1a1a); 
    color: #00f2ff; 
    font-weight: bold; 
    border-bottom: 2px solid #00f2ff; 
}

QTabBar::tab:hover:!selected { 
    background-color: #333; 
    color: #eee; 
}

/* --- CONTAINERS & GROUPS --- */
QFrame#Group { 
    background-color: rgba(34, 34, 34, 0.6); 
    border: 1px solid #444; 
    border-radius: 8px; 
    margin: 5px; 
    padding: 10px; 
}

QLabel#Header { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 16px; 
    margin-bottom: 12px; 
    text-transform: uppercase;
}

QLabel#SubText { 
    color: #aaa; 
    font-size: 11px; 
}

/* --- INPUT FIELDS --- */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0a0a0a;
    border: 1px solid #444;
    color: #eee;
    padding: 8px;
    border-radius: 4px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus { 
    border: 1px solid #00f2ff; 
    background-color: #000; 
}

/* --- BUTTONS BASICS --- */
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333, stop:1 #222);
    border: 1px solid #444;
    color: #ddd;
    padding: 8px 18px;
    border-radius: 5px;
    font-weight: bold;
    font-size: 11px;
    outline: none;
}

QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #333);
    color: white;
    border: 1px solid #00f2ff;
}

QPushButton:pressed {
    background-color: #111;
}

/* --- SPECIAL BUTTONS --- */
QPushButton#EditBtn { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0055aa, stop:1 #003366); 
    color: white; 
    border: 1px solid #00f2ff; 
}
QPushButton#EditBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0066cc, stop:1 #004488); 
    border: 1px solid #ffffff;
}

QPushButton#TestBtn { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #222); 
    color: #eee; 
    border: 1px solid #666; 
}
QPushButton#TestBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #555, stop:1 #333); 
    color: white; 
    border: 1px solid #00f2ff; 
}

QPushButton#SaveBtn { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #008800, stop:1 #004400); 
    color: #00ff00; 
    border: 1px solid #00ff00;
}
QPushButton#SaveBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00aa00, stop:1 #005500); 
}

QPushButton#ColorBtn {
    min-width: 60px;
    border-radius: 3px;
    background-color: #440088; 
    color: white; 
    border: 1px solid #6600aa; 
    padding: 4px 8px;
}
QPushButton#ColorBtn:hover {
    background-color: #5500aa;
    border: 1px solid #00f2ff;
}

/* --- CHECKBOX & RADIO --- */
QCheckBox {
    spacing: 8px;
    color: #eee;
    font-size: 11px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    background-color: #111;
    border: 1px solid #444;
    border-radius: 4px;
}
QCheckBox::indicator:checked {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f2ff, stop:1 #0088aa);
    border: 1px solid #00f2ff;
    image: url(assets/check.png); /* Fallback to text if missing */
}
QCheckBox::indicator:hover {
    border: 1px solid #00f2ff;
}

/* --- SLIDERS --- */
QSlider::groove:horizontal {
    border: 1px solid #333;
    height: 4px;
    background: #111;
    margin: 2px 0;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00f2ff, stop:1 #0088aa);
    border: 1px solid #00f2ff;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #ffffff;
    border: 1px solid #ffffff;
}

/* --- PREVIEW BOX --- */
QLabel#PreviewBox, QLabel#AspectRatioLabel { 
    border: 2px dashed #444; 
    background-color: #000; 
    color: #555; 
    font-weight: bold;
}
"""


# --- HELPER CLASS: RESPONSIVE IMAGE LABEL ---
class AspectRatioLabel(QLabel):
    """A label that scales its image proportionally when the window size changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)  # Important so it can shrink
        self.setScaledContents(False)
        self.pixmap_cache = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 2px dashed #444; background-color: #000; color: #555;")
        self.setText("NO PREVIEW")

    def setPixmap(self, p):
        self.pixmap_cache = p
        self.update_scaled()

    def resizeEvent(self, e):
        self.update_scaled()
        super().resizeEvent(e)

    def update_scaled(self):
        if self.pixmap_cache:
            # Scale image to current label size (KeepAspectRatio)
            scaled = self.pixmap_cache.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled)
        else:
            self.setText("NO PREVIEW")


class TabStreaming(QWidget):
    def __init__(self, parent_config=None):
        super().__init__()
        self.parent_config = parent_config

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- HEADLINE ---
        head = QLabel("OBS STUDIO INTEGRATION")
        # Uses your existing style for headers
        head.setObjectName("Header")
        head.setStyleSheet("font-size: 22px; margin-bottom: 10px;")
        layout.addWidget(head)

        # --- SERVICE STATUS & PORT ---
        status_group = QFrame(objectName="Group")
        status_group.setStyleSheet("#Group { background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 10px; }")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(10)

        # Service Toggle
        self.btn_toggle_service = QPushButton("OBS SERVICE: OFF")
        self.btn_toggle_service.setCheckable(True)
        self.btn_toggle_service.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_service.setFixedHeight(45)
        self.btn_toggle_service.toggled.connect(self.on_service_toggled)
        status_layout.addWidget(self.btn_toggle_service)

        # Apply initial style
        self.update_button_style(False)

        # Port Configuration
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("HTTP Port:", styleSheet="color: #bbb; border: none;"))
        self.ent_port = QLineEdit("31337")
        self.ent_port.setFixedWidth(80)
        self.ent_port.setStyleSheet("background-color: #111; color: #fff; border: 1px solid #444; padding: 5px; border-radius: 3px;")
        self.ent_port.textChanged.connect(self.on_port_ui_update)
        self.ent_port.editingFinished.connect(self.on_port_commit)
        port_row.addWidget(self.ent_port)
        
        port_row.addWidget(QLabel("  WS Port:", styleSheet="color: #bbb; border: none;"))
        self.ent_ws_port = QLineEdit("31338")
        self.ent_ws_port.setFixedWidth(80)
        self.ent_ws_port.setStyleSheet("background-color: #111; color: #fff; border: 1px solid #444; padding: 5px; border-radius: 3px;")
        self.ent_ws_port.textChanged.connect(self.on_port_ui_update)
        self.ent_ws_port.editingFinished.connect(self.on_port_commit)
        port_row.addWidget(self.ent_ws_port)
        
        port_row.addStretch()
        status_layout.addLayout(port_row)

        layout.addWidget(status_group)

        # --- INFO GROUP ---
        info_group = QFrame(objectName="Group")
        info_group.setStyleSheet("#Group { background-color: #222; border: 1px solid #333; border-radius: 5px; }")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "If you capture Planetside with game capture, use the <b>Browser Source</b> method.<br>"
            "This renders the overlay via a local web server."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #ccc; font-size: 13px; line-height: 1.4;")
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        # --- URL SECTION ---
        url_group = QFrame(objectName="Group")
        url_layout = QHBoxLayout(url_group)

        self.lbl_url = QLabel("http://localhost:31337/")
        self.lbl_url.setStyleSheet("color: #00ff00; font-family: 'Consolas'; font-size: 18px; font-weight: bold;")

        self.btn_copy = QPushButton("COPY URL")
        self.btn_copy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Uses your button style, but with specific colors
        self.btn_copy.setStyleSheet("""
            QPushButton { background-color: #004400; color: #00ff00; border: 1px solid #006600; font-weight: bold; padding: 8px; outline: none; }
            QPushButton:hover { background-color: #006600; color: white; border: 1px solid #00ff00; }
            QPushButton:focus { border: 1px solid #006600; }
        """)
        self.btn_copy.clicked.connect(self.copy_to_clipboard)

        url_layout.addWidget(self.lbl_url)
        url_layout.addWidget(self.btn_copy)
        layout.addWidget(url_group)

        # --- INSTRUCTIONS ---
        step_group = QFrame(objectName="Group")
        step_layout = QVBoxLayout(step_group)
        step_layout.setSpacing(10)

        lbl_instr = QLabel("SETUP INSTRUCTIONS:")
        lbl_instr.setStyleSheet("color: #00f2ff; font-weight: bold; font-size: 14px;")
        step_layout.addWidget(lbl_instr)

        steps = [
            "1. Open OBS Studio.",
            "2. Add a new Source: <span style='color:#00f2ff;'>Browser</span>.",
            "3. Uncheck 'Local file'.",
            "4. Paste the URL above into the URL field.",
            "5. Set Width and Height to your screen resolution.",
            "6. Check 'Refresh browser when scene becomes active'.",
            "7. Click OK.",
            "<i>Note: If localhost doesn't work, try <b>127.0.0.1</b> instead.</i>"
        ]

        for step in steps:
            l = QLabel(step)
            l.setStyleSheet("color: #ddd; font-size: 13px;")
            step_layout.addWidget(l)

        layout.addWidget(step_group)



    def on_service_toggled(self, checked):
        self.update_button_style(checked)
        if self.parent_config:
            self.parent_config.signals.setting_changed.emit("obs_service_toggle", checked)

    def update_button_style(self, checked):
        if checked:
            self.btn_toggle_service.setText("OBS SERVICE: ON")
            self.btn_toggle_service.setStyleSheet("""
                QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 5px; border: 1px solid #006600; outline: none; font-size: 14px; }
                QPushButton:focus { border: 1px solid #006600; }
                QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }
            """)
        else:
            self.btn_toggle_service.setText("OBS SERVICE: OFF")
            self.btn_toggle_service.setStyleSheet("""
                QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 5px; border: 1px solid #660000; outline: none; font-size: 14px; }
                QPushButton:focus { border: 1px solid #660000; }
                QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }
            """)

    def on_port_ui_update(self):
        h_port = self.ent_port.text()
        self.lbl_url.setText(f"http://localhost:{h_port}/")

    def on_port_commit(self):
        h_port = self.ent_port.text()
        ws_port = self.ent_ws_port.text()
        if self.parent_config:
            ports = {
                "port": int(h_port) if h_port.isdigit() else 31337,
                "ws_port": int(ws_port) if ws_port.isdigit() else 31338
            }
            self.parent_config.signals.setting_changed.emit("obs_service_ports", ports)

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.lbl_url.text())

        # Feedback Animation (Change text)
        orig_text = self.lbl_url.text()
        self.lbl_url.setText("COPIED!")
        self.lbl_url.setStyleSheet("color: #00f2ff; font-family: 'Consolas'; font-size: 18px; font-weight: bold;")

        # Timer to reset text (uses QTimer.singleShot)
        from PyQt6.QtCore import QTimer  # Import if valid locally, else above
        QTimer.singleShot(1500, lambda: self._reset_label(orig_text))

    def _reset_label(self, text):
        self.lbl_url.setText(text)
        self.lbl_url.setStyleSheet("color: #00ff00; font-family: 'Consolas'; font-size: 18px; font-weight: bold;")


class OverlayConfigWindow(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Overlay")
        # Default size
        default_w, default_h = 1150, 780
        
        # Load last size if controller is available
        if self.controller:
            saved_size = self.controller.config.get("overlay_config_size", {})
            w = saved_size.get("width", default_w)
            h = saved_size.get("height", default_h)
            self.resize(w, h)
        else:
            self.resize(default_w, default_h)

        # Load Stylesheet directly here
        self.setStyleSheet(OVERLAY_STYLE)

        self.signals = OverlaySignals()

        layout = QVBoxLayout(self)

        # The Core: The Tab System
        self.tabs = QTabWidget()

        # --- TAB 1: IDENTITY ---
        self.tab_ident = QWidget()
        self.setup_identity_tab()
        self.tabs.addTab(self.tab_ident, " IDENTITY ")

        # --- TAB 2: EVENTS ---
        self.tab_events = QWidget()
        self.setup_events_tab()
        self.tabs.addTab(self.tab_events, " EVENTS ")

        # --- TAB 3: KILLSTREAK ---
        self.tab_streak = QWidget()
        self.setup_streak_tab()
        self.tabs.addTab(self.tab_streak, " KILLSTREAK ")

        # --- TAB 4: CROSSHAIR ---
        self.tab_cross = QWidget()
        self.setup_crosshair_tab()
        self.tabs.addTab(self.tab_cross, " CROSSHAIR ")

        # --- TAB 5: SESSION STATS ---
        self.tab_stats = QWidget()
        self.setup_stats_tab()
        self.tabs.addTab(self.tab_stats, " STATS ")

        # --- TAB 6: KILLFEED ---
        self.tab_feed = QWidget()
        self.setup_feed_tab()
        self.tabs.addTab(self.tab_feed, " KILLFEED ")

        # --- TAB 6: AUTO VOICE ---
        self.tab_voice = QWidget()
        self.setup_voice_tab()
        self.tabs.addTab(self.tab_voice, " VOICE MACROS ")

        # --- TAB 7: TWITCH CHAT (NEW) ---
        self.tab_twitch = QWidget()
        self.setup_twitch_tab()
        self.tabs.addTab(self.tab_twitch, " TWITCH CHAT ")  # New tab on the far right

        # --- [NEW] TAB 8: STREAMING / OBS ---
        # Here we use the new class instead of a setup method
        self.tab_streaming = TabStreaming(self)
        self.tabs.addTab(self.tab_streaming, " OBS / STREAM ")


        layout.addWidget(self.tabs)


    # --- TAB SETUP METHODS ---

    def setup_identity_tab(self):
        tab_layout = QVBoxLayout(self.tab_ident)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(20)

        # --- SELECTION ---
        sel_group = QFrame(objectName="Group")
        sel_layout = QVBoxLayout(sel_group)

        header = QLabel("ACTIVE TRACKING IDENTITY")
        header.setObjectName("Header")
        sel_layout.addWidget(header)
        sel_layout.addWidget(QLabel("Select the character you are currently playing.", objectName="SubText"))

        self.char_combo = QComboBox()
        self.char_combo.setMinimumWidth(300)
        sel_layout.addWidget(self.char_combo)

        self.btn_del_char = QPushButton("DELETE SELECTED")
        self.btn_del_char.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_del_char.setStyleSheet(
            "QPushButton { background: #440000; color: #ff4444; border: 1px solid #660000; outline: none; }"
            "QPushButton:hover { background: #550000; border: 1px solid #ff4444; }"
            "QPushButton:focus { border: 1px solid #660000; }"
        )
        sel_layout.addWidget(self.btn_del_char)

        layout.addWidget(sel_group)

        # --- ADD NEW ---
        add_group = QFrame(objectName="Group")
        add_layout = QVBoxLayout(add_group)

        add_header = QLabel("ADD NEW CHARACTER")
        add_header.setObjectName("Header")
        add_header.setStyleSheet("color: #ffcc00; font-size: 14px;")
        add_layout.addWidget(add_header)

        input_row = QHBoxLayout()
        self.char_input = QLineEdit()
        self.char_input.setPlaceholderText("Enter exact character name...")

        self.btn_add_char = QPushButton("ADD")
        self.btn_add_char.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add_char.setFixedWidth(80)
        self.btn_add_char.setStyleSheet(
            "QPushButton { background: #004400; color: #00ff00; font-weight: bold; border: 1px solid #006600; outline: none; }"
            "QPushButton:hover { background: #005500; border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #006600; }"
        )

        input_row.addWidget(self.char_input)
        input_row.addWidget(self.btn_add_char)
        add_layout.addLayout(input_row)

        layout.addWidget(add_group)

        # --- MASTER SWITCH ---
        master_box = QFrame(objectName="Group")
        master_box.setStyleSheet("background-color: #0f1a25; border: 1px solid #00f2ff;")
        m_layout = QVBoxLayout(master_box)
        self.check_master = QCheckBox("SYSTEM OVERLAY MASTER-SWITCH")
        self.check_master.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 16px; padding: 10px;")
        m_layout.addWidget(self.check_master)

        # --- DEBUG OVERLAY ---
        debug_group = QFrame(objectName="Group")
        debug_layout = QVBoxLayout(debug_group)
        debug_header = QLabel("DEBUG OVERLAY")
        debug_header.setObjectName("Header")
        debug_layout.addWidget(debug_header)
        debug_layout.addWidget(QLabel("Force overlay to render without the game running.", objectName="SubText"))
        self.btn_debug_overlay = QPushButton("DEBUG OVERLAY: OFF")
        self.btn_debug_overlay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_debug_overlay.setCheckable(True)
        self.btn_debug_overlay.setChecked(False)
        self.btn_debug_overlay.setFixedHeight(35)
        self.btn_debug_overlay.setStyleSheet(
            "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #660000; outline: none; }"
            "QPushButton:hover { background-color: #550000; border: 1px solid #ffcc00; }"
            "QPushButton:focus { border: 1px solid #660000; }"
        )
        debug_layout.addWidget(self.btn_debug_overlay)

        # --- SCI-FI STYLE TOGGLE ---
        debug_layout.addWidget(QLabel("Toggle the experimental sci-fi HUD style.", objectName="SubText"))
        self.btn_toggle_scifi = QPushButton("SCI-FI HUD: ON")
        self.btn_toggle_scifi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_scifi.setCheckable(True)
        self.btn_toggle_scifi.setChecked(True)
        self.btn_toggle_scifi.setFixedHeight(35)
        self.btn_toggle_scifi.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
            "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #006600; }"
        )
        debug_layout.addWidget(self.btn_toggle_scifi)

        layout.addStretch()  # Push everything up
        layout.addWidget(debug_group)
        layout.addWidget(master_box)
        
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

    def toggle_sub_container(self, widget):
        """Universal function to expand/collapse submenus."""
        is_visible = widget.isVisible()
        widget.setVisible(not is_visible)

    def setup_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- 0. SAVE SLOT BAR (Top) ---
        slot_bar = QHBoxLayout()
        slot_bar.setSpacing(6)

        lbl_slot = QLabel("PRESET:")
        lbl_slot.setStyleSheet("color: #00f2ff; font-weight: bold; font-size: 12px;")
        slot_bar.addWidget(lbl_slot)

        self.combo_event_slot = QComboBox()
        self.combo_event_slot.setMinimumWidth(180)
        self.combo_event_slot.setStyleSheet(
            "QComboBox { background-color: #0a141d; color: #00f2ff; border: 1px solid #00f2ff; padding: 6px 10px; font-weight: bold; font-size: 12px; }"
            "QComboBox:hover { border: 1px solid #33ffff; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background-color: #111; color: #eee; selection-background-color: #00f2ff; selection-color: black; }"
        )
        slot_bar.addWidget(self.combo_event_slot)

        self.btn_slot_new = QPushButton("+ NEW")
        self.btn_slot_new.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_slot_new.setFixedHeight(32)
        self.btn_slot_new.setStyleSheet(
            "QPushButton { background-color: #003300; color: #66ff66; font-weight: bold; padding: 4px 12px; border: 1px solid #006600; border-radius: 3px; outline: none; }"
            "QPushButton:hover { background-color: #004400; border: 1px solid #00ff00; color: white; }"
            "QPushButton:focus { border: 1px solid #006600; }"
        )
        slot_bar.addWidget(self.btn_slot_new)

        self.btn_slot_delete = QPushButton("DELETE")
        self.btn_slot_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_slot_delete.setFixedHeight(32)
        self.btn_slot_delete.setStyleSheet(
            "QPushButton { background-color: #330000; color: #ff6666; font-weight: bold; padding: 4px 12px; border: 1px solid #660000; border-radius: 3px; outline: none; }"
            "QPushButton:hover { background-color: #440000; border: 1px solid #ff4444; color: white; }"
            "QPushButton:focus { border: 1px solid #660000; }"
        )
        slot_bar.addWidget(self.btn_slot_delete)

        self.btn_slot_rename = QPushButton("RENAME")
        self.btn_slot_rename.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_slot_rename.setFixedHeight(32)
        self.btn_slot_rename.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #ccc; font-weight: bold; padding: 4px 12px; border: 1px solid #444; border-radius: 3px; outline: none; }"
            "QPushButton:hover { background-color: #3a3a3a; border: 1px solid #888; color: white; }"
            "QPushButton:focus { border: 1px solid #444; }"
        )
        slot_bar.addWidget(self.btn_slot_rename)

        # Visual separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(24)
        sep.setStyleSheet("color: #444;")
        slot_bar.addWidget(sep)

        self.btn_slot_import = QPushButton("⬇ IMPORT")
        self.btn_slot_import.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_slot_import.setFixedHeight(32)
        self.btn_slot_import.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #ccc; font-weight: bold; padding: 4px 12px; border: 1px solid #444; border-radius: 3px; outline: none; }"
            "QPushButton:hover { background-color: #3a3a3a; border: 1px solid #888; color: white; }"
            "QPushButton:focus { border: 1px solid #444; }"
        )
        self.btn_slot_import.setToolTip("Import a preset .zip file")
        slot_bar.addWidget(self.btn_slot_import)

        self.btn_slot_export = QPushButton("⬆ EXPORT")
        self.btn_slot_export.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_slot_export.setFixedHeight(32)
        self.btn_slot_export.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #ccc; font-weight: bold; padding: 4px 12px; border: 1px solid #444; border-radius: 3px; outline: none; }"
            "QPushButton:hover { background-color: #3a3a3a; border: 1px solid #888; color: white; }"
            "QPushButton:focus { border: 1px solid #444; }"
        )
        self.btn_slot_export.setToolTip("Export current preset as a .zip (settings + images + sounds)")
        slot_bar.addWidget(self.btn_slot_export)

        slot_bar.addStretch()
        layout.addLayout(slot_bar)

        # --- NEW: MASTER TOGGLE & GLOW ---
        master_row = QHBoxLayout()
        master_row.setSpacing(10)
        
        self.check_events_active = QCheckBox("Enable Events (Effects)")
        self.check_events_active.setChecked(True)
        self.check_events_active.setStyleSheet("color: #00ff00; font-weight: bold;")
        
        self.check_evt_glow = QCheckBox("Enable Glow")
        self.check_evt_glow.setChecked(True)
        self.check_evt_glow.setStyleSheet("color: #00f2ff;")
        
        self.btn_evt_glow_color = QPushButton("PICK")
        self.btn_evt_glow_color.setObjectName("ColorBtn")
        self.btn_evt_glow_color.setFixedHeight(28)
        self.btn_evt_glow_color.setFixedWidth(70)
        
        master_row.addWidget(self.check_events_active)
        master_row.addSpacing(20)
        master_row.addWidget(self.check_evt_glow)
        master_row.addWidget(QLabel("Glow Color:", styleSheet="color: #ddd; font-size: 11px;"))
        master_row.addWidget(self.btn_evt_glow_color)
        master_row.addStretch()
        layout.addLayout(master_row)

        # --- DEFINITION OF DROPDOWNS ---
        # Heal milestones intentionally limited to configured subset values.
        self.EXPANDABLE_EVENTS = {
            "Heal": [
                "Heal 50", "Heal 250", "Heal 500", "Heal 1000", "Heal 5000"
            ],
            "Revive Given": [
                # IMPORTANT: The names must start with "Revive Given"!
                "Revive Given 5", "Revive Given 10", "Revive Given 25", "Revive Given 50",
                "Revive Given 100", "Revive Given 500"
            ],
            "Resupply": [
                "Resupply 50", "Resupply 100", "Resupply 250", "Resupply 500", "Resupply 1000"
            ],
            "Repair": [
                "Repair 50", "Repair 250", "Repair 500", "Repair 1000", "Repair 5000"
            ],
            # NEW: Kill Subset
            "Kill": [
                "Kill Infil", "Kill Light Assault", "Kill Medic", "Kill Engineer", "Kill Heavy", "Kill MAX"
            ],
            # NEW: Death Subset
            "Death": [
                "Headshot Death",
                "Get RoadKilled"
            ],
            # NEW: Vehicle Destruction Subset (Renamed from Vehicle Kill)
            "Vehicle Destruction": [
                "Kill Flash", "Kill Sunderer", "Kill Lightning", "Kill Magrider", "Kill Vanguard", "Kill Prowler",
                "Kill Scythe", "Kill Reaver", "Kill Mosquito", "Kill Liberator", "Kill Galaxy", "Kill Valkyrie",
                "Kill Harasser", "Kill Ant", "Kill Colossus", "Kill Javelin", "Kill Dervish", "Kill Chimera",
                "Kill Corsair"
            ],
            # NEW: Gunner Vehicle Destruction Subset
            "Gunner Vehicle Destruction": [
                "Gunner Kill Flash", "Gunner Kill Sunderer", "Gunner Kill Lightning", "Gunner Kill Magrider",
                "Gunner Kill Vanguard", "Gunner Kill Prowler", "Gunner Kill Scythe", "Gunner Kill Reaver",
                "Gunner Kill Mosquito", "Gunner Kill Liberator", "Gunner Kill Galaxy", "Gunner Kill Valkyrie",
                "Gunner Kill Harasser", "Gunner Kill Ant", "Gunner Kill Colossus", "Gunner Kill Javelin",
                "Gunner Kill Dervish", "Gunner Kill Chimera", "Gunner Kill Corsair"
            ],
            "Hitmarker": [
                "Headshot Hitmarker"
            ]
        }

        # --- 1. GLOBAL CONTROLS (Top) ---
        global_ctrl_layout = QHBoxLayout()

        self.btn_queue_toggle = QPushButton("QUEUE: ON")
        self.btn_queue_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_queue_toggle.setCheckable(True)
        self.btn_queue_toggle.setChecked(True)
        self.btn_queue_toggle.setFixedHeight(40)
        self.btn_queue_toggle.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; padding: 10px; outline: none; border: 1px solid #006600; }"
            "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #006600; }"
        )
        global_ctrl_layout.addWidget(self.btn_queue_toggle)

        lbl_g_timer = QLabel("If Queue is off or no time set (ms):")
        lbl_g_timer.setStyleSheet("color: #aaa; margin-left: 15px; font-size: 11px;")
        global_ctrl_layout.addWidget(lbl_g_timer)

        self.ent_global_duration = QLineEdit("3000")
        self.ent_global_duration.setFixedWidth(60)
        self.ent_global_duration.setToolTip("How long an event is displayed when the Queue is OFF (Fallback).")
        self.ent_global_duration.setStyleSheet(
            "background-color: #0a141d; color: #00f2ff; border: 1px solid #333; padding: 5px;")
        global_ctrl_layout.addWidget(self.ent_global_duration)

        global_ctrl_layout.addStretch()

        self.btn_apply_all = QPushButton("APPLY LAYOUT TO ALL")
        self.btn_apply_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply_all.setToolTip("Copies position and scale of the current event to ALL others.")
        self.btn_apply_all.setStyleSheet(
            "QPushButton { background-color: #442200; color: #ffdddd; padding: 8px; border-radius: 4px; outline: none; border: 1px solid #553300; }"
            "QPushButton:hover { background-color: #553300; border: 1px solid #ffdddd; }"
            "QPushButton:focus { border: 1px solid #553300; }"
        )
        self.btn_apply_all.setFixedHeight(40)
        global_ctrl_layout.addWidget(self.btn_apply_all)

        layout.addLayout(global_ctrl_layout)

        # --- 2. EVENT SELECTION GRID (Middle) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #1a1a1a; border: none;")

        grid_widget = QWidget()
        grid_layout = QHBoxLayout(grid_widget)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(0, 10, 0, 10)

        # Kategorien definieren
        self.event_categories = {
            "STANDARD": ["Kill", "Headshot", "Assist", "Death", "Suicide", "Hitmarker", "Team Kill", "Team Kill Victim"],
            "VEHICLES": ["Gunner Kill", "Vehicle Destruction", "Gunner Vehicle Destruction"],
            "STREAKS": ["Squad Wiper", "Double Squad Wipe", "Squad Lead's Nightmare", "One Man Platoon"],
            "MULTI KILL": ["Double Kill", "Multi Kill", "Mega Kill", "Ultra Kill", "Monster Kill", "Ludacris Kill",
                           "Holy Shit"],
            "SPECIAL": ["Bounty Kill", "Domination", "Revenge", "Killstreak Stop", "Nade Kill",
                        "Knife Kill", "RoadKill", "Spitfire Kill"],
            "SUPPORT": ["Revive Given", "Revive Taken", "Heal", "Resupply", "Repair", "Break Construction",
                        "Mine Kill", "Squad Spawn", "Transport Assist","Sunderer Spawn"],
            "OBJECTIVES": ["Point Control", "Base Capture", "Alert End",
                           "Alert Win"],
            "SYSTEM": ["Login TR", "Login NC", "Login VS", "Login NSO"]
        }

        self.event_buttons = {}

        for cat_name, items in self.event_categories.items():
            cat_box = QFrame(objectName="Group")
            cat_box.setStyleSheet(
                "QFrame#Group { background-color: #202020; border: 1px solid #333; border-radius: 4px; }")
            cat_vbox = QVBoxLayout(cat_box)
            cat_vbox.setContentsMargins(5, 5, 5, 5)
            cat_vbox.setSpacing(2)

            lbl_cat = QLabel(cat_name)
            lbl_cat.setStyleSheet(
                "color: #00f2ff; font-weight: bold; font-size: 11px; border-bottom: 1px solid #444; padding-bottom: 4px; margin-bottom: 4px;")
            lbl_cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cat_vbox.addWidget(lbl_cat)

            for item in items:
                # Haupt-Button erstellen
                display_text = item
                if item in self.EXPANDABLE_EVENTS:
                    display_text += " ▼"

                btn = QPushButton(display_text)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setStyleSheet("""
                    QPushButton { background-color: transparent; color: #ccc; border: 1px solid transparent; padding: 3px; text-align: left; outline: none; }
                    QPushButton:hover { background-color: #00f2ff; color: black; border-radius: 2px; border: 1px solid #00f2ff; }
                    QPushButton:focus { border: 1px solid transparent; border-radius: 2px; }
                """)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _, x=item: self.select_event(x))
                cat_vbox.addWidget(btn)
                self.event_buttons[item] = btn

                # >>> AUTOMATISCHE DROPDOWN LOGIK (Heal, Revive, etc.) <<<
                if item in self.EXPANDABLE_EVENTS:
                    # 1. Container erstellen
                    sub_container = QWidget()
                    sub_layout = QVBoxLayout(sub_container)
                    sub_layout.setContentsMargins(15, 0, 0, 0)  # Einrücken
                    sub_layout.setSpacing(2)

                    # 2. Sub-Buttons aus der Liste erstellen
                    sub_items = self.EXPANDABLE_EVENTS[item]
                    for sub_item in sub_items:
                        sub_btn = QPushButton(sub_item)
                        sub_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                        sub_btn.setStyleSheet("""
                            QPushButton { background-color: transparent; color: #999; border: 1px solid transparent; padding: 2px; text-align: left; font-size: 10px; outline: none; }
                            QPushButton:hover { background-color: #00f2ff; color: black; border-radius: 2px; border: 1px solid #00f2ff; }
                            QPushButton:focus { border: 1px solid transparent; border-radius: 2px; }
                        """)
                        sub_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                        sub_btn.clicked.connect(lambda _, x=sub_item: self.select_event(x))
                        sub_layout.addWidget(sub_btn)
                        self.event_buttons[sub_item] = sub_btn  # Registrieren

                    # 3. Standardmäßig verstecken
                    sub_container.hide()
                    cat_vbox.addWidget(sub_container)

                    # 4. Haupt-Button verbindet mit Toggle-Funktion
                    # Wir nutzen partial oder lambda mit default argument, um den richtigen Container zu binden
                    btn.clicked.connect(lambda checked, c=sub_container: self.toggle_sub_container(c))
                # >>> ENDE LOGIK <<<

            cat_vbox.addStretch()
            grid_layout.addWidget(cat_box)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, 1)

        # --- 3. EDIT AREA (Bottom) ---
        edit_box = QFrame(objectName="Group")
        edit_box.setStyleSheet("QFrame#Group { background-color: #222; border-top: 2px solid #333; }")
        edit_layout = QVBoxLayout(edit_box)
        edit_layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_editing = QLabel("EDITING: NONE")
        self.lbl_editing.setStyleSheet("color: #00ff00; font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        edit_layout.addWidget(self.lbl_editing)

        # Container Split
        editor_split = QHBoxLayout()

        # LEFT: INPUTS
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 10, 0)
        input_layout.setSpacing(10)

        # Image & Sound
        io_grid = QGridLayout()
        io_grid.setSpacing(8)
        
        # --- IMAGE ROW ---
        io_grid.addWidget(QLabel("Image(s) (PNG/JPG):"), 0, 0)
        
        self.combo_evt_img = QComboBox()
        self.combo_evt_img.setEditable(True)
        self.combo_evt_img.setPlaceholderText("No file selected")
        self.combo_evt_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        io_grid.addWidget(self.combo_evt_img, 0, 1)
        
        # Button Container for Image (Browse + Delete)
        img_btns = QHBoxLayout()
        img_btns.setSpacing(2)
        
        self.btn_browse_evt_img = QPushButton("...")
        self.btn_browse_evt_img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_evt_img.setFixedWidth(40)
        self.btn_browse_evt_img.setStyleSheet("padding: 2px;")
        self.btn_browse_evt_img.setToolTip("Add Image File")
        
        self.btn_del_evt_img = QPushButton("del")
        self.btn_del_evt_img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_del_evt_img.setFixedWidth(40)
        self.btn_del_evt_img.setStyleSheet("color: #ff4444; font-weight: bold; padding: 2px;")
        self.btn_del_evt_img.setToolTip("Remove selected image")
        self.btn_del_evt_img.clicked.connect(lambda: self.combo_evt_img.removeItem(self.combo_evt_img.currentIndex()))
        
        img_btns.addWidget(self.btn_browse_evt_img)
        img_btns.addWidget(self.btn_del_evt_img)
        io_grid.addLayout(img_btns, 0, 2)

        # --- SOUND ROW ---
        io_grid.addWidget(QLabel("Sound(s) (MP3/OGG):"), 1, 0)
        
        self.combo_evt_snd = QComboBox()
        self.combo_evt_snd.setEditable(True)
        self.combo_evt_snd.setPlaceholderText("No file selected")
        self.combo_evt_snd.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        io_grid.addWidget(self.combo_evt_snd, 1, 1)
        
        # Button Container for Sound
        snd_btns = QHBoxLayout()
        snd_btns.setSpacing(2)
        
        self.btn_browse_evt_snd = QPushButton("...")
        self.btn_browse_evt_snd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_evt_snd.setFixedWidth(40)
        self.btn_browse_evt_snd.setStyleSheet("padding: 2px;")
        
        self.btn_del_evt_snd = QPushButton("del")
        self.btn_del_evt_snd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_del_evt_snd.setFixedWidth(40)
        self.btn_del_evt_snd.setStyleSheet("color: #ff4444; font-weight: bold; padding: 2px;")
        self.btn_del_evt_snd.setToolTip("Remove selected sound")
        self.btn_del_evt_snd.clicked.connect(lambda: self.combo_evt_snd.removeItem(self.combo_evt_snd.currentIndex()))

        snd_btns.addWidget(self.btn_browse_evt_snd)
        snd_btns.addWidget(self.btn_del_evt_snd)
        io_grid.addLayout(snd_btns, 1, 2)
        
        input_layout.addLayout(io_grid)

        # Scale & Duration
        sd_layout = QHBoxLayout()
        sd_layout.setSpacing(15)
        sd_layout.addWidget(QLabel("Scale:"))
        self.slider_evt_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_evt_scale.setRange(10, 300)
        self.slider_evt_scale.setValue(100)
        self.slider_evt_scale.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_scale_val = QLabel("1.00")
        self.lbl_scale_val.setStyleSheet("color: #00f2ff; font-weight: bold; font-family: Consolas;")
        self.lbl_scale_val.setFixedWidth(40)
        self.slider_evt_scale.valueChanged.connect(lambda val: self.lbl_scale_val.setText(f"{val / 100:.2f}"))
        sd_layout.addWidget(self.slider_evt_scale)
        sd_layout.addWidget(self.lbl_scale_val)
        sd_layout.addWidget(QLabel("Duration (ms):"))
        self.ent_evt_duration = QLineEdit("3000")
        self.ent_evt_duration.setFixedWidth(60)
        self.ent_evt_duration.setToolTip("If left empty or 0, the global timer is used.")
        sd_layout.addWidget(self.ent_evt_duration)
        input_layout.addLayout(sd_layout)

        # Volume
        vol_layout = QHBoxLayout()
        vol_layout.setSpacing(15)
        vol_layout.addWidget(QLabel("Volume:"))
        self.slider_evt_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_evt_vol.setRange(0, 100)
        self.slider_evt_vol.setValue(100)
        self.slider_evt_vol.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_vol_val = QLabel("100%")
        self.lbl_vol_val.setStyleSheet("color: #00f2ff; font-weight: bold; font-family: Consolas;")
        self.lbl_vol_val.setFixedWidth(40)
        self.slider_evt_vol.valueChanged.connect(lambda val: self.lbl_vol_val.setText(f"{val}%"))
        vol_layout.addWidget(self.slider_evt_vol)
        vol_layout.addWidget(self.lbl_vol_val)
        input_layout.addLayout(vol_layout)

        # CHECKBOX: Play Duplicate
        self.check_play_duplicate = QCheckBox("Play Duplicate")
        self.check_play_duplicate.setStyleSheet("color: #ddd;")
        self.check_play_duplicate.setToolTip("If enabled: Multiple identical events can be in the queue.\nIf disabled: Only one instance of this event is allowed in the queue.")
        input_layout.addWidget(self.check_play_duplicate)

        # CHECKBOX: Impact Glitch
        self.check_evt_impact = QCheckBox("Impact Glitch")
        self.check_evt_impact.setStyleSheet("color: #ddd;")
        self.check_evt_impact.setToolTip("If enabled: This event triggers the global HUD glitch impact effect.")
        input_layout.addWidget(self.check_evt_impact)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #444;")
        line.setFixedHeight(1)
        input_layout.addWidget(line)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        self.btn_edit_hud = QPushButton("MOVE UI")
        self.btn_edit_hud.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_hud.setObjectName("EditBtn")
        self.btn_edit_hud.setMinimumHeight(40)
        self.btn_edit_hud.setToolTip("Switches the overlay to Edit Mode to move the event.")
        self.btn_test_preview = QPushButton("TEST PREVIEW")
        self.btn_test_preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_preview.setObjectName("TestBtn")
        self.btn_test_preview.setMinimumHeight(40)
        self.btn_save_event = QPushButton("SAVE EVENT")
        self.btn_save_event.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_event.setObjectName("SaveBtn")
        self.btn_save_event.setMinimumHeight(40)
        btn_box.addWidget(self.btn_edit_hud)
        btn_box.addWidget(self.btn_test_preview)
        btn_box.addWidget(self.btn_save_event)
        input_layout.addLayout(btn_box)

        # RIGHT: PREVIEW
        self.lbl_event_preview = AspectRatioLabel()

        # WICHTIG: Deine Layout-Verbesserungen sind hier integriert:
        self.lbl_event_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.lbl_event_preview.setMaximumHeight(280)

        self.lbl_event_preview.setStyleSheet("border: 1px dashed #444; background-color: #151515;")
        self.lbl_event_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_event_preview.setText("PREVIEW")

        editor_split.addWidget(input_container, 55)
        editor_split.addWidget(self.lbl_event_preview, 45)
        editor_split.setAlignment(self.lbl_event_preview, Qt.AlignmentFlag.AlignCenter)

        edit_layout.addLayout(editor_split)
        layout.addWidget(edit_box, 0)

    def closeEvent(self, event):
        """Save window size on close."""
        if self.controller:
            size = self.size()
            if "overlay_config_size" not in self.controller.config:
                self.controller.config["overlay_config_size"] = {}
            
            self.controller.config["overlay_config_size"]["width"] = size.width()
            self.controller.config["overlay_config_size"]["height"] = size.height()
            
            try:
                self.controller.save_config()
            except Exception as e:
                print(f"Error saving overlay config size: {e}")
        
        super().closeEvent(event)

    def select_event(self, event_name):
        self.current_event = event_name
        self.lbl_editing.setText(f"EDITING: {event_name.upper()}")

        # Highlight logic: Reset all, then highlight selected
        default_style = """
            QPushButton { background-color: transparent; color: #ccc; border: 1px solid transparent; padding: 3px; text-align: left; outline: none; }
            QPushButton:hover { background-color: #00f2ff; color: black; border-radius: 2px; border: 1px solid #00f2ff; }
            QPushButton:focus { border: 1px solid transparent; border-radius: 2px; }
        """
        sub_default_style = """
            QPushButton { background-color: transparent; color: #999; border: 1px solid transparent; padding: 2px; text-align: left; font-size: 10px; outline: none; }
            QPushButton:hover { background-color: #00f2ff; color: black; border-radius: 2px; border: 1px solid #00f2ff; }
            QPushButton:focus { border: 1px solid transparent; border-radius: 2px; }
        """
        
        highlight_style = "background-color: #004080; color: white; border: 1px solid #0055aa; border-radius: 2px; padding: 3px; text-align: left; outline: none;"

        for name, btn in self.event_buttons.items():
            # Check if it's a main event or sub event to restore correct default style
            is_sub = False
            for sub_list in self.EXPANDABLE_EVENTS.values():
                if name in sub_list:
                    is_sub = True
                    break
            
            if name == event_name:
                btn.setStyleSheet(highlight_style)
            else:
                if is_sub:
                    btn.setStyleSheet(sub_default_style)
                else:
                    btn.setStyleSheet(default_style)

        # Load values
        cfg = self.controller.config.get("events", {}).get(event_name, {})
        
        # ... (Image, Sound, Scale, etc. loading) ...
        # (Assuming update_edit_fields_from_config calls are here or will be handled by signal)
        # We need to trigger the signal to update fields in the main window controller, 
        # OR update them here if the logic is here.
        # Wait, the previous logic sent a signal `setting_changed`.
        # Taking a look at `Dior Client.py`, it seems `on_event_selected_in_qt` updates the fields.
        
        self.signals.setting_changed.emit("event_selection", event_name)

    def update_preview_image(self, image_path):
        """Helper: Loads image into Responsive Preview-Box"""
        if image_path and os.path.exists(image_path):
            pix = QPixmap(image_path)
            self.lbl_event_preview.setPixmap(pix)
            self.lbl_event_preview.setStyleSheet("border: 2px solid #00f2ff; background-color: black;")
        else:
            self.lbl_event_preview.setText("IMG NOT FOUND")
            self.lbl_event_preview.pixmap_cache = None
            self.lbl_event_preview.update_scaled()  # Reset
            self.lbl_event_preview.setStyleSheet("border: 2px dashed #444; background-color: #000; color: #555;")

    def setup_crosshair_tab(self):
        layout = QVBoxLayout(self.tab_cross)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.check_cross = QCheckBox("Show Crosshair")
        self.check_cross.setObjectName("Header")
        layout.addWidget(self.check_cross)

        layout.addWidget(QLabel("Crosshair Image (PNG):"))
        img_layout = QHBoxLayout()
        self.cross_path = QLineEdit()
        img_layout.addWidget(self.cross_path)

        self.btn_browse_cross = QPushButton("...")
        self.btn_browse_cross.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_cross.setFixedWidth(40)
        self.btn_browse_cross.setStyleSheet("padding: 2px;")
        img_layout.addWidget(self.btn_browse_cross)
        layout.addLayout(img_layout)

        # Crosshair Size Slider
        layout.addWidget(QLabel("Crosshair Display Size:"))
        self.slider_cross_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_cross_size.setRange(8, 256)
        self.slider_cross_size.setValue(32) # Default
        self.lbl_cross_size = QLabel("32 px")
        
        # Connect slider update to label AND live update
        self.slider_cross_size.valueChanged.connect(lambda v: self.lbl_cross_size.setText(f"{v} px"))
        self.slider_cross_size.valueChanged.connect(self.trigger_live_update)
        
        # Connect text path change to live update
        self.cross_path.textChanged.connect(self.trigger_live_update)
        
        size_layout = QHBoxLayout()
        size_layout.addWidget(self.slider_cross_size)
        size_layout.addWidget(self.lbl_cross_size)
        layout.addLayout(size_layout)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        action_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_edit_cross = QPushButton("MOVE UI", objectName="EditBtn")
        self.btn_edit_cross.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_cross.setMinimumHeight(35)

        self.btn_test_cross = QPushButton("TEST UI")
        self.btn_test_cross.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_cross.setObjectName("TestBtn")
        self.btn_test_cross.setMinimumHeight(35)

        action_layout.addWidget(self.btn_edit_cross)
        action_layout.addWidget(self.btn_test_cross)
        layout.addLayout(action_layout)

        self.btn_center_cross = QPushButton("AUTO-CENTER (Middle)")
        self.btn_center_cross.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.btn_center_cross)

        self.btn_toggle_cross_shadow = QPushButton("CROSSHAIR SHADOW: OFF")
        self.btn_toggle_cross_shadow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_cross_shadow.setCheckable(True)
        layout.addWidget(self.btn_toggle_cross_shadow)

        self.btn_toggle_cross_expand = QPushButton("ADS+FIRE EXPANSION: ON")
        self.btn_toggle_cross_expand.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_cross_expand.setCheckable(True)
        self.btn_toggle_cross_expand.setChecked(True)
        self.btn_toggle_cross_expand.setToolTip(
            "If enabled: crosshair ring expands while ADS+fire is held.\n"
            "Order-gated: hold RMB first, then hold LMB."
        )
        layout.addWidget(self.btn_toggle_cross_expand)

        # --- NEW EDITOR BUTTON ---
        self.btn_open_editor = QPushButton("CROSSHAIR EDITOR")
        self.btn_open_editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_editor.setStyleSheet(
            "QPushButton { background-color: #004080; color: white; border: 1px solid #0055aa; font-weight: bold; margin-top: 10px; padding: 10px; outline: none; }"
            "QPushButton:hover { border: 1px solid #00f2ff; }"
            "QPushButton:focus { border: 1px solid #0055aa; }"
        )
        self.btn_open_editor.clicked.connect(self.open_crosshair_editor)
        layout.addWidget(self.btn_open_editor)

    def trigger_live_update(self):
        """Triggers the controller to update the crosshair immediately."""
        if self.controller and hasattr(self.controller, 'save_crosshair_settings_qt'):
            self.controller.save_crosshair_settings_qt()

    def open_crosshair_editor(self):
        """Öffnet den neuen Crosshair Editor."""
        self.editor_win = CrosshairEditorWindow()
        # Verbinde das Signal: Wenn gespeichert, Pfad update
        self.editor_win.crosshair_saved.connect(self.apply_generated_crosshair)
        self.editor_win.showFullScreen()

    def apply_generated_crosshair(self, filename, size_px=128):
        """Callback wenn der Editor speichert."""
        self.cross_path.setText(filename)
        
        # Automatisch die Größe anpassen, damit es 1:1 Pixel-Perfekt ist
        if hasattr(self, 'slider_cross_size'):
            # Block signals to prevent double update loop if needed, 
             # though simpler is just to set it.
            self.slider_cross_size.setValue(size_px)
        
        self.trigger_live_update()

    def setup_streak_tab(self):
        layout = QVBoxLayout(self.tab_streak)
        layout.setContentsMargins(10, 10, 10, 10)  # Less margin outside

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_widget.setObjectName("StreakContent")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(10)  # COMPACT: Global spacing reduced

        # --- 1. HEADER & MASTER SWITCH ---
        header_layout = QHBoxLayout()
        lbl_header = QLabel("KILLSTREAK SYSTEM")
        lbl_header.setStyleSheet("color: #00f2ff; font-weight: bold; font-size: 16px;")
        header_layout.addWidget(lbl_header)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        sw_layout = QHBoxLayout()
        # Compact Checkbox Styles
        cb_style = "QCheckBox { font-weight: bold; font-size: 11px; spacing: 5px; }"

        self.check_streak_master = QCheckBox("ENABLE KILLSTREAK SYSTEM")
        self.check_streak_master.setStyleSheet(cb_style + "QCheckBox { color: #00ff00; }")

        self.check_streak_anim = QCheckBox("ENABLE PULSE ANIMATION")
        self.check_streak_anim.setStyleSheet(cb_style + "QCheckBox { color: #ffcc00; }")
        self.check_streak_glow = QCheckBox("ENABLE GLOW")
        self.check_streak_glow.setStyleSheet(cb_style + "QCheckBox { color: #00f2ff; }")
        self.check_streak_glow.setChecked(True)

        sw_layout.addWidget(self.check_streak_master)
        sw_layout.addWidget(self.check_streak_anim)
        sw_layout.addSpacing(10)
        sw_layout.addWidget(self.check_streak_glow)
        
        sw_layout.addWidget(QLabel("Glow Color:", styleSheet="border: none; color: #ddd; font-size: 11px;"))
        self.btn_streak_glow_color = QPushButton("PICK")
        self.btn_streak_glow_color.setObjectName("ColorBtn")
        self.btn_streak_glow_color.setFixedHeight(28)
        self.btn_streak_glow_color.setFixedWidth(70)
        sw_layout.addWidget(self.btn_streak_glow_color)
        sw_layout.addStretch()
        
        main_layout.addLayout(sw_layout)

        # --- 2. MAIN VISUALS ---
        vis_group = QFrame()
        # COMPACT: Reduced padding
        vis_group.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 5px;")
        vis_layout = QVBoxLayout(vis_group)
        vis_layout.setSpacing(5)  # COMPACT: Spacing within group

        vis_layout.addWidget(QLabel("MAIN BACKGROUND & ANIMATION",
                                    styleSheet="color: #00f2ff; font-weight:bold; font-size: 11px; border: none; margin-bottom: 2px;"))

        img_row = QHBoxLayout()
        img_row.setContentsMargins(0, 0, 0, 0)
        img_row.addWidget(QLabel("Main Image:", styleSheet="border: none; color: #ddd;"))
        self.ent_streak_img = QLineEdit("KS_Counter.png")
        self.ent_streak_img.setStyleSheet("background-color: #111; color: #eee; border: 1px solid #444; padding: 3px;")

        self.btn_browse_streak_img = QPushButton("...")
        self.btn_browse_streak_img.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_streak_img.setFixedWidth(40)
        self.btn_browse_streak_img.setStyleSheet(
            "QPushButton { background-color: #333; color: white; border: 1px solid #555; padding: 2px; outline: none; }"
            "QPushButton:hover { border: 1px solid #00f2ff; }"
            "QPushButton:focus { border: 1px solid #555; }"
        )

        img_row.addWidget(self.ent_streak_img)
        img_row.addWidget(self.btn_browse_streak_img)
        vis_layout.addLayout(img_row)

        speed_row = QHBoxLayout()
        speed_row.setContentsMargins(0, 0, 0, 0)
        speed_row.addWidget(QLabel("Pulse Speed:", styleSheet="border: none; color: #ddd;"))
        self.ent_streak_speed = QLineEdit("50")
        self.ent_streak_speed.setFixedWidth(50)
        self.ent_streak_speed.setStyleSheet(
            "background-color: #111; color: #eee; border: 1px solid #444; padding: 3px;")
        speed_row.addWidget(self.ent_streak_speed)

        lbl_info = QLabel("(Higher = Faster)")
        lbl_info.setStyleSheet("color: #666; font-size: 10px; margin-left: 5px; border: none;")
        speed_row.addWidget(lbl_info)
        speed_row.addStretch()
        vis_layout.addLayout(speed_row)
        main_layout.addWidget(vis_group)

        # --- 3. FACTION KNIVES ---
        knife_group = QFrame()
        knife_group.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 5px;")
        knife_layout = QVBoxLayout(knife_group)
        knife_layout.setSpacing(2)  # Very tight

        lbl_knife = QLabel("FACTION KNIVES / ICONS (PNG)")
        lbl_knife.setStyleSheet("color: #00f2ff; font-weight:bold; font-size: 11px; border: none;")
        knife_layout.addWidget(lbl_knife)

        self.knife_inputs = {}
        self.knife_browse_btns = {}

        for faction in ["TR", "NC", "VS"]:
            f_row = QHBoxLayout()
            f_row.setContentsMargins(0, 0, 0, 0)
            f_row.addWidget(QLabel(f"{faction}:", styleSheet="border: none; color: #ddd; min-width: 30px;"))
            line_edit = QLineEdit()
            line_edit.setStyleSheet("background-color: #111; color: #eee; border: 1px solid #444; padding: 3px;")

            btn_browse = QPushButton("...")
            btn_browse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_browse.setFixedWidth(40)
            btn_browse.setStyleSheet(
                "QPushButton { background-color: #333; color: white; border: 1px solid #555; padding: 2px; outline: none; }"
                "QPushButton:hover { border: 1px solid #00f2ff; }"
                "QPushButton:focus { border: 1px solid #555; }"
            )

            f_row.addWidget(line_edit)
            f_row.addWidget(btn_browse)
            knife_layout.addLayout(f_row)

            self.knife_inputs[faction] = line_edit
            self.knife_browse_btns[faction] = btn_browse

        main_layout.addWidget(knife_group)

        # --- 4. PATH RECORDING ---
        path_group = QFrame()
        path_group.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 5px;")
        path_layout = QVBoxLayout(path_group)
        path_layout.setSpacing(5)

        lbl_path = QLabel("CUSTOM PATH RECORDING")
        lbl_path.setStyleSheet("color: #ff8c00; font-weight:bold; font-size: 11px; border: none;")
        path_layout.addWidget(lbl_path)

        path_desc = QLabel(
            "1. Click 'REC PATH'. 2. Click points on screen. 3. Press SPACE to stop.")
        path_desc.setStyleSheet("color: #888; font-size: 10px; font-style: italic; border: none;")
        path_layout.addWidget(path_desc)

        btn_path_row = QHBoxLayout()
        btn_path_row.setContentsMargins(0, 0, 0, 0)

        self.btn_path_record = QPushButton("REC PATH")
        self.btn_path_record.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_path_record.setObjectName("RecordBtn")
        self.btn_path_record.setProperty("recording", "false")
        self.btn_path_record.setStyleSheet("""
            QPushButton { 
                background-color: #883300; 
                color: white; 
                border: 1px solid #aa4400; 
                border-radius: 4px;
                font-size: 11px;
                padding: 6px 10px;
                outline: none;
            }
            QPushButton:focus { border: 1px solid #aa4400; }
            QPushButton:hover { 
                background-color: #aa4400; 
                border: 2px solid #ff0000; /* Force Bright Red Outline */
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #aa4400;
                border: 1px solid #ff0000;
            }
            QPushButton[recording="true"] {
                background-color: #ff0000;
                color: white;
                font-weight: bold;
                border: 1px solid #cc0000;
                outline: none;
            }
            QPushButton[recording="true"]:hover {
                background-color: #ff3333;
                border: 2px solid #ffffff; /* FORCE WHITE OUTLINE */
            }
            QPushButton[recording="true"]:pressed {
                background-color: #ff0000;
                border-color: #ff6666;
            }
        """)

        self.btn_path_clear = QPushButton("CLEAR PATH")
        self.btn_path_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_path_clear.setObjectName("TestBtn")
        self.btn_path_clear.setStyleSheet("""
            QPushButton { 
                background-color: #333; 
                color: #eee; 
                border: 1px solid #555; 
                font-size: 12px;
                border-radius: 4px;
                padding: 6px 10px;
                outline: none;
            }
            QPushButton:focus { border: 1px solid #555; }
            QPushButton:hover { 
                background-color: #444; 
                border: 1px solid #00f2ff !important;
                color: #ffffff !important;
            }
        """)

        btn_path_row.addWidget(self.btn_path_record)
        btn_path_row.addWidget(self.btn_path_clear)
        path_layout.addLayout(btn_path_row)
        main_layout.addWidget(path_group)

        # KNIFE TOGGLE BUTTON
        self.btn_toggle_knives = QPushButton("KNIFE ICONS: ON")
        self.btn_toggle_knives.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_knives.setCheckable(True)
        self.btn_toggle_knives.setChecked(True)
        self.btn_toggle_knives.setFixedHeight(35)
        # Standard-Style (Grün = An)
        self.btn_toggle_knives.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; border: 1px solid #006600; outline: none; }"
            "QPushButton:hover { border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #006600; }"
        )
        main_layout.addWidget(self.btn_toggle_knives)

        # --- 5. POSITION & SCALE ---
        pos_group = QFrame()
        pos_group.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 5px;")
        pos_layout = QGridLayout(pos_group)
        pos_layout.setSpacing(5)

        lbl_pos = QLabel("POSITION & DESIGN")
        lbl_pos.setStyleSheet("color: #00f2ff; font-weight:bold; font-size: 11px; border: none;")
        pos_layout.addWidget(lbl_pos, 0, 0, 1, 3)

        pos_layout.addWidget(QLabel("Offset X:", styleSheet="border:none; color:#ddd;"), 1, 0)
        self.slider_tx = QSlider(Qt.Orientation.Horizontal)
        self.slider_tx.setRange(-200, 200)
        # Make slider compact (limit height)
        self.slider_tx.setFixedHeight(15)
        pos_layout.addWidget(self.slider_tx, 1, 1, 1, 2)

        pos_layout.addWidget(QLabel("Offset Y:", styleSheet="border:none; color:#ddd;"), 2, 0)
        self.slider_ty = QSlider(Qt.Orientation.Horizontal)
        self.slider_ty.setRange(-200, 200)
        self.slider_ty.setFixedHeight(15)
        pos_layout.addWidget(self.slider_ty, 2, 1, 1, 2)

        pos_layout.addWidget(QLabel("Scale:", styleSheet="border:none; color:#ddd;"), 3, 0)
        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(10, 300)
        self.slider_scale.setValue(100)
        self.slider_scale.setFixedHeight(15)
        pos_layout.addWidget(self.slider_scale, 3, 1, 1, 2)

        pos_layout.addWidget(QLabel("Style:", styleSheet="border:none; color:#ddd;"), 4, 0)

        design_box = QHBoxLayout()
        design_box.setContentsMargins(0, 0, 0, 0)

        self.btn_pick_color = QPushButton("PICK")
        self.btn_pick_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_pick_color.setFixedWidth(70)
        self.btn_pick_color.setFixedHeight(28)
        self.btn_pick_color.setObjectName("ColorBtn")

        self.slider_font_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_font_size.setRange(10, 150)
        self.slider_font_size.setValue(26)
        self.slider_font_size.setFixedWidth(100)
        self.slider_font_size.setFixedHeight(15)

        design_box.addWidget(self.btn_pick_color)
        design_box.addWidget(QLabel("Size:", styleSheet="border:none; color:#ddd; margin-left:10px; font-size: 11px;"))
        design_box.addWidget(self.slider_font_size)
        design_box.addStretch()

        pos_layout.addLayout(design_box, 4, 1, 1, 2)
        main_layout.addWidget(pos_group)

        # --- 6. ACTION BUTTONS ---
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        action_layout.setContentsMargins(0, 5, 0, 0)  # Only little margin at top

        # 1. MOVE UI (Blue)
        self.btn_edit_streak = QPushButton("MOVE UI")
        self.btn_edit_streak.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_streak.setMinimumHeight(35)
        self.btn_edit_streak.setObjectName("EditBtn")

        # 2. TEST ANIMATION (Grey)
        self.btn_test_streak = QPushButton("TEST")
        self.btn_test_streak.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_streak.setMinimumHeight(35)
        self.btn_test_streak.setObjectName("TestBtn")

        # 3. SAVE SETTINGS (Green)
        self.btn_save_streak = QPushButton("SAVE SETTINGS")
        self.btn_save_streak.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_streak.setMinimumHeight(35)
        self.btn_save_streak.setObjectName("SaveBtn")

        action_layout.addWidget(self.btn_edit_streak)
        action_layout.addWidget(self.btn_test_streak)
        action_layout.addWidget(self.btn_save_streak)

        main_layout.addLayout(action_layout)
        main_layout.addStretch()

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def setup_stats_tab(self):
        tab_layout = QVBoxLayout(self.tab_stats)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ==========================================
        # 1. SESSION STATS WIDGET
        # ==========================================
        stats_group = QFrame(objectName="Group")
        st_layout = QVBoxLayout(stats_group)

        st_header = QLabel("--- SESSION STATS WIDGET ---")
        st_header.setObjectName("Header")
        st_layout.addWidget(st_header)

        # --- STATS TOGGLE BUTTON (Moved here) ---
        self.btn_toggle_stats = QPushButton("STATS WIDGET: ON")
        self.btn_toggle_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_stats.setFixedHeight(40)
        self.btn_toggle_stats.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; }"
            "QPushButton:hover { background-color: #005500; }"
            "QPushButton:focus { border: 1px solid #00ff00; }"
        )
        st_layout.addWidget(self.btn_toggle_stats)

        # Text Adjustments
        lbl_adj = QLabel("Text Adjust Number:")
        lbl_adj.setStyleSheet("color: #ffcc00;")
        st_layout.addWidget(lbl_adj)
        adj_grid = QGridLayout()

        adj_grid.addWidget(QLabel("Text X:"), 0, 0)
        self.slider_st_tx = QSlider(Qt.Orientation.Horizontal)
        self.slider_st_tx.setRange(-200, 200)
        adj_grid.addWidget(self.slider_st_tx, 0, 1)

        adj_grid.addWidget(QLabel("Text Y:"), 1, 0)
        self.slider_st_ty = QSlider(Qt.Orientation.Horizontal)
        self.slider_st_ty.setRange(-200, 200)
        adj_grid.addWidget(self.slider_st_ty, 1, 1)

        st_layout.addLayout(adj_grid)

        # TOGGLES FOR INDIVIDUAL STATS
        st_layout.addWidget(QLabel("Visible Stats:", styleSheet="color: #ffcc00; font-weight:bold;"))
        toggle_grid = QGridLayout()
        toggle_grid.setContentsMargins(10, 0, 10, 10)
        
        self.check_show_k = QCheckBox("Kills")   ; self.check_show_k.setStyleSheet("color: #00ff00;")
        self.check_show_d = QCheckBox("Deaths")  ; self.check_show_d.setStyleSheet("color: #00ff00;")
        self.check_show_hsr = QCheckBox("HSR")   ; self.check_show_hsr.setStyleSheet("color: #00ff00;")
        self.check_show_kpm = QCheckBox("KPM")   ; self.check_show_kpm.setStyleSheet("color: #00ff00;")
        self.check_show_kph = QCheckBox("KPH")   ; self.check_show_kph.setStyleSheet("color: #00ff00;")
        self.check_show_time = QCheckBox("Time") ; self.check_show_time.setStyleSheet("color: #00ff00;")
        self.check_show_dhsr = QCheckBox("DHSR") ; self.check_show_dhsr.setStyleSheet("color: #00ff00;")
        self.check_show_kd = QCheckBox("KD")     ; self.check_show_kd.setStyleSheet("color: #00ff00;")

        toggle_grid.addWidget(self.check_show_k, 0, 0)
        toggle_grid.addWidget(self.check_show_d, 0, 1)
        toggle_grid.addWidget(self.check_show_hsr, 0, 2)
        toggle_grid.addWidget(self.check_show_kpm, 1, 0)
        toggle_grid.addWidget(self.check_show_kph, 1, 1)
        toggle_grid.addWidget(self.check_show_time, 1, 2)
        toggle_grid.addWidget(self.check_show_dhsr, 2, 0)
        toggle_grid.addWidget(self.check_show_kd, 2, 1)
        
        st_layout.addLayout(toggle_grid)

        # FONT SIZE (STATS)
        st_fs_layout = QHBoxLayout()
        st_fs_layout.addWidget(QLabel("Font Size:"))
        self.combo_st_font = QComboBox()
        self.combo_st_font.addItems(["8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72", "100"])
        self.combo_st_font.setCurrentText("22")
        st_fs_layout.addWidget(self.combo_st_font)
        
        st_fs_layout.addSpacing(15)
        
        # COLORS (STATS)
        st_fs_layout.addWidget(QLabel("Label Color:"))
        self.btn_stats_label_color = QPushButton("PICK")
        self.btn_stats_label_color.setObjectName("ColorBtn")
        self.btn_stats_label_color.setFixedHeight(28)
        self.btn_stats_label_color.setToolTip("Color for the labels (e.g. 'KD', 'HSR')")
        st_fs_layout.addWidget(self.btn_stats_label_color)

        st_fs_layout.addWidget(QLabel("Value Color:"))
        self.btn_stats_value_color = QPushButton("PICK")
        self.btn_stats_value_color.setObjectName("ColorBtn")
        self.btn_stats_value_color.setFixedHeight(28)
        self.btn_stats_value_color.setToolTip("Default color for values")
        st_fs_layout.addWidget(self.btn_stats_value_color)
        
        self.check_stats_glow = QCheckBox("Stats Glow")
        self.check_stats_glow.setStyleSheet("color: #00ff00;")
        self.check_stats_glow.setChecked(True)
        st_fs_layout.addWidget(self.check_stats_glow)
        
        st_fs_layout.addWidget(QLabel("Glow Color:"))
        self.btn_stats_glow_color = QPushButton("PICK")
        self.btn_stats_glow_color.setObjectName("ColorBtn")
        self.btn_stats_glow_color.setFixedHeight(28)
        self.btn_stats_glow_color.setFixedWidth(70)
        st_fs_layout.addWidget(self.btn_stats_glow_color)
        
        st_fs_layout.addStretch()
        st_layout.addLayout(st_fs_layout)

        layout.addWidget(stats_group)

        # ==========================================
        # 3. ACTION BUTTONS (Bottom)
        # ==========================================
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.setContentsMargins(0, 15, 0, 0)

        # Here only Edit, Test, Save (no live buttons anymore)
        self.btn_edit_hud_stats = QPushButton("MOVE UI")
        self.btn_edit_hud_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_hud_stats.setObjectName("EditBtn")
        self.btn_edit_hud_stats.setMinimumHeight(35)

        self.btn_test_stats = QPushButton("TEST UI")
        self.btn_test_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_stats.setObjectName("TestBtn")
        self.btn_test_stats.setMinimumHeight(35)

        self.btn_save_stats = QPushButton("SAVE SETTINGS")
        self.btn_save_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_stats.setObjectName("SaveBtn")
        self.btn_save_stats.setMinimumHeight(35)

        btn_box.addWidget(self.btn_edit_hud_stats)
        btn_box.addWidget(self.btn_test_stats)
        btn_box.addWidget(self.btn_save_stats)

        layout.addLayout(btn_box)
        
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)
        layout.addStretch()

    def setup_feed_tab(self):
        tab_layout = QVBoxLayout(self.tab_feed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ==========================================
        # KILLFEED
        # ==========================================
        feed_group = QFrame(objectName="Group")
        kf_layout = QVBoxLayout(feed_group)

        kf_header = QLabel("--- KILLFEED ---")
        kf_header.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 16px;")
        kf_layout.addWidget(kf_header)

        # --- KILLFEED TOGGLE BUTTON ---
        self.btn_toggle_feed = QPushButton("KILLFEED: ON")
        self.btn_toggle_feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_feed.setFixedHeight(40)
        self.btn_toggle_feed.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
            "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #00ff00; }"
        )
        kf_layout.addWidget(self.btn_toggle_feed)

        # Headshot Icon
        kf_layout.addWidget(QLabel("Headshot Icon (PNG):", objectName="SubText"))
        hs_h = QHBoxLayout()
        self.ent_hs_icon = QLineEdit()
        self.btn_browse_hs_icon = QPushButton("...")
        self.btn_browse_hs_icon.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_hs_icon.setFixedWidth(40)
        self.btn_browse_hs_icon.setStyleSheet("padding: 2px;")

        hs_h.addWidget(self.ent_hs_icon)
        hs_h.addWidget(self.btn_browse_hs_icon)
        kf_layout.addLayout(hs_h)

        # Revive Checkbox
        self.check_show_revives = QCheckBox("Show Revives in Feed")
        self.check_show_revives.setStyleSheet("color: #00ff00;")
        kf_layout.addWidget(self.check_show_revives)

        self.check_show_gunner = QCheckBox("Show Gunner Kills in Feed")
        self.check_show_gunner.setStyleSheet("color: #00ff00;")
        kf_layout.addWidget(self.check_show_gunner)

        self.check_show_vehicle = QCheckBox("Show Vehicle Kills in Feed")
        self.check_show_vehicle.setStyleSheet("color: #00ff00;")
        kf_layout.addWidget(self.check_show_vehicle)

        # Auto remove / lifetime
        feed_ttl_layout = QHBoxLayout()
        self.check_feed_auto_remove = QCheckBox("Auto-remove feed lines")
        self.check_feed_auto_remove.setStyleSheet("color: #00ff00;")
        self.check_feed_auto_remove.setChecked(True)
        self.check_feed_auto_remove.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        feed_ttl_layout.addWidget(self.check_feed_auto_remove)
        feed_ttl_layout.addStretch()
        lbl_feed_stay = QLabel("Stay (sec):")
        lbl_feed_stay.setStyleSheet("color: #ddd;")
        feed_ttl_layout.addWidget(lbl_feed_stay)
        feed_ttl_layout.addSpacing(6)
        self.spin_feed_stay_sec = QSpinBox()
        self.spin_feed_stay_sec.setRange(1, 600)
        self.spin_feed_stay_sec.setValue(10)
        self.spin_feed_stay_sec.setFixedWidth(80)
        feed_ttl_layout.addWidget(self.spin_feed_stay_sec)
        kf_layout.addLayout(feed_ttl_layout)

        # FONT SIZE (FEED)
        kf_fs_layout = QHBoxLayout()
        kf_fs_layout.addWidget(QLabel("Feed Font Size:"))
        self.combo_feed_font = QComboBox()
        self.combo_feed_font.addItems(["8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72", "100"])
        # Standard Feed Font is 19 - we add it if not present
        if self.combo_feed_font.findText("19") == -1:
            self.combo_feed_font.addItem("19")
        self.combo_feed_font.setCurrentText("19")
        kf_fs_layout.addWidget(self.combo_feed_font)
        
        # NEU: HS Icon Skalierung (Dropdown)
        kf_fs_layout.addWidget(QLabel("   Icon Size:"))
        self.combo_hs_scale = QComboBox()
        self.combo_hs_scale.addItems(["16", "19", "24", "28", "32", "36", "48", "64", "72", "80", "100"])
        self.combo_hs_scale.setCurrentText("19")
        self.combo_hs_scale.setFixedWidth(60)
        kf_fs_layout.addWidget(self.combo_hs_scale)
        
        kf_fs_layout.addStretch()
        kf_layout.addLayout(kf_fs_layout)

        layout.addWidget(feed_group)

        # ACTION BUTTONS
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.setContentsMargins(0, 15, 0, 0)

        self.btn_edit_hud_feed = QPushButton("MOVE UI")
        self.btn_edit_hud_feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_hud_feed.setObjectName("EditBtn")
        self.btn_edit_hud_feed.setMinimumHeight(35)

        self.btn_test_feed = QPushButton("TEST UI")
        self.btn_test_feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_feed.setObjectName("TestBtn")
        self.btn_test_feed.setMinimumHeight(35)

        self.btn_save_feed = QPushButton("SAVE SETTINGS")
        self.btn_save_feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_feed.setObjectName("SaveBtn")
        self.btn_save_feed.setMinimumHeight(35)

        btn_box.addWidget(self.btn_edit_hud_feed)
        btn_box.addWidget(self.btn_test_feed)
        btn_box.addWidget(self.btn_save_feed)

        layout.addLayout(btn_box)
        layout.addStretch()
        
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

    def setup_voice_tab(self):
        tab_layout = QVBoxLayout(self.tab_voice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header
        header = QLabel("AUTO VOICE MACRO CONFIG")
        header.setObjectName("Header")
        layout.addWidget(header)

        subtext = QLabel(
            "Automatically presses 'V' + Number when events occur.\nKeep 'OFF' to disable specific triggers.")
        subtext.setObjectName("SubText")
        layout.addWidget(subtext)

        layout.addSpacing(10)

        # --- MASTER SWITCH (NEW) ---
        self.btn_toggle_voice = QPushButton("VOICE MACROS: ON")
        self.btn_toggle_voice.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_voice.setCheckable(True)
        self.btn_toggle_voice.setChecked(True)
        self.btn_toggle_voice.setFixedHeight(40)
        self.btn_toggle_voice.setStyleSheet(
            "QPushButton { background-color: #004400; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #006600; }"
            "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            "QPushButton:focus { border: 1px solid #00ff00; }"
        )
        layout.addWidget(self.btn_toggle_voice)

        layout.addSpacing(20)

        if sys.platform.startswith("linux"):
            self.btn_request_voice_permission = QPushButton("REQUEST LINUX PERMISSIONS")
            self.btn_request_voice_permission.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.btn_request_voice_permission.setFixedHeight(45)
            self.btn_request_voice_permission.setToolTip("Triggers a harmless keypress to force the OS to ask for input permissions.")
            self.btn_request_voice_permission.setStyleSheet(
                "QPushButton { background-color: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; outline: none; margin-bottom: 10px; font-weight: bold; font-size: 13px; }"
                "QPushButton:hover { background-color: #444; color: #00f2ff; border: 1px solid #00f2ff; }"
            )
            layout.addWidget(self.btn_request_voice_permission)

        # Grid for Trigger List
        grid_frame = QFrame(objectName="Group")
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setVerticalSpacing(15)

        self.voice_combos = {}
        triggers = [
            ("I was Revived", "revived", "Use '1' for Thanks"),
            ("I Teamkilled someone", "tk", "Use '8' for Sorry"),
            ("Killed Infiltrator", "kill_infil", "Tactical Callout?"),
            ("Killed MAX Unit", "kill_max", "Taunt?"),
            ("Killed High KD Player (>2.0)", "kill_high_kd", "V6 recommended"),
            ("Headshot Kill", "kill_hs", "Nice Shot?")
        ]

        options = ["OFF"] + [str(i) for i in range(10)]

        for i, (label_text, key, hint) in enumerate(triggers):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-family: 'Consolas'; font-size: 13px; color: white;")

            combo = QComboBox()
            combo.addItems(options)
            combo.setFixedWidth(80)
            self.voice_combos[key] = combo

            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet("color: #555; font-size: 11px;")

            grid_layout.addWidget(lbl, i, 0)
            grid_layout.addWidget(combo, i, 1)
            grid_layout.addWidget(hint_lbl, i, 2)

        layout.addWidget(grid_frame)

        # Save Button
        self.btn_save_voice = QPushButton("SAVE VOICE MACROS", objectName="SaveBtn")
        self.btn_save_voice.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_voice.setFixedWidth(250)
        layout.addWidget(self.btn_save_voice, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

    def setup_twitch_tab(self):
        tab_layout = QVBoxLayout(self.tab_twitch)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- 1. HEADER & TOGGLE ---
        header_group = QFrame(objectName="Group")
        h_layout = QVBoxLayout(header_group)

        lbl_header = QLabel("TWITCH CHAT OVERLAY")
        lbl_header.setObjectName("Header")
        h_layout.addWidget(lbl_header)

        self.btn_toggle_twitch = QPushButton("TWITCH CHAT: OFF")
        self.btn_toggle_twitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_twitch.setCheckable(True)
        self.btn_toggle_twitch.setFixedHeight(40)
        # Style wird später vom Controller gesetzt/aktualisiert
        self.btn_toggle_twitch.setStyleSheet(
            "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; }"
            "QPushButton:hover { background-color: #550000; }"
            "QPushButton:focus { border: 1px solid #ff4444; }"
        )
        h_layout.addWidget(self.btn_toggle_twitch)

        layout.addWidget(header_group)

        # --- 2. CHANNEL SETTINGS ---
        chan_group = QFrame(objectName="Group")
        c_layout = QVBoxLayout(chan_group)

        c_layout.addWidget(QLabel("Channel Name (e.g. 'shroud'):", objectName="SubText"))

        chan_row = QHBoxLayout()
        self.ent_twitch_channel = QLineEdit()
        self.ent_twitch_channel.setPlaceholderText("Enter Twitch channel name...")
        chan_row.addWidget(self.ent_twitch_channel)

        # --- NEU: ALWAYS ON BUTTON ---
        self.btn_twitch_always = QPushButton("ALWAYS OFF")
        self.btn_twitch_always.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_twitch_always.setCheckable(True)
        self.btn_twitch_always.setFixedWidth(100)
        self.btn_twitch_always.setStyleSheet(
            "QPushButton { background-color: #440000; color: white; font-weight: bold; outline: none; }"
            "QPushButton:hover { background-color: #550000; }"
            "QPushButton:focus { border: 1px solid #ff4444; }"
        )
        chan_row.addWidget(self.btn_twitch_always)

        self.btn_connect_twitch = QPushButton("CONNECT")
        self.btn_connect_twitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_connect_twitch.setFixedWidth(100)
        self.btn_connect_twitch.setStyleSheet(
            "QPushButton { background-color: #6441a5; color: white; font-weight: bold; outline: none; }"
            "QPushButton:hover { background-color: #7552b6; }"
            "QPushButton:focus { border: 1px solid #a970ff; }"
        )
        chan_row.addWidget(self.btn_connect_twitch)

        c_layout.addLayout(chan_row)
        layout.addWidget(chan_group)

        # --- 2.5 IGNORE LIST ---
        ignore_group = QFrame(objectName="Group")
        i_layout = QVBoxLayout(ignore_group)

        i_layout.addWidget(QLabel("Ignore Users (comma separated):", objectName="SubText"))
        self.ent_twitch_ignore = QLineEdit()
        self.ent_twitch_ignore.setPlaceholderText("e.g. Nightbot, StreamElements, user123...")
        i_layout.addWidget(self.ent_twitch_ignore)

        # NEW: Ignore special characters
        self.btn_twitch_ignore_special = QPushButton("IGNORE SPECIAL CHARS (!): OFF")
        self.btn_twitch_ignore_special.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_twitch_ignore_special.setCheckable(True)
        self.btn_twitch_ignore_special.setFixedHeight(30)
        self.btn_twitch_ignore_special.setStyleSheet(
            "QPushButton { background-color: #440000; color: white; font-weight: bold; border-radius: 4px; outline: none; border: 1px solid #660000; }"
            "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            "QPushButton:focus { border: 1px solid #660000; }"
        )
        i_layout.addWidget(self.btn_twitch_ignore_special)

        layout.addWidget(ignore_group)

        # Appearance Group
        app_group = QFrame(objectName="Group")
        a_layout = QGridLayout(app_group)
        a_layout.setSpacing(10)

        a_layout.addWidget(QLabel("APPEARANCE", styleSheet="color: #00f2ff; font-weight: bold; margin-bottom: 5px;"), 0, 0, 1, 2)

        # Background Opacity
        a_layout.addWidget(QLabel("Background Opacity:"), 1, 0)
        self.slider_twitch_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_opacity.setRange(0, 100)
        self.slider_twitch_opacity.setValue(30)
        a_layout.addWidget(self.slider_twitch_opacity, 1, 1)

        # Font Size
        a_layout.addWidget(QLabel("Font Size:"), 2, 0)
        self.combo_twitch_font = QComboBox()
        self.combo_twitch_font.addItems(["10", "12", "14", "16", "18", "20", "24"])
        self.combo_twitch_font.setCurrentText("12")
        self.combo_twitch_font.setFixedWidth(60)
        a_layout.addWidget(self.combo_twitch_font, 2, 1)

        # Position (Offset)
        a_layout.addWidget(QLabel("Position X / Y:"), 3, 0)
        pos_row = QHBoxLayout()
        self.slider_twitch_x = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_x.setRange(0, 1920)
        self.slider_twitch_x.setValue(50)
        self.slider_twitch_y = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_y.setRange(0, 1080)
        self.slider_twitch_y.setValue(300)
        pos_row.addWidget(self.slider_twitch_x)
        pos_row.addWidget(self.slider_twitch_y)
        a_layout.addLayout(pos_row, 3, 1)

        # Dimensions (Width / Height)
        a_layout.addWidget(QLabel("Size W / H:"), 4, 0)
        size_row = QHBoxLayout()
        self.slider_twitch_w = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_w.setRange(200, 800)
        self.slider_twitch_w.setValue(350)
        self.slider_twitch_h = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_h.setRange(200, 1000)
        self.slider_twitch_h.setValue(400)
        size_row.addWidget(self.slider_twitch_w)
        size_row.addWidget(self.slider_twitch_h)
        a_layout.addLayout(size_row, 4, 1)

        # Hold Time
        a_layout.addWidget(QLabel("Hold Text for (s):"), 5, 0)
        self.spin_twitch_hold = QSpinBox()
        self.spin_twitch_hold.setRange(0, 600)
        self.spin_twitch_hold.setSuffix(" s (0 = Permanent)")
        self.spin_twitch_hold.setValue(15)
        self.spin_twitch_hold.setFixedWidth(120)
        a_layout.addWidget(self.spin_twitch_hold, 5, 1)

        layout.addWidget(app_group)

        # --- 4. SILENCE ALERT (NEW) ---
        silence_group = QFrame(objectName="Group")
        s_layout = QVBoxLayout(silence_group)

        s_header = QLabel("SILENCE ALERT")
        s_header.setObjectName("Header")
        s_layout.addWidget(s_header)
        s_layout.addWidget(QLabel("Plays a sound if no message is received for a certain time.", objectName="SubText"))

        # Enable Checkbox
        self.check_twitch_silence_active = QCheckBox("Enable Silence Alert")
        s_layout.addWidget(self.check_twitch_silence_active)

        # Time Input
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Silence Timeout (s):"))
        self.spin_twitch_silence_seconds = QSpinBox()
        self.spin_twitch_silence_seconds.setRange(5, 86400) # 5 seconds to 24 hours
        self.spin_twitch_silence_seconds.setValue(600)
        self.spin_twitch_silence_seconds.setFixedWidth(100)
        time_row.addWidget(self.spin_twitch_silence_seconds)
        time_row.addStretch()
        s_layout.addLayout(time_row)

        # Audio File Picker
        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Alert Sound:"))
        
        self.combo_twitch_silence_snd = QComboBox()
        self.combo_twitch_silence_snd.setEditable(True)
        self.combo_twitch_silence_snd.setPlaceholderText("No file selected")
        self.combo_twitch_silence_snd.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        audio_row.addWidget(self.combo_twitch_silence_snd)
        
        self.btn_browse_twitch_silence_snd = QPushButton("...")
        self.btn_browse_twitch_silence_snd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_browse_twitch_silence_snd.setFixedWidth(40)
        self.btn_browse_twitch_silence_snd.setStyleSheet("padding: 2px;")
        
        self.btn_del_twitch_silence_snd = QPushButton("del")
        self.btn_del_twitch_silence_snd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_del_twitch_silence_snd.setFixedWidth(40)
        self.btn_del_twitch_silence_snd.setStyleSheet("color: #ff4444; font-weight: bold; padding: 2px;")
        self.btn_del_twitch_silence_snd.clicked.connect(lambda: self.combo_twitch_silence_snd.removeItem(self.combo_twitch_silence_snd.currentIndex()))

        audio_row.addWidget(self.btn_browse_twitch_silence_snd)
        audio_row.addWidget(self.btn_del_twitch_silence_snd)
        s_layout.addLayout(audio_row)

        # Volume & Test Button
        vt_row = QHBoxLayout()
        vt_row.addWidget(QLabel("Volume:"))
        self.slider_twitch_silence_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_twitch_silence_vol.setRange(0, 100)
        self.slider_twitch_silence_vol.setValue(100)
        self.lbl_twitch_silence_vol_val = QLabel("100%")
        self.lbl_twitch_silence_vol_val.setFixedWidth(40)
        self.lbl_twitch_silence_vol_val.setStyleSheet("color: #00f2ff; font-weight: bold;")
        self.slider_twitch_silence_vol.valueChanged.connect(lambda v: self.lbl_twitch_silence_vol_val.setText(f"{v}%"))
        
        vt_row.addWidget(self.slider_twitch_silence_vol)
        vt_row.addWidget(self.lbl_twitch_silence_vol_val)
        
        self.btn_test_twitch_silence_snd = QPushButton("TEST")
        self.btn_test_twitch_silence_snd.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_twitch_silence_snd.setFixedWidth(80)
        self.btn_test_twitch_silence_snd.setStyleSheet("background-color: #444; color: #eee;")
        vt_row.addWidget(self.btn_test_twitch_silence_snd)
        
        s_layout.addLayout(vt_row)

        layout.addWidget(silence_group)

        # --- 5. ACTION BUTTONS ---
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_test_twitch = QPushButton("TEST MSG")
        self.btn_test_twitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_test_twitch.setObjectName("TestBtn")
        self.btn_test_twitch.setMinimumHeight(35)

        self.btn_save_twitch = QPushButton("SAVE SETTINGS")
        self.btn_save_twitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_twitch.setObjectName("SaveBtn")
        self.btn_save_twitch.setMinimumHeight(35)

        self.btn_edit_twitch = QPushButton("MOVE UI")
        self.btn_edit_twitch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_twitch.setObjectName("EditBtn")
        self.btn_edit_twitch.setMinimumHeight(35)
        
        btn_box.addWidget(self.btn_edit_twitch)
        btn_box.addWidget(self.btn_test_twitch)
        btn_box.addWidget(self.btn_save_twitch)

        layout.addLayout(btn_box)
        layout.addStretch()
        
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OverlayConfigWindow()
    window.show()
    sys.exit(app.exec())
