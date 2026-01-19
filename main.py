#!/usr/bin/env python3
"""
Ultrasound Imaging Software

A professional medical imaging application for viewing ultrasound DICOM files.

Usage:
    python main.py --file path/to/ultrasound.dcm       # Simple FAST GUI
    python main.py --qt --file path/to/ultrasound.dcm  # Professional Qt GUI
    python main.py --qt                                 # Qt GUI without file
"""

import fast
import sys
import os
import argparse


def get_file_info(filepath):
    """
    Extract file information for display in the GUI.
    For DICOM files, extract metadata using pydicom.
    """
    info = {
        'Filename': os.path.basename(filepath),
    }
    
    if filepath.lower().endswith('.dcm'):
        try:
            import pydicom
            ds = pydicom.dcmread(filepath, stop_before_pixels=True, force=True)
            
            # Extract useful metadata
            info['Patient'] = str(ds.get('PatientName', 'N/A'))
            info['Study Date'] = str(ds.get('StudyDate', 'N/A'))
            info['Modality'] = str(ds.get('Modality', 'US'))
            info['Frames'] = str(ds.get('NumberOfFrames', 1))
            info['Size'] = f"{ds.get('Columns', '?')} × {ds.get('Rows', '?')}"
            
            # Transfer Syntax
            if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID'):
                ts_uid = str(ds.file_meta.TransferSyntaxUID)
                ts_names = {
                    '1.2.840.10008.1.2': 'Implicit VR LE',
                    '1.2.840.10008.1.2.1': 'Explicit VR LE',
                    '1.2.840.10008.1.2.5': 'RLE Lossless',
                }
                info['Compression'] = ts_names.get(ts_uid, ts_uid[:20] + '...')
        except Exception as e:
            info['Note'] = f'Could not read DICOM metadata: {e}'
    else:
        # For non-DICOM files
        info['Type'] = filepath.split('.')[-1].upper()
        try:
            info['Size'] = f"{os.path.getsize(filepath) / 1024:.1f} KB"
        except:
            pass
    
    return info


def main():
    parser = argparse.ArgumentParser(
        description="Ultrasound Imaging Software",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --file path/to/ultrasound.dcm       # Simple FAST GUI
  python main.py --qt --file path/to/ultrasound.dcm  # Professional Qt GUI
  python main.py --qt                                 # Qt GUI (open file dialog)
  python main.py --stream                             # Streaming mode
        """
    )
    parser.add_argument('--file', type=str, help="Path to ultrasound file (DICOM, AVI, MP4, etc)")
    parser.add_argument('--stream', action='store_true', help="Enable streaming mode")
    parser.add_argument('--qt', action='store_true', help="Use professional Qt-based GUI")
    
    args = parser.parse_args()
    
    # Professional Qt GUI mode
    if args.qt:
        try:
            from src.qt_gui import run_qt_app
            print("Starting Professional Qt GUI...")
            sys.exit(run_qt_app(args.file))
        except ImportError as e:
            print(f"Error: Could not import Qt GUI module: {e}")
            print("\nMake sure PySide2 is installed:")
            print("  pip install pyside2==5.15.2.1")
            sys.exit(1)
    
    # Simple FAST GUI mode
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        
        print(f"Loading file: {args.file}")
        
        # Extract file info for display
        file_info = get_file_info(args.file)
        
        from _backup.gui import UltrasoundWindow
        window = UltrasoundWindow(mode='playback', filepath=args.file, file_info=file_info)
        window.run()
        
    elif args.stream:
        print("Starting streaming mode...")
        print("Note: Streaming requires a configured source in pipelines.py")
        from _backup.gui import UltrasoundWindow
        window = UltrasoundWindow(mode='stream')
        window.run()
        
    else:
        print("=" * 50)
        print("  Ultrasound Imaging Software")
        print("=" * 50)
        print("\nUsage options:\n")
        print("  Simple GUI:       python main.py --file <path>")
        print("  Professional GUI: python main.py --qt [--file <path>]")
        print()
        parser.print_help()


if __name__ == "__main__":
    main()
