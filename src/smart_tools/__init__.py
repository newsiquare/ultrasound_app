"""
Smart Clinical Tools Module

Provides intelligent tools for enhanced clinical measurements:
- Precision Loupe: Floating magnifier for pixel-perfect measurements
- Smart Edge Snapping: Gradient-based cursor snapping to tissue boundaries
- Auto-Trace: Region growing algorithm for automatic contour detection
"""

from .magnifier import MagnifierWidget
from .edge_snap import EdgeSnapDetector
from .auto_trace import RegionGrowingTracer

__all__ = [
    'MagnifierWidget',
    'EdgeSnapDetector',
    'RegionGrowingTracer',
]
