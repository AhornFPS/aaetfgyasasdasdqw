import sys
import time
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
                             QComboBox)
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF

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
    color: #888888;   /* <--- ÄNDERUNG: Standard ist Grau (damit Blau leuchtet) */
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
    update_db_count = pyqtSignal(int)


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


# --- GUI KLASSEN ---

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
        # Standard-Modus: Nur Total anzeigen
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

        # 1. HINTERGRUND & RAHMEN
        painter.fillRect(0, 0, w, h, QColor("#121212"))
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawRect(0, 0, w, h)

        # 2. DATEN AUSWÄHLEN (Je nach Modus)
        if self.show_factions:
            # Modus: FRACTIONS (Total + 3 Fraktionen)

            # Wir nehmen ALLE Listen zusammen (inkl. Total), um das Maximum für die Skala zu finden
            # Da 'Total' immer am höchsten ist, bestimmt es die Skala.
            all_visible_data = self.pop_history + self.faction_history["TR"] + self.faction_history["NC"] + \
                               self.faction_history["VS"]

            data_sets = [
                (self.pop_history, "#00f2ff"),  # Total (Cyan) - als Referenz
                (self.faction_history["TR"], "#de0b0b"),  # Rot
                (self.faction_history["NC"], "#007bff"),  # Blau
                (self.faction_history["VS"], "#9d00ff")  # Lila
            ]
        else:
            # Modus: ONLY TOTAL
            all_visible_data = self.pop_history
            data_sets = [
                (self.pop_history, "#00f2ff")  # Nur Total (Cyan)
            ]

        if not all_visible_data: return

        # 3. DYNAMISCHE SKALA BERECHNEN
        max_val = max(max(all_visible_data), 100)  # Mindestens 100
        max_val = int(max_val * 1.1)  # +10% Puffer

        # 4. GRID & LABELS ZEICHNEN
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

        # 5. GRAPHEN ZEICHNEN (Hilfsfunktion)
        def draw_layer(data, color_hex):
            if not data: return

            points = []
            step_x = w / (len(data) - 1) if len(data) > 1 else w

            # Punkte berechnen
            for i, val in enumerate(data):
                x = i * step_x
                normalized = val / max(1, max_val)
                y = h - (normalized * h)
                y = max(0, min(y, h))
                points.append(QPointF(x, y))

            if len(points) > 1:
                # Linie
                path_pen = QPen(QColor(color_hex), 2)
                painter.setPen(path_pen)
                painter.drawPolyline(points)

                # Füllung (Alpha 30) - Optional, sieht bei vielen Graphen manchmal chaotisch aus,
                # aber wir lassen es drin für den coolen Look.
                painter.setPen(Qt.PenStyle.NoPen)
                fill_color = QColor(color_hex)
                fill_color.setAlpha(30)
                painter.setBrush(QBrush(fill_color))

                poly_points = [QPointF(0, h)] + points + [QPointF(w, h)]
                painter.drawPolygon(QPolygonF(poly_points))

        # Alle aktiven Sets zeichnen
        # Wir zeichnen sie in der Reihenfolge der Liste.
        # Tipp: Wenn man will, dass 'Total' im Hintergrund liegt, müsste man die Liste sortieren.
        # Aber da 'Total' meist oben ist, passt es so.
        for d_list, col in data_sets:
            draw_layer(d_list, col)


class FactionBox(QFrame):
    def __init__(self, name, color):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header Labels
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
        # Die Spalten-Namen festlegen
        self.header_names = ["PLAYER", "K", "KPM", "D", "A", "K/D", "KDA"]
        self.table.setHorizontalHeaderLabels(self.header_names)

        self.table.setMinimumHeight(300)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Spaltenbreiten
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 35)

        # Interaktion aktivieren
        h.setSectionsClickable(True)
        h.sectionClicked.connect(self.on_header_clicked)

        layout.addWidget(self.table)

        # --- SORTIER STATUS ---
        # Standard: Spalte 1 (Kills)
        self.current_sort_col = 1
        self.current_sort_asc = False
        self.last_player_data = []

        # Initiales Header-Update (damit "K" direkt blau ist)
        self.update_header_visuals()

    def update_counts(self, perc, count):
        self.lbl_perc.setText(f"{perc:.1f}%")
        self.lbl_count.setText(f"{count} Players")
        self.bar.setValue(int(perc * 10))

    def on_header_clicked(self, index):
        """Umschalten der Sortierung bei Klick."""
        if index == self.current_sort_col:
            # Gleiche Spalte: Richtung umkehren
            self.current_sort_asc = not self.current_sort_asc
        else:
            # Neue Spalte: Aktivieren und Standard (High-to-Low) setzen
            self.current_sort_col = index
            self.current_sort_asc = False

        # Tabelle neu laden (Visuals + Daten)
        self.refresh_table_view()

    def update_header_visuals(self):
        """Färbt nur den aktiven Header blau, Rest grau."""
        for i, name in enumerate(self.header_names):
            item = self.table.horizontalHeaderItem(i)
            if not item:
                item = QTableWidgetItem(name)
                self.table.setHorizontalHeaderItem(i, item)

            # Text setzen (immer sauber ohne Pfeile)
            item.setText(name)

            if i == self.current_sort_col:
                # AKTIVE SPALTE: Neon Blau (#00f2ff)
                item.setForeground(QColor("#00f2ff"))
            else:
                # INAKTIVE SPALTE: Grau (#888888)
                item.setForeground(QColor("#888888"))

    def update_table(self, players):
        self.last_player_data = players
        self.refresh_table_view()

    def refresh_table_view(self):
        # 1. Visuelles Feedback (Farbe) aktualisieren
        self.update_header_visuals()

        self.table.clearContents()

        # 2. Daten vorbereiten (Werte berechnen)
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

        # 3. Sortieren
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

        # 4. Befüllen
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

        # Layout direkt auf self anwenden
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # --- HEADER (Titel & Server Dropdown) ---
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # BUTTON LINKS: KD MODE
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

        # ÄNDERUNG: Zuerst den Graph hinzufügen...
        main_layout.addWidget(self.graph)

        # ... dann den Controller-Bereich (Button) DARUNTER erstellen
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

        graph_ctrl_layout.addWidget(self.btn_toggle_graph)  # Button links
        graph_ctrl_layout.addStretch()  # Rest auffüllen (Button bleibt links)

        main_layout.addLayout(graph_ctrl_layout)

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

        self.lbl_db_count = QLabel("DB: 0", self)
        self.lbl_db_count.setStyleSheet("color: #666; font-family: 'Consolas'; font-size: 11px; font-weight: bold;")
        self.lbl_db_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.lbl_db_count.show()  # Wichtig, da es nicht im Layout liegt

    def on_toggle_kd_clicked(self):
        if self.controller:
            # Wir rufen direkt die Methode im MainClient auf,
            # da dieser die Logik und den State (kd_mode_revive) besitzt.
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
        # Positioniert das Label fest unten rechts (160px von rechts, 30px von unten)
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