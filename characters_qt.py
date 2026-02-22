import sys
import time
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QFrame, QTabWidget, QTextEdit,
                             QSplitter, QTreeWidget, QTreeWidgetItem, QScrollArea, QProgressBar)
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

class NumericTableWidgetItem(QTableWidgetItem):
    """Sorts QTableWidgetItems intelligently by number if available via DataRole, else strings."""
    def __lt__(self, other):
        my_val = self.data(Qt.ItemDataRole.UserRole)
        other_val = other.data(Qt.ItemDataRole.UserRole)
        if my_val is not None and other_val is not None:
            try:
                return float(my_val) < float(other_val)
            except ValueError:
                pass
        return super().__lt__(other)


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
        
        self.dir_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Tree Widget
        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderLabel("Directive Trees")
        self.dir_tree.setStyleSheet("QTreeWidget { background-color: #121212; color: #eee; border: 1px solid #333; }"
                                    "QTreeWidget::item:selected { background-color: #2a2a2a; color: #00f2ff; font-weight: bold; }")
        self.dir_splitter.addWidget(self.dir_tree)
        self.dir_tree.itemClicked.connect(self.on_directive_tree_clicked)
        
        # Right: Details Scroll Area
        self.dir_scroll = QScrollArea()
        self.dir_scroll.setWidgetResizable(True)
        self.dir_scroll.setStyleSheet("QScrollArea { background-color: #1a1a1a; border: 1px solid #333; }")
        
        self.dir_details_widget = QWidget()
        self.dir_details_widget.setStyleSheet("background-color: transparent;")
        self.dir_details_layout = QVBoxLayout(self.dir_details_widget)
        self.dir_details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.dir_scroll.setWidget(self.dir_details_widget)
        self.dir_splitter.addWidget(self.dir_scroll)
        
        self.dir_splitter.setSizes([300, 700])
        layout.addWidget(self.dir_splitter)

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
        self.current_faction_id = str(c_stats.get('faction_id', "0"))
        self.add_log(f"SYS: Character Data Loaded. Faction: {self.current_faction_id}")
        print(f"DEBUG: update_overview set current_faction_id to {self.current_faction_id}")
        
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
            
            item_kills = NumericTableWidgetItem(f"{kills:,}")
            item_kills.setData(Qt.ItemDataRole.UserRole, kills)
            self.weapon_table.setItem(row, 1, item_kills)
            
            item_kpm = NumericTableWidgetItem(f"{kpm:.2f}")
            item_kpm.setData(Qt.ItemDataRole.UserRole, kpm)
            self.weapon_table.setItem(row, 2, item_kpm)

            item_kd = NumericTableWidgetItem(f"{kd:.2f}")
            item_kd.setData(Qt.ItemDataRole.UserRole, kd)
            self.weapon_table.setItem(row, 3, item_kd)

            item_acc = NumericTableWidgetItem(f"{acc:.1f}%")
            item_acc.setData(Qt.ItemDataRole.UserRole, acc)
            self.weapon_table.setItem(row, 4, item_acc)

            item_hsr = NumericTableWidgetItem(f"{hsr:.1f}%")
            item_hsr.setData(Qt.ItemDataRole.UserRole, hsr)
            self.weapon_table.setItem(row, 5, item_hsr)
            
            item_vkills = NumericTableWidgetItem(f"{vkills:,}")
            item_vkills.setData(Qt.ItemDataRole.UserRole, vkills)
            self.weapon_table.setItem(row, 6, item_vkills)
            
            item_vkpm = NumericTableWidgetItem(f"{vkpm:.2f}")
            item_vkpm.setData(Qt.ItemDataRole.UserRole, vkpm)
            self.weapon_table.setItem(row, 7, item_vkpm)
            
            item_time = NumericTableWidgetItem(time_str)
            item_time.setData(Qt.ItemDataRole.UserRole, play_time)
            self.weapon_table.setItem(row, 8, item_time)

        self.weapon_table.setSortingEnabled(True)

    @pyqtSlot(str)
    def add_log(self, text):
        self.log_area.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    # --- DIRECTIVE LOGIC ---

    def _fetch_thread(self, char_id):
        self.current_char_id = char_id
        # Use dynamic s_id from controller if available, fallback to env or example
        s_id = getattr(self.controller, "s_id", None) or os.getenv("CENSUS_S_ID", "s:example")
        url = f"https://census.daybreakgames.com/{s_id}/get/ps2:v2/characters_directive_tree?character_id={char_id}&c:limit=500&c:join=directive_tree^on:directive_tree_id^to:directive_tree_id^inject_at:tree(directive_tree_category^on:directive_tree_category_id^to:directive_tree_category_id^inject_at:category)"
        try:
            import requests
            r = requests.get(url, timeout=30)
            data = r.json()
            
            # Update on main thread
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "update_directive_table", 
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(list, data.get("characters_directive_tree_list", [])))
            
        except Exception as e:
            print(f"Directive API Error: {e}")
            self.add_log(f"ERR: Tree API failed: {e}")

    @pyqtSlot(list)
    def update_directive_table(self, data_list):
        """Called by the thread when tree data is available. Populates the left pane tree."""
        self.dir_tree.clear()
        
        categories = {}
        for item in data_list:
            tree_data = item.get("tree", {})
            cat_data = tree_data.get("category", {})
            
            cat_name = cat_data.get("name", {}).get("en", "Unknown Category")
            tree_name = tree_data.get("name", {}).get("en", "Unknown Tree")
            tree_id = item.get("directive_tree_id")
            
            # Store completion status
            # 'current_directive_tier_id' usually indicates the tier they are currently on, so completed is that - 1 usually, 
            # or just show the tier ID they are currently working on as 'Level'.
            status = item.get("current_directive_tier_id", "0")
            completion_time = item.get("completion_time", "0")
            
            if cat_name not in categories:
                categories[cat_name] = []
                
            categories[cat_name].append({
                "name": tree_name,
                "id": tree_id,
                "level": status,
                "completed": completion_time != "0"
            })
            
        for cat_name, trees in sorted(categories.items()):
            cat_item = QTreeWidgetItem(self.dir_tree, [cat_name])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_item.setExpanded(True)
            
            for tree in sorted(trees, key=lambda x: x["name"]):
                tree_str = f"{tree['name']} (Level {tree['level']})"
                if tree['completed']:
                    tree_str = f"{tree['name']} (Completed)"
                tree_item = QTreeWidgetItem(cat_item, [tree_str])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, tree["id"])
                if tree["completed"]:
                    tree_item.setForeground(0, Qt.GlobalColor.green)
                else:
                    tree_item.setForeground(0, Qt.GlobalColor.yellow)
                    
        self.add_log(f"Fetch: {len(data_list)} Directive Trees loaded.")

    def on_directive_tree_clicked(self, item, column):
        tree_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not tree_id:
            return  # Category clicked
            
        self.add_log(f"Fetching details for Tree {tree_id}...")
        
        # Clear existing details
        for i in reversed(range(self.dir_details_layout.count())):
            widget_to_remove = self.dir_details_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)
                
        lbl = QLabel("Loading tree details...")
        lbl.setStyleSheet("color: #00f2ff;")
        self.dir_details_layout.addWidget(lbl)
        
        # Start detail fetch thread
        import threading
        t = threading.Thread(target=self._fetch_tree_details_thread, args=(self.current_char_id, tree_id))
        t.daemon = True
        t.start()

    def _fetch_tree_details_thread(self, char_id, tree_id):
        # Use dynamic s_id from controller if available, fallback to env or example
        s_id = getattr(self.controller, "s_id", None) or os.getenv("CENSUS_S_ID", "s:example")

        # 1. Fetch static tree structure
        # FIXED: Routed the objectives join through objective_set_to_objective so we actually receive param1 and param5.
        url_tree = f"https://census.daybreakgames.com/{s_id}/get/ps2:v2/directive_tree?directive_tree_id={tree_id}&c:lang=en&c:join=directive_tier^on:directive_tree_id^to:directive_tree_id^list:1^inject_at:tiers(directive^on:directive_tier_id^to:directive_tier_id^terms:directive_tree_id={tree_id}^list:1^inject_at:directives(objective_set_to_objective^on:objective_set_id^to:objective_set_id^list:1^inject_at:objective_set_to_objective(objective^on:objective_group_id^to:objective_group_id^list:1^inject_at:objectives)))"
        
        # 2. Fetch character progress for this tree
        url_char = f"https://census.daybreakgames.com/{s_id}/get/ps2:v2/characters_directive?character_id={char_id}&directive_tree_id={tree_id}&c:limit=500"
        url_char_obj = f"https://census.daybreakgames.com/{s_id}/get/ps2:v2/characters_directive_objective?character_id={char_id}&directive_tree_id={tree_id}&c:limit=500"
        
        try:
            import requests
            r_tree = requests.get(url_tree, timeout=30).json()
            r_char = requests.get(url_char, timeout=30).json()
            r_char_obj = requests.get(url_char_obj, timeout=30).json()
            
            tree_data = r_tree.get("directive_tree_list", [{}])[0]
            char_directives = {d["directive_id"]: d for d in r_char.get("characters_directive_list", [])}
            char_objectives = {d["objective_id"]: d for d in r_char_obj.get("characters_directive_objective_list", [])}
            
            # Get character faction from the loaded char_data or from a previously stored variable
            char_faction = getattr(self, "current_faction_id", "0")
            
            payload = {
                "tree": tree_data,
                "char_dir": char_directives,
                "char_obj": char_objectives,
                "char_faction": char_faction
            }
            
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self, "update_tree_details_ui", 
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(dict, payload))
                                     
        except Exception as e:
            print(f"Details API Error: {e}")
            self.add_log(f"ERR: Details API failed: {e}")

    @pyqtSlot(dict)
    def update_tree_details_ui(self, payload):
        # Clear existing details
        for i in reversed(range(self.dir_details_layout.count())):
            widget_to_remove = self.dir_details_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)
                
        tree = payload.get("tree", {})
        char_dir = payload.get("char_dir", {})
        char_obj = payload.get("char_obj", {})
        
        if not tree:
            lbl = QLabel("Failed to load tree data.")
            lbl.setStyleSheet("color: red;")
            self.dir_details_layout.addWidget(lbl)
            return
            
        tree_name = tree.get("name", {}).get("en", "Unknown Tree")
        title = QLabel(f"<span style='font-size: 18px; color: #00f2ff; font-weight: bold;'>{tree_name}</span>")
        self.dir_details_layout.addWidget(title)
        
        # Load Faction Filter Data once (name-based matching is more stable than item IDs)
        faction_map_size = 0
        faction_name_map = {}
        
        def normalize_filter_name(name):
            if not name:
                return ""
            # Keep alnum chars, normalize separators/casing for loose CSV matches
            cleaned = "".join(ch if ch.isalnum() else " " for ch in str(name).upper())
            return " ".join(cleaned.split())
        
        def lookup_factions_by_name(name):
            norm = normalize_filter_name(name)
            if not norm:
                return set()
            
            exact = faction_name_map.get(norm)
            if exact:
                return set(exact)
            
            # Fallback: allow substring matches for minor naming format differences
            for csv_name_norm, factions in faction_name_map.items():
                if len(csv_name_norm) < 4:
                    continue
                if csv_name_norm in norm or norm in csv_name_norm:
                    return set(factions)
            return set()

        try:
            from dior_utils import get_asset_path
            import csv
            csv_path = get_asset_path("sanction-list.csv")
            if os.path.exists(csv_path):
                # Use utf-8-sig to handle potential BOM
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    fields = [fn.strip() for fn in (reader.fieldnames or [])]
                    
                    # Robust key matching (ignore case/spaces)
                    fac_key = next((f for f in fields if f.lower().replace(" ", "") == "factionid"), "Faction ID")
                    name_key = next((f for f in fields if f.lower().replace(" ", "") == "itemname"), "Item Name")
                    
                    for row in reader:
                        # Clean the row keys and values
                        clean_row = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                        f_id = clean_row.get(fac_key, "")
                        i_name = clean_row.get(name_key, "")
                        
                        if i_name and f_id:
                            norm_name = normalize_filter_name(i_name)
                            if norm_name:
                                faction_name_map.setdefault(norm_name, set()).add(f_id)
                    
                    faction_map_size = len(faction_name_map)
                    if faction_map_size == 0:
                         self.add_log(f"WRN: CSV loaded but 0 items mapped. Keys searched: {name_key}, {fac_key}. Found: {fields}")
                    else:
                        print(f"DEBUG: Found keys - Name:{name_key}, Fac:{fac_key}. Sample: {list(faction_name_map.keys())[:3]}")
            else:
                self.add_log(f"WRN: sanction-list.csv not found at {csv_path}")
        except Exception as e:
            print(f"Failed to load sanction-list.csv for faction filtering: {e}")
            self.add_log(f"ERR: Faction list load error: {e}")
            
        char_faction = str(payload.get("char_faction", "0"))
        print(f"DEBUG: update_tree_details_ui using Char Faction: {char_faction}")
        
        def infer_faction_from_name(name):
            """Primary filter for directives since names are reliable"""
            n = name.upper()
            
            # Special variants (Survivor/Networked/Unique Empire Picks)
            if "NS-W" in n or "NSX-W" in n or "XOXO" in n: return "1" # VS
            if "NS-G" in n or "NSX-G" in n or "NS-C" in n: return "2" # NC
            if "NS-M" in n or "NSX-M" in n or "NS-B" in n: return "3" # TR

            nso_terms = [
                "AR-", "SR-", "CB-", "XMG-", "PMG-", "BAR-", "SG-", "XGG-", "NP-"
            ]
            vs_terms = [
                "PULSAR", "ORION", "SOLSTICE", "BEAMER", "LASHER", "SCYTHE", "MAGRIDER", "SIRIUS", "ZENITH", "PHASESHIFT", 
                "VX", "VA", "VE", "SPYKER", "CERBERUS", "HV-45", "H-V45", "TERMINUS", "CORVUS", "ERIDANI", "SKORPIOS", "CANIS", "HORIZON", "LACERTA", 
                "PPA", "SARON", "PROTON", "APHELION", "STARFALL", "EQUINOX", "SVA-88", "FLARE", "URSA", "COBALT", "OBELISK",
                "GHOST", "PARALLAX", "XM98", "PHANTOM", "SPECTRE", "NYX", "NEMESIS", "HADES", "POLARIS", "QUASAR", "COSMOS", "NEBULA", "BLUESHIFT", "MANTIS",
                "SERPENT", "PROMINENCE", "NOVA", "THANATOS", "DEIMOS", "SPIKER", "MANTICORE", "V10", "LANCER", "VS-", " VS ", "EIDOLON", "ECLIPSE", "SUPERNOVA"
            ]
            nc_terms = [
                "GAUSS", "MERCENARY", "MAG-SHOT", "VANGUARD", "REAVER", "NC6", "GD-", "AF-", "LA-", "AC-", " AC ", "EM1", "EM6", "ANCHOR", "JACKHAMMER",
                "REBEL", "DESPERADO", "GR-22", "CARNAGE", "REAPER", "BANDIT", "CYCLONE", "TEMPEST", "GLADIUS", "PROMISE", "BISHOP",
                "ENFORCER", "CANISTER", "MJOLNIR", "PHOENIX", "SPARROW", "RAVEN", "CYLINDER", "RAILJACK", "SAW", "BLUEPRINT", "COVENANT",
                "WARDEN", "VANDAL", "LONGSHOT", "BOLT DRIVER", "SAS-R", "GLADIATOR", "MERC", "MAULER", "TRAWLER", "TITAN", "ENFORCER", "FALCON",
                "A-TROSS", "SHRIKE", "SWEEPER", "BRUISER", "MAG-SCATTER", "IMPETUS", "LA80", "NC-", " NC ", "TESSERACT"
            ]
            tr_terms = [
                "CYCLER", "CARV", "REPEATER", "PROWLER", "MOSQUITO", "T1", "T9", "TX", "SABR", "TRAC", "JAGUAR", "LYNX", "TMG",
                "INQUISITOR", "EMPEROR", "T1B", "TAR", "TORQ-9", "ARMISTICE", "SHURIKEN", "JACKAL", "DRAGOON",
                "VULCAN", "MARAUDER", "GATEKEEPER", "STRIKER", "POUNDERS", "FRACTURES", "MSW-R", "BULL", "RHINO", "ARBALEST", "MINIGUN",
                "99SV", "M77-B", "RAMS .50M", "TSAR-42", "TRAP-M1", "CLAYMORE", "VULCAN", "GATEKEEPER", "POUNDERS", "STRIKER", "ONAGER",
                "NIGHTHAWK", "HAYMAKER", "BARRAGE", "BLACKJACK", "SKEP", "HAILSTORM", "M77-B", "TR-", " TR ", "LC", "HC"
            ]
            
            # Check for exact faction tags first
            if "(VS)" in n: return "1"
            if "(NC)" in n: return "2"
            if "(TR)" in n: return "3"
            
            # Prefix/Term scan
            for t in nso_terms:
                if t in n: return "4"
            for t in vs_terms:
                if t in n: return "1"
            for t in nc_terms:
                if t in n: return "2"
            for t in tr_terms:
                if t in n: return "3"
            return None

        if faction_map_size > 0:
            self.add_log(f"LOG: Loaded {faction_map_size} weapons for faction filtering. Char Faction: {char_faction}")
        else:
            self.add_log("WRN: Faction filter inactive (Map empty).")
            
        tiers = tree.get("tiers", [])
        if isinstance(tiers, dict):
            tiers = [tiers]
            
        tiers.sort(key=lambda x: int(x.get("directive_tier_id", 0)))
        
        # Color mapping for tiers
        tier_colors = {
            1: "#cd7f32", # Bronze
            2: "#c0c0c0", # Silver
            3: "#ffd700", # Gold
            4: "#b900ff"  # Auraxium (purple)
        }
        
        for tier in tiers:
            tier_id = int(tier.get("directive_tier_id", 0))
            tier_name = tier.get("name", {}).get("en", f"Tier {tier_id}")
            comp_count = tier.get("completion_count", "0")
            
            tier_frame = QFrame()
            tier_frame.setObjectName("StatCard")
            tier_layout = QVBoxLayout(tier_frame)
            
            t_color = tier_colors.get(tier_id, "#ffffff")
            tier_title = QLabel(f"<b>{tier_name}</b> (Needs {comp_count} Directives)")
            tier_title.setStyleSheet(f"color: {t_color}; font-size: 14px;")
            tier_layout.addWidget(tier_title)
            
            directives = tier.get("directives", [])
            if isinstance(directives, dict):
                directives = [directives]
            
            if not directives:
                tier_layout.addWidget(QLabel("No directives found (or API load failure)."))
            
            valid_directives = 0
            seen_directive_ids = set()
            seen_directive_names = set()
            for dir_data in directives:
                d_id = dir_data.get("directive_id")
                if not d_id: continue
                
                # De-duplication: Skip if we've already rendered this specific directive in this tier
                if d_id in seen_directive_ids:
                    continue
                seen_directive_ids.add(d_id)
                
                # CENSUS API BUG FIX: Sometimes Census injects directives from OTHER trees/tiers
                # We strictly enforce that the directive belongs to this specific tree and tier.
                if dir_data.get("directive_tree_id") != str(tree.get("directive_tree_id")) or \
                   dir_data.get("directive_tier_id") != str(tier_id):
                    continue
                    
                d_name = dir_data.get("name", {}).get("en", "Unknown Directive")
                
                # Check character progress on this directive
                c_dir = char_dir.get(d_id, {})
                dir_completed = c_dir.get("completion_time", "0") != "0"
                has_progress = False
                
                # Define kill requirements per tier for Medal objectives (Type 66)
                # These are industry standard PS2 values
                tier_kills = {1: 10, 2: 60, 3: 250, 4: 1160}
                
                # Extract flat objectives from the join mappings
                flat_objectives = []
                os2o = dir_data.get("objective_set_to_objective", [])
                if isinstance(os2o, dict): os2o = [os2o]
                for mapping in os2o:
                    objs = mapping.get("objectives", [])
                    if isinstance(objs, dict): objs = [objs]
                    flat_objectives.extend(objs)
                
                # Identify weapon ID / requirements
                # PS2 has two main objective types for weapons:
                # 12: Kill count (param1=requirement, param5=weapon_id)
                # 66: Ribbon/Medal count (param1=weapon_id, requirement usually 1 ribbon/medal)
                
                o_max = 1
                o_curr = 0
                match_names = [d_name]  # Use subgoal/directive names for CSV matching (IDs can differ)
                
                for obj in flat_objectives:
                    o_id = obj.get("objective_id")
                    o_type = str(obj.get("objective_type_id")) # Ensure string for comparison
                    obj_name = obj.get("name", {}).get("en") if isinstance(obj.get("name"), dict) else obj.get("name")
                    if obj_name:
                        match_names.append(str(obj_name))
                    
                    current_item_id = ""
                    if o_type == "12": # Kill Count
                        current_item_id = str(obj.get("param5", ""))
                    elif o_type == "66": # Medal/Ribbon Count
                        current_item_id = str(obj.get("param1", ""))
                    
                    # Trace for debugging
                    print(f"TRACE: Directive {d_name} | Obj {o_id} | Type {o_type} | Found IID: {current_item_id}")
                        
                    # State tracking (usually use the first objective for progress bar)
                    if o_id in char_obj:
                        o_curr = int(char_obj.get(o_id).get("state_data", "0"))
                    
                    # Requirement extraction (use first objective)
                    if o_type == "12":
                        o_max = int(obj.get("param1", "1"))
                    elif o_type == "66":
                        o_max = tier_kills.get(tier_id, 1160)
                              
                # Find if user has any progress on objectives for the HAS_PROGRESS check used in filtering
                has_progress = o_curr > 0
                
                # INCLUSIVE FACTION FILTERING
                # A directive should ONLY be skipped if we are CERTAIN it is off-faction.
                # If name inference or mapping suggests it belongs to our character's faction or is NS, RETAIN.
                skip_faction = False
                
                if not dir_completed and not has_progress:
                    # 1. Primary Check: Name-based inference
                    inferred = infer_faction_from_name(d_name)
                    
                    # We skip if the name EXPLICITLY points to another faction (1,2,3,4)
                    # and that faction does not match the character
                    if inferred and inferred in ["1", "2", "3", "4"]:
                        if inferred != char_faction:
                            skip_faction = True
                            print(f"TRACE: Hiding {d_name} (Inferred {inferred} != Char {char_faction})")
                    
                    # 2. Secondary Check: CSV map-based by name (subgoal names are more stable than IDs)
                    if not skip_faction and not inferred:
                        # For multi-name directives (rare), skip only if ALL matched names are off-faction.
                        faction_confirmed = False
                        off_faction_found = False
                        matched_csv_name = None
                        
                        for subgoal_name in dict.fromkeys(match_names):
                            matched_factions = lookup_factions_by_name(subgoal_name)
                            if not matched_factions:
                                continue
                            
                            matched_csv_name = subgoal_name
                            # Faction 0 or empty/None = Universal/Common Pool
                            if any(f in ["0", "", "None"] for f in matched_factions):
                                faction_confirmed = True
                                break
                            if char_faction in matched_factions:
                                faction_confirmed = True
                                break
                            if matched_factions == {"4"}:  # NSO specific only
                                if char_faction == "4":
                                    faction_confirmed = True
                                    break
                                off_faction_found = True
                            elif matched_factions.intersection({"1", "2", "3", "4"}):
                                off_faction_found = True
                        
                        if off_faction_found and not faction_confirmed:
                            skip_faction = True
                            print(f"TRACE: Hiding {d_name} (CSV name match confirms off-faction via '{matched_csv_name}')")
                    
                    if not skip_faction:
                         if valid_directives < 20:
                              print(f"DIAGNOSTIC: RETAINED {d_name} (Names: {match_names}) Inferred: {inferred}")
                                    
                if skip_faction:
                    continue

                # Census can return multiple faction-qualified variants with different directive_ids
                # but identical visible names (e.g., Exceptional weapon entries). Collapse by name.
                d_name_key = normalize_filter_name(d_name)
                if d_name_key and d_name_key in seen_directive_names:
                    if valid_directives < 20:
                        print(f"TRACE: Skipping duplicate directive name '{d_name}' in tier {tier_id}")
                    continue
                if d_name_key:
                    seen_directive_names.add(d_name_key)
                    
                valid_directives += 1
                
                completion_date_str = ""
                if dir_completed:
                    c_time = int(c_dir.get("completion_time", "0"))
                    import datetime
                    completion_date_str = datetime.datetime.fromtimestamp(c_time).strftime('%Y-%m-%d')
                
                display_name = d_name
                if dir_completed and completion_date_str:
                    display_name += f" ({completion_date_str})"
                    
                lbl_name = QLabel(display_name)
                lbl_name.setFixedWidth(240)
                if dir_completed:
                    lbl_name.setStyleSheet("color: #00cc00;")
                else:
                    lbl_name.setStyleSheet("color: #ccc;")
                
                # Overrides for display
                if dir_completed:
                    o_curr = o_max
                if o_curr > o_max:  
                    o_curr = o_max
                    
                if dir_completed:
                    bar = QLabel("Completed")
                    bar.setStyleSheet("background-color: #00cc00; color: white; padding: 2px; font-weight: bold;")
                    bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    bar = QLabel(f"{o_curr} / {o_max}")
                    bar.setStyleSheet("background-color: #111; color: white; border: 1px solid #333; padding: 2px;")
                    bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                row_layout = QHBoxLayout()
                row_layout.addWidget(lbl_name)
                row_layout.addWidget(bar)
                
                tier_layout.addLayout(row_layout)
                
            if valid_directives == 0:
                # If we skipped all because of faction filter
                lbl_empty = QLabel("No Faction-Aligned directives found for this tier.")
                lbl_empty.setStyleSheet("color: #888; font-style: italic;")
                tier_layout.addWidget(lbl_empty)
                
            self.dir_details_layout.addWidget(tier_frame)
            
        self.dir_details_layout.addStretch()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Stylesheet is now loaded in __init__, but for standalone test:
    win = CharacterWidget()  # Name corrected
    win.show()
    sys.exit(app.exec())
