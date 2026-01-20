"""
Annotation system for ultrasound imaging software.

This module provides annotation data models and UI widgets:
- Line, Rectangle, Polygon shapes (data models)
- Measurements (width, height, area, length)
- Layer panel widget for annotation management

Note: Actual rendering is handled by FASTAnnotationManager in fast_annotations.py
"""

from PySide2.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                                QPushButton, QCheckBox, QScrollArea, QSizePolicy,
                                QComboBox, QStyledItemDelegate, QStyle)
from PySide2.QtCore import Qt, QPoint, QRect, Signal
from PySide2.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath
import math
from typing import Tuple, List, Optional


# Default annotation color (Cyan) as RGB tuple (0-1 range)
DEFAULT_COLOR = (0.0, 1.0, 1.0)

# Annotation class types with colors (RGB 0-1 range)
CLASS_TYPES = {
    'None': {'color': (0.0, 1.0, 1.0), 'hex': '#00FFFF'},      # Cyan (default)
    'Thrombus': {'color': (1.0, 0.42, 0.42), 'hex': '#FF6B6B'},  # Red
    'Plaque': {'color': (1.0, 0.85, 0.24), 'hex': '#FFD93D'},    # Yellow
    'Calcification': {'color': (0.42, 0.80, 1.0), 'hex': '#6BCBFF'},  # Blue
}


class Annotation:
    """
    Base class for all annotations.
    
    Stores annotation data (points, color, state) without rendering logic.
    Rendering is handled by FASTAnnotationManager.
    """
    
    _id_counter = 0
    _pixel_spacing = None  # mm per pixel, shared across annotations
    
    @classmethod
    def set_pixel_spacing(cls, spacing):
        """Set pixel spacing in mm/pixel."""
        cls._pixel_spacing = spacing
    
    @classmethod
    def reset_id_counter(cls):
        """Reset ID counter (for testing)."""
        cls._id_counter = 0
    
    def __init__(self, color: Tuple[float, float, float] = DEFAULT_COLOR):
        """
        Initialize annotation.
        
        Args:
            color: RGB tuple with values 0-1, default cyan
        """
        Annotation._id_counter += 1
        self.id = Annotation._id_counter
        self.color = color  # RGB tuple (0-1 range)
        self.class_type = 'None'  # Classification type (Thrombus, Plaque, Calcification)
        self.points: List[Tuple[float, float]] = []  # List of (x, y) pixel coordinates
        self.completed = False
        self.selected = False
        self.visible = True
    
    def set_class_type(self, class_type: str):
        """Set annotation class type and update color."""
        if class_type in CLASS_TYPES:
            self.class_type = class_type
            self.color = CLASS_TYPES[class_type]['color']
    
    def _px_to_mm(self, pixels):
        """Convert pixels to mm if pixel_spacing available."""
        if Annotation._pixel_spacing:
            return pixels * Annotation._pixel_spacing
        return None
    
    def _format_length(self, pixels):
        """Format length with unit (mm or px)."""
        mm = self._px_to_mm(pixels)
        if mm is not None:
            return f"{mm:.2f} mm"
        return f"{pixels:.1f} px"
    
    def _format_area(self, pixels_sq):
        """Format area with unit (cm² or px²)."""
        if Annotation._pixel_spacing:
            mm_sq = pixels_sq * (Annotation._pixel_spacing ** 2)
            cm_sq = mm_sq / 100  # mm² to cm²
            return f"{cm_sq:.2f} cm²"
        return f"{pixels_sq:.0f} px²"
    
    def add_point(self, x: float, y: float):
        """Add a point to the annotation."""
        self.points.append((x, y))
    
    def update_last_point(self, x: float, y: float):
        """Update the last point (for dragging)."""
        if self.points:
            self.points[-1] = (x, y)
    
    def complete(self):
        """Mark annotation as complete."""
        self.completed = True
    
    def get_measurements(self):
        """Return measurements dict. Override in subclasses."""
        return {}
    
    def get_name(self):
        """Return annotation name for layer panel."""
        return f"Annotation {self.id}"
    
    def get_bounding_rect(self) -> Tuple[float, float, float, float]:
        """
        Return bounding rectangle as (x, y, width, height).
        
        Returns:
            Tuple of (min_x, min_y, width, height) in pixel coordinates
        """
        if len(self.points) < 2:
            return (0, 0, 0, 0)
        x_coords = [p[0] for p in self.points]
        y_coords = [p[1] for p in self.points]
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        return (min_x, min_y, max_x - min_x, max_y - min_y)


class LineAnnotation(Annotation):
    """
    Line annotation with length measurement.
    
    Two points define the line endpoints.
    """
    
    def _calculate_length(self) -> float:
        """Calculate line length in pixels."""
        if len(self.points) < 2:
            return 0
        dx = self.points[1][0] - self.points[0][0]
        dy = self.points[1][1] - self.points[0][1]
        return math.sqrt(dx * dx + dy * dy)
    
    def get_measurements(self):
        length_px = self._calculate_length()
        return {"Length": self._format_length(length_px)}
    
    def get_name(self):
        return f"Line {self.id}"


class RectAnnotation(Annotation):
    """
    Rectangle annotation with width, height, area measurements.
    
    Two points define opposite corners of the rectangle.
    """
    
    def get_corners(self) -> List[Tuple[float, float]]:
        """
        Get the 4 corners of the rectangle in order: TL, TR, BR, BL.
        
        Returns:
            List of 4 (x, y) tuples representing corners
        """
        if len(self.points) < 2:
            return []
        
        x1, y1 = self.points[0]
        x2, y2 = self.points[1]
        
        # Normalize to get min/max
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)
        
        return [
            (min_x, min_y),  # Top-left
            (max_x, min_y),  # Top-right
            (max_x, max_y),  # Bottom-right
            (min_x, max_y),  # Bottom-left
        ]
    
    def _get_dimensions(self) -> Tuple[float, float]:
        """Get width and height in pixels."""
        if len(self.points) < 2:
            return (0, 0)
        w = abs(self.points[1][0] - self.points[0][0])
        h = abs(self.points[1][1] - self.points[0][1])
        return (w, h)
    
    def get_measurements(self):
        w, h = self._get_dimensions()
        area = w * h
        return {
            "Width": self._format_length(w),
            "Height": self._format_length(h),
            "Area": self._format_area(area)
        }
    
    def get_name(self):
        return f"Rectangle {self.id}"


class PolygonAnnotation(Annotation):
    """
    Polygon annotation with perimeter and area measurements.
    
    Multiple points define the polygon vertices.
    Click to add vertices, double-click or press Enter to complete.
    """
    
    def __init__(self, color: Tuple[float, float, float] = DEFAULT_COLOR, 
                 closed: bool = True):
        """
        Initialize polygon annotation.
        
        Args:
            color: RGB tuple with values 0-1
            closed: Whether the polygon should be closed (connect last to first)
        """
        super().__init__(color)
        self.closed = closed
    
    def _calculate_perimeter(self) -> float:
        """Calculate polygon perimeter in pixels."""
        if len(self.points) < 2:
            return 0
        
        perimeter = 0
        for i in range(len(self.points) - 1):
            dx = self.points[i + 1][0] - self.points[i][0]
            dy = self.points[i + 1][1] - self.points[i][1]
            perimeter += math.sqrt(dx * dx + dy * dy)
        
        # Add closing edge if closed
        if self.closed and len(self.points) >= 3:
            dx = self.points[0][0] - self.points[-1][0]
            dy = self.points[0][1] - self.points[-1][1]
            perimeter += math.sqrt(dx * dx + dy * dy)
        
        return perimeter
    
    def _calculate_area(self) -> float:
        """
        Calculate polygon area using shoelace formula.
        
        Returns:
            Area in square pixels (absolute value)
        """
        if len(self.points) < 3:
            return 0
        
        # Shoelace formula
        n = len(self.points)
        area = 0
        for i in range(n):
            j = (i + 1) % n
            area += self.points[i][0] * self.points[j][1]
            area -= self.points[j][0] * self.points[i][1]
        
        return abs(area) / 2
    
    def get_measurements(self):
        perimeter = self._calculate_perimeter()
        measurements = {"Perimeter": self._format_length(perimeter)}
        
        if self.closed and len(self.points) >= 3:
            area = self._calculate_area()
            measurements["Area"] = self._format_area(area)
        
        return measurements
    
    def get_name(self):
        return f"Polygon {self.id}"


# Legacy alias for backward compatibility during transition
FreeformAnnotation = PolygonAnnotation
CircleAnnotation = PolygonAnnotation  # Temporarily alias, will be removed


class AnnotationOverlay(QWidget):
    """Transparent overlay widget for drawing annotations on top of the image."""
    
    annotation_added = Signal(object)  # Emitted when annotation is completed
    wl_changed = Signal(float, float)  # Emitted when W/L changes (delta_window, delta_level)
    preview_updated = Signal(str, list)  # Emitted when preview changes (tool_type, points)
    preview_cleared = Signal()  # Emitted when preview is cleared
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Default transparent, enable only for annotation/W/L modes
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        self.annotations = []
        self.current_annotation = None
        self.current_tool = None
        self.is_drawing = False
        
        # W/L drag state
        self._wl_start_pos = None
        
        # Polygon drawing state
        self._polygon_points = []
        
        # Current mouse position for preview line
        self._current_mouse_pos = None
    
    def set_tool(self, tool_type):
        """Set the current annotation tool."""
        self.current_tool = tool_type
        # Reset polygon points when tool changes
        self._polygon_points = []
        self._current_mouse_pos = None
        self.preview_cleared.emit()
    
    def paintEvent(self, event):
        """
        Paint event - all annotation rendering is now handled by FAST LineRenderer.
        
        FAST handles:
        - Completed annotations (via annotation_added signal)
        - Preview during drawing (via preview_updated signal)
        
        Qt Overlay is now only used for:
        - Mouse event handling
        - Coordinate collection
        """
        # All rendering is now done by FAST LineRenderer
        # This ensures annotations follow zoom/pan automatically
        pass
    
    def _draw_annotation(self, painter, annotation):
        """Draw a single annotation using Qt."""
        # Convert color tuple to QColor
        r, g, b = annotation.color
        qcolor = QColor(int(r * 255), int(g * 255), int(b * 255))
        pen = QPen(qcolor, 2 if not annotation.selected else 3)
        painter.setPen(pen)
        
        ann_type = type(annotation).__name__
        
        if ann_type == 'LineAnnotation' and len(annotation.points) >= 2:
            p1 = QPoint(int(annotation.points[0][0]), int(annotation.points[0][1]))
            p2 = QPoint(int(annotation.points[1][0]), int(annotation.points[1][1]))
            painter.drawLine(p1, p2)
            
        elif ann_type == 'RectAnnotation' and len(annotation.points) >= 2:
            corners = annotation.get_corners()
            if len(corners) >= 4:
                painter.setBrush(QBrush(QColor(0, 255, 255, 30)))
                p1 = QPoint(int(corners[0][0]), int(corners[0][1]))
                p3 = QPoint(int(corners[2][0]), int(corners[2][1]))
                rect = QRect(p1, p3).normalized()
                painter.drawRect(rect)
                painter.setBrush(Qt.NoBrush)
                
        elif ann_type == 'PolygonAnnotation' and len(annotation.points) >= 2:
            path = QPainterPath()
            path.moveTo(annotation.points[0][0], annotation.points[0][1])
            for pt in annotation.points[1:]:
                path.lineTo(pt[0], pt[1])
            if annotation.closed and len(annotation.points) >= 3:
                path.closeSubpath()
            painter.drawPath(path)
    
    def _draw_polygon_preview(self, painter):
        """Draw polygon preview while user is adding points."""
        pen = QPen(QColor(0, 255, 255), 2, Qt.DashLine)
        painter.setPen(pen)
        
        if len(self._polygon_points) >= 1:
            path = QPainterPath()
            path.moveTo(self._polygon_points[0][0], self._polygon_points[0][1])
            for pt in self._polygon_points[1:]:
                path.lineTo(pt[0], pt[1])
            # Draw line to current mouse position
            if self._current_mouse_pos:
                path.lineTo(self._current_mouse_pos[0], self._current_mouse_pos[1])
            painter.drawPath(path)
    
    def mousePressEvent(self, event):
        """Start drawing annotation or W/L adjustment."""
        if event.button() != Qt.LeftButton:
            return
        
        # Handle W/L mode
        if self.current_tool == 'wl':
            self._wl_start_pos = event.pos()
            return
        
        if not self.current_tool:
            return
        
        pos = event.pos()
        x, y = pos.x(), pos.y()
        
        # Handle polygon tool - click to add points
        if self.current_tool == 'polygon':
            self._polygon_points.append((x, y))
            # Emit preview update for FAST rendering
            self.preview_updated.emit('polygon', list(self._polygon_points))
            self.update()
            return
        
        self.is_drawing = True
        
        # Create new annotation based on tool type
        if self.current_tool == 'line':
            self.current_annotation = LineAnnotation()
        elif self.current_tool == 'rectangle':
            self.current_annotation = RectAnnotation()
        
        if self.current_annotation:
            self.current_annotation.add_point(x, y)
            self.current_annotation.add_point(x, y)  # Add second point for dragging
            # Emit preview update for FAST rendering
            self.preview_updated.emit(self.current_tool, list(self.current_annotation.points))
        
        self.update()
    
    def mouseDoubleClickEvent(self, event):
        """Complete polygon on double-click."""
        if self.current_tool == 'polygon' and len(self._polygon_points) >= 3:
            # Create and complete polygon
            annotation = PolygonAnnotation(closed=True)
            for pt in self._polygon_points:
                annotation.add_point(pt[0], pt[1])
            annotation.complete()
            
            self.annotations.append(annotation)
            self.annotation_added.emit(annotation)
            self._polygon_points = []
            self._current_mouse_pos = None
            # Clear preview in FAST
            self.preview_cleared.emit()
            self.update()
    
    def mouseMoveEvent(self, event):
        """Update annotation while dragging or adjust W/L."""
        pos = event.pos()
        x, y = pos.x(), pos.y()
        
        # Handle W/L mode
        if self.current_tool == 'wl' and self._wl_start_pos is not None:
            # Horizontal = window (contrast), Vertical = level (brightness)
            delta_window = (pos.x() - self._wl_start_pos.x()) * 1.0
            delta_level = -(pos.y() - self._wl_start_pos.y()) * 1.0  # Invert Y
            self._wl_start_pos = pos
            self.wl_changed.emit(delta_window, delta_level)
            return
        
        # Track current mouse position for preview
        self._current_mouse_pos = (x, y)
        
        # Handle polygon preview - update preview with mouse position
        if self.current_tool == 'polygon' and len(self._polygon_points) >= 1:
            # Emit preview with current points + mouse position
            preview_points = list(self._polygon_points) + [(x, y)]
            self.preview_updated.emit('polygon', preview_points)
            self.update()
            return
        
        if not self.is_drawing or not self.current_annotation:
            return
        
        # Update the last point
        self.current_annotation.update_last_point(x, y)
        # Emit preview update for FAST rendering
        self.preview_updated.emit(self.current_tool, list(self.current_annotation.points))
        
        self.update()
    
    def mouseReleaseEvent(self, event):
        """Complete the annotation or W/L adjustment."""
        if event.button() != Qt.LeftButton:
            return
        
        # Handle W/L mode
        if self.current_tool == 'wl':
            self._wl_start_pos = None
            return
        
        # Polygon is completed on double-click, not release
        if self.current_tool == 'polygon':
            return
        
        if not self.is_drawing:
            return
        
        self.is_drawing = False
        
        if self.current_annotation:
            self.current_annotation.complete()
            self.annotations.append(self.current_annotation)
            self.annotation_added.emit(self.current_annotation)
            self.current_annotation = None
            # Clear preview in FAST
            self.preview_cleared.emit()
        
        self.update()
    
    def clear_annotations(self):
        """Clear all annotations."""
        self.annotations.clear()
        self.update()
    
    def remove_annotation(self, annotation):
        """Remove a specific annotation."""
        if annotation in self.annotations:
            self.annotations.remove(annotation)
            self.update()


class ClassColorDelegate(QStyledItemDelegate):
    """Custom delegate to render class type items with their corresponding colors."""
    
    def paint(self, painter, option, index):
        # Get the class name from the item
        class_name = index.data(Qt.DisplayRole)
        
        # Get the color for this class
        color_hex = CLASS_TYPES.get(class_name, CLASS_TYPES['None'])['hex']
        
        # Draw the background if selected/hovered
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor('#094771'))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor('#3e3e42'))
        else:
            painter.fillRect(option.rect, QColor('#252526'))
        
        # Draw the text with the class color
        painter.setPen(QColor(color_hex))
        painter.setFont(option.font)
        text_rect = option.rect.adjusted(8, 0, -4, 0)  # Add left padding
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, class_name)


class LayerItemWidget(QWidget):
    """Custom widget for each annotation layer item with table-style layout."""
    
    visibility_toggled = Signal(object, bool)
    delete_clicked = Signal(object)
    class_changed = Signal(object, str)  # annotation, new_class_type
    
    def __init__(self, annotation, parent=None):
        super().__init__(parent)
        
        self.annotation = annotation
        self.is_visible = True
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        
        # Column 1: Visibility toggle (24px)
        self.visibility_btn = QPushButton("\ue0be")  # eye icon
        self.visibility_btn.setFixedSize(24, 24)
        self.visibility_btn.setFont(QFont("lucide", 12))
        self.visibility_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #00ffff;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-radius: 3px;
            }
        """)
        self.visibility_btn.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.visibility_btn)
        
        # Column 2: Shape icon (24px)
        icons = {
            'Line': '\ue11f',        # minus
            'Rectangle': '\ue379',   # rectangle-horizontal
            'Polygon': '\ue27d',     # pentagon
        }
        name = annotation.get_name()
        shape_type = name.split()[0] if name else 'Shape'
        icon = icons.get(shape_type, '\ue27d')
        
        self.icon_label = QLabel(icon)
        self.icon_label.setFont(QFont("lucide", 12))
        self.icon_label.setStyleSheet("color: #00ffff;")
        self.icon_label.setFixedWidth(24)
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Column 3: Label name (60px fixed)
        self.name_label = QLabel(name)
        self.name_label.setFixedWidth(60)
        self.name_label.setStyleSheet("color: #ffffff; font-size: 11px;")
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.name_label)
        
        # Column 4: Class dropdown (90px)
        self.class_combo = QComboBox()
        self.class_combo.setFixedWidth(90)
        self.class_combo.setFixedHeight(22)
        
        # Use custom delegate for colored items in dropdown
        self.class_combo.setItemDelegate(ClassColorDelegate(self.class_combo))
        
        # Add class options
        for class_name in CLASS_TYPES.keys():
            self.class_combo.addItem(class_name)
        
        # Set current class
        current_index = list(CLASS_TYPES.keys()).index(annotation.class_type) if annotation.class_type in CLASS_TYPES else 0
        self.class_combo.setCurrentIndex(current_index)
        
        self._update_combo_style()
        self.class_combo.currentTextChanged.connect(self._on_class_changed)
        layout.addWidget(self.class_combo)
        
        # Column 5: Measurements info (fixed 30px with tooltip)
        measurements = annotation.get_measurements()
        full_measure_text = " | ".join([f"{v}" for v in measurements.values()])
        self.measure_label = QLabel("...")
        self.measure_label.setFixedWidth(30)
        self.measure_label.setStyleSheet("color: #888888; font-size: 10px;")
        self.measure_label.setAlignment(Qt.AlignCenter)
        self.measure_label.setToolTip(full_measure_text)  # Hover to show full info
        layout.addWidget(self.measure_label)
        
        # Column 6: Delete button (24px)
        self.delete_btn = QPushButton("\ue18d")  # trash-2 icon
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setFont(QFont("lucide", 12))
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #555555;
            }
            QPushButton:hover {
                background-color: #ff5555;
                border-radius: 3px;
                color: #ffffff;
            }
        """)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.delete_btn)
        
        self.setFixedHeight(32)
        self.setStyleSheet("""
            LayerItemWidget {
                background-color: #2d2d30;
                border-radius: 4px;
            }
            LayerItemWidget:hover {
                background-color: #3e3e42;
            }
        """)
    
    def _update_combo_style(self):
        """Update combo box style based on selected class."""
        class_type = self.class_combo.currentText()
        color_hex = CLASS_TYPES.get(class_type, CLASS_TYPES['None'])['hex']
        
        self.class_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: #252526;
                border: 1px solid {color_hex};
                border-radius: 3px;
                color: {color_hex};
                font-size: 10px;
                padding: 2px 4px;
            }}
            QComboBox:hover {{
                border: 1px solid {color_hex};
                background-color: #3e3e42;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {color_hex};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #252526;
                border: 1px solid #3e3e42;
                selection-background-color: #094771;
                color: #cccccc;
            }}
        """)
        
        # Also update icon color to match class
        self.icon_label.setStyleSheet(f"color: {color_hex};")
    
    def _on_class_changed(self, class_type):
        """Handle class type change."""
        self._update_combo_style()
        self.class_changed.emit(self.annotation, class_type)
    
    def _toggle_visibility(self):
        """Toggle visibility and update icon."""
        self.is_visible = not self.is_visible
        self.visibility_btn.setText("\ue0be" if self.is_visible else "\ue0bf")
        
        class_type = self.class_combo.currentText()
        color_hex = CLASS_TYPES.get(class_type, CLASS_TYPES['None'])['hex']
        
        self.visibility_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {color_hex if self.is_visible else '#555555'};
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-radius: 3px;
            }}
        """)
        self.visibility_toggled.emit(self.annotation, self.is_visible)
    
    def _on_delete_clicked(self):
        self.delete_clicked.emit(self.annotation)


class LayerPanelWidget(QWidget):
    """Right panel displaying annotation layers with professional table-style UI."""
    
    annotation_deleted = Signal(object)
    annotation_selected = Signal(object)
    visibility_changed = Signal(object, bool)
    class_type_changed = Signal(object, str)  # annotation, new_class_type
    collapse_requested = Signal()  # Signal to request panel collapse
    
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide2.QtWidgets import QVBoxLayout, QScrollArea, QLabel, QPushButton
        
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        
        # Header with title and count
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_label = QLabel("LAYERS")
        header_label.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        self.count_label = QLabel("0 items")
        self.count_label.setStyleSheet("color: #888888; font-size: 11px;")
        header_layout.addWidget(self.count_label)
        
        main_layout.addLayout(header_layout)
        
        # Separator
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #3e3e42;")
        main_layout.addWidget(separator)
        
        # Column header row (table header style)
        column_header = QWidget()
        column_header.setFixedHeight(24)
        column_layout = QHBoxLayout(column_header)
        column_layout.setContentsMargins(8, 0, 8, 0)
        column_layout.setSpacing(6)
        
        # Header: Global visibility toggle
        self.global_visibility_btn = QPushButton("\ue0be")  # eye icon
        self.global_visibility_btn.setFixedSize(24, 20)
        self.global_visibility_btn.setFont(QFont("lucide", 10))
        self.global_visibility_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666666;
            }
            QPushButton:hover {
                color: #00ffff;
            }
        """)
        self.global_visibility_btn.setCursor(Qt.PointingHandCursor)
        self.global_visibility_btn.clicked.connect(self._toggle_all_visibility)
        column_layout.addWidget(self.global_visibility_btn)
        
        # Header: Shape icon column
        icon_header = QLabel("\ue4fe")  # blocks icon
        icon_header.setFont(QFont("lucide", 10))
        icon_header.setStyleSheet("color: #666666;")
        icon_header.setFixedWidth(24)
        icon_header.setAlignment(Qt.AlignCenter)
        column_layout.addWidget(icon_header)
        
        # Header: Label column
        label_header = QLabel("Label")
        label_header.setFixedWidth(60)
        label_header.setStyleSheet("color: #666666; font-size: 10px;")
        label_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        column_layout.addWidget(label_header)
        
        # Header: Class column
        class_header = QLabel("Class")
        class_header.setFixedWidth(90)
        class_header.setStyleSheet("color: #666666; font-size: 10px;")
        class_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        column_layout.addWidget(class_header)
        
        # Header: Info column (fixed 30px to match item)
        info_header = QLabel("Info")
        info_header.setFixedWidth(30)
        info_header.setStyleSheet("color: #666666; font-size: 10px;")
        info_header.setAlignment(Qt.AlignCenter)
        column_layout.addWidget(info_header)
        
        # Header: Clear all button
        self.clear_all_btn = QPushButton("\ue18d")  # trash-2 icon
        self.clear_all_btn.setFixedSize(24, 20)
        self.clear_all_btn.setFont(QFont("lucide", 10))
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666666;
            }
            QPushButton:hover {
                background-color: #ff5555;
                border-radius: 3px;
                color: #ffffff;
            }
        """)
        self.clear_all_btn.setCursor(Qt.PointingHandCursor)
        self.clear_all_btn.clicked.connect(self._on_clear_clicked)
        column_layout.addWidget(self.clear_all_btn)
        
        main_layout.addWidget(column_header)
        
        self.all_visible = True  # Track global visibility state
        
        # Scrollable area for items
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2d2d30;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
        """)
        
        # Container for items
        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)  # No margin, layout matches control row
        self.items_layout.setSpacing(4)
        self.items_layout.addStretch()
        
        scroll_area.setWidget(self.items_container)
        main_layout.addWidget(scroll_area, 1)
        
        self.annotations = []
        self.item_widgets = {}
    
    def add_annotation(self, annotation):
        """Add an annotation to the list."""
        self.annotations.append(annotation)
        
        # Create custom item widget
        item_widget = LayerItemWidget(annotation)
        item_widget.visibility_toggled.connect(self._on_visibility_toggled)
        item_widget.delete_clicked.connect(self._on_delete_item)
        item_widget.class_changed.connect(self._on_class_changed)
        
        # Insert before the stretch
        self.items_layout.insertWidget(self.items_layout.count() - 1, item_widget)
        self.item_widgets[annotation] = item_widget
        
        self._update_count()
    
    def remove_annotation(self, annotation):
        """Remove an annotation from the list."""
        if annotation in self.annotations:
            self.annotations.remove(annotation)
        
        if annotation in self.item_widgets:
            widget = self.item_widgets.pop(annotation)
            self.items_layout.removeWidget(widget)
            widget.deleteLater()
        
        self._update_count()
    
    def clear_all(self):
        """Clear all annotations."""
        for annotation in self.annotations[:]:
            self.annotation_deleted.emit(annotation)
        
        self.annotations.clear()
        for widget in self.item_widgets.values():
            self.items_layout.removeWidget(widget)
            widget.deleteLater()
        self.item_widgets.clear()
        
        self._update_count()
    
    def _update_count(self):
        """Update count label."""
        count = len(self.annotations)
        self.count_label.setText(f"{count} item{'s' if count != 1 else ''}")
    
    def _on_visibility_toggled(self, annotation, visible):
        """Handle visibility toggle."""
        annotation.visible = visible
        self.visibility_changed.emit(annotation, visible)
    
    def _on_delete_item(self, annotation):
        """Handle delete from item widget."""
        self.annotation_deleted.emit(annotation)
        self.remove_annotation(annotation)
    
    def _on_clear_clicked(self):
        """Handle clear all button click."""
        self.clear_all()
    
    def _on_class_changed(self, annotation, class_type):
        """Handle class type change from item widget."""
        annotation.set_class_type(class_type)
        self.class_type_changed.emit(annotation, class_type)
    
    def _toggle_all_visibility(self):
        """Toggle visibility of all annotations."""
        self.all_visible = not self.all_visible
        
        # Update header button icon
        self.global_visibility_btn.setText("\ue0be" if self.all_visible else "\ue0bf")
        self.global_visibility_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: """ + ("#00ffff" if self.all_visible else "#555555") + """;
            }
            QPushButton:hover {
                color: """ + ("#00ffff" if self.all_visible else "#888888") + """;
            }
        """)
        
        # Toggle all item widgets
        for annotation, widget in self.item_widgets.items():
            widget.is_visible = self.all_visible
            widget.visibility_btn.setText("\ue0be" if self.all_visible else "\ue0bf")
            
            class_type = widget.class_combo.currentText()
            color_hex = CLASS_TYPES.get(class_type, CLASS_TYPES['None'])['hex']
            
            widget.visibility_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    color: {color_hex if self.all_visible else '#555555'};
                }}
                QPushButton:hover {{
                    background-color: #3e3e42;
                    border-radius: 3px;
                }}
            """)
            annotation.visible = self.all_visible
            self.visibility_changed.emit(annotation, self.all_visible)
