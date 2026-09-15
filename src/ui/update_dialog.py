"""
ZUGZWANG - Update Notification Dialog
macOS-style UI for version alerts and download progress.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QProgressBar, QTextEdit, QVBoxLayout
from src.ui.toast_system import ToastNotification as InfoBar
 
from ..core.config import APP_BUILD, APP_VERSION
from .components import ZugzwangDialog


class UpdateDialog(ZugzwangDialog):
    """
    Premium Apple-style update notification screen using the popup system.
    """
    
    update_started = Signal(str) # download_url

    def __init__(self, new_version: str, download_url: str, parent=None, release_notes: str = ""):
        self.new_version = new_version
        self.download_url = download_url
        self.release_notes = release_notes.strip() if release_notes else ""
        
        title = "Software Update"
        desc = f"A new version of ZUGZWANG is ready to install.\nYou are currently using v{APP_VERSION} (build {APP_BUILD})."
        
        super().__init__(
            title=title,
            message=desc,
            parent=parent,
            confirm_text="Update Now",
            cancel_text="Later",
            single_button=False,
            destructive=False
        )
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.WindowSystemMenuHint)
        self.ok_btn.setText("Update Now")
        self.cancel_btn.setText("Later")
        
        has_notes = bool(self.release_notes)
        dlg_w = 380
        dlg_h = 300 if has_notes else 225
        
        self.setFixedSize(dlg_w, dlg_h)
        self.container.setFixedSize(dlg_w, dlg_h)
        
        layout = self.container.layout()
        
        # Subtitle for version info (inserted just after the title at index 1)
        self.subtitle_label = QLabel(f"Version {self.new_version} is available")
        self.subtitle_label.setStyleSheet(
            "color: #0A84FF; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; "
            "font-size: 12px; font-weight: 600; background: rgba(10, 132, 255, 0.12); "
            "border: 1px solid rgba(10, 132, 255, 0.25); border-radius: 6px; padding: 3px 8px;"
        )
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        layout.insertWidget(1, self.subtitle_label)
        
        # Optional release notes preview
        insert_idx = 3
        if has_notes:
            self.notes_view = QTextEdit()
            self.notes_view.setReadOnly(True)
            self.notes_view.setPlainText(self.release_notes)
            self.notes_view.setFixedHeight(75)
            self.notes_view.setStyleSheet("""
                QTextEdit {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    color: #D1D1D6;
                    font-family: 'SF Pro Text', 'PT Root UI', sans-serif;
                    font-size: 11px;
                    padding: 6px 8px;
                }
            """)
            layout.insertWidget(insert_idx, self.notes_view)
            insert_idx += 1

        # Add Progress Bar & Status (Hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: rgba(255, 255, 255, 0.1); border: none; border-radius: 3px; }
            QProgressBar::chunk { background: #0A84FF; border-radius: 3px; }
        """)
        
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #8E8E93; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 11px; background: transparent; border: none;")
        
        layout.insertWidget(insert_idx, self.progress_bar)
        layout.insertWidget(insert_idx + 1, self.status_label)
        
        # Re-wire OK button to start update instead of closing immediately
        self.ok_btn.clicked.disconnect()
        self.ok_btn.clicked.connect(self._start_update)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        if parent:
            target_win = parent.window() if hasattr(parent, "window") else parent
            center = target_win.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def _start_update(self):
        self.ok_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Starting download...")
        self.status_label.setStyleSheet("color: #8E8E93; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 11px; background: transparent; border: none;")
        self.update_started.emit(self.download_url)

    def set_progress(self, val: int):
        self.progress_bar.setValue(val)
        self.status_label.setText(f"Downloading update... {val}%")

    def set_finished(self):
        self.progress_bar.setValue(100)
        self.status_label.setText("Download complete! Launching update...")
        self.status_label.setStyleSheet("color: #30D158; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 11px; font-weight: 600; background: transparent; border: none;")

    def set_error(self, msg: str):
        self.status_label.setText(f"Error: {msg}")
        self.status_label.setStyleSheet("color: #FF453A; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 11px; background: transparent; border: none;")
        self.ok_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        InfoBar.error("Update Failed", msg, duration=5000, parent=self)
