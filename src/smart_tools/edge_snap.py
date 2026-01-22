"""
Smart Edge Snapping - Gradient-based cursor snapping

Uses Sobel gradients to detect tissue boundaries and automatically
snap the cursor to the nearest edge for precise measurements.
"""

import numpy as np
from typing import Optional, Tuple

from .base import compute_sobel_gradient, extract_roi, is_point_in_bounds


class EdgeSnapDetector:
    """
    Detects edges using Sobel gradients and snaps cursor to nearest edge.
    
    Parameters:
    - snap_radius: Search radius in pixels (default: 15)
    - gradient_threshold: Minimum gradient magnitude to consider as edge (default: 30)
    """
    
    def __init__(self, snap_radius: int = 15, gradient_threshold: float = 30.0):
        """
        Initialize edge snap detector.
        
        Args:
            snap_radius: Maximum distance to search for edges (pixels)
            gradient_threshold: Minimum gradient magnitude for edge detection
        """
        self.snap_radius = snap_radius
        self.gradient_threshold = gradient_threshold
        self._enabled = True
    
    def set_enabled(self, enabled: bool):
        """Enable or disable edge snapping."""
        self._enabled = enabled
    
    def is_enabled(self) -> bool:
        """Check if edge snapping is enabled."""
        return self._enabled
    
    def set_snap_radius(self, radius: int):
        """Set snap radius in pixels."""
        self.snap_radius = max(5, min(50, radius))  # Clamp between 5-50
    
    def set_gradient_threshold(self, threshold: float):
        """Set gradient threshold for edge detection."""
        self.gradient_threshold = max(10.0, threshold)
    
    def find_nearest_edge(self, frame: np.ndarray, cursor_pos: Tuple[int, int],
                         radius: Optional[int] = None) -> Optional[Tuple[int, int]]:
        """
        Find nearest edge within radius of cursor.
        
        Args:
            frame: Grayscale image (H, W)
            cursor_pos: Current cursor position (x, y) in image coordinates
            radius: Search radius (uses self.snap_radius if None)
        
        Returns:
            Snapped position (x, y) or None if no edge found
        """
        if not self._enabled or frame is None:
            return None
        
        if radius is None:
            radius = self.snap_radius
        
        cursor_x, cursor_y = cursor_pos
        
        # Extract ROI around cursor
        roi_size = radius * 2 + 1
        roi, offset_x, offset_y = extract_roi(
            frame,
            cursor_x,
            cursor_y,
            roi_size,
            roi_size,
            pad_value=0
        )
        
        if roi.size == 0:
            return None
        
        # Compute gradients on ROI
        try:
            gx, gy, magnitude = compute_sobel_gradient(roi)
        except Exception:
            # Gradient computation failed
            return None
        
        # Find maximum gradient in ROI
        max_gradient = np.max(magnitude)
        
        if max_gradient < self.gradient_threshold:
            # No significant edge found
            return None
        
        # Find position of maximum gradient
        max_pos = np.unravel_index(np.argmax(magnitude), magnitude.shape)
        edge_y, edge_x = max_pos  # Note: numpy returns (row, col) = (y, x)
        
        # Convert ROI coordinates back to image coordinates
        snapped_x = offset_x + edge_x
        snapped_y = offset_y + edge_y
        
        # Verify snapped position is within frame bounds
        if not is_point_in_bounds(snapped_x, snapped_y, frame.shape[1], frame.shape[0]):
            return None
        
        # Calculate distance from cursor to snapped position
        dx = snapped_x - cursor_x
        dy = snapped_y - cursor_y
        distance_sq = dx * dx + dy * dy
        
        # Only snap if within radius
        if distance_sq <= radius * radius:
            return (snapped_x, snapped_y)
        
        return None
