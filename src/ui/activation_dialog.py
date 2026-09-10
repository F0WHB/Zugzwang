from src.ui.toast_system import ToastNotification
"""
ZUGZWANG - Activation Dialog (macOS Redesign)
"Apple Style" - Premium, minimal, highly-polished.
"""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
    QLineEdit, QFrame, QGraphicsDropShadowEffect, QPushButton
)
from qfluentwidgets import (
    FluentIcon, IconWidget, LineEdit, InfoBarPosition
)
from .theme import Theme
from ..core.security import LicenseManager

class ActivationDialog(QDialog):
    """
    macOS-style Activation screen.
    """
    
    activated = Signal()
    open_send_requested = Signal()

    def __init__(self, parent=None, startup_prompt: bool = False):
        super().__init__(parent)
        self._startup_prompt = startup_prompt
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self._build_ui()
        
    def _build_ui(self):
        # We don't set a fixed height here, we let the layout automatically hug the content.
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        self.container.setStyleSheet("""
            QFrame#MainContainer {
                background: #2C2C2E;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 14px;
            }
        """)
        self.setFixedWidth(410)
        self.container.setFixedWidth(410)
        dialog_layout.addWidget(self.container)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. HEADER (macOS Sheet Style)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)
        
        icon_chip = QFrame()
        icon_chip.setFixedSize(40, 40)
        icon_chip.setStyleSheet("background: #3A3A3C; border-radius: 9px;")
        chip_layout = QVBoxLayout(icon_chip)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        
        # Use SHIELD if available, fallback to VPN/Safe
        icon_type = getattr(FluentIcon, "SHIELD", FluentIcon.VPN)
        icon = IconWidget(icon_type)
        icon.setFixedSize(18, 18)
        icon.setStyleSheet("color: #FFFFFF; background: transparent;")
        chip_layout.addWidget(icon, 0, Qt.AlignCenter)
        
        header_layout.addWidget(icon_chip, 0, Qt.AlignTop)
        
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)
        from ..core.i18n import get_language, tr
        title = QLabel(tr("activation.title", get_language(None)))
        title.setStyleSheet("""
            color: #FFFFFF; 
            background: transparent;
            font-family: "-apple-system", "SF Pro Display", sans-serif; 
            font-size: 17px; 
            font-weight: 600;
        """)
        header_text_layout.addWidget(title)
        
        subtitle = QLabel(tr("activation.subtitle", get_language(None)))
        subtitle.setStyleSheet("""
            color: #8E8E93; 
            background: transparent;
            font-family: "-apple-system", "SF Pro Text", sans-serif; 
            font-size: 13px;
            font-weight: 400;
        """)
        header_text_layout.addWidget(subtitle)
        
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch(1)
        
        layout.addLayout(header_layout)
        layout.addSpacing(20)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. PERSUASION / BENEFITS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        benefits_layout = QVBoxLayout()
        benefits_layout.setSpacing(11)
        benefits_layout.setContentsMargins(0, 0, 0, 0)
        
        def _make_prop(text: str):
            row = QHBoxLayout()
            row.setSpacing(12)
            row.setContentsMargins(0, 0, 0, 0)
            
            chk = QLabel("✓")
            chk.setStyleSheet("color: #0A84FF; background: transparent; font-family: '-apple-system', sans-serif; font-size: 14px; font-weight: 300; letter-spacing: 0px;")
            
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #EBEBF0; background: transparent; font-family: '-apple-system', 'SF Pro Text', sans-serif; font-size: 14px; font-weight: 400; letter-spacing: 0px; line-height: 1.4;")
            
            row.addWidget(chk, 0, Qt.AlignVCenter)
            row.addWidget(lbl, 1, Qt.AlignVCenter)
            return row
            
        benefits_layout.addLayout(_make_prop(tr("activation.f1", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f2", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f3", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f4", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f5", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f6", get_language(None))))
        benefits_layout.addLayout(_make_prop(tr("activation.f7", get_language(None))))
        layout.addLayout(benefits_layout)
        
        layout.addSpacing(20)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. FOCAL TASK (PRODUCT KEY)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        key_lbl = QLabel(tr("activation.key", get_language(None)))
        key_lbl.setStyleSheet("color: #8E8E93; background: transparent; font-family: '-apple-system', sans-serif; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
        layout.addWidget(key_lbl)
        layout.addSpacing(6)
        
        from PySide6.QtWidgets import QLineEdit
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("ZUG-XXXX-XXXX-XXXX")
        self.key_input.setFixedHeight(40)
        self.key_input.setAttribute(Qt.WA_MacShowFocusRect, 0)
        self.key_input.setStyleSheet("""
            QLineEdit {
                background: #1C1C1E;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                color: #FFFFFF;
                font-family: "SF Mono", "Menlo", monospace;
                font-size: 13px; padding: 8px 12px; letter-spacing: 1px;
                outline: none;
            }
            QLineEdit:focus { 
                border: 1px solid #0A84FF;
                background: #1C1C1E;
                outline: none;
            }
        """)
        self.key_input.textChanged.connect(self._on_key_changed)
        layout.addWidget(self.key_input)
        layout.addSpacing(14)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. SUBORDINATE REFERENCE (MACHINE ID)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(8)
        
        mid_lbl = QLabel(tr("activation.machine", get_language(None)))
        mid_lbl.setStyleSheet("color: #8E8E93; background: transparent; font-family: '-apple-system', sans-serif; font-size: 11px; font-weight: 500;")
        mid_layout.addWidget(mid_lbl)
        
        self.mid_field = QLabel()
        self.mid_field.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mid_field.setStyleSheet("color: #AEAEB2; font-family: 'Menlo', 'Menlo', monospace; font-size: 11.5px; letter-spacing: 0.5px; background: transparent;")
        mid_layout.addWidget(self.mid_field)
        
        copy_btn = QPushButton()
        copy_btn.setFixedSize(28, 28)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setIcon(FluentIcon.COPY.icon(color=QColor(142, 142, 147, 180)))
        copy_btn.setIconSize(QSize(16, 16))
        copy_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: rgba(255,255,255,0.05); border-radius: 14px; }")
        copy_btn.clicked.connect(self._copy_id)
        mid_layout.addWidget(copy_btn)
        
        mid_layout.addStretch(1)
        layout.addLayout(mid_layout)
        
        layout.addSpacing(14)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5. FOOTER (Action Buttons)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━
        
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        def open_url(url): QDesktopServices.openUrl(QUrl(url))
        
        need_key_btn = QPushButton("Activation")
        need_key_btn.setCursor(Qt.PointingHandCursor)
        need_key_btn.setStyleSheet("""
            QPushButton {
                color: #30D158; 
                background: transparent;
                border: none;
                font-family: '-apple-system', sans-serif; 
                font-size: 14px; 
                font-weight: 500;
                letter-spacing: 0px;
                text-transform: none;
                text-align: center;
                padding: 0;
            }
            QPushButton:hover { color: #28CD53; text-decoration: underline; }
        """)
        need_key_btn.clicked.connect(lambda: open_url("https://wa.me/212663007212"))
        layout.addWidget(need_key_btn)
        
        layout.addSpacing(10)
        
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(10)
        
        from PySide6.QtWidgets import QSizePolicy
        
        # Primary Action Pair (RIGHT)
        self.close_btn = QPushButton("Continue trial")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedHeight(44)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; 
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 10px;
                color: #FFFFFF;
                font-family: "-apple-system", "SF Pro Text", sans-serif; font-size: 15px; font-weight: 500;
                letter-spacing: 0px;
                text-transform: none;
                padding: 0 20px;
                white-space: nowrap;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.05); }
        """)
        self.close_btn.clicked.connect(self._on_exit_clicked)
        self.close_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        footer.addWidget(self.close_btn)
        
        self.activate_btn = QPushButton("Activate")
        self.activate_btn.setFixedHeight(44)
        self.activate_btn.setCursor(Qt.PointingHandCursor)
        self.activate_btn.setProperty("isValid", False)
        self.activate_btn.setStyleSheet("""
            QPushButton {
                background: rgba(10, 132, 255, 0.15);
                color: rgba(10, 132, 255, 0.5);
                border: none;
                border-radius: 10px;
                font-family: "-apple-system", "SF Pro Text", sans-serif;
                font-size: 15px; font-weight: 500;
                letter-spacing: 0px;
                text-transform: none;
                padding: 0 20px;
            }
            QPushButton:disabled {
                background: rgba(10, 132, 255, 0.15);
                color: rgba(10, 132, 255, 0.5);
            }
            QPushButton[isValid="true"] {
                background: #0A84FF;
                color: #FFFFFF;
            }
            QPushButton[isValid="true"]:hover { 
                background: #0070DF; 
            }
        """)
        self.activate_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.activate_btn.setEnabled(False)
        self.activate_btn.clicked.connect(self._activate)
        footer.addWidget(self.activate_btn)
        
        layout.addLayout(footer)
        
        self._refresh_machine_id()
        
        if self.parent():
            self.adjustSize()
            center = self.parent().geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def _on_key_changed(self, text: str):
        self.key_input.blockSignals(True)
        clean = text.replace("-", "").upper()
        
        formatted = ""
        if len(clean) > 0:
            formatted += clean[:3]
        if len(clean) > 3:
            formatted += "-" + clean[3:7]
        if len(clean) > 7:
            formatted += "-" + clean[7:11]
        if len(clean) > 11:
            formatted += "-" + clean[11:15]
            
        self.key_input.setText(formatted)
        self.key_input.setCursorPosition(len(formatted))
        self.key_input.blockSignals(False)
        
        is_valid = len(clean) >= 15
        if self.activate_btn.property("isValid") != is_valid:
            self.activate_btn.setProperty("isValid", is_valid)
            self.activate_btn.setEnabled(is_valid)
            self.activate_btn.style().unpolish(self.activate_btn)
            self.activate_btn.style().polish(self.activate_btn)

    def _on_open_send(self):
        self.open_send_requested.emit()
        self.accept()

    def _on_exit_clicked(self):
        self.reject()
        
    def _copy_id(self):
        machine_id = self.mid_field.text().strip()
        if not machine_id:
            self._refresh_machine_id()
            machine_id = self.mid_field.text().strip()
        QGuiApplication.clipboard().setText(machine_id)
        ToastNotification.success("Copied", "Machine ID copied to clipboard.", duration=2000, position=InfoBarPosition.TOP, parent=self)

    def _refresh_machine_id(self):
        machine_id = (LicenseManager.get_machine_id() or "").strip().upper()
        self.mid_field.setText(machine_id)
        
    def _activate(self):
        key = self.key_input.text().strip()
        if not key:
            ToastNotification.error("Required", "Please enter your license key.", duration=3000, parent=self)
            return
            
        if LicenseManager.activate(key):
            self.activated.emit()
            self.accept()
        else:
            ToastNotification.error("Invalid Key", "Product key does not match this machine.", duration=4000, parent=self)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        super().keyPressEvent(event)

# 1.1.0
