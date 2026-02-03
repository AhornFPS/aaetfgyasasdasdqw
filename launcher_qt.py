import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor


# --- SIGNALE ---
class LauncherSignals(QObject):
    # Sendet 'high' oder 'low' an das Hauptprogramm
    launch_requested = pyqtSignal(str)


# --- STYLESHEET ---
LAUNCHER_STYLE = """
QWidget#Launcher {
    background-color: #1a1a1a;
}
QFrame#ProfileCard {
    background-color: #252525;
    border: 2px solid #333;
    border-radius: 12px;
}
QFrame#ProfileCard:hover {
    border: 2px solid #00f2ff;
}
QLabel#Header {
    font-family: 'Arial';
    font-size: 26px;
    font-weight: bold;
    color: #00f2ff;
}
QLabel#ProfileTitle {
    font-size: 20px;
    font-weight: bold;
    font-family: 'Consolas';
}
QLabel#Description {
    color: #888;
    font-size: 11px;
    line-height: 15px;
}
QPushButton#LaunchBtn {
    border-radius: 6px;
    font-weight: bold;
    font-family: 'Consolas';
    font-size: 14px;
    padding: 15px;
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
}
QPushButton#LaunchBtn:hover {
    border: 1px solid white;
}
"""


class ProfileCard(QFrame):
    def __init__(self, title, subtitle, desc, color, mode, signal):
        super().__init__()
        self.setObjectName("ProfileCard")
        self.mode = mode
        self.signal = signal

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Sektion (z.B. [ VEHICLE ])
        lbl_sub = QLabel(f"[ {subtitle} ]")
        lbl_sub.setStyleSheet(f"color: {color}; font-weight: bold; font-family: 'Consolas';")
        layout.addWidget(lbl_sub)

        # Titel
        lbl_title = QLabel(title)
        lbl_title.setObjectName("ProfileTitle")
        layout.addWidget(lbl_title)

        # Beschreibung
        lbl_desc = QLabel(desc)
        lbl_desc.setObjectName("Description")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        layout.addStretch()

        # Action Button
        btn = QPushButton(f"INITIALIZE: {title}")
        btn.setObjectName("LaunchBtn")
        btn.setStyleSheet(f"background-color: {color};")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.on_click)
        layout.addWidget(btn)

    def on_click(self):
        self.signal.launch_requested.emit(self.mode)


class LauncherWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Launcher")
        self.setWindowTitle("Dior Client - Launcher")
        self.resize(1100, 650)

        # WICHTIG: Stylesheet anwenden
        self.setStyleSheet(LAUNCHER_STYLE)

        self.signals = LauncherSignals()

        # Layout direkt auf self (Korrekt!)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(50, 50, 50, 50)
        main_layout.setSpacing(30)

        # Header
        header = QLabel("> GAME_START_DASHBOARD")
        header.setObjectName("Header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        # Cards Container
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(25)

        # High Fidelity Card
        self.high_card = ProfileCard(
            "High Settings", "VEHICLE",
            "Load High Fidelity Assets & Maximum Visual Range. Perfect for pilots and tankers.",
            "#006600", "high", self.signals
        )

        # Performance Card
        self.low_card = ProfileCard(
            "Low Settings", "INFANTRY",
            "Disable Shadows & Particles for Peak Framerates. Optimized for competitive infantry play.",
            "#660000", "low", self.signals
        )

        cards_layout.addWidget(self.high_card)
        cards_layout.addWidget(self.low_card)
        main_layout.addLayout(cards_layout)

        # Info Footer
        self.lbl_info = QLabel("STATUS: SYSTEM_READY | INTEGRITY: OPTIMAL")
        self.lbl_info.setStyleSheet("color: #4a6a7a; font-family: 'Consolas'; font-size: 11px;")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_info)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Style ist jetzt in __init__, aber schadet hier nicht:
    app.setStyleSheet(LAUNCHER_STYLE)

    # KORREKTUR: Klassenname angepasst (war LauncherWindow)
    launcher = LauncherWidget()
    launcher.show()
    sys.exit(app.exec())