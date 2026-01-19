#!/usr/bin/env python3
"""
Test FAST LineRenderer with DICOM video playback.
"""
import fast
import sys

dicom_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/siquarepan/Downloads/055829-00000000.dcm"
print(f"Using DICOM: {dicom_path}")

# Use the same streamer as main app
from src.pipelines import create_playback_pipeline
streamer = create_playback_pipeline(dicom_path)

if not streamer:
    print("Failed to create streamer")
    sys.exit(1)

print("Streamer created successfully")

# Create SimpleWindow
window = fast.SimpleWindow2D.create()
window.set2DMode()
window.setTitle("Test LineRenderer with Video")

view = window.getView()
view.set2DMode()

# Image renderer
img_renderer = fast.ImageRenderer.create()
img_renderer.connect(streamer)
view.addRenderer(img_renderer)

# Line renderer with static mesh
print("Creating LineRenderer...")
line_renderer = fast.LineRenderer.create(fast.Color.Cyan(), 4.0, True)

vertices = [
    fast.MeshVertex([200.0, 200.0, 0.0]),
    fast.MeshVertex([700.0, 500.0, 0.0]),
]
lines = [fast.MeshLine(0, 1, fast.Color.Cyan())]
mesh = fast.Mesh.create(vertices, lines, [])

line_renderer.addInputData(mesh)
view.addRenderer(line_renderer)

# Don't use ComputationThread in standalone test - causes Qt thread issues
# The main app handles this properly via QGLWidget embedding

print("Starting window...")
window.start()
print("Window closed")
