"""
FAST-based annotation rendering system.

This module provides annotation rendering using FAST framework's LineRenderer,
VertexRenderer and TextRenderer, enabling annotations to automatically follow
view zoom/pan transformations.

Key components:
- FASTAnnotationManager: Manages FAST renderers for all annotations
- CoordinateConverter: Converts between pixel and world coordinates
"""

import fast
import math
from typing import List, Tuple, Optional, Dict, Any

# Class type colors for annotation rendering (RGB 0-1 range)
CLASS_COLORS = {
    'None': (0.0, 1.0, 1.0),        # Cyan (default)
    'Thrombus': (1.0, 0.42, 0.42),  # Red
    'Plaque': (1.0, 0.85, 0.24),    # Yellow
    'Calcification': (0.42, 0.80, 1.0),  # Blue
}


def to_fast_color(color_tuple: Tuple[float, float, float]) -> fast.Color:
    """Convert RGB tuple (0-1 range) to FAST Color."""
    return fast.Color(color_tuple[0], color_tuple[1], color_tuple[2])


def qcolor_to_tuple(qcolor) -> Tuple[float, float, float]:
    """Convert QColor to RGB tuple (0-1 range)."""
    return (qcolor.redF(), qcolor.greenF(), qcolor.blueF())


class CoordinateConverter:
    """
    Converts between Qt widget coordinates and FAST world coordinates.
    
    In FAST 2D mode:
    - Origin (0,0) is at image top-left
    - FAST automatically scales and centers the image to fit the widget
    - We need to account for this transformation
    """
    
    def __init__(self, image_width: int = 512, image_height: int = 512, 
                 pixel_spacing: float = 1.0):
        """
        Initialize converter.
        
        Args:
            image_width: Image width in pixels (default 512)
            image_height: Image height in pixels (default 512)
            pixel_spacing: Physical size per pixel (mm/pixel), default 1.0
        """
        self.image_width = image_width
        self.image_height = image_height
        self.pixel_spacing = pixel_spacing if pixel_spacing and pixel_spacing > 0 else 1.0
        
        # Widget dimensions (set by set_widget_size)
        self.widget_width = image_width
        self.widget_height = image_height
        
        # Computed transform values
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._update_transform()
    
    def set_image_size(self, width: int, height: int):
        """Update image dimensions."""
        self.image_width = width
        self.image_height = height
        self._update_transform()
    
    def set_widget_size(self, width: int, height: int):
        """Update widget dimensions."""
        self.widget_width = width
        self.widget_height = height
        self._update_transform()
    
    def set_pixel_spacing(self, spacing: float):
        """Update pixel spacing."""
        self.pixel_spacing = spacing if spacing > 0 else 1.0
    
    def _update_transform(self):
        """
        Calculate the transform from widget coords to image coords.
        
        FAST scales the image to fit the widget while maintaining aspect ratio,
        and centers it within the widget.
        """
        if self.image_width <= 0 or self.image_height <= 0:
            return
        if self.widget_width <= 0 or self.widget_height <= 0:
            return
        
        # Calculate scale to fit image in widget (maintain aspect ratio)
        scale_x = self.widget_width / self.image_width
        scale_y = self.widget_height / self.image_height
        self._scale = min(scale_x, scale_y)
        
        # Calculate offset to center the image
        scaled_width = self.image_width * self._scale
        scaled_height = self.image_height * self._scale
        self._offset_x = (self.widget_width - scaled_width) / 2.0
        self._offset_y = (self.widget_height - scaled_height) / 2.0
    
    def widget_to_image(self, wx: float, wy: float) -> Tuple[float, float]:
        """
        Convert widget coordinates to image pixel coordinates.
        
        Args:
            wx: X coordinate in widget pixels
            wy: Y coordinate in widget pixels
            
        Returns:
            (ix, iy) image pixel coordinates
        """
        if self._scale == 0:
            return (wx, wy)
        
        # Remove centering offset, then remove scale
        ix = (wx - self._offset_x) / self._scale
        iy = (wy - self._offset_y) / self._scale
        return (ix, iy)
    
    def pixel_to_world(self, px: float, py: float) -> Tuple[float, float, float]:
        """
        Convert Qt widget coordinates to FAST world coordinates.
        
        This first converts widget coords to image coords, then to world coords.
        
        Args:
            px: X coordinate in widget pixels
            py: Y coordinate in widget pixels
            
        Returns:
            (wx, wy, wz) world coordinates, wz is always 0 for 2D
        """
        # First convert widget coords to image coords
        ix, iy = self.widget_to_image(px, py)
        
        # FAST world coordinates = image pixel coordinates
        return (float(ix), float(iy), 0.0)
    
    def world_to_pixel(self, wx: float, wy: float) -> Tuple[int, int]:
        """
        Convert FAST world coordinates to Qt pixel coordinates.
        
        Args:
            wx: X coordinate in world units
            wy: Y coordinate in world units
            
        Returns:
            (px, py) pixel coordinates
        """
        px = int(wx / self.pixel_spacing)
        py = int(wy / self.pixel_spacing)
        return (px, py)
    
    def format_length(self, pixels: float) -> str:
        """Format length with appropriate unit."""
        if self.pixel_spacing != 1.0:
            mm = pixels * self.pixel_spacing
            return f"{mm:.2f} mm"
        return f"{pixels:.1f} px"
    
    def format_area(self, pixels_sq: float) -> str:
        """Format area with appropriate unit."""
        if self.pixel_spacing != 1.0:
            mm_sq = pixels_sq * (self.pixel_spacing ** 2)
            cm_sq = mm_sq / 100  # mm² to cm²
            return f"{cm_sq:.2f} cm²"
        return f"{pixels_sq:.0f} px²"


class FASTAnnotationManager:
    """
    Manages FAST renderers for annotation visualization.
    
    This class handles:
    - Creating and managing LineRenderer for lines/rectangles/polygons
    - Creating and managing VertexRenderer for annotation endpoints
    - Creating and managing TextRenderer for measurement labels
    - Rebuilding Mesh data when annotations change
    """
    
    # Default colors
    DEFAULT_COLOR = (0.0, 1.0, 1.0)  # Cyan
    SELECTED_COLOR = (1.0, 1.0, 0.0)  # Yellow
    PREVIEW_COLOR = (0.0, 1.0, 1.0)  # Cyan with transparency effect
    
    def __init__(self, fast_view: fast.View):
        """
        Initialize annotation manager.
        
        Args:
            fast_view: The FAST View to add renderers to
        """
        self.view = fast_view
        self.annotations: List[Any] = []  # List of Annotation objects
        self.coord_converter = CoordinateConverter()
        
        # Track current drawing state
        self.preview_points: List[Tuple[float, float]] = []
        self.preview_tool: Optional[str] = None
        
        # FAST Renderers - one LineRenderer per class_type for color support
        self._line_renderers: Dict[str, fast.LineRenderer] = {}  # class_type -> LineRenderer
        self._line_meshes: Dict[str, fast.Mesh] = {}  # class_type -> Mesh
        self._vertex_renderer: Optional[fast.VertexRenderer] = None
        self._text_renderers: Dict[int, fast.TextRenderer] = {}
        
        # Preview renderer (always cyan)
        self._preview_renderer: Optional[fast.LineRenderer] = None
        self._preview_mesh: Optional[fast.Mesh] = None
        
        # Flags
        self._renderers_added = False
        self._needs_update = True
    
    def _get_or_create_renderer(self, class_type: str) -> fast.LineRenderer:
        """Get or create a LineRenderer for the given class type."""
        if class_type not in self._line_renderers:
            color = CLASS_COLORS.get(class_type, CLASS_COLORS['None'])
            renderer = fast.LineRenderer.create(
                fast.Color(color[0], color[1], color[2]), 0.5, True
            )
            self._line_renderers[class_type] = renderer
        return self._line_renderers[class_type]
    
    @property
    def vertex_renderer(self) -> fast.VertexRenderer:
        """Get or create VertexRenderer for endpoints."""
        if self._vertex_renderer is None:
            # Create with 8px size, in pixels, min 4px, cyan, full opacity, drawOnTop
            self._vertex_renderer = fast.VertexRenderer.create(
                8.0, True, 4, fast.Color.Cyan(), 1.0, True
            )
        return self._vertex_renderer
    
    def set_image_info(self, width: int, height: int, pixel_spacing: float = 1.0):
        """
        Set image information for coordinate conversion.
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
            pixel_spacing: Physical size per pixel (mm/pixel)
        """
        self.coord_converter.set_image_size(width, height)
        self.coord_converter.set_pixel_spacing(pixel_spacing)
    
    def ensure_renderer_added(self):
        """
        Ensure the line renderer is added to the view.
        Call this after view.removeAllRenderers() is called.
        """
        try:
            print(f"[FASTAnnotationManager] ensure_renderer_added called, annotations: {len(self.annotations)}")
            # Reset the flag since removeAllRenderers was called
            self._renderers_added = False
            # Force update to redraw existing annotations
            self._needs_update = True
            self.update_renderers()
        except Exception as e:
            print(f"[FASTAnnotationManager] Error in ensure_renderer_added: {e}")
    
    def add_annotation(self, annotation):
        """
        Add an annotation and trigger renderer update.
        
        Args:
            annotation: Annotation object (LineAnnotation, RectAnnotation, etc.)
        """
        print(f"[FASTAnnotationManager] Adding annotation: {type(annotation).__name__}")
        self.annotations.append(annotation)
        self._needs_update = True
        self.update_renderers()
        print(f"[FASTAnnotationManager] Total annotations: {len(self.annotations)}")
    
    def remove_annotation(self, annotation):
        """
        Remove an annotation and trigger renderer update.
        
        Args:
            annotation: Annotation to remove
        """
        if annotation in self.annotations:
            self.annotations.remove(annotation)
            self._needs_update = True
            self.update_renderers()
    
    def clear_all(self):
        """Remove all annotations."""
        self.annotations.clear()
        self._text_renderers.clear()
        self._needs_update = True
        self.update_renderers()
    
    def set_visibility(self, annotation, visible: bool):
        """
        Set annotation visibility.
        
        Args:
            annotation: The annotation to modify
            visible: Whether the annotation should be visible
        """
        annotation.visible = visible
        self._needs_update = True
        self.update_renderers()
    
    def update_annotation(self, annotation):
        """
        Update an annotation (e.g., after color change).
        
        Args:
            annotation: The annotation that was modified
        """
        if annotation in self.annotations:
            self._needs_update = True
            self.update_renderers()
    
    def set_preview(self, tool: str, points: List[Tuple[float, float]]):
        """
        Set preview points for annotation being drawn.
        
        Args:
            tool: Tool type ('line', 'rectangle', 'polygon')
            points: List of (x, y) pixel coordinates
        """
        self.preview_tool = tool
        self.preview_points = points
        self._needs_update = True
        self.update_renderers()
    
    def clear_preview(self):
        """Clear the preview."""
        print(f"[FASTAnnotationManager] clear_preview called, annotations count: {len(self.annotations)}")
        self.preview_tool = None
        self.preview_points = []
        self._needs_update = True
        self.update_renderers()
    
    def update_renderers(self):
        """
        Rebuild meshes and update all renderers.
        
        This is called whenever annotations change.
        Uses separate LineRenderer for each class_type to support per-class colors.
        """
        if not self._needs_update:
            return
        
        print(f"[FASTAnnotationManager] update_renderers: processing {len(self.annotations)} annotations")
        
        # Group annotations by class_type
        annotations_by_class: Dict[str, List[Any]] = {}
        for ann in self.annotations:
            if not ann.visible:
                continue
            class_type = getattr(ann, 'class_type', 'None')
            if class_type not in annotations_by_class:
                annotations_by_class[class_type] = []
            annotations_by_class[class_type].append(ann)
        
        # Remove old renderers
        for class_type, renderer in list(self._line_renderers.items()):
            try:
                self.view.removeRenderer(renderer)
            except Exception:
                pass
        self._line_renderers.clear()
        self._line_meshes.clear()
        
        # Remove old preview renderer
        if self._preview_renderer:
            try:
                self.view.removeRenderer(self._preview_renderer)
            except Exception:
                pass
            self._preview_renderer = None
        
        # Create mesh and renderer for each class_type
        for class_type, anns in annotations_by_class.items():
            vertices = []
            lines = []
            vertex_offset = 0
            
            for ann in anns:
                ann_vertices, ann_lines = self._annotation_to_mesh_data(ann, vertex_offset)
                vertices.extend(ann_vertices)
                lines.extend(ann_lines)
                vertex_offset += len(ann_vertices)
            
            if vertices and lines:
                # Create mesh
                mesh = fast.Mesh.create(vertices, lines, [])
                self._line_meshes[class_type] = mesh
                
                # Create renderer with class color
                color = CLASS_COLORS.get(class_type, CLASS_COLORS['None'])
                renderer = fast.LineRenderer.create(
                    fast.Color(color[0], color[1], color[2]), 0.5, True
                )
                renderer.addInputData(mesh)
                self.view.addRenderer(renderer)
                self._line_renderers[class_type] = renderer
                
                print(f"[FASTAnnotationManager] Created renderer for {class_type}: {len(vertices)} vertices, {len(lines)} lines")
        
        # Handle preview separately (always cyan)
        if self.preview_tool and len(self.preview_points) >= 1:
            preview_vertices, preview_lines = self._preview_to_mesh_data(0)
            if preview_vertices and preview_lines:
                self._preview_mesh = fast.Mesh.create(preview_vertices, preview_lines, [])
                self._preview_renderer = fast.LineRenderer.create(
                    fast.Color(0.0, 1.0, 1.0), 0.5, True  # Cyan for preview
                )
                self._preview_renderer.addInputData(self._preview_mesh)
                self.view.addRenderer(self._preview_renderer)
        
        self._renderers_added = len(self._line_renderers) > 0 or self._preview_renderer is not None
        self._needs_update = False
    
    def _annotation_to_mesh_data(self, annotation, vertex_offset: int
                                  ) -> Tuple[List[fast.MeshVertex], List[fast.MeshLine]]:
        """
        Convert an annotation to FAST mesh data.
        
        Args:
            annotation: The annotation to convert
            vertex_offset: Starting index for vertices
            
        Returns:
            (vertices, lines) tuple
        """
        vertices = []
        lines = []
        color = to_fast_color(annotation.color)
        
        ann_type = type(annotation).__name__
        
        if ann_type == 'LineAnnotation':
            if len(annotation.points) >= 2:
                p1, p2 = annotation.points[0], annotation.points[1]
                w1 = self.coord_converter.pixel_to_world(p1[0], p1[1])
                w2 = self.coord_converter.pixel_to_world(p2[0], p2[1])
                
                vertices.append(fast.MeshVertex([w1[0], w1[1], w1[2]]))
                vertices.append(fast.MeshVertex([w2[0], w2[1], w2[2]]))
                lines.append(fast.MeshLine(vertex_offset, vertex_offset + 1, color))
        
        elif ann_type == 'RectAnnotation':
            if len(annotation.points) >= 2:
                # Get 4 corners
                corners = annotation.get_corners()
                for corner in corners:
                    w = self.coord_converter.pixel_to_world(corner[0], corner[1])
                    vertices.append(fast.MeshVertex([w[0], w[1], w[2]]))
                
                # Connect as rectangle: 0-1, 1-2, 2-3, 3-0
                lines.append(fast.MeshLine(vertex_offset, vertex_offset + 1, color))
                lines.append(fast.MeshLine(vertex_offset + 1, vertex_offset + 2, color))
                lines.append(fast.MeshLine(vertex_offset + 2, vertex_offset + 3, color))
                lines.append(fast.MeshLine(vertex_offset + 3, vertex_offset, color))
        
        elif ann_type == 'PolygonAnnotation':
            if len(annotation.points) >= 2:
                # Add all vertices
                for pt in annotation.points:
                    w = self.coord_converter.pixel_to_world(pt[0], pt[1])
                    vertices.append(fast.MeshVertex([w[0], w[1], w[2]]))
                
                # Connect consecutive points
                for i in range(len(annotation.points) - 1):
                    lines.append(fast.MeshLine(vertex_offset + i, vertex_offset + i + 1, color))
                
                # Close polygon if completed
                if annotation.completed and annotation.closed:
                    lines.append(fast.MeshLine(
                        vertex_offset + len(annotation.points) - 1, 
                        vertex_offset, 
                        color
                    ))
        
        return vertices, lines
    
    def _preview_to_mesh_data(self, vertex_offset: int
                               ) -> Tuple[List[fast.MeshVertex], List[fast.MeshLine]]:
        """
        Convert preview points to FAST mesh data.
        
        Args:
            vertex_offset: Starting index for vertices
            
        Returns:
            (vertices, lines) tuple
        """
        vertices = []
        lines = []
        color = to_fast_color(self.PREVIEW_COLOR)
        
        if self.preview_tool == 'line' and len(self.preview_points) >= 2:
            p1, p2 = self.preview_points[0], self.preview_points[1]
            w1 = self.coord_converter.pixel_to_world(p1[0], p1[1])
            w2 = self.coord_converter.pixel_to_world(p2[0], p2[1])
            
            vertices.append(fast.MeshVertex([w1[0], w1[1], w1[2]]))
            vertices.append(fast.MeshVertex([w2[0], w2[1], w2[2]]))
            lines.append(fast.MeshLine(vertex_offset, vertex_offset + 1, color))
        
        elif self.preview_tool == 'rectangle' and len(self.preview_points) >= 2:
            p1, p2 = self.preview_points[0], self.preview_points[1]
            # Calculate 4 corners
            corners = [
                (p1[0], p1[1]),
                (p2[0], p1[1]),
                (p2[0], p2[1]),
                (p1[0], p2[1])
            ]
            for corner in corners:
                w = self.coord_converter.pixel_to_world(corner[0], corner[1])
                vertices.append(fast.MeshVertex([w[0], w[1], w[2]]))
            
            lines.append(fast.MeshLine(vertex_offset, vertex_offset + 1, color))
            lines.append(fast.MeshLine(vertex_offset + 1, vertex_offset + 2, color))
            lines.append(fast.MeshLine(vertex_offset + 2, vertex_offset + 3, color))
            lines.append(fast.MeshLine(vertex_offset + 3, vertex_offset, color))
        
        elif self.preview_tool == 'polygon' and len(self.preview_points) >= 2:
            for pt in self.preview_points:
                w = self.coord_converter.pixel_to_world(pt[0], pt[1])
                vertices.append(fast.MeshVertex([w[0], w[1], w[2]]))
            
            for i in range(len(self.preview_points) - 1):
                lines.append(fast.MeshLine(vertex_offset + i, vertex_offset + i + 1, color))
        
        return vertices, lines
    
    def get_annotation_at_point(self, px: float, py: float, 
                                 tolerance: float = 10.0) -> Optional[Any]:
        """
        Find annotation at given pixel coordinates.
        
        Args:
            px: X coordinate in pixels
            py: Y coordinate in pixels
            tolerance: Distance tolerance in pixels
            
        Returns:
            Annotation at the point, or None
        """
        # Simple hit testing - check distance to annotation lines
        for ann in reversed(self.annotations):  # Check top-most first
            if not ann.visible:
                continue
            
            if self._point_near_annotation(ann, px, py, tolerance):
                return ann
        
        return None
    
    def _point_near_annotation(self, annotation, px: float, py: float, 
                                tolerance: float) -> bool:
        """Check if a point is near an annotation."""
        ann_type = type(annotation).__name__
        
        if ann_type == 'LineAnnotation' and len(annotation.points) >= 2:
            return self._point_near_line(
                annotation.points[0], annotation.points[1], 
                (px, py), tolerance
            )
        
        elif ann_type == 'RectAnnotation' and len(annotation.points) >= 2:
            corners = annotation.get_corners()
            for i in range(4):
                if self._point_near_line(
                    corners[i], corners[(i + 1) % 4], (px, py), tolerance
                ):
                    return True
        
        elif ann_type == 'PolygonAnnotation' and len(annotation.points) >= 2:
            for i in range(len(annotation.points) - 1):
                if self._point_near_line(
                    annotation.points[i], annotation.points[i + 1], 
                    (px, py), tolerance
                ):
                    return True
            if annotation.closed and len(annotation.points) >= 3:
                if self._point_near_line(
                    annotation.points[-1], annotation.points[0], 
                    (px, py), tolerance
                ):
                    return True
        
        return False
    
    def _point_near_line(self, p1: Tuple[float, float], p2: Tuple[float, float],
                          point: Tuple[float, float], tolerance: float) -> bool:
        """Check if point is near a line segment."""
        x1, y1 = p1
        x2, y2 = p2
        px, py = point
        
        # Line length squared
        line_len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
        if line_len_sq == 0:
            # Point-to-point distance
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2) <= tolerance
        
        # Project point onto line
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / line_len_sq))
        
        # Closest point on line
        closest_x = x1 + t * (x2 - x1)
        closest_y = y1 + t * (y2 - y1)
        
        # Distance to closest point
        dist = math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)
        return dist <= tolerance
