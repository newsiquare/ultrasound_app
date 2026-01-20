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
    QDialog, QScrollArea
)
from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt, Slot, QSize, QTimer
from PySide2.QtGui import QIcon, QFont, QPalette, QColor, QKeySequence
from PySide2.QtWidgets import QShortcut
from shiboken2 import wrapInstance

from .annotations import AnnotationOverlay, LayerPanelWidget
from .fast_annotations import FASTAnnotationManager, CoordinateConverter


class FileListWidget(QWidget):
    """Left panel with file list and controls."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Header row with title and icon buttons
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        
        header = QLabel(" Files")
        header.setFont(QFont("lucide", 12, QFont.Bold))
        header.setStyleSheet("color: #ffffff; padding: 5px;")
        header_layout.addWidget(header)
        
        header_layout.addStretch()
        
        # Icon button style
        icon_btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                font-family: 'lucide';
                font-size: 14px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """
        
        # Open File button (icon only)
        self.open_file_btn = QPushButton("\ue0cd")  # file-plus
        self.open_file_btn.setFixedSize(28, 28)
        self.open_file_btn.setToolTip("Open File")
        self.open_file_btn.setStyleSheet(icon_btn_style)
        header_layout.addWidget(self.open_file_btn)
        
        # Open Folder button (icon only)
        self.open_folder_btn = QPushButton("\ue246")  # folder-open
        self.open_folder_btn.setFixedSize(28, 28)
        self.open_folder_btn.setToolTip("Open Folder")
        self.open_folder_btn.setStyleSheet(icon_btn_style)
        header_layout.addWidget(self.open_folder_btn)
        
        layout.addWidget(header_row)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
        """)
        layout.addWidget(self.file_list)
        
        # Patient Info Section
        patient_header = QLabel(" Patient Info")
        patient_header.setFont(QFont("lucide", 11, QFont.Bold))
        patient_header.setStyleSheet("color: #ffffff; padding: 5px 5px 0px 5px; margin-top: 8px;")
        layout.addWidget(patient_header)
        
        # Patient info container
        self.patient_info = QLabel("No file loaded")
        self.patient_info.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                font-size: 11px;
                padding: 5px;
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)
        self.patient_info.setWordWrap(True)
        layout.addWidget(self.patient_info)
        
        # Info label
        self.info_label = QLabel("No files loaded")
        self.info_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def add_file(self, filepath, info=None):
        """Add a file to the list if not already present."""
        # Check for duplicates
        if self.has_file(filepath):
            return
        
        filename = os.path.basename(filepath)
        item = QListWidgetItem(f" {filename}")
        item.setData(Qt.UserRole, filepath)
        if info:
            item.setToolTip(f"{filepath}\n{info}")
            # Store metadata for display
            item.setData(Qt.UserRole + 1, info)
        self.file_list.addItem(item)
        self.update_info()
    
    def has_file(self, filepath):
        """Check if file is already in the list."""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.data(Qt.UserRole) == filepath:
                return True
        return False
    
    def select_file(self, filepath):
        """Select a file in the list by filepath."""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.data(Qt.UserRole) == filepath:
                self.file_list.setCurrentItem(item)
                return
    
    def update_patient_info(self, metadata):
        """Update patient info panel with DICOM metadata."""
        if not metadata:
            self.patient_info.setText("No metadata available")
            return
        
        lines = []
        if 'PatientName' in metadata:
            lines.append(f"<b>Patient:</b> {metadata['PatientName']}")
        if 'StudyDate' in metadata:
            date = metadata['StudyDate']
            # Format YYYYMMDD to YYYY/MM/DD
            if len(date) == 8:
                date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
            lines.append(f"<b>Date:</b> {date}")
        if 'Modality' in metadata:
            lines.append(f"<b>Modality:</b> {metadata['Modality']}")
        if 'Manufacturer' in metadata:
            lines.append(f"<b>Device:</b> {metadata['Manufacturer']}")
        if 'InstitutionName' in metadata:
            lines.append(f"<b>Institution:</b> {metadata['InstitutionName']}")
        if 'NumberOfFrames' in metadata:
            lines.append(f"<b>Frames:</b> {metadata['NumberOfFrames']}")
        
        if lines:
            self.patient_info.setText("<br>".join(lines))
        else:
            self.patient_info.setText("No metadata available")
    
    def update_info(self):
        """Update the info label."""
        count = self.file_list.count()
        self.info_label.setText(f"{count} file(s) loaded")


class ToolbarWidget(QToolBar):
    """Top toolbar with tool buttons."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.setMovable(False)
        self.setIconSize(QSize(24, 24))
        self.setStyleSheet("""
            QToolBar {
                background-color: #3c3c3c;
                border: none;
                padding: 5px;
                spacing: 5px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-bottom: 3px solid transparent;
                border-radius: 4px;
                padding: 6px;
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
        """)
        
        # Create tool buttons using QToolButton (supports custom fonts for Lucide icons)
        # Note: Zoom (scroll wheel) and Pan (right-click drag) are always available via FAST's built-in controls
        
        # Rotate tool
        self.rotate_action = QToolButton(self)
        self.rotate_action.setText(" Rotate")
        self.rotate_action.setFont(QFont("lucide", 11))
        self.rotate_action.setCheckable(True)
        self.rotate_action.setToolTip("Rotate image")
        self.addWidget(self.rotate_action)
                
        # Reset View (not checkable - just an action)
        self.reset_action = QToolButton(self)
        self.reset_action.setText(" Reset")
        self.reset_action.setFont(QFont("lucide", 11))
        self.reset_action.setCheckable(False)
        self.reset_action.setToolTip("Reset view to default (fit to window)")
        self.addWidget(self.reset_action)
        
        # Window/Level tool
        self.wl_action = QToolButton(self)
        self.wl_action.setText(" W/L")
        self.wl_action.setFont(QFont("lucide", 11))
        self.wl_action.setCheckable(True)
        self.wl_action.setToolTip("Window/Level: Drag up/down for brightness, left/right for contrast")
        self.addWidget(self.wl_action)
        
        self.addSeparator()
        
        # Annotate tool with dropdown menu
        self.annotate_button = QToolButton(self)
        self.annotate_button.setText(" Annotate")
        self.annotate_button.setFont(QFont("lucide", 11))
        self.annotate_button.setToolTip("Annotation tools")
        self.annotate_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.annotate_button.setCheckable(True)
        # Set explicit size to ensure dropdown arrow has enough space
        self.annotate_button.setStyleSheet("""
            QToolButton {
                padding-right: 20px;
            }
            QToolButton::menu-button {
                width: 20px;
            }
        """)
        
        # Create annotation menu
        self.annotate_menu = QMenu(self)
        self.annotate_menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 2px;
            }
            QMenu::item {
                padding: 6px 10px;
                margin: 0px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
            QMenu::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        
        # Add annotation tools (use non-checkable actions to avoid indicator space)
        self.line_action = self.annotate_menu.addAction("─ Line")
        self.rect_action = self.annotate_menu.addAction("▭ Rectangle")
        self.polygon_action = self.annotate_menu.addAction("⬡ Polygon")
        
        # Group for exclusive selection
        self.annotate_group = QActionGroup(self)
        self.annotate_group.addAction(self.line_action)
        self.annotate_group.addAction(self.rect_action)
        self.annotate_group.addAction(self.polygon_action)
        self.annotate_group.setExclusive(True)
        
        self.annotate_button.setMenu(self.annotate_menu)
        self.addWidget(self.annotate_button)
        
        self.addSeparator()
        
        # Screenshot
        self.screenshot_action = QToolButton(self)
        self.screenshot_action.setText(" Screenshot")
        self.screenshot_action.setFont(QFont("lucide", 11))
        self.screenshot_action.setToolTip("Save screenshot")
        self.addWidget(self.screenshot_action)
        
        # Settings
        self.settings_action = QToolButton(self)
        self.settings_action.setText(" Settings")
        self.settings_action.setFont(QFont("lucide", 11))
        self.settings_action.setToolTip("Settings")
        self.addWidget(self.settings_action)
        
        self.addSeparator()
        
        # Layers panel toggle action (QAction for overflow menu support)
        self.layers_toggle_action = QToolButton(self)
        self.layers_toggle_action.setText(" Layers")
        self.layers_toggle_action.setFont(QFont("lucide", 11))
        self.layers_toggle_action.setToolTip("Toggle Layers Panel")
        self.addWidget(self.layers_toggle_action)


class ShortcutsDialog(QDialog):
    """Keyboard shortcuts reference dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(" Keyboard Shortcuts")
        self.setFixedSize(420, 520)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
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
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)
        
        # Title with icon and text
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 10)
        title_layout.setSpacing(8)
        title_layout.setAlignment(Qt.AlignCenter)
        
        title_icon = QLabel("")  # keyboard icon
        title_icon.setFont(QFont("lucide", 18))
        title_icon.setStyleSheet("color: #0078d4;")
        title_layout.addWidget(title_icon)
        
        title_text = QLabel("Keyboard Shortcuts")
        title_text.setFont(QFont("Helvetica Neue", 16, QFont.Bold))
        title_text.setStyleSheet("color: #ffffff;")
        title_layout.addWidget(title_text)
        
        layout.addWidget(title_container)
        
        # Scroll area for shortcuts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Define shortcuts by category
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
            "工具": [
                ("W", "Window/Level 調整"),
                ("A", "標註工具"),
                ("1 / 2 / 3", "線段 / 矩形 / 多邊形"),
                ("Esc", "取消當前操作"),
            ],
            "檔案": [
                ("Cmd+O", "開啟檔案"),
                ("Cmd+S", "儲存截圖"),
            ],
            "面板": [
                ("P", "切換圖層面板"),
                ("?", "顯示此快捷鍵面板"),
            ],
        }
        
        for category, items in shortcuts.items():
            # Category header
            header = QLabel(f"【{category}】")
            header.setFont(QFont("Helvetica Neue", 12, QFont.Bold))
            header.setStyleSheet("color: #ffffff; margin-top: 5px;")
            content_layout.addWidget(header)
            
            # Separator line
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #3e3e42;")
            line.setFixedHeight(1)
            content_layout.addWidget(line)
            
            # Shortcut items
            for key, desc in items:
                item_widget = QWidget()
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(10, 2, 10, 2)
                
                # Key label (styled as keyboard key)
                key_label = QLabel(key)
                key_label.setFixedWidth(120)
                key_label.setStyleSheet("""
                    color: #0078d4;
                    font-family: 'SF Mono', Consolas, Monaco, 'Courier New', monospace;
                    font-weight: bold;
                    font-size: 12px;
                """)
                item_layout.addWidget(key_label)
                
                # Description
                desc_label = QLabel(desc)
                desc_label.setStyleSheet("color: #cccccc;")
                item_layout.addWidget(desc_label)
                item_layout.addStretch()
                
                content_layout.addWidget(item_widget)
        
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # Close hint
        hint = QLabel("按 Esc 或 ? 關閉")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #888888; font-size: 11px; margin-top: 10px;")
        layout.addWidget(hint)
    
    def keyPressEvent(self, event):
        """Close on Esc or ? key."""
        if event.key() == Qt.Key_Escape or event.text() == '?':
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
        self.annotations = []  # List of all annotations
        
        # FAST Annotation Manager (will be initialized after fast_view is created)
        self.fast_annotation_manager = None
        
        # Window/Level state
        self.intensity_level = 127.0
        self.intensity_window = 255.0
        self._wl_dragging = False
        self._wl_start_pos = None
        
        self.setup_ui()
        self.apply_dark_theme()
        self.connect_signals()
        self.setup_shortcuts()
        
        # Timer for updating frame info
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_frame_info)
        self.update_timer.start(100)  # Update every 100ms
        
    def setup_ui(self):
        self.setWindowTitle("🔷 Ultrasound Imaging Software")
        self.setMinimumSize(1200, 800)
        
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
        
        # FAST View container with annotation overlay
        self.view_container = QFrame()
        self.view_container.setStyleSheet("background-color: #1e1e1e;")
        self.view_container.setFrameShape(QFrame.NoFrame)
        view_layout = QVBoxLayout(self.view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create FAST view
        self.create_fast_view()
        if self.fast_widget:
            # Create container for FAST widget and overlay
            stack_container = QWidget()
            container_layout = QVBoxLayout(stack_container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addWidget(self.fast_widget)
            
            # Add annotation overlay as child of fast_widget (not stack_container)
            # This ensures proper event propagation to the OpenGL widget
            self.annotation_overlay = AnnotationOverlay(self.fast_widget)
            self.annotation_overlay.setGeometry(0, 0, self.fast_widget.width(), self.fast_widget.height())
            
            # （1/2）安裝平移事件過濾器 (forward events to FAST view)
            self.annotation_overlay.installEventFilter(self)

            # Connect resize to update overlay size and reset camera
            def update_overlay_size():
                if self.annotation_overlay and self.fast_widget:
                    self.annotation_overlay.setGeometry(0, 0, 
                        self.fast_widget.width(), self.fast_widget.height())
                    # Update coordinate converter with new widget size
                    if self.fast_annotation_manager:
                        self.fast_annotation_manager.coord_converter.set_widget_size(
                            self.fast_widget.width(), self.fast_widget.height()
                        )
            
            def on_resize(event):
                update_overlay_size()
                # Direct API call for instant camera recalculation
                if self.fast_view and self.current_streamer:
                    try:
                        self.fast_view.recalculateCamera() # 重新計算相機位置，根據場景邊界框自動調整
                    except:
                        pass
            
            stack_container.resizeEvent = on_resize
            
            view_layout.addWidget(stack_container)
        else:
            # Placeholder if FAST view fails
            placeholder = QLabel("No image loaded\n\nClick 'Open File...' to load a DICOM file")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #888888; font-size: 14px;")
            self.placeholder_label = placeholder
            self.annotation_overlay = None
            view_layout.addWidget(placeholder)
        
        right_layout.addWidget(self.view_container, 1)
        
        # Playback controls
        self.playback = PlaybackControlWidget()
        right_layout.addWidget(self.playback)
        
        splitter.addWidget(right_panel)
        
        # Layer panel (right side)
        self.layer_panel = LayerPanelWidget()
        self.layer_panel.setStyleSheet("background-color: #252526;")
        splitter.addWidget(self.layer_panel)
        
        # Save splitter reference for toggle
        self.main_splitter = splitter
        splitter.setSizes([150, 1000, 250])
        
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
            self.annotation_overlay.wl_changed.connect(self.on_wl_changed)
            # Connect preview signals for FAST annotation sync
            self.annotation_overlay.preview_updated.connect(self.on_preview_updated)
            self.annotation_overlay.preview_cleared.connect(self.on_preview_cleared)
        self.layer_panel.annotation_deleted.connect(self.on_annotation_deleted)
        self.layer_panel.visibility_changed.connect(self.on_annotation_visibility_changed)
        
        # Layers panel toggle
        self.toolbar.layers_toggle_action.clicked.connect(self.toggle_layers_panel)
        
        # Settings -> show shortcuts
        self.toolbar.settings_action.clicked.connect(self.show_shortcuts_dialog)
    
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
        """Load an ultrasound file."""
        self.status_bar.showMessage(f"Loading: {filepath}")
        
        try:
            # Import pipeline function
            from .pipelines import create_playback_pipeline
            from .annotations import Annotation
            
            # Extract DICOM metadata for patient info panel
            dicom_metadata = {}
            pixel_spacing = None
            image_width, image_height = 0, 0
            if filepath.lower().endswith('.dcm'):
                try:
                    import pydicom
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True, force=True)
                    dicom_metadata = {
                        'PatientName': str(ds.get('PatientName', 'Anonymous')),
                        'StudyDate': str(ds.get('StudyDate', '')),
                        'Modality': str(ds.get('Modality', 'US')),
                        'Manufacturer': str(ds.get('Manufacturer', '')),
                        'InstitutionName': str(ds.get('InstitutionName', '')),
                        'NumberOfFrames': str(ds.get('NumberOfFrames', 1)),
                    }
                    
                    # Extract image dimensions
                    if hasattr(ds, 'Columns') and hasattr(ds, 'Rows'):
                        image_width = int(ds.Columns)
                        image_height = int(ds.Rows)
                    
                    # Extract PixelSpacing for real measurements
                    # Try standard PixelSpacing first
                    if hasattr(ds, 'PixelSpacing') and ds.PixelSpacing:
                        pixel_spacing = float(ds.PixelSpacing[0])  # mm/pixel
                    # For ultrasound, try SequenceOfUltrasoundRegions
                    elif hasattr(ds, 'SequenceOfUltrasoundRegions'):
                        regions = ds.SequenceOfUltrasoundRegions
                        if regions and len(regions) > 0:
                            region = regions[0]
                            if hasattr(region, 'PhysicalDeltaX'):
                                # PhysicalDeltaX is in cm, convert to mm
                                pixel_spacing = float(region.PhysicalDeltaX) * 10
                    
                    if pixel_spacing:
                        print(f"Pixel spacing: {pixel_spacing:.4f} mm/pixel")
                    if image_width and image_height:
                        print(f"Image size: {image_width} x {image_height}")
                except Exception as e:
                    print(f"Could not read DICOM metadata: {e}")
            
            # Set pixel spacing for annotations
            Annotation.set_pixel_spacing(pixel_spacing)
            
            # Update FAST annotation manager with image info
            if self.fast_annotation_manager and image_width > 0 and image_height > 0:
                self.fast_annotation_manager.set_image_info(
                    image_width, image_height, 
                    pixel_spacing if pixel_spacing else 1.0
                )
                # Also set widget size for coordinate conversion
                if self.fast_widget:
                    self.fast_annotation_manager.coord_converter.set_widget_size(
                        self.fast_widget.width(), self.fast_widget.height()
                    )
            
            # Update patient info panel
            self.file_panel.update_patient_info(dicom_metadata)
            
            # Create streamer
            self.current_streamer = create_playback_pipeline(filepath)
            
            if self.current_streamer is None:
                QMessageBox.critical(self, "Error", "Failed to load file")
                return
            
            # Add to file list and select
            self.file_panel.add_file(filepath)
            self.file_panel.select_file(filepath)
            self.current_file = filepath
            
            # Setup FAST pipeline
            if self.fast_view:
                self.setup_pipeline()
            
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
            
            # Create renderer
            self.renderer = fast.ImageRenderer.create()
            self.renderer.connect(self.current_streamer)
            self.renderer.setIntensityLevel(self.intensity_level)
            self.renderer.setIntensityWindow(self.intensity_window)
            
            # Clear and add renderer
            self.fast_view.removeAllRenderers()
            self.fast_view.addRenderer(self.renderer)
            # Note: Do NOT call reinitialize() here - it resets internal size to 400x300
            
            # Re-add annotation renderer after removeAllRenderers
            if self.fast_annotation_manager:
                self.fast_annotation_manager.ensure_renderer_added()
            
            # Start computation thread
            self.computation_thread.start()
            self.is_playing = True
            self.playback.play_btn.setText("")  # pause icon
            
            # Event-driven centering: poll until first frame is rendered
            self._center_attempts = 0
            self._center_timer = QTimer(self)
            self._center_timer.timeout.connect(self._check_and_center)
            self._center_timer.start(50)  # Check every 50ms
            
        except Exception as e:
            print(f"Error setting up pipeline: {e}")
    
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
    
    def on_annotation_deleted(self, annotation):
        """Handle annotation deletion from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.remove_annotation(annotation)
        # Also remove from FAST annotation manager
        if self.fast_annotation_manager:
            self.fast_annotation_manager.remove_annotation(annotation)
    
    def on_annotation_visibility_changed(self, annotation, visible):
        """Handle annotation visibility toggle from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.update()  # Refresh display
        # Also update FAST annotation manager
        if self.fast_annotation_manager:
            self.fast_annotation_manager.set_visibility(annotation, visible)
    
    def on_annotation_added(self, annotation):
        """Handle new annotation added - sync to FAST annotation manager."""
        if self.fast_annotation_manager:
            self.fast_annotation_manager.add_annotation(annotation)
    
    def on_preview_updated(self, tool_type, points):
        """Handle annotation preview update - sync to FAST annotation manager."""
        if self.fast_annotation_manager:
            self.fast_annotation_manager.set_preview(tool_type, points)
    
    def on_preview_cleared(self):
        """Handle annotation preview cleared - sync to FAST annotation manager."""
        if self.fast_annotation_manager:
            self.fast_annotation_manager.clear_preview()
    
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
            self.toolbar.layers_toggle_action.setText(" Layers")  # chevron-left: click to open
            self.status_bar.showMessage("Layers panel hidden")
        else:
            # Panel is hidden, restore it
            restore_width = getattr(self, '_saved_layer_width', 300)
            sizes[2] = restore_width
            self.main_splitter.setSizes(sizes)
            self.toolbar.layers_toggle_action.setText(" Layers")  # chevron-right: click to close
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
        self.shortcut_help.activated.connect(self.show_shortcuts_dialog)
        
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
    
    def show_shortcuts_dialog(self):
        """Show keyboard shortcuts dialog."""
        dialog = ShortcutsDialog(self)
        dialog.exec_()
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.computation_thread:
            self.computation_thread.stop()
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
