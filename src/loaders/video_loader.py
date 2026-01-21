"""
Async video loader using QThread.

Provides non-blocking loading of video files (AVI, MP4, etc.) with progress reporting.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from PySide2.QtCore import QThread, Signal


@dataclass
class VideoLoadResult:
    """Result object from video loading operation."""
    success: bool
    filepath: str
    streamer: Any = None  # FAST streamer object
    image_width: int = 0
    image_height: int = 0
    num_frames: int = 0
    framerate: int = 30
    error_message: str = ""


class VideoLoadWorker(QThread):
    """
    Background worker for loading video files.
    
    Signals:
        progress(int): Loading progress 0-100
        stage_changed(str): Current loading stage description
        finished_loading(VideoLoadResult): Loading complete with result
        error_occurred(str): Error message if loading failed
    """
    
    progress = Signal(int)
    stage_changed = Signal(str)
    finished_loading = Signal(object)  # VideoLoadResult
    error_occurred = Signal(str)
    
    # Supported video extensions
    VIDEO_EXTENSIONS = ['.avi', '.mp4', '.mov', '.mkv', '.wmv', '.webm']
    
    def __init__(self, filepath: str, loop: bool = True, grayscale: bool = True, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.loop = loop
        self.grayscale = grayscale
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the loading operation."""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled
    
    @classmethod
    def is_video_file(cls, filepath: str) -> bool:
        """Check if file is a supported video format."""
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.VIDEO_EXTENSIONS
    
    def run(self):
        """Execute the loading operation in background thread."""
        try:
            result = self._load_video()
            if not self._cancelled:
                self.finished_loading.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.error_occurred.emit(str(e))
    
    def _load_video(self) -> VideoLoadResult:
        """
        Load video file with progress reporting.
        
        Returns:
            VideoLoadResult with streamer
        """
        import fast
        
        result = VideoLoadResult(
            success=False,
            filepath=self.filepath
        )
        
        # Stage 1: Validate file
        self.stage_changed.emit("驗證影片檔案...")
        self.progress.emit(10)
        
        if not os.path.exists(self.filepath):
            result.error_message = "檔案不存在"
            return result
        
        if self._cancelled:
            return result
        
        # Stage 2: Create MovieStreamer
        self.stage_changed.emit("建立影片串流器...")
        self.progress.emit(50)
        
        try:
            streamer = fast.MovieStreamer.create(
                self.filepath,
                grayscale=self.grayscale,
                loop=self.loop
            )
            
            result.streamer = streamer
            result.success = True
            self.progress.emit(100)
            
        except Exception as e:
            result.error_message = f"無法載入影片: {e}"
        
        return result
