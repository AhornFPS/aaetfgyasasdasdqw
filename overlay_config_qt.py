import sys
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame, QTabWidget,
                             QCheckBox, QComboBox, QSlider, QScrollArea, QGridLayout,
                             QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QColor, QPixmap


# --- SIGNALE ---
class OverlaySignals(QObject):
    setting_changed = pyqtSignal(str, object)  # Key, Wert
    test_trigger = pyqtSignal(str)  # Event-Name für Test
    edit_mode_toggled = pyqtSignal(str)  # Welches HUD Element verschoben wird


# --- STYLESHEET ---
OVERLAY_STYLE = """
/* --- HAUPTFENSTER & TABS --- */
QWidget#Overlay { background-color: #1a1a1a; }

QTabWidget::pane { 
    border: 1px solid #333; 
    background-color: #1a1a1a; 
    top: -1px; 
}

QTabBar::tab { 
    background-color: #252525; 
    color: #888; 
    padding: 12px; 
    min-width: 100px; 
    border: 1px solid #333; 
    border-bottom: none; 
    border-top-left-radius: 4px; 
    border-top-right-radius: 4px; 
}

QTabBar::tab:selected { 
    background-color: #1a1a1a; 
    color: #00f2ff; 
    font-weight: bold; 
    border-bottom: 2px solid #00f2ff; 
}

QTabBar::tab:hover:!selected { 
    background-color: #333; 
    color: #eee; 
}

/* --- CONTAINER & GRUPPEN --- */
QFrame#Group { 
    background-color: #222; 
    border: 1px solid #333; 
    border-radius: 5px; 
    margin: 5px; 
    padding: 5px; 
}

QLabel#Header { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 16px; 
    margin-bottom: 10px; 
}

QLabel#SubText { 
    color: #888; 
    font-size: 11px; 
}

/* --- EINGABEFELDER --- */
QLineEdit, QComboBox {
    background-color: #111;
    border: 1px solid #444;
    color: #eee;
    padding: 6px;
    border-radius: 3px;
}

QLineEdit:focus { 
    border: 1px solid #00f2ff; 
    background-color: #000; 
}

/* --- BUTTONS BASICS --- */
QPushButton {
    background-color: #2a2a2a;
    border: 1px solid #444;
    color: #ddd;
    padding: 8px 15px;      /* Mehr Innenabstand */
    border-radius: 4px;
    font-weight: bold;
    font-size: 11px;
    min-height: 20px;       /* Mindesthöhe damit sie massiver wirken */
}

QPushButton:hover {
    background-color: #3a3a3a;
    border-color: #00f2ff;
    color: white;
}

QPushButton:pressed { 
    background-color: #00f2ff; 
    color: black; 
    border-color: #00f2ff;
}

/* --- SPEZIAL-BUTTONS (TARGETED BY ID) --- */

/* MOVE UI / EDIT (Kräftiges Blau) */
QPushButton#EditBtn { 
    background-color: #004080; 
    color: white; 
    border: 1px solid #0055aa; 
    font-size: 12px;
}
QPushButton#EditBtn:hover { 
    background-color: #0066cc; 
    border-color: #00f2ff; 
}

/* TEST BUTTON (Dunkelgrau) */
QPushButton#TestBtn { 
    background-color: #333; 
    color: #eee; 
    border: 1px solid #555; 
    font-size: 12px;
}
QPushButton#TestBtn:hover { 
    background-color: #444; 
    border-color: #ccc; 
}

/* SAVE BUTTON (Dunkelgrün) */
QPushButton#SaveBtn { 
    background-color: #004400; 
    color: #00ff00; 
    border: 1px solid #006600; 
    font-size: 12px;
}
QPushButton#SaveBtn:hover { 
    background-color: #006600; 
    border-color: #00ff00; 
    color: white; 
}

/* RECORD BUTTON (Orange/Rot) */
QPushButton#RecordBtn { 
    background-color: #883300; 
    color: white; 
    border: 1px solid #aa4400; 
}
QPushButton#RecordBtn:hover { 
    background-color: #aa4400; 
    border-color: #ff8c00; 
}

/* CLEAR BUTTON (Sehr dunkel) */
QPushButton#ClearBtn { 
    background-color: #1a1a1a; 
    color: #888; 
    border: 1px solid #333; 
}
QPushButton#ClearBtn:hover { 
    background-color: #222; 
    border-color: #555; 
    color: #ccc;
}

/* COLOR PICKER (Lila) */
QPushButton#ColorBtn { 
    background-color: #440088; 
    color: white; 
    border: 1px solid #6600aa; 
}
QPushButton#ColorBtn:hover { 
    background-color: #5500aa; 
    border-color: #ff00ff; 
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
    """Ein Label, das sein Bild proportional skaliert, wenn sich die Fenstergröße ändert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)  # Wichtig, damit es auch kleiner werden kann
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
            # Skaliert das Bild auf die aktuelle Größe des Labels (KeepAspectRatio)
            scaled = self.pixmap_cache.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled)
        else:
            self.setText("NO PREVIEW")


class OverlayConfigWindow(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Overlay")
        self.resize(1150, 850)

        # Stylesheet direkt hier laden
        self.setStyleSheet(OVERLAY_STYLE)

        self.signals = OverlaySignals()

        layout = QVBoxLayout(self)

        # Das Herzstück: Das Tab-System
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

        # --- TAB 5: SESSION STATS & FEED ---
        self.tab_stats = QWidget()
        self.setup_stats_tab()
        self.tabs.addTab(self.tab_stats, " STATS AND FEED ")

        # --- TAB 6: AUTO VOICE ---
        self.tab_voice = QWidget()
        self.setup_voice_tab()
        self.tabs.addTab(self.tab_voice, " VOICE MACROS ")

        layout.addWidget(self.tabs)

    # --- TAB SETUP METHODEN ---

    def setup_identity_tab(self):
        layout = QVBoxLayout(self.tab_ident)
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
        self.btn_del_char.setStyleSheet("background: #440000; color: #ff4444; border: 1px solid #660000;")
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
        self.btn_add_char.setFixedWidth(80)
        self.btn_add_char.setStyleSheet(
            "background: #004400; color: #00ff00; font-weight: bold; border: 1px solid #006600;")

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

        layout.addStretch()  # Drückt alles nach oben
        layout.addWidget(master_box)

    def setup_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- 1. GLOBAL CONTROLS (Oben) ---
        global_ctrl_layout = QHBoxLayout()

        # Queue Toggle
        self.btn_queue_toggle = QPushButton("QUEUE: ON")
        self.btn_queue_toggle.setCheckable(True)
        self.btn_queue_toggle.setChecked(True)
        self.btn_queue_toggle.setStyleSheet(
            "background-color: #004400; color: white; font-weight: bold; padding: 10px;")

        # Bulk Action
        self.btn_apply_all = QPushButton("APPLY LAYOUT TO ALL (Except Hitmarker)")
        self.btn_apply_all.setStyleSheet("background-color: #552200; color: #ffdddd; padding: 10px;")

        global_ctrl_layout.addWidget(self.btn_queue_toggle)
        global_ctrl_layout.addWidget(self.btn_apply_all)
        layout.addLayout(global_ctrl_layout)

        # --- 2. EVENT SELECTION GRID (Mitte) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #1a1a1a; border: none;")

        grid_widget = QWidget()
        grid_layout = QHBoxLayout(grid_widget)
        grid_layout.setSpacing(5)

        self.event_categories = {
            "STANDARD": ["Kill", "Headshot", "Death", "Hitmarker", "Team Kill", "Team Kill Victim"],
            "STREAKS": ["Squad Wiper", "Double Squad Wipe", "Squad Lead's Nightmare", "One Man Platoon"],
            "MULTI KILL": ["Double Kill", "Multi Kill", "Mega Kill", "Ultra Kill", "Monster Kill", "Ludicrous Kill",
                           "Holy Shit"],
            "SPECIAL": ["Bounty Kill", "Domination", "Revenge","Infil Kill", "Killstreak Stop", "Nade Kill", "Knife Kill", "Max Kill", "RoadKill", "Get Roadkilled",
                        "Spitfire Kill", "Gunner Kill"],
            "SUPPORT": ["Revive Given", "Revive Taken", "Heal", "Resupply", "Repair", "Break Construction","Mine Kill"],
            "OBJECTIVES": ["Point Control", "Sunderer Spawn", "Base Capture", "Gunner Assist", "Alert End",
                           "Alert Win"],
            "SYSTEM": ["Login TR", "Login NC", "Login VS", "Login NSO"]
        }

        self.event_buttons = {}

        for cat_name, items in self.event_categories.items():
            cat_box = QFrame(objectName="Group")
            cat_vbox = QVBoxLayout(cat_box)
            cat_vbox.setContentsMargins(5, 5, 5, 5)

            lbl_cat = QLabel(cat_name)
            lbl_cat.setStyleSheet("color: #00f2ff; font-weight: bold; font-size: 10px; border-bottom: 1px solid #333;")
            lbl_cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cat_vbox.addWidget(lbl_cat)

            for item in items:
                btn = QPushButton(item)
                btn.setStyleSheet("""
                    QPushButton { background-color: #1a1a1a; color: #ccc; border: none; padding: 4px; font-size: 11px; }
                    QPushButton:hover { background-color: #00f2ff; color: black; }
                """)
                btn.clicked.connect(lambda _, x=item: self.select_event(x))
                cat_vbox.addWidget(btn)
                self.event_buttons[item] = btn

            cat_vbox.addStretch()
            grid_layout.addWidget(cat_box)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, 3)

        # --- 3. EDIT AREA (Unten) ---
        edit_box = QFrame(objectName="Group")
        edit_layout = QVBoxLayout(edit_box)

        self.lbl_editing = QLabel("EDITING: NONE")
        self.lbl_editing.setStyleSheet("color: #00ff00; font-size: 16px; font-weight: bold;")
        edit_layout.addWidget(self.lbl_editing)

        # Container Split: Links Input, Rechts Preview
        editor_split = QHBoxLayout()

        # --- LINKS: INPUTS ---
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)

        # Image & Sound Row
        io_grid = QGridLayout()
        io_grid.addWidget(QLabel("Image (PNG/JPG):"), 0, 0)
        self.ent_evt_img = QLineEdit()
        io_grid.addWidget(self.ent_evt_img, 0, 1)
        self.btn_browse_evt_img = QPushButton("...")
        self.btn_browse_evt_img.setFixedWidth(30)
        io_grid.addWidget(self.btn_browse_evt_img, 0, 2)

        io_grid.addWidget(QLabel("Sound (MP3/OGG):"), 1, 0)
        self.ent_evt_snd = QLineEdit()
        io_grid.addWidget(self.ent_evt_snd, 1, 1)
        self.btn_browse_evt_snd = QPushButton("...")
        self.btn_browse_evt_snd.setFixedWidth(30)
        io_grid.addWidget(self.btn_browse_evt_snd, 1, 2)

        input_layout.addLayout(io_grid)

        # Scale & Duration Row
        sd_layout = QHBoxLayout()

        sd_layout.addWidget(QLabel("Scale:"))
        self.slider_evt_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_evt_scale.setRange(10, 300)
        self.slider_evt_scale.setValue(100)

        # Scale Value Label
        self.lbl_scale_val = QLabel("1.00")
        self.lbl_scale_val.setStyleSheet("color: #00f2ff; font-weight: bold; font-family: Consolas;")
        self.lbl_scale_val.setFixedWidth(40)
        # Direktes Update beim Schieben
        self.slider_evt_scale.valueChanged.connect(lambda val: self.lbl_scale_val.setText(f"{val / 100:.2f}"))

        sd_layout.addWidget(self.slider_evt_scale)
        sd_layout.addWidget(self.lbl_scale_val)

        sd_layout.addWidget(QLabel("Duration (ms):"))
        self.ent_evt_duration = QLineEdit("3000")
        self.ent_evt_duration.setFixedWidth(60)
        sd_layout.addWidget(self.ent_evt_duration)

        input_layout.addLayout(sd_layout)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)  # Abstand zwischen Buttons

        self.btn_edit_hud = QPushButton("MOVE UI")
        self.btn_edit_hud.setObjectName("EditBtn")  # -> Blau
        self.btn_edit_hud.setMinimumHeight(35)  # Schön hoch

        self.btn_test_preview = QPushButton("TEST PREVIEW")
        self.btn_test_preview.setObjectName("TestBtn")  # -> Grau
        self.btn_test_preview.setMinimumHeight(35)

        self.btn_save_event = QPushButton("SAVE EVENT")
        self.btn_save_event.setObjectName("SaveBtn")  # -> Grün
        self.btn_save_event.setMinimumHeight(35)

        btn_box.addWidget(self.btn_edit_hud)
        btn_box.addWidget(self.btn_test_preview)
        btn_box.addWidget(self.btn_save_event)

        input_layout.addLayout(btn_box)

        # --- RECHTS: PREVIEW ---
        # Wir nutzen unsere Custom Class AspectRatioLabel
        self.lbl_event_preview = AspectRatioLabel()
        # SizePolicy: Expanding sagt dem Layout "Nimm dir so viel Platz wie möglich"
        self.lbl_event_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Zusammenbau
        editor_split.addWidget(input_container, 60)  # 60% Breite
        editor_split.addWidget(self.lbl_event_preview, 40)  # 40% Breite

        edit_layout.addLayout(editor_split)
        layout.addWidget(edit_box, 2)

    def select_event(self, event_name):
        """Wird aufgerufen, wenn man im Grid auf ein Event klickt"""
        self.lbl_editing.setText(f"EDITING: {event_name}")
        self.signals.setting_changed.emit("event_selection", event_name)

    def update_preview_image(self, image_path):
        """Helper: Lädt das Bild in die Responsive Preview-Box"""
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

        self.btn_browse_cross = QPushButton("Browse")
        img_layout.addWidget(self.btn_browse_cross)
        layout.addLayout(img_layout)

        # HIER WAR DER ALTE TEXT
        self.btn_edit_cross = QPushButton("MOVE UI", objectName="EditBtn")
        layout.addWidget(self.btn_edit_cross)

        self.btn_center_cross = QPushButton("AUTO-CENTER (Middle)")
        layout.addWidget(self.btn_center_cross)

    def setup_streak_tab(self):
        layout = QVBoxLayout(self.tab_streak)
        layout.setContentsMargins(10, 10, 10, 10)  # Weniger Rand außen

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #1a1a1a;")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(10)  # KOMPAKTER: Globaler Abstand zwischen Gruppen reduziert

        # --- 1. HEADER & MASTER SWITCH ---
        header_layout = QHBoxLayout()
        lbl_header = QLabel("KILLSTREAK SYSTEM")
        lbl_header.setStyleSheet("color: #00f2ff; font-weight: bold; font-size: 16px;")
        header_layout.addWidget(lbl_header)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        sw_layout = QHBoxLayout()
        # Checkbox Styles etwas kompakter
        cb_style = "QCheckBox { font-weight: bold; font-size: 11px; spacing: 5px; }"

        self.check_streak_master = QCheckBox("ENABLE KILLSTREAK SYSTEM")
        self.check_streak_master.setStyleSheet(cb_style + "QCheckBox { color: #00ff00; }")

        self.check_streak_anim = QCheckBox("ENABLE PULSE ANIMATION")
        self.check_streak_anim.setStyleSheet(cb_style + "QCheckBox { color: #ffcc00; }")

        sw_layout.addWidget(self.check_streak_master)
        sw_layout.addWidget(self.check_streak_anim)
        main_layout.addLayout(sw_layout)

        # --- 2. MAIN VISUALS ---
        vis_group = QFrame()
        # KOMPAKTER: Padding reduziert
        vis_group.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 5px; padding: 5px;")
        vis_layout = QVBoxLayout(vis_group)
        vis_layout.setSpacing(5)  # KOMPAKTER: Abstand innerhalb der Gruppe

        vis_layout.addWidget(QLabel("MAIN BACKGROUND & ANIMATION",
                                    styleSheet="color: #00f2ff; font-weight:bold; font-size: 11px; border: none; margin-bottom: 2px;"))

        img_row = QHBoxLayout()
        img_row.setContentsMargins(0, 0, 0, 0)
        img_row.addWidget(QLabel("Main Image:", styleSheet="border: none; color: #ddd;"))
        self.ent_streak_img = QLineEdit("KS_Counter.png")
        self.ent_streak_img.setStyleSheet("background-color: #111; color: #eee; border: 1px solid #444; padding: 3px;")

        self.btn_browse_streak_img = QPushButton("...")
        self.btn_browse_streak_img.setFixedWidth(30)
        self.btn_browse_streak_img.setStyleSheet(
            "background-color: #333; color: white; border: 1px solid #555; padding: 2px;")

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
        knife_layout.setSpacing(2)  # Sehr eng beieinander

        lbl_knife = QLabel("FACTION KNIVES / ICONS (PNG)")
        lbl_knife.setStyleSheet("color: #00f2ff; font-weight:bold; font-size: 11px; border: none; margin-bottom: 2px;")
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
            btn_browse.setFixedWidth(30)
            btn_browse.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; padding: 2px;")

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
        self.btn_path_record.setStyleSheet("""
            QPushButton { background-color: #aa4400; color: white; border: 1px solid #cc5500; padding: 5px; font-weight: bold; border-radius: 3px; font-size: 11px;}
            QPushButton:hover { background-color: #bb5500; border-color: #ff8c00; }
        """)

        self.btn_path_clear = QPushButton("CLEAR PATH")
        self.btn_path_clear.setStyleSheet("""
            QPushButton { background-color: #222; color: #888; border: 1px solid #333; padding: 5px; font-weight: bold; border-radius: 3px; font-size: 11px;}
            QPushButton:hover { background-color: #333; color: #ccc; border-color: #555; }
        """)

        btn_path_row.addWidget(self.btn_path_record)
        btn_path_row.addWidget(self.btn_path_clear)
        path_layout.addLayout(btn_path_row)
        main_layout.addWidget(path_group)

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
        # Slider etwas kompakter machen (Höhe begrenzen)
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

        self.btn_pick_color = QPushButton("COLOR")
        self.btn_pick_color.setFixedWidth(70)
        self.btn_pick_color.setStyleSheet("""
            QPushButton { background-color: #5500aa; color: white; border: 1px solid #7700cc; padding: 3px; font-weight: bold; border-radius: 3px; font-size: 10px; }
            QPushButton:hover { background-color: #6600cc; border-color: #ff00ff; }
        """)

        self.combo_font_size = QComboBox()
        self.combo_font_size.addItems(["12", "16", "20", "24", "26", "28", "32", "36", "48", "72"])
        self.combo_font_size.setCurrentText("26")
        self.combo_font_size.setFixedWidth(50)
        self.combo_font_size.setStyleSheet(
            "background-color: #111; color: #eee; border: 1px solid #444; padding: 1px; font-size: 11px;")

        design_box.addWidget(self.btn_pick_color)
        design_box.addWidget(QLabel("Size:", styleSheet="border:none; color:#ddd; margin-left:10px; font-size: 11px;"))
        design_box.addWidget(self.combo_font_size)
        design_box.addStretch()

        pos_layout.addLayout(design_box, 4, 1, 1, 2)
        main_layout.addWidget(pos_group)

        # --- 6. ACTION BUTTONS ---
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        action_layout.setContentsMargins(0, 5, 0, 0)  # Nur wenig Abstand nach oben

        # Button Style Templates (Kompakter)
        style_base = "border-radius: 4px; font-weight: bold; font-size: 12px; padding: 5px;"

        # 1. MOVE UI (Blau)
        self.btn_edit_streak = QPushButton("MOVE UI")
        self.btn_edit_streak.setMinimumHeight(35)
        self.btn_edit_streak.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_streak.setStyleSheet(f"""
            QPushButton {{ background-color: #004080; color: white; border: 1px solid #0055aa; {style_base} }}
            QPushButton:hover {{ background-color: #0066cc; border: 1px solid #00f2ff; }}
            QPushButton:pressed {{ background-color: #00f2ff; color: black; }}
        """)

        # 2. TEST ANIMATION (Grau)
        self.btn_test_streak = QPushButton("TEST")
        self.btn_test_streak.setMinimumHeight(35)
        self.btn_test_streak.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_streak.setStyleSheet(f"""
            QPushButton {{ background-color: #333; color: #eee; border: 1px solid #555; {style_base} }}
            QPushButton:hover {{ background-color: #444; border: 1px solid #ccc; }}
            QPushButton:pressed {{ background-color: #666; }}
        """)

        # 3. SAVE SETTINGS (Grün)
        self.btn_save_streak = QPushButton("SAVE SETTINGS")
        self.btn_save_streak.setMinimumHeight(35)
        self.btn_save_streak.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_streak.setStyleSheet(f"""
            QPushButton {{ background-color: #004400; color: #00ff00; border: 1px solid #006600; {style_base} }}
            QPushButton:hover {{ background-color: #006600; border: 1px solid #00ff00; color: white; }}
            QPushButton:pressed {{ background-color: #00ff00; color: black; }}
        """)

        action_layout.addWidget(self.btn_edit_streak)
        action_layout.addWidget(self.btn_test_streak)
        action_layout.addWidget(self.btn_save_streak)

        main_layout.addLayout(action_layout)
        main_layout.addStretch()

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def setup_stats_tab(self):
        layout = QVBoxLayout(self.tab_stats)
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
        self.btn_toggle_stats.setFixedHeight(40)
        self.btn_toggle_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_stats.setStyleSheet(
            "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        st_layout.addWidget(self.btn_toggle_stats)

        # Background Image
        st_layout.addWidget(QLabel("Background (PNG):", objectName="SubText"))
        st_img_h = QHBoxLayout()
        self.ent_stats_img = QLineEdit()
        self.btn_browse_stats_bg = QPushButton("...")
        self.btn_browse_stats_bg.setFixedWidth(40)
        st_img_h.addWidget(self.ent_stats_img)
        st_img_h.addWidget(self.btn_browse_stats_bg)
        st_layout.addLayout(st_img_h)

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

        # Scale
        st_layout.addWidget(QLabel("Image scale:"))
        self.slider_st_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_st_scale.setRange(10, 200)
        self.slider_st_scale.setValue(100)
        st_layout.addWidget(self.slider_st_scale)

        layout.addWidget(stats_group)

        # ==========================================
        # 2. KILLFEED
        # ==========================================
        feed_group = QFrame(objectName="Group")
        kf_layout = QVBoxLayout(feed_group)

        kf_header = QLabel("--- KILLFEED ---")
        kf_header.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 16px;")
        kf_layout.addWidget(kf_header)

        # --- KILLFEED TOGGLE BUTTON (New) ---
        self.btn_toggle_feed = QPushButton("KILLFEED: ON")
        self.btn_toggle_feed.setFixedHeight(40)
        self.btn_toggle_feed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_feed.setStyleSheet(
            "background-color: #004400; color: white; font-weight: bold; border-radius: 4px;")
        kf_layout.addWidget(self.btn_toggle_feed)

        # Headshot Icon
        kf_layout.addWidget(QLabel("Headshot Icon (PNG):", objectName="SubText"))
        hs_h = QHBoxLayout()
        self.ent_hs_icon = QLineEdit()
        self.btn_browse_hs_icon = QPushButton("...")
        self.btn_browse_hs_icon.setFixedWidth(40)

        hs_h.addWidget(self.ent_hs_icon)
        hs_h.addWidget(self.btn_browse_hs_icon)
        kf_layout.addLayout(hs_h)

        # Revive Checkbox
        self.check_show_revives = QCheckBox("Show Revives in Feed")
        self.check_show_revives.setStyleSheet("color: #00ff00;")
        kf_layout.addWidget(self.check_show_revives)

        layout.addWidget(feed_group)

        # ==========================================
        # 3. ACTION BUTTONS (Bottom)
        # ==========================================
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.setContentsMargins(0, 15, 0, 0)

        # Hier nur noch Edit, Test, Save (keine Live-Buttons mehr)
        self.btn_edit_hud_stats = QPushButton("MOVE UI")
        self.btn_edit_hud_stats.setObjectName("EditBtn")
        self.btn_edit_hud_stats.setMinimumHeight(35)

        self.btn_test_stats = QPushButton("TEST UI")
        self.btn_test_stats.setObjectName("TestBtn")
        self.btn_test_stats.setMinimumHeight(35)

        self.btn_save_stats = QPushButton("SAVE SETTINGS")
        self.btn_save_stats.setObjectName("SaveBtn")
        self.btn_save_stats.setMinimumHeight(35)

        btn_box.addWidget(self.btn_edit_hud_stats)
        btn_box.addWidget(self.btn_test_stats)
        btn_box.addWidget(self.btn_save_stats)

        layout.addLayout(btn_box)
        layout.addStretch()

    def setup_voice_tab(self):
        layout = QVBoxLayout(self.tab_voice)
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

        layout.addSpacing(20)

        # Grid für die Trigger-Liste
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
        self.btn_save_voice.setFixedWidth(250)
        layout.addWidget(self.btn_save_voice, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OverlayConfigWindow()
    window.show()
    sys.exit(app.exec())