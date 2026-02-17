import sys
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QFrame, QTabWidget, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, pyqtSlot


# --- SIGNALS ---
class CharacterSignals(QObject):
    # From GUI -> Logic (Triggers run_search)
    search_requested = pyqtSignal(str)

    # From Logic -> GUI (Triggers process_search_results_qt)
    search_finished = pyqtSignal(dict, list)


# --- STYLESHEET ---
CHAR_STYLE = """
QWidget#Characters { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a1a, stop:1 #121212); 
}

QTabWidget::pane { 
    border: 1px solid #333; 
    background-color: rgba(20, 20, 20, 0.8); 
    top: -1px; 
    border-radius: 8px;
}

QTabBar::tab { 
    background-color: #252525; 
    color: #888; 
    padding: 12px 25px; 
    border: 1px solid #333; 
    border-bottom: none; 
    border-top-left-radius: 6px; 
    border-top-right-radius: 6px; 
    margin-right: 2px;
}

QTabBar::tab:selected { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2a2a, stop:1 #1a1a1a); 
    color: #00f2ff; 
    font-weight: bold; 
    border-bottom: 2px solid #00f2ff; 
}

QFrame#StatCard { 
    background-color: rgba(30, 30, 30, 0.6); 
    border: 1px solid #333; 
    border-radius: 10px; 
    padding: 10px;
}

QLabel#GroupTitle { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 15px; 
    margin-bottom: 10px; 
    text-transform: uppercase;
}

QLabel#StatLabel { 
    color: #888; 
    font-size: 12px; 
}

QLabel#StatValue { 
    color: white; 
    font-weight: bold; 
    font-size: 16px; 
}

QTableWidget { 
    background-color: transparent; 
    border: none; 
    color: white; 
    gridline-color: #333; 
    font-size: 12px;
}

QHeaderView::section { 
    background-color: #1a1a1a; 
    color: #00f2ff; 
    padding: 8px; 
    border: none; 
    font-weight: bold; 
    text-transform: uppercase;
    font-size: 11px;
}

QTextEdit#LogArea { 
    background-color: #050505; 
    color: #00f2ff; 
    font-family: 'Consolas', monospace; 
    font-size: 11px; 
    border: 1px solid #333; 
    border-radius: 5px;
}

QLineEdit { 
    background-color: #0a0a0a; 
    color: white; 
    border: 1px solid #444; 
    padding: 10px; 
    border-radius: 5px;
}

QLineEdit:focus {
    border: 1px solid #00f2ff;
}

QPushButton#ActionBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333, stop:1 #222);
    color: #eee;
    border: 1px solid #444;
    padding: 10px 20px;
    font-weight: bold;
    border-radius: 5px;
    font-size: 12px;
    text-transform: uppercase;
}

QPushButton#ActionBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #333);
    border-color: #00f2ff;
    color: white;
}
"""


class CharacterWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.setObjectName("Characters")
        self.resize(1000, 900)


        # IMPORTANT: Apply stylesheet
        self.setStyleSheet(CHAR_STYLE)

        # Initialize signals
        self.signals = CharacterSignals()

        # Instance attributes
        self.info_labels = {}
        self.stats_ui = {}
        self.weapon_table = QTableWidget(0, 4)

        # Apply layout directly to self
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- 1. TITLE & SEARCH ---
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("CHARACTER ANALYSIS")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00f2ff;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter Character Name...")
        self.search_input.setFixedWidth(250)
        self.search_input.returnPressed.connect(self.trigger_search)

        self.btn_search = QPushButton("SEARCH", objectName="ActionBtn")
        self.btn_search.clicked.connect(self.trigger_search)

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

    def setup_weapon_tab(self):
        layout = QVBoxLayout(self.weapon_tab)
        # NEW COLUMNS: KPM, K/D, ACC, HSR, VEHICLE KILLS, VEHICLE KPM, TIME
        headers = ["WEAPON", "KILLS", "KPM", "K/D", "ACC %", "HSR %", "V.KILLS", "V.KPM", "TIME"]
        self.weapon_table.setColumnCount(len(headers))
        self.weapon_table.setHorizontalHeaderLabels(headers)
        
        h = self.weapon_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Adjust all other columns to content
        for i in range(1, len(headers)):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            
        self.weapon_table.verticalHeader().setVisible(False)
        layout.addWidget(self.weapon_table)

    def setup_directive_tab(self):
        layout = QVBoxLayout(self.directive_tab)
        # Configure table
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

        # 1. UI Feedback: Clear field & Logs
        self.search_input.clear()
        self.add_log(f"UPLINK: Requesting data for Character '{name}'...")

        # 2. Set Stats to "SEARCHING..."
        for lbl in self.info_labels.values(): lbl.setText("...")
        for lbl in self.stats_ui.values(): lbl.setText("...")
        self.weapon_table.setRowCount(0)

        # 3. Send Signal to Dior Client.py
        self.signals.search_requested.emit(name)

    def update_overview(self, c_stats):
        # Master Data
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
        self.weapon_table.setSortingEnabled(False)  # Performance beim Füllen

        for w in sorted(weapon_list, key=lambda x: x.get('kills', 0), reverse=True):
            row = self.weapon_table.rowCount()
            self.weapon_table.insertRow(row)
            
            # FETCH DATA
            kills = w.get('kills', 0)
            deaths = w.get('deaths', 0)
            shots = w.get('shots', 0)
            hits = w.get('hits', 0)
            hs = w.get('hs', 0)
            vkills = w.get('vkills', 0)
            play_time = w.get('time', 0)  # Sekunden
            
            # CALCULATIONS
            acc = (hits / shots * 100) if shots > 0 else 0.0
            hsr = (hs / kills * 100) if kills > 0 else 0.0
            kd = kills / max(1, deaths)
            
            minutes = play_time / 60.0
            kpm = kills / max(1, minutes) if minutes > 0 else 0.0
            vkpm = vkills / max(1, minutes) if minutes > 0 else 0.0
            
            # Time Formatting (HH:MM)
            hours = int(play_time // 3600)
            rem_min = int((play_time % 3600) // 60)
            time_str = f"{hours}h {rem_min}m"

            # WRITE TO TABLE
            # 0: WEAPON, 1: KILLS, 2: KPM, 3: K/D, 4: ACC %, 5: HSR %, 6: V.KILLS, 7: V.KPM, 8: TIME
            
            self.weapon_table.setItem(row, 0, QTableWidgetItem(w.get('name', '?')))
            
            item_kills = QTableWidgetItem(f"{kills:,}")
            item_kills.setData(Qt.ItemDataRole.DisplayRole, kills) # Make sortable
            self.weapon_table.setItem(row, 1, item_kills)
            
            self.weapon_table.setItem(row, 2, QTableWidgetItem(f"{kpm:.2f}"))
            self.weapon_table.setItem(row, 3, QTableWidgetItem(f"{kd:.2f}"))
            self.weapon_table.setItem(row, 4, QTableWidgetItem(f"{acc:.1f}%"))
            self.weapon_table.setItem(row, 5, QTableWidgetItem(f"{hsr:.1f}%"))
            
            item_vkills = QTableWidgetItem(f"{vkills:,}")
            item_vkills.setData(Qt.ItemDataRole.DisplayRole, vkills)
            self.weapon_table.setItem(row, 6, item_vkills)
            
            self.weapon_table.setItem(row, 7, QTableWidgetItem(f"{vkpm:.2f}"))
            
            item_time = QTableWidgetItem(time_str)
            item_time.setData(Qt.ItemDataRole.UserRole, play_time) # For sorting (would need custom sorter, but UserRole might help)
            self.weapon_table.setItem(row, 8, item_time)

        self.weapon_table.setSortingEnabled(True)

    @pyqtSlot(str)
    def add_log(self, text):
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    # --- DIRECTIVE LOGIC ---

    def _fetch_thread(self, char_id):
        url = f"https://census.daybreakgames.com/s:ahornstream/get/ps2:v2/characters_directive_tier?character_id={char_id}&c:limit=500&c:join=type:directive%5Eon:directive_tree_id%5Eto:directive_tree_id&c:lang=en"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            
            # Update on main thread
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "update_directive_table", 
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(list, data.get("characters_directive_tier_list", [])))
            
        except Exception as e:
            print(f"Directive API Error: {e}")

   # @pyqtSignal(list)
    def update_directive_table(self, data_list):
        """Called by the thread when data is available."""
        self.directive_table.setRowCount(0)
        self.directive_table.setSortingEnabled(False)

        for item in data_list:
            tree_id = item.get("directive_tree_id")
            tier_id = item.get("directive_tier_id", "0")
            
            # 1. Resolve names (Local)
            dir_info = self.directives_db.get(tree_id, {})
            name = dir_info.get("name", f"Unknown ({tree_id})")
            
            # 2. Tier Name via Join (API Payload)
            # Since we use c:join, 'directive_tree_id_join_directive' is in the payload
            # BUT: characters_directive_tier only returns TIER ID.
            # The join in the URL 'type:directive^on:directive_tree_id^to:directive_tree_id'
            # is a bit tricky, as it joins on 'directive', not 'directive_tier'.
            # Let's see what we get.
            # Fallback: Show Tier ID
            
            tier_val = int(tier_id)
            # Simple mapping logic for standard directives (1=Bronze, 2=Silver, 3=Gold, 4=Aurax)
            # Some have different IDs. We simply use the ID as indicator.
            
            # Calculate Status (Progress)
            # The API often returns 'current_directive_tier' as well.
            
            row = self.directive_table.rowCount()
            self.directive_table.insertRow(row)
            
            # Name
            self.directive_table.setItem(row, 0, QTableWidgetItem(name))
            
            # Tier
            tier_item = QTableWidgetItem(str(tier_val))
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.directive_table.setItem(row, 1, tier_item)
            
            # Status (API often provides completion date)
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Stylesheet is now loaded in __init__, but for standalone test:
    win = CharacterWidget()  # Name corrected
    win.show()
    sys.exit(app.exec())
