"""
Professional Ultrasound Imaging Software GUI using FAST + PySide2.

This module provides a professional DICOM viewer interface with:
- Left panel: File list
- Top toolbar: Tool buttons (pan, zoom, rotate, annotate, play, screenshot)
- Center: FAST-based ultrasound image viewer
- Bottom: Playback controls and status bar

Requirements:
    conda install pyside2 -c conda-forge
"""

import platform
import os
import sys
import numpy as np

# Suppress Qt font warning messages
os.environ['QT_LOGGING_RULES'] = 'qt.qpa.fonts.warning=false'

# Must import PySide2.QtSvg before FAST on non-Windows platforms
if platform.system() != 'Windows':
    import PySide2.QtSvg

import fast  # Must import FAST before rest of PySide2

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QToolBar, QToolButton,
    QStatusBar, QSlider, QLabel, QPushButton, QFileDialog, QMessageBox,
    QFrame, QSizePolicy, QAction, QActionGroup, QStyle, QMenu,
    QDialog, QScrollArea, QComboBox, QGroupBox, QCheckBox,
    QGraphicsOpacityEffect, QTreeView, QStyledItemDelegate, QAbstractItemView,
    QTabWidget, QTextEdit
)
from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt, Slot, QSize, QTimer, QModelIndex
from PySide2.QtGui import (
    QIcon, QFont, QPalette, QColor, QKeySequence, QImage, QPixmap, QPainter,
    QStandardItemModel, QStandardItem
)
from PySide2.QtWidgets import QShortcut
from shiboken2 import wrapInstance

from .annotations import AnnotationOverlay, LayerPanelWidget
from .fast_annotations import FASTAnnotationManager, CoordinateConverter
from .image_processing import (
    ColormapManager, ColormapType, ImageFilterProcessor, FilterType,
    COLORMAP_DISPLAY_NAMES, FILTER_DISPLAY_NAMES,
    create_colormap_processor, create_filter_processor, create_frame_tap_processor
)
from .loaders import DicomLoadWorker, DicomLoadResult, VideoLoadWorker, LoadProgressDialog
from .viewport import Viewport, ViewportManager, LayoutButtonWidget
from .study_browser import FileListWidget, ThumbnailCache


class ToolbarWidget(QToolBar):
    """Top toolbar with tool buttons."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        self.setMovable(False)
        self.setIconSize(QSize(20, 20))
        self.setStyleSheet("""
            QToolBar {
                background-color: #3c3c3c;
                border: none;
                padding: 3px;
                spacing: 3px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-bottom: 3px solid transparent;
                border-radius: 4px;
                padding: 4px;
                padding-left: 10px;
                padding-right: 7px;
                color: #cccccc;
            }
            QToolButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #505050;
                border-bottom: 3px solid #0078d4;
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-bottom: 3px solid #005a9e;
                color: #ffffff;
            }
            QToolButton:pressed {
                background-color: #005a9e;
            }
            /* Menu Button Specific Style (for Split Buttons) */
            QToolButton[is_dropdown="true"] {
                padding-right: 20px; /* Make space for the menu button */
                padding-left: 10px;
            }
            QToolButton::menu-button {
                border-left: 1px solid #505050;
                width: 20px;
                /* Optional: nice background for the arrow area */
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                margin-bottom: 3px; /* Prevent covering bottom border */
            }
            QToolButton::menu-button:hover {
                background-color: #505050;
            }
            QToolButton::menu-indicator {
                image: none; /* We use the default arrow or none if managed by style, strictly relying on default arrow here for now or add explicit one if resizing needed */
                width: 10px;
                height: 10px;
                subcontrol-position: center center;
                subcontrol-origin: padding;
            }
            /* Explicit fallback if needed, but usually qt draws it. 
               Let's try standard styling first. If image: none is set, it disappears!
               So removing 'image: none' from previous menuButton targeting if it conflicts,
               but let's keep the specific #menuButton one separate. */
            
            /* The specific #menuButton (Gear icon) is NOT a split button, it is InstantPopup */
            QToolButton#menuButton {
                border-left: 1px solid #505050;
                padding-left: 8px;
            }
            QToolButton#menuButton::menu-indicator {
                image: none;
            }

            /* Unified QMenu Style for All Dropdowns */
            QMenu {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:hover,
            QMenu::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #505050;
                margin: 4px 0;
            }
        """)
        
        # 1. Rotate
        self.rotate_action = QToolButton(self)
        self.rotate_action.setText("Rotate")
        self.rotate_action.setIcon(QIcon("assets/icons/rotate-ccw.svg"))
        self.rotate_action.setCheckable(True)
        self.rotate_action.setToolTip("Rotate image")
        self.rotate_action.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addWidget(self.rotate_action)
                
        # 2. Reset View
        self.reset_action = QToolButton(self)
        self.reset_action.setText("Reset")
        self.reset_action.setIcon(QIcon("assets/icons/crosshair.svg"))
        self.reset_action.setCheckable(False)
        self.reset_action.setToolTip("Reset view to default")
        self.reset_action.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addWidget(self.reset_action)
        
        # 3. Window/Level
        self.wl_action = QToolButton(self)
        self.wl_action.setText("W/L")
        self.wl_action.setIcon(QIcon("assets/icons/sun.svg"))
        self.wl_action.setCheckable(True)
        self.wl_action.setToolTip("Window/Level Adjustment")
        self.wl_action.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addWidget(self.wl_action)
        
        # 4. Annotate (Dropdown)
        self.annotate_button = QToolButton(self)
        self.annotate_button.setText("Annotate")
        self.annotate_button.setIcon(QIcon("assets/icons/pen-tool.svg"))
        self.annotate_button.setToolTip("Annotation tools")
        self.annotate_button.setObjectName("toolButton_Annotate")
        self.annotate_button.setProperty("is_dropdown", True)
        self.annotate_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.annotate_button.setCheckable(True)
        self.annotate_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        self.annotate_menu = QMenu(self)
        
        # Add annotation tools with icons
        self.line_action = self.annotate_menu.addAction("Line")
        self.line_action.setIcon(QIcon("assets/icons/minus.svg"))
        
        self.rect_action = self.annotate_menu.addAction("Rectangle")
        self.rect_action.setIcon(QIcon("assets/icons/square.svg"))
        
        self.polygon_action = self.annotate_menu.addAction("Polygon")
        self.polygon_action.setIcon(QIcon("assets/icons/hexagon.svg"))
        
        self.annotate_group = QActionGroup(self)
        self.annotate_group.addAction(self.line_action)
        self.annotate_group.addAction(self.rect_action)
        self.annotate_group.addAction(self.polygon_action)
        self.annotate_group.setExclusive(True)
        
        self.annotate_button.setMenu(self.annotate_menu)
        self.addWidget(self.annotate_button)
        
        # 5. Measure (Dropdown)
        self.measure_button = QToolButton(self)
        self.measure_button.setText("Measure")
        self.measure_button.setIcon(QIcon("assets/icons/ruler.svg"))
        self.measure_button.setToolTip("Measurement tools")
        self.measure_button.setObjectName("toolButton_Measure")
        self.measure_button.setProperty("is_dropdown", True)
        self.measure_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.measure_button.setCheckable(True)
        self.measure_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        self.measure_menu = QMenu(self)
        
        # Add measurement tools with icons
        self.distance_action = self.measure_menu.addAction("Distance")
        self.distance_action.setIcon(QIcon("assets/icons/ruler.svg"))
        
        self.angle_action = self.measure_menu.addAction("Angle")
        self.angle_action.setIcon(QIcon("assets/icons/triangle-right.svg"))
        
        self.area_action = self.measure_menu.addAction("Area")
        self.area_action.setIcon(QIcon("assets/icons/hexagon.svg"))
        
        self.perimeter_action = self.measure_menu.addAction("Perimeter")
        self.perimeter_action.setIcon(QIcon("assets/icons/activity.svg"))
        
        self.ellipse_action = self.measure_menu.addAction("Ellipse")
        self.ellipse_action.setIcon(QIcon("assets/icons/circle.svg"))
        
        self.measure_menu.addSeparator()
        self.clear_measures_action = self.measure_menu.addAction("Clear All")
        self.clear_measures_action.setIcon(QIcon("assets/icons/trash-2.svg"))
        
        self.measure_group = QActionGroup(self)
        self.measure_group.addAction(self.distance_action)
        self.measure_group.addAction(self.angle_action)
        self.measure_group.addAction(self.area_action)
        self.measure_group.addAction(self.perimeter_action)
        self.measure_group.addAction(self.ellipse_action)
        self.measure_group.setExclusive(True)
        
        self.measure_button.setMenu(self.measure_menu)
        self.addWidget(self.measure_button)
        
        # 6. LUT (Dropdown)
        self.colormap_button = QToolButton(self)
        self.colormap_button.setText("LUT")
        self.colormap_button.setIcon(QIcon("assets/icons/palette.svg"))
        self.colormap_button.setToolTip("Color mapping (LUT)")
        self.colormap_button.setObjectName("toolButton_LUT")
        self.colormap_button.setProperty("is_dropdown", True)
        self.colormap_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.colormap_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        self.colormap_menu = QMenu(self)
        self.colormap_group = QActionGroup(self)
        self.colormap_group.setExclusive(True)
        self.colormap_actions = {}
        
        colormap_icons = {'grayscale': '⬜', 'hot': '🔥', 'cool': '❄️', 'bone': '🦴', 'viridis': '🌈', 'plasma': '💜', 'inferno': '🌋'}
        for cmap in ColormapType:
            display_name = COLORMAP_DISPLAY_NAMES.get(cmap, cmap.value)
            icon = colormap_icons.get(cmap.value, '')
            action = self.colormap_menu.addAction(f"{icon} {display_name}")
            action.setCheckable(True)
            action.setData(cmap)
            self.colormap_group.addAction(action)
            self.colormap_actions[cmap] = action
            if cmap == ColormapType.GRAYSCALE:
                action.setChecked(True)
        
        self.colormap_button.setMenu(self.colormap_menu)
        self.addWidget(self.colormap_button)
        
        # 7. Filter (Dropdown)
        self.filter_button = QToolButton(self)
        self.filter_button.setText("Filter")
        self.filter_button.setIcon(QIcon("assets/icons/wand.svg"))
        self.filter_button.setToolTip("Image filters")
        self.filter_button.setObjectName("toolButton_Filter")
        self.filter_button.setProperty("is_dropdown", True)
        self.filter_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.filter_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        
        self.filter_menu = QMenu(self)
        self.filter_group = QActionGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_actions = {}
        
        # Filter icons mapping
        filter_svgs = {
            'none': 'assets/icons/circle.svg',
            'gaussian': 'assets/icons/aperture.svg',
            'median': 'assets/icons/layers.svg', # reusing layers
            'sharpen': 'assets/icons/zap.svg',
            'edge_enhance': 'assets/icons/activity.svg', # reusing activity
            'speckle_reduce': 'assets/icons/eye.svg',
        }
        
        for ftype in FilterType:
            display_name = FILTER_DISPLAY_NAMES.get(ftype, ftype.value)
            icon_path = filter_svgs.get(ftype.value, '')
            action = self.filter_menu.addAction(display_name)
            if icon_path:
                 action.setIcon(QIcon(icon_path))
            action.setCheckable(True)
            action.setData(ftype)
            self.filter_group.addAction(action)
            self.filter_actions[ftype] = action
            if ftype == FilterType.NONE:
                action.setChecked(True)
        
        self.filter_menu.addSeparator()
        
        self.filter_strength_action = self.filter_menu.addAction("▸ Strength: 50%")
        self.filter_strength_action.setEnabled(False)
        
        self.filter_button.setMenu(self.filter_menu)
        self.addWidget(self.filter_button)
        
        # 8. Screenshot
        self.screenshot_action = QToolButton(self)
        self.screenshot_action.setText("Screenshot")
        self.screenshot_action.setIcon(QIcon("assets/icons/camera.svg"))
        self.screenshot_action.setToolTip("Save screenshot")
        self.screenshot_action.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addWidget(self.screenshot_action)
        
        # 9. Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer.setStyleSheet("background-color: transparent;")
        self.addWidget(spacer)
        
        # 10. Menu (Gear Icon) - Consolidated Settings
        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setText("Menu")
        self.menu_button.setIcon(QIcon("assets/icons/settings.svg"))
        self.menu_button.setToolTip("Settings & Help")
        self.menu_button.setPopupMode(QToolButton.InstantPopup) # Always open menu
        self.menu_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        self.main_menu = QMenu(self)
        
        # Menu Actions
        
        # Shortcuts
        self.menu_shortcuts = self.main_menu.addAction("Keyboard Shortcuts")
        self.menu_shortcuts.setIcon(QIcon("assets/icons/keyboard.svg"))
        
        # Help
        self.menu_help = self.main_menu.addAction("Help")
        self.menu_help.setIcon(QIcon("assets/icons/help-circle.svg"))
        
        # About
        self.menu_about = self.main_menu.addAction("About")
        self.menu_about.setIcon(QIcon("assets/icons/info.svg"))
        
        self.menu_button.setMenu(self.main_menu)
        self.addWidget(self.menu_button)

        # 11. Layers Toggle (Moved from Menu)
        self.layers_button = QToolButton(self)
        self.layers_button.setText("Layers")
        self.layers_button.setIcon(QIcon("assets/icons/layers.svg"))
        self.layers_button.setToolTip("Toggle Layers Panel")
        self.layers_button.setCheckable(True)
        self.layers_button.setChecked(True)
        self.layers_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addWidget(self.layers_button)


class FilterStrengthDialog(QDialog):
    """Dialog for adjusting filter strength."""
    
    def __init__(self, initial_strength=0.5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter Strength")
        self.setFixedSize(300, 150)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._strength = initial_strength
        self.setup_ui()
    
    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 8px;
            }
            QLabel {
                color: #cccccc;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #3e3e42;
                height: 8px;
                background: #1e1e1e;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #005a9e;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #1e90ff;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1e90ff;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Adjust Filter Strength")
        title.setFont(QFont("Helvetica Neue", 14, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Slider with labels
        slider_row = QHBoxLayout()
        
        weak_label = QLabel("Weak")
        weak_label.setStyleSheet("color: #888888; font-size: 11px;")
        slider_row.addWidget(weak_label)
        
        self.strength_slider = QSlider(Qt.Horizontal)
        self.strength_slider.setMinimum(0)
        self.strength_slider.setMaximum(100)
        self.strength_slider.setValue(int(self._strength * 100))
        self.strength_slider.valueChanged.connect(self.on_slider_changed)
        slider_row.addWidget(self.strength_slider, 1)
        
        strong_label = QLabel("Strong")
        strong_label.setStyleSheet("color: #888888; font-size: 11px;")
        slider_row.addWidget(strong_label)
        
        layout.addLayout(slider_row)
        
        # Value label
        self.value_label = QLabel(f"{int(self._strength * 100)}%")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setFont(QFont("SF Mono", 16, QFont.Bold))
        self.value_label.setStyleSheet("color: #0078d4;")
        layout.addWidget(self.value_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def on_slider_changed(self, value):
        """Update label when slider changes."""
        self._strength = value / 100.0
        self.value_label.setText(f"{value}%")
    
    def get_strength(self) -> float:
        """Get the selected strength value (0.0 to 1.0)."""
        return self._strength


class HelpDialog(QDialog):
    """Help and info dialog with tabs."""
    
    def __init__(self, parent=None, initial_tab=0):
        super().__init__(parent)
        self.setWindowTitle("SonoView Pro Help")
        self.setFixedSize(600, 500)
        # Keep on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setup_ui()
        self.tabs.setCurrentIndex(initial_tab)
    
    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d30;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background: #252526;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #2d2d30;
                color: #cccccc;
                padding: 8px 20px;
                border: 1px solid #3e3e42;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3e3e42;
                color: #ffffff;
                border-bottom: 2px solid #0078d4;
            }
            QTabBar::tab:hover {
                background: #3e3e42;
            }
            QLabel { color: #cccccc; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # 1. Welcome Tab
        self.tabs.addTab(self.create_welcome_tab(), "Welcome")
        
        # 2. Commands Tab (Shortcuts)
        self.tabs.addTab(self.create_commands_tab(), "Commands")
        
        # 3. Privacy Tab
        self.tabs.addTab(self.create_privacy_tab(), "Privacy Policy")
        
        # 4. About Tab
        self.tabs.addTab(self.create_about_tab(), "About")
        
        # Close button area
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #0078d4;
            }
        """)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        


    def create_welcome_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        
        title = QLabel("Welcome to SonoView Pro")
        title.setFont(QFont("Helvetica Neue", 20, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Professional Ultrasound Imaging Software\nStreamlined for efficiency and precision.")
        subtitle.setFont(QFont("Helvetica Neue", 12))
        subtitle.setStyleSheet("color: #aaaaaa;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Icon placeholder
        icon = QLabel("🔷")
        icon.setFont(QFont("lucide", 48)) 
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        layout.addStretch()
        return tab

    def create_commands_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)
        
        # Translated shortcuts for consistency with previous version
        shortcuts = {
            "播放控制": [
                ("Space", "播放 / 暫停"),
                ("Home", "跳至第一幀"),
                ("End", "跳至最後一幀"),
                ("← / →", "上一幀 / 下一幀"),
                ("Shift+← / →", "快退 / 快進 5 幀"),
                ("L", "切換循環播放"),
            ],
            "檢視控制": [
                ("滑鼠滾輪", "縮放"),
                ("右鍵拖曳", "平移"),
                ("R", "重置檢視"),
            ],
            "佈局切換": [
                ("Ctrl+1", "單視窗 (1×1)"),
                ("Ctrl+2", "左右雙視窗 (1×2)"),
                ("Ctrl+3", "上下雙視窗 (2×1)"),
                ("Ctrl+4", "四視窗 (2×2)"),
            ],
            "工具": [
                ("W", "Window/Level 調整"),
                ("A", "標註工具"),
                ("1 / 2 / 3", "線段 / 矩形 / 多邊形"),
                ("Esc", "取消當前操作"),
            ],
            "影像處理": [
                ("C", "色彩映射選單"),
                ("F", "濾波器選單"),
            ],
            "檔案": [
                ("Cmd+O", "開啟檔案"),
                ("Cmd+S", "儲存截圖"),
            ],
            "面板": [
                ("P", "切換圖層面板"),
                ("?", "顯示此説明面板"),
            ],
        }
        
        for category, items in shortcuts.items():
            header = QLabel(f"【{category}】")
            header.setFont(QFont("Helvetica Neue", 11, QFont.Bold))
            header.setStyleSheet("color: #ffffff; margin-top: 5px;")
            content_layout.addWidget(header)
            
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #3e3e42;")
            line.setFixedHeight(1)
            content_layout.addWidget(line)
            
            for key, desc in items:
                item_widget = QWidget()
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(10, 2, 10, 2)
                
                key_label = QLabel(key)
                key_label.setFixedWidth(120)
                key_label.setStyleSheet("""
                    color: #0078d4;
                    font-family: 'SF Mono', Consolas, Monaco, 'Courier New', monospace;
                    font-weight: bold;
                    font-size: 12px;
                """)
                item_layout.addWidget(key_label)
                
                desc_label = QLabel(desc)
                desc_label.setStyleSheet("color: #cccccc;")
                item_layout.addWidget(desc_label)
                item_layout.addStretch()
                content_layout.addWidget(item_widget)
                
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return tab

    def create_privacy_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 10px;
                color: #cccccc;
                font-family: sans-serif;
                font-size: 13px;
            }
        """)
        text.setHtml("""
            <h3 style='color: white;'>隱私權聲明</h3>
            <p>您的隱私對我們非常重要。</p>
            <p><strong>資料收集：</strong><br>
            SonoView Pro 不會收集、儲存或傳輸任何個人數據或醫療影像至外部伺服器。所有處理均在您的設備上本地執行。</p>
            <p><strong>檔案存取：</strong><br>
            應用程式僅存取您明確開啟或儲存的檔案。</p>
            <p><strong>條款更新：</strong><br>
            此政策可能會在未來的版本中更新。</p>
            <br>
            <p><em>最後更新：2026年1月</em></p>
        """)
        layout.addWidget(text)
        return tab

    def create_about_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)
        
        name = QLabel("SonoView Pro")
        name.setFont(QFont("Helvetica Neue", 20, QFont.Bold))
        name.setStyleSheet("color: #0078d4;")
        layout.addWidget(name)
        
        ver = QLabel("Version 1.0.0")
        ver.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(ver)
        
        copy = QLabel("© 2026 SonoView Inc.\nAll rights reserved.")
        copy.setAlignment(Qt.AlignCenter)
        copy.setStyleSheet("color: #888888;")
        layout.addWidget(copy)
        
        credits_lbl = QLabel("Powered by:\nFAST (Framework for Heterogeneous Medical Image Computing)\nPySide2 (Qt for Python)")
        credits_lbl.setAlignment(Qt.AlignCenter)
        credits_lbl.setStyleSheet("color: #666666; margin-top: 20px;")
        layout.addWidget(credits_lbl)
        
        layout.addStretch()
        return tab

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class PlaybackControlWidget(QWidget):
    """Bottom playback control bar with enhanced navigation."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_rate = 30  # Default frame rate for time calculation
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)
        
        # Common button style with enhanced hover effect
        nav_btn_style = """
            QPushButton {
                background-color: #3c3c3c;
                color: #cccccc;
                border: 1px solid #505050;
                border-bottom: 3px solid #505050;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                min-width: 32px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: #ffffff;
                border-color: #606060;
                border-bottom: 3px solid #0078d4;
            }
            QPushButton:pressed {
                background-color: #0078d4;
                border-bottom: 3px solid #005a9e;
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border-color: #0078d4;
                border-bottom: 3px solid #005a9e;
                color: #ffffff;
            }
        """
        
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #505050;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -4px 0;
                background: #0078d4;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #1a8cff;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)
        
        # === Navigation Buttons ===
        # First frame button
        self.first_btn = QPushButton("")  # skip-back
        self.first_btn.setFixedWidth(36)
        self.first_btn.setToolTip("First frame (Home)")
        self.first_btn.setStyleSheet(nav_btn_style)
        self.first_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.first_btn)
        
        # Rewind button (-5 frames)
        self.rewind_btn = QPushButton("")  # rewind
        self.rewind_btn.setFixedWidth(36)
        self.rewind_btn.setToolTip("Rewind 5 frames")
        self.rewind_btn.setStyleSheet(nav_btn_style)
        self.rewind_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.rewind_btn)
        
        # Play/Pause button
        self.play_btn = QPushButton("")  # play
        self.play_btn.setFixedWidth(40)
        self.play_btn.setToolTip("Play/Pause (Space)")
        self.play_btn.setStyleSheet(nav_btn_style)
        self.play_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.play_btn)
        
        # Forward button (+5 frames)
        self.forward_btn = QPushButton("")  # fast-forward
        self.forward_btn.setFixedWidth(36)
        self.forward_btn.setToolTip("Forward 5 frames")
        self.forward_btn.setStyleSheet(nav_btn_style)
        self.forward_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.forward_btn)
        
        # Last frame button
        self.last_btn = QPushButton("")  # skip-forward
        self.last_btn.setFixedWidth(36)
        self.last_btn.setToolTip("Last frame (End)")
        self.last_btn.setStyleSheet(nav_btn_style)
        self.last_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.last_btn)
        
        # Loop toggle button
        self.loop_btn = QPushButton("")  # repeat
        self.loop_btn.setFixedWidth(36)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)  # Default: loop enabled
        self.loop_btn.setToolTip("Loop playback (L)")
        self.loop_btn.setStyleSheet(nav_btn_style)
        self.loop_btn.setFont(QFont("lucide", 14))
        layout.addWidget(self.loop_btn)
        
        # Spacing
        layout.addSpacing(8)
        
        # === Frame Slider ===
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(100)
        self.frame_slider.setValue(0)
        layout.addWidget(self.frame_slider, 1)
        
        # Spacing
        layout.addSpacing(8)
        
        # === Info Labels ===
        # Time display
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(90)
        self.time_label.setToolTip("Current time / Total time")
        self.time_label.setStyleSheet("color: #aaaaaa; font-family: 'SF Mono', Consolas, Monaco, 'Courier New', monospace;")
        layout.addWidget(self.time_label)
        
        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #505050;")
        layout.addWidget(sep1)
        
        # Frame info
        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setFixedWidth(110)
        self.frame_label.setToolTip("Current frame / Total frames")
        self.frame_label.setStyleSheet("font-family: 'SF Mono', Consolas, Monaco, 'Courier New', monospace;")
        layout.addWidget(self.frame_label)
        
        # Separator
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #505050;")
        layout.addWidget(sep2)
        
        # Window/Level info
        self.wl_label = QLabel("W: 255  L: 127")
        self.wl_label.setFixedWidth(100)
        self.wl_label.setToolTip("Window / Level")
        self.wl_label.setStyleSheet("font-family: 'SF Mono', Consolas, Monaco, 'Courier New', monospace;")
        layout.addWidget(self.wl_label)
    
    def update_time_display(self, current_frame, total_frames):
        """Update time label based on frame number and frame rate."""
        if total_frames <= 0:
            self.time_label.setText("00:00 / 00:00")
            return
        
        current_sec = current_frame / self.frame_rate
        total_sec = total_frames / self.frame_rate
        
        current_str = f"{int(current_sec // 60):02d}:{int(current_sec % 60):02d}"
        total_str = f"{int(total_sec // 60):02d}:{int(total_sec % 60):02d}"
        
        self.time_label.setText(f"{current_str} / {total_str}")


class UltrasoundViewerWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.fast_view = None
        self.fast_widget = None
        self.computation_thread = None
        self.current_streamer = None
        self.renderer = None
        self.is_playing = True
        self.current_file = None
        self.total_frames = 0
        self.current_frame = 0
        self.zoom_level = 1.0
        self.rotation_angle = 0
        self.current_tool = 'none'
        self.current_annotation_tool = None
        self.current_measure_tool = None  # Current measurement tool type
        self.annotations = []  # List of all annotations
        self.measurements = []  # List of all measurements
        
        # FAST Annotation Manager (will be initialized after fast_view is created)
        self.fast_annotation_manager = None
        
        # Async loading state
        self._load_worker = None
        self._load_progress_dialog = None
        
        # Window/Level state
        self.intensity_level = 127.0
        self.intensity_window = 255.0
        self._wl_dragging = False
        self._wl_start_pos = None
        
        # Image processing state
        self.colormap_manager = ColormapManager()
        self.filter_processor = ImageFilterProcessor()
        self.current_colormap = ColormapType.GRAYSCALE
        self.current_filter = FilterType.NONE
        self.filter_strength = 0.5

        # LUT overlay state (CPU colormap on top of grayscale FAST view)
        self.lut_overlay_label = None
        self.lut_overlay_effect = None
        self.lut_overlay_enabled = False
        self.lut_overlay_opacity = 0.85
        self.lut_overlay_processor = None
        self._lut_last_frame_id = -1
        self._lut_last_view_matrix = None
        self.debug_lut_transform = False # For debugging FAST / LUT alignment (True 會打印)
        
        # FAST pipeline processors (will be initialized in setup_pipeline)
        self.pipeline_colormap_processor = None
        self.pipeline_filter_processor = None
        self.pipeline_frame_tap_processor = None
        
        self.setup_ui()
        self.apply_dark_theme()
        self.connect_signals()
        self.setup_shortcuts()
        
        # Timer for updating frame info
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_frame_info)
        self.update_timer.start(100)  # Update every 100ms

        # Timer for LUT overlay updates
        self.lut_overlay_timer = QTimer(self)
        self.lut_overlay_timer.timeout.connect(self._update_lut_overlay)
        self.lut_overlay_timer.start(33)
        
        # Timer for annotation overlay updates (syncs with FAST view matrix)
        self.annotation_update_timer = QTimer(self)
        self.annotation_update_timer.timeout.connect(self._update_annotation_overlay)
        self.annotation_update_timer.start(50)  # Update every 50ms
        
    def setup_ui(self):
        self.setWindowTitle("🔷 Ultrasound Imaging Software")
        self.setMinimumSize(1400, 900)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout with splitter
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel (file list)
        self.file_panel = FileListWidget()
        self.file_panel.setMinimumWidth(150)
        self.file_panel.setMaximumWidth(250)
        splitter.addWidget(self.file_panel)
        
        # Right panel (toolbar + viewer + playback)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = ToolbarWidget()
        right_layout.addWidget(self.toolbar)
        
        # ViewportManager (replaces single FAST view)
        self.viewport_manager = ViewportManager()
        self.viewport_manager.active_viewport_changed.connect(self._on_active_viewport_changed)
        self.viewport_manager.layout_changed.connect(self._on_layout_changed)
        right_layout.addWidget(self.viewport_manager, 1)
        
        # Playback controls
        self.playback = PlaybackControlWidget()
        right_layout.addWidget(self.playback)
        
        splitter.addWidget(right_panel)
        
        # Layer panel (right side)
        self.layer_panel = LayerPanelWidget()
        self.layer_panel.setStyleSheet("background-color: #252526;")
        splitter.addWidget(self.layer_panel)
        
        # Now sync viewport references (after layer_panel is created)
        self._sync_viewport_references()
        
        # Save splitter reference for toggle
        self.main_splitter = splitter
        # Default size: 1400x900
        # Splitter: [Left(Files)=200, Center(Viewer)=950, Right(Layers)=250]
        splitter.setSizes([200, 950, 250])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
        """)
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)
    
    def _sync_viewport_references(self):
        """Sync references from active viewport for backward compatibility."""
        vp = self.viewport_manager.get_active_viewport()
        if vp:
            self.fast_view = vp.fast_view
            self.fast_widget = vp.fast_widget
            self.fast_annotation_manager = vp.fast_annotation_manager
            self.annotation_overlay = vp.annotation_overlay
            self.lut_overlay_label = vp.lut_overlay_label
            self.lut_overlay_effect = vp.lut_overlay_effect
            self.lut_overlay_processor = vp.lut_overlay_processor
            self.renderer = vp.renderer  # Required for W/L adjustment
            
            # Setup annotation overlay connections
            if self.annotation_overlay:
                self.annotation_overlay.installEventFilter(self)
                if self.fast_annotation_manager:
                    self.annotation_overlay.set_coord_converter(
                        self.fast_annotation_manager.coord_converter
                    )
                
                # Reconnect annotation signals (disconnect first to avoid duplicates)
                try:
                    self.annotation_overlay.annotation_added.disconnect()
                    self.annotation_overlay.measure_added.disconnect()
                    self.annotation_overlay.wl_changed.disconnect()
                    self.annotation_overlay.preview_updated.disconnect()
                    self.annotation_overlay.preview_cleared.disconnect()
                except:
                    pass
                
                self.annotation_overlay.annotation_added.connect(self.layer_panel.add_annotation)
                self.annotation_overlay.annotation_added.connect(self.on_annotation_added)
                self.annotation_overlay.measure_added.connect(self.on_measure_added)
                self.annotation_overlay.wl_changed.connect(self.on_wl_changed)
                self.annotation_overlay.preview_updated.connect(self.on_preview_updated)
                self.annotation_overlay.preview_cleared.connect(self.on_preview_cleared)
    
    def _on_active_viewport_changed(self, viewport: Viewport):
        """Handle active viewport change."""
        self._sync_viewport_references()
        
        # Update current file reference
        self.current_file = viewport.current_file
        self.current_streamer = viewport.current_streamer
        
        # Update status bar
        if viewport.current_file:
            filename = os.path.basename(viewport.current_file)
            self.status_bar.showMessage(f"Active: {filename}")
        else:
            self.status_bar.showMessage("Ready")
    
    def _on_layout_changed(self, layout_name: str):
        """Handle layout change."""
        self.status_bar.showMessage(f"Layout: {layout_name}")
    
    def create_fast_view(self):
        """Create and embed FAST view widget."""
        try:
            self.fast_view = fast.View()
            self.fast_view.set2DMode()
            self.fast_view.setBackgroundColor(fast.Color(0.1, 0.1, 0.1))
            self.fast_view.setAutoUpdateCamera(True)  # 當內容變化時自動更新相機
            
            # Wrap as Qt widget
            self.fast_widget = wrapInstance(int(self.fast_view.asQGLWidget()), QGLWidget)
            self.fast_widget.setMinimumSize(400, 300)
            
            # Enable proper mouse/keyboard interaction (critical for FAST zoom/pan)
            self.fast_widget.setFocusPolicy(Qt.StrongFocus)
            self.fast_widget.setMouseTracking(True)
            
            # Initialize FAST Annotation Manager
            self.fast_annotation_manager = FASTAnnotationManager(self.fast_view)
            
        except Exception as e:
            print(f"Error creating FAST view: {e}")
            self.fast_view = None
            self.fast_widget = None
            self.fast_annotation_manager = None
    
    def apply_dark_theme(self):
        """Apply dark theme to the application."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #252526;
                color: #ffffff;
            }
            QSplitter::handle {
                background-color: #3e3e42;
                width: 2px;
            }
        """)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        # File panel
        self.file_panel.open_file_btn.clicked.connect(self.open_file_dialog)
        self.file_panel.open_folder_btn.clicked.connect(self.open_folder_dialog)
        self.file_panel.file_list.itemClicked.connect(self.on_file_selected)
        
        # Toolbar - tools (Zoom and Pan are always available via FAST's built-in controls)
        self.toolbar.reset_action.clicked.connect(self.reset_view)
        self.toolbar.rotate_action.clicked.connect(self.rotate_image)
        self.toolbar.wl_action.clicked.connect(lambda checked: self.set_tool('wl' if checked else 'none'))
        
        # Annotation tools
        self.toolbar.annotate_button.clicked.connect(lambda checked: self.set_tool('annotate' if checked else 'none'))
        self.toolbar.line_action.triggered.connect(lambda: self.set_annotation_tool('line'))
        self.toolbar.rect_action.triggered.connect(lambda: self.set_annotation_tool('rectangle'))
        self.toolbar.polygon_action.triggered.connect(lambda: self.set_annotation_tool('polygon'))
        
        # Measure tools
        self.toolbar.measure_button.clicked.connect(lambda checked: self.set_tool('measure' if checked else 'none'))
        self.toolbar.distance_action.triggered.connect(lambda: self.set_measure_tool('distance'))
        self.toolbar.angle_action.triggered.connect(lambda: self.set_measure_tool('angle'))
        self.toolbar.area_action.triggered.connect(lambda: self.set_measure_tool('area'))
        self.toolbar.perimeter_action.triggered.connect(lambda: self.set_measure_tool('perimeter'))
        self.toolbar.ellipse_action.triggered.connect(lambda: self.set_measure_tool('ellipse'))
        self.toolbar.clear_measures_action.triggered.connect(self.clear_all_measures)
        
        # Toolbar - other actions
        self.toolbar.screenshot_action.clicked.connect(self.take_screenshot)
        
        # Playback bar
        self.playback.play_btn.clicked.connect(self.toggle_playback)
        self.playback.first_btn.clicked.connect(self.first_frame)
        self.playback.rewind_btn.clicked.connect(self.rewind_frames)
        self.playback.forward_btn.clicked.connect(self.forward_frames)
        self.playback.last_btn.clicked.connect(self.last_frame)
        self.playback.loop_btn.toggled.connect(self.toggle_loop)
        self.playback.frame_slider.sliderPressed.connect(self.on_slider_pressed)
        self.playback.frame_slider.sliderReleased.connect(self.on_slider_released)
        self.playback.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        
        # Annotation overlay <-> Layer panel
        if self.annotation_overlay:
            self.annotation_overlay.annotation_added.connect(self.layer_panel.add_annotation)
            self.annotation_overlay.annotation_added.connect(self.on_annotation_added)
            self.annotation_overlay.measure_added.connect(self.on_measure_added)
            self.annotation_overlay.wl_changed.connect(self.on_wl_changed)
            # Connect preview signals for FAST annotation sync
            self.annotation_overlay.preview_updated.connect(self.on_preview_updated)
            self.annotation_overlay.preview_cleared.connect(self.on_preview_cleared)
        self.layer_panel.annotation_deleted.connect(self.on_annotation_deleted)
        self.layer_panel.visibility_changed.connect(self.on_annotation_visibility_changed)
        self.layer_panel.class_type_changed.connect(self.on_annotation_class_changed)
        
        # Layers panel toggle
        
        # Menu Actions
        self.toolbar.layers_button.toggled.connect(self.toggle_layers_panel)
        self.toolbar.menu_shortcuts.triggered.connect(lambda: self.show_help_dialog(1)) # Tab 1: Commands
        self.toolbar.menu_help.triggered.connect(lambda: self.show_help_dialog(0))      # Tab 0: Welcome
        self.toolbar.menu_about.triggered.connect(lambda: self.show_help_dialog(3))     # Tab 3: About (skip Privacy@2)
        
        # Image processing - Colormap
        self.toolbar.colormap_group.triggered.connect(self.on_colormap_changed)
        self.toolbar.colormap_button.clicked.connect(self.show_colormap_menu)
        
        # Image processing - Filters
        self.toolbar.filter_group.triggered.connect(self.on_filter_changed)
        self.toolbar.filter_button.clicked.connect(self.show_filter_strength_dialog)
    
    @Slot()
    def open_file_dialog(self):
        """Open file dialog to select DICOM/video file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Ultrasound File",
            "",
            "DICOM Files (*.dcm);;Video Files (*.avi *.mp4 *.mov);;All Files (*.*)"
        )
        if filepath:
            self.load_file(filepath)
    
    @Slot()
    def open_folder_dialog(self):
        """Open folder dialog to select DICOM directory."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Open DICOM Folder",
            "",
            QFileDialog.ShowDirsOnly
        )
        if folder_path:
            self.load_folder(folder_path)
    
    def load_folder(self, folder_path):
        """Load all DICOM files from a folder."""
        import glob
        
        # Find all DICOM files recursively
        dcm_files = glob.glob(os.path.join(folder_path, "**", "*.dcm"), recursive=True)
        dcm_files.sort()
        
        if not dcm_files:
            QMessageBox.information(self, "No Files Found", "No DICOM files found in the selected folder.")
            return
        
        self.status_bar.showMessage(f"Found {len(dcm_files)} DICOM files")
        
        # Add all files to list
        for filepath in dcm_files:
            self.file_panel.add_file(filepath)
        
        # Load the first file
        if dcm_files:
            self.load_file(dcm_files[0])
    
    def load_file(self, filepath):
        """Load an ultrasound file using async loading."""
        # Check if already loading
        if self._load_worker and self._load_worker.isRunning():
            QMessageBox.warning(self, "載入中", "請等待目前檔案載入完成")
            return
        
        self.status_bar.showMessage(f"Loading: {filepath}")
        
        # Determine file type and create appropriate worker
        is_dicom = filepath.lower().endswith('.dcm')
        is_video = VideoLoadWorker.is_video_file(filepath)
        
        if is_dicom:
            self._start_dicom_loading(filepath)
        elif is_video:
            self._start_video_loading(filepath)
        else:
            # Fall back to sync loading for other file types
            self._load_file_sync(filepath)
    
    def _start_dicom_loading(self, filepath):
        """Start async DICOM loading with progress dialog."""
        # Create progress dialog
        self._load_progress_dialog = LoadProgressDialog(self, "載入 DICOM")
        self._load_progress_dialog.set_filename(os.path.basename(filepath))
        
        # Create worker thread
        self._load_worker = DicomLoadWorker(filepath, loop=True, parent=self)
        
        # Connect signals
        self._load_worker.progress.connect(self._load_progress_dialog.set_progress)
        self._load_worker.stage_changed.connect(self._load_progress_dialog.set_stage)
        self._load_worker.finished_loading.connect(self._on_dicom_load_complete)
        self._load_worker.error_occurred.connect(self._on_load_error)
        self._load_progress_dialog.cancelled.connect(self._on_load_cancelled)
        
        # Disable toolbar during loading
        self.toolbar.setEnabled(False)
        
        # Start loading
        self._load_worker.start()
        self._load_progress_dialog.show()
    
    def _start_video_loading(self, filepath):
        """Start async video loading."""
        # Video loading is fast, use simpler approach
        self.status_bar.showMessage(f"載入影片: {os.path.basename(filepath)}")
        
        self._load_worker = VideoLoadWorker(filepath, loop=True, parent=self)
        self._load_worker.finished_loading.connect(self._on_video_load_complete)
        self._load_worker.error_occurred.connect(self._on_load_error)
        
        self.toolbar.setEnabled(False)
        self._load_worker.start()
    
    def _on_dicom_load_complete(self, result: DicomLoadResult):
        """Handle DICOM loading completion."""
        # Close progress dialog
        if self._load_progress_dialog:
            self._load_progress_dialog.close_on_complete()
            self._load_progress_dialog = None
        
        # Re-enable toolbar
        self.toolbar.setEnabled(True)
        
        if not result.success:
            QMessageBox.critical(self, "載入失敗", result.error_message)
            self.status_bar.showMessage("載入失敗")
            return
        
        # Apply the loaded data
        self._apply_dicom_result(result)
    
    def _on_video_load_complete(self, result):
        """Handle video loading completion."""
        self.toolbar.setEnabled(True)
        
        if not result.success:
            QMessageBox.critical(self, "載入失敗", result.error_message)
            self.status_bar.showMessage("載入失敗")
            return
        
        # Load into active viewport
        viewport = self.viewport_manager.get_active_viewport()
        if viewport:
            shared_thread = self.viewport_manager._shared_computation_thread
            viewport.load_streamer(result.streamer, result.filepath, shared_thread=shared_thread)
            self.viewport_manager.ensure_computation_thread_running()
            self._sync_viewport_references()
            self.current_streamer = viewport.current_streamer
            self.current_file = viewport.current_file
            
            self.is_playing = True
            self.playback.play_btn.setText("\ue131")  # pause icon
        
        self.file_panel.add_file(result.filepath)
        self.file_panel.select_file(result.filepath)
        
        self.status_bar.showMessage(f"已載入: {os.path.basename(result.filepath)}")
    
    def _on_load_error(self, error_message: str):
        """Handle loading error."""
        if self._load_progress_dialog:
            self._load_progress_dialog.close_on_cancel()
            self._load_progress_dialog = None
        
        self.toolbar.setEnabled(True)
        QMessageBox.critical(self, "載入錯誤", error_message)
        self.status_bar.showMessage("載入錯誤")
    
    def _on_load_cancelled(self):
        """Handle loading cancellation."""
        if self._load_worker:
            self._load_worker.cancel()
            self._load_worker.wait(2000)  # Wait up to 2 seconds
        
        if self._load_progress_dialog:
            self._load_progress_dialog.close_on_cancel()
            self._load_progress_dialog = None
        
        self.toolbar.setEnabled(True)
        self.status_bar.showMessage("載入已取消")
    
    def _apply_dicom_result(self, result: DicomLoadResult):
        """Apply loaded DICOM data to the active viewport."""
        from .annotations import Annotation, Measure
        
        # Set pixel spacing for annotations
        Annotation.set_pixel_spacing(result.pixel_spacing)
        Measure.set_pixel_spacing(result.pixel_spacing)
        
        # Update patient info panel
        self.file_panel.update_patient_info(result.metadata)
        
        # Load into active viewport
        viewport = self.viewport_manager.get_active_viewport()
        if viewport:
            shared_thread = self.viewport_manager._shared_computation_thread
            viewport.load_streamer(
                result.streamer,
                result.filepath,
                result.metadata,
                result.pixel_spacing,
                result.image_width,
                result.image_height,
                shared_thread=shared_thread
            )
            self.viewport_manager.ensure_computation_thread_running()
            
            # Sync references for compatibility
            self._sync_viewport_references()
            self.current_streamer = viewport.current_streamer
            self.current_file = viewport.current_file
            
            # Update playback button state
            self.is_playing = True
            self.playback.play_btn.setText("\ue131")  # pause icon
            
            # Event-driven centering
            self._center_attempts = 0
            self._center_timer = QTimer(self)
            self._center_timer.timeout.connect(self._check_and_center)
            self._center_timer.start(50)
            
            # Set LUT overlay
            self._set_lut_overlay_enabled(self.current_colormap != ColormapType.GRAYSCALE)
        
        # Add to file list
        self.file_panel.add_file(result.filepath)
        self.file_panel.select_file(result.filepath)
        
        self.status_bar.showMessage(f"已載入: {os.path.basename(result.filepath)}")
        
        if result.pixel_spacing:
            print(f"Pixel spacing: {result.pixel_spacing:.4f} mm/pixel")
        if result.image_width and result.image_height:
            print(f"Image size: {result.image_width} x {result.image_height}")
    
    def _load_file_sync(self, filepath):
        """Fallback synchronous loading for non-DICOM/video files."""
        try:
            from .pipelines import create_playback_pipeline
            
            streamer = create_playback_pipeline(filepath)
            
            if streamer is None:
                QMessageBox.critical(self, "Error", "Failed to load file")
                return
            
            # Load into active viewport
            viewport = self.viewport_manager.get_active_viewport()
            if viewport:
                shared_thread = self.viewport_manager._shared_computation_thread
                viewport.load_streamer(streamer, filepath, shared_thread=shared_thread)
                self.viewport_manager.ensure_computation_thread_running()
                self._sync_viewport_references()
                self.current_streamer = viewport.current_streamer
                self.current_file = viewport.current_file
                
                self.is_playing = True
                self.playback.play_btn.setText("\ue131")  # pause icon
            
            self.file_panel.add_file(filepath)
            self.file_panel.select_file(filepath)
            
            self.status_bar.showMessage(f"Loaded: {os.path.basename(filepath)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")
            self.status_bar.showMessage("Error loading file")
    
    def setup_pipeline(self):
        """Setup FAST rendering pipeline."""
        if not self.current_streamer or not self.fast_view:
            return
        
        try:
            # Create computation thread
            self.computation_thread = fast.ComputationThread.create()
            self.computation_thread.addView(self.fast_view)

            self.pipeline_colormap_processor = None
            self.pipeline_filter_processor = None
            self.pipeline_frame_tap_processor = None
            
            # Build processing pipeline:
            # Streamer -> FilterProcessor -> FrameTapProcessor -> Renderer
            
            # Create filter processor
            FilterProcessorClass = create_filter_processor()
            self.pipeline_filter_processor = FilterProcessorClass.create()
            self.pipeline_filter_processor.connect(self.current_streamer)
            self.pipeline_filter_processor.setFilter(self.current_filter, self.filter_strength)

            # Create frame tap processor (grayscale passthrough + capture)
            FrameTapProcessorClass = create_frame_tap_processor()
            self.pipeline_frame_tap_processor = FrameTapProcessorClass.create()
            self.pipeline_frame_tap_processor.connect(self.pipeline_filter_processor)
            self.lut_overlay_processor = self.pipeline_frame_tap_processor
            self._lut_last_frame_id = -1
            
            # Create renderer and connect to filter processor output
            self.renderer = fast.ImageRenderer.create()
            self.renderer.connect(self.pipeline_frame_tap_processor)
            self.renderer.setIntensityLevel(self.intensity_level)
            self.renderer.setIntensityWindow(self.intensity_window)
            
            # Clear and add renderer
            self.fast_view.removeAllRenderers()
            self.fast_view.addRenderer(self.renderer)
            # Note: Do NOT call reinitialize() here - it resets internal size to 400x300
            
            # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
            
            # Start computation thread
            self.computation_thread.start()
            self.is_playing = True
            self.playback.play_btn.setText("")  # pause icon
            
            # Event-driven centering: poll until first frame is rendered
            self._center_attempts = 0
            self._center_timer = QTimer(self)
            self._center_timer.timeout.connect(self._check_and_center)
            self._center_timer.start(50)  # Check every 50ms
            
            self._set_lut_overlay_enabled(self.current_colormap != ColormapType.GRAYSCALE)
            print(f"Pipeline setup: Colormap={self.current_colormap.name}, Filter={self.current_filter.name}")
            
        except Exception as e:
            print(f"Error setting up pipeline: {e}")
            import traceback
            traceback.print_exc()

    def _update_annotation_overlay(self):
        """
        Update annotation overlay with current FAST view matrix.
        
        This ensures annotations are correctly positioned when the FAST view
        is zoomed or panned, and triggers repaint of the Qt overlay.
        """
        if not self.fast_view or not self.annotation_overlay:
            return
        
        # Get coordinate converter from annotation overlay
        coord_converter = self.annotation_overlay._coord_converter
        if not coord_converter:
            return
        
        try:
            # Get current view matrix and ortho params from FAST view
            view_matrix = None
            ortho_params = None
            
            try:
                view_matrix = self.fast_view.getViewMatrix()
            except Exception:
                pass
            
            try:
                ortho_params = self.fast_view.getOrthoProjectionParameters()
            except Exception:
                pass
            
            # Update coordinate converter with view matrix
            # Returns True if view changed
            if coord_converter.set_view_matrix(view_matrix, ortho_params):
                # View changed - trigger repaint
                self.annotation_overlay.update()
        except Exception as e:
            # Silently ignore errors to avoid spam
            pass

    def _set_lut_overlay_enabled(self, enabled: bool):
        self.lut_overlay_enabled = enabled
        if self.lut_overlay_label:
            self.lut_overlay_label.setVisible(enabled)
            if not enabled:
                self.lut_overlay_label.clear()
        if self.annotation_overlay:
            self.annotation_overlay.raise_()
        self._lut_last_frame_id = -1
        self._lut_last_view_matrix = None

    def _update_lut_overlay(self):
        if not self.lut_overlay_enabled:
            return
        if not self.lut_overlay_processor or not self.lut_overlay_label:
            return

        frame, frame_id = self.lut_overlay_processor.getLatestFrame(copy=False)
        if frame is None:
            return

        view_matrix = None
        ortho_params = None
        perspective_matrix = None
        if self.fast_view:
            try:
                view_matrix = self.fast_view.getViewMatrix()
            except Exception:
                view_matrix = None
            try:
                ortho_params = self.fast_view.getOrthoProjectionParameters()
            except Exception:
                ortho_params = None
            try:
                perspective_matrix = self.fast_view.getPerspectiveMatrix()
            except Exception:
                perspective_matrix = None

        view_key = None
        if view_matrix and (ortho_params or perspective_matrix):
            try:
                view_key = tuple(round(v, 6) for row in view_matrix for v in row)
                if ortho_params:
                    view_key += tuple(round(v, 6) for v in ortho_params)
                if perspective_matrix:
                    view_key += tuple(round(v, 6) for row in perspective_matrix for v in row)
            except Exception:
                view_key = None

        if frame_id == self._lut_last_frame_id and view_key == self._lut_last_view_matrix:
            return

        self._lut_last_frame_id = frame_id
        self._lut_last_view_matrix = view_key

        rgb = self.colormap_manager.apply_colormap(frame, self.current_colormap)
        if rgb.dtype != np.uint8:
            rgb = np.clip(rgb, 0, 255).astype(np.uint8)

        if rgb.ndim != 3 or rgb.shape[2] != 3:
            return

        height, width, _ = rgb.shape
        bytes_per_line = 3 * width
        qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
        base_pixmap = QPixmap.fromImage(qimage)

        target_size = self.lut_overlay_label.size()
        if target_size.isEmpty():
            self.lut_overlay_label.setPixmap(base_pixmap)
            return

        canvas = QPixmap(target_size)
        canvas.fill(Qt.transparent)

        def _draw_with_fit():
            scaled = base_pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            x = (target_size.width() - scaled.width()) // 2
            y = (target_size.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()

        if not view_matrix or (not ortho_params and not perspective_matrix):
            _draw_with_fit()
            self.lut_overlay_label.setPixmap(canvas)
            return

        try:
            if ortho_params and len(ortho_params) == 6:
                l, r, b, t, n, f = ortho_params
                if r == l or t == b or f == n:
                    _draw_with_fit()
                    self.lut_overlay_label.setPixmap(canvas)
                    return

                proj = np.array([
                    [2.0 / (r - l), 0.0, 0.0, -(r + l) / (r - l)],
                    [0.0, 2.0 / (t - b), 0.0, -(t + b) / (t - b)],
                    [0.0, 0.0, -2.0 / (f - n), -(f + n) / (f - n)],
                    [0.0, 0.0, 0.0, 1.0],
                ], dtype=np.float64)
            elif ortho_params and len(ortho_params) == 16:
                proj = np.array(ortho_params, dtype=np.float64).reshape(4, 4)
            elif perspective_matrix:
                proj = np.array(perspective_matrix, dtype=np.float64)
                if proj.shape != (4, 4):
                    proj = proj.reshape(4, 4)
            else:
                _draw_with_fit()
                self.lut_overlay_label.setPixmap(canvas)
                return

            view = np.array(view_matrix, dtype=np.float64)

            def world_to_ndc(x, y):
                p = np.array([x, y, 0.0, 1.0], dtype=np.float64)
                clip = proj @ (view @ p)
                if clip[3] == 0:
                    return None
                return (clip[0] / clip[3], clip[1] / clip[3])

            info = self.lut_overlay_processor.getLatestImageInfo()
            size = info.get("size") if info else None
            spacing = info.get("spacing") if info else None
            transform_matrix = info.get("transform_matrix") if info else None

            if not size or not spacing:
                size = (width, height, 1.0)
                spacing = (1.0, 1.0, 1.0)

            sx, sy = float(size[0]), float(size[1])
            spx, spy = float(spacing[0]), float(spacing[1])
            phys_w = sx * spx
            phys_h = sy * spy

            if transform_matrix is None:
                transform_matrix = [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]

            transform = np.array(transform_matrix, dtype=np.float64)

            def image_to_world(x, y):
                p = np.array([x, y, 0.0, 1.0], dtype=np.float64)
                w = transform @ p
                return (w[0], w[1])

            p00 = image_to_world(0.0, 0.0)
            p10 = image_to_world(phys_w, 0.0)
            p01 = image_to_world(0.0, phys_h)
            p11 = image_to_world(phys_w, phys_h)

            points = [
                world_to_ndc(p00[0], p00[1]),
                world_to_ndc(p10[0], p10[1]),
                world_to_ndc(p01[0], p01[1]),
                world_to_ndc(p11[0], p11[1]),
            ]

            if any(p is None for p in points):
                _draw_with_fit()
                self.lut_overlay_label.setPixmap(canvas)
                return

            w = target_size.width()
            h = target_size.height()
            screen_points = [
                ((x * 0.5 + 0.5) * w, (1 - (y * 0.5 + 0.5)) * h)
                for x, y in points
            ]

            xs = [p[0] for p in screen_points]
            ys = [p[1] for p in screen_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            box_w = max_x - min_x
            box_h = max_y - min_y

            if box_w <= 1 or box_h <= 1:
                _draw_with_fit()
                self.lut_overlay_label.setPixmap(canvas)
                return

            scaled = base_pixmap.scaled(int(box_w), int(box_h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(int(min_x), int(min_y), scaled)
            painter.end()

            if self.debug_lut_transform:
                try:
                    image_px_w = max(1.0, float(width))
                    image_px_h = max(1.0, float(height))
                    fast_scale_x = box_w / image_px_w
                    fast_scale_y = box_h / image_px_h
                    lut_scale_x = scaled.width() / image_px_w
                    lut_scale_y = scaled.height() / image_px_h
                    print(
                        "[LUT DEBUG] "
                        f"FAST bbox(px)=({min_x:.1f},{min_y:.1f},{max_x:.1f},{max_y:.1f}) "
                        f"FAST scale(px/px)=({fast_scale_x:.2f},{fast_scale_y:.2f}) "
                        f"LUT bbox(px)=({min_x:.1f},{min_y:.1f},{(min_x + box_w):.1f},{(min_y + box_h):.1f}) "
                        f"LUT scale(px/px)=({lut_scale_x:.2f},{lut_scale_y:.2f})"
                    )
                except Exception:
                    pass
        except Exception:
            _draw_with_fit()

        self.lut_overlay_label.setPixmap(canvas)
        if self.annotation_overlay:
            self.annotation_overlay.raise_()
    
    def _check_and_center(self):
        """Poll to check if first frame is rendered, then center the image."""
        self._center_attempts += 1
        
        try:
            # Check if streamer has started producing frames
            if self.current_streamer and hasattr(self.current_streamer, 'getCurrentFrameIndex'):
                frame_idx = self.current_streamer.getCurrentFrameIndex()
                if frame_idx >= 0:  # First frame has been rendered
                    self._center_timer.stop()
                    self.fast_view.recalculateCamera() # 重新計算相機位置，根據場景邊界框自動調整
                    print(f"Image centered after {self._center_attempts * 50}ms")
                    return
        except:
            pass
        
        # Stop after max attempts (2 seconds)
        if self._center_attempts >= 40:
            self._center_timer.stop()
            # Fallback: try to center anyway
            if self.fast_view:
                self.fast_view.recalculateCamera() # 重新計算相機位置，根據場景邊界框自動調整
            print("Image centered (fallback after timeout)")
    
    @Slot(QListWidgetItem)
    def on_file_selected(self, item):
        """Handle file selection from list."""
        filepath = item.data(Qt.UserRole)
        if filepath and filepath != self.current_file:
            self.load_file(filepath)
    
    @Slot()
    def toggle_playback(self):
        """Toggle play/pause."""
        if self.current_streamer:
            if self.is_playing:
                # Pause
                if hasattr(self.current_streamer, 'setPause'):
                    self.current_streamer.setPause(True)
                self.playback.play_btn.setText("")  # play icon
                self.is_playing = False
                self.status_bar.showMessage("Paused")
            else:
                # Play
                if hasattr(self.current_streamer, 'setPause'):
                    self.current_streamer.setPause(False)
                self.playback.play_btn.setText("")  # pause icon
                self.is_playing = True
                self.status_bar.showMessage("Playing")
    
    @Slot(int)
    def on_frame_slider_changed(self, value):
        """Handle frame slider change."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            self.current_streamer.setCurrentFrameIndex(value)
    
    def on_slider_pressed(self):
        """Pause when user starts dragging slider."""
        if self.is_playing and self.current_streamer:
            if hasattr(self.current_streamer, 'setPause'):
                self.current_streamer.setPause(True)
    
    def on_slider_released(self):
        """Resume if was playing when user releases slider."""
        if self.is_playing and self.current_streamer:
            if hasattr(self.current_streamer, 'setPause'):
                self.current_streamer.setPause(False)
    
    def update_frame_info(self):
        """Update frame info and progress bar."""
        if self.current_streamer:
            try:
                # Get current frame from streamer
                if hasattr(self.current_streamer, 'getCurrentFrameIndex'):
                    self.current_frame = self.current_streamer.getCurrentFrameIndex()
                if hasattr(self.current_streamer, 'getNrOfFrames'):
                    self.total_frames = self.current_streamer.getNrOfFrames()
                
                # Update slider (without triggering valueChanged)
                if self.total_frames > 0:
                    self.playback.frame_slider.blockSignals(True)
                    self.playback.frame_slider.setMaximum(self.total_frames - 1)
                    self.playback.frame_slider.setValue(self.current_frame)
                    self.playback.frame_slider.blockSignals(False)
                
                # Update frame label
                self.playback.frame_label.setText(f"Frame: {self.current_frame + 1} / {self.total_frames}")
                
                # Update time display
                self.playback.update_time_display(self.current_frame, self.total_frames)
                
                # Update W/L display
                self.playback.wl_label.setText(f"W: {self.intensity_window:.0f}  L: {self.intensity_level:.0f}")
            except:
                pass
    
    def set_tool(self, tool_name):
        """Set current tool and update view interaction mode."""
        self.current_tool = tool_name
        self.status_bar.showMessage(f"Tool: {tool_name.capitalize()}")
        
        # Manually update button states (exclusive selection)
        self.toolbar.wl_action.setChecked(tool_name == 'wl')
        self.toolbar.annotate_button.setChecked(tool_name == 'annotate')
        self.toolbar.rotate_action.setChecked(False)  # Rotate is immediate action, always reset

        # Disable annotation overlay when not in annotate mode
        if tool_name != 'annotate' and self.annotation_overlay:
            self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.annotation_overlay.set_tool(None)
        
        # Update FAST view interaction based on tool
        if self.fast_view:
            if tool_name == 'wl':
                # Enable overlay for W/L drag
                if self.annotation_overlay:
                    self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                    self.annotation_overlay.set_tool('wl')
                self.status_bar.showMessage(f"W/L: Drag to adjust | W:{self.intensity_window:.0f} L:{self.intensity_level:.0f}")
            elif tool_name == 'annotate':
                self.status_bar.showMessage("Annotate: Click dropdown to select tool")
    
    def set_annotation_tool(self, tool_type):
        """Set the current annotation tool type."""
        self.current_tool = 'annotate'
        self.current_annotation_tool = tool_type
        self.toolbar.annotate_button.setChecked(True)
        self.toolbar.measure_button.setChecked(False)  # Uncheck measure button
        
        # Enable annotation overlay for drawing
        if self.annotation_overlay:
            self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.annotation_overlay.set_tool(tool_type)
        
        tool_names = {
            'line': '─ Line',
            'rectangle': '▭ Rectangle', 
            'polygon': '⬡ Polygon'
        }
        
        # Different help text for polygon tool
        if tool_type == 'polygon':
            self.status_bar.showMessage(f"Annotation: {tool_names.get(tool_type, tool_type)} - Click to add vertices, double-click to complete")
        else:
            self.status_bar.showMessage(f"Annotation: {tool_names.get(tool_type, tool_type)} - Click and drag to draw")
    
    def set_measure_tool(self, tool_type):
        """Set the current measurement tool type."""
        self.current_tool = 'measure'
        self.current_measure_tool = tool_type
        self.toolbar.measure_button.setChecked(True)
        self.toolbar.annotate_button.setChecked(False)  # Uncheck annotate button
        
        # Enable annotation overlay for drawing measurements
        if self.annotation_overlay:
            self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.annotation_overlay.set_tool(tool_type)
        
        tool_names = {
            'distance': '📏 Distance',
            'angle': '📐 Angle',
            'area': '⬡ Area',
            'perimeter': '⌢ Perimeter',
            'ellipse': '⬭ Ellipse'
        }
        
        # Different help text for different tools
        if tool_type == 'angle':
            self.status_bar.showMessage(f"Measure: {tool_names.get(tool_type, tool_type)} - Click 3 points (start, vertex, end)")
        elif tool_type in ('area', 'perimeter'):
            self.status_bar.showMessage(f"Measure: {tool_names.get(tool_type, tool_type)} - Click to add points, double-click to complete")
        elif tool_type == 'ellipse':
            self.status_bar.showMessage(f"Measure: {tool_names.get(tool_type, tool_type)} - Click center, drag to define axes")
        else:
            self.status_bar.showMessage(f"Measure: {tool_names.get(tool_type, tool_type)} - Click and drag to measure")
    
    def on_measure_added(self, measure):
        """Handle new measurement from overlay."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        # Add to overlay's measurement list for rendering
        if self.annotation_overlay:
            if measure not in self.annotation_overlay.measurements:
                self.annotation_overlay.measurements.append(measure)
            # Trigger repaint to draw shapes and text labels
            self.annotation_overlay.update()
        
        # Show measurement result in status bar
        measurements = measure.get_measurements()
        result_str = " | ".join([f"{k}: {v}" for k, v in measurements.items()])
        self.status_bar.showMessage(f"Measurement: {result_str}", 5000)
    
    def clear_all_measures(self):
        """Clear all measurements from the view."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        
        # Clear from annotation overlay
        if self.annotation_overlay:
            self.annotation_overlay.measurements.clear()
            self.annotation_overlay.update()
        
        self.status_bar.showMessage("All measurements cleared", 3000)
    
    def on_annotation_deleted(self, annotation):
        """Handle annotation deletion from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.remove_annotation(annotation)
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
    
    def on_annotation_visibility_changed(self, annotation, visible):
        """Handle annotation visibility toggle from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.update()  # Refresh display
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
    
    def on_annotation_class_changed(self, annotation, class_type):
        """Handle annotation class type change from layer panel."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        if self.annotation_overlay:
            self.annotation_overlay.update()  # Refresh display
    
    def on_annotation_added(self, annotation):
        """Handle new annotation added."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        pass
    
    def on_preview_updated(self, tool_type, points):
        """Handle annotation preview update."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        pass
    
    def on_preview_cleared(self):
        """Handle annotation preview cleared."""
        # Note: FAST LineRenderer is disabled - Qt AnnotationOverlay handles all rendering
        pass
    
    def on_wl_changed(self, delta_window, delta_level):
        """Handle Window/Level drag changes."""
        # Update values (clamp to reasonable ranges)
        self.intensity_window = max(1, min(1000, self.intensity_window + delta_window))
        self.intensity_level = max(0, min(500, self.intensity_level + delta_level))
        
        # Apply to renderer
        if self.renderer:
            try:
                self.renderer.setIntensityWindow(self.intensity_window)
                self.renderer.setIntensityLevel(self.intensity_level)
            except:
                pass
        
        # Update status bar
        self.status_bar.showMessage(f"W/L: W:{self.intensity_window:.0f} L:{self.intensity_level:.0f}")
    
    def reset_view(self):
        """Reset view to default zoom and pan."""
        self.zoom_level = 1.0
        self.rotation_angle = 0
        
        if self.fast_view:
            try:
                # Directly call FAST API to reset camera (fits view to content)
                self.fast_view.setAutoUpdateCamera(True)
                self.fast_view.recalculateCamera()
                
                self.status_bar.showMessage("View reset to default")
            except Exception as e:
                self.status_bar.showMessage(f"Reset: {e}")
    
    # （2/2）平移事件過濾器 （將右鍵點擊事件轉發給 fast_widget 以實現平移）
    def eventFilter(self, obj, event):
        """Filter events from annotation overlay to forward right-click to fast_widget for pan."""
        from PySide2.QtCore import QEvent
        from PySide2.QtWidgets import QApplication
        
        if obj == self.annotation_overlay and self.fast_widget:
            # Forward right-click events for pan
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
                if hasattr(event, 'button') and event.button() == Qt.RightButton:
                    # Create a new event and send to fast_widget
                    QApplication.sendEvent(self.fast_widget, event)
                    return True  # Event handled
                elif hasattr(event, 'buttons') and event.buttons() == Qt.RightButton:
                    # For MouseMove during right-drag
                    QApplication.sendEvent(self.fast_widget, event)
                    return True
        
        return super().eventFilter(obj, event)

    def toggle_layers_panel(self):
        """Toggle visibility of the layers panel."""
        sizes = self.main_splitter.sizes()
        
        if sizes[2] > 0:
            # Panel is visible, hide it by saving current size and setting to 0
            self._saved_layer_width = sizes[2]
            sizes[2] = 0
            self.main_splitter.setSizes(sizes)
            self.toolbar.layers_button.setChecked(False)
            self.status_bar.showMessage("Layers panel hidden")
        else:
            # Panel is hidden, restore it
            restore_width = getattr(self, '_saved_layer_width', 300)
            sizes[2] = restore_width
            self.main_splitter.setSizes(sizes)
            self.toolbar.layers_button.setChecked(True)
            self.status_bar.showMessage("Layers panel shown")
    
    def rotate_image(self):
        """Rotate the image by 90 degrees."""
        self.rotation_angle = (self.rotation_angle + 90) % 360
        self.status_bar.showMessage(f"Rotation: {self.rotation_angle}°")
        
        # Apply rotation to FAST view
        if self.fast_view:
            try:
                # FAST View rotation (if supported)
                # Note: FAST's View doesn't have direct rotation, 
                # we'd need to apply a transform to the renderer
                pass
            except:
                pass
    
    def prev_frame(self):
        """Go to previous frame."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            new_frame = max(0, self.current_frame - 1)
            self.current_streamer.setCurrentFrameIndex(new_frame)
    
    def next_frame(self):
        """Go to next frame."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            new_frame = min(self.total_frames - 1, self.current_frame + 1)
            self.current_streamer.setCurrentFrameIndex(new_frame)
    
    def first_frame(self):
        """Go to first frame."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            self.current_streamer.setCurrentFrameIndex(0)
            self.status_bar.showMessage("Jumped to first frame")
    
    def last_frame(self):
        """Go to last frame."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            self.current_streamer.setCurrentFrameIndex(max(0, self.total_frames - 1))
            self.status_bar.showMessage("Jumped to last frame")
    
    def rewind_frames(self):
        """Rewind 5 frames."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            new_frame = max(0, self.current_frame - 5)
            self.current_streamer.setCurrentFrameIndex(new_frame)
    
    def forward_frames(self):
        """Forward 5 frames."""
        if self.current_streamer and hasattr(self.current_streamer, 'setCurrentFrameIndex'):
            new_frame = min(self.total_frames - 1, self.current_frame + 5)
            self.current_streamer.setCurrentFrameIndex(new_frame)
    
    def toggle_loop(self, enabled):
        """Toggle loop playback."""
        if self.current_streamer and hasattr(self.current_streamer, 'setLooping'):
            self.current_streamer.setLooping(enabled)
        self.status_bar.showMessage(f"Loop: {'On' if enabled else 'Off'}")
    
    @Slot()
    def take_screenshot(self):
        """Take a screenshot of the current view."""
        if self.fast_view:
            try:
                filepath, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Screenshot",
                    "screenshot.png",
                    "PNG Files (*.png);;JPEG Files (*.jpg)"
                )
                if filepath:
                    # Use FAST's screenshot capability
                    self.fast_view.takeScreenshot(filepath)
                    self.status_bar.showMessage(f"Screenshot saved: {filepath}")
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Could not save screenshot:\n{str(e)}")
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Shortcuts dialog - use Shift+/ for ? key, and also F1
        self.shortcut_help = QShortcut(QKeySequence("?"), self)
        self.shortcut_help.activated.connect(lambda: self.show_help_dialog(1))
        
        # Playback shortcuts
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.activated.connect(self.toggle_playback)
        
        self.shortcut_home = QShortcut(QKeySequence(Qt.Key_Home), self)
        self.shortcut_home.activated.connect(self.first_frame)
        
        self.shortcut_end = QShortcut(QKeySequence(Qt.Key_End), self)
        self.shortcut_end.activated.connect(self.last_frame)
        
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(self.prev_frame)
        
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(self.next_frame)
        
        self.shortcut_shift_left = QShortcut(QKeySequence("Shift+Left"), self)
        self.shortcut_shift_left.activated.connect(self.rewind_frames)
        
        self.shortcut_shift_right = QShortcut(QKeySequence("Shift+Right"), self)
        self.shortcut_shift_right.activated.connect(self.forward_frames)
        
        self.shortcut_loop = QShortcut(QKeySequence("L"), self)
        self.shortcut_loop.activated.connect(lambda: self.playback.loop_btn.toggle())
        
        # View shortcuts
        self.shortcut_reset = QShortcut(QKeySequence("R"), self)
        self.shortcut_reset.activated.connect(self.reset_view)
        
        # Tool shortcuts
        self.shortcut_wl = QShortcut(QKeySequence("W"), self)
        self.shortcut_wl.activated.connect(lambda: self.toolbar.wl_action.trigger())
        
        self.shortcut_annotate = QShortcut(QKeySequence("A"), self)
        self.shortcut_annotate.activated.connect(lambda: self.toolbar.annotate_button.click())
        
        self.shortcut_line = QShortcut(QKeySequence("1"), self)
        self.shortcut_line.activated.connect(lambda: self.set_annotation_tool('line'))
        
        self.shortcut_rect = QShortcut(QKeySequence("2"), self)
        self.shortcut_rect.activated.connect(lambda: self.set_annotation_tool('rectangle'))
        
        self.shortcut_polygon = QShortcut(QKeySequence("3"), self)
        self.shortcut_polygon.activated.connect(lambda: self.set_annotation_tool('polygon'))
        
        self.shortcut_escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.shortcut_escape.activated.connect(lambda: self.set_tool('none'))
        
        # Panel shortcuts
        self.shortcut_layers = QShortcut(QKeySequence("P"), self)
        self.shortcut_layers.activated.connect(self.toggle_layers_panel)
        
        # Image processing shortcuts
        self.shortcut_colormap = QShortcut(QKeySequence("C"), self)
        self.shortcut_colormap.activated.connect(lambda: self.toolbar.colormap_button.showMenu())
        
        self.shortcut_filter = QShortcut(QKeySequence("F"), self)
        self.shortcut_filter.activated.connect(lambda: self.toolbar.filter_button.showMenu())
        
        # Layout shortcuts (Ctrl+1/2/3/4)
        self.shortcut_layout_1x1 = QShortcut(QKeySequence("Ctrl+1"), self)
        self.shortcut_layout_1x1.activated.connect(lambda: self.viewport_manager.set_layout('1x1'))
        
        self.shortcut_layout_1x2 = QShortcut(QKeySequence("Ctrl+2"), self)
        self.shortcut_layout_1x2.activated.connect(lambda: self.viewport_manager.set_layout('1x2'))
        
        self.shortcut_layout_2x1 = QShortcut(QKeySequence("Ctrl+3"), self)
        self.shortcut_layout_2x1.activated.connect(lambda: self.viewport_manager.set_layout('2x1'))
        
        self.shortcut_layout_2x2 = QShortcut(QKeySequence("Ctrl+4"), self)
        self.shortcut_layout_2x2.activated.connect(lambda: self.viewport_manager.set_layout('2x2'))
    
    def show_help_dialog(self, initial_tab=0):
        """Show the Help/Shortcuts dialog."""
        dialog = HelpDialog(self, initial_tab=initial_tab)
        dialog.exec_()
    
    # ==================== Image Processing Methods ====================
    
    def on_colormap_changed(self, action):
        """Handle colormap selection change."""
        colormap_type = action.data()
        if colormap_type:
            self.current_colormap = colormap_type
            self.colormap_manager.set_current_colormap(colormap_type)
            
            # Enable/disable LUT overlay based on colormap selection
            self._set_lut_overlay_enabled(colormap_type != ColormapType.GRAYSCALE)
            
            self.apply_image_processing()
            
            display_name = COLORMAP_DISPLAY_NAMES.get(colormap_type, colormap_type.value)
            self.status_bar.showMessage(f"Colormap: {display_name}", 3000)
    
    def show_colormap_menu(self):
        """Show colormap menu when button is clicked."""
        # Menu already attached, just let it pop up
        pass
    
    def on_filter_changed(self, action):
        """Handle filter selection change."""
        filter_type = action.data()
        if filter_type:
            self.current_filter = filter_type
            self.filter_processor.current_filter = filter_type
            
            # Update the pipeline processor if it exists
            if self.pipeline_filter_processor:
                self.pipeline_filter_processor.setFilter(filter_type, self.filter_strength)
            
            self.apply_image_processing()
            
            display_name = FILTER_DISPLAY_NAMES.get(filter_type, filter_type.value)
            self.status_bar.showMessage(f"Filter: {display_name}", 3000)
    
    def show_filter_strength_dialog(self):
        """Show dialog to adjust filter strength."""
        dialog = FilterStrengthDialog(self.filter_strength, self)
        if dialog.exec_() == QDialog.Accepted:
            self.filter_strength = dialog.get_strength()
            self.filter_processor.filter_strength = self.filter_strength
            
            # Update the pipeline processor if it exists
            if self.pipeline_filter_processor:
                self.pipeline_filter_processor.setFilter(self.current_filter, self.filter_strength)
            
            # Update menu label
            self.toolbar.filter_strength_action.setText(f"▸ Strength: {int(self.filter_strength * 100)}%")
            self.apply_image_processing()
            self.status_bar.showMessage(f"Filter strength: {int(self.filter_strength * 100)}%", 3000)
    
    def apply_image_processing(self):
        """Apply current image processing settings to the renderer.
        
        With PythonProcessObject-based processors in the pipeline,
        filter changes are applied in real-time.
        """
        if not self.renderer:
            return
        
        # The actual processing is done by the pipeline processors
        # (FilterProcessor and FrameTapProcessor) which are already
        # connected in setup_pipeline()
        self._lut_last_frame_id = -1
        
        # Log current settings
        colormap_name = self.current_colormap.value
        filter_name = self.current_filter.value
        
        if self.current_colormap != ColormapType.GRAYSCALE:
            print(f"Image processing active: Colormap={colormap_name}")
        
        if self.current_filter != FilterType.NONE:
            print(f"Image processing active: Filter={filter_name} ({int(self.filter_strength * 100)}%)")

    def closeEvent(self, event):
        """
        Handle window close with proper cleanup order.
        
        Critical cleanup sequence to prevent mutex lock and bus errors:
        1. Stop ViewportManager's shared ComputationThread
        2. Clean up each Viewport's FAST resources (views, renderers)
        3. Wait briefly for C++ layer to complete cleanup
        4. Accept close event and let Qt destroy widgets
        
        This ensures FAST threads are fully stopped and resources are released
        before Qt destroys the widget hierarchy.
        """
        print("[Cleanup] Application closing...")
        
        # CRITICAL: Stop ViewportManager's shared computation thread BEFORE Qt destroys widgets
        # This prevents "mutex lock failed" error caused by thread accessing destroyed View objects
        if hasattr(self, 'viewport_manager') and self.viewport_manager:
            print("[Cleanup] Calling viewport_manager.cleanup()...")
            try:
                # This will:
                # 1. Remove event filter
                # 2. Stop shared ComputationThread
                # 3. Call cleanup() on each Viewport
                #    - Remove all renderers
                #    - Clear annotation managers
                #    - Stop individual pipelines
                #    - Clear object references
                self.viewport_manager.cleanup()
                print("[Cleanup] ViewportManager cleanup complete")
                
                # Brief delay to ensure FAST's C++ layer completes cleanup
                # FAST operations may be asynchronous, so we give it time to finish
                # before Qt destroys the widget hierarchy
                import time
                time.sleep(0.05)  # 50ms safety delay
                print("[Cleanup] Safety delay complete")
                
            except Exception as e:
                print(f"[Cleanup] Error during viewport_manager cleanup: {e}")
                import traceback
                traceback.print_exc()
        
        # Legacy: Stop old computation thread if exists (for backward compatibility)
        # This is kept for any code path that might still use the old single-thread approach
        if hasattr(self, 'computation_thread') and self.computation_thread:
            print("[Cleanup] Stopping legacy computation thread...")
            try:
                self.computation_thread.stop()
                print("[Cleanup] Legacy thread stopped")
            except Exception as e:
                print(f"[Cleanup] Error stopping legacy thread: {e}")
        
        print("[Cleanup] Cleanup complete, accepting close event")
        event.accept()


def run_qt_app(filepath=None):
    """Run the Qt-based application."""
    # Check for existing QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Set default application font to avoid missing font warnings
    default_font = QFont("Helvetica Neue", 11)
    default_font.setStyleHint(QFont.SansSerif)
    app.setFont(default_font)
    
    # Load Lucide icon font
    from PySide2.QtGui import QFontDatabase
    font_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts', 'lucide.ttf')
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id >= 0:
            print(f"Lucide icon font loaded successfully")
        else:
            print(f"Failed to load Lucide icon font")
    
    # Create and show window
    window = UltrasoundViewerWindow()
    
    # Load file if provided
    if filepath:
        window.load_file(filepath)
    
    window.show()
    
    # Run event loop
    return app.exec_()
