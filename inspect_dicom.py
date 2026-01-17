import pydicom
import sys

def inspect_dicom(filepath):
    print(f"Inspecting file: {filepath}")
    try:
        ds = pydicom.dcmread(filepath)
        print("Successfully read DICOM file.")
        print(f"SOP Class UID: {ds.get('SOPClassUID', 'N/A')}")
        print(f"Transfer Syntax UID: {ds.file_meta.TransferSyntaxUID}")
        print(f"Modality: {ds.get('Modality', 'N/A')}")
        print(f"Rows: {ds.get('Rows', 'N/A')}")
        print(f"Columns: {ds.get('Columns', 'N/A')}")
        print(f"Photometric Interpretation: {ds.get('PhotometricInterpretation', 'N/A')}")
        
        if 'PixelData' in ds:
            print(f"Pixel Data present. Length: {len(ds.PixelData)}")
            try:
                arr = ds.pixel_array
                print(f"Pixel array shape: {arr.shape}")
            except Exception as e:
                print(f"Failed to decode pixel_array: {e}")
        else:
            print("No Pixel Data found.")
            
    except Exception as e:
        print(f"Error reading DICOM file with pydicom: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_dicom.py <path_to_dicom>")
        sys.exit(1)
    
    inspect_dicom(sys.argv[1])
