"""
Precision Loupe - Floating Picture-in-Picture Magnifier

Provides a frameless floating window that displays a magnified view
of the area under the cursor for pixel-perfect measurements.
"""

import numpy as np
from PySide2.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide2.QtCore import Qt, QSize, QPoint
from PySide2.QtGui import QPainter, QPen, QColor, QImage, QPixmap, QFont
from typing import Optional, Tuple

from .base import extract_roi, magnify_image


class MagnifierWidget(QWidget):
    """
    Floating Picture-in-Picture magnifier widget.
    
    Features:
    - Extracts 32x32 pixel region from current frame
    - Displays 4x magnification (128x128 output)
    - Crosshair overlay for precise alignment
    - Pixel value display at center point
    - Frameless, always-on-top floating window
    """
    
    def __init__(self, parent=None, roi_size: int = 32, magnification: int = 4):
        """
        Initialize magnifier widget.
        
        Args:
            parent: Parent widget
            roi_size: Size of region to extract (pixels)
            magnification: Magnification factor (e.g., 4 for 4x)
        """
        super().__init__(parent)
        
        self.roi_size = roi_size
        self.magnification = magnification
        self.display_size = roi_size * magnification
        
        # Current magnified view
        self._magnified_image = None
        self._center_pixel_value = None
        
        # Setup UI
        self.setWindowFlags(
            Qt.Tool |  # Tool window (doesn't show in taskbar)
            Qt.FramelessWindowHint |  # No window frame
            Qt.WindowStaysOnTopHint |  # Always on top
            Qt.X11BypassWindowManagerHint  # Bypass WM for positioning
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.display_size + 20, self.display_size + 40)  # Add padding for border and text
        
        # Start hidden
        self.hide()
    
    def update_view(self, frame: np.ndarray, center_x: int, center_y: int):
        """
        Update magnifier view with new frame and center position.
        
        Args:
            frame: Source image (H, W) grayscale uint8
            center_x, center_y: Center position in image coordinates
        """
        if frame is None or frame.size == 0:
            self._magnified_image = None
            self._center_pixel_value = None
            return
        
        # Extract ROI around cursor
        roi, offset_x, offset_y = extract_roi(
            frame, 
            int(center_x), 
            int(center_y),
            self.roi_size, 
            self.roi_size,
            pad_value=0
        )
        
        # Get pixel value at center
        center_roi_y = self.roi_size // 2
        center_roi_x = self.roi_size // 2
        if 0 <= center_roi_y < roi.shape[0] and 0 <= center_roi_x < roi.shape[1]:
            self._center_pixel_value = int(roi[center_roi_y, center_roi_x])
        else:
            self._center_pixel_value = None
        
        # Magnify using nearest neighbor to preserve pixel grid
        magnified = magnify_image(roi, self.magnification, method='nearest')
        
        # Store for painting
        self._magnified_image = magnified
        
        # Trigger repaint
        self.update()
    
    def paintEvent(self, event):
        """Paint magnified view with crosshair and pixel value."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), QColor(40, 40, 40, 220))
        
        if self._magnified_image is not None:
            # Convert numpy array to QImage
            h, w = self._magnified_image.shape
            bytes_per_line = w
            
            # Create QImage from grayscale data
            qimage = QImage(
                self._magnified_image.data,
                w, h,
                bytes_per_line,
                QImage.Format_Grayscale8
            )
            
            # Draw image centered with padding
            x_offset = 10
            y_offset = 10
            painter.drawImage(x_offset, y_offset, qimage)
            
            # Draw border around image
            border_rect = self.rect().adjusted(
                x_offset - 1, 
                y_offset - 1,
                -(self.width() - w - x_offset) - 1,
                -(self.height() - h - y_offset) - 1
            )
            painter.setPen(QPen(QColor(0, 255, 255), 2))  # Cyan border
            painter.drawRect(border_rect)
            
            # Draw crosshair at center
            center_x = x_offset + w // 2
            center_y = y_offset + h // 2
            crosshair_length = 10
            
            painter.setPen(QPen(QColor(255, 0, 0, 200), 1))  # Red crosshair
            # Horizontal line
            painter.drawLine(
                center_x - crosshair_length, center_y,
                center_x + crosshair_length, center_y
            )
            # Vertical line
            painter.drawLine(
                center_x, center_y - crosshair_length,
                center_x, center_y + crosshair_length
            )
            
            # Draw pixel value if available
            if self._center_pixel_value is not None:
                text = f"Value: {self._center_pixel_value}"
                font = QFont("Arial", 10, QFont.Bold)
                painter.setFont(font)
                
                # Draw text at bottom
                text_y = y_offset + h + 15
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(10, text_y, text)
        
        else:
            # No image - show placeholder
            painter.setPen(QColor(150, 150, 150))
            font = QFont("Arial", 9)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "No image")
        
        painter.end()
    
    def position_near_cursor(self, cursor_widget_pos: QPoint, offset_x: int = 20, offset_y: int = 20):
        """
        Position magnifier near cursor with offset to avoid covering measurement point.
        
        Args:
            cursor_widget_pos: Cursor position in widget coordinates
            offset_x, offset_y: Offset from cursor (pixels)
        """
        # Convert widget position to global screen coordinates
        if self.parent():
            global_pos = self.parent().mapToGlobal(cursor_widget_pos)
        else:
            global_pos = cursor_widget_pos
        
        # Position with offset
        new_x = global_pos.x() + offset_x
        new_y = global_pos.y() + offset_y
        
        # Keep on screen (simple boundary check)
        # TODO: Add screen boundary detection if needed
        
        self.move(new_x, new_y)
