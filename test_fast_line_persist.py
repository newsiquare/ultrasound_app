#!/usr/bin/env python3
"""
Test FAST LineRenderer with real DICOM streamer (like main app).
"""
import fast
import sys
import os

# Find a DICOM file
dicom_path = None
test_dirs = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    "/tmp"
]
for d in test_dirs:
    if os.path.exists(d):
        for f in os.listdir(d):
            if f.endswith('.dcm'):
                dicom_path = os.path.join(d, f)
                break
    if dicom_path:
        break

if not dicom_path:
    print("Please provide a DICOM file path as argument")
    print("Usage: python3 test_fast_line_persist.py /path/to/file.dcm")
    if len(sys.argv) > 1:
        dicom_path = sys.argv[1]
    else:
        sys.exit(1)

print(f"Using DICOM: {dicom_path}")

# Create streamer for multi-frame DICOM
streamer = fast.MovieStreamer.create(dicom_path, True)

# Create window
window = fast.SimpleWindow2D.create()
window.set2DMode()
window.setTitle("FAST LineRenderer + DICOM Test")

view = window.getView()
view.set2DMode()

# Image renderer connected to streamer
img_renderer = fast.ImageRenderer.create()
img_renderer.connect(streamer)
view.addRenderer(img_renderer)

# LineRenderer with static line
print("Creating LineRenderer...")
line_renderer = fast.LineRenderer.create(fast.Color.Cyan(), 3.0, True)

vertices = [
    fast.MeshVertex([200.0, 200.0, 0.0]),
    fast.MeshVertex([600.0, 600.0, 0.0]),
]
lines = [fast.MeshLine(0, 1, fast.Color.Cyan())]
mesh = fast.Mesh.create(vertices, lines, [])
line_renderer.addInputData(mesh)
view.addRenderer(line_renderer)

print("Starting window - does the cyan line persist while video plays?")
window.start()
