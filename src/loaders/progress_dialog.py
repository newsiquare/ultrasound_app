"""
Progress dialog for async loading operations.

Provides visual feedback during file loading with cancel support.
"""

from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame
)
from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QFont


class LoadProgressDialog(QDialog):
    """
    Modal progress dialog for file loading operations.
    
    Features:
    - Progress bar with percentage
    - Stage description label
    - Cancel button
    - Dark theme matching the main application
    """
    
    # Signal emitted when user clicks cancel
    cancelled = Signal()
    
    def __init__(self, parent=None, title: str = "載入檔案"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(400, 150)
        self.setWindowFlags(
            Qt.Dialog | 
            Qt.CustomizeWindowHint | 
            Qt.WindowTitleHint
        )
        
        self._setup_ui()
        self._apply_style()
    
    def _setup_ui(self):
        """Setup dialog UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # File name label
        self.file_label = QLabel("準備載入...")
        self.file_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.file_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.file_label)
        
        # Stage description
        self.stage_label = QLabel("初始化...")
        self.stage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stage_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)
        
        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _apply_style(self):
        """Apply dark theme styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #3e3e42;
                border-radius: 4px;
                background-color: #2d2d30;
                text-align: center;
                color: #ffffff;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:pressed {
                background-color: #0078d4;
            }
        """)
    
    def set_filename(self, filename: str):
        """Set the filename being loaded."""
        # Truncate long filenames
        if len(filename) > 45:
            filename = "..." + filename[-42:]
        self.file_label.setText(f"載入: {filename}")
    
    def set_stage(self, stage: str):
        """Set the current loading stage description."""
        self.stage_label.setText(stage)
    
    def set_progress(self, value: int):
        """Set progress bar value (0-100)."""
        self.progress_bar.setValue(value)
    
    def _on_cancel(self):
        """Handle cancel button click."""
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("取消中...")
        self.stage_label.setText("正在取消...")
        self.cancelled.emit()
    
    def close_on_complete(self):
        """Close dialog after loading completes."""
        self.accept()
    
    def close_on_cancel(self):
        """Close dialog after cancellation."""
        self.reject()
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        # Emit cancelled if closed by X button
        if self.result() != QDialog.Accepted:
            self.cancelled.emit()
        super().closeEvent(event)
