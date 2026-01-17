import fast
import sys

def verify():
    print("Verifying FAST installation...")
    try:
        # Version is printed by the banner usually, or we can check fast.Config.getDocumentationUrl() etc.
        print("FAST imported successfully.")
        # Try creating a simple object
        importer = fast.ImageFileImporter.create("non_existent_file.dcm")
        print("FAST objects created successfully.")
    except ImportError:
        print("FAST (pyfast) is not installed or import failed.")
        sys.exit(1)
    except Exception as e:
        print(f"FAST verification error: {e}")
        # Depending on the error (e.g. file not found is expected here but object creation worked), 
        # we might still be good.
        if "No such file" in str(e):
             print("Import mechanism working (File not found detected).")
        else:
             sys.exit(1)
    
    print("FAST environment check passed.")

if __name__ == "__main__":
    verify()
