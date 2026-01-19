#!/usr/bin/env python3
"""
Test FAST coordinate system to understand how it works.
"""
import fast
import numpy as np

# Create a simple 512x512 test image with visible features
print("Creating test image 512x512...")
test_data = np.zeros((512, 512), dtype=np.uint8)
# Fill with gray background
test_data[:] = 50
# Draw a cross at center (brighter)
test_data[256, :] = 200  # horizontal line at row 256
test_data[:, 256] = 200  # vertical line at col 256
# Draw corners - make them brighter
test_data[0:30, 0:30] = 255     # top-left corner marker
test_data[0:30, -30:] = 255     # top-right corner marker
test_data[-30:, 0:30] = 255     # bottom-left corner marker
test_data[-30:, -30:] = 255     # bottom-right corner marker
# Mark center with a box
test_data[240:272, 240:272] = 255  # center marker

# Create FAST image
image = fast.Image.createFromArray(test_data)
print(f"Image size: {image.getWidth()} x {image.getHeight()}")
print(f"Image spacing: {image.getSpacing()}")

# Create window first
window = fast.SimpleWindow2D.create()
window.set2DMode()
window.setTitle("FAST Coordinate Test - Close window to exit")

# Get the view from window
view = window.getView()
view.set2DMode()
view.setBackgroundColor(fast.Color.Black())

# Add image renderer
img_renderer = fast.ImageRenderer.create()
img_renderer.addInputData(image)
view.addRenderer(img_renderer)

# Create test lines at known pixel positions
print("Drawing test lines:")
print("  RED:   (0,0) to (100,100) - should be top-left diagonal")
print("  GREEN: (100,100) to (256,256) - should go toward center") 
print("  BLUE:  (256,256) to (511,511) - should be center to bottom-right")
print("  CYAN:  (0,256) to (512,256) - horizontal center line")
print("  MAGENTA:(256,0) to (256,512) - vertical center line")

vertices = [
    fast.MeshVertex([0.0, 0.0, 0.0]),      # 0: top-left
    fast.MeshVertex([100.0, 100.0, 0.0]),  # 1
    fast.MeshVertex([256.0, 256.0, 0.0]),  # 2: center
    fast.MeshVertex([511.0, 511.0, 0.0]),  # 3: bottom-right
    fast.MeshVertex([0.0, 256.0, 0.0]),    # 4: left-middle
    fast.MeshVertex([512.0, 256.0, 0.0]),  # 5: right-middle
    fast.MeshVertex([256.0, 0.0, 0.0]),    # 6: top-middle
    fast.MeshVertex([256.0, 512.0, 0.0]),  # 7: bottom-middle
]

lines = [
    fast.MeshLine(0, 1, fast.Color.Red()),      # red diagonal from origin
    fast.MeshLine(1, 2, fast.Color.Green()),    # green to center
    fast.MeshLine(2, 3, fast.Color.Blue()),     # blue to bottom-right
    fast.MeshLine(4, 5, fast.Color.Cyan()),     # cyan horizontal
    fast.MeshLine(6, 7, fast.Color.Magenta()),  # magenta vertical
]

mesh = fast.Mesh.create(vertices, lines, [])
line_renderer = fast.LineRenderer.create(fast.Color.White(), 4.0, True)
line_renderer.addInputData(mesh)
view.addRenderer(line_renderer)

# Start window
print("\nStarting window - observe where the lines appear relative to image markers")
print("Press R to reset view if needed")
window.start()
