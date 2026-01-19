#!/usr/bin/env python3
"""
測試 FAST View 在 2D 模式下的滑鼠交互和重置功能
"""
import sys
import os

# 在 import fast 之前先 import，確保 Qt 庫載入順序正確
import fast

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSizePolicy
)
from PySide2.QtOpenGL import QGLWidget
from PySide2.QtCore import Qt
from shiboken2 import wrapInstance


class TestWindow(QMainWindow):
    def __init__(self, dicom_path):
        super().__init__()
        self.dicom_path = dicom_path
        self.setWindowTitle("FAST Interaction Test")
        self.setMinimumSize(800, 600)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Info label
        self.info = QLabel("測試：1) 滾輪縮放 2) 拖曳平移 3) 按 R 鍵重置 4) 點擊按鈕重置")
        layout.addWidget(self.info)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        btn1 = QPushButton("recalculateCamera()")
        btn1.clicked.connect(self.test_recalculate)
        btn_layout.addWidget(btn1)
        
        btn2 = QPushButton("setAutoUpdateCamera + recalculate")
        btn2.clicked.connect(self.test_auto_update)
        btn_layout.addWidget(btn2)
        
        btn3 = QPushButton("setZoom(1.0)")
        btn3.clicked.connect(self.test_set_zoom)
        btn_layout.addWidget(btn3)
        
        btn4 = QPushButton("reinitialize()")
        btn4.clicked.connect(self.test_reinitialize)
        btn_layout.addWidget(btn4)
        
        layout.addLayout(btn_layout)
        
        # Create FAST view
        self.fast_view = fast.View()
        self.fast_view.set2DMode()
        self.fast_view.setBackgroundColor(fast.Color(0.1, 0.1, 0.1))
        self.fast_view.setAutoUpdateCamera(True)
        
        # Wrap as Qt widget
        self.fast_widget = wrapInstance(int(self.fast_view.asQGLWidget()), QGLWidget)
        self.fast_widget.setMinimumSize(400, 300)
        self.fast_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fast_widget.setFocusPolicy(Qt.StrongFocus)
        self.fast_widget.setMouseTracking(True)
        
        layout.addWidget(self.fast_widget, 1)
        
        # Load file and setup pipeline
        self.setup_pipeline()
    
    def setup_pipeline(self):
        try:
            # 使用主程式的 pipeline 函數（支援壓縮 DICOM）
            from src.pipelines import create_playback_pipeline
            
            streamer = create_playback_pipeline(self.dicom_path, loop=True)
            
            # Create renderer
            renderer = fast.ImageRenderer.create()
            renderer.connect(streamer)
            
            # Add to view
            self.fast_view.addRenderer(renderer)
            
            # Create and start computation thread
            self.thread = fast.ComputationThread.create()
            self.thread.addView(self.fast_view)
            self.thread.start()
            
            self.info.setText("載入成功！測試滾輪縮放、拖曳平移、按 R 鍵")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.info.setText(f"Error: {e}")
    
    def test_recalculate(self):
        try:
            self.fast_view.recalculateCamera()
            self.info.setText("recalculateCamera() 已調用")
        except Exception as e:
            self.info.setText(f"Error: {e}")
    
    def test_auto_update(self):
        try:
            self.fast_view.setAutoUpdateCamera(True)
            self.fast_view.recalculateCamera()
            self.info.setText("setAutoUpdateCamera(True) + recalculateCamera() 已調用")
        except Exception as e:
            self.info.setText(f"Error: {e}")
    
    def test_set_zoom(self):
        try:
            self.fast_view.setZoom(1.0)
            self.info.setText("setZoom(1.0) 已調用")
        except Exception as e:
            self.info.setText(f"Error: {e}")
    
    def test_reinitialize(self):
        try:
            self.fast_view.reinitialize()
            self.info.setText("reinitialize() 已調用")
        except Exception as e:
            self.info.setText(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_fast_interaction.py <dicom_file>")
        sys.exit(1)
    
    # 使用已存在的 QApplication（FAST 可能已創建）或創建新的
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    window = TestWindow(sys.argv[1])
    window.show()
    sys.exit(app.exec_())
