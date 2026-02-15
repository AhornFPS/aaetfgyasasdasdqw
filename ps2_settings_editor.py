import sys
import os
import ctypes
import configparser
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTabWidget, QScrollArea, QFrame, QLineEdit, QComboBox, 
    QCheckBox, QPushButton, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QGroupBox, QSpinBox, QDoubleSpinBox, QSlider,
    QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QFont, QColor

# --- STYLESHEET (Matches Dior Client Aesthetic) ---
EDITOR_STYLE = """
QMainWindow {
    background-color: #1a1a1a;
}
QTabWidget::pane {
    border: 1px solid #333;
    background: #1a1a1a;
}
QTabBar::tab {
    background: #2a2a2a;
    color: #888;
    padding: 10px 20px;
    border: 1px solid #333;
    border-bottom: none;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #333;
    color: #00f2ff;
    border-top: 2px solid #00f2ff;
}
QGroupBox {
    border: 1px solid #444;
    border-radius: 5px;
    margin-top: 20px;
    font-weight: bold;
    color: #ddd;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #00f2ff;
}
QLabel {
    color: #ccc;
    font-size: 12px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #222;
    border: 1px solid #444;
    color: #fff;
    padding: 2px;
    border-radius: 2px;
    min-height: 18px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #00f2ff;
}
QSlider::groove:horizontal {
    border: 1px solid #444;
    height: 8px;
    background: #222;
    margin: 2px 0;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #00f2ff;
    border: 1px solid #00f2ff;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}
QPushButton {
    background-color: #333;
    border: 1px solid #444;
    color: #ddd;
    padding: 8px 15px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #444;
    border: 1px solid #fff;
    color: #fff;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QWidget#ScrollContent {
    background-color: transparent;
}
"""

# --- RESOLUTION HELPER ---
class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
    ]

def get_supported_resolutions():
    resolutions = set()
    devmode = DEVMODE()
    devmode.dmSize = ctypes.sizeof(DEVMODE)
    
    i = 0
    # Create user32 interface
    user32 = ctypes.windll.user32
    
    while user32.EnumDisplaySettingsW(None, i, ctypes.byref(devmode)):
        i += 1
        # Filter for typical color depth to assume game-ready modes (usually 32-bit)
        if devmode.dmBitsPerPel == 32:
            resolutions.add((devmode.dmPelsWidth, devmode.dmPelsHeight))
            
    # Sort: Width desc, then Height desc
    return sorted(list(resolutions), key=lambda x: (x[0], x[1]), reverse=True)

# ----------------------------

class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return False

class PS2SettingsEditor(QMainWindow):
    def __init__(self, parent=None, base_path=None):
        super().__init__(parent)
        self.wheel_blocker = WheelBlocker()
        self.setWindowTitle("Planetside 2 Settings Editor (Enhanced)")
        self.resize(1000, 800)
        self.setStyleSheet(EDITOR_STYLE)
        
        self.base_path = base_path or os.getcwd()
        self.current_ini_path = None
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  # Preserve case sensivity
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header = QLabel("SETTINGS EDITOR")
        header.setStyleSheet("font-family: 'Black Ops One'; font-size: 24px; color: #00f2ff; margin-bottom: 10px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)
        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.tab_graphics = QWidget()
        self.tabs.addTab(self.tab_graphics, "GRAPHICS")
        
        # Footer Actions
        footer_layout = QHBoxLayout()
        
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #666;")
        
        btn_load = QPushButton("LOAD FILE")
        btn_load.clicked.connect(self.load_ini_dialog)
        
        btn_save = QPushButton("SAVE SETTINGS")
        btn_save.setStyleSheet("background-color: #004400; border: 1px solid #006600;")
        btn_save.clicked.connect(self.save_settings_dialog)
        
        footer_layout.addWidget(self.lbl_status)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_load)
        footer_layout.addWidget(btn_save)
        
        main_layout.addLayout(footer_layout)
        
        # Initial Load (Default to Low if exists, else ask)
        self.load_default_ini()

    def create_form_group(self, title, section_name, fields):
        """
        Helper to create a group box with form layout for specific INI section.
        """
        group = QGroupBox(title)
        # Use GridLayout to pack everything left
        layout = QGridLayout()
        layout.setColumnStretch(2, 1) # Push everything to the left
        layout.setVerticalSpacing(4)  # Tighter vertical spacing
        layout.setHorizontalSpacing(10) # Reasonable gap between label and field
        
        if not self.config.has_section(section_name):
            self.config.add_section(section_name)
            
        for field_def in fields:
            option_original = field_def[0]
            if isinstance(option_original, tuple):
                ini_key = option_original[0]
                display_label = option_original[1]
            else:
                ini_key = option_original
                display_label = option_original
                
            widget_type = field_def[1]
            min_val = field_def[2] if len(field_def) > 2 else None
            max_val = field_def[3] if len(field_def) > 3 else None
            
            val = self.config.get(section_name, ini_key, fallback="")
            widget = None
            is_mapped_combo = False
            
            # --- CUSTOM TYPES ---
            
            if widget_type == 'slider_percent':
                container = QWidget()
                container.setMinimumWidth(200)
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(0,0,0,0)
                
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(50, 250)
                
                label_val = QLabel("100%")
                label_val.setFixedWidth(50)
                
                label_warn = QLabel("")
                label_warn.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 10px;")
                
                try:
                    current_percent = int(float(val) * 100)
                except:
                    current_percent = 100
                    
                slider.setValue(current_percent)
                label_val.setText(f"{current_percent}%")
                
                slider.installEventFilter(self.wheel_blocker)

                # Logic capturing local variables for safe execution
                def on_slide(v, k=ini_key, l_v=label_val, l_w=label_warn):
                    l_v.setText(f"{v}%")
                    float_val = v / 100.0
                    self.config.set(section_name, k, f"{float_val:.6f}")
                    
                    if v > 100:
                        l_w.setText("High value warning!")
                    else:
                        l_w.setText("")
                        
                slider.valueChanged.connect(on_slide)
                
                # Trigger initial check
                on_slide(current_percent)
                
                h_layout.addWidget(slider)
                h_layout.addWidget(label_val)
                h_layout.addWidget(label_warn)
                
                widget = container

            elif widget_type == 'slider_distance':
                container = QWidget()
                container.setMinimumWidth(250)
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(0,0,0,0)
                
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(100, 6000)
                
                # Use QSpinBox for manual input
                spin = QSpinBox()
                spin.setRange(100, 6000)
                spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons) # Optional: cleaner look
                spin.setFixedWidth(60)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet("background-color: #222; color: #fff; border: 1px solid #444; border-radius: 3px;")

                try:
                    current_val = int(float(val))
                except:
                    current_val = 100
                    
                slider.setValue(current_val)
                spin.setValue(current_val)
                
                slider.installEventFilter(self.wheel_blocker)
                spin.installEventFilter(self.wheel_blocker)
                
                # Logic capturing local variables for safe execution
                def on_slide_dist(v, k=ini_key, s=spin):
                    if s.value() != v:
                        s.blockSignals(True)
                        s.setValue(v)
                        s.blockSignals(False)
                    self.config.set(section_name, k, f"{v}.000000")
                
                def on_spin_dist(v, k=ini_key, sl=slider):
                    if sl.value() != v:
                        sl.blockSignals(True)
                        sl.setValue(v)
                        sl.blockSignals(False)
                    self.config.set(section_name, k, f"{v}.000000")

                slider.valueChanged.connect(on_slide_dist)
                spin.valueChanged.connect(on_spin_dist)
                
                h_layout.addWidget(slider)
                h_layout.addWidget(spin)
                
                widget = container
                
            elif widget_type == 'mapped_combo':
                is_mapped_combo = True
                mapping = min_val 
                widget = QComboBox()
                
                val_to_index = {}
                for i, (disp, v_str) in enumerate(mapping):
                    widget.addItem(disp, v_str)
                    val_to_index[str(v_str)] = i
                    
                if str(val) in val_to_index:
                    widget.setCurrentIndex(val_to_index[str(val)])
                else:
                    if "-1" in val_to_index: 
                        widget.setCurrentIndex(val_to_index["-1"])

            # FIX: Capture 'widget' as default argument 'w' to lock it
                def on_combo_change(idx, w=widget, k=ini_key):
                    data_val = w.itemData(idx)
                    self.config.set(section_name, k, str(data_val))
                    
                widget.currentIndexChanged.connect(on_combo_change)

            elif widget_type == 'slider_float':
                container = QWidget()
                container.setMinimumWidth(200) # Ensure it doesn't collapse
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(0,0,0,0)

                # Slider 0-100 mapped to 0.0-1.0
                slider = QSlider(Qt.Orientation.Horizontal)
                min_f = min_val if min_val is not None else 0.0
                max_f = max_val if max_val is not None else 1.0
                
                # We'll map float range [min_f, max_f] to int [0, 100]
                slider.setRange(0, 100)

                # Spinbox
                spin = QDoubleSpinBox()
                spin.setRange(min_f, max_f)
                spin.setSingleStep(0.01)
                spin.setDecimals(2)
                spin.setFixedWidth(70)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
                spin.setStyleSheet("background-color: #222; color: #fff; border: 1px solid #444; border-radius: 3px;")

                try:
                    current_val = float(val)
                except:
                    current_val = min_f

                # Clamp initial value
                if current_val < min_f: current_val = min_f
                if current_val > max_f: current_val = max_f

                spin.setValue(current_val)
                
                # Convert float val to slider int (0-100)
                # ratio = (val - min) / (max - min)
                if max_f > min_f:
                    ratio = (current_val - min_f) / (max_f - min_f)
                    slider_val = int(ratio * 100)
                else:
                    slider_val = 0
                slider.setValue(slider_val)

                slider.installEventFilter(self.wheel_blocker)
                spin.installEventFilter(self.wheel_blocker)

                # Logic capturing local variables
                def on_slider_float(v, k=ini_key, s=spin, mn=min_f, mx=max_f):
                    # v is 0-100
                    ratio = v / 100.0
                    float_val = mn + (ratio * (mx - mn))
                    
                    if abs(s.value() - float_val) > 0.005:
                        s.blockSignals(True)
                        s.setValue(float_val)
                        s.blockSignals(False)
                    
                    self.config.set(section_name, k, f"{float_val:.6f}")

                def on_spin_float(v, k=ini_key, sl=slider, mn=min_f, mx=max_f):
                    # v is float
                    if mx > mn:
                        ratio = (v - mn) / (mx - mn)
                        slider_v = int(ratio * 100)
                    else:
                        slider_v = 0
                        
                    if sl.value() != slider_v:
                        sl.blockSignals(True)
                        sl.setValue(slider_v)
                        sl.blockSignals(False)
                        
                    self.config.set(section_name, k, f"{v:.6f}")

                slider.valueChanged.connect(on_slider_float)
                spin.valueChanged.connect(on_spin_float)

                h_layout.addWidget(slider)
                h_layout.addWidget(spin)
                
                widget = container
                
            elif widget_type == 'resolution_selector':
                # Special widget: "Resolution" dropdown that controls FullscreenWidth/Height
                widget = QComboBox()
                widget.setMinimumWidth(150)
                widget.installEventFilter(self.wheel_blocker)
                
                # Get available resolutions
                try:
                    resolutions = get_supported_resolutions()
                except:
                    # Fallback if ctypes fails
                    resolutions = [(1920, 1080), (1280, 720)]
                
                # Read current
                cur_w = self.config.get(section_name, "FullscreenWidth", fallback="1920")
                cur_h = self.config.get(section_name, "FullscreenHeight", fallback="1080")
                try:
                    cur_res = (int(cur_w), int(cur_h))
                except:
                    cur_res = (1920, 1080)
                
                # Add current if missing (top of list logic or simple append)
                if cur_res not in resolutions:
                    resolutions.insert(0, cur_res)
                    
                # Populate
                idx_to_select = 0
                for i, (w, h) in enumerate(resolutions):
                    widget.addItem(f"{w}x{h}", (w, h))
                    if (w, h) == cur_res:
                        idx_to_select = i
                        
                widget.setCurrentIndex(idx_to_select)
                
                # Connect
                def on_res_change(idx, w=widget, s=section_name):
                    data = w.itemData(idx)
                    if data:
                        wd, ht = data
                        self.config.set(s, "FullscreenWidth", str(wd))
                        self.config.set(s, "FullscreenHeight", str(ht))
                        
                widget.currentIndexChanged.connect(on_res_change)
                
            elif widget_type == 'int':
                widget = QSpinBox()
                widget.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                mn = min_val if min_val is not None else -1
                mx = max_val if max_val is not None else 999999
                widget.setRange(mn, mx)
                try: widget.setValue(int(float(val))) if val else widget.setValue(0)
                except: widget.setValue(0)
                
            elif widget_type == 'float':
                widget = QDoubleSpinBox()
                widget.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                mn = min_val if min_val is not None else 0.0
                mx = max_val if max_val is not None else 10000.0
                widget.setRange(mn, mx)
                widget.setSingleStep(0.01)
                widget.setDecimals(6)
                try: widget.setValue(float(val)) if val else widget.setValue(0.0)
                except: widget.setValue(0.0)
                
            elif widget_type == 'bool':
                widget = QCheckBox()
                widget.setChecked(val in ['1', 'On', 'True'])
                
            elif isinstance(widget_type, list): 
                widget = QComboBox()
                widget.addItems(widget_type)
                if val:
                    widget.setCurrentText(val)
                    
            else: 
                widget = QLineEdit(str(val))
            
            # Generic Signals (Only attach if NOT handled above!)
            if not is_mapped_combo:
                # Capture variables in lambdas to avoid loop variable leaking
                if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    if isinstance(widget, QDoubleSpinBox):
                        widget.valueChanged.connect(lambda v, s=section_name, o=ini_key: self.config.set(s, o, f"{v:.6f}"))
                    else:
                        widget.valueChanged.connect(lambda v, s=section_name, o=ini_key: self.config.set(s, o, str(v)))
                elif isinstance(widget, QCheckBox):
                    widget.stateChanged.connect(lambda v, s=section_name, o=ini_key: self.config.set(s, o, "1" if v else "0"))
                elif isinstance(widget, QComboBox):
                    # Only for simple list combos, NOT mapped ones
                    widget.currentTextChanged.connect(lambda v, s=section_name, o=ini_key: self.config.set(s, o, v))
                elif isinstance(widget, QLineEdit):
                    widget.textChanged.connect(lambda v, s=section_name, o=ini_key: self.config.set(s, o, v))
                
            
            # Form Layout used to handle this, now we do it manually in the block below
            # layout.addRow(display_label, widget)
            
            # Constrain widths for "smaller" look
            if isinstance(widget, (QSpinBox, QDoubleSpinBox, QComboBox, QSlider)):
                widget.installEventFilter(self.wheel_blocker)

            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setFixedWidth(70)
            elif isinstance(widget, QComboBox):
                widget.setMinimumWidth(100)
                widget.setMaximumWidth(200)
            elif isinstance(widget, QLineEdit):
                widget.setMaximumWidth(200)

            # Add to Grid: Row i, Label (0), Widget (1)
            row = layout.rowCount()
            
            lbl_widget = QLabel(display_label)
            lbl_widget.setStyleSheet("color: #ccc; font-size: 11px;") # Slightly smaller font
            
            layout.addWidget(lbl_widget, row, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(widget, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
        group.setLayout(layout)
        return group

    def setup_tabs(self):
        # Clear existing
        for tab in [self.tab_graphics]:
            if tab.layout():
                QWidget().setLayout(tab.layout()) # Garbage collect old layout
            
        # --- GRAPHICS TAB ---
        layout_gfx = QVBoxLayout(self.tab_graphics)
        scroll_gfx = QScrollArea()
        scroll_gfx.setWidgetResizable(True)
        content_gfx = QWidget()
        content_gfx.setObjectName("ScrollContent")
        vbox_gfx = QVBoxLayout(content_gfx)
        
        # Display Section
        vbox_gfx.addWidget(self.create_form_group("Display", "Display", [
            ("Mode", ["BorderlessFullscreen", "Windowed"]),
            ("FullscreenMode", ["BorderlessFullscreen", "Windowed"]),
            ("Resolution", "resolution_selector"),
            (("Gamma", "Brightness"), "slider_float", 0.0, 1.0),
            ("VerticalFOV", "int", 50, 170),
        ]))
        
        # Rendering Section

        
        graphics_quality_map = [
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
        ]

        texture_quality_map = [
            ("Low", "3"),
            ("Medium", "2"),
            ("High", "1"),
            ("Ultra", "0")
        ]

        shadow_quality_map = [
            ("Off", "0"),
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
            ("Ultra", "4"),
        ]

        lighting_quality_map = [
            ("Low", "1"),
            ("Medium", "3"),
            ("High", "2"),
        ]

        effects_quality_map = [
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
        ]

        terrain_quality_map = [
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
        ]

        flora_quality_map = [
            ("Off", "4"),
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
        ]
        
        model_quality_map = [
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
        ]
        
        particle_map = [
            ("Low", "0"),
            ("Medium", "1"),
            ("High", "2"),
            ("Ultra", "3"),
        ]

        # Common fallback for -1/Custom if needed by maps
        
        vbox_gfx.addWidget(self.create_form_group("Rendering", "Rendering", [

            ("GraphicsQuality", "mapped_combo", graphics_quality_map),
            ("TextureQuality", "mapped_combo", texture_quality_map), 
            ("ShadowQuality", "mapped_combo", shadow_quality_map),
            ("LightingQuality", "mapped_combo", lighting_quality_map),
            ("EffectsQuality", "mapped_combo", effects_quality_map),
            ("TerrainQuality", "mapped_combo", terrain_quality_map),
            ("FloraQuality", "mapped_combo", flora_quality_map),
            ("ModelQuality", "mapped_combo", model_quality_map),
            ("ParticleLOD", "mapped_combo", particle_map),
            ("RenderQuality", "slider_percent"), # 50% - 250%
            (("RenderDistance", "Global Render Distance"), "slider_distance"),
            ("UseGlobalRenderDistance", "bool"),
            ("InfantryRenderDistance", "slider_distance"),
            ("GroundVehicleRenderDistance", "slider_distance"),
            ("AirVehicleRenderDistance", "slider_distance"),
            ("VSync", "bool"),
            ("FogShadowsEnable", "bool"),
            ("AmbientOcclusion", "bool"),
            ("BloomEnabled", "bool"),
            ("Smoothing", "bool"),
            ("Smoothingmaxframerate", "int"),
            ("Smoothingminframerate", "int"),
        ]))
        vbox_gfx.addStretch()
        scroll_gfx.setWidget(content_gfx)
        layout_gfx.addWidget(scroll_gfx)

        vbox_gfx.addStretch()
        scroll_gfx.setWidget(content_gfx)
        layout_gfx.addWidget(scroll_gfx)

    def load_ini_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open UserOptions.ini", self.base_path, "INI Files (*.ini);;All Files (*)")
        if path:
            self.load_ini(path)

    def load_default_ini(self):
        # 1. Try to find path in config.json (Dior Client config)
        config_json_path = os.path.join(self.base_path, "config.json")
        game_ini_path = None
        
        if os.path.exists(config_json_path):
            try:
                with open(config_json_path, 'r') as f:
                    data = json.load(f)
                    ps2_path = data.get("ps2_path", "")
                    if ps2_path and os.path.exists(ps2_path):
                        candidate = os.path.join(ps2_path, "UserOptions.ini")
                        if os.path.exists(candidate):
                            game_ini_path = candidate
            except Exception as e:
                print(f"Error reading config.json: {e}")

        # 2. Decision Logic
        if game_ini_path:
            self.load_ini(game_ini_path)
            # Make sure we know we are editing the LIVE config
            self.lbl_status.setText(f"Loaded LIVE Config: {game_ini_path}")
        else:
            # Fallback to assets/UserOptions_low.ini
            low_path = os.path.join(self.base_path, "assets", "Planetside 2 ini", "UserOptions_low.ini")
            if os.path.exists(low_path):
                self.load_ini(low_path)
                self.lbl_status.setText(f"Loaded Default: {os.path.basename(low_path)}")
            else:
                self.lbl_status.setText("No default INI found. Please load manually.")
                # Still setup tabs with empty/default config
                self.setup_tabs()

    def load_ini(self, path):
        try:
            self.config.read(path)
            
            # FORCE OverallQuality to Custom (-1)
            if not self.config.has_section("Rendering"):
                self.config.add_section("Rendering")
            self.config.set("Rendering", "OverallQuality", "-1")
            
            self.current_ini_path = path
            self.setup_tabs()
            self.lbl_status.setText(f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load INI file:\n{str(e)}")

    def save_settings_dialog(self):
        # Helper dialog to choose target
        msg = QDialog(self)
        msg.setWindowTitle("Save Configuration")
        msg.setFixedSize(350, 200)
        msg.setStyleSheet("background-color: #222; color: #fff;")
        
        layout = QVBoxLayout(msg)
        layout.addWidget(QLabel("Select Target Profile to Overwrite:"))
        
        btn_low = QPushButton("SAVE AS: LOW Profile")
        btn_low.clicked.connect(lambda: self.save_to_file("low", msg))
        btn_low.setStyleSheet("background-color: #660000; color: white; padding: 10px;")
        
        btn_high = QPushButton("SAVE AS: HIGH Profile")
        btn_high.clicked.connect(lambda: self.save_to_file("high", msg))
        btn_high.setStyleSheet("background-color: #006600; color: white; padding: 10px;")
        
        layout.addWidget(btn_low)
        layout.addWidget(btn_high)
        
        layout.addWidget(QLabel("Note: This will overwrite the selected profile in assets."))
        
        msg.exec()

    def save_to_file(self, mode, dialog):
        dialog.close()
        
        if mode == "low":
            filename = "UserOptions_low.ini"
        else:
            filename = "UserOptions_high.ini"
            
        target_path = os.path.join(self.base_path, "assets", "Planetside 2 ini", filename)
        
        # Ensure dir exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        try:
            with open(target_path, 'w') as configfile:
                self.config.write(configfile)
            
            QMessageBox.information(self, "Success", f"Settings saved to:\n{filename}")
            self.lbl_status.setText(f"Saved: {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{str(e)}")

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = PS2SettingsEditor(base_path=os.path.dirname(os.path.abspath(__file__)))
    window.show()
    sys.exit(app.exec())
