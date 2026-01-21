"""
Image Processing Module for Ultrasound Imaging Software.

This module provides:
- Colormap/LUT management (Grayscale, Hot, Cool, Bone, etc.)
- Image filters (Gaussian, Median, Sharpen, Speckle Reduction)
- Filter strength controls
"""

import numpy as np
from typing import Dict, Optional, Tuple, Callable
from enum import Enum


class ColormapType(Enum):
    """Available colormap types."""
    GRAYSCALE = "grayscale"
    HOT = "hot"
    COOL = "cool"
    BONE = "bone"
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"


class FilterType(Enum):
    """Available filter types."""
    NONE = "none"
    GAUSSIAN = "gaussian"
    MEDIAN = "median"
    SHARPEN = "sharpen"
    EDGE_ENHANCE = "edge_enhance"
    SPECKLE_REDUCE = "speckle_reduce"


class ColormapManager:
    """
    Manages colormap/LUT generation and application.
    
    Each colormap is a 256x3 numpy array mapping grayscale values to RGB.
    """
    
    def __init__(self):
        self._colormaps: Dict[str, np.ndarray] = {}
        self._current_colormap = ColormapType.GRAYSCALE
        self._generate_all_colormaps()
    
    def _generate_all_colormaps(self):
        """Pre-generate all colormap LUTs."""
        self._colormaps = {
            ColormapType.GRAYSCALE.value: self._generate_grayscale(),
            ColormapType.HOT.value: self._generate_hot(),
            ColormapType.COOL.value: self._generate_cool(),
            ColormapType.BONE.value: self._generate_bone(),
            ColormapType.VIRIDIS.value: self._generate_viridis(),
            ColormapType.PLASMA.value: self._generate_plasma(),
            ColormapType.INFERNO.value: self._generate_inferno(),
        }
    
    def _generate_grayscale(self) -> np.ndarray:
        """Generate grayscale LUT (identity mapping)."""
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            lut[i] = [i, i, i]
        return lut
    
    def _generate_hot(self) -> np.ndarray:
        """
        Generate 'Hot' colormap LUT.
        Black → Red → Yellow → White
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            if i < 85:
                # Black to Red
                r = int(i * 3)
                g = 0
                b = 0
            elif i < 170:
                # Red to Yellow
                r = 255
                g = int((i - 85) * 3)
                b = 0
            else:
                # Yellow to White
                r = 255
                g = 255
                b = int((i - 170) * 3)
            lut[i] = [r, g, b]
        return lut
    
    def _generate_cool(self) -> np.ndarray:
        """
        Generate 'Cool' colormap LUT.
        Cyan → Magenta gradient
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            r = i
            g = 255 - i
            b = 255
            lut[i] = [r, g, b]
        return lut
    
    def _generate_bone(self) -> np.ndarray:
        """
        Generate 'Bone' colormap LUT.
        Black → Blue-gray → White (common in medical imaging)
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t = i / 255.0
            if t < 0.375:
                # Black to blue-gray
                r = int(t / 0.375 * 0.3 * 255)
                g = int(t / 0.375 * 0.3 * 255)
                b = int(t / 0.375 * 0.5 * 255)
            elif t < 0.75:
                # Blue-gray to light
                tt = (t - 0.375) / 0.375
                r = int((0.3 + tt * 0.4) * 255)
                g = int((0.3 + tt * 0.5) * 255)
                b = int((0.5 + tt * 0.3) * 255)
            else:
                # Light to white
                tt = (t - 0.75) / 0.25
                r = int((0.7 + tt * 0.3) * 255)
                g = int((0.8 + tt * 0.2) * 255)
                b = int((0.8 + tt * 0.2) * 255)
            lut[i] = [r, g, b]
        return lut
    
    def _generate_viridis(self) -> np.ndarray:
        """
        Generate 'Viridis' colormap LUT.
        Purple → Blue → Green → Yellow (perceptually uniform, colorblind-friendly)
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        # Simplified viridis approximation
        for i in range(256):
            t = i / 255.0
            r = int((0.267 + t * (0.993 - 0.267)) * 255 * (0.3 + 0.7 * t))
            g = int((0.004 + t * (0.906 - 0.004)) * 255)
            b = int((0.329 + t * (-0.143)) * 255 + 84)
            lut[i] = [
                min(255, max(0, r)),
                min(255, max(0, g)),
                min(255, max(0, int(0.329 * 255 * (1 - t * 0.5) + 84 * t)))
            ]
        # Use proper viridis values
        viridis_data = [
            (68, 1, 84), (72, 33, 115), (67, 62, 133), (56, 88, 140),
            (45, 112, 142), (37, 133, 142), (30, 155, 138), (42, 176, 127),
            (81, 197, 105), (134, 213, 73), (194, 223, 35), (253, 231, 37)
        ]
        # Interpolate
        for i in range(256):
            t = i / 255.0 * (len(viridis_data) - 1)
            idx = int(t)
            frac = t - idx
            if idx >= len(viridis_data) - 1:
                lut[i] = viridis_data[-1]
            else:
                c1 = viridis_data[idx]
                c2 = viridis_data[idx + 1]
                lut[i] = [
                    int(c1[0] + frac * (c2[0] - c1[0])),
                    int(c1[1] + frac * (c2[1] - c1[1])),
                    int(c1[2] + frac * (c2[2] - c1[2])),
                ]
        return lut
    
    def _generate_plasma(self) -> np.ndarray:
        """
        Generate 'Plasma' colormap LUT.
        Blue → Purple → Orange → Yellow
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        plasma_data = [
            (13, 8, 135), (75, 3, 161), (125, 3, 168), (168, 34, 150),
            (203, 70, 121), (229, 107, 93), (248, 148, 65), (253, 195, 40),
            (240, 249, 33)
        ]
        for i in range(256):
            t = i / 255.0 * (len(plasma_data) - 1)
            idx = int(t)
            frac = t - idx
            if idx >= len(plasma_data) - 1:
                lut[i] = plasma_data[-1]
            else:
                c1 = plasma_data[idx]
                c2 = plasma_data[idx + 1]
                lut[i] = [
                    int(c1[0] + frac * (c2[0] - c1[0])),
                    int(c1[1] + frac * (c2[1] - c1[1])),
                    int(c1[2] + frac * (c2[2] - c1[2])),
                ]
        return lut
    
    def _generate_inferno(self) -> np.ndarray:
        """
        Generate 'Inferno' colormap LUT.
        Black → Purple → Red → Yellow
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        inferno_data = [
            (0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99),
            (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164)
        ]
        for i in range(256):
            t = i / 255.0 * (len(inferno_data) - 1)
            idx = int(t)
            frac = t - idx
            if idx >= len(inferno_data) - 1:
                lut[i] = inferno_data[-1]
            else:
                c1 = inferno_data[idx]
                c2 = inferno_data[idx + 1]
                lut[i] = [
                    int(c1[0] + frac * (c2[0] - c1[0])),
                    int(c1[1] + frac * (c2[1] - c1[1])),
                    int(c1[2] + frac * (c2[2] - c1[2])),
                ]
        return lut
    
    def get_colormap(self, colormap_type: ColormapType) -> np.ndarray:
        """Get the LUT for a specific colormap."""
        return self._colormaps.get(colormap_type.value, self._colormaps[ColormapType.GRAYSCALE.value])
    
    def set_current_colormap(self, colormap_type: ColormapType):
        """Set the current active colormap."""
        self._current_colormap = colormap_type
    
    def get_current_colormap(self) -> ColormapType:
        """Get the current active colormap type."""
        return self._current_colormap
    
    def apply_colormap(self, image: np.ndarray, colormap_type: Optional[ColormapType] = None) -> np.ndarray:
        """
        Apply colormap to a grayscale image.
        
        Args:
            image: 2D grayscale image (H, W) with values 0-255
            colormap_type: Colormap to apply, or use current if None
            
        Returns:
            3D RGB image (H, W, 3)
        """
        if colormap_type is None:
            colormap_type = self._current_colormap
        
        if colormap_type == ColormapType.GRAYSCALE:
            # Return as-is for grayscale (or stack to RGB)
            if image.ndim == 2:
                return np.stack([image, image, image], axis=-1)
            return image
        
        lut = self.get_colormap(colormap_type)
        
        # Ensure image is uint8
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        
        # Apply LUT using advanced indexing
        return lut[image]
    
    @staticmethod
    def get_available_colormaps() -> list:
        """Get list of available colormap names."""
        return [c.value for c in ColormapType]


class ImageFilterProcessor:
    """
    Manages image filter processing.
    
    Provides various filters for ultrasound image enhancement.
    """
    
    def __init__(self):
        self._current_filter = FilterType.NONE
        self._filter_strength = 0.5  # 0.0 to 1.0
        
        # Filter-specific parameters
        self._gaussian_sigma = 1.0
        self._median_size = 3
        self._sharpen_amount = 0.5
        self._edge_enhance_amount = 0.3
        self._speckle_sigma = 0.1
    
    @property
    def filter_strength(self) -> float:
        return self._filter_strength
    
    @filter_strength.setter
    def filter_strength(self, value: float):
        self._filter_strength = max(0.0, min(1.0, value))
    
    @property
    def current_filter(self) -> FilterType:
        return self._current_filter
    
    @current_filter.setter
    def current_filter(self, filter_type: FilterType):
        self._current_filter = filter_type
    
    def gaussian_blur(self, image: np.ndarray, sigma: Optional[float] = None) -> np.ndarray:
        """
        Apply Gaussian blur for smoothing/denoising.
        
        Args:
            image: Input image
            sigma: Standard deviation of Gaussian kernel (default uses strength-based)
            
        Returns:
            Blurred image
        """
        if sigma is None:
            sigma = 0.5 + self._filter_strength * 2.5  # 0.5 to 3.0
        
        try:
            from scipy.ndimage import gaussian_filter
            return gaussian_filter(image.astype(np.float32), sigma=sigma).astype(image.dtype)
        except ImportError:
            # Fallback: simple box blur approximation
            return self._simple_blur(image, int(sigma * 2) * 2 + 1)
    
    def median_filter(self, image: np.ndarray, size: Optional[int] = None) -> np.ndarray:
        """
        Apply median filter for salt-and-pepper noise removal.
        
        Args:
            image: Input image
            size: Kernel size (must be odd)
            
        Returns:
            Filtered image
        """
        if size is None:
            size = 3 + int(self._filter_strength * 4) * 2  # 3, 5, 7, 9, 11
            if size % 2 == 0:
                size += 1
        
        try:
            from scipy.ndimage import median_filter
            return median_filter(image, size=size)
        except ImportError:
            # Fallback: simple implementation
            return self._simple_median(image, size)
    
    def sharpen(self, image: np.ndarray, amount: Optional[float] = None) -> np.ndarray:
        """
        Apply unsharp masking for image sharpening.
        
        Args:
            image: Input image
            amount: Sharpening amount (0.0 to 2.0)
            
        Returns:
            Sharpened image
        """
        if amount is None:
            amount = self._filter_strength * 1.5  # 0.0 to 1.5
        
        # Unsharp mask: original + amount * (original - blurred)
        blurred = self.gaussian_blur(image, sigma=1.0)
        
        # Calculate the high-pass component
        high_pass = image.astype(np.float32) - blurred.astype(np.float32)
        
        # Add weighted high-pass back to original
        sharpened = image.astype(np.float32) + amount * high_pass
        
        return np.clip(sharpened, 0, 255).astype(np.uint8)
    
    def edge_enhance(self, image: np.ndarray, amount: Optional[float] = None) -> np.ndarray:
        """
        Apply edge enhancement using Laplacian.
        
        Args:
            image: Input image
            amount: Enhancement amount
            
        Returns:
            Edge-enhanced image
        """
        if amount is None:
            amount = self._filter_strength * 0.5  # 0.0 to 0.5
        
        try:
            from scipy.ndimage import laplace
            
            # Calculate Laplacian (edges)
            edges = laplace(image.astype(np.float32))
            
            # Enhance: original - amount * laplacian (subtracting enhances edges)
            enhanced = image.astype(np.float32) - amount * edges
            
            return np.clip(enhanced, 0, 255).astype(np.uint8)
        except ImportError:
            return image
    
    def speckle_reduce(self, image: np.ndarray, sigma: Optional[float] = None) -> np.ndarray:
        """
        Apply speckle reduction for ultrasound images.
        Uses Lee filter approximation.
        
        Args:
            image: Input ultrasound image
            sigma: Noise variance estimate
            
        Returns:
            Speckle-reduced image
        """
        if sigma is None:
            sigma = 0.05 + self._filter_strength * 0.2  # 0.05 to 0.25
        
        try:
            from scipy.ndimage import uniform_filter, variance
            
            img_float = image.astype(np.float64)
            window_size = 5 + int(self._filter_strength * 4) * 2
            
            # Local mean
            local_mean = uniform_filter(img_float, size=window_size)
            
            # Local variance
            local_sqr_mean = uniform_filter(img_float ** 2, size=window_size)
            local_var = local_sqr_mean - local_mean ** 2
            local_var = np.maximum(local_var, 0)  # Avoid negative variance
            
            # Noise variance estimate
            noise_var = sigma ** 2 * np.mean(img_float) ** 2
            
            # Lee filter weight
            weight = local_var / (local_var + noise_var + 1e-10)
            
            # Apply filter
            result = local_mean + weight * (img_float - local_mean)
            
            return np.clip(result, 0, 255).astype(np.uint8)
        except ImportError:
            # Fallback to simple smoothing
            return self.gaussian_blur(image)
    
    def _simple_blur(self, image: np.ndarray, size: int) -> np.ndarray:
        """Simple box blur fallback."""
        from functools import reduce
        kernel = np.ones((size, size), dtype=np.float32) / (size * size)
        
        # Pad image
        pad = size // 2
        padded = np.pad(image, pad, mode='reflect')
        
        result = np.zeros_like(image, dtype=np.float32)
        for i in range(size):
            for j in range(size):
                result += kernel[i, j] * padded[i:i+image.shape[0], j:j+image.shape[1]]
        
        return result.astype(image.dtype)
    
    def _simple_median(self, image: np.ndarray, size: int) -> np.ndarray:
        """Simple median filter fallback."""
        pad = size // 2
        padded = np.pad(image, pad, mode='reflect')
        result = np.zeros_like(image)
        
        for i in range(image.shape[0]):
            for j in range(image.shape[1]):
                window = padded[i:i+size, j:j+size]
                result[i, j] = np.median(window)
        
        return result
    
    def apply_filter(self, image: np.ndarray, filter_type: Optional[FilterType] = None) -> np.ndarray:
        """
        Apply the specified (or current) filter to an image.
        
        Args:
            image: Input image
            filter_type: Filter to apply, or use current if None
            
        Returns:
            Filtered image
        """
        if filter_type is None:
            filter_type = self._current_filter
        
        if filter_type == FilterType.NONE:
            return image
        elif filter_type == FilterType.GAUSSIAN:
            return self.gaussian_blur(image)
        elif filter_type == FilterType.MEDIAN:
            return self.median_filter(image)
        elif filter_type == FilterType.SHARPEN:
            return self.sharpen(image)
        elif filter_type == FilterType.EDGE_ENHANCE:
            return self.edge_enhance(image)
        elif filter_type == FilterType.SPECKLE_REDUCE:
            return self.speckle_reduce(image)
        else:
            return image
    
    @staticmethod
    def get_available_filters() -> list:
        """Get list of available filter names."""
        return [f.value for f in FilterType]


class ImageProcessingPipeline:
    """
    Combined image processing pipeline.
    
    Applies filters and colormap in sequence:
    Input → Filter → Window/Level → Colormap → Output
    """
    
    def __init__(self):
        self.colormap_manager = ColormapManager()
        self.filter_processor = ImageFilterProcessor()
        
        # Window/Level settings
        self.window = 255.0
        self.level = 127.5
    
    def set_window_level(self, window: float, level: float):
        """Set Window/Level for contrast adjustment."""
        self.window = max(1, window)
        self.level = level
    
    def apply_window_level(self, image: np.ndarray) -> np.ndarray:
        """Apply Window/Level transform to image."""
        img_float = image.astype(np.float32)
        
        # Calculate min/max based on Window/Level
        min_val = self.level - self.window / 2
        max_val = self.level + self.window / 2
        
        # Apply linear mapping
        result = (img_float - min_val) / (max_val - min_val) * 255
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def process(self, image: np.ndarray, 
                apply_filter: bool = True,
                apply_wl: bool = True,
                apply_colormap: bool = True) -> np.ndarray:
        """
        Process image through the full pipeline.
        
        Args:
            image: Input grayscale image
            apply_filter: Whether to apply current filter
            apply_wl: Whether to apply Window/Level
            apply_colormap: Whether to apply colormap
            
        Returns:
            Processed image (RGB if colormap applied, grayscale otherwise)
        """
        result = image.copy()
        
        # 1. Apply filter
        if apply_filter and self.filter_processor.current_filter != FilterType.NONE:
            result = self.filter_processor.apply_filter(result)
        
        # 2. Apply Window/Level
        if apply_wl:
            result = self.apply_window_level(result)
        
        # 3. Apply colormap
        if apply_colormap:
            result = self.colormap_manager.apply_colormap(result)
        
        return result


# Convenience functions for FAST integration
def create_colormap_shader_code(colormap_type: ColormapType) -> str:
    """
    Generate GLSL shader code for GPU-based colormap application.
    For use with FAST custom renderers.
    """
    manager = ColormapManager()
    lut = manager.get_colormap(colormap_type)
    
    # Convert LUT to GLSL array string
    lut_str = ",".join([f"vec3({r/255:.3f},{g/255:.3f},{b/255:.3f})" 
                        for r, g, b in lut])
    
    shader = f"""
    #version 330 core
    
    uniform sampler2D inputTexture;
    in vec2 texCoord;
    out vec4 fragColor;
    
    const vec3 colormap[256] = vec3[]({lut_str});
    
    void main() {{
        float intensity = texture(inputTexture, texCoord).r;
        int idx = int(clamp(intensity * 255.0, 0.0, 255.0));
        fragColor = vec4(colormap[idx], 1.0);
    }}
    """
    return shader


# Display names for UI
COLORMAP_DISPLAY_NAMES = {
    ColormapType.GRAYSCALE: "灰階 (Grayscale)",
    ColormapType.HOT: "熱力圖 (Hot)",
    ColormapType.COOL: "冷色調 (Cool)",
    ColormapType.BONE: "骨骼 (Bone)",
    ColormapType.VIRIDIS: "Viridis",
    ColormapType.PLASMA: "Plasma",
    ColormapType.INFERNO: "Inferno",
}

FILTER_DISPLAY_NAMES = {
    FilterType.NONE: "無 (None)",
    FilterType.GAUSSIAN: "高斯模糊 (Gaussian)",
    FilterType.MEDIAN: "中值濾波 (Median)",
    FilterType.SHARPEN: "銳化 (Sharpen)",
    FilterType.EDGE_ENHANCE: "邊緣增強 (Edge Enhance)",
    FilterType.SPECKLE_REDUCE: "斑點降噪 (Speckle Reduce)",
}


# ============================================================
# FAST PythonProcessObject for Frame Tapping (grayscale only)
# ============================================================

def create_frame_tap_processor():
    """
    Factory function to create FrameTapProcessor.
    Must be called after FAST is imported.
    """
    import fast
    import threading

    class FrameTapProcessor(fast.PythonProcessObject):
        """
        FAST ProcessObject that passes through grayscale frames and
        stores the latest frame for UI overlay usage.
        """

        def __init__(self):
            super().__init__()
            self.createInputPort(0)
            self.createOutputPort(0)
            self._lock = threading.Lock()
            self._latest_frame = None
            self._latest_info = None
            self._frame_id = 0
            self._enabled = True

        def setEnabled(self, enabled: bool):
            if enabled != self._enabled:
                self._enabled = enabled
                self.setModified(True)

        def isEnabled(self) -> bool:
            return self._enabled

        def getLatestFrame(self, copy: bool = True):
            """
            Return (frame, frame_id). Frame is 2D uint8 grayscale.
            """
            with self._lock:
                if self._latest_frame is None:
                    return None, self._frame_id
                frame = self._latest_frame.copy() if copy else self._latest_frame
                return frame, self._frame_id

        def getLatestImageInfo(self):
            """
            Return latest image info dict with size, spacing, transform_matrix.
            """
            with self._lock:
                info = self._latest_info.copy() if self._latest_info else None
                return info

        def execute(self):
            input_image = self.getInputData(0)
            if input_image is None:
                return

            input_array = np.asarray(input_image)

            if not self._enabled:
                output_image = fast.Image.createFromArray(input_array)
                self.addOutputData(0, output_image)
                return

            if input_array.ndim == 3 and input_array.shape[2] == 3:
                gray = np.mean(input_array, axis=2).astype(np.uint8)
            elif input_array.ndim == 3 and input_array.shape[2] == 1:
                gray = input_array[:, :, 0]
            elif input_array.ndim == 2:
                gray = input_array
            else:
                gray = input_array

            if gray.dtype != np.uint8:
                gray = np.clip(gray, 0, 255).astype(np.uint8)

            with self._lock:
                self._latest_frame = np.ascontiguousarray(gray)
                try:
                    size = input_image.getSize()
                    spacing = input_image.getSpacing()
                    transform = input_image.getTransform()
                    transform_matrix = transform.getMatrix() if transform else None
                except Exception:
                    size = None
                    spacing = None
                    transform_matrix = None
                self._latest_info = {
                    "size": size,
                    "spacing": spacing,
                    "transform_matrix": transform_matrix,
                }
                self._frame_id += 1

            output_image = fast.Image.createFromArray(gray)
            self.addOutputData(0, output_image)

    return FrameTapProcessor


# ============================================================
# FAST PythonProcessObject for Colormap Processing
# ============================================================

def create_colormap_processor():
    """
    Factory function to create ColormapProcessor.
    Must be called after FAST is imported.
    """
    import fast
    
    class ColormapProcessor(fast.PythonProcessObject):
        """
        FAST ProcessObject that applies colormap LUT to grayscale images.
        
        Converts single-channel grayscale images to 3-channel RGB using
        a lookup table (LUT) for the selected colormap.
        
        Usage:
            processor = ColormapProcessor.create()
            processor.connect(streamer)
            processor.setColormap(ColormapType.HOT)
            renderer.connect(processor)
        """
        
        def __init__(self):
            super().__init__()
            self.createInputPort(0)
            self.createOutputPort(0)
            
            # Initialize colormap manager and LUT
            self._colormap_manager = ColormapManager()
            self._current_colormap = ColormapType.GRAYSCALE
            self._lut = self._colormap_manager.get_colormap(ColormapType.GRAYSCALE)
            self._enabled = True
            
        def setColormap(self, colormap_type: ColormapType):
            """Set the colormap to use for conversion."""
            if colormap_type != self._current_colormap:
                self._current_colormap = colormap_type
                self._lut = self._colormap_manager.get_colormap(colormap_type)
                self.setModified(True)
        
        def getColormap(self) -> ColormapType:
            """Get the current colormap type."""
            return self._current_colormap
        
        def setEnabled(self, enabled: bool):
            """Enable or disable colormap processing."""
            if enabled != self._enabled:
                self._enabled = enabled
                self.setModified(True)
        
        def isEnabled(self) -> bool:
            """Check if colormap processing is enabled."""
            return self._enabled
        
        def execute(self):
            """Process each frame: apply colormap LUT."""
            # Get input image
            input_image = self.getInputData(0)
            
            if input_image is None:
                return
            
            # Get numpy array from FAST image
            input_array = np.asarray(input_image)
            
            # Check if grayscale passthrough (no conversion needed)
            if not self._enabled or self._current_colormap == ColormapType.GRAYSCALE:
                # Pass through unchanged
                output_image = fast.Image.createFromArray(input_array)
                self.addOutputData(0, output_image)
                return
            
            # Handle different input shapes
            if input_array.ndim == 3 and input_array.shape[2] == 3:
                # Already RGB, convert to grayscale first
                gray = np.mean(input_array, axis=2).astype(np.uint8)
            elif input_array.ndim == 3 and input_array.shape[2] == 1:
                # Single channel 3D array, squeeze to 2D
                gray = input_array[:, :, 0]
            elif input_array.ndim == 2:
                # Already grayscale
                gray = input_array
            else:
                # Unsupported format, pass through
                output_image = fast.Image.createFromArray(input_array)
                self.addOutputData(0, output_image)
                return
            
            # Ensure uint8 for LUT indexing
            if gray.dtype != np.uint8:
                gray = np.clip(gray, 0, 255).astype(np.uint8)
            
            # Apply LUT (vectorized operation - very fast)
            rgb = self._lut[gray]  # Shape: (H, W, 3)
            
            # Ensure contiguous array
            rgb = np.ascontiguousarray(rgb)
            
            # Create FAST image from RGB array
            output_image = fast.Image.createFromArray(rgb)
            self.addOutputData(0, output_image)
    
    return ColormapProcessor


def create_filter_processor():
    """
    Factory function to create FilterProcessor.
    Must be called after FAST is imported.
    """
    import fast
    
    class FilterProcessor(fast.PythonProcessObject):
        """
        FAST ProcessObject that applies image filters.
        
        Supports various filters: Gaussian, Median, Sharpen, Edge Enhance, Speckle Reduce.
        """
        
        def __init__(self):
            super().__init__()
            self.createInputPort(0)
            self.createOutputPort(0)
            
            # Initialize filter processor
            self._filter_processor = ImageFilterProcessor()
            self._current_filter = FilterType.NONE
            self._strength = 0.5
            self._enabled = True
            
        def setFilter(self, filter_type: FilterType, strength: float = None):
            """Set the filter to apply, optionally with strength."""
            modified = False
            
            if filter_type != self._current_filter:
                self._current_filter = filter_type
                self._filter_processor.current_filter = filter_type
                modified = True
            
            if strength is not None:
                strength = max(0.0, min(1.0, strength))
                if strength != self._strength:
                    self._strength = strength
                    self._filter_processor.filter_strength = strength
                    modified = True
            
            if modified:
                self.setModified(True)
        
        def getFilter(self) -> FilterType:
            """Get the current filter type."""
            return self._current_filter
        
        def setStrength(self, strength: float):
            """Set filter strength (0.0 to 1.0)."""
            strength = max(0.0, min(1.0, strength))
            if strength != self._strength:
                self._strength = strength
                self._filter_processor.filter_strength = strength
                self.setModified(True)
        
        def getStrength(self) -> float:
            """Get the current filter strength."""
            return self._strength
        
        def setEnabled(self, enabled: bool):
            """Enable or disable filter processing."""
            if enabled != self._enabled:
                self._enabled = enabled
                self.setModified(True)
        
        def isEnabled(self) -> bool:
            """Check if filter processing is enabled."""
            return self._enabled
        
        def execute(self):
            """Process each frame: apply filter."""
            # Get input image
            input_image = self.getInputData(0)
            
            if input_image is None:
                return
            
            # Get numpy array from FAST image
            input_array = np.asarray(input_image)
            
            # Check if filter passthrough (no processing needed)
            if not self._enabled or self._current_filter == FilterType.NONE:
                # Pass through unchanged
                output_image = fast.Image.createFromArray(input_array)
                self.addOutputData(0, output_image)
                return
            
            # Handle RGB images - convert to grayscale for filtering
            is_rgb = input_array.ndim == 3 and input_array.shape[2] == 3
            if is_rgb:
                # Filter on luminance channel, then apply to all channels
                gray = np.mean(input_array, axis=2).astype(np.uint8)
                filtered = self._filter_processor.apply_filter(gray)
                # Scale RGB by filter result / original gray ratio
                with np.errstate(divide='ignore', invalid='ignore'):
                    ratio = np.where(gray > 0, filtered.astype(np.float32) / gray.astype(np.float32), 1.0)
                    ratio = np.clip(ratio, 0, 2)  # Limit ratio to prevent overflow
                result = np.clip(input_array * ratio[:, :, np.newaxis], 0, 255).astype(np.uint8)
            else:
                # Grayscale image - filter directly
                result = self._filter_processor.apply_filter(input_array)
            
            # Ensure contiguous array
            result = np.ascontiguousarray(result)
            
            # Create FAST image
            output_image = fast.Image.createFromArray(result)
            self.addOutputData(0, output_image)
    
    return FilterProcessor

