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

# Must import PySide2.QtSvg before FAST on non-Windows platforms
if platform.system() != 'Windows':
    import PySide2.QtSvg

import fast  # Must import FAST before rest of PySide2

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QToolBar, QToolButton,
    QStatusBar, QSlider, QLabel, QPushButton, QFileDialog, QMessageBox,
    QFrame, QSizePolicy, QAction, QActionGroup, QStyle, QMenu
)
from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt, Slot, QSize, QTimer
from PySide2.QtGui import QIcon, QFont, QPalette, QColor
from shiboken2 import wrapInstance

from .annotations import AnnotationOverlay, LayerPanelWidget


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
        
        header = QLabel("📁 Files")
        header.setFont(QFont("Arial", 12, QFont.Bold))
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
        self.open_file_btn = QPushButton("\ue24d")  # file-plus
        self.open_file_btn.setFixedSize(28, 28)
        self.open_file_btn.setToolTip("Open File")
        self.open_file_btn.setStyleSheet(icon_btn_style)
        header_layout.addWidget(self.open_file_btn)
        
        # Open Folder button (icon only)
        self.open_folder_btn = QPushButton("\ue219")  # folder-open
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
        patient_header = QLabel("👤 Patient Info")
        patient_header.setFont(QFont("Arial", 11, QFont.Bold))
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
        item = QListWidgetItem(f"📄 {filename}")
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
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QToolButton:hover {
                background-color: #505050;
                border: 1px solid #606060;
            }
            QToolButton:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
            }
        """)
        
        # Create tool buttons
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        
        # Pan tool
        self.pan_action = QAction("🖐️ Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.setChecked(True)
        self.pan_action.setToolTip("Pan (drag to move)")
        self.tool_group.addAction(self.pan_action)
        self.addAction(self.pan_action)
        
        # Zoom tool
        self.zoom_action = QAction("🔍 Zoom", self)
        self.zoom_action.setCheckable(True)
        self.zoom_action.setToolTip("Zoom (scroll to zoom)")
        self.tool_group.addAction(self.zoom_action)
        self.addAction(self.zoom_action)
        
        # Reset View (not checkable - just an action)
        self.reset_action = QAction("🎯 Reset", self)
        self.reset_action.setCheckable(False)
        self.reset_action.setToolTip("Reset view to default (fit to window)")
        self.addAction(self.reset_action)
        
        # Rotate tool
        self.rotate_action = QAction("🔄 Rotate", self)
        self.rotate_action.setCheckable(True)
        self.rotate_action.setToolTip("Rotate image")
        self.tool_group.addAction(self.rotate_action)
        self.addAction(self.rotate_action)
        
        # Window/Level tool
        self.wl_action = QAction("☀️ W/L", self)
        self.wl_action.setCheckable(True)
        self.wl_action.setToolTip("Window/Level: Drag up/down for brightness, left/right for contrast")
        self.tool_group.addAction(self.wl_action)
        self.addAction(self.wl_action)
        
        self.addSeparator()
        
        # Annotate tool with dropdown menu
        self.annotate_button = QToolButton(self)
        self.annotate_button.setText("✏️ Annotate")
        self.annotate_button.setToolTip("Annotation tools")
        self.annotate_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.annotate_button.setCheckable(True)
        
        # Create annotation menu
        self.annotate_menu = QMenu(self)
        self.annotate_menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
        """)
        
        # Add annotation tools
        self.line_action = self.annotate_menu.addAction("─ Line")
        self.line_action.setCheckable(True)
        self.rect_action = self.annotate_menu.addAction("▭ Rectangle")
        self.rect_action.setCheckable(True)
        self.circle_action = self.annotate_menu.addAction("○ Circle")
        self.circle_action.setCheckable(True)
        self.freeform_action = self.annotate_menu.addAction("✎ Freeform")
        self.freeform_action.setCheckable(True)
        
        # Group for exclusive selection
        self.annotate_group = QActionGroup(self)
        self.annotate_group.addAction(self.line_action)
        self.annotate_group.addAction(self.rect_action)
        self.annotate_group.addAction(self.circle_action)
        self.annotate_group.addAction(self.freeform_action)
        self.annotate_group.setExclusive(True)
        
        self.annotate_button.setMenu(self.annotate_menu)
        self.addWidget(self.annotate_button)
        
        self.addSeparator()
        
        # Playback controls (use same-length text for consistent button width)
        self.play_action = QAction("⏸️ Pause", self)  # Start with Pause text
        self.play_action.setCheckable(True)
        self.play_action.setChecked(True)  # Start in playing state
        self.play_action.setToolTip("Play/Pause")
        self.addAction(self.play_action)
        
        # Set fixed width for play button to match Reset/Rotate
        play_button = self.widgetForAction(self.play_action)
        if play_button:
            play_button.setMinimumWidth(75)
            play_button.setMaximumWidth(75)
        
        self.prev_action = QAction("⏮️", self)
        self.prev_action.setToolTip("Previous frame")
        self.addAction(self.prev_action)
        
        self.next_action = QAction("⏭️", self)
        self.next_action.setToolTip("Next frame")
        self.addAction(self.next_action)
        
        self.addSeparator()
        
        # Screenshot
        self.screenshot_action = QAction("📷 Screenshot", self)
        self.screenshot_action.setToolTip("Save screenshot")
        self.addAction(self.screenshot_action)
        
        # Settings
        self.settings_action = QAction("⚙️ Settings", self)
        self.settings_action.setToolTip("Settings")
        self.addAction(self.settings_action)
        
        self.addSeparator()
        
        # Layers panel toggle action (QAction for overflow menu support)
        self.layers_toggle_action = QAction("▶ Layers", self)
        self.layers_toggle_action.setToolTip("Toggle Layers Panel")
        self.addAction(self.layers_toggle_action)


class PlaybackControlWidget(QWidget):
    """Bottom playback control bar."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
            }
            QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #505050;
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
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)
        
        # Play/Pause button
        self.play_btn = QPushButton("▶️")
        self.play_btn.setFixedWidth(40)
        layout.addWidget(self.play_btn)
        
        # Frame slider
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(100)
        self.frame_slider.setValue(0)
        layout.addWidget(self.frame_slider, 1)
        
        # Frame info
        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setFixedWidth(120)
        layout.addWidget(self.frame_label)
        
        # Separator
        layout.addWidget(QLabel("|"))
        
        # Window/Level info
        self.wl_label = QLabel("W: 255  L: 127")
        self.wl_label.setFixedWidth(100)
        layout.addWidget(self.wl_label)


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
        self.current_tool = 'pan'
        self.current_annotation_tool = None
        self.annotations = []  # List of all annotations
        
        # Window/Level state
        self.intensity_level = 127.0
        self.intensity_window = 255.0
        self._wl_dragging = False
        self._wl_start_pos = None
        
        self.setup_ui()
        self.apply_dark_theme()
        self.connect_signals()
        
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
            
            # Add annotation overlay as child (will be positioned manually)
            self.annotation_overlay = AnnotationOverlay(stack_container)
            self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Start transparent
            self.annotation_overlay.setGeometry(self.fast_widget.geometry())
            self.annotation_overlay.raise_()  # Ensure it's on top
            
            # Connect resize to update overlay size and reset camera
            def update_overlay_size():
                if self.annotation_overlay and self.fast_widget:
                    self.annotation_overlay.setGeometry(0, 0, 
                        stack_container.width(), stack_container.height())
            
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
            
            # Install event filter for interaction
            self.installEventFilter(self.fast_widget)
            
        except Exception as e:
            print(f"Error creating FAST view: {e}")
            self.fast_view = None
            self.fast_widget = None
    
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
        
        # Toolbar - tools
        self.toolbar.pan_action.triggered.connect(lambda: self.set_tool('pan'))
        self.toolbar.zoom_action.triggered.connect(lambda: self.set_tool('zoom'))
        self.toolbar.reset_action.triggered.connect(self.reset_view)
        self.toolbar.rotate_action.triggered.connect(self.rotate_image)
        self.toolbar.wl_action.triggered.connect(lambda: self.set_tool('wl'))
        
        # Annotation tools
        self.toolbar.annotate_button.clicked.connect(lambda: self.set_tool('annotate'))
        self.toolbar.line_action.triggered.connect(lambda: self.set_annotation_tool('line'))
        self.toolbar.rect_action.triggered.connect(lambda: self.set_annotation_tool('rectangle'))
        self.toolbar.circle_action.triggered.connect(lambda: self.set_annotation_tool('circle'))
        self.toolbar.freeform_action.triggered.connect(lambda: self.set_annotation_tool('freeform'))
        
        # Toolbar - playback
        self.toolbar.play_action.triggered.connect(self.toggle_playback)
        self.toolbar.prev_action.triggered.connect(self.prev_frame)
        self.toolbar.next_action.triggered.connect(self.next_frame)
        self.toolbar.screenshot_action.triggered.connect(self.take_screenshot)
        
        # Playback bar
        self.playback.play_btn.clicked.connect(self.toggle_playback)
        self.playback.frame_slider.sliderPressed.connect(self.on_slider_pressed)
        self.playback.frame_slider.sliderReleased.connect(self.on_slider_released)
        self.playback.frame_slider.valueChanged.connect(self.on_frame_slider_changed)
        
        # Annotation overlay <-> Layer panel
        if self.annotation_overlay:
            self.annotation_overlay.annotation_added.connect(self.layer_panel.add_annotation)
            self.annotation_overlay.wl_changed.connect(self.on_wl_changed)
        self.layer_panel.annotation_deleted.connect(self.on_annotation_deleted)
        self.layer_panel.visibility_changed.connect(self.on_annotation_visibility_changed)
        
        # Layers panel toggle
        self.toolbar.layers_toggle_action.triggered.connect(self.toggle_layers_panel)
    
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
                except Exception as e:
                    print(f"Could not read DICOM metadata: {e}")
            
            # Set pixel spacing for annotations
            Annotation.set_pixel_spacing(pixel_spacing)
            
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
            self.fast_view.reinitialize() # 重新初始化整個 View
            
            # Start computation thread
            self.computation_thread.start()
            self.is_playing = True
            self.playback.play_btn.setText("⏸️")
            
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
                self.playback.play_btn.setText("▶️")
                self.toolbar.play_action.setText("▶️ Play")
                self.toolbar.play_action.setChecked(False)
                self.is_playing = False
                self.status_bar.showMessage("Paused")
            else:
                # Play
                if hasattr(self.current_streamer, 'setPause'):
                    self.current_streamer.setPause(False)
                self.playback.play_btn.setText("⏸️")
                self.toolbar.play_action.setText("⏸️ Pause")
                self.toolbar.play_action.setChecked(True)
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
                
                # Update label
                self.playback.frame_label.setText(f"Frame: {self.current_frame + 1} / {self.total_frames}")
            except:
                pass
    
    def set_tool(self, tool_name):
        """Set current tool and update view interaction mode."""
        self.current_tool = tool_name
        self.status_bar.showMessage(f"Tool: {tool_name.capitalize()}")
        
        # Disable annotation overlay when not in annotate mode
        if tool_name != 'annotate' and self.annotation_overlay:
            self.annotation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        # Update FAST view interaction based on tool
        if self.fast_view:
            if tool_name == 'pan':
                # Default pan mode
                pass
            elif tool_name == 'zoom':
                self.status_bar.showMessage("Zoom: Use mouse scroll to zoom in/out")
            elif tool_name == 'wl':
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
            'circle': '○ Circle',
            'freeform': '✎ Freeform'
        }
        self.status_bar.showMessage(f"Annotation: {tool_names.get(tool_type, tool_type)} - Click and drag to draw")
    
    def on_annotation_deleted(self, annotation):
        """Handle annotation deletion from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.remove_annotation(annotation)
    
    def on_annotation_visibility_changed(self, annotation, visible):
        """Handle annotation visibility toggle from layer panel."""
        if self.annotation_overlay:
            self.annotation_overlay.update()  # Refresh display
    
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
        
        if self.fast_widget:
            try:
                # Simulate pressing 'r' key which is FAST's built-in reset shortcut
                from PySide2.QtGui import QKeyEvent
                from PySide2.QtCore import QEvent
                
                # Create and send key press event for 'r'
                key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_R, Qt.NoModifier, 'r')
                QApplication.sendEvent(self.fast_widget, key_event)
                
                # Send key release event
                key_release = QKeyEvent(QEvent.KeyRelease, Qt.Key_R, Qt.NoModifier, 'r')
                QApplication.sendEvent(self.fast_widget, key_release)
                
                self.status_bar.showMessage("View reset to default (press 'r')")
            except Exception as e:
                self.status_bar.showMessage(f"Reset: {e}")
    
    def toggle_layers_panel(self):
        """Toggle visibility of the layers panel."""
        sizes = self.main_splitter.sizes()
        
        if sizes[2] > 0:
            # Panel is visible, hide it by saving current size and setting to 0
            self._saved_layer_width = sizes[2]
            sizes[2] = 0
            self.main_splitter.setSizes(sizes)
            self.toolbar.layers_toggle_action.setText("◀ Layers")  # Click to open
            self.status_bar.showMessage("Layers panel hidden")
        else:
            # Panel is hidden, restore it
            restore_width = getattr(self, '_saved_layer_width', 300)
            sizes[2] = restore_width
            self.main_splitter.setSizes(sizes)
            self.toolbar.layers_toggle_action.setText("▶ Layers")  # Click to close
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
