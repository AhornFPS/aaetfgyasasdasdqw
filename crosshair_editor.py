import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QSlider, QComboBox, QColorDialog, 
                             QFrame, QCheckBox, QApplication, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QAction

# Import dior_utils relative to where this file will be (root of project)
from dior_utils import get_asset_path, BASE_DIR

class CrosshairEditorWindow(QMainWindow):
    crosshair_saved = pyqtSignal(str) # Emits filename when saved

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DIOR - CROSSHAIR EDITOR")
        self.resize(1200, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #111; }
            QWidget { font-family: 'Consolas', sans-serif; color: #eee; }
            QFrame#ControlPanel { background-color: #1a1a1a; border-left: 1px solid #333; }
            QLabel { font-size: 12px; }
            QLabel#Header { font-size: 16px; font-weight: bold; color: #00f2ff; margin-bottom: 10px; }
            QPushButton { 
                background-color: #2a2a2a; color: #ddd; border: 1px solid #444; 
                padding: 5px 10px; border-radius: 3px; 
            }
            QPushButton:hover { background-color: #3a3a3a; border-color: #00f2ff; color: white; }
            QComboBox { background-color: #222; border: 1px solid #444; padding: 4px; color: #eee; }
            QSlider::handle:horizontal { background-color: #00f2ff; width: 10px; margin: -5px 0; border-radius: 5px; }
            QSlider::groove:horizontal { background-color: #333; height: 4px; border-radius: 2px; }
        """)

        # Default Settings
        self.settings = {
            "shape": "Cross", # Cross, Dot, Circle, T-Shape
            "color": QColor(0, 255, 0),
            "size": 20,
            "thickness": 2,
            "gap": 4,
            "dot_size": 0, # 0 = No center dot
            "outline": True,
            "outline_color": QColor(0, 0, 0),
            "outline_thickness": 1
        }

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. PREVIEW AREA (Left/Center)
        self.preview_area = QWidget()
        self.preview_area.setStyleSheet("background-color: #666666;") # Neutral Gray for better visibility
        # Override paintEvent for preview
        self.preview_area.paintEvent = self.paint_preview
        
        main_layout.addWidget(self.preview_area, 1) # Expand

        # 2. CONTROL PANEL (Right)
        control_panel = QFrame()
        control_panel.setObjectName("ControlPanel")
        control_panel.setFixedWidth(350)
        ctrl_layout = QVBoxLayout(control_panel)
        ctrl_layout.setContentsMargins(20, 20, 20, 20)
        ctrl_layout.setSpacing(15)

        # Header
        ctrl_layout.addWidget(QLabel("CROSSHAIR SETTINGS", objectName="Header"))

        # Shape
        ctrl_layout.addWidget(QLabel("Shape:"))
        self.combo_shape = QComboBox()
        self.combo_shape.addItems(["Cross", "Dot", "Circle", "T-Shape"])
        self.combo_shape.currentTextChanged.connect(self.update_shape)
        ctrl_layout.addWidget(self.combo_shape)

        # Color
        color_row = QHBoxLayout()
        self.btn_color = QPushButton("Color")
        self.btn_color.clicked.connect(self.choose_color)
        self.lbl_color_preview = QLabel("   ")
        self.lbl_color_preview.setStyleSheet(f"background-color: {self.settings['color'].name()}; border: 1px solid #fff;")
        self.lbl_color_preview.setFixedSize(30, 20)
        color_row.addWidget(self.btn_color)
        color_row.addWidget(self.lbl_color_preview)
        color_row.addStretch()
        ctrl_layout.addLayout(color_row)

        # Sliders
        self.add_slider(ctrl_layout, "Size", 4, 100, self.settings["size"], self.update_size)
        self.add_slider(ctrl_layout, "Thickness", 1, 20, self.settings["thickness"], self.update_thickness)
        self.add_slider(ctrl_layout, "Gap", 0, 50, self.settings["gap"], self.update_gap)
        self.add_slider(ctrl_layout, "Center Dot Size", 0, 20, self.settings["dot_size"], self.update_dot)

        # Outline
        outline_row = QHBoxLayout()
        self.chk_outline = QCheckBox("Enable Outline")
        self.chk_outline.setChecked(self.settings["outline"])
        self.chk_outline.toggled.connect(self.toggle_outline)
        outline_row.addWidget(self.chk_outline)
        ctrl_layout.addLayout(outline_row)

        self.add_slider(ctrl_layout, "Outline Thickness", 1, 5, self.settings["outline_thickness"], self.update_outline_thick)

        ctrl_layout.addStretch()

        # Actions
        btn_layout = QHBoxLayout()
        
        self.btn_save = QPushButton("SAVE & USE")
        self.btn_save.setStyleSheet("background-color: #004400; color: #00ff00; font-weight: bold; py: 10px;")
        self.btn_save.setFixedHeight(40)
        self.btn_save.clicked.connect(self.save_crosshair)
        
        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setStyleSheet("background-color: #440000; color: #ffcccc;")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.clicked.connect(self.close)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        ctrl_layout.addLayout(btn_layout)

        main_layout.addWidget(control_panel)

    def add_slider(self, layout, label_text, min_val, max_val, init_val, handler):
        row = QVBoxLayout()
        row.setSpacing(2)
        lbl = QLabel(f"{label_text}: {init_val}")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        
        # Lambda to update label and call handler
        def value_changed(val):
            lbl.setText(f"{label_text}: {val}")
            handler(val)
            self.preview_area.update()

        slider.valueChanged.connect(value_changed)
        
        row.addWidget(lbl)
        row.addWidget(slider)
        layout.addLayout(row)

    # --- UPDATERS ---
    def update_shape(self, text):
        self.settings["shape"] = text
        self.preview_area.update()

    def update_size(self, val):
        self.settings["size"] = val

    def update_thickness(self, val):
        self.settings["thickness"] = val

    def update_gap(self, val):
        self.settings["gap"] = val

    def update_dot(self, val):
        self.settings["dot_size"] = val

    def toggle_outline(self, checked):
        self.settings["outline"] = checked
        self.preview_area.update()
        
    def update_outline_thick(self, val):
        self.settings["outline_thickness"] = val

    def choose_color(self):
        c = QColorDialog.getColor(self.settings["color"], self, "Select Crosshair Color")
        if c.isValid():
            self.settings["color"] = c
            self.lbl_color_preview.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #fff;")
            self.preview_area.update()

    # --- PAINTING ---
    def paint_preview(self, event):
        painter = QPainter(self.preview_area)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw Background Grid (Optional, for better visibility)
        w = self.preview_area.width()
        h = self.preview_area.height()
        cx = w / 2
        cy = h / 2

        # Draw Crosshair
        self.draw_crosshair(painter, cx, cy)

    def draw_crosshair(self, painter, cx, cy):
        s = self.settings
        
        # Explicit Casting for safety
        size = int(s["size"])
        thickness = int(s["thickness"])
        gap = int(s["gap"])
        dot_size = int(s["dot_size"])
        outline_thickness = int(s["outline_thickness"])
        
        # Prepare Pens
        main_pen = QPen(s["color"])
        main_pen.setWidth(thickness)
        main_pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        outline_pen = QPen(s["outline_color"])
        # Outline width = thickness + 2 * outline_thickness
        outline_pen.setWidth(thickness + (outline_thickness * 2))
        outline_pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        lines = []

        # Calculate Lines based on Shape
        half_len = size / 2

        if s["shape"] in ["Cross", "T-Shape"]:
            # Horizontal (Left)
            lines.append((cx - half_len, cy, cx - gap, cy))
            # Horizontal (Right)
            lines.append((cx + gap, cy, cx + half_len, cy))
            
            # Vertical (Top)
            lines.append((cx, cy - half_len, cx, cy - gap))
            
            # Vertical (Bottom)
            if s["shape"] == "Cross":
               lines.append((cx, cy + gap, cx, cy + half_len))
        
        # Paint Logic
        # 1. Outline (First pass)
        if s["outline"]:
            for x1, y1, x2, y2 in lines:
                painter.setPen(outline_pen)
                painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
            
            # Dot Outline
            if dot_size > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(s["outline_color"])
                r = dot_size / 2 + outline_thickness # Radius roughly
                # Draw slightly larger circle
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # 2. Main Color (Second pass)
        for x1, y1, x2, y2 in lines:
            painter.setPen(main_pen)
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
        
        # 3. Shape Specifics (Circle, Dot)
        if s["shape"] == "Circle":
            # Outline
            if s["outline"]:
                painter.setPen(outline_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                rad = size / 2
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(rad), int(rad))
                
            # Fill
            painter.setPen(main_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rad = size / 2
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(rad), int(rad))

        if s["shape"] == "Dot":
             # Already handled by Center Dot logic mostly, but if Shape is Dot, we force a dot?
             pass

        # Center Dot
        if dot_size > 0 or s["shape"] == "Dot":
            sz = dot_size
            if s["shape"] == "Dot": sz = max(sz, size / 2)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(s["color"])
            # Draw ellipse expects radius or diameter depending on overload, QPoint + rx + ry is radius
            # Let's use bounding rect for clarity or radius
            rad = sz / 2
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(rad), int(rad))


    def save_crosshair(self):
        # Create a QPixmap to render into
        # Size: 128x128 should be enough for most crosshairs
        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw at center
        self.draw_crosshair(painter, size/2, size/2)
        painter.end()

        # Save to assets
        filename = "custom_crosshair_gen.png"
        save_path = get_asset_path(filename)
        
        try:
            pixmap.save(save_path, "PNG")
            self.crosshair_saved.emit(filename)
            QMessageBox.information(self, "Success", f"Crosshair saved to {filename}!")
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save crosshair: {str(e)}")

# Test
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CrosshairEditorWindow()
    win.show()
    sys.exit(app.exec())
