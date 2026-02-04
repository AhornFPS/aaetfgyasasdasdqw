import sys
import time
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame,
                             QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
                             QComboBox)
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush

# --- 1. DESIGN & FARBEN ---
STYLESHEET = """
QWidget {
    background-color: #1a1a1a;
    color: #ffffff;
    font-family: 'Consolas', 'Segoe UI', sans-serif;
}

QLabel#TotalPlayers {
    font-size: 22px;
    font-weight: bold;
    color: #00f2ff;
    padding: 10px;
}

QTableWidget {
    background-color: #1a1a1a;
    border: none;
    gridline-color: #333333;
    font-size: 11px;
    selection-background-color: #00f2ff;
    selection-color: black;
}

QTableWidget::item { padding: 4px; }

QHeaderView::section {
    background-color: #141414;
    color: #00f2ff;
    padding: 5px;
    border: 1px solid #252525;
    font-weight: bold;
    font-size: 10px;
}

QProgressBar {
    background-color: #333333;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}

QProgressBar::chunk { border-radius: 4px; }

QComboBox {
    background-color: #2b2b2b;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 5px 10px;
    color: #00f2ff;
    font-weight: bold;
    min-width: 180px;
}
QComboBox:hover { border: 1px solid #00f2ff; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid #333333;
}
QComboBox QAbstractItemView {
    background-color: #1a1a1a;
    color: #ffffff;
    border: 1px solid #00f2ff;
    selection-background-color: #00f2ff;
    selection-color: #000000;
}
"""


# --- DATEN-SCHNITTSTELLE ---
class DashboardSignals(QObject):
    update_population = pyqtSignal(int)
    update_factions = pyqtSignal(dict)
    update_top_list = pyqtSignal(list)
    server_changed = pyqtSignal(str)


class DashboardController:
    def __init__(self, window):
        self.window = window
        self.signals = DashboardSignals()
        # WICHTIG: Referenz speichern
        self.window.dash_ctl = self

        self.signals.update_population.connect(self.window.graph.update_history)
        self.signals.update_population.connect(lambda val: self.window.lbl_total.setText(f"Total Players: {val}"))
        self.signals.update_factions.connect(self.update_faction_ui)
        self.signals.update_top_list.connect(self.update_top_list_ui)

    def update_faction_ui(self, data):
        total = sum(data.values())
        for name, count in data.items():
            if name in self.window.fac_boxes:
                perc = (count / total * 100) if total > 0 else 0
                self.window.fac_boxes[name].update_counts(perc, count)

    def update_top_list_ui(self, all_players):
        for name in ["TR", "NC", "VS"]:
            if name in self.window.fac_boxes:
                f_players = [p for p in all_players if p.get("fac") == name]
                self.window.fac_boxes[name].update_table(f_players)


# --- GUI KLASSEN ---

class TelemetryGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.pop_history = [0] * 100
        self.max_pop = 1500

    def update_history(self, new_val):
        self.pop_history.append(new_val)
        if len(self.pop_history) > 100:
            self.pop_history.pop(0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#050505"))
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawRect(0, 0, w, h)

        if not self.pop_history: return

        points = []
        step_x = w / (len(self.pop_history) - 1)
        for i, val in enumerate(self.pop_history):
            x = i * step_x
            y = h - (val * (h / self.max_pop))
            y = max(0, min(y, h))
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#00f2ff"), 2))
        painter.drawPolyline(points)

        painter.setPen(Qt.PenStyle.NoPen)
        fill_color = QColor("#00f2ff")
        fill_color.setAlpha(30)
        painter.setBrush(QBrush(fill_color))
        poly_points = [QPointF(0, h)] + points + [QPointF(w, h)]
        painter.drawPolygon(poly_points)


class FactionBox(QFrame):
    def __init__(self, name, color):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.lbl_name = QLabel(name)
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setStyleSheet(f"font-family: 'Arial'; font-size: 16px; font-weight: bold; color: {color};")
        layout.addWidget(self.lbl_name)

        self.lbl_perc = QLabel("0.0%")
        self.lbl_perc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_perc.setStyleSheet("font-family: 'Consolas'; font-size: 20px; font-weight: bold; color: white;")
        layout.addWidget(self.lbl_perc)

        self.lbl_count = QLabel("0 Players")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_count.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(self.lbl_count)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
        self.bar.setRange(0, 1000)
        layout.addWidget(self.bar)

        self.table = QTableWidget(10, 7)
        self.table.setHorizontalHeaderLabels(["PLAYER", "K", "KPM", "D", "A", "K/D", "KDA"])
        self.table.setMinimumHeight(300)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 35)

        layout.addWidget(self.table)

    def update_counts(self, perc, count):
        self.lbl_perc.setText(f"{perc:.1f}%")
        self.lbl_count.setText(f"{count} Players")
        self.bar.setValue(int(perc * 10))

    def update_table(self, players):
        self.table.clearContents()
        top_players = sorted(players, key=lambda x: x.get('k', 0), reverse=True)[:10]

        for row, p in enumerate(top_players):
            k, d, a = p.get('k', 0), p.get('d', 0), p.get('a', 0)
            active_min = p.get('active_min', 1.0)
            kpm = k / active_min
            kd = k / max(1, d)
            kda = (k + a) / max(1, d)

            col_kpm = self.get_kpm_color(kpm)
            col_kd = self.get_kpm_color(kd)

            items = [
                (p.get('name', 'Unknown'), "#cccccc"),
                (str(k), "white"),
                (f"{kpm:.1f}", col_kpm),
                (str(d), "white"),
                (str(a), "white"),
                (f"{kd:.1f}", col_kd),
                (f"{kda:.1f}", "#00f2ff")
            ]
            bg_color = QColor("#1d1d1d") if (row % 2 == 0) else QColor("#1a1a1a")

            for col, (text, fg_hex) in enumerate(items):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(fg_hex))
                item.setBackground(bg_color)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col > 0 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

    def get_kpm_color(self, val):
        if val >= 3.0: return "#e600ff"
        if val >= 2.0: return "#00f2ff"
        if val >= 1.0: return "#00ff00"
        return "#777777"


class DashboardWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller

        # Layout direkt auf self anwenden
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # --- HEADER (Titel & Server Dropdown) ---
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # HIER WAREN FRÜHER DIE BUTTONS (JETZT ENTFERNT)

        header_layout.addStretch()

        header_layout.addWidget(QLabel("SERVER:"))
        self.server_combo = QComboBox()
        self.server_map = {
            "Wainwright (EU)": "10",
            "Osprey (US)": "1",
            "SolTech (Asia)": "40",
            "Jaeger (Events)": "19"
        }
        self.server_combo.addItems(list(self.server_map.keys()))
        self.server_combo.currentTextChanged.connect(self.on_server_selected)
        header_layout.addWidget(self.server_combo)

        main_layout.addWidget(header_container)

        # --- GRAPH ---
        self.graph = TelemetryGraph()
        main_layout.addWidget(self.graph)

        # --- TOTAL PLAYERS ---
        self.lbl_total = QLabel("Total Players: 0")
        self.lbl_total.setObjectName("TotalPlayers")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_total)

        # --- FRAKTIONEN ---
        fac_layout = QHBoxLayout()
        fac_layout.setSpacing(15)

        self.fac_boxes = {}
        colors = {"TR": "#ff0000", "NC": "#0066ff", "VS": "#9900ff"}

        for name in ["TR", "NC", "VS"]:
            box = FactionBox(name, colors[name])
            self.fac_boxes[name] = box
            fac_layout.addWidget(box)

        main_layout.addLayout(fac_layout)

        # Footer
        self.lbl_footer = QLabel("Last Update: Live via Controller")
        self.lbl_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_footer.setStyleSheet("color: #444; font-size: 9px;")
        main_layout.addWidget(self.lbl_footer)

    def on_server_selected(self, server_name):
        world_id = self.server_map.get(server_name, "10")
        if self.controller:
            if hasattr(self.controller, 'dash_controller'):
                self.controller.dash_controller.signals.server_changed.emit(world_id)

        print(f"DEBUG: Server changed to {server_name} (ID: {world_id})")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = DashboardWidget()
    window.show()
    sys.exit(app.exec())