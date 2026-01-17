"""
Annotation system for ultrasound imaging software.

This module provides annotation tools for drawing and measuring on ultrasound images:
- Line, Rectangle, Circle, Freeform shapes
- Measurements (width, height, area, length)
- Annotation overlay widget for drawing
"""

from PySide2.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                                QPushButton, QCheckBox, QScrollArea, QSizePolicy)
from PySide2.QtCore import Qt, QPoint, QRect, Signal
from PySide2.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath
import math


class Annotation:
    """Base class for all annotations."""
    
    _id_counter = 0
    
    def __init__(self, color=QColor(0, 255, 255)):  # Cyan color
        Annotation._id_counter += 1
        self.id = Annotation._id_counter
        self.color = color
        self.points = []
        self.completed = False
        self.selected = False
        self.visible = True  # For layer panel visibility toggle
    
    def add_point(self, point):
        """Add a point to the annotation."""
        self.points.append(point)
    
    def update_last_point(self, point):
        """Update the last point (for dragging)."""
        if self.points:
            self.points[-1] = point
    
    def complete(self):
        """Mark annotation as complete."""
        self.completed = True
    
    def draw(self, painter):
        """Draw the annotation. Override in subclasses."""
        raise NotImplementedError
    
    def get_measurements(self):
        """Return measurements dict. Override in subclasses."""
        return {}
    
    def get_name(self):
        """Return annotation name for layer panel."""
        return f"Annotation {self.id}"
    
    def get_bounding_rect(self):
        """Return bounding rectangle."""
        if len(self.points) < 2:
            return QRect()
        x_coords = [p.x() for p in self.points]
        y_coords = [p.y() for p in self.points]
        return QRect(min(x_coords), min(y_coords), 
                     max(x_coords) - min(x_coords),
                     max(y_coords) - min(y_coords))


class LineAnnotation(Annotation):
    """Line annotation with length measurement."""
    
    def draw(self, painter):
        if len(self.points) < 2:
            return
        
        pen = QPen(self.color, 2 if not self.selected else 3)
        painter.setPen(pen)
        painter.drawLine(self.points[0], self.points[1])
        
        # Draw measurement label
        if self.completed:
            self._draw_measurement(painter)
    
    def _draw_measurement(self, painter):
        if len(self.points) < 2:
            return
        length = self._calculate_length()
        mid = QPoint((self.points[0].x() + self.points[1].x()) // 2,
                     (self.points[0].y() + self.points[1].y()) // 2 - 10)
        
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(Qt.white))
        painter.drawText(mid, f"L: {length:.1f}px")
    
    def _calculate_length(self):
        if len(self.points) < 2:
            return 0
        dx = self.points[1].x() - self.points[0].x()
        dy = self.points[1].y() - self.points[0].y()
        return math.sqrt(dx*dx + dy*dy)
    
    def get_measurements(self):
        return {"Length": f"{self._calculate_length():.1f}px"}
    
    def get_name(self):
        return f"Line {self.id}"


class RectAnnotation(Annotation):
    """Rectangle annotation with width, height, area measurements."""
    
    def draw(self, painter):
        if len(self.points) < 2:
            return
        
        pen = QPen(self.color, 2 if not self.selected else 3)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(0, 255, 255, 30)))  # Semi-transparent fill
        
        rect = QRect(self.points[0], self.points[1]).normalized()
        painter.drawRect(rect)
        
        # Draw measurement label
        if self.completed:
            self._draw_measurement(painter, rect)
    
    def _draw_measurement(self, painter, rect):
        w = rect.width()
        h = rect.height()
        area = w * h
        
        label_pos = QPoint(rect.left(), rect.top() - 5)
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(Qt.white))
        painter.drawText(label_pos, f"W:{w} H:{h} A:{area}")
    
    def get_measurements(self):
        if len(self.points) < 2:
            return {}
        rect = QRect(self.points[0], self.points[1]).normalized()
        w, h = rect.width(), rect.height()
        return {
            "Width": f"{w}px",
            "Height": f"{h}px",
            "Area": f"{w * h}px²"
        }
    
    def get_name(self):
        return f"Rectangle {self.id}"


class CircleAnnotation(Annotation):
    """Circle annotation with radius and area measurements."""
    
    def draw(self, painter):
        if len(self.points) < 2:
            return
        
        pen = QPen(self.color, 2 if not self.selected else 3)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(0, 255, 255, 30)))
        
        center = self.points[0]
        radius = self._calculate_radius()
        
        painter.drawEllipse(center, radius, radius)
        
        if self.completed:
            self._draw_measurement(painter, center, radius)
    
    def _calculate_radius(self):
        if len(self.points) < 2:
            return 0
        dx = self.points[1].x() - self.points[0].x()
        dy = self.points[1].y() - self.points[0].y()
        return int(math.sqrt(dx*dx + dy*dy))
    
    def _draw_measurement(self, painter, center, radius):
        area = math.pi * radius * radius
        label_pos = QPoint(center.x(), center.y() - radius - 10)
        
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(Qt.white))
        painter.drawText(label_pos, f"R:{radius} A:{area:.0f}")
    
    def get_measurements(self):
        radius = self._calculate_radius()
        area = math.pi * radius * radius
        return {
            "Radius": f"{radius}px",
            "Area": f"{area:.1f}px²"
        }
    
    def get_name(self):
        return f"Circle {self.id}"


class FreeformAnnotation(Annotation):
    """Freeform drawing annotation."""
    
    def draw(self, painter):
        if len(self.points) < 2:
            return
        
        pen = QPen(self.color, 2 if not self.selected else 3)
        painter.setPen(pen)
        
        path = QPainterPath()
        path.moveTo(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        
        painter.drawPath(path)
    
    def get_measurements(self):
        # Calculate approximate length
        length = 0
        for i in range(1, len(self.points)):
            dx = self.points[i].x() - self.points[i-1].x()
            dy = self.points[i].y() - self.points[i-1].y()
            length += math.sqrt(dx*dx + dy*dy)
        return {"Length": f"{length:.1f}px"}
    
    def get_name(self):
        return f"Freeform {self.id}"


class AnnotationOverlay(QWidget):
    """Transparent overlay widget for drawing annotations on top of the image."""
    
    annotation_added = Signal(object)  # Emitted when annotation is completed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        self.annotations = []
        self.current_annotation = None
        self.current_tool = None
        self.is_drawing = False
    
    def set_tool(self, tool_type):
        """Set the current annotation tool."""
        self.current_tool = tool_type
    
    def paintEvent(self, event):
        """Draw all annotations."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw completed annotations (only if visible)
        for annotation in self.annotations:
            if annotation.visible:
                annotation.draw(painter)
        
        # Draw current annotation being drawn
        if self.current_annotation:
            self.current_annotation.draw(painter)
    
    def mousePressEvent(self, event):
        """Start drawing annotation."""
        if event.button() != Qt.LeftButton or not self.current_tool:
            return
        
        self.is_drawing = True
        pos = event.pos()
        
        # Create new annotation based on tool type
        if self.current_tool == 'line':
            self.current_annotation = LineAnnotation()
        elif self.current_tool == 'rectangle':
            self.current_annotation = RectAnnotation()
        elif self.current_tool == 'circle':
            self.current_annotation = CircleAnnotation()
        elif self.current_tool == 'freeform':
            self.current_annotation = FreeformAnnotation()
        
        if self.current_annotation:
            self.current_annotation.add_point(pos)
            self.current_annotation.add_point(pos)  # Add second point for dragging
        
        self.update()
    
    def mouseMoveEvent(self, event):
        """Update annotation while dragging."""
        if not self.is_drawing or not self.current_annotation:
            return
        
        pos = event.pos()
        
        if self.current_tool == 'freeform':
            # For freeform, add points continuously
            self.current_annotation.add_point(pos)
        else:
            # For other shapes, update the last point
            self.current_annotation.update_last_point(pos)
        
        self.update()
    
    def mouseReleaseEvent(self, event):
        """Complete the annotation."""
        if event.button() != Qt.LeftButton or not self.is_drawing:
            return
        
        self.is_drawing = False
        
        if self.current_annotation:
            self.current_annotation.complete()
            self.annotations.append(self.current_annotation)
            self.annotation_added.emit(self.current_annotation)
            self.current_annotation = None
        
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


class LayerItemWidget(QWidget):
    """Custom widget for each annotation layer item."""
    
    visibility_toggled = Signal(object, bool)
    delete_clicked = Signal(object)
    
    def __init__(self, annotation, parent=None):
        super().__init__(parent)
        
        self.annotation = annotation
        self.is_visible = True
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        
        # Visibility toggle button (Lucide icons)
        self.visibility_btn = QPushButton("\ue0be")  # eye icon
        self.visibility_btn.setFixedSize(24, 24)
        self.visibility_btn.setFont(QFont("lucide", 14))
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
        
        # Shape icon (Lucide icons)
        icons = {
            'Line': '\ue11f',        # minus
            'Rectangle': '\ue379',   # rectangle-horizontal
            'Circle': '\ue07a',      # circle
            'Freeform': '\ue1f8'     # pencil
        }
        name = annotation.get_name()
        shape_type = name.split()[0] if name else 'Shape'
        icon = icons.get(shape_type, '\ue07a')
        
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("lucide", 14))
        icon_label.setStyleSheet("color: #00ffff;")
        icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)
        
        # Name and measurements (can shrink when panel is narrowed)
        info_container = QWidget()
        info_container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_layout = QVBoxLayout(info_container)
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        info_layout.addWidget(name_label)
        
        measurements = annotation.get_measurements()
        measure_text = " | ".join([f"{k}:{v}" for k, v in measurements.items()])
        measure_label = QLabel(measure_text)
        measure_label.setStyleSheet("color: #888888; font-size: 10px;")
        info_layout.addWidget(measure_label)
        
        layout.addWidget(info_container, 1)  # stretch=1, same as control row
        
        # Delete button (QPushButton for consistent rendering with control row)
        self.delete_btn = QPushButton("\ue18d")  # trash-2 icon
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setFont(QFont("lucide", 14))
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #888888;
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
        
        self.setStyleSheet("""
            LayerItemWidget {
                background-color: #2d2d30;
                border-radius: 4px;
            }
            LayerItemWidget:hover {
                background-color: #3e3e42;
            }
        """)
    
    def _toggle_visibility(self):
        """Toggle visibility and update icon."""
        self.is_visible = not self.is_visible
        # Lucide icons: e0be = eye, e0bf = eye-off
        self.visibility_btn.setText("\ue0be" if self.is_visible else "\ue0bf")
        self.visibility_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: """ + ("#00ffff" if self.is_visible else "#555555") + """;
            }
        """)
        self.visibility_toggled.emit(self.annotation, self.is_visible)
    
    def _on_delete_clicked(self):
        self.delete_clicked.emit(self.annotation)


class LayerPanelWidget(QWidget):
    """Right panel displaying annotation layers with professional UI."""
    
    annotation_deleted = Signal(object)
    annotation_selected = Signal(object)
    visibility_changed = Signal(object, bool)
    collapse_requested = Signal()  # Signal to request panel collapse
    
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide2.QtWidgets import QVBoxLayout, QScrollArea, QLabel, QPushButton
        
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header with title and count (simplified)
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
        
        # Control row: use SAME layout structure as LayerItemWidget for alignment
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 6, 8, 6)  # Same as item
        control_layout.setSpacing(8)  # Same as item
        
        # 1. Global visibility toggle button (same position as item eye)
        self.global_visibility_btn = QPushButton("\ue0be")  # eye icon
        self.global_visibility_btn.setFixedSize(24, 24)
        self.global_visibility_btn.setFont(QFont("lucide", 14))
        self.global_visibility_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #888888;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-radius: 3px;
            }
        """)
        self.global_visibility_btn.setCursor(Qt.PointingHandCursor)
        self.global_visibility_btn.clicked.connect(self._toggle_all_visibility)
        control_layout.addWidget(self.global_visibility_btn)
        
        # 2. Blocks icon for shape indicator
        spacer_icon = QLabel("\ue4fe")  # blocks icon
        spacer_icon.setFont(QFont("lucide", 14))
        spacer_icon.setStyleSheet("color: #888888;")
        spacer_icon.setFixedWidth(24)
        control_layout.addWidget(spacer_icon)
        
        # 3. Label info text (same position as item info_container)
        label_info = QLabel("Label info")
        label_info.setStyleSheet("color: #888888; font-size: 11px;")
        control_layout.addWidget(label_info, 1)
        
        # 4. Clear all button (same position as item trash)
        self.clear_all_btn = QPushButton("\ue18d")  # trash-2 icon
        self.clear_all_btn.setFixedSize(24, 24)
        self.clear_all_btn.setFont(QFont("lucide", 14))
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #888888;
            }
            QPushButton:hover {
                background-color: #ff5555;
                border-radius: 3px;
                color: #ffffff;
            }
        """)
        self.clear_all_btn.setCursor(Qt.PointingHandCursor)
        self.clear_all_btn.clicked.connect(self._on_clear_clicked)
        control_layout.addWidget(self.clear_all_btn)
        
        main_layout.addLayout(control_layout)
        
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
                background-color: #3e3e42;
                border-radius: 3px;
            }
        """)
        
        # Toggle all item widgets
        for annotation, widget in self.item_widgets.items():
            widget.is_visible = self.all_visible
            widget.visibility_btn.setText("\ue0be" if self.all_visible else "\ue0bf")
            widget.visibility_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    color: """ + ("#00ffff" if self.all_visible else "#555555") + """;
                }
            """)
            annotation.visible = self.all_visible
            self.visibility_changed.emit(annotation, self.all_visible)
