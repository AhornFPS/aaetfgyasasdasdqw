import sys
import time
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
                             QComboBox)
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF

# --- 1. DESIGN & COLORS ---
STYLESHEET = """
QWidget {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a1a, stop:1 #121212);
    color: #ffffff;
    font-family: 'Consolas', 'Segoe UI', sans-serif;
}

QLabel#TotalPlayers {
    font-family: 'Black Ops One', sans-serif;
    font-size: 26px;
    font-weight: bold;
    color: #00f2ff;
    padding: 15px;
    text-transform: uppercase;
}

QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: #222222;
    font-size: 12px;
    selection-background-color: #00f2ff;
    selection-color: black;
}

QTableWidget::item { 
    padding: 6px; 
}

QHeaderView::section {
    background-color: #0a0a0a;
    color: #00f2ff;  
    padding: 10px;
    border: 1px solid #1a1a1a;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
    font-family: 'Black Ops One', sans-serif;
}

QProgressBar {
    background-color: #0a0a0a;
    border: 1px solid #333;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}

QProgressBar::chunk { 
    border-radius: 5px; 
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005577, stop:1 #00f2ff);
}

QComboBox {
    background-color: #0a0a0a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 8px 15px;
    color: #00f2ff;
    font-weight: bold;
    font-family: 'Black Ops One', sans-serif;
    min-width: 200px;
    text-transform: uppercase;
}

QComboBox:hover { 
    border: 1px solid #00f2ff; 
    background-color: #111;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left: 1px solid #444;
}

QComboBox QAbstractItemView {
    background-color: #0a0a0a;
    color: #ffffff;
    border: 1px solid #00f2ff;
    selection-background-color: #00f2ff;
    selection-color: #000000;
}
"""


# --- DATA INTERFACE ---
class DashboardSignals(QObject):
    update_population = pyqtSignal(int)
    update_factions = pyqtSignal(dict)
    update_top_list = pyqtSignal(list)
    server_changed = pyqtSignal(str)
    update_db_count = pyqtSignal(int)


class DashboardController:
    def __init__(self, window):
        self.window = window
        self.signals = DashboardSignals()
        # IMPORTANT: Save reference
        self.window.dash_ctl = self

        self.signals.update_population.connect(self.window.graph.update_history)
        self.signals.update_population.connect(lambda val: self.window.lbl_total.setText(f"Total Players: {val}"))
        self.signals.update_factions.connect(self.update_faction_ui)
        self.signals.update_top_list.connect(self.update_top_list_ui)
        self.signals.update_db_count.connect(lambda c: self.window.lbl_db_count.setText(f"UNIQUE DB: {c:,}"))

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


# --- GUI CLASSES ---

class TelemetryGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.pop_history = [0] * 100
        self.faction_history = {
            "TR": [0] * 100,
            "NC": [0] * 100,
            "VS": [0] * 100
        }
        # Default mode: Only show total
        self.show_factions = False

    def update_history(self, total, faction_data=None):
        self.pop_history.append(total)
        if len(self.pop_history) > 100: self.pop_history.pop(0)

        if faction_data:
            for fac in ["TR", "NC", "VS"]:
                val = faction_data.get(fac, 0)
                self.faction_history[fac].append(val)
                if len(self.faction_history[fac]) > 100: self.faction_history[fac].pop(0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 1. BACKGROUND & FRAME
        painter.fillRect(0, 0, w, h, QColor("#121212"))
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawRect(0, 0, w, h)

        # 2. SELECT DATA (Depending on mode)
        if self.show_factions:
            # Mode: FACTIONS (Total + 3 factions)

            # We take ALL lists together (incl. Total) to find the maximum for the scale
            # Since 'Total' is always the highest, it determines the scale.
            all_visible_data = self.pop_history + self.faction_history["TR"] + self.faction_history["NC"] + \
                               self.faction_history["VS"]

            data_sets = [
                (self.pop_history, "#00f2ff"),  # Total (Cyan) - as reference
                (self.faction_history["TR"], "#de0b0b"),  # Red
                (self.faction_history["NC"], "#007bff"),  # Blue
                (self.faction_history["VS"], "#9d00ff")  # Purple
            ]
        else:
            # Mode: ONLY TOTAL
            all_visible_data = self.pop_history
            data_sets = [
                (self.pop_history, "#00f2ff")  # Only Total (Cyan)
            ]

        if not all_visible_data: return

        # 3. CALCULATE DYNAMIC SCALE
        max_val = max(max(all_visible_data), 100)  # Minimum 100
        max_val = int(max_val * 1.1)  # +10% buffer

        # 4. DRAW GRID & LABELS
        grid_pen = QPen(QColor(40, 40, 40), 1, Qt.PenStyle.DashLine)
        text_pen = QPen(QColor(100, 100, 100))
        painter.setFont(self.font())

        steps = 4
        for i in range(1, steps + 1):
            val = int(max_val * (i / steps))
            y_pos = h - (val / max_val * h)

            # Linie
            painter.setPen(grid_pen)
            painter.drawLine(0, int(y_pos), w, int(y_pos))

            # Text
            painter.setPen(text_pen)
            painter.drawText(5, int(y_pos) - 2, str(val))

        # 5. DRAW GRAPHS (Helper function)
        def draw_layer(data, color_hex):
            if not data: return

            points = []
            step_x = w / (len(data) - 1) if len(data) > 1 else w

            # Calculate points
            for i, val in enumerate(data):
                x = i * step_x
                normalized = val / max(1, max_val)
                y = h - (normalized * h)
                y = max(0, min(y, h))
                points.append(QPointF(x, y))

            if len(points) > 1:
                # Line
                path_pen = QPen(QColor(color_hex), 2)
                painter.setPen(path_pen)
                painter.drawPolyline(points)

                # Filling (Alpha 30) - Optional, can look messy with many graphs,
                # but we keep it for the cool look.
                painter.setPen(Qt.PenStyle.NoPen)
                fill_color = QColor(color_hex)
                fill_color.setAlpha(30)
                painter.setBrush(QBrush(fill_color))

                poly_points = [QPointF(0, h)] + points + [QPointF(w, h)]
                painter.drawPolygon(QPolygonF(poly_points))

        # Draw all active sets
        # We draw them in the order of the list.
        # Tip: If you want 'Total' in the background, you'd need to sort the list.
        # But since 'Total' is usually on top, this works.
        for d_list, col in data_sets:
            draw_layer(d_list, col)


class FactionBox(QFrame):
    def __init__(self, name, color):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header labels
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

        # --- TABLE SETUP ---
        self.table = QTableWidget(15, 7)
        # Set column names
        self.header_names = ["PLAYER", "K", "KPM", "D", "A", "K/D", "KDA"]
        self.table.setHorizontalHeaderLabels(self.header_names)

        self.table.setMinimumHeight(300)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Column widths
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 35)

        # Activate interaction
        h.setSectionsClickable(True)
        h.sectionClicked.connect(self.on_header_clicked)

        layout.addWidget(self.table)

        # --- SORTIER STATUS ---
        # Standard: Spalte 1 (Kills)
        self.current_sort_col = 1
        self.current_sort_asc = False
        self.last_player_data = []

        # Initial header update (so "K" is blue right away)
        self.update_header_visuals()

    def update_counts(self, perc, count):
        self.lbl_perc.setText(f"{perc:.1f}%")
        self.lbl_count.setText(f"{count} Players")
        self.bar.setValue(int(perc * 10))

    def on_header_clicked(self, index):
        """Toggle sorting on click."""
        if index == self.current_sort_col:
            # Same column: reverse direction
            self.current_sort_asc = not self.current_sort_asc
        else:
            # New column: activate and set default (high-to-low) set
            self.current_sort_col = index
            self.current_sort_asc = False

        # Reload table (visuals + data)
        self.refresh_table_view()

    def update_header_visuals(self):
        """Colors only active header blue, others grey."""
        for i, name in enumerate(self.header_names):
            item = self.table.horizontalHeaderItem(i)
            if not item:
                item = QTableWidgetItem(name)
                self.table.setHorizontalHeaderItem(i, item)

            # Set text (always clean without arrows)
            item.setText(name)

            if i == self.current_sort_col:
                # ACTIVE COLUMN: Neon Blue (#00f2ff)
                item.setForeground(QColor("#00f2ff"))
            else:
                # INACTIVE COLUMN: Grey (#888888)
                item.setForeground(QColor("#888888"))

    def update_table(self, players):
        self.last_player_data = players
        self.refresh_table_view()

    def refresh_table_view(self):
        # 1. Update visual feedback (color)
        self.update_header_visuals()

        self.table.clearContents()

        # 2. Prepare data (calculate values)
        enriched_data = []
        for p in self.last_player_data:
            k = p.get('k', 0)
            d = p.get('d', 0)
            a = p.get('a', 0)
            active_min = p.get('active_min', 1.0)

            p_sort = p.copy()
            p_sort.update({
                '_kpm': k / active_min if active_min > 0 else 0,
                '_kd': k / max(1, d),
                '_kda': (k + a) / max(1, d)
            })
            enriched_data.append(p_sort)

        # 3. Sorting
        key_map = {
            0: lambda x: x.get('name', '').lower(),
            1: lambda x: x.get('k', 0),
            2: lambda x: x.get('_kpm', 0),
            3: lambda x: x.get('d', 0),
            4: lambda x: x.get('a', 0),
            5: lambda x: x.get('_kd', 0),
            6: lambda x: x.get('_kda', 0)
        }
        sort_key = key_map.get(self.current_sort_col, lambda x: x.get('k', 0))

        sorted_players = sorted(
            enriched_data,
            key=sort_key,
            reverse=not self.current_sort_asc
        )[:15]

        # 4. Fill table
        for row, p in enumerate(sorted_players):
            k, d, a = p.get('k', 0), p.get('d', 0), p.get('a', 0)
            kpm, kd, kda = p.get('_kpm'), p.get('_kd'), p.get('_kda')

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
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if col == 0 else Qt.AlignmentFlag.AlignCenter
                item.setTextAlignment(align)
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

        # Apply layout directly to self
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # --- HEADER (Titel & Server Dropdown) ---
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # LEFT BUTTON: KD MODE
        self.btn_toggle_kd = QPushButton("KD MODE: REVIVE")
        self.btn_toggle_kd.setFixedWidth(120)
        self.btn_toggle_kd.setStyleSheet("""
            QPushButton { 
                background-color: #2b2b2b; color: #00ff00; border: 1px solid #333; 
                font-size: 10px; font-weight: bold; padding: 4px; 
            }
            QPushButton:hover { border: 1px solid #00ff00; }
        """)
        self.btn_toggle_kd.clicked.connect(self.on_toggle_kd_clicked)
        header_layout.addWidget(self.btn_toggle_kd)

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

        # CHANGE: First add the graph...
        main_layout.addWidget(self.graph)

        # ... then create the controller area (button) BELOW it
        graph_ctrl_layout = QHBoxLayout()
        self.btn_toggle_graph = QPushButton("MODE: ALL PLAYERS")
        self.btn_toggle_graph.setFixedWidth(150)
        self.btn_toggle_graph.setStyleSheet("""
                    QPushButton { 
                        background-color: #2b2b2b; color: #00f2ff; border: 1px solid #333; 
                        font-size: 10px; font-weight: bold; padding: 4px; 
                    }
                    QPushButton:hover { border: 1px solid #00f2ff; }
                """)
        self.btn_toggle_graph.clicked.connect(self.toggle_graph_mode)

        graph_ctrl_layout.addWidget(self.btn_toggle_graph)  # Button left
        graph_ctrl_layout.addStretch()  # Fill rest (Button remains left)

        main_layout.addLayout(graph_ctrl_layout)

        # --- TOTAL PLAYERS ---
        self.lbl_total = QLabel("Total Players: 0")
        self.lbl_total.setObjectName("TotalPlayers")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_total)

        # --- FACTIONS ---
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

        self.lbl_db_count = QLabel("DB: 0", self)
        self.lbl_db_count.setStyleSheet("color: #666; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        self.lbl_db_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.lbl_db_count.show()  # Important, as it's not in the layout

    def on_toggle_kd_clicked(self):
        if self.controller:
            # We call the method in MainClient directly,
            # as it holds the logic and state (kd_mode_revive).
            if hasattr(self.controller, 'toggle_kd_mode'):
                self.controller.toggle_kd_mode()
            else:
                print("DEBUG: Controller has no toggle_kd_mode method")
        else:
            print("DEBUG: No Controller connected")

    def toggle_graph_mode(self):
        self.graph.show_factions = not self.graph.show_factions
        if self.graph.show_factions:
            self.btn_toggle_graph.setText("MODE: FACTIONS")
        else:
            self.btn_toggle_graph.setText("MODE: ALL PLAYERS")
        self.graph.update()

    def on_server_selected(self, server_name):
        world_id = self.server_map.get(server_name, "10")
        if self.controller:
            if hasattr(self.controller, 'dash_controller'):
                self.controller.dash_controller.signals.server_changed.emit(world_id)

        print(f"DEBUG: Server changed to {server_name} (ID: {world_id})")

    def resizeEvent(self, event):
        # Positions the label fixed at bottom right (160px from right, 30px from bottom)
        if hasattr(self, 'lbl_db_count'):
            w = self.width()
            h = self.height()
            self.lbl_db_count.setGeometry(w - 160, h - 30, 150, 20)
        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = DashboardWidget()
    window.show()
    sys.exit(app.exec())