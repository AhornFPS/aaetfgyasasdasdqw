import sys
import os
import configparser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTabWidget, QScrollArea, QFrame, QLineEdit, QComboBox, 
    QCheckBox, QPushButton, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QGroupBox, QSpinBox, QDoubleSpinBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal
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
    padding: 5px;
    border-radius: 3px;
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

class PS2SettingsEditor(QMainWindow):
    def __init__(self, parent=None, base_path=None):
        super().__init__(parent)
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
        self.tab_audio = QWidget()
        self.tab_interface = QWidget()
        self.tab_controls = QWidget()
        self.tab_general = QWidget()
        
        self.tabs.addTab(self.tab_graphics, "GRAPHICS")
        self.tabs.addTab(self.tab_audio, "AUDIO")
        self.tabs.addTab(self.tab_interface, "INTERFACE")
        self.tabs.addTab(self.tab_controls, "CONTROLS")
        self.tabs.addTab(self.tab_general, "GENERAL")
        
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
        layout = QFormLayout()
        
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
                
            elif widget_type == 'int':
                widget = QSpinBox()
                mn = min_val if min_val is not None else -1
                mx = max_val if max_val is not None else 999999
                widget.setRange(mn, mx)
                try: widget.setValue(int(float(val))) if val else widget.setValue(0)
                except: widget.setValue(0)
                
            elif widget_type == 'float':
                widget = QDoubleSpinBox()
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
                
            layout.addRow(display_label, widget)
            
        group.setLayout(layout)
        return group

    def setup_tabs(self):
        # Clear existing
        for tab in [self.tab_graphics, self.tab_audio, self.tab_interface, self.tab_controls, self.tab_general]:
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
            ("Mode", ["Windowed", "Fullscreen", "WindowedFullscreen"]),
            ("FullscreenMode", ["Windowed", "Fullscreen", "WindowedFullscreen"]),
            ("FullscreenWidth", "int"),
            ("FullscreenHeight", "int"),
            ("WindowedWidth", "int"),
            ("WindowedHeight", "int"),
            ("Maximized", "bool"),
            (("Gamma", "Brightness"), "float", 0.0, 1.0), # Renamed Gamma to Brightness
            ("VerticalFOV", "int", 50, 170),
        ]))
        
        # Rendering Section
        overall_quality_map = [
            ("Custom", "-1"),
            ("Very Low", "5"),
            ("Low", "1"),
            ("Medium", "2"),
            ("High", "3"),
            ("Ultra", "4"),

        ]
        
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
            ("OverallQuality", "mapped_combo", overall_quality_map),
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
            ("FogShadowsEnable", "bool"),
            ("MotionBlur", "bool"),
            ("VSync", "bool"),
            ("AO", "bool"),
            ("BloomEnabled", "bool"),
            ("Smoothing", "bool"),
            ("Smoothingmaxframerate", "int"),
            ("Smoothingminframerate", "int"),
            ("UseLod0a", "bool"),
        ]))
        vbox_gfx.addStretch()
        scroll_gfx.setWidget(content_gfx)
        layout_gfx.addWidget(scroll_gfx)

        # --- AUDIO TAB ---
        layout_aud = QVBoxLayout(self.tab_audio)
        scroll_aud = QScrollArea()
        scroll_aud.setWidgetResizable(True)
        content_aud = QWidget()
        content_aud.setObjectName("ScrollContent")
        vbox_aud = QVBoxLayout(content_aud)
        
        vbox_aud.addWidget(self.create_form_group("Sound Volumes", "Sound", [
            ("Master", "float", 0.0, 1.0),
            ("Music", "float", 0.0, 1.0),
            ("Game", "float", 0.0, 1.0),
            ("Dialog", "float", 0.0, 1.0),
            ("UI", "float", 0.0, 1.0),
        ]))
        vbox_aud.addWidget(self.create_form_group("Sound Options", "Sound", [
            ("HitIndicator", "bool"),
            ("LowAmmoIndicator", "bool"),
            ("VehicleChatter", "bool"),
            ("IdleMusic", "bool"),
            ("UseFloat32Output", "bool"),
            ("ExclusiveMode", "bool"),
        ]))
        vbox_aud.addWidget(self.create_form_group("Voice Chat Options", "Voice", [
            ("Enable", "bool"),
            ("Ducking", "float"),
            ("EchoEnabled", "bool"),
        ]))
        vbox_aud.addWidget(self.create_form_group("Voice Chat Volumes", "Voice", [
            ("ReceiveVolume", "float", 0.0, 100.0),
            ("MicrophoneVolume", "float", 0.0, 100.0),
            ("ProximityVolume", "float", 0.0, 100.0),
            ("SquadVolume", "float", 0.0, 100.0),
            ("OutfitVolume", "float", 0.0, 100.0),
            ("RaidVolume", "float", 0.0, 100.0),
        ]))
        vbox_aud.addStretch()
        scroll_aud.setWidget(content_aud)
        layout_aud.addWidget(scroll_aud)

        # --- INTERFACE TAB ---
        layout_int = QVBoxLayout(self.tab_interface)
        scroll_int = QScrollArea()
        scroll_int.setWidgetResizable(True)
        content_int = QWidget()
        content_int.setObjectName("ScrollContent")
        vbox_int = QVBoxLayout(content_int)
        
        vbox_int.addWidget(self.create_form_group("HUD Options", "UI", [
            ("DrawHud", "bool"), # Generally in [General] or [UI], putting here for clarity
            ("HudMode", "int"),
            ("CentralizedHudMode", "bool"),
            ("ShowReticleIFF", "bool"),
            ("HudShowHealth", "bool"),
            ("DrawMission", "bool"),
            ("DrawKillSpam", "bool"),
            ("DrawLootDrop", "bool"),
            ("ShowGroupNotifications", "bool"),
            ("ShowOutfitNotifications", "bool"),
            ("HudShowTopCompass", "bool"),
        ]))
        
        vbox_int.addWidget(self.create_form_group("HUD Customization", "UI", [
             ("HudTiltAngle", "int"),
             ("MiniMapZoomLevel", "float"),
             ("MapZoomLevel", "int"),
             ("MapStatisticsView", "bool"),
             ("OrbitalStrikeAlpha", "float"),
        ]))
        
        vbox_int.addWidget(self.create_form_group("Color Blind", "Rendering", [
             ("ColorBlindFilterType", "int"),
             ("ColorBlindFilterAmount", "float"),
             ("ColorBlindFilterStrength", "float"),
        ]))
        vbox_int.addStretch()
        scroll_int.setWidget(content_int)
        layout_int.addWidget(scroll_int)

        # --- CONTROLS TAB ---
        layout_ctrl = QVBoxLayout(self.tab_controls)
        scroll_ctrl = QScrollArea()
        scroll_ctrl.setWidgetResizable(True)
        content_ctrl = QWidget()
        content_ctrl.setObjectName("ScrollContent")
        vbox_ctrl = QVBoxLayout(content_ctrl)
        
        vbox_ctrl.addWidget(self.create_form_group("Mouse Sensitivity", "General", [
            ("MouseSensitivity", "float", 0.0, 1.0),
            ("ScopedMouseSensitivity", "float", 0.0, 1.0),
            ("ADSMouseSensitivity", "float", 0.0, 1.0),
            ("VehicleMouseSensitivity", "float", 0.0, 1.0),
            ("VehicleGunnerMouseSensitivity", "float", 0.0, 1.0),
            ("FlightMouseSensitivity", "float", 0.0, 1.0),
            ("JoystickSensitivity", "float", 0.0, 100.0),
        ]))
        vbox_ctrl.addWidget(self.create_form_group("Input Options", "General", [
            ("InvertVerticalLook", "bool"),
            ("InvertVerticalFly", "bool"),
            ("InvertTankSteering", "bool"),
            ("MouseRawInput", "bool"),
            ("MouseSmoothing", "bool"),
            ("JoystickDeadzone", "float"),
            ("JoystickEnable", "bool"),
        ]))
        vbox_ctrl.addStretch()
        scroll_ctrl.setWidget(content_ctrl)
        layout_ctrl.addWidget(scroll_ctrl)

        # --- GENERAL TAB ---
        layout_gen = QVBoxLayout(self.tab_general)
        scroll_gen = QScrollArea()
        scroll_gen.setWidgetResizable(True)
        content_gen = QWidget()
        content_gen.setObjectName("ScrollContent")
        vbox_gen = QVBoxLayout(content_gen)
        
        vbox_gen.addWidget(self.create_form_group("Gameplay", "General", [
            ("AutoDetectPerformanceSettings", "int"),
            ("ReduceInputLag", "bool"),
            ("SprintToggle", "bool"),
            ("ToggleCrouch", "bool"),
            ("ZoomToggle", "bool"),
            ("DecloakOnFire", "bool"),
            ("EnableAutoWield", "bool"),
            ("AbilityQueueSeconds", "float"),
        ]))
        vbox_gen.addWidget(self.create_form_group("Auto Refuse", "AutoRefuse", [
            ("FriendInvitation", "bool"),
            ("DuelInvitation", "bool"),
            ("GuildInvitation", "bool"),
            ("GroupInvitation", "bool"),
            ("TradeRequest", "bool"),
            ("Whispers", "bool"),
        ]))
        vbox_gen.addStretch()
        scroll_gen.setWidget(content_gen)
        layout_gen.addWidget(scroll_gen)

    def load_ini_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open UserOptions.ini", self.base_path, "INI Files (*.ini);;All Files (*)")
        if path:
            self.load_ini(path)

    def load_default_ini(self):
        # Try finding low ini first
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
