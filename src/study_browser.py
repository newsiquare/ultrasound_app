"""
Study Browser Widget - Hierarchical DICOM file browser.

This module provides a tree-based file browser that organizes DICOM files
into a Patient → Study → Series hierarchy with thumbnail preview support.
"""

import os
import numpy as np

from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QLabel, QPushButton,
    QStyledItemDelegate, QAbstractItemView, QStyle
)
from PySide2.QtCore import Qt, QSize
from PySide2.QtGui import (
    QFont, QColor, QImage, QPixmap, QPainter,
    QStandardItemModel, QStandardItem
)


class ThumbnailCache:
    """LRU cache for series thumbnails."""
    
    def __init__(self, max_size=50):
        self.max_size = max_size
        self._cache = {}  # filepath -> QPixmap
        self._order = []  # LRU order
    
    def get(self, filepath):
        """Get thumbnail from cache."""
        if filepath in self._cache:
            # Move to end (most recently used)
            self._order.remove(filepath)
            self._order.append(filepath)
            return self._cache[filepath]
        return None
    
    def put(self, filepath, pixmap):
        """Add thumbnail to cache."""
        if filepath in self._cache:
            self._order.remove(filepath)
        elif len(self._cache) >= self.max_size:
            # Remove oldest
            oldest = self._order.pop(0)
            del self._cache[oldest]
        
        self._cache[filepath] = pixmap
        self._order.append(filepath)
    
    def has(self, filepath):
        return filepath in self._cache
    
    @staticmethod
    def generate_thumbnail(filepath, size=48):
        """Generate thumbnail from DICOM first frame."""
        try:
            import pydicom
            ds = pydicom.dcmread(filepath, stop_before_pixels=False)
            if hasattr(ds, 'pixel_array'):
                arr = ds.pixel_array
                # Handle multi-frame: take first frame
                if len(arr.shape) == 3:
                    arr = arr[0] if arr.shape[0] < arr.shape[2] else arr[:, :, 0]
                elif len(arr.shape) == 4:
                    arr = arr[0, :, :, 0]
                
                # Normalize to 0-255
                arr = arr.astype(np.float32)
                arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8) * 255
                arr = arr.astype(np.uint8)
                
                # Need to copy array to ensure contiguous memory
                arr = np.ascontiguousarray(arr)
                
                # Create QImage
                h, w = arr.shape[:2]
                if len(arr.shape) == 2:
                    img = QImage(arr.data, w, h, w, QImage.Format_Grayscale8)
                else:
                    img = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888)
                
                # Scale to thumbnail size
                pixmap = QPixmap.fromImage(img).scaled(
                    size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                return pixmap
        except Exception as e:
            print(f"Thumbnail generation failed for {filepath}: {e}")
        
        return None


class SeriesItemDelegate(QStyledItemDelegate):
    """Custom delegate for rendering Series items with thumbnails."""
    
    THUMBNAIL_SIZE = 48
    ITEM_HEIGHT = 56
    PADDING = 4
    
    def __init__(self, thumbnail_cache, parent=None):
        super().__init__(parent)
        self.thumbnail_cache = thumbnail_cache
        self._placeholder = self._create_placeholder()
    
    def _create_placeholder(self):
        """Create placeholder pixmap for loading thumbnails."""
        pixmap = QPixmap(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        pixmap.fill(QColor("#3e3e42"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#888888"))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "...")
        painter.end()
        return pixmap
    
    def paint(self, painter, option, index):
        """Custom paint for Series items."""
        # Check if this is a Series item
        item_type = index.data(Qt.UserRole + 2)
        
        if item_type != 'series':
            # Use default painting for Patient/Study/Other items
            super().paint(painter, option, index)
            return
        
        filepath = index.data(Qt.UserRole)
        
        # Draw selection background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#0078d4"))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#3e3e42"))
        
        # Get thumbnail
        thumbnail = self.thumbnail_cache.get(filepath) if filepath else None
        if thumbnail is None:
            thumbnail = self._placeholder
        
        # Draw thumbnail
        thumb_rect = option.rect.adjusted(self.PADDING, self.PADDING, 0, -self.PADDING)
        thumb_rect.setWidth(self.THUMBNAIL_SIZE)
        thumb_rect.setHeight(self.THUMBNAIL_SIZE)
        
        # Center thumbnail vertically
        y_offset = (option.rect.height() - self.THUMBNAIL_SIZE) // 2
        thumb_rect.moveTop(option.rect.top() + y_offset)
        
        painter.drawPixmap(thumb_rect, thumbnail)
        
        # Draw border around thumbnail
        painter.setPen(QColor("#555555"))
        painter.drawRect(thumb_rect)
        
        # Draw text (Series name and frame count)
        text_rect = option.rect.adjusted(
            self.THUMBNAIL_SIZE + self.PADDING * 2, self.PADDING,
            -self.PADDING, -self.PADDING
        )
        
        display_text = index.data(Qt.DisplayRole) or ""
        frame_info = index.data(Qt.UserRole + 3) or ""
        
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 10))
        
        # Draw series name
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, display_text)
        
        # Draw frame info in gray
        if frame_info:
            painter.setPen(QColor("#888888"))
            painter.setFont(QFont("Segoe UI", 9))
            frame_rect = text_rect.adjusted(0, 18, 0, 0)
            painter.drawText(frame_rect, Qt.AlignLeft | Qt.AlignTop, frame_info)
    
    def sizeHint(self, option, index):
        """Return size hint for items."""
        item_type = index.data(Qt.UserRole + 2)
        if item_type == 'series':
            return QSize(option.rect.width(), self.ITEM_HEIGHT)
        return super().sizeHint(option, index)


class FileListWidget(QWidget):
    """Left panel with hierarchical file browser (Patient → Study → Series)."""
    
    # Data roles
    ROLE_FILEPATH = Qt.UserRole
    ROLE_METADATA = Qt.UserRole + 1
    ROLE_ITEM_TYPE = Qt.UserRole + 2  # 'patient', 'study', 'series', 'other', 'other_file'
    ROLE_FRAME_INFO = Qt.UserRole + 3
    ROLE_STUDY_KEY = Qt.UserRole + 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumbnail_cache = ThumbnailCache(max_size=50)
        self._patients = {}  # patient_key -> patient_item
        self._other_files_item = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Header row with title and icon buttons
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        
        header = QLabel(" Studies")
        header.setFont(QFont("lucide", 12, QFont.Bold))
        header.setStyleSheet("color: #ffffff; padding: 5px;")
        header_layout.addWidget(header)
        
        header_layout.addStretch()
        
        # Icon button style
        icon_btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                font-family: 'lucide';
                font-size: 14px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """
        
        # Open File button (icon only)
        self.open_file_btn = QPushButton("\ue0cd")  # file-plus
        self.open_file_btn.setFixedSize(28, 28)
        self.open_file_btn.setToolTip("Open File")
        self.open_file_btn.setStyleSheet(icon_btn_style)
        header_layout.addWidget(self.open_file_btn)
        
        # Open Folder button (icon only)
        self.open_folder_btn = QPushButton("\ue246")  # folder-open
        self.open_folder_btn.setFixedSize(28, 28)
        self.open_folder_btn.setToolTip("Open Folder")
        self.open_folder_btn.setStyleSheet(icon_btn_style)
        header_layout.addWidget(self.open_folder_btn)
        
        layout.addWidget(header_row)
        
        # Tree view for hierarchical display
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([""])
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setIndentation(16)
        self.tree_view.setAnimated(True)
        self.tree_view.setExpandsOnDoubleClick(False)
        self.tree_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Set custom delegate for thumbnails
        self.delegate = SeriesItemDelegate(self.thumbnail_cache, self)
        self.tree_view.setItemDelegate(self.delegate)
        
        self.tree_view.setStyleSheet("""
            QTreeView {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                outline: none;
            }
            QTreeView::item {
                padding: 4px;
                border-bottom: 1px solid #3e3e42;
            }
            QTreeView::item:selected {
                background-color: #0078d4;
            }
            QTreeView::item:hover {
                background-color: #3e3e42;
            }
            QTreeView::branch:has-children:closed {
                image: url(none);
                border-image: none;
            }
            QTreeView::branch:has-children:open {
                image: url(none);
                border-image: none;
            }
        """)
        layout.addWidget(self.tree_view)
        
        # Backward compatibility adapter
        self.file_list = _TreeViewListAdapter(self.tree_view, self)
        
        # Patient Info Section
        patient_header = QLabel(" Patient Info")
        patient_header.setFont(QFont("lucide", 11, QFont.Bold))
        patient_header.setStyleSheet("color: #ffffff; padding: 5px 5px 0px 5px; margin-top: 8px;")
        layout.addWidget(patient_header)
        
        # Patient info container
        self.patient_info = QLabel("No file loaded")
        self.patient_info.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                font-size: 11px;
                padding: 5px;
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)
        self.patient_info.setWordWrap(True)
        layout.addWidget(self.patient_info)
        
        # Info label
        self.info_label = QLabel("No files loaded")
        self.info_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def _get_or_create_patient_item(self, patient_key, patient_name, patient_id):
        """Get or create a patient item."""
        if patient_key in self._patients:
            return self._patients[patient_key]
        
        # Create new patient item
        display_name = f"👤 {patient_name}" if patient_name else "👤 Unknown"
        if patient_id:
            display_name += f" ({patient_id})"
        
        item = QStandardItem(display_name)
        item.setData('patient', self.ROLE_ITEM_TYPE)
        item.setEditable(False)
        
        # Bold font for patients
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        
        self.model.appendRow(item)
        self._patients[patient_key] = item
        return item
    
    def _get_or_create_study_item(self, patient_item, study_key, study_date, study_desc):
        """Get or create a study item under a patient."""
        # Check if study already exists
        for i in range(patient_item.rowCount()):
            child = patient_item.child(i)
            if child and child.data(self.ROLE_STUDY_KEY) == study_key:
                return child
        
        # Format date
        date_str = study_date or "Unknown Date"
        if len(date_str) == 8:
            date_str = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
        
        display_name = f"📋 {date_str}"
        if study_desc:
            display_name += f" - {study_desc}"
        
        item = QStandardItem(display_name)
        item.setData('study', self.ROLE_ITEM_TYPE)
        item.setData(study_key, self.ROLE_STUDY_KEY)
        item.setEditable(False)
        
        patient_item.appendRow(item)
        return item
    
    def _get_or_create_other_files_item(self):
        """Get or create the 'Other Files' container."""
        if self._other_files_item is None:
            item = QStandardItem("📁 其他檔案")
            item.setData('other', self.ROLE_ITEM_TYPE)
            item.setEditable(False)
            self.model.appendRow(item)
            self._other_files_item = item
        return self._other_files_item
    
    def add_file(self, filepath, info=None):
        """Add a file to the hierarchical list."""
        if self.has_file(filepath):
            return
        
        is_dicom = filepath.lower().endswith('.dcm')
        
        if is_dicom:
            self._add_dicom_file(filepath, info)
        else:
            self._add_other_file(filepath, info)
        
        self.update_info()
    
    def _add_dicom_file(self, filepath, info=None):
        """Add a DICOM file with hierarchy extraction."""
        try:
            import pydicom
            ds = pydicom.dcmread(filepath, stop_before_pixels=True)
            
            # Extract DICOM hierarchy info
            patient_name = str(getattr(ds, 'PatientName', 'Unknown'))
            patient_id = str(getattr(ds, 'PatientID', ''))
            study_date = str(getattr(ds, 'StudyDate', ''))
            study_desc = str(getattr(ds, 'StudyDescription', ''))
            series_num = str(getattr(ds, 'SeriesNumber', '1'))
            series_desc = str(getattr(ds, 'SeriesDescription', ''))
            num_frames = getattr(ds, 'NumberOfFrames', 1)
            
            # Create hierarchy keys
            patient_key = f"{patient_name}_{patient_id}"
            study_key = f"{study_date}_{study_desc}"
            
            # Get or create hierarchy items
            patient_item = self._get_or_create_patient_item(patient_key, patient_name, patient_id)
            study_item = self._get_or_create_study_item(patient_item, study_key, study_date, study_desc)
            
            # Create series item
            series_name = series_desc if series_desc else f"Series {series_num}"
            item = QStandardItem(series_name)
            item.setData(filepath, self.ROLE_FILEPATH)
            item.setData('series', self.ROLE_ITEM_TYPE)
            item.setData(f"{num_frames} 幀", self.ROLE_FRAME_INFO)
            item.setEditable(False)
            
            # Store metadata
            metadata = {
                'PatientName': patient_name,
                'PatientID': patient_id,
                'StudyDate': study_date,
                'StudyDescription': study_desc,
                'SeriesNumber': series_num,
                'SeriesDescription': series_desc,
                'NumberOfFrames': num_frames,
                'Modality': str(getattr(ds, 'Modality', '')),
                'Manufacturer': str(getattr(ds, 'Manufacturer', '')),
                'InstitutionName': str(getattr(ds, 'InstitutionName', '')),
            }
            item.setData(metadata, self.ROLE_METADATA)
            item.setToolTip(f"{filepath}\n{num_frames} frames")
            
            study_item.appendRow(item)
            
            # Expand hierarchy
            self.tree_view.expand(self.model.indexFromItem(patient_item))
            self.tree_view.expand(self.model.indexFromItem(study_item))
            
            # Generate thumbnail
            self._generate_thumbnail_async(filepath)
            
        except Exception as e:
            print(f"Failed to parse DICOM hierarchy: {e}")
            self._add_other_file(filepath, info)
    
    def _add_other_file(self, filepath, info=None):
        """Add a non-DICOM file."""
        other_item = self._get_or_create_other_files_item()
        
        filename = os.path.basename(filepath)
        item = QStandardItem(f"📄 {filename}")
        item.setData(filepath, self.ROLE_FILEPATH)
        item.setData('other_file', self.ROLE_ITEM_TYPE)
        item.setEditable(False)
        
        if info:
            item.setToolTip(f"{filepath}\n{info}")
            item.setData(info, self.ROLE_METADATA)
        
        other_item.appendRow(item)
        self.tree_view.expand(self.model.indexFromItem(other_item))
    
    def _generate_thumbnail_async(self, filepath):
        """Generate thumbnail (sync for now)."""
        if not self.thumbnail_cache.has(filepath):
            pixmap = ThumbnailCache.generate_thumbnail(filepath, 48)
            if pixmap:
                self.thumbnail_cache.put(filepath, pixmap)
                self.tree_view.viewport().update()
    
    def has_file(self, filepath):
        """Check if file is already in the list."""
        return self._find_item_by_filepath(filepath) is not None
    
    def _find_item_by_filepath(self, filepath, parent=None):
        """Recursively find item by filepath."""
        if parent is None:
            parent = self.model.invisibleRootItem()
        
        for i in range(parent.rowCount()):
            child = parent.child(i)
            if child:
                if child.data(self.ROLE_FILEPATH) == filepath:
                    return child
                found = self._find_item_by_filepath(filepath, child)
                if found:
                    return found
        return None
    
    def select_file(self, filepath):
        """Select a file in the tree by filepath."""
        item = self._find_item_by_filepath(filepath)
        if item:
            index = self.model.indexFromItem(item)
            self.tree_view.setCurrentIndex(index)
            self.tree_view.scrollTo(index)
    
    def update_patient_info(self, metadata):
        """Update patient info panel with DICOM metadata."""
        if not metadata:
            self.patient_info.setText("No metadata available")
            return
        
        lines = []
        if 'PatientName' in metadata:
            lines.append(f"<b>Patient:</b> {metadata['PatientName']}")
        if 'StudyDate' in metadata:
            date = metadata['StudyDate']
            if len(date) == 8:
                date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
            lines.append(f"<b>Date:</b> {date}")
        if 'Modality' in metadata:
            lines.append(f"<b>Modality:</b> {metadata['Modality']}")
        if 'Manufacturer' in metadata:
            lines.append(f"<b>Device:</b> {metadata['Manufacturer']}")
        if 'InstitutionName' in metadata:
            lines.append(f"<b>Institution:</b> {metadata['InstitutionName']}")
        if 'NumberOfFrames' in metadata:
            lines.append(f"<b>Frames:</b> {metadata['NumberOfFrames']}")
        
        if lines:
            self.patient_info.setText("<br>".join(lines))
        else:
            self.patient_info.setText("No metadata available")
    
    def update_info(self):
        """Update the info label."""
        patient_count = len(self._patients)
        series_count = self._count_series()
        
        if patient_count == 0:
            self.info_label.setText("No files loaded")
        else:
            self.info_label.setText(f"{patient_count} patient(s), {series_count} series")
    
    def _count_series(self):
        """Count total series items."""
        count = 0
        
        def count_recursive(parent):
            nonlocal count
            for i in range(parent.rowCount()):
                child = parent.child(i)
                if child:
                    if child.data(self.ROLE_ITEM_TYPE) in ('series', 'other_file'):
                        count += 1
                    count_recursive(child)
        
        count_recursive(self.model.invisibleRootItem())
        return count


class _TreeViewListAdapter:
    """Adapter for backward compatibility with file_list.itemClicked signal."""
    
    def __init__(self, tree_view, file_list_widget):
        self.tree_view = tree_view
        self.file_list_widget = file_list_widget
        self._item_clicked_callbacks = []
        
        self.tree_view.clicked.connect(self._on_tree_clicked)
        self.tree_view.doubleClicked.connect(self._on_tree_double_clicked)
    
    @property
    def itemClicked(self):
        return self
    
    def connect(self, callback):
        self._item_clicked_callbacks.append(callback)
    
    def _on_tree_clicked(self, index):
        item = self.file_list_widget.model.itemFromIndex(index)
        if item:
            wrapper = _ItemWrapper(item)
            for callback in self._item_clicked_callbacks:
                callback(wrapper)
    
    def _on_tree_double_clicked(self, index):
        self._on_tree_clicked(index)


class _ItemWrapper:
    """Wrapper to make QStandardItem compatible with QListWidgetItem interface."""
    
    def __init__(self, item):
        self._item = item
    
    def data(self, role):
        return self._item.data(role)
    
    def text(self):
        return self._item.text()
