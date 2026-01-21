"""
Async DICOM loader using QThread.

Provides non-blocking loading of DICOM files with progress reporting.
"""

import os
import tempfile
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from PySide2.QtCore import QThread, Signal


@dataclass
class DicomLoadResult:
    """Result object from DICOM loading operation."""
    success: bool
    filepath: str
    streamer: Any = None  # FAST streamer object
    metadata: Dict[str, Any] = field(default_factory=dict)
    pixel_spacing: Optional[float] = None
    image_width: int = 0
    image_height: int = 0
    num_frames: int = 1
    framerate: int = 30
    error_message: str = ""
    temp_dir: Optional[str] = None  # Temp directory to clean up later


class DicomLoadWorker(QThread):
    """
    Background worker for loading DICOM files.
    
    Signals:
        progress(int): Loading progress 0-100
        stage_changed(str): Current loading stage description
        finished_loading(DicomLoadResult): Loading complete with result
        error_occurred(str): Error message if loading failed
    """
    
    # Signals
    progress = Signal(int)
    stage_changed = Signal(str)
    finished_loading = Signal(object)  # DicomLoadResult
    error_occurred = Signal(str)
    
    def __init__(self, filepath: str, loop: bool = True, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.loop = loop
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the loading operation."""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled
    
    def run(self):
        """Execute the loading operation in background thread."""
        try:
            result = self._load_dicom()
            if not self._cancelled:
                self.finished_loading.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.error_occurred.emit(str(e))
    
    def _load_dicom(self) -> DicomLoadResult:
        """
        Load DICOM file with progress reporting.
        
        Returns:
            DicomLoadResult with streamer and metadata
        """
        import fast
        import pydicom
        from pydicom.pixel_data_handlers.util import convert_color_space
        
        result = DicomLoadResult(
            success=False,
            filepath=self.filepath
        )
        
        # Stage 1: Read metadata (5%)
        self.stage_changed.emit("讀取 DICOM 中繼資料...")
        self.progress.emit(2)
        
        if self._cancelled:
            return result
        
        try:
            ds = pydicom.dcmread(self.filepath, stop_before_pixels=True, force=True)
            
            # Extract metadata
            result.metadata = {
                'PatientName': str(ds.get('PatientName', 'Anonymous')),
                'StudyDate': str(ds.get('StudyDate', '')),
                'Modality': str(ds.get('Modality', 'US')),
                'Manufacturer': str(ds.get('Manufacturer', '')),
                'InstitutionName': str(ds.get('InstitutionName', '')),
                'NumberOfFrames': str(ds.get('NumberOfFrames', 1)),
            }
            
            # Extract dimensions
            if hasattr(ds, 'Columns') and hasattr(ds, 'Rows'):
                result.image_width = int(ds.Columns)
                result.image_height = int(ds.Rows)
            
            # Extract pixel spacing
            if hasattr(ds, 'PixelSpacing') and ds.PixelSpacing:
                result.pixel_spacing = float(ds.PixelSpacing[0])
            elif hasattr(ds, 'SequenceOfUltrasoundRegions'):
                regions = ds.SequenceOfUltrasoundRegions
                if regions and len(regions) > 0:
                    region = regions[0]
                    if hasattr(region, 'PhysicalDeltaX'):
                        result.pixel_spacing = float(region.PhysicalDeltaX) * 10
            
            result.num_frames = int(ds.get('NumberOfFrames', 1))
            
        except Exception as e:
            result.error_message = f"無法讀取 DICOM 中繼資料: {e}"
            return result
        
        self.progress.emit(5)
        
        if self._cancelled:
            return result
        
        # Stage 2: Check compression (10%)
        self.stage_changed.emit("檢測壓縮格式...")
        self.progress.emit(8)
        
        is_compressed, ts_uid, ts_name = self._is_dicom_compressed()
        
        self.progress.emit(10)
        
        if self._cancelled:
            return result
        
        # Stage 3: Create streamer
        if not is_compressed:
            # Try FAST native streamer for uncompressed DICOM
            self.stage_changed.emit("使用 FAST 原生載入器...")
            self.progress.emit(15)
            
            try:
                streamer = fast.DICOMMultiFrameStreamer.create(
                    self.filepath,
                    loop=self.loop,
                    grayscale=True,
                    cropToROI=False,
                )
                result.streamer = streamer
                result.success = True
                self.progress.emit(100)
                return result
            except Exception as e:
                print(f"FAST DICOMMultiFrameStreamer failed: {e}, falling back to pydicom")
        
        # Fallback: Use pydicom decompression
        self.stage_changed.emit("解壓縮 DICOM 像素資料...")
        self.progress.emit(20)
        
        if self._cancelled:
            return result
        
        try:
            # Read full DICOM with pixel data
            ds = pydicom.dcmread(self.filepath, force=True)
            
            if not hasattr(ds, 'PixelData'):
                result.error_message = "DICOM 檔案沒有像素資料"
                return result
            
            self.progress.emit(30)
            
            if self._cancelled:
                return result
            
            # Stage 4: Decompress pixel array
            self.stage_changed.emit("讀取像素陣列...")
            arr = ds.pixel_array
            
            self.progress.emit(50)
            
            if self._cancelled:
                return result
            
            # Handle color space conversion
            photometric = ds.get('PhotometricInterpretation', 'MONOCHROME2')
            if 'YBR' in photometric:
                self.stage_changed.emit("轉換色彩空間...")
                arr = convert_color_space(arr, photometric, 'RGB')
            
            self.progress.emit(55)
            
            if self._cancelled:
                return result
            
            # Convert to grayscale if needed
            if arr.ndim == 4 and arr.shape[3] == 3:
                self.stage_changed.emit("轉換為灰階...")
                arr = np.mean(arr, axis=3).astype(np.uint8)
            elif arr.ndim == 3 and arr.shape[2] == 3:
                self.stage_changed.emit("轉換為灰階...")
                arr = np.mean(arr, axis=2).astype(np.uint8)
            
            # Ensure proper shape
            if ds.get('NumberOfFrames', 1) == 1:
                if arr.ndim == 2:
                    arr = arr[np.newaxis, ...]
            
            if arr.dtype != np.uint8:
                arr = arr.astype(np.uint8)
            
            result.num_frames = arr.shape[0]
            
            self.progress.emit(60)
            
            if self._cancelled:
                return result
            
            # Stage 5: Save to temporary MHD files
            self.stage_changed.emit("寫入暫存檔案...")
            temp_dir = tempfile.mkdtemp(prefix="fast_ultrasound_")
            result.temp_dir = temp_dir
            
            total_frames = arr.shape[0]
            for i in range(total_frames):
                if self._cancelled:
                    return result
                
                frame = arr[i]
                raw_path = os.path.join(temp_dir, f"frame_{i}.raw")
                mhd_path = os.path.join(temp_dir, f"frame_{i}.mhd")
                
                # Write raw data
                frame.astype(np.uint8).tofile(raw_path)
                
                # Write MHD header
                h, w = frame.shape
                with open(mhd_path, 'w') as f:
                    f.write(f"ObjectType = Image\n")
                    f.write(f"NDims = 2\n")
                    f.write(f"DimSize = {w} {h}\n")
                    f.write(f"ElementType = MET_UCHAR\n")
                    f.write(f"ElementDataFile = frame_{i}.raw\n")
                
                # Update progress (60-90%)
                progress = 60 + int(30 * (i + 1) / total_frames)
                self.progress.emit(progress)
            
            file_pattern = os.path.join(temp_dir, "frame_#.mhd")
            
            self.progress.emit(90)
            
            if self._cancelled:
                return result
            
            # Stage 6: Create ImageFileStreamer
            self.stage_changed.emit("建立串流管道...")
            
            # Get framerate
            framerate = 30
            try:
                fr = ds.get('FrameTime', None)
                if fr:
                    framerate = int(1000 / float(fr))
                else:
                    fr = ds.get('RecommendedDisplayFrameRate', 30)
                    framerate = int(fr) if fr else 30
            except:
                pass
            
            result.framerate = framerate
            
            streamer = fast.ImageFileStreamer.create(
                file_pattern,
                loop=self.loop,
                framerate=framerate,
                useTimestamps=False
            )
            
            result.streamer = streamer
            result.success = True
            self.progress.emit(100)
            
        except Exception as e:
            result.error_message = f"載入失敗: {e}"
            import traceback
            traceback.print_exc()
        
        return result
    
    def _is_dicom_compressed(self):
        """Check if DICOM file uses compressed transfer syntax."""
        import pydicom
        
        try:
            ds = pydicom.dcmread(self.filepath, stop_before_pixels=True, force=True)
            
            ts_uid = None
            if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID'):
                ts_uid = str(ds.file_meta.TransferSyntaxUID)
            
            if ts_uid is None:
                return True, None, "Unknown"
            
            uncompressed = {
                '1.2.840.10008.1.2': 'Implicit VR Little Endian',
                '1.2.840.10008.1.2.1': 'Explicit VR Little Endian',
                '1.2.840.10008.1.2.2': 'Explicit VR Big Endian',
            }
            
            if ts_uid in uncompressed:
                return False, ts_uid, uncompressed[ts_uid]
            
            compressed_names = {
                '1.2.840.10008.1.2.5': 'RLE Lossless',
                '1.2.840.10008.1.2.4.50': 'JPEG Baseline',
                '1.2.840.10008.1.2.4.51': 'JPEG Extended',
                '1.2.840.10008.1.2.4.70': 'JPEG Lossless',
                '1.2.840.10008.1.2.4.80': 'JPEG-LS Lossless',
                '1.2.840.10008.1.2.4.81': 'JPEG-LS Near-lossless',
                '1.2.840.10008.1.2.4.90': 'JPEG 2000 Lossless',
                '1.2.840.10008.1.2.4.91': 'JPEG 2000',
            }
            name = compressed_names.get(ts_uid, f'Compressed ({ts_uid})')
            return True, ts_uid, name
            
        except Exception as e:
            return True, None, "Unknown"
