"""
Viewport module for multi-window layout support.

Provides:
- Viewport: Single image view with FAST rendering
- ViewportManager: Layout management for multiple viewports
- LayoutButtonWidget: Floating layout selection buttons
"""

import os
import numpy as np

from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QGraphicsOpacityEffect,
    QButtonGroup, QApplication
)
from PySide2.QtCore import Qt, Signal, QTimer, QSize, QPropertyAnimation, QEasingCurve, QObject, QEvent
from PySide2.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide2.QtOpenGL import QGLWidget
from shiboken2 import wrapInstance

import fast

from .annotations import AnnotationOverlay
from .fast_annotations import FASTAnnotationManager, CoordinateConverter
from .image_processing import (
    ColormapManager, ColormapType, FilterType,
    create_filter_processor, create_frame_tap_processor
)


class ViewportEventFilter(QObject):
    """
    Application-level event filter to detect viewport clicks.
    
    This filter intercepts mouse events at the QApplication level,
    allowing us to detect clicks on FAST's QGLWidget without
    interfering with its internal event handling.
    """
    
    def __init__(self, viewport_manager):
        super().__init__()
        self.viewport_manager = viewport_manager
    
    def eventFilter(self, obj, event):
        """Filter events to detect viewport clicks."""
        if event.type() == QEvent.MouseButtonPress:
            try:
                # Find which viewport contains the clicked widget
                viewport = self._find_parent_viewport(obj)
                if viewport is not None:
                    if viewport != self.viewport_manager.active_viewport:
                        self.viewport_manager.set_active_viewport(viewport)
            except RuntimeError:
                # Qt object may have been deleted - ignore safely
                pass
        
        # Never block the event - just observe
        return False
    
    def _find_parent_viewport(self, widget):
        """
        Find the Viewport that contains the given widget.
        
        Traverses the parent chain to find a Viewport ancestor,
        or checks if the widget belongs to any viewport's container.
        """
        from shiboken2 import isValid
        
        if widget is None or not isValid(widget):
            return None
        
        # Direct check: is widget a Viewport?
        if isinstance(widget, Viewport):
            return widget
        
        # Check if widget is inside any viewport's widget tree
        for vp in self.viewport_manager.viewports:
            # Check if widget is part of this viewport
            if self._is_child_of(widget, vp):
                return vp
        
        return None
    
    def _is_child_of(self, widget, parent):
        """
        Check if widget is a child (direct or indirect) of parent.
        """
        from shiboken2 import isValid
        
        current = widget
        while current is not None and isValid(current):
            if current == parent:
                return True
            try:
                current = current.parent() if hasattr(current, 'parent') else None
            except RuntimeError:
                # C++ object deleted
                return False
        return False


class Viewport(QWidget):
    """
    Single image viewport with FAST rendering capabilities.
    
    Encapsulates:
    - FAST View and widget
    - Annotation overlay
    - LUT overlay
    - Pipeline management
    """
    
    # Signals
    activated = Signal(object)  # Emitted when viewport becomes active
    file_loaded = Signal(str)   # Emitted when a file is loaded
    
    def __init__(self, viewport_id: int = 0, parent=None):
        super().__init__(parent)
        self.viewport_id = viewport_id
        self.is_active = False
        
        # FAST components
        self.fast_view = None
        self.fast_widget = None
        self.computation_thread = None
        self.current_streamer = None
        self.renderer = None
        self.current_file = None
        
        # Annotation components
        self.annotation_overlay = None
        self.fast_annotation_manager = None
        
        # LUT overlay
        self.lut_overlay_label = None
        self.lut_overlay_effect = None
        self.lut_overlay_enabled = False
        self.lut_overlay_processor = None
        self._lut_last_frame_id = -1
        self._lut_last_view_matrix = None
        
        # Pipeline processors
        self.pipeline_filter_processor = None
        self.pipeline_frame_tap_processor = None
        
        # Image processing state
        self.colormap_manager = ColormapManager()
        self.current_colormap = ColormapType.GRAYSCALE
        self.current_filter = FilterType.NONE
        self.filter_strength = 0.5
        
        # Rendering state
        self.intensity_level = 127.0
        self.intensity_window = 255.0
        self.is_playing = False
        
        # Image info
        self.image_width = 0
        self.image_height = 0
        self.pixel_spacing = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup viewport UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Container for FAST widget
        self.container = QFrame()
        self.container.setStyleSheet("background-color: #1e1e1e; border: 2px solid #3e3e42;")
        self.container.setFrameShape(QFrame.Box)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create FAST view
        self._create_fast_view()
        
        if self.fast_widget:
            container_layout.addWidget(self.fast_widget)
            
            # LUT overlay label
            self.lut_overlay_label = QLabel(self.fast_widget)
            self.lut_overlay_label.setAlignment(Qt.AlignCenter)
            self.lut_overlay_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.lut_overlay_label.setStyleSheet("background: transparent;")
            self.lut_overlay_effect = QGraphicsOpacityEffect(self.lut_overlay_label)
            self.lut_overlay_effect.setOpacity(0.85)
            self.lut_overlay_label.setGraphicsEffect(self.lut_overlay_effect)
            self.lut_overlay_label.hide()
            
            # Annotation overlay
            self.annotation_overlay = AnnotationOverlay(self.fast_widget)
            self.annotation_overlay.raise_()
            
            if self.fast_annotation_manager:
                self.annotation_overlay.set_coord_converter(
                    self.fast_annotation_manager.coord_converter
                )
            
            # Install event filter to capture clicks on fast_widget
            self.fast_widget.installEventFilter(self)
        else:
            # Placeholder with click support
            self.placeholder = QLabel("點擊此處後載入檔案")
            self.placeholder.setAlignment(Qt.AlignCenter)
            self.placeholder.setStyleSheet("color: #888888; font-size: 12px;")
            container_layout.addWidget(self.placeholder)
        
        layout.addWidget(self.container)
        
        # Handle resize
        self.container.resizeEvent = self._on_resize
        
        # Install event filter on container to capture clicks
        self.container.installEventFilter(self)
        
        # Click to activate (backup)
        self.mousePressEvent = self._on_click
    
    def _create_fast_view(self):
        """Create FAST view and widget."""
        try:
            self.fast_view = fast.View()
            self.fast_view.set2DMode()
            self.fast_view.setBackgroundColor(fast.Color(0.1, 0.1, 0.1))
            self.fast_view.setAutoUpdateCamera(True)
            
            self.fast_widget = wrapInstance(int(self.fast_view.asQGLWidget()), QGLWidget)
            self.fast_widget.setMinimumSize(200, 150)
            self.fast_widget.setFocusPolicy(Qt.StrongFocus)
            self.fast_widget.setMouseTracking(True)
            
            self.fast_annotation_manager = FASTAnnotationManager(self.fast_view)
            
        except Exception as e:
            print(f"Error creating FAST view for viewport {self.viewport_id}: {e}")
            self.fast_view = None
            self.fast_widget = None
            self.fast_annotation_manager = None
    
    def _on_resize(self, event):
        """Handle container resize."""
        if self.fast_widget:
            w, h = self.fast_widget.width(), self.fast_widget.height()
            
            if self.annotation_overlay:
                self.annotation_overlay.setGeometry(0, 0, w, h)
            
            if self.lut_overlay_label:
                self.lut_overlay_label.setGeometry(0, 0, w, h)
                self._lut_last_frame_id = -1
            
            if self.fast_annotation_manager:
                self.fast_annotation_manager.coord_converter.set_widget_size(w, h)
            
            if self.fast_view and self.current_streamer:
                try:
                    self.fast_view.recalculateCamera()
                except:
                    pass
    
    def _on_click(self, event):
        """Handle click to activate viewport."""
        self.activated.emit(self)
        event.accept()
    
    def eventFilter(self, obj, event):
        """Event filter to capture mouse clicks on child widgets."""
        from PySide2.QtCore import QEvent
        if event.type() == QEvent.MouseButtonPress:
            self.activated.emit(self)
        return False  # Don't block the event
    
    def set_active(self, active: bool):
        """Set viewport active state."""
        self.is_active = active
        if active:
            self.container.setStyleSheet("background-color: #1e1e1e; border: 2px solid #0078d4;")
        else:
            self.container.setStyleSheet("background-color: #1e1e1e; border: 2px solid #3e3e42;")
    
    def load_streamer(self, streamer, filepath: str, metadata: dict = None,
                      pixel_spacing: float = None, image_width: int = 0, image_height: int = 0,
                      shared_thread=None):
        """Load a streamer into this viewport.
        
        Args:
            shared_thread: Optional shared ComputationThread from ViewportManager.
        """
        self.current_streamer = streamer
        self.current_file = filepath
        self.pixel_spacing = pixel_spacing
        self.image_width = image_width
        self.image_height = image_height
        
        if self.fast_annotation_manager and image_width > 0 and image_height > 0:
            self.fast_annotation_manager.set_image_info(
                image_width, image_height,
                pixel_spacing if pixel_spacing else 1.0
            )
            if self.fast_widget:
                self.fast_annotation_manager.coord_converter.set_widget_size(
                    self.fast_widget.width(), self.fast_widget.height()
                )
        
        self.setup_pipeline(shared_thread=shared_thread)
        self.file_loaded.emit(filepath)
    
    def setup_pipeline(self, shared_thread=None):
        """Setup FAST rendering pipeline.
        
        Args:
            shared_thread: Optional shared ComputationThread from ViewportManager.
                          If provided, will use shared thread instead of creating own.
        """
        if not self.current_streamer or not self.fast_view:
            return
        
        # Stop any existing rendering
        if self.renderer:
            self.fast_view.removeAllRenderers()
        
        try:
            # Filter processor
            FilterProcessorClass = create_filter_processor()
            self.pipeline_filter_processor = FilterProcessorClass.create()
            self.pipeline_filter_processor.connect(self.current_streamer)
            self.pipeline_filter_processor.setFilter(self.current_filter, self.filter_strength)
            
            # Frame tap processor
            FrameTapProcessorClass = create_frame_tap_processor()
            self.pipeline_frame_tap_processor = FrameTapProcessorClass.create()
            self.pipeline_frame_tap_processor.connect(self.pipeline_filter_processor)
            self.lut_overlay_processor = self.pipeline_frame_tap_processor
            self._lut_last_frame_id = -1
            
            # Renderer
            self.renderer = fast.ImageRenderer.create()
            self.renderer.connect(self.pipeline_frame_tap_processor)
            self.renderer.setIntensityLevel(self.intensity_level)
            self.renderer.setIntensityWindow(self.intensity_window)
            
            # Setup view
            self.fast_view.removeAllRenderers()
            self.fast_view.addRenderer(self.renderer)
            
            if self.fast_annotation_manager:
                self.fast_annotation_manager.ensure_renderer_added()
            
            # Use shared thread if provided, otherwise create own (legacy mode)
            if shared_thread:
                self.computation_thread = None  # Don't manage thread ourselves
            elif not self.computation_thread:
                self.computation_thread = fast.ComputationThread.create()
                self.computation_thread.addView(self.fast_view)
                self.computation_thread.start()
            
            self.is_playing = True
            
        except Exception as e:
            print(f"Error setting up pipeline for viewport {self.viewport_id}: {e}")
            import traceback
            traceback.print_exc()
    
    def stop_pipeline(self):
        """Stop the computation thread."""
        if self.computation_thread:
            try:
                self.computation_thread.stop()
            except:
                pass
            self.computation_thread = None
        self.is_playing = False
    
    def clear(self):
        """Clear the viewport."""
        self.stop_pipeline()
        self.current_streamer = None
        self.current_file = None
        if self.fast_view:
            self.fast_view.removeAllRenderers()


class LayoutButtonWidget(QWidget):
    """
    Floating layout selection buttons.
    
    Displays layout options in the top-right corner of the viewport area.
    """
    
    layout_changed = Signal(str)  # Emits layout name: '1x1', '1x2', '2x1', '2x2'
    
    LAYOUTS = {
        '1x1': '⊡',
        '1x2': '⊟',
        '2x1': '⊞',
        '2x2': '⊞',
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_layout = '1x1'
        self._setup_ui()
        
        # Semi-transparent by default, fully visible on hover
        self.setMouseTracking(True)
        self._opacity = 0.6
        self._update_opacity()
    
    def _setup_ui(self):
        """Setup layout buttons."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 180);
                border-radius: 4px;
            }
        """)
        
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons = {}
        
        btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px;
                min-width: 24px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #777;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """
        
        for layout_name in ['1x1', '1x2', '2x1', '2x2']:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style)
            btn.setToolTip(self._get_tooltip(layout_name))
            btn.clicked.connect(lambda checked=False, name=layout_name: self._on_layout_clicked(name))
            
            # Custom paint for layout icon
            btn.paintEvent = lambda event, b=btn, n=layout_name: self._paint_button(event, b, n)
            
            self.button_group.addButton(btn)
            self.buttons[layout_name] = btn
            layout.addWidget(btn)
        
        # Set default
        self.buttons['1x1'].setChecked(True)
    
    def _get_tooltip(self, layout_name: str) -> str:
        """Get tooltip for layout button."""
        tooltips = {
            '1x1': '單一視窗 (Ctrl+1)',
            '1x2': '左右並排 (Ctrl+2)',
            '2x1': '上下並排 (Ctrl+3)',
            '2x2': '四分割 (Ctrl+4)',
        }
        return tooltips.get(layout_name, layout_name)
    
    def _paint_button(self, event, button, layout_name):
        """Custom paint for layout icon."""
        QPushButton.paintEvent(button, event)
        
        painter = QPainter(button)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate icon area
        rect = button.rect()
        margin = 4
        icon_rect = rect.adjusted(margin, margin, -margin, -margin)
        
        # Set colors
        if button.isChecked():
            pen_color = QColor(255, 255, 255)
            fill_color = QColor(255, 255, 255, 80)
        else:
            pen_color = QColor(180, 180, 180)
            fill_color = QColor(180, 180, 180, 40)
        
        painter.setPen(QPen(pen_color, 1))
        painter.setBrush(QBrush(fill_color))
        
        x, y = icon_rect.x(), icon_rect.y()
        w, h = icon_rect.width(), icon_rect.height()
        gap = 2
        
        if layout_name == '1x1':
            painter.drawRect(x, y, w, h)
        elif layout_name == '1x2':
            half_w = (w - gap) // 2
            painter.drawRect(x, y, half_w, h)
            painter.drawRect(x + half_w + gap, y, half_w, h)
        elif layout_name == '2x1':
            half_h = (h - gap) // 2
            painter.drawRect(x, y, w, half_h)
            painter.drawRect(x, y + half_h + gap, w, half_h)
        elif layout_name == '2x2':
            half_w = (w - gap) // 2
            half_h = (h - gap) // 2
            painter.drawRect(x, y, half_w, half_h)
            painter.drawRect(x + half_w + gap, y, half_w, half_h)
            painter.drawRect(x, y + half_h + gap, half_w, half_h)
            painter.drawRect(x + half_w + gap, y + half_h + gap, half_w, half_h)
        
        painter.end()
    
    def _on_layout_clicked(self, layout_name: str):
        """Handle layout button click."""
        if layout_name != self.current_layout:
            self.current_layout = layout_name
            self.layout_changed.emit(layout_name)
    
    def set_layout(self, layout_name: str):
        """Set current layout programmatically."""
        if layout_name in self.buttons:
            self.buttons[layout_name].setChecked(True)
            self.current_layout = layout_name
    
    def _update_opacity(self):
        """Update widget opacity."""
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(self._opacity)
        self.setGraphicsEffect(effect)
    
    def enterEvent(self, event):
        """Mouse enter - increase opacity."""
        self._opacity = 1.0
        self._update_opacity()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Mouse leave - decrease opacity."""
        self._opacity = 0.6
        self._update_opacity()
        super().leaveEvent(event)


class ViewportManager(QWidget):
    """
    Manages multiple viewports in a grid layout.
    
    Supports layouts: 1x1, 1x2, 2x1, 2x2
    """
    
    # Signals
    active_viewport_changed = Signal(object)  # Viewport
    layout_changed = Signal(str)              # Layout name
    
    LAYOUTS = {
        '1x1': (1, 1),
        '1x2': (1, 2),
        '2x1': (2, 1),
        '2x2': (2, 2),
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewports = []
        self.active_viewport = None
        self.current_layout = '1x1'
        self.max_viewports = 4
        
        # Shared ComputationThread for all viewports
        # FAST requires a single thread to manage all OpenGL contexts
        self._shared_computation_thread = None
        self._thread_started = False
        
        # Application-level event filter for viewport activation
        self._event_filter = None
        
        self._setup_ui()
        self._create_viewports()
        self._apply_layout('1x1')
        
        # Install application-level event filter
        self._install_event_filter()
    
    def _setup_ui(self):
        """Setup manager UI."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Container for viewports
        self.viewport_container = QWidget()
        self.viewport_container.setStyleSheet("background-color: #1e1e1e;")
        self.grid_layout = QGridLayout(self.viewport_container)
        self.grid_layout.setContentsMargins(2, 2, 2, 2)
        self.grid_layout.setSpacing(2)
        
        self.main_layout.addWidget(self.viewport_container)
        
        # Floating layout buttons (will be positioned in resizeEvent)
        self.layout_buttons = LayoutButtonWidget(self)
        self.layout_buttons.layout_changed.connect(self.set_layout)
        self.layout_buttons.raise_()
    
    def _create_viewports(self):
        """Create viewport instances."""
        # Create shared computation thread FIRST
        self._shared_computation_thread = fast.ComputationThread.create()
        
        for i in range(self.max_viewports):
            viewport = Viewport(viewport_id=i, parent=self)
            viewport.activated.connect(self._on_viewport_activated)
            
            # Add viewport's FAST View to shared thread
            if viewport.fast_view:
                self._shared_computation_thread.addView(viewport.fast_view)
            
            self.viewports.append(viewport)
        
        # Set first viewport as active
        if self.viewports:
            self.viewports[0].set_active(True)
            self.active_viewport = self.viewports[0]
    
    def _apply_layout(self, layout_name: str):
        """Apply the specified layout."""
        if layout_name not in self.LAYOUTS:
            return
        
        rows, cols = self.LAYOUTS[layout_name]
        
        # Remove all viewports from grid
        for viewport in self.viewports:
            self.grid_layout.removeWidget(viewport)
            viewport.hide()
        
        # Add viewports according to layout
        viewport_idx = 0
        for row in range(rows):
            for col in range(cols):
                if viewport_idx < len(self.viewports):
                    viewport = self.viewports[viewport_idx]
                    self.grid_layout.addWidget(viewport, row, col)
                    viewport.show()
                    viewport_idx += 1
        
        self.current_layout = layout_name
        self.layout_buttons.set_layout(layout_name)
        
        # Ensure active viewport is visible
        if self.active_viewport and not self.active_viewport.isVisible():
            self.set_active_viewport(self.viewports[0])
    
    def _on_viewport_activated(self, viewport: Viewport):
        """Handle viewport activation."""
        self.set_active_viewport(viewport)
    
    def set_layout(self, layout_name: str):
        """Set the current layout."""
        if layout_name != self.current_layout:
            self._apply_layout(layout_name)
            self.layout_changed.emit(layout_name)
    
    def set_active_viewport(self, viewport: Viewport):
        """Set the active viewport."""
        if self.active_viewport:
            self.active_viewport.set_active(False)
        
        viewport.set_active(True)
        self.active_viewport = viewport
        self.active_viewport_changed.emit(viewport)
    
    def get_active_viewport(self) -> Viewport:
        """Get the currently active viewport."""
        return self.active_viewport
    
    def get_visible_viewports(self):
        """Get list of currently visible viewports."""
        return [vp for vp in self.viewports if vp.isVisible()]
    
    def resizeEvent(self, event):
        """Position layout buttons on resize."""
        super().resizeEvent(event)
        
        # Position layout buttons in top-right corner
        btn_width = self.layout_buttons.sizeHint().width()
        btn_height = self.layout_buttons.height()
        margin = 10
        
        self.layout_buttons.setGeometry(
            self.width() - btn_width - margin,
            margin,
            btn_width + 8,
            btn_height
        )
        self.layout_buttons.raise_()
    
    def _install_event_filter(self):
        """Install application-level event filter for viewport activation."""
        app = QApplication.instance()
        if app:
            self._event_filter = ViewportEventFilter(self)
            app.installEventFilter(self._event_filter)
    
    def _remove_event_filter(self):
        """Remove event filter (call on cleanup)."""
        if self._event_filter:
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self._event_filter)
            self._event_filter = None
    
    def ensure_computation_thread_running(self):
        """Ensure the shared computation thread is running."""
        if self._shared_computation_thread and not self._thread_started:
            self._shared_computation_thread.start()
            self._thread_started = True
    
    def stop_computation_thread(self):
        """Stop the shared computation thread."""
        if self._shared_computation_thread and self._thread_started:
            try:
                self._shared_computation_thread.stop()
            except:
                pass
            self._thread_started = False
    
    def cleanup(self):
        """Cleanup resources."""
        self._remove_event_filter()
        self.stop_computation_thread()
        
        # Cleanup viewports
        for vp in self.viewports:
            if hasattr(vp, 'cleanup'):
                vp.cleanup()
