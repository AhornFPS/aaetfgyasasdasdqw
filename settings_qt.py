import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QSlider, QComboBox, QSizePolicy, QSpinBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

# --- STYLING ---
SETTING_STYLE = """
QWidget#Settings { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a1a, stop:1 #121212); 
}

QFrame#Group { 
    background-color: rgba(35, 35, 35, 0.7); 
    border: 1px solid #333; 
    border-radius: 12px; 
    margin-top: 15px;
    padding: 10px;
}

QFrame#Group:hover {
    border: 1px solid #444;
    background-color: rgba(45, 45, 45, 0.8);
}

QLabel#GroupTitle { 
    color: #00f2ff; 
    font-weight: bold; 
    font-size: 16px; 
    font-family: 'Black Ops One', sans-serif;
    padding-bottom: 8px;
    text-transform: uppercase;
}

QLabel#InfoText { 
    color: #888; 
    font-size: 12px; 
    margin-bottom: 5px;
}

QLabel#PathLabel { 
    color: #ffffff; 
    background-color: #050505; 
    border: 1px solid #333; 
    padding: 12px; 
    border-radius: 6px;
    font-family: 'Consolas', monospace;
}

QPushButton#ActionBtn { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333, stop:1 #222);
    color: #00f2ff; 
    border: 1px solid #444; 
    padding: 10px 20px; 
    font-weight: bold; 
    border-radius: 6px; 
    font-size: 13px;
    text-transform: uppercase;
}

QPushButton#ActionBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #333);
    border-color: #00f2ff; 
    color: white;
}

QPushButton#SaveBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #006600, stop:1 #003300);
    color: #00ff00;
    font-weight: bold;
    border-radius: 6px;
    padding: 15px 25px;
    font-size: 14px;
    border: 1px solid #00ff00;
    text-transform: uppercase;
}

QPushButton#SaveBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00aa00, stop:1 #005500); 
    border-color: #ffffff; 
    color: white;
}

QPushButton#ClearBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #440000, stop:1 #220000);
    color: #ff4444; 
    border: 1px solid #660000; 
    padding: 10px 20px; 
    font-weight: bold; 
    border-radius: 6px; 
    font-size: 13px;
    text-transform: uppercase;
}

QPushButton#ClearBtn:hover { 
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #660000, stop:1 #440000);
    border-color: #ff0000; 
    color: white;
}

/* Custom Slider Styling */
QSlider::groove:horizontal {
    border: 1px solid #333;
    height: 6px;
    background: #111;
    margin: 2px 0;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f2ff, stop:1 #006666);
    border: 1px solid #00f2ff;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #ffffff;
    border: 1px solid #00f2ff;
}
"""


class SettingsSignals(QObject):
    save_requested = pyqtSignal(dict)  # Send config data to Main
    browse_ps2_requested = pyqtSignal()  # Trigger for folder dialog
    browse_bg_requested = pyqtSignal()  # Trigger for Background-Dialog
    clear_bg_requested = pyqtSignal()   # Trigger for Background Reset
    check_updates_requested = pyqtSignal()  # Trigger for release update checks


class SettingsWidget(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.is_dev_environment = not bool(getattr(sys, "frozen", False))
        self.setObjectName("Settings")
        self.setStyleSheet(SETTING_STYLE)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.signals = SettingsSignals()

        # Layout Setup: keep settings content scrollable so page growth
        # does not force a larger minimum size for the whole app window.
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # Headline
        head = QLabel("GLOBAL CONFIGURATION")
        head.setStyleSheet("font-size: 24px; color: #00f2ff; font-weight: bold; font-family: 'Impact';")
        main_layout.addWidget(head)

        # --- GROUP 1: GAME PATH ---
        self.game_group = QFrame(objectName="Group")
        game_layout = QVBoxLayout(self.game_group)
        game_layout.setContentsMargins(15, 15, 15, 15)

        game_layout.addWidget(QLabel("> PLANETSIDE 2 DIRECTORY", objectName="GroupTitle"))
        game_layout.addWidget(QLabel("Required for UserOptions.ini modifications (Launcher)", objectName="InfoText"))

        # Path Display & Button
        path_row = QHBoxLayout()
        self.lbl_ps2_path = QLabel("Checking config...", objectName="PathLabel")
        self.lbl_ps2_path.setMinimumWidth(300)

        self.btn_ps2 = QPushButton("BROWSE FOLDER", objectName="ActionBtn")
        self.btn_ps2.setFixedWidth(150)
        self.btn_ps2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ps2.clicked.connect(lambda: self.signals.browse_ps2_requested.emit())

        path_row.addWidget(self.lbl_ps2_path)
        path_row.addWidget(self.btn_ps2)
        game_layout.addLayout(path_row)

        main_layout.addWidget(self.game_group)

        # --- GROUP 2: AUDIO ---
        self.audio_group = QFrame(objectName="Group")
        audio_layout = QVBoxLayout(self.audio_group)
        audio_layout.setContentsMargins(15, 15, 15, 15)

        audio_layout.addWidget(QLabel("> AUDIO SETTINGS", objectName="GroupTitle"))

        # Volume Slider
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Master Volume:", styleSheet="color: white;"))

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(50)
        self.slider_vol.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.slider_vol.setStyleSheet("QSlider::handle:horizontal { background-color: #00f2ff; }")

        self.lbl_vol_val = QLabel("50%")
        self.lbl_vol_val.setFixedWidth(40)
        self.lbl_vol_val.setStyleSheet("color: #00f2ff; font-weight: bold; font-family: Consolas;")
        self.lbl_vol_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # --- IMPORTANT: AUTO-SAVE ---

        # 1. Visual update while dragging (only changes text)
        self.slider_vol.valueChanged.connect(self.update_volume_label)

        # 2. Save on release (Performance!)
        self.slider_vol.sliderReleased.connect(self.request_save)

        vol_row.addWidget(self.slider_vol)
        vol_row.addWidget(self.lbl_vol_val)
        audio_layout.addLayout(vol_row)
        
        # Audio Device Selector
        device_row = QHBoxLayout()
        device_row.addWidget(QLabel("Output Device:", styleSheet="color: white;"))
        
        self.combo_audio_device = QComboBox()
        self.combo_audio_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_audio_device.setStyleSheet("""
            QComboBox {
                background-color: #111;
                border: 1px solid #444;
                color: #eee;
                padding: 6px;
                border-radius: 3px;
            }
            QComboBox:focus { 
                border: 1px solid #00f2ff; 
                background-color: #000; 
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #111;
                color: #eee;
                border: 1px solid #333;
                selection-background-color: #00f2ff;
                selection-color: #000;
            }
        """)
        
        self.populate_audio_devices()
        self.combo_audio_device.currentIndexChanged.connect(self.request_save)
        
        device_row.addWidget(self.combo_audio_device)
        audio_layout.addLayout(device_row)

        main_layout.addWidget(self.audio_group)

        # --- GROUP 3: UI VISUALS ---
        self.ui_group = QFrame(objectName="Group")
        ui_layout = QVBoxLayout(self.ui_group)
        ui_layout.setContentsMargins(15, 15, 15, 15)

        ui_layout.addWidget(QLabel("> CLIENT APPEARANCE", objectName="GroupTitle"))

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("Menu Background Image:", styleSheet="color: #aaa;"))
        
        self.lbl_bg_name = QLabel("No image selected", objectName="PathLabel")
        self.lbl_bg_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_bg = QPushButton("CHANGE IMAGE", objectName="ActionBtn")
        self.btn_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bg.clicked.connect(lambda: self.signals.browse_bg_requested.emit())

        self.btn_clear_bg = QPushButton("CLEAR", objectName="ClearBtn")
        self.btn_clear_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_bg.clicked.connect(lambda: self.signals.clear_bg_requested.emit())

        bg_row.addWidget(self.lbl_bg_name)
        bg_row.addWidget(self.btn_bg)
        bg_row.addWidget(self.btn_clear_bg)
        ui_layout.addLayout(bg_row)

        main_layout.addWidget(self.ui_group)

        # --- GROUP 4: DISCORD ---
        self.discord_group = QFrame(objectName="Group")
        discord_layout = QVBoxLayout(self.discord_group)
        discord_layout.setContentsMargins(15, 15, 15, 15)

        discord_layout.addWidget(QLabel("> DISCORD INTEGRATION", objectName="GroupTitle"))
        discord_layout.addWidget(
            QLabel("Share your current character, server, and last seen base in Discord Rich Presence.",
                   objectName="InfoText")
        )

        discord_row = QHBoxLayout()
        discord_row.addWidget(QLabel("Discord Rich Presence:", styleSheet="color: #aaa;"))

        self.btn_discord_presence = QPushButton(objectName="ActionBtn")
        self.btn_discord_presence.setCheckable(True)
        self.btn_discord_presence.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_discord_presence.toggled.connect(self.on_discord_presence_toggled)
        self.update_discord_presence_button(False)

        discord_row.addStretch()
        discord_row.addWidget(self.btn_discord_presence)
        discord_layout.addLayout(discord_row)

        main_layout.addWidget(self.discord_group)

        # --- GROUP 5: OVERLAY RUNTIME ---
        self.runtime_group = QFrame(objectName="Group")
        runtime_layout = QVBoxLayout(self.runtime_group)
        runtime_layout.setContentsMargins(15, 15, 15, 15)
        runtime_layout.addWidget(QLabel("> OVERLAY RUNTIME", objectName="GroupTitle"))
        runtime_layout.addWidget(QLabel("Choose which overlay renderer should be active.", objectName="InfoText"))

        runtime_row = QHBoxLayout()
        runtime_row.addWidget(QLabel("Overlay Backend:", styleSheet="color: #aaa;"))
        self.combo_overlay_backend = QComboBox()
        self.combo_overlay_backend.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_overlay_backend.setStyleSheet("""
            QComboBox {
                background-color: #111;
                border: 1px solid #444;
                color: #eee;
                padding: 6px;
                border-radius: 3px;
                min-width: 170px;
            }
            QComboBox:focus {
                border: 1px solid #00f2ff;
                background-color: #000;
            }
            QComboBox::drop-down { border: 0px; }
            QComboBox QAbstractItemView {
                background-color: #111;
                color: #eee;
                border: 1px solid #333;
                selection-background-color: #00f2ff;
                selection-color: #000;
            }
        """)
        self.combo_overlay_backend.addItem("Legacy (Qt/Web)", "legacy")
        self.combo_overlay_backend.addItem("Tauri Spike", "tauri")
        self.combo_overlay_backend.currentIndexChanged.connect(self.request_save)
        runtime_row.addStretch()
        runtime_row.addWidget(self.combo_overlay_backend)
        runtime_layout.addLayout(runtime_row)
        main_layout.addWidget(self.runtime_group)

        # --- GROUP 6: DEV TOOLS (SOURCE ONLY) ---
        self.dev_group = QFrame(objectName="Group")
        dev_layout = QVBoxLayout(self.dev_group)
        dev_layout.setContentsMargins(15, 15, 15, 15)

        dev_layout.addWidget(QLabel("> DEVELOPER TOOLS", objectName="GroupTitle"))
        dev_layout.addWidget(QLabel("Source-mode diagnostics for overlay development.", objectName="InfoText"))

        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Overlay Perf Debug HUD:", styleSheet="color: #aaa;"))

        self.btn_overlay_perf_debug = QPushButton(objectName="ActionBtn")
        self.btn_overlay_perf_debug.setCheckable(True)
        self.btn_overlay_perf_debug.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_overlay_perf_debug.toggled.connect(self.on_overlay_perf_debug_toggled)
        self.update_overlay_perf_debug_button(False)

        dev_row.addStretch()
        dev_row.addWidget(self.btn_overlay_perf_debug)
        dev_layout.addLayout(dev_row)

        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("WS Batch Mode (v2):", styleSheet="color: #aaa;"))
        self.btn_ws_batching_v2 = QPushButton(objectName="ActionBtn")
        self.btn_ws_batching_v2.setCheckable(True)
        self.btn_ws_batching_v2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ws_batching_v2.toggled.connect(self.on_ws_batching_toggled)
        self.update_ws_batching_button(False)
        batch_row.addStretch()
        batch_row.addWidget(self.btn_ws_batching_v2)
        dev_layout.addLayout(batch_row)

        trace_row = QHBoxLayout()
        trace_row.addWidget(QLabel("Event Trace Export (JSONL):", styleSheet="color: #aaa;"))
        self.btn_overlay_trace_export = QPushButton(objectName="ActionBtn")
        self.btn_overlay_trace_export.setCheckable(True)
        self.btn_overlay_trace_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_overlay_trace_export.toggled.connect(self.on_trace_export_toggled)
        self.update_trace_export_button(False)
        trace_row.addStretch()
        trace_row.addWidget(self.btn_overlay_trace_export)
        dev_layout.addLayout(trace_row)

        pipeline_row = QHBoxLayout()
        pipeline_row.addWidget(QLabel("Event Pipeline v2:", styleSheet="color: #aaa;"))
        self.btn_event_pipeline_v2 = QPushButton(objectName="ActionBtn")
        self.btn_event_pipeline_v2.setCheckable(True)
        self.btn_event_pipeline_v2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_event_pipeline_v2.toggled.connect(self.on_event_pipeline_toggled)
        self.update_event_pipeline_button(True)
        pipeline_row.addStretch()
        pipeline_row.addWidget(self.btn_event_pipeline_v2)
        dev_layout.addLayout(pipeline_row)

        scheduler_row = QHBoxLayout()
        scheduler_row.addWidget(QLabel("JS Scheduler v2:", styleSheet="color: #aaa;"))
        self.btn_js_scheduler_v2 = QPushButton(objectName="ActionBtn")
        self.btn_js_scheduler_v2.setCheckable(True)
        self.btn_js_scheduler_v2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_js_scheduler_v2.toggled.connect(self.on_js_scheduler_toggled)
        self.update_js_scheduler_button(True)
        scheduler_row.addStretch()
        scheduler_row.addWidget(self.btn_js_scheduler_v2)
        dev_layout.addLayout(scheduler_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Overlay Flush FPS:", styleSheet="color: #aaa;"))
        self.combo_overlay_fps = QComboBox()
        self.combo_overlay_fps.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_overlay_fps.setStyleSheet("""
            QComboBox {
                background-color: #111;
                border: 1px solid #444;
                color: #eee;
                padding: 6px;
                border-radius: 3px;
                min-width: 90px;
            }
            QComboBox:focus {
                border: 1px solid #00f2ff;
                background-color: #000;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #111;
                color: #eee;
                border: 1px solid #333;
                selection-background-color: #00f2ff;
                selection-color: #000;
            }
        """)
        for fps in (30, 60, 90, 120, 144, 165, 240):
            self.combo_overlay_fps.addItem(str(fps))
        self.combo_overlay_fps.currentIndexChanged.connect(self.request_save)
        fps_row.addStretch()
        fps_row.addWidget(self.combo_overlay_fps)
        dev_layout.addLayout(fps_row)

        dedupe_row = QHBoxLayout()
        dedupe_row.addWidget(QLabel("Event Dedupe Window (ms):", styleSheet="color: #aaa;"))
        self.spin_overlay_dedupe_ms = QSpinBox()
        self.spin_overlay_dedupe_ms.setRange(0, 5000)
        self.spin_overlay_dedupe_ms.setSingleStep(10)
        self.spin_overlay_dedupe_ms.setValue(120)
        self.spin_overlay_dedupe_ms.setStyleSheet("QSpinBox { background-color: #111; border: 1px solid #444; color: #eee; padding: 6px; border-radius: 3px; }")
        self.spin_overlay_dedupe_ms.valueChanged.connect(self.request_save)
        dedupe_row.addStretch()
        dedupe_row.addWidget(self.spin_overlay_dedupe_ms)
        dev_layout.addLayout(dedupe_row)

        transient_row = QHBoxLayout()
        transient_row.addWidget(QLabel("Transient Queue Cap:", styleSheet="color: #aaa;"))
        self.spin_overlay_transient_cap = QSpinBox()
        self.spin_overlay_transient_cap.setRange(64, 20000)
        self.spin_overlay_transient_cap.setSingleStep(64)
        self.spin_overlay_transient_cap.setValue(2048)
        self.spin_overlay_transient_cap.setStyleSheet("QSpinBox { background-color: #111; border: 1px solid #444; color: #eee; padding: 6px; border-radius: 3px; }")
        self.spin_overlay_transient_cap.valueChanged.connect(self.request_save)
        transient_row.addStretch()
        transient_row.addWidget(self.spin_overlay_transient_cap)
        dev_layout.addLayout(transient_row)

        main_layout.addWidget(self.dev_group)
        self.dev_group.setVisible(self.is_dev_environment)

        # Spacer at the bottom
        main_layout.addStretch()

        # --- SAVE BUTTON (Manual) ---
        self.btn_save = QPushButton("SAVE SETTINGS", objectName="SaveBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        # The button now also uses the central request_save method
        self.btn_save.clicked.connect(self.request_save)
        main_layout.addWidget(self.btn_save)

        self.btn_check_updates = QPushButton("CHECK FOR UPDATES", objectName="ActionBtn")
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.clicked.connect(lambda: self.signals.check_updates_requested.emit())
        main_layout.addWidget(self.btn_check_updates)

    def populate_audio_devices(self):
        self.combo_audio_device.clear()
        self.combo_audio_device.addItem("Default")
        devices_added = set()
        
        try:
            import pygame
            import pygame._sdl2.audio as sdl2_audio

            # Ensure minimal init for listing
            if not pygame.get_init():
                pygame.init()
            
            # Need audio subsystem initialized to list
            if not pygame.mixer.get_init():
                try: pygame.mixer.init()
                except: pass

            try:
                # SDL2 device names (these are what the overlay uses)
                candidates = sdl2_audio.get_audio_device_names(False)
                for dev in candidates:
                    if dev not in devices_added:
                        self.combo_audio_device.addItem(dev)
                        devices_added.add(dev)
            except Exception as e:
                print(f"Audio List Error: {e}")
            
            # On Linux, also try pactl as backup if SDL2 found nothing
            if not devices_added and sys.platform != "win32":
                try:
                    import subprocess
                    result = subprocess.run(
                        ["pactl", "list", "sinks"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in result.stdout.split('\n'):
                        stripped = line.strip()
                        if stripped.startswith('Description:'):
                            desc = stripped.split(':', 1)[1].strip()
                            if desc not in devices_added:
                                self.combo_audio_device.addItem(desc)
                                devices_added.add(desc)
                except Exception:
                    pass

        except Exception as e:
            print(f"Audio Enum Error: {e}")

    def load_config(self, config_data, ps2_dir):
        """Fills the fields with the current values."""
        # 1. Path
        self.lbl_ps2_path.setText(ps2_dir if ps2_dir else "NOT_FOUND (Please Browse)")

        # 2. Audio Volume
        vol = config_data.get("audio_volume", 50)

        # --- IMPORTANT: Block signals during load ---
        # Prevents setting the value from triggering a "Save" event
        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(int(vol))
        self.slider_vol.blockSignals(False)

        self.lbl_vol_val.setText(f"{vol}%")
        
        # 3. Audio Device
        device = config_data.get("audio_device", "Default")
        self.combo_audio_device.blockSignals(True)
        index = self.combo_audio_device.findText(device)
        if index >= 0:
            self.combo_audio_device.setCurrentIndex(index)
        else:
            self.combo_audio_device.setCurrentIndex(0) # Default
        self.combo_audio_device.blockSignals(False)

        # 4. Background Path
        bg_path = config_data.get("main_background_path", "")
        if bg_path:
            import os
            self.lbl_bg_name.setText(os.path.basename(bg_path))
        else:
            self.lbl_bg_name.setText("None")

        # 5. Discord Rich Presence
        discord_active = bool(config_data.get("discord_presence_active", False))
        self.btn_discord_presence.blockSignals(True)
        self.btn_discord_presence.setChecked(discord_active)
        self.btn_discord_presence.blockSignals(False)
        self.update_discord_presence_button(discord_active)

        # 6. Overlay perf debug (dev only)
        overlay_backend = str(config_data.get("overlay_backend", "legacy") or "legacy").strip().lower()
        self.combo_overlay_backend.blockSignals(True)
        idx_backend = self.combo_overlay_backend.findData(overlay_backend)
        if idx_backend < 0:
            idx_backend = self.combo_overlay_backend.findData("legacy")
        if idx_backend < 0:
            idx_backend = 0
        self.combo_overlay_backend.setCurrentIndex(idx_backend)
        self.combo_overlay_backend.blockSignals(False)

        # 7. Overlay perf debug (dev only)
        overlay_perf_debug = bool(config_data.get("overlay_perf_debug", False))
        self.btn_overlay_perf_debug.blockSignals(True)
        self.btn_overlay_perf_debug.setChecked(overlay_perf_debug)
        self.btn_overlay_perf_debug.blockSignals(False)
        self.update_overlay_perf_debug_button(overlay_perf_debug)

        ws_batching = bool(config_data.get("overlay_ws_batching_v2", False))
        self.btn_ws_batching_v2.blockSignals(True)
        self.btn_ws_batching_v2.setChecked(ws_batching)
        self.btn_ws_batching_v2.blockSignals(False)
        self.update_ws_batching_button(ws_batching)

        trace_export = bool(config_data.get("overlay_trace_export", False))
        self.btn_overlay_trace_export.blockSignals(True)
        self.btn_overlay_trace_export.setChecked(trace_export)
        self.btn_overlay_trace_export.blockSignals(False)
        self.update_trace_export_button(trace_export)

        event_pipeline_v2 = bool(config_data.get("event_pipeline_v2", True))
        self.btn_event_pipeline_v2.blockSignals(True)
        self.btn_event_pipeline_v2.setChecked(event_pipeline_v2)
        self.btn_event_pipeline_v2.blockSignals(False)
        self.update_event_pipeline_button(event_pipeline_v2)

        js_scheduler_v2 = bool(config_data.get("js_scheduler_v2", True))
        self.btn_js_scheduler_v2.blockSignals(True)
        self.btn_js_scheduler_v2.setChecked(js_scheduler_v2)
        self.btn_js_scheduler_v2.blockSignals(False)
        self.update_js_scheduler_button(js_scheduler_v2)

        # 8. Overlay flush FPS (dev only)
        overlay_flush_fps = int(config_data.get("overlay_flush_fps", 120) or 120)
        self.combo_overlay_fps.blockSignals(True)
        idx = self.combo_overlay_fps.findText(str(overlay_flush_fps))
        if idx < 0:
            self.combo_overlay_fps.setCurrentText("120")
        else:
            self.combo_overlay_fps.setCurrentIndex(idx)
        self.combo_overlay_fps.blockSignals(False)

        dedupe_ms = int(config_data.get("overlay_dedupe_window_ms", 120) or 120)
        self.spin_overlay_dedupe_ms.blockSignals(True)
        self.spin_overlay_dedupe_ms.setValue(max(0, min(5000, dedupe_ms)))
        self.spin_overlay_dedupe_ms.blockSignals(False)

        transient_cap = int(config_data.get("overlay_transient_max_pending", 2048) or 2048)
        self.spin_overlay_transient_cap.blockSignals(True)
        self.spin_overlay_transient_cap.setValue(max(64, min(20000, transient_cap)))
        self.spin_overlay_transient_cap.blockSignals(False)

    def update_discord_presence_button(self, active):
        if active:
            self.btn_discord_presence.setText("ENABLED")
            self.btn_discord_presence.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_discord_presence.setText("DISABLED")
            self.btn_discord_presence.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_discord_presence_toggled(self, active):
        self.update_discord_presence_button(bool(active))
        self.request_save()

    def update_overlay_perf_debug_button(self, active):
        if active:
            self.btn_overlay_perf_debug.setText("ENABLED")
            self.btn_overlay_perf_debug.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_overlay_perf_debug.setText("DISABLED")
            self.btn_overlay_perf_debug.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_overlay_perf_debug_toggled(self, active):
        self.update_overlay_perf_debug_button(bool(active))
        self.request_save()

    def update_ws_batching_button(self, active):
        if active:
            self.btn_ws_batching_v2.setText("ENABLED")
            self.btn_ws_batching_v2.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_ws_batching_v2.setText("DISABLED")
            self.btn_ws_batching_v2.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_ws_batching_toggled(self, active):
        self.update_ws_batching_button(bool(active))
        self.request_save()

    def update_trace_export_button(self, active):
        if active:
            self.btn_overlay_trace_export.setText("ENABLED")
            self.btn_overlay_trace_export.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_overlay_trace_export.setText("DISABLED")
            self.btn_overlay_trace_export.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_trace_export_toggled(self, active):
        self.update_trace_export_button(bool(active))
        self.request_save()

    def update_event_pipeline_button(self, active):
        if active:
            self.btn_event_pipeline_v2.setText("ENABLED")
            self.btn_event_pipeline_v2.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_event_pipeline_v2.setText("DISABLED")
            self.btn_event_pipeline_v2.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_event_pipeline_toggled(self, active):
        self.update_event_pipeline_button(bool(active))
        self.request_save()

    def update_js_scheduler_button(self, active):
        if active:
            self.btn_js_scheduler_v2.setText("ENABLED")
            self.btn_js_scheduler_v2.setStyleSheet(
                "QPushButton { background-color: #004400; color: white; font-weight: bold; border: 1px solid #006600; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #005500; border: 1px solid #00ff00; }"
            )
        else:
            self.btn_js_scheduler_v2.setText("DISABLED")
            self.btn_js_scheduler_v2.setStyleSheet(
                "QPushButton { background-color: #440000; color: #ffcccc; font-weight: bold; border: 1px solid #660000; padding: 10px 20px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #550000; border: 1px solid #ff4444; }"
            )

    def on_js_scheduler_toggled(self, active):
        self.update_js_scheduler_button(bool(active))
        self.request_save()

    def update_volume_label(self, val):
        """Only for optics while dragging."""
        self.lbl_vol_val.setText(f"{val}%")

    def request_save(self):
        """Collects data and sends it to Main (to save)."""
        data = {
            "audio_volume": self.slider_vol.value(),
            "audio_device": self.combo_audio_device.currentText(),
            "main_background_path": self.lbl_bg_name.text() if self.lbl_bg_name.text() != "None" else "",
            "discord_presence_active": bool(self.btn_discord_presence.isChecked()),
        }
        if self.is_dev_environment:
            data["overlay_perf_debug"] = bool(self.btn_overlay_perf_debug.isChecked())
            backend_data = self.combo_overlay_backend.currentData()
            data["overlay_backend"] = backend_data if backend_data else "legacy"
            try:
                data["overlay_flush_fps"] = int(self.combo_overlay_fps.currentText())
            except Exception:
                data["overlay_flush_fps"] = 120
            data["overlay_dedupe_window_ms"] = int(self.spin_overlay_dedupe_ms.value())
            data["overlay_transient_max_pending"] = int(self.spin_overlay_transient_cap.value())
            data["overlay_ws_batching_v2"] = bool(self.btn_ws_batching_v2.isChecked())
            data["overlay_trace_export"] = bool(self.btn_overlay_trace_export.isChecked())
            data["event_pipeline_v2"] = bool(self.btn_event_pipeline_v2.isChecked())
            data["js_scheduler_v2"] = bool(self.btn_js_scheduler_v2.isChecked())
        else:
            backend_data = self.combo_overlay_backend.currentData()
            data["overlay_backend"] = backend_data if backend_data else "legacy"
        # Send signal
        self.signals.save_requested.emit(data)


