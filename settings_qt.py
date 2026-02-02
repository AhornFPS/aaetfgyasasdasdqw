import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFrame, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QObject


class SettingsSignals(QObject):
    save_requested = pyqtSignal(dict)
    browse_obs_requested = pyqtSignal()
    browse_ps2_requested = pyqtSignal()
    change_bg_requested = pyqtSignal()


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
    font-size: 12px; 
    font-family: 'Consolas';
}
QLabel#FieldLabel { color: #4a6a7a; font-size: 11px; }
QLineEdit { 
    background-color: #0a141d; 
    color: #00f2ff; 
    border: 1px solid #333; 
    padding: 8px; 
    border-radius: 4px;
}
QPushButton#ActionBtn { 
    background-color: #1a2b3c; 
    color: #00f2ff; 
    border: none; 
    padding: 8px 15px; 
    font-weight: bold;
}
QPushButton#ActionBtn:hover { background-color: #00f2ff; color: black; }
QPushButton#SaveBtn { 
    background-color: #00f2ff; 
    color: black; 
    font-weight: bold; 
    padding: 12px; 
    border-radius: 4px;
}
"""


class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Settings")
        self.resize(600, 750)
        self.signals = SettingsSignals()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        # --- SOURCE CONFIG (OBS & Streamable) ---
        self.config_group = QFrame(objectName="Group")
        conf_layout = QVBoxLayout(self.config_group)
        conf_layout.addWidget(QLabel("> SOURCE_CONFIG", objectName="GroupTitle"))

        # OBS Dir
        conf_layout.addWidget(QLabel("OBS_VIDEO_DIR:", objectName="FieldLabel"))
        obs_h = QHBoxLayout()
        self.obs_entry = QLineEdit()
        self.btn_obs = QPushButton("BROWSE", objectName="ActionBtn")
        self.btn_obs.clicked.connect(lambda: self.signals.browse_obs_requested.emit())
        obs_h.addWidget(self.obs_entry)
        obs_h.addWidget(self.btn_obs)
        conf_layout.addLayout(obs_h)

        # Email
        conf_layout.addWidget(QLabel("STREAMABLE.IO EMAIL:", objectName="FieldLabel"))
        self.email_entry = QLineEdit()
        conf_layout.addWidget(self.email_entry)

        # Password
        conf_layout.addWidget(QLabel("STREAMABLE.IO PW:", objectName="FieldLabel"))
        self.pw_entry = QLineEdit()
        self.pw_entry.setEchoMode(QLineEdit.EchoMode.Password)
        conf_layout.addWidget(self.pw_entry)

        self.btn_save = QPushButton("LOCK SETTINGS", objectName="SaveBtn")
        self.btn_save.clicked.connect(self.collect_and_save)
        conf_layout.addWidget(self.btn_save)

        main_layout.addWidget(self.config_group)

        # --- GAME DIRECTORY ---
        self.game_group = QFrame(objectName="Group")
        game_layout = QVBoxLayout(self.game_group)
        game_layout.addWidget(QLabel("> GAME_DIRECTORY", objectName="GroupTitle"))

        path_h = QHBoxLayout()
        path_h.addWidget(QLabel("Pfad:", objectName="FieldLabel"))
        self.lbl_ps2_path = QLabel("Not set")
        self.lbl_ps2_path.setStyleSheet("color: #888; font-size: 10px;")
        self.lbl_ps2_path.setWordWrap(True)
        path_h.addWidget(self.lbl_ps2_path, 1)
        game_layout.addLayout(path_h)

        self.btn_ps2 = QPushButton("ORDNER WÄHLEN", objectName="ActionBtn")
        self.btn_ps2.clicked.connect(lambda: self.signals.browse_ps2_requested.emit())
        game_layout.addWidget(self.btn_ps2)

        main_layout.addWidget(self.game_group)

        # --- UI VISUALS ---
        self.ui_group = QFrame(objectName="Group")
        ui_layout = QVBoxLayout(self.ui_group)
        ui_layout.addWidget(QLabel("> UI_VISUALS", objectName="GroupTitle"))

        self.btn_bg = QPushButton("HINTERGRUND ÄNDERN", objectName="ActionBtn")
        self.btn_bg.clicked.connect(lambda: self.signals.change_bg_requested.emit())
        ui_layout.addWidget(self.btn_bg)

        main_layout.addWidget(self.ui_group)
        main_layout.addStretch()

    def load_config(self, config_data, ps2_dir):
        """Füllt die Felder mit den aktuellen Werten"""
        self.obs_entry.setText(config_data.get("watch_folder", ""))
        self.email_entry.setText(config_data.get("email", ""))
        self.pw_entry.setText(config_data.get("pw", ""))
        self.lbl_ps2_path.setText(ps2_dir if ps2_dir else "NOT_FOUND")

    def collect_and_save(self):
        data = {
            "watch_folder": self.obs_entry.text(),
            "email": self.email_entry.text(),
            "pw": self.pw_entry.text()
        }
        self.signals.save_requested.emit(data)