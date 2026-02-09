import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QSlider)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

# --- STYLING ---
SETTING_STYLE = """
QWidget#Settings { background-color: #1a1a1a; }

QFrame#Group { 
    background-color: #252525; 
    border: 1px solid #333; 
    border-radius: 8px; 
    margin-top: 10px;
}
QLabel#GroupTitle { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 14px; 
    font-family: 'Consolas';
    padding-bottom: 5px;
}
QLabel#InfoText { color: #888; font-size: 11px; }
QLabel#PathLabel { 
    color: #ffffff; 
    background-color: #111; 
    border: 1px solid #444; 
    padding: 8px; 
    border-radius: 4px;
    font-family: 'Consolas';
}

QPushButton#ActionBtn { 
    background-color: #2a2a2a; 
    color: #00f2ff; 
    border: 1px solid #444; 
    padding: 8px 15px; 
    font-weight: bold; 
    border-radius: 4px; 
    font-size: 12px;
}
QPushButton#ActionBtn:hover { 
    background-color: #3a3a3a; 
    border-color: #00f2ff; 
    color: white;
}

QPushButton#SaveBtn {
    background-color: #004400;
    color: #00ff00;
    font-weight: bold;
    border-radius: 4px;
    padding: 10px 15px;
    font-size: 12px;
    border: 1px solid #006600;
}
QPushButton#SaveBtn:hover { 
    background-color: #006600; 
    border-color: #00ff00; 
    color: white;
}
"""


class SettingsSignals(QObject):
    save_requested = pyqtSignal(dict)  # Sendet die Config-Daten an Main
    browse_ps2_requested = pyqtSignal()  # Trigger für Folder-Dialog
    change_bg_requested = pyqtSignal()  # Trigger für Background-Dialog


class SettingsWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Settings")
        self.setStyleSheet(SETTING_STYLE)

        self.signals = SettingsSignals()

        # Layout Setup
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # Headline
        head = QLabel("GLOBAL CONFIGURATION")
        head.setStyleSheet("font-size: 24px; color: #00f2ff; font-weight: bold; font-family: 'Impact';")
        main_layout.addWidget(head)

        # --- GROUP 1: GAME PATH ---
        self.game_group = QFrame(objectName="Group")
        game_layout = QVBoxLayout(self.game_group)
        game_layout.setContentsMargins(15, 15, 15, 15)

        game_layout.addWidget(QLabel("> PLANETSIDE 2 DIRECTORY", objectName="GroupTitle"))
        game_layout.addWidget(QLabel("Required for UserOptions.ini modifications (Launcher)", objectName="InfoText"))

        # Path Display & Button
        path_row = QHBoxLayout()
        self.lbl_ps2_path = QLabel("Checking config...", objectName="PathLabel")
        self.lbl_ps2_path.setMinimumWidth(300)

        self.btn_ps2 = QPushButton("BROWSE FOLDER", objectName="ActionBtn")
        self.btn_ps2.setFixedWidth(150)
        self.btn_ps2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ps2.clicked.connect(lambda: self.signals.browse_ps2_requested.emit())

        path_row.addWidget(self.lbl_ps2_path)
        path_row.addWidget(self.btn_ps2)
        game_layout.addLayout(path_row)

        main_layout.addWidget(self.game_group)

        # --- GROUP 2: AUDIO ---
        self.audio_group = QFrame(objectName="Group")
        audio_layout = QVBoxLayout(self.audio_group)
        audio_layout.setContentsMargins(15, 15, 15, 15)

        audio_layout.addWidget(QLabel("> AUDIO SETTINGS", objectName="GroupTitle"))

        # Volume Slider
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Master Volume:", styleSheet="color: white;"))

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(50)
        self.slider_vol.setStyleSheet("QSlider::handle:horizontal { background-color: #00f2ff; }")

        self.lbl_vol_val = QLabel("50%")
        self.lbl_vol_val.setStyleSheet("color: #00f2ff; font-weight: bold; width: 40px;")

        # --- WICHTIG: AUTOMATISCHES SPEICHERN ---

        # 1. Visuelles Update beim Ziehen (ändert nur Text)
        self.slider_vol.valueChanged.connect(self.update_volume_label)

        # 2. Speichern beim Loslassen (Performance!)
        self.slider_vol.sliderReleased.connect(self.request_save)

        vol_row.addWidget(self.slider_vol)
        vol_row.addWidget(self.lbl_vol_val)
        audio_layout.addLayout(vol_row)

        main_layout.addWidget(self.audio_group)

        # --- GROUP 3: UI VISUALS ---
        self.ui_group = QFrame(objectName="Group")
        ui_layout = QVBoxLayout(self.ui_group)
        ui_layout.setContentsMargins(15, 15, 15, 15)

        ui_layout.addWidget(QLabel("> CLIENT APPEARANCE", objectName="GroupTitle"))

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("Menu Background Image:", styleSheet="color: #aaa;"))

        self.btn_bg = QPushButton("CHANGE IMAGE", objectName="ActionBtn")
        self.btn_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bg.clicked.connect(lambda: self.signals.change_bg_requested.emit())

        bg_row.addWidget(self.btn_bg)
        ui_layout.addLayout(bg_row)

        main_layout.addWidget(self.ui_group)

        # Spacer nach unten
        main_layout.addStretch()

        # --- SAVE BUTTON (Manual) ---
        self.btn_save = QPushButton("SAVE SETTINGS", objectName="SaveBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        # Auch der Button nutzt jetzt die zentrale request_save Methode
        self.btn_save.clicked.connect(self.request_save)
        main_layout.addWidget(self.btn_save)

    def load_config(self, config_data, ps2_dir):
        """Füllt die Felder mit den aktuellen Werten."""
        # 1. Pfad
        self.lbl_ps2_path.setText(ps2_dir if ps2_dir else "NOT_FOUND (Please Browse)")

        # 2. Audio Volume
        vol = config_data.get("audio_volume", 50)

        # --- WICHTIG: Signale blockieren beim Laden ---
        # Verhindert, dass das Setzen des Wertes ein "Speichern"-Event auslöst
        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(int(vol))
        self.slider_vol.blockSignals(False)

        self.lbl_vol_val.setText(f"{vol}%")

    def update_volume_label(self, val):
        """Nur für die Optik beim Ziehen."""
        self.lbl_vol_val.setText(f"{val}%")

    def request_save(self):
        """Sammelt Daten und sendet sie an Main (zum Speichern)."""
        data = {
            "audio_volume": self.slider_vol.value()
        }
        # Signal senden
        self.signals.save_requested.emit(data)
