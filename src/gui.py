import fast
from .pipelines import create_display_pipeline

class UltrasoundWindow:
    """
    Enhanced Ultrasound Imaging Software GUI with professional medical imaging features.
    
    Features:
    - Playback controls (play/pause/seek/framerate)
    - Image adjustments (brightness, contrast via Window/Level)
    - Denoising filter with toggle
    - Colormap options
    - File information display
    """
    
    def __init__(self, mode='playback', filepath=None, file_info=None):
        self.mode = mode
        self.filepath = filepath
        self.file_info = file_info or {}
        self.width = 1280
        self.height = 800
        
        # Store references to processing objects
        self.importer = None
        self.renderer = None
        self.nlm_filter = None
        self.nlm_renderer = None
        self.widgets = []
        
        # Setup the pipeline based on mode
        if self.mode == 'playback' and self.filepath:
            from .pipelines import create_playback_pipeline
            self.importer = create_playback_pipeline(self.filepath)
            if self.importer is None:
                print("Failed to initialize pipeline. Exiting.")
                self._create_empty_window()
                return
        else:
            self.importer = fast.ImageFileImporter.create(self.filepath) if self.filepath else None

        if self.importer:
            self._setup_processing_pipeline()
            self._setup_window_with_widgets()
        else:
            self._create_empty_window()
    
    def _create_empty_window(self):
        """Create an empty window when no data is available."""
        self.window = fast.SimpleWindow2D.create()
        self.window.setTitle("Ultrasound Imaging Software - No Data")
        self.window.setWidth(self.width)
        self.window.setHeight(self.height)
    
    def _setup_processing_pipeline(self):
        """Setup the image processing pipeline with optional denoising."""
        
        # Main renderer for original image
        self.renderer = fast.ImageRenderer.create()
        self.renderer.connect(self.importer)
        
        # Set default intensity settings for grayscale
        self.renderer.setIntensityLevel(127.5)
        self.renderer.setIntensityWindow(255)
        
        # Denoising filter (Non-Local Means)
        self.nlm_filter = fast.NonLocalMeans.create(
            filterSize=3,
            searchSize=11,
            smoothingAmount=0.2,
            inputMultiplicationWeight=0.5,
        )
        self.nlm_filter.connect(self.importer)
        
        # Renderer for denoised image (starts disabled)
        self.nlm_renderer = fast.ImageRenderer.create()
        self.nlm_renderer.connect(self.nlm_filter)
        self.nlm_renderer.setIntensityLevel(127.5)
        self.nlm_renderer.setIntensityWindow(255)
        self.nlm_renderer.setDisabled(True)  # Start with filter OFF
    
    def _setup_window_with_widgets(self):
        """Setup the window with all GUI widgets."""
        
        # Create window
        self.window = fast.SimpleWindow2D.create()
        self.window.setTitle("Ultrasound Imaging Software")
        self.window.setWidth(self.width)
        self.window.setHeight(self.height)
        
        # Add renderers
        self.window.connect(self.renderer)
        self.window.connect(self.nlm_renderer)
        
        # --- Create Widgets ---
        self.widgets = []
        
        # 1. Playback Widget (if streaming)
        if hasattr(self.importer, 'setFramerate'):
            try:
                playback_widget = fast.PlaybackWidget(self.importer)
                self.widgets.append(playback_widget)
                print("✓ Playback controls enabled")
            except Exception as e:
                print(f"Note: Playback widget not available: {e}")
        
        # 2. Image Adjustment Widgets
        self._add_image_adjustment_widgets()
        
        # 3. Processing Widgets
        self._add_processing_widgets()
        
        # Add all widgets to the window (on the right side)
        if self.widgets:
            self.window.connect(self.widgets, fast.WidgetPosition_RIGHT)
        
        # Print controls
        self._print_controls()
    
    def _add_image_adjustment_widgets(self):
        """Add brightness and contrast (Window/Level) control widgets."""
        
        # Window Level (controls brightness)
        level_slider = fast.SliderWidget(
            'Brightness (Level)',  # Label
            127.5,                  # Initial value
            0,                      # Min
            255,                    # Max
            1,                      # Step
            fast.SliderCallback(lambda x: self._set_level(x))
        )
        self.widgets.append(level_slider)
        
        # Window Width (controls contrast)
        window_slider = fast.SliderWidget(
            'Contrast (Window)',   # Label
            255,                    # Initial value
            1,                      # Min
            510,                    # Max
            1,                      # Step
            fast.SliderCallback(lambda x: self._set_window(x))
        )
        self.widgets.append(window_slider)
        
        print("✓ Image adjustment controls enabled")
    
    def _add_processing_widgets(self):
        """Add image processing control widgets."""
        
        # Denoise Toggle Button
        denoise_toggle = fast.ButtonWidget(
            'Denoise Filter',
            True,  # Initially OFF (checkbox unchecked = filter disabled)
            fast.ButtonCallback(lambda checked: self._toggle_denoise(checked))
        )
        self.widgets.append(denoise_toggle)
        
        # Smoothing Amount Slider
        smoothing_slider = fast.SliderWidget(
            'Denoise Strength',
            0.2,    # Initial
            0.05,   # Min
            0.8,    # Max
            0.05,   # Step
            fast.SliderCallback(lambda x: self.nlm_filter.setSmoothingAmount(x))
        )
        self.widgets.append(smoothing_slider)
        
        print("✓ Processing controls enabled")
    
    def _set_level(self, value):
        """Set intensity level for both renderers."""
        self.renderer.setIntensityLevel(value)
        self.nlm_renderer.setIntensityLevel(value)
    
    def _set_window(self, value):
        """Set intensity window for both renderers."""
        self.renderer.setIntensityWindow(value)
        self.nlm_renderer.setIntensityWindow(value)
    
    def _toggle_denoise(self, checked):
        """Toggle denoise filter on/off."""
        # When button is checked, disable the original renderer and enable NLM
        # When unchecked, show original
        if checked:
            self.renderer.setDisabled(True)
            self.nlm_renderer.setDisabled(False)
            print("Denoise filter: ON")
        else:
            self.renderer.setDisabled(False)
            self.nlm_renderer.setDisabled(True)
            print("Denoise filter: OFF")
    
    def _print_controls(self):
        """Print keyboard controls information."""
        print("\n" + "="*50)
        print("  Ultrasound Imaging Software")
        print("="*50)
        
        if self.file_info:
            print(f"\n📁 File Information:")
            for key, value in self.file_info.items():
                print(f"   {key}: {value}")
        
        print(f"\n⌨️  Keyboard Controls:")
        print("   'q'     : Quit")
        print("   'r'     : Reset view")
        print("   Space   : Play/Pause")
        print("   ←/→     : Previous/Next frame")
        print("   Mouse   : Drag to pan, Scroll to zoom")
        print("\n🎛️  GUI Controls (right panel):")
        print("   Brightness/Contrast sliders")
        print("   Denoise filter toggle and strength")
        print("="*50 + "\n")

    def run(self):
        """Start the visualization window."""
        self.window.run()
