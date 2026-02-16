import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QSlider, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

# --- STYLING ---
SETTING_STYLE = """
QWidget#Settings { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a1a, stop:1 #121212); 
}

QFrame#Group { 
    background-color: rgba(35, 35, 35, 0.7); 
    border: 1px solid #333; 
    border-radius: 12px; 
    margin-top: 15px;
    padding: 10px;
}

QFrame#Group:hover {
    border: 1px solid #444;
    background-color: rgba(45, 45, 45, 0.8);
}

QLabel#GroupTitle { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 16px; 
    font-family: 'Black Ops One', sans-serif;
    padding-bottom: 8px;
    text-transform: uppercase;
}

QLabel#InfoText { 
    color: #888; 
    font-size: 12px; 
    margin-bottom: 5px;
}

QLabel#PathLabel { 
    color: #ffffff; 
    background-color: #050505; 
    border: 1px solid #333; 
    padding: 12px; 
    border-radius: 6px;
    font-family: 'Consolas', monospace;
}

QPushButton#ActionBtn { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333, stop:1 #222);
    color: #00f2ff; 
    border: 1px solid #444; 
    padding: 10px 20px; 
    font-weight: bold; 
    border-radius: 6px; 
    font-size: 13px;
    text-transform: uppercase;
}

QPushButton#ActionBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #333);
    border-color: #00f2ff; 
    color: white;
}

QPushButton#SaveBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #006600, stop:1 #003300);
    color: #00ff00;
    font-weight: bold;
    border-radius: 6px;
    padding: 15px 25px;
    font-size: 14px;
    border: 1px solid #00ff00;
    text-transform: uppercase;
}

QPushButton#SaveBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00aa00, stop:1 #005500); 
    border-color: #ffffff; 
    color: white;
}

QPushButton#ClearBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #440000, stop:1 #220000);
    color: #ff4444; 
    border: 1px solid #660000; 
    padding: 10px 20px; 
    font-weight: bold; 
    border-radius: 6px; 
    font-size: 13px;
    text-transform: uppercase;
}

QPushButton#ClearBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #660000, stop:1 #440000);
    border-color: #ff0000; 
    color: white;
}

/* Custom Slider Styling */
QSlider::groove:horizontal {
    border: 1px solid #333;
    height: 6px;
    background: #111;
    margin: 2px 0;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f2ff, stop:1 #006666);
    border: 1px solid #00f2ff;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #ffffff;
    border: 1px solid #00f2ff;
}
"""


class SettingsSignals(QObject):
    save_requested = pyqtSignal(dict)  # Sendet die Config-Daten an Main
    browse_ps2_requested = pyqtSignal()  # Trigger für Folder-Dialog
    browse_bg_requested = pyqtSignal()  # Trigger for Background-Dialog
    clear_bg_requested = pyqtSignal()   # Trigger for Background Reset
    check_updates_requested = pyqtSignal()  # Trigger for release update checks


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
        self.slider_vol.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.slider_vol.setStyleSheet("QSlider::handle:horizontal { background-color: #00f2ff; }")

        self.lbl_vol_val = QLabel("50%")
        self.lbl_vol_val.setFixedWidth(40)
        self.lbl_vol_val.setStyleSheet("color: #00f2ff; font-weight: bold; font-family: Consolas;")
        self.lbl_vol_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # --- WICHTIG: AUTOMATISCHES SPEICHERN ---

        # 1. Visuelles Update beim Ziehen (ändert nur Text)
        self.slider_vol.valueChanged.connect(self.update_volume_label)

        # 2. Speichern beim Loslassen (Performance!)
        self.slider_vol.sliderReleased.connect(self.request_save)

        vol_row.addWidget(self.slider_vol)
        vol_row.addWidget(self.lbl_vol_val)
        audio_layout.addLayout(vol_row)
        
        # Audio Device Selector
        device_row = QHBoxLayout()
        device_row.addWidget(QLabel("Output Device:", styleSheet="color: white;"))
        
        self.combo_audio_device = QComboBox()
        self.combo_audio_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_audio_device.setStyleSheet("""
            QComboBox {
                background-color: #111;
                border: 1px solid #444;
                color: #eee;
                padding: 6px;
                border-radius: 3px;
            }
            QComboBox:focus { 
                border: 1px solid #00f2ff; 
                background-color: #000; 
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #111;
                color: #eee;
                border: 1px solid #333;
                selection-background-color: #00f2ff;
                selection-color: #000;
            }
        """)
        
        self.populate_audio_devices()
        self.combo_audio_device.currentIndexChanged.connect(self.request_save)
        
        device_row.addWidget(self.combo_audio_device)
        audio_layout.addLayout(device_row)

        main_layout.addWidget(self.audio_group)

        # --- GROUP 3: UI VISUALS ---
        self.ui_group = QFrame(objectName="Group")
        ui_layout = QVBoxLayout(self.ui_group)
        ui_layout.setContentsMargins(15, 15, 15, 15)

        ui_layout.addWidget(QLabel("> CLIENT APPEARANCE", objectName="GroupTitle"))

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("Menu Background Image:", styleSheet="color: #aaa;"))
        
        self.lbl_bg_name = QLabel("No image selected", objectName="PathLabel")
        self.lbl_bg_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_bg = QPushButton("CHANGE IMAGE", objectName="ActionBtn")
        self.btn_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bg.clicked.connect(lambda: self.signals.browse_bg_requested.emit())

        self.btn_clear_bg = QPushButton("CLEAR", objectName="ClearBtn")
        self.btn_clear_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_bg.clicked.connect(lambda: self.signals.clear_bg_requested.emit())

        bg_row.addWidget(self.lbl_bg_name)
        bg_row.addWidget(self.btn_bg)
        bg_row.addWidget(self.btn_clear_bg)
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

        self.btn_check_updates = QPushButton("CHECK FOR UPDATES", objectName="ActionBtn")
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.clicked.connect(lambda: self.signals.check_updates_requested.emit())
        main_layout.addWidget(self.btn_check_updates)

    def populate_audio_devices(self):
        self.combo_audio_device.clear()
        self.combo_audio_device.addItem("Default")
        devices_added = set()
        
        try:
            import pygame
            import pygame._sdl2.audio as sdl2_audio

            # Ensure minimal init for listing
            if not pygame.get_init():
                pygame.init()
            
            # Need audio subsystem initialized to list
            if not pygame.mixer.get_init():
                try: pygame.mixer.init()
                except: pass

            try:
                # SDL2 device names (these are what the overlay uses)
                candidates = sdl2_audio.get_audio_device_names(False)
                for dev in candidates:
                    if dev not in devices_added:
                        self.combo_audio_device.addItem(dev)
                        devices_added.add(dev)
            except Exception as e:
                print(f"Audio List Error: {e}")
            
            # On Linux, also try pactl as backup if SDL2 found nothing
            if not devices_added and sys.platform != "win32":
                try:
                    import subprocess
                    result = subprocess.run(
                        ["pactl", "list", "sinks"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in result.stdout.split('\n'):
                        stripped = line.strip()
                        if stripped.startswith('Description:'):
                            desc = stripped.split(':', 1)[1].strip()
                            if desc not in devices_added:
                                self.combo_audio_device.addItem(desc)
                                devices_added.add(desc)
                except Exception:
                    pass

        except Exception as e:
            print(f"Audio Enum Error: {e}")

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
        
        # 3. Audio Device
        device = config_data.get("audio_device", "Default")
        self.combo_audio_device.blockSignals(True)
        index = self.combo_audio_device.findText(device)
        if index >= 0:
            self.combo_audio_device.setCurrentIndex(index)
        else:
            self.combo_audio_device.setCurrentIndex(0) # Default
        self.combo_audio_device.blockSignals(False)

        # 4. Background Path
        bg_path = config_data.get("main_background_path", "")
        if bg_path:
            import os
            self.lbl_bg_name.setText(os.path.basename(bg_path))
        else:
            self.lbl_bg_name.setText("None")

    def update_volume_label(self, val):
        """Nur für die Optik beim Ziehen."""
        self.lbl_vol_val.setText(f"{val}%")

    def request_save(self):
        """Sammelt Daten und sendet sie an Main (zum Speichern)."""
        data = {
            "audio_volume": self.slider_vol.value(),
            "audio_device": self.combo_audio_device.currentText(),
            "main_background_path": self.lbl_bg_name.text() if self.lbl_bg_name.text() != "None" else ""
        }
        # Signal senden
        self.signals.save_requested.emit(data)


