import json
import os
import sys
import threading
import time
import requests
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QFrame, QTabWidget, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QObject


# --- SIGNALE ---
class CharacterSignals(QObject):
    # Von GUI -> Logik (Triggert run_search)
    search_requested = pyqtSignal(str)

    # Von Logik -> GUI (Triggert process_search_results_qt)
    search_finished = pyqtSignal(dict, list)


# --- STYLESHEET ---
CHAR_STYLE = """
QWidget#Characters { background-color: #1a1a1a; }
QTabWidget::pane { border: 1px solid #333; background: #121212; top: -1px; }
QTabBar::tab { background: #1a1a1a; color: #888; padding: 10px 20px; border: 1px solid #333; border-bottom: none; }
QTabBar::tab:selected { background: #121212; color: #00f2ff; font-weight: bold; border-bottom: 2px solid #00f2ff; }
QFrame#StatCard { background-color: #1a1a1a; border: 1px solid #333; border-radius: 5px; }
QLabel#GroupTitle { color: #00f2ff; font-weight: bold; font-size: 13px; margin-bottom: 5px; }
QLabel#StatLabel { color: #4a6a7a; font-size: 11px; }
QLabel#StatValue { color: white; font-weight: bold; font-size: 14px; }
QTableWidget { background-color: #121212; border: none; color: white; gridline-color: #1a1a1a; }
QHeaderView::section { background-color: #1a1a1a; color: #00f2ff; padding: 5px; border: none; font-weight: bold; }
QTextEdit#LogArea { background-color: #020508; color: #00f2ff; font-family: 'Consolas'; font-size: 10px; border: 1px solid #333; }
QLineEdit { background-color: #222; color: white; border: 1px solid #444; padding: 5px; }
"""


class CharacterWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Characters")
        self.resize(1000, 900)


        # WICHTIG: Stylesheet anwenden
        self.setStyleSheet(CHAR_STYLE)

        # Signale initialisieren
        self.signals = CharacterSignals()

        # Instanzattribute
        self.info_labels = {}
        self.stats_ui = {}
        self.directive_overview_labels = {}
        self.weapon_table = QTableWidget(0, 4)
        self.directives_db = self.load_directives_db()

        # Layout direkt auf self anwenden
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- 1. TITEL & SUCHE ---
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("CHARACTER ANALYSIS")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00f2ff;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter Character Name...")
        self.search_input.setFixedWidth(250)
        self.search_input.returnPressed.connect(self.trigger_search)

        self.btn_search = QPushButton("SEARCH")
        self.btn_search.clicked.connect(self.trigger_search)
        self.btn_search.setStyleSheet("background: #333; color: #00f2ff; padding: 5px 15px;")

        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.search_input)
        header_layout.addWidget(self.btn_search)
        main_layout.addLayout(header_layout)

        # --- 2. TABS ---
        self.tabs = QTabWidget()
        self.overview_tab = QWidget()
        self.setup_overview_tab()
        self.tabs.addTab(self.overview_tab, "OVERVIEW")
        self.weapon_tab = QWidget()
        self.setup_weapon_tab()
        self.tabs.addTab(self.weapon_tab, "WEAPON STATS")
        
        self.directive_tab = QWidget()
        self.directive_table = QTableWidget(0, 3) # Name, Tier, Progress
        self.setup_directive_tab()
        self.tabs.addTab(self.directive_tab, "DIRECTIVES")

        main_layout.addWidget(self.tabs)

        # --- 3. LOG AREA ---
        self.log_area = QTextEdit()
        self.log_area.setObjectName("LogArea")
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(150)
        main_layout.addWidget(self.log_area)

    def setup_overview_tab(self):
        layout = QHBoxLayout(self.overview_tab)

        # General Info
        gen_box = QFrame()
        gen_box.setObjectName("StatCard")
        gen_layout = QVBoxLayout(gen_box)
        
        title_label = QLabel("GENERAL INFORMATION")
        title_label.setObjectName("GroupTitle")
        gen_layout.addWidget(title_label)

        for field in ["Name:", "Faction:", "Server:", "Outfit:", "Rank:", "Time Played:"]:
            row = QHBoxLayout()
            
            val = QLabel("-")
            val.setObjectName("StatValue")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.info_labels[field] = val
            
            field_label = QLabel(field)
            field_label.setObjectName("StatLabel")
            row.addWidget(field_label)
            
            row.addWidget(val)
            gen_layout.addLayout(row)
        gen_layout.addStretch()
        layout.addWidget(gen_box, 1)

        # Performance
        perf_box = QFrame()
        perf_box.setObjectName("StatCard")
        perf_layout = QHBoxLayout(perf_box)
        for group in ["LIFETIME PERFORMANCE", "LAST 30 DAYS"]:
            col = QVBoxLayout()
            
            group_label = QLabel(group)
            group_label.setObjectName("GroupTitle")
            col.addWidget(group_label)
            
            for stat in ["Kills", "Deaths", "K/D", "KPM", "KPH", "SPM", "Score"]:
                stat_label = QLabel(stat)
                stat_label.setObjectName("StatLabel")
                col.addWidget(stat_label)
                
                val = QLabel("-")
                val.setObjectName("StatValue")
                self.stats_ui[f"{group}_{stat}"] = val
                col.addWidget(val)
            col.addStretch()
            perf_layout.addLayout(col)
        layout.addWidget(perf_box, 2)

        # Directives Overview
        dir_box = QFrame()
        dir_box.setObjectName("StatCard")
        dir_layout = QVBoxLayout(dir_box)

        dir_title = QLabel("DIRECTIVES OVERVIEW")
        dir_title.setObjectName("GroupTitle")
        dir_layout.addWidget(dir_title)

        for field in ["Total Lines:", "Completed:", "In Progress:", "Top Directive:"]:
            row = QHBoxLayout()
            field_label = QLabel(field)
            field_label.setObjectName("StatLabel")
            row.addWidget(field_label)

            val = QLabel("-")
            val.setObjectName("StatValue")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.directive_overview_labels[field] = val
            row.addWidget(val)
            dir_layout.addLayout(row)

        dir_layout.addStretch()
        layout.addWidget(dir_box, 1)

    def setup_weapon_tab(self):
        layout = QVBoxLayout(self.weapon_tab)
        self.weapon_table.setHorizontalHeaderLabels(["WEAPON", "KILLS", "ACC %", "HSR %"])
        self.weapon_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.weapon_table.verticalHeader().setVisible(False)
        layout.addWidget(self.weapon_table)

    def setup_directive_tab(self):
        layout = QVBoxLayout(self.directive_tab)
        # Tabelle konfigurieren
        self.directive_table.setHorizontalHeaderLabels(["DIRECTIVE LINE", "CURRENT TIER", "STATUS"])
        
        h = self.directive_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        self.directive_table.verticalHeader().setVisible(False)
        self.directive_table.setAlternatingRowColors(True)
        self.directive_table.setStyleSheet("alternate-background-color: #161616;")
        layout.addWidget(self.directive_table)

    # --- LOGIK ---

    def trigger_search(self):
        name = self.search_input.text().strip()
        if not name: return

        # 1. UI Feedback: Feld leeren & Logs
        self.search_input.clear()
        self.add_log(f"UPLINK: Requesting data for Character '{name}'...")

        # 2. Stats auf "SEARCHING..." setzen
        for lbl in self.info_labels.values(): lbl.setText("...")
        for lbl in self.stats_ui.values(): lbl.setText("...")
        for lbl in self.directive_overview_labels.values(): lbl.setText("...")
        self.weapon_table.setRowCount(0)

        # 3. Signal an Dior Client.py senden
        self.signals.search_requested.emit(name)

    def update_overview(self, c_stats):
        # Stammdaten
        for label_name, key in [("Name:", 'name'), ("Faction:", 'fac_short'), ("Server:", 'server'),
                                ("Outfit:", 'outfit'), ("Rank:", 'rank'), ("Time Played:", 'time_played')]:
            if label_name in self.info_labels:
                self.info_labels[label_name].setText(str(c_stats.get(key, '-')))

        # Performance Stats
        for group in ["LIFETIME PERFORMANCE", "LAST 30 DAYS"]:
            prefix = "lt" if group == "LIFETIME PERFORMANCE" else "m30"
            for stat in ["Kills", "Deaths", "K/D", "KPM", "KPH", "SPM", "Score"]:
                ui_key = f"{group}_{stat}"
                if ui_key in self.stats_ui:
                    clean_stat = stat.lower().replace("/", "")
                    val = c_stats.get(f"{prefix}_{clean_stat}", "-")
                    self.stats_ui[ui_key].setText(str(val))

    def update_weapons(self, weapon_list):
        self.weapon_table.setRowCount(0)
        for w in sorted(weapon_list, key=lambda x: x.get('kills', 0), reverse=True):
            row = self.weapon_table.rowCount()
            self.weapon_table.insertRow(row)
            kills = w.get('kills', 0)
            acc = (w.get('hits', 0) / w.get('shots', 1) * 100) if w.get('shots', 0) > 0 else 0
            hsr = (w.get('hs', 0) / kills * 100) if kills > 0 else 0
            self.weapon_table.setItem(row, 0, QTableWidgetItem(w.get('name', '?')))
            self.weapon_table.setItem(row, 1, QTableWidgetItem(f"{kills:,}"))
            self.weapon_table.setItem(row, 2, QTableWidgetItem(f"{acc:.1f}%"))
            self.weapon_table.setItem(row, 3, QTableWidgetItem(f"{hsr:.1f}%"))

    def add_log(self, text):
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    # --- DIRECTIVE LOGIC ---
    def load_directives_db(self):
        path = os.path.join(os.path.dirname(__file__), "assets", "directives.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            print(f"ERR: Failed to load directives.json ({exc})")
            return {}

    def fetch_directives(self, char_id):
        """Startet den Thread zum Laden der Directives."""
        self.directive_table.setRowCount(0)
        self.add_log("Fetch: Loading Directives...")
        
        t = threading.Thread(target=self._fetch_thread, args=(char_id,), daemon=True)
        t.start()

    def _fetch_thread(self, char_id):
        url = f"https://census.daybreakgames.com/s:ahornstream/get/ps2:v2/characters_directive_tier?character_id={char_id}&c:limit=500&c:join=type:directive%5Eon:directive_tree_id%5Eto:directive_tree_id&c:lang=en"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            
            # Auf Hauptthread updaten
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "update_directive_table", 
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(list, data.get("characters_directive_tier_list", [])))
            
        except Exception as e:
            print(f"Directive API Error: {e}")

   # @pyqtSignal(list)
    def update_directive_table(self, data_list):
        """Wird vom Thread aufgerufen, wenn Daten da sind."""
        self.directive_table.setRowCount(0)
        self.directive_table.setSortingEnabled(False)

        for item in data_list:
            tree_id = str(item.get("directive_tree_id"))
            tier_id = item.get("directive_tier_id", "0")
            
            # 1. Namen auflösen (Lokal)
            dir_info = self.directives_db.get(tree_id, {})
            name = dir_info.get("name", f"Unknown ({tree_id})")
            
            # 2. Tier Name via Join (API Payload)
            # Da wir c:join nutzen, ist 'directive_tree_id_join_directive' im Payload
            # ABER: characters_directive_tier gibt nur TIER ID.
            # Der Join in der URL 'type:directive^on:directive_tree_id^to:directive_tree_id' 
            # ist etwas tricky, da er auf 'directive' joint, nicht 'directive_tier'.
            # Wir schauen mal was wir bekommen.
            # Fallback: Tier ID anzeigen
            
            tier_val = int(tier_id)
            # Einfache Mapping-Logik für Standard Directives (1=Bronze, 2=Silver, 3=Gold, 4=Aurax)
            # Manche haben aber andere IDs. Wir nehmen einfach die ID als Indikator.
            
            # Status berechnen (Progress)
            # Die API gibt oft auch 'current_directive_tier' zurück.
            
            row = self.directive_table.rowCount()
            self.directive_table.insertRow(row)
            
            # Name
            self.directive_table.setItem(row, 0, QTableWidgetItem(name))
            
            # Tier
            tier_item = QTableWidgetItem(str(tier_val))
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.directive_table.setItem(row, 1, tier_item)
            
            # Status (API liefert oft completion date)
            ts = item.get("completion_time", "0")
            status = "Completed" if ts != "0" else "In Progress"
            
            status_item = QTableWidgetItem(status)
            if status == "Completed":
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            
            self.directive_table.setItem(row, 2, status_item)

        self.directive_table.setSortingEnabled(True)
        self.add_log(f"Fetch: {len(data_list)} Directives loaded.")
        self.update_directive_overview(data_list)

    def update_directive_overview(self, data_list):
        total_lines = len(data_list)
        completed = 0
        in_progress = 0
        top_entry = None
        top_tier = -1

        for item in data_list:
            tier_id = int(item.get("directive_tier_id", "0"))
            is_completed = item.get("completion_time", "0") != "0"
            if is_completed:
                completed += 1
            else:
                in_progress += 1

            if tier_id > top_tier:
                top_tier = tier_id
                top_entry = item

        top_name = "-"
        if top_entry:
            tree_id = str(top_entry.get("directive_tree_id"))
            dir_info = self.directives_db.get(tree_id, {})
            top_name = dir_info.get("name", f"Unknown ({tree_id})")

        if "Total Lines:" in self.directive_overview_labels:
            self.directive_overview_labels["Total Lines:"].setText(str(total_lines))
        if "Completed:" in self.directive_overview_labels:
            self.directive_overview_labels["Completed:"].setText(str(completed))
        if "In Progress:" in self.directive_overview_labels:
            self.directive_overview_labels["In Progress:"].setText(str(in_progress))
        if "Top Directive:" in self.directive_overview_labels:
            self.directive_overview_labels["Top Directive:"].setText(top_name)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Stylesheet wird jetzt in __init__ geladen, aber für Standalone Test:
    win = CharacterWidget()  # Name korrigiert
    win.show()
    sys.exit(app.exec())
