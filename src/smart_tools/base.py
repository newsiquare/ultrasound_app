"""
Base utilities for smart clinical tools.

Provides shared functionality for image processing and coordinate handling.
"""

import numpy as np
from typing import Tuple, Optional
from collections import OrderedDict


class FrameCache:
    """
    Simple LRU cache for recently grabbed frames.
    
    Helps avoid repeated frame grabs from FrameTapProcessor.
    """
    
    def __init__(self, max_size: int = 5):
        self._cache = OrderedDict()
        self._max_size = max_size
    
    def get(self, frame_id: int) -> Optional[np.ndarray]:
        """Get frame from cache if available."""
        if frame_id in self._cache:
            # Move to end (most recent)
            self._cache.move_to_end(frame_id)
            return self._cache[frame_id]
        return None
    
    def put(self, frame_id: int, frame: np.ndarray):
        """Add frame to cache."""
        if frame_id in self._cache:
            self._cache.move_to_end(frame_id)
        else:
            self._cache[frame_id] = frame
            if len(self._cache) > self._max_size:
                # Remove oldest
                self._cache.popitem(last=False)
    
    def clear(self):
        """Clear all cached frames."""
        self._cache.clear()


def extract_roi(frame: np.ndarray, center_x: int, center_y: int, 
                width: int, height: int, 
                pad_value: int = 0) -> Tuple[np.ndarray, int, int]:
    """
    Extract a region of interest (ROI) from frame, handling boundary cases.
    
    Args:
        frame: Source image (H, W) grayscale
        center_x, center_y: Center of ROI in image coordinates
        width, height: Size of ROI to extract
        pad_value: Value to use for out-of-bounds pixels
    
    Returns:
        Tuple of (roi_image, offset_x, offset_y)
        - roi_image: Extracted region (height, width)
        - offset_x, offset_y: Offset of ROI top-left in original frame
    """
    h, w = frame.shape[:2]
    
    # Calculate ROI bounds
    half_w = width // 2
    half_h = height // 2
    
    x1 = center_x - half_w
    y1 = center_y - half_h
    x2 = x1 + width
    y2 = y1 + height
    
    # Create output ROI
    roi = np.full((height, width), pad_value, dtype=frame.dtype)
    
    # Calculate valid intersection with frame
    src_x1 = max(0, x1)
    src_y1 = max(0, y1)
    src_x2 = min(w, x2)
    src_y2 = min(h, y2)
    
    dst_x1 = src_x1 - x1
    dst_y1 = src_y1 - y1
    dst_x2 = dst_x1 + (src_x2 - src_x1)
    dst_y2 = dst_y1 + (src_y2 - src_y1)
    
    # Copy valid region
    if src_x2 > src_x1 and src_y2 > src_y1:
        roi[dst_y1:dst_y2, dst_x1:dst_x2] = frame[src_y1:src_y2, src_x1:src_x2]
    
    return roi, x1, y1


def compute_sobel_gradient(frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute Sobel gradients and magnitude.
    
    Args:
        frame: Grayscale image (H, W)
    
    Returns:
        Tuple of (gradient_x, gradient_y, magnitude)
        - gradient_x: Horizontal gradient (detects vertical edges)
        - gradient_y: Vertical gradient (detects horizontal edges)
        - magnitude: Gradient magnitude sqrt(gx^2 + gy^2)
    """
    # Sobel kernels
    sobel_x = np.array([[-1, 0, 1],
                        [-2, 0, 2],
                        [-1, 0, 1]], dtype=np.float32)
    
    sobel_y = np.array([[-1, -2, -1],
                        [ 0,  0,  0],
                        [ 1,  2,  1]], dtype=np.float32)
    
    # Convert to float for gradient computation
    frame_float = frame.astype(np.float32)
    
    # Apply convolution (simplified - assumes valid boundary handling)
    from scipy.ndimage import convolve
    gx = convolve(frame_float, sobel_x)
    gy = convolve(frame_float, sobel_y)
    
    # Compute magnitude
    magnitude = np.sqrt(gx**2 + gy**2)
    
    return gx, gy, magnitude


def magnify_image(image: np.ndarray, scale: int, 
                  method: str = 'nearest') -> np.ndarray:
    """
    Magnify image by integer scale factor.
    
    Args:
        image: Input image (H, W) or (H, W, C)
        scale: Magnification factor (e.g., 4 for 4x)
        method: Interpolation method ('nearest' or 'bilinear')
    
    Returns:
        Magnified image (H*scale, W*scale)
    """
    if scale <= 1:
        return image
    
    h, w = image.shape[:2]
    new_h, new_w = h * scale, w * scale
    
    if method == 'nearest':
        # Nearest neighbor (fastest, preserves pixel values)
        return np.repeat(np.repeat(image, scale, axis=0), scale, axis=1)
    
    elif method == 'bilinear':
        # Bilinear interpolation (smoother but slower)
        from scipy.ndimage import zoom
        if image.ndim == 2:
            return zoom(image, scale, order=1)
        else:
            return zoom(image, (scale, scale, 1), order=1)
    
    else:
        raise ValueError(f"Unknown interpolation method: {method}")


def distance_squared(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Compute squared Euclidean distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return dx * dx + dy * dy


def is_point_in_bounds(x: int, y: int, width: int, height: int) -> bool:
    """Check if point is within image bounds."""
    return 0 <= x < width and 0 <= y < height
