import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame, QTabWidget,
                             QCheckBox, QComboBox, QSlider, QScrollArea, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor


# --- SIGNALE ---
class OverlaySignals(QObject):
    setting_changed = pyqtSignal(str, object)  # Key, Wert
    test_trigger = pyqtSignal(str)  # Event-Name für Test
    edit_mode_toggled = pyqtSignal(str)  # Welches HUD Element verschoben wird


# --- STYLESHEET ---
OVERLAY_STYLE = """
QWidget#Overlay { background-color: #1a1a1a; }
QTabWidget::pane { border: 1px solid #333; background: #1a1a1a; }
QTabBar::tab { background: #252525; color: #888; padding: 12px; min-width: 100px; border: 1px solid #333; }
QTabBar::tab:selected { background: #00f2ff; color: black; font-weight: bold; }

QFrame#Group { background-color: #222; border: 1px solid #333; border-radius: 5px; margin: 5px; }
QLabel#Header { color: #00f2ff; font-weight: bold; font-size: 16px; margin-bottom: 10px; }
QLabel#SubText { color: #888; font-size: 11px; }

QPushButton#EditBtn { background-color: #0066ff; color: white; font-weight: bold; padding: 10px; border-radius: 4px; }
QPushButton#TestBtn { background-color: #444; color: white; padding: 10px; }
QPushButton#SaveBtn { background-color: #004400; color: white; font-weight: bold; padding: 10px; }
"""


class OverlayConfigWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Overlay")
        self.resize(1150, 850) # Etwas höher für die Voice-Liste
        self.signals = OverlaySignals()

        layout = QVBoxLayout(self)

        # Das Herzstück: Das Tab-System
        self.tabs = QTabWidget()

        # --- TAB 1: IDENTITY (Wer bist du?) ---
        self.tab_ident = QWidget()
        self.setup_identity_tab()
        self.tabs.addTab(self.tab_ident, " IDENTITY ")

        # --- TAB 2: EVENTS (Bilder & Sounds bei Kills) ---
        self.tab_events = QWidget()
        self.setup_events_tab()
        self.tabs.addTab(self.tab_events, " EVENTS ")

        # --- TAB 3: KILLSTREAK (Messer-System) ---
        self.tab_streak = QWidget()
        self.setup_streak_tab()
        self.tabs.addTab(self.tab_streak, " KILLSTREAK ")

        # --- TAB 4: CROSSHAIR (Fadenkreuz) ---
        self.tab_cross = QWidget()
        self.setup_crosshair_tab()
        self.tabs.addTab(self.tab_cross, " CROSSHAIR ")

        # --- TAB 5: SESSION STATS & FEED (NEU) ---
        self.tab_stats = QWidget()
        self.setup_stats_tab() # Die Methode haben wir im vorletzten Schritt gebaut
        self.tabs.addTab(self.tab_stats, " STATS & FEED ")

        # --- TAB 6: AUTO VOICE (NEU) ---
        self.tab_voice = QWidget()
        self.setup_voice_tab() # Die Methode haben wir im letzten Schritt gebaut
        self.tabs.addTab(self.tab_voice, " VOICE MACROS ")

        layout.addWidget(self.tabs)

    # --- TAB SETUP METHODEN ---

    def setup_identity_tab(self):
        layout = QVBoxLayout(self.tab_ident)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QLabel("ACTIVE TRACKING IDENTITY")
        header.setObjectName("Header")
        layout.addWidget(header)

        layout.addWidget(QLabel("Select the character you are currently playing.", objectName="SubText"))

        self.char_combo = QComboBox()
        self.char_combo.setMinimumWidth(300)
        layout.addWidget(self.char_combo)

        btn_del = QPushButton("DELETE SELECTED")
        btn_del.setStyleSheet("background: #440000; color: #ff4444;")
        layout.addWidget(btn_del)

        layout.addSpacing(40)

        # Master Switch Group
        master_box = QFrame(objectName="Group")
        m_layout = QVBoxLayout(master_box)
        self.check_master = QCheckBox("SYSTEM OVERLAY MASTER-SWITCH")
        self.check_master.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 14px;")
        m_layout.addWidget(self.check_master)
        layout.addWidget(master_box)

    def setup_events_tab(self):
        layout = QVBoxLayout(self.tab_events)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- 1. GLOBAL CONTROLS (Oben) ---
        global_ctrl_layout = QHBoxLayout()

        # Queue Toggle
        self.btn_queue_toggle = QPushButton("QUEUE: ON")
        self.btn_queue_toggle.setStyleSheet(
            "background-color: #004400; color: white; font-weight: bold; padding: 10px;")

        # Bulk Action
        btn_apply_all = QPushButton("APPLY LAYOUT TO ALL (Except Hitmarker)")
        btn_apply_all.setStyleSheet("background-color: #552200; color: #ffdddd; padding: 10px;")

        global_ctrl_layout.addWidget(self.btn_queue_toggle)
        global_ctrl_layout.addWidget(btn_apply_all)
        layout.addLayout(global_ctrl_layout)

        # --- 2. EVENT SELECTION GRID (Mitte) ---
        # Wir nutzen eine ScrollArea, falls die Liste zu lang wird
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
            "SPECIAL": ["Domination", "Revenge", "Killstreak Stop", "Nade Kill", "Knife Kill", "Max Kill", "Road Kill",
                        "Spitfire Kill", "Gunner Kill"],
            "SUPPORT": ["Revive Given", "Revive Taken", "Heal", "Resupply", "Repair", "Break Construction"],
            "OBJECTIVES": ["Point Control", "Sunderer Spawn", "Base Capture", "Gunner Assist", "Alert End",
                           "Alert Win"],
            "SYSTEM": ["Login TR", "Login NC", "Login VS", "Login NSO"]
        }

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
                # Beim Klick rufen wir eine Funktion auf, die die Auswahl ändert
                btn.clicked.connect(lambda checked, i=item: self.select_event(i))
                cat_vbox.addWidget(btn)

            cat_vbox.addStretch()
            grid_layout.addWidget(cat_box)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, 3)  # Nimmt mehr Platz ein

        # --- 3. EDIT AREA (Unten) ---
        edit_box = QFrame(objectName="Group")
        edit_layout = QVBoxLayout(edit_box)

        self.lbl_editing = QLabel("EDITING: Kill")
        self.lbl_editing.setStyleSheet("color: #00ff00; font-size: 16px; font-weight: bold;")
        edit_layout.addWidget(self.lbl_editing)

        # Image & Sound Row
        io_grid = QGridLayout()

        io_grid.addWidget(QLabel("Image (PNG/JPG):"), 0, 0)
        self.ent_evt_img = QLineEdit()
        io_grid.addWidget(self.ent_evt_img, 0, 1)
        # Button benannt
        self.btn_browse_evt_img = QPushButton("...")
        self.btn_browse_evt_img.setFixedWidth(30)
        io_grid.addWidget(self.btn_browse_evt_img, 0, 2)

        io_grid.addWidget(QLabel("Sound (MP3/OGG):"), 1, 0)
        self.ent_evt_snd = QLineEdit()
        io_grid.addWidget(self.ent_evt_snd, 1, 1)
        # Button benannt
        self.btn_browse_evt_snd = QPushButton("...")
        self.btn_browse_evt_snd.setFixedWidth(30)
        io_grid.addWidget(self.btn_browse_evt_snd, 1, 2)

        edit_layout.addLayout(io_grid)

        # Scale & Duration Row
        sd_layout = QHBoxLayout()

        sd_layout.addWidget(QLabel("Scale:"))
        self.slider_evt_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_evt_scale.setRange(10, 300)
        sd_layout.addWidget(self.slider_evt_scale)

        sd_layout.addWidget(QLabel("Duration (ms):"))
        self.ent_evt_duration = QLineEdit("3000")
        self.ent_evt_duration.setFixedWidth(60)
        sd_layout.addWidget(self.ent_evt_duration)

        edit_layout.addLayout(sd_layout)

        # Action Buttons
        btn_box = QHBoxLayout()
        self.btn_edit_hud = QPushButton("LAYOUT PER MAUS VERSCHIEBEN", objectName="EditBtn")
        self.btn_test_preview = QPushButton("TEST PREVIEW", objectName="TestBtn")
        self.btn_save_event = QPushButton("SAVE EVENT", objectName="SaveBtn")  # NEU

        btn_box.addWidget(self.btn_edit_hud)
        btn_box.addWidget(self.btn_test_preview)
        btn_box.addWidget(self.btn_save_event)  # NEU

        edit_layout.addLayout(btn_box)
        layout.addWidget(edit_box, 2)

    def select_event(self, event_name):
        """Wird aufgerufen, wenn man im Grid auf ein Event klickt"""
        self.lbl_editing.setText(f"EDITING: {event_name}")
        # Hier senden wir ein Signal an das Hauptprogramm,
        # damit dieses die passenden Pfade/Werte in die Felder lädt
        self.signals.setting_changed.emit("event_selection", event_name)

    def setup_crosshair_tab(self):
        layout = QVBoxLayout(self.tab_cross)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.check_cross = QCheckBox("CROSSHAIR ANZEIGEN")
        self.check_cross.setObjectName("Header")
        layout.addWidget(self.check_cross)

        layout.addWidget(QLabel("Crosshair Image (PNG):"))
        img_layout = QHBoxLayout()
        self.cross_path = QLineEdit()
        img_layout.addWidget(self.cross_path)
        img_layout.addWidget(QPushButton("Browse"))
        layout.addLayout(img_layout)

        self.btn_edit_cross = QPushButton("LAYOUT PER MAUS VERSCHIEBEN", objectName="EditBtn")
        layout.addWidget(self.btn_edit_cross)

        self.btn_center = QPushButton("AUTO-CENTER (MITTE)")
        layout.addWidget(self.btn_center)

    def setup_streak_tab(self):
        layout = QVBoxLayout(self.tab_streak)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- HEADER & MASTER SWITCH ---
        header = QLabel("KILLSTREAK SYSTEM")
        header.setObjectName("Header")
        layout.addWidget(header)

        self.check_streak_master = QCheckBox("KILLSTREAK SYSTEM AKTIVIEREN (Master)")
        self.check_streak_master.setStyleSheet("color: #00ff00; font-weight: bold;")
        layout.addWidget(self.check_streak_master)

        self.check_streak_anim = QCheckBox("PULSIERENDE ANIMATION AKTIVIEREN")
        self.check_streak_anim.setStyleSheet("color: #ffcc00;")
        layout.addWidget(self.check_streak_anim)

        # --- MESSER KONFIGURATION (Fraktionen) ---
        knife_group = QFrame(objectName="Group")
        knife_layout = QVBoxLayout(knife_group)
        lbl_knife = QLabel("FRAKTIONS-MESSER (PNG)")
        lbl_knife.setStyleSheet("color: #00f2ff; font-size: 10px;")
        knife_layout.addWidget(lbl_knife)

        self.knife_inputs = {}
        for faction in ["TR", "NC", "VS"]:
            f_row = QHBoxLayout()
            f_row.addWidget(QLabel(f"{faction}:", width=30))
            line_edit = QLineEdit()
            btn_browse = QPushButton("📁")
            btn_browse.setFixedWidth(40)

            f_row.addWidget(line_edit)
            f_row.addWidget(btn_browse)
            knife_layout.addLayout(f_row)
            self.knife_inputs[faction] = line_edit

        layout.addWidget(knife_group)

        # --- POSITION & SKALIERUNG ---
        pos_group = QFrame(objectName="Group")
        pos_layout = QGridLayout(pos_group)
        lbl_pos = QLabel("ZAHL-POSITION (RELATIV):")
        lbl_pos.setStyleSheet("color: #00f2ff;")
        pos_layout.addWidget(lbl_pos, 0, 0, 1, 2)

        # X-Position
        pos_layout.addWidget(QLabel("X-Achse:"), 1, 0)
        self.slider_tx = QSlider(Qt.Orientation.Horizontal)
        self.slider_tx.setRange(-200, 200)
        pos_layout.addWidget(self.slider_tx, 1, 1)

        # Y-Position
        pos_layout.addWidget(QLabel("Y-Achse:"), 2, 0)
        self.slider_ty = QSlider(Qt.Orientation.Horizontal)
        self.slider_ty.setRange(-200, 200)
        pos_layout.addWidget(self.slider_ty, 2, 1)

        # Skalierung
        pos_layout.addWidget(QLabel("HUD-SKALIERUNG:"), 3, 0)
        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(10, 300)  # 0.1 bis 3.0
        pos_layout.addWidget(self.slider_scale, 3, 1)

        layout.addWidget(pos_group)

        # --- DESIGN & FARBE ---
        design_group = QFrame(objectName="Group")
        design_layout = QHBoxLayout(design_group)

        self.btn_pick_color = QPushButton("🎨 ZAHL-FARBE WÄHLEN")
        self.btn_pick_color.setObjectName("ActionBtn")

        self.combo_font_size = QComboBox()
        self.combo_font_size.addItems(["12", "16", "20", "24", "26", "28", "32", "36", "48", "72"])

        design_layout.addWidget(self.btn_pick_color)
        design_layout.addWidget(QLabel("Größe:"))
        design_layout.addWidget(self.combo_font_size)

        layout.addWidget(design_group)

        # --- ACTION BUTTONS ---
        action_layout = QHBoxLayout()
        self.btn_save_streak = QPushButton("SAVE", objectName="SaveBtn")
        self.btn_edit_streak = QPushButton("EDIT UI", objectName="EditBtn")
        self.btn_test_streak = QPushButton("TEST", objectName="TestBtn")

        action_layout.addWidget(self.btn_save_streak)
        action_layout.addWidget(self.btn_edit_streak)
        action_layout.addWidget(self.btn_test_streak)
        layout.addLayout(action_layout)

        layout.addStretch()

    def setup_stats_tab(self):
        layout = QVBoxLayout(self.tab_stats)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- SESSION STATS WIDGET BEREICH ---
        stats_group = QFrame(objectName="Group")
        st_layout = QVBoxLayout(stats_group)

        st_header = QLabel("--- SESSION STATS WIDGET ---")
        st_header.setObjectName("Header")
        st_layout.addWidget(st_header)

        self.check_stats_active = QCheckBox("SHOW LIVE STATS")
        self.check_stats_active.setStyleSheet("color: #00ff00; font-weight: bold;")
        st_layout.addWidget(self.check_stats_active)

        # Hintergrund Bild Wahl
        st_layout.addWidget(QLabel("Hintergrund (PNG):", objectName="SubText"))
        st_img_h = QHBoxLayout()
        self.ent_stats_img = QLineEdit()
        btn_st_browse = QPushButton("...")
        btn_st_browse.setFixedWidth(40)
        st_img_h.addWidget(self.ent_stats_img)
        st_img_h.addWidget(btn_st_browse)
        st_layout.addLayout(st_img_h)

        # Feinjustierung Text (X/Y Slider)
        lbl_adj = QLabel("Text Feinjustierung (Innerhalb des Bildes):")
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

        # Skalierung
        st_layout.addWidget(QLabel("Bild Skalierung:"))
        self.slider_st_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_st_scale.setRange(10, 200)  # 0.1 bis 2.0
        st_layout.addWidget(self.slider_st_scale)

        layout.addWidget(stats_group)

        # --- KILLFEED BEREICH ---
        feed_group = QFrame(objectName="Group")
        kf_layout = QVBoxLayout(feed_group)

        kf_header = QLabel("--- KILLFEED ---")
        kf_header.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 16px;")
        kf_layout.addWidget(kf_header)

        # Headshot Icon
        kf_layout.addWidget(QLabel("Headshot Icon (PNG):", objectName="SubText"))
        hs_h = QHBoxLayout()
        self.ent_hs_icon = QLineEdit()
        btn_hs_browse = QPushButton("...")
        btn_hs_browse.setFixedWidth(40)
        hs_h.addWidget(self.ent_hs_icon)
        hs_h.addWidget(btn_hs_browse)
        kf_layout.addLayout(hs_h)

        self.check_show_revives = QCheckBox("Revives im Killfeed anzeigen")
        self.check_show_revives.setStyleSheet("color: #00ff00;")
        kf_layout.addWidget(self.check_show_revives)

        layout.addWidget(feed_group)

        # --- AKTION BUTTONS ---
        btn_box = QHBoxLayout()
        self.btn_save_stats = QPushButton("SAVE SETTINGS", objectName="SaveBtn")
        self.btn_edit_hud_stats = QPushButton("LAYOUT PER MAUS VERSCHIEBEN", objectName="EditBtn")
        self.btn_test_stats = QPushButton("TEST UI", objectName="TestBtn")

        btn_box.addWidget(self.btn_save_stats)
        btn_box.addWidget(self.btn_edit_hud_stats)
        btn_box.addWidget(self.btn_test_stats)
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
        layout.addWidget(self.btn_save_voice, alignment=Qt.AlignmentFlag.AlignCenter)  # Hier ist es korrektr)

        layout.addStretch()