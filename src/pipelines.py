import fast
import os

import fast
import os
import pydicom
import numpy as np

class NumpyImageSource(fast.PythonProcessObject):
    """
    Streams frames from a numpy array (Frames, H, W).
    Uses timer-based updates for animation.
    """
    def __init__(self, data, framerate=30):
        super().__init__()
        self.createOutputPort(0)
        self.data = data
        self.frame_idx = 0
        self.framerate = framerate
        self.last_time = 0
        
    def execute(self):
        import time
        current_time = time.time()
        
        # Control framerate
        if self.last_time > 0:
            elapsed = current_time - self.last_time
            target_interval = 1.0 / self.framerate
            if elapsed < target_interval:
                time.sleep(target_interval - elapsed)
        
        self.last_time = time.time()
        
        frame_data = self.data[self.frame_idx]
        frame_data = np.ascontiguousarray(frame_data)
        
        try:
            image = fast.Image.createFromArray(frame_data)
            if self.frame_idx == 0:
                print(f"FAST Image Created: {image.getWidth()}x{image.getHeight()}, Channels: {image.getNrOfChannels()}, Type: {image.getDataType()}")
            self.addOutputData(0, image)
        except Exception as e:
            print(f"Error creating FAST image at frame {self.frame_idx}: {e}")
            
        # Loop through frames
        self.frame_idx = (self.frame_idx + 1) % self.data.shape[0]
        
        # Mark as modified to trigger re-execution
        self.setModified(True)


# Alias for compatibility
NumpyStreamer = NumpyImageSource

def save_frames_as_mhd(arr, temp_dir):
    """
    Save numpy array frames as MHD files for FAST ImageFileStreamer.
    Returns the file pattern path.
    """
    import tempfile
    import shutil
    
    # Create temp directory if not exists
    os.makedirs(temp_dir, exist_ok=True)
    
    print(f"Saving {arr.shape[0]} frames to temporary MHD files...")
    
    for i in range(arr.shape[0]):
        frame = arr[i]
        # Save as raw data
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
    
    print(f"Saved {arr.shape[0]} frames to {temp_dir}")
    return os.path.join(temp_dir, "frame_#.mhd")


def is_dicom_compressed(filepath):
    """
    Check if a DICOM file uses compressed transfer syntax.
    Returns (is_compressed, transfer_syntax_uid, transfer_syntax_name)
    """
    try:
        # Read only metadata, not pixel data (faster)
        ds = pydicom.dcmread(filepath, stop_before_pixels=True, force=True)
        
        # Get Transfer Syntax UID
        ts_uid = str(ds.file_meta.TransferSyntaxUID) if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID') else None
        
        if ts_uid is None:
            return True, None, "Unknown (assuming compressed)"
        
        # Uncompressed Transfer Syntaxes
        uncompressed_syntaxes = {
            '1.2.840.10008.1.2': 'Implicit VR Little Endian',
            '1.2.840.10008.1.2.1': 'Explicit VR Little Endian', 
            '1.2.840.10008.1.2.2': 'Explicit VR Big Endian',
        }
        
        if ts_uid in uncompressed_syntaxes:
            return False, ts_uid, uncompressed_syntaxes[ts_uid]
        else:
            # Look up common compressed formats
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
        print(f"Warning: Could not determine transfer syntax: {e}")
        return True, None, "Unknown (assuming compressed)"


def create_playback_pipeline(filepath, loop=True):
    """
    Creates a pipeline to play back a file.
    Smart switching: uses DICOMMultiFrameStreamer for uncompressed DICOM,
    falls back to pydicom + ImageFileStreamer for compressed DICOM.
    """
    is_dicom = filepath.lower().endswith('.dcm')
    
    if not is_dicom:
        # Use native FAST importer for non-DICOM (images/videos)
        video_extensions = ['.avi', '.mp4', '.mov', '.mkv', '.wmv']
        if any(filepath.lower().endswith(ext) for ext in video_extensions):
            return fast.MovieStreamer.create(filepath, grayscale=True, loop=loop)
        else:
            return fast.ImageFileImporter.create(filepath)
    
    # --- DICOM file handling ---
    
    # Check if compressed
    is_compressed, ts_uid, ts_name = is_dicom_compressed(filepath)
    print(f"DICOM Transfer Syntax: {ts_name}")
    
    if not is_compressed:
        # Try FAST's native DICOMMultiFrameStreamer (faster, no temp files)
        try:
            print("Using FAST DICOMMultiFrameStreamer (uncompressed DICOM)...")
            streamer = fast.DICOMMultiFrameStreamer.create(
                filepath,
                loop=loop,
                grayscale=True,
                cropToROI=False,
            )
            print("DICOMMultiFrameStreamer created successfully")
            return streamer
        except Exception as e:
            print(f"DICOMMultiFrameStreamer failed: {e}")
            print("Falling back to pydicom method...")
    else:
        print("Compressed DICOM detected, using pydicom method...")
    
    # Fallback: Use pydicom + save to MHD + ImageFileStreamer
    try:
        from pydicom.pixel_data_handlers.util import convert_color_space
        import tempfile
        
        print(f"Loading DICOM with pydicom: {filepath}")
        ds = pydicom.dcmread(filepath, force=True)
        
        if not hasattr(ds, 'PixelData'):
            raise ValueError("DICOM file has no Pixel Data")

        arr = ds.pixel_array
        print(f"Loaded DICOM. Shape: {arr.shape}, Dtype: {arr.dtype}")
        print(f"Min: {np.min(arr)}, Max: {np.max(arr)}")
        
        # Handle Color Space (YBR -> RGB)
        photometric = ds.get('PhotometricInterpretation', 'MONOCHROME2')
        if 'YBR' in photometric:
            print(f"Converting {photometric} to RGB...")
            arr = convert_color_space(arr, photometric, 'RGB')
        
        # Convert to grayscale for B-mode display
        if arr.ndim == 4 and arr.shape[3] == 3:
            print("Converting RGB to Grayscale...")
            arr = np.mean(arr, axis=3).astype(np.uint8)
        elif arr.ndim == 3 and arr.shape[2] == 3:
            print("Converting RGB to Grayscale...")
            arr = np.mean(arr, axis=2).astype(np.uint8)
            
        # Ensure proper shape (Frames, H, W)
        if ds.get('NumberOfFrames', 1) == 1:
            if arr.ndim == 2:
                arr = arr[np.newaxis, ...]
        
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)
            
        print(f"Final array shape: {arr.shape}, Dtype: {arr.dtype}")
        print(f"Final Min: {np.min(arr)}, Max: {np.max(arr)}")
        
        # Save frames to temporary MHD files
        temp_dir = tempfile.mkdtemp(prefix="fast_ultrasound_")
        file_pattern = save_frames_as_mhd(arr, temp_dir)
        
        # Use FAST's native ImageFileStreamer
        print(f"Creating ImageFileStreamer with pattern: {file_pattern}")
        
        # Get framerate from DICOM if available
        framerate = 30
        try:
            fr = ds.get('FrameTime', None)  # Frame time in ms
            if fr:
                framerate = int(1000 / float(fr))
            else:
                fr = ds.get('RecommendedDisplayFrameRate', 30)
                framerate = int(fr) if fr else 30
        except:
            pass
        
        print(f"Using framerate: {framerate} fps")
        
        streamer = fast.ImageFileStreamer.create(
            file_pattern,
            loop=loop,
            framerate=framerate,
            useTimestamps=False  # Faster seeking
        )
        print("ImageFileStreamer created successfully")
        return streamer
        
    except Exception as e:
        print(f"Error loading DICOM: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_streaming_pipeline(source_id=0):
    """
    Creates a pipeline for real-time streaming.
    If no physical device, we can verify with a specific Streamer or OpenIGTLink.
    """
    # Using a dummy streamer for demonstration if no device present
    # fast.Streamer.create() or fast.Camera.create() for webcam test
    streamer = fast.ImageFileImporter.create("test_data/US-2D_#.mhd") # Example placeholder
    # In a real scenario:
    # streamer = fast.ClariusStreamer.create() 
    # or 
    # streamer = fast.OpenIGTLinkStreamer.create()
    
    return streamer

def create_display_pipeline(input_process):
    """
    Adds display processing to the pipeline.
    """
    renderer = fast.ImageRenderer.create()
    renderer.connect(input_process)
    return renderer
