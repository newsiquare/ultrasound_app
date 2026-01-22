"""
Auto-Trace - Automatic region growing and contour extraction

Implements region growing algorithm to automatically trace closed
contours (e.g., cysts, ventricles) from a single seed point.
"""

import numpy as np
from typing import List, Tuple, Optional, Set
from collections import deque

from .base import is_point_in_bounds


class RegionGrowingTracer:
    """
    Automatic contour tracing using region growing algorithm.
    
    Parameters:
    - tolerance: Max pixel intensity difference for region inclusion (default: 15)
    - min_area: Minimum region area to consider (pixels)
    - max_area: Maximum region area to prevent runaway growth
    """
    
    def __init__(self, tolerance: int = 15, min_area: int = 50, max_area: int = 100000):
        """
        Initialize region growing tracer.
        
        Args:
            tolerance: Maximum intensity difference from seed for inclusion
            min_area: Minimum region area in pixels
            max_area: Maximum region area in pixels (safety limit)
        """
        self.tolerance = tolerance
        self.min_area = min_area
        self.max_area = max_area
    
    def set_tolerance(self, tolerance: int):
        """Set tolerance for region growing."""
        self.tolerance = max(1, min(100, tolerance))  # Clamp 1-100
    
    def trace_region(self, frame: np.ndarray, seed_point: Tuple[int, int],
                     tolerance: Optional[int] = None) -> Optional[List[Tuple[int, int]]]:
        """
        Grow region from seed point and extract boundary.
        
        Args:
            frame: Grayscale image (H, W)
            seed_point: Starting point (x, y) in image coordinates
            tolerance: Override default tolerance if provided
        
        Returns:
            List of boundary points [(x1,y1), (x2,y2), ...] as polygon,
            or None if region is invalid
        """
        if frame is None or frame.size == 0:
            return None
        
        if tolerance is None:
            tolerance = self.tolerance
        
        seed_x, seed_y = seed_point
        h, w = frame.shape[:2]
        
        # Check if seed point is valid
        if not is_point_in_bounds(seed_x, seed_y, w, h):
            return None
        
        # Get seed intensity value
        seed_value = float(frame[seed_y, seed_x])
        
        # Region growing using flood fill
        region_mask = np.zeros((h, w), dtype=bool)
        visited = set()
        queue = deque([(seed_x, seed_y)])
        
        while queue and len(visited) < self.max_area:
            current_x, current_y = queue.popleft()
            
            # Skip if already visited
            if (current_x, current_y) in visited:
                continue
            
            # Check bounds
            if not is_point_in_bounds(current_x, current_y, w, h):
                continue
            
            # Check intensity difference
            current_value = float(frame[current_y, current_x])
            if abs(current_value - seed_value) > tolerance:
                continue
            
            # Add to region
            visited.add((current_x, current_y))
            region_mask[current_y, current_x] = True
            
            # Add 4-connected neighbors to queue
            neighbors = [
                (current_x + 1, current_y),      # Right
                (current_x - 1, current_y),      # Left
                (current_x, current_y + 1),      # Down
                (current_x, current_y - 1),      # Up
            ]
            
            for nx, ny in neighbors:
                if (nx, ny) not in visited:
                    queue.append((nx, ny))
        
        # Check if region is too small or too large
        region_area = len(visited)
        if region_area < self.min_area or region_area > self.max_area:
            return None
        
        # Extract boundary contour
        boundary_points = self._extract_boundary(region_mask)
        
        if boundary_points is None or len(boundary_points) < 3:
            return None
        
        # Simplify contour (reduce number of points)
        simplified = self._simplify_contour(boundary_points, epsilon=2.0)
        
        return simplified
    
    def _extract_boundary(self, region_mask: np.ndarray) -> Optional[List[Tuple[int, int]]]:
        """
        Extract boundary points from region mask.
        
        Args:
            region_mask: Boolean mask of region
        
        Returns:
            List of boundary points in order, or None if extraction fails
        """
        try:
            # Use opencv for contour detection if available
            import cv2
            
            # Convert boolean mask to uint8
            mask_uint8 = region_mask.astype(np.uint8) * 255
            
            # Find contours
            contours, _ = cv2.findContours(
                mask_uint8,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_NONE
            )
            
            if len(contours) == 0:
                return None
            
            # Get largest contour (should be the only external one)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Convert to list of (x, y) tuples
            boundary_points = [(int(pt[0][0]), int(pt[0][1])) for pt in largest_contour]
            
            return boundary_points
        
        except ImportError:
            # Fallback: simple boundary walk if opencv not available
            return self._extract_boundary_simple(region_mask)
    
    def _extract_boundary_simple(self, region_mask: np.ndarray) -> Optional[List[Tuple[int, int]]]:
        """
        Simple boundary extraction without opencv (fallback).
        
        Finds pixels in region that have at least one neighbor outside region.
        """
        h, w = region_mask.shape
        boundary_points = []
        
        for y in range(h):
            for x in range(w):
                if not region_mask[y, x]:
                    continue
                
                # Check if any 4-connected neighbor is outside region
                is_boundary = False
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    nx, ny = x + dx, y + dy
                    if not is_point_in_bounds(nx, ny, w, h) or not region_mask[ny, nx]:
                        is_boundary = True
                        break
                
                if is_boundary:
                    boundary_points.append((x, y))
        
        return boundary_points if boundary_points else None
    
    def _simplify_contour(self, points: List[Tuple[int, int]], 
                         epsilon: float = 2.0) -> List[Tuple[int, int]]:
        """
        Simplify contour using Douglas-Peucker algorithm.
        
        Args:
            points: List of contour points
            epsilon: Maximum distance from point to line segment
        
        Returns:
            Simplified contour with fewer points
        """
        try:
            import cv2
            
            # Convert to numpy array format for opencv
            points_array = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
            
            # Apply Douglas-Peucker simplification
            simplified = cv2.approxPolyDP(points_array, epsilon, closed=True)
            
            # Convert back to list of tuples
            return [(int(pt[0][0]), int(pt[0][1])) for pt in simplified]
        
        except ImportError:
            # If opencv not available, just subsample points
            stride = max(1, len(points) // 50)  # Keep ~50 points max
            return points[::stride]
