"""
ZUGZWANG - Reusable UI Components
Shared widgets used across multiple pages.
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPropertyAnimation, QEasingCurve, Property, QRectF, QRect, QEvent
from PySide6.QtGui import QColor, QFont, QPainter, QBrush, QPixmap, QPen, QPainterPath, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout,
    QPushButton, QFrame, QSizePolicy, QDialog, QComboBox, QStyledItemDelegate, QStyle,
)
from ..core.i18n import tr, get_language
from qfluentwidgets import (
    IconWidget, FluentIconBase, FluentIcon, drawIcon, EditableComboBox
)

from .icons import apply_button_icon


class StatCard(QFrame):
    """Dashboard stat card showing a metric with label and subtitle."""

    def __init__(self, title: str, value: str = "-", subtitle: str = "", color: str = "#212A3B"):
        super().__init__()
        self.setObjectName("Card")
        self._color = color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(4)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setObjectName("CardTitle")

        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("CardValue")
        self._value_lbl.setStyleSheet(f"color: {color};")

        self._sub_lbl = QLabel(subtitle)
        self._sub_lbl.setObjectName("CardSub")

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._value_lbl)
        layout.addWidget(self._sub_lbl)

    def set_value(self, value: str) -> None:
        self._value_lbl.setText(value)

    def set_subtitle(self, text: str) -> None:
        self._sub_lbl.setText(text)


class SectionCard(QFrame):
    """Reusable rounded section container with an optional header row."""

    def __init__(self, title: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("SectionCard")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(16)

        self._header = QWidget()
        self._header_layout = QHBoxLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(10)

        self._title_wrap = QWidget()
        title_layout = QVBoxLayout(self._title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("SectionCardTitle")
        title_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setObjectName("SectionCardSubtitle")
        self._subtitle_label.setVisible(bool(subtitle))
        title_layout.addWidget(self._subtitle_label)

        self._header_layout.addWidget(self._title_wrap)
        self._header_layout.addStretch()

        self._layout.addWidget(self._header)
        self._header.setVisible(bool(title or subtitle))

    def add_header_widget(self, widget: QWidget) -> None:
        self._header_layout.addWidget(widget)

    def body_layout(self) -> QVBoxLayout:
        return self._layout

    def set_title(self, title: str, subtitle: str = "") -> None:
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setVisible(bool(subtitle))
        self._header.setVisible(bool(title or subtitle))


class StatusBadge(QLabel):
    """Colored badge label for status display."""

    STATUS_STYLES = {
        "running": "BadgeInfo",
        "completed": "BadgeSuccess",
        "failed": "BadgeError",
        "paused": "BadgeWarning",
        "cancelled": "BadgeWarning",
        "pending": "BadgeWarning",
        "idle": "BadgeInfo",
    }

    def __init__(self, status: str = "idle"):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self.setText(status.upper())
        obj_name = self.STATUS_STYLES.get(status.lower(), "BadgeInfo")
        self.setObjectName(obj_name)
        # Force style refresh
        self.style().unpolish(self)
        self.style().polish(self)


class SectionHeader(QWidget):
    """Page section header with title and optional subtitle."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PageHeader")
        layout.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("PageSubtitle")
            layout.addWidget(sub_lbl)


class Divider(QFrame):
    """Horizontal divider line."""

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setObjectName("SectionDivider")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(1)


class FieldLabel(QLabel):
    """Styled field label for form inputs."""

    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("FieldLabel")


def make_field(label: str, widget: QWidget) -> QVBoxLayout:
    """Helper to create a labeled form field layout."""
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(FieldLabel(label))
    layout.addWidget(widget)
    return layout


def make_button(
    text: str,
    style: str = "SecondaryBtn",
    icon: str = "",
    tooltip: str = "",
) -> QPushButton:
    """Factory for styled buttons."""
    btn = QPushButton(text)
    btn.setObjectName(style)
    btn.setCursor(Qt.PointingHandCursor)
    if icon:
        apply_button_icon(btn, icon)
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


class EmptyState(QFrame):
    """Friendly empty state widget shown when no results exist."""

    def __init__(self, icon: str = "", title: str = "No results yet", body: str = ""):
        super().__init__()
        self.setObjectName("EmptyState")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(170)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setObjectName("EmptyStateIcon")
            icon_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("EmptyStateTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        if body:
            body_lbl = QLabel(body)
            body_lbl.setObjectName("EmptyStateBody")
            body_lbl.setAlignment(Qt.AlignCenter)
            body_lbl.setWordWrap(True)
            body_lbl.setMaximumWidth(440)
            body_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            layout.addWidget(body_lbl)


class WorkspaceListItem(QFrame):
    """Dense clickable item used in the middle workspace list."""

    activated = Signal(str)

    def __init__(self, key: str, title: str, meta: str = "", preview: str = "", badge: str = ""):
        super().__init__()
        self._key = key
        self.setObjectName("WorkspaceItem")
        self.setProperty("active", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(74)
        self.setAccessibleName(title)
        self.setAccessibleDescription("Workspace item")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self._title = QLabel(title)
        self._title.setObjectName("WorkspaceItemTitle")
        self._title.setWordWrap(False)
        top_row.addWidget(self._title, 1)

        self._badge = QLabel(badge)
        self._badge.setObjectName("WorkspaceItemBadge")
        self._badge.setVisible(bool(badge))
        top_row.addWidget(self._badge)
        layout.addLayout(top_row)

        self._meta = QLabel(meta)
        self._meta.setObjectName("WorkspaceItemMeta")
        self._meta.setWordWrap(False)
        self._meta.setVisible(bool(meta))
        layout.addWidget(self._meta)

        self._preview = QLabel(preview)
        self._preview.setObjectName("WorkspaceItemPreview")
        self._preview.setWordWrap(False)
        self._preview.setMaximumHeight(18)
        self._preview.setVisible(bool(preview))
        layout.addWidget(self._preview)

    @property
    def key(self) -> str:
        return self._key

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def update_content(self, title: str, meta: str = "", preview: str = "", badge: str = "") -> None:
        self._title.setText(title)
        self._meta.setText(meta)
        self._meta.setVisible(bool(meta))
        self._preview.setText(preview)
        self._preview.setVisible(bool(preview))
        self._badge.setText(badge)
        self._badge.setVisible(bool(badge))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self._key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit(self._key)
            event.accept()
            return
        super().keyPressEvent(event)


class ZugzwangDialog(QDialog):
    """
    Premium macOS ZUGZWANG Style Dialog.
    Centered text, high-fidelity geometry, and Apple-style buttons to match Image 3.
    """
    def __init__(self, title: str, message: str, parent=None, confirm_text: str = "OK", cancel_text: str = "CANCEL", single_button: bool = False, destructive: bool = False):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(Qt.NonModal)
        self.setFixedWidth(320)
        self._drag_pos = None
        
        # Main layout for the dialog to allow dynamic height
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Main shadow/glass container
        self.container = QFrame(self)
        self.container.setObjectName("DialogContainer")
        self.container.setStyleSheet("""
            QFrame#DialogContainer {
                background: rgba(40, 40, 40, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 14px;
            }
        """)
        
        main_layout.addWidget(self.container)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        
        self.title_label = QLabel(title)

        self.title_label.setStyleSheet("color: #FFFFFF; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 16px; font-weight: 600; background: transparent; border: none;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        self.message_label = QLabel(message)
        self.message_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 13px; font-weight: 400; background: transparent; border: none; line-height: 1.2;")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)
        
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(10)
        
        # Cancel Button (Dark #2C2C2E)
        if not single_button:
            from ..core.i18n import get_language, tr
            btn_cancel_txt = cancel_text if cancel_text and cancel_text != "CANCEL" else tr("dialog.cancel", get_language(None))
            self.cancel_btn = QPushButton(btn_cancel_txt)
            self.cancel_btn.setFixedHeight(32)
            self.cancel_btn.setCursor(Qt.PointingHandCursor)
            self.cancel_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.1);
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-family: 'SF Pro Text', 'PT Root UI', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    letter-spacing: 1px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.15); }
            """)
            self.cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(self.cancel_btn)
            
        # OK/Confirm Button (Red #FF453A or #0A84FF)
        btn_confirm_txt = confirm_text if confirm_text and confirm_text != "OK" else tr("dialog.ok", get_language(None))
        self.ok_btn = QPushButton(btn_confirm_txt)
        self.ok_btn.setFixedHeight(32)
        self.ok_btn.setCursor(Qt.PointingHandCursor)
        # Choose color dynamically based on text or destructive flag
        color = "#FF453A" if destructive or "Delete" in confirm_text or "Wipe" in title else "#0A84FF"
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 6px;
                font-family: 'SF Pro Text', 'PT Root UI', sans-serif;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {color}CC; }}
        """)
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)
        
        if parent:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.sizeHint().height() // 2 - 20)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

class FeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._drag_pos = None
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.container = QFrame(self)
        main_layout.addWidget(self.container)
        
        self.container.setObjectName("FeedbackContainer")
        self.container.setFixedWidth(380)
        self.container.setStyleSheet("""
            QFrame#FeedbackContainer {
                background-color: #2C2C2E;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QLabel { background: transparent; border: none; letter-spacing: 0px; }
        """)
        
        from PySide6.QtCore import QSize
        from qfluentwidgets import FluentIcon
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(0)
        
        # Header - Text
        self.icon_lbl = QLabel()
        from PySide6.QtGui import QPainterPath, QPainter, QColor, QPixmap
        
        def _get_solid_heart_pixmap(size=36, color="#FF3B30"):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            scale = size / 24.0
            painter.scale(scale, scale)
            
            path.moveTo(12, 21.35)
            path.lineTo(10.55, 20.03)
            path.cubicTo(5.4, 15.36, 2, 12.28, 2, 8.5)
            path.cubicTo(2, 5.42, 4.42, 3, 7.5, 3)
            path.cubicTo(9.24, 3, 10.91, 3.81, 12, 5.09)
            path.cubicTo(13.09, 3.81, 14.76, 3, 16.5, 3)
            path.cubicTo(19.58, 3, 22, 5.42, 22, 8.5)
            path.cubicTo(22, 12.28, 18.6, 15.36, 13.45, 20.04)
            path.lineTo(12, 21.35)
            
            painter.fillPath(path, QColor(color))
            painter.end()
            return pixmap

        self.icon_lbl.setPixmap(_get_solid_heart_pixmap())
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel(tr("whatsnew.support.title", parent._language if hasattr(parent, '_language') else 'en'))
        self.title_label.setStyleSheet("color: #FFFFFF; font-family: '-apple-system', 'SF Pro Display', sans-serif; font-size: 17px; font-weight: 600;")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.message_label = QLabel("I built this solo — your support keeps the scrapers running and updates coming.")
        self.message_label.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 13px; font-weight: 400;")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        
        layout.addWidget(self.icon_lbl)
        layout.addSpacing(8)
        layout.addWidget(self.title_label)
        layout.addSpacing(8)
        layout.addWidget(self.message_label)
        
        layout.addSpacing(20) # Section spacing
        
        # Support Section
        support_title = QLabel(tr("whatsnew.support.direct", parent._language if hasattr(parent, '_language') else 'en'))
        support_title.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;")
        support_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(support_title)
        layout.addSpacing(12)
        
        self.donate_btn = QPushButton("Support the Developer ☕")
        self.donate_btn.setFixedHeight(44)
        self.donate_btn.setCursor(Qt.PointingHandCursor)
        self.donate_btn.setStyleSheet("""
            QPushButton {
                background-color: #0A84FF;
                border: 1px solid #0A84FF;
                border-radius: 10px;
                color: #FFFFFF;
                font-family: '-apple-system', 'SF Pro Text', sans-serif;
                font-size: 15px;
                font-weight: 500;
                letter-spacing: normal;
                text-transform: none;
            }
            QPushButton:hover { background-color: #007AFF; }
            QPushButton:pressed { background-color: #0062CC; }
        """)
        self.donate_btn.clicked.connect(self._on_donate)
        layout.addWidget(self.donate_btn)
        
        layout.addSpacing(8) # Exact 8px caption-to-button gap
        
        impact_label = QLabel("Covers hosting and keeps zugzwang free for job seekers.")
        impact_label.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 400;")
        impact_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(impact_label)
        
        layout.addSpacing(20) # 20px gap before next section starts
        
        crow = QHBoxLayout()
        crow.setSpacing(12)
        crow.setContentsMargins(0, 0, 0, 0)
        
        self.tg_btn = QPushButton("Telegram")
        self.tg_btn.setFixedHeight(44)
        self.tg_btn.setCursor(Qt.PointingHandCursor)
        self.tg_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 10px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 15px;
                font-weight: 500;
                letter-spacing: normal;
                text-transform: none;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.05); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.02); }
        """)
        self.tg_btn.clicked.connect(self._on_telegram)
        
        self.wa_btn = QPushButton("WhatsApp")
        self.wa_btn.setFixedHeight(44)
        self.wa_btn.setCursor(Qt.PointingHandCursor)
        self.wa_btn.setStyleSheet(self.tg_btn.styleSheet())
        self.wa_btn.clicked.connect(self._on_whatsapp)
        
        crow.addWidget(self.tg_btn)
        crow.addWidget(self.wa_btn)
        layout.addLayout(crow)

        layout.addSpacing(20) # Section spacing
        
        # Social Section
        share_title = QLabel(tr("whatsnew.support.promote", parent._language if hasattr(parent, '_language') else 'en'))
        share_title.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;")
        share_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(share_title)
        layout.addSpacing(12)
        
        srow = QHBoxLayout()
        srow.setSpacing(10)
        srow.setContentsMargins(0, 0, 0, 0)
        
        def create_icon_btn(icon, color_hex="#FFFFFF"):
            btn = QPushButton()
            btn.setFixedSize(44, 44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(icon.icon(color=QColor(color_hex)))
            btn.setIconSize(QSize(17, 17))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3A3A3C;
                    border: none;
                    border-radius: 22px;
                }
                QPushButton:hover { background-color: #4A4A4C; }
                QPushButton:pressed { background-color: #2C2C2E; }
            """)
            return btn
            
        self.x_btn = create_icon_btn(FluentIcon.SHARE, "#FFFFFF")
        self.x_btn.setToolTip("Share on X (Twitter)")
        self.x_btn.clicked.connect(lambda: self._on_share("x"))
        
        self.fb_btn = create_icon_btn(FluentIcon.CHAT, "#FFFFFF")
        self.fb_btn.setToolTip("Share via Messages")
        self.fb_btn.clicked.connect(lambda: self._on_share("fb"))
        
        self.wa_share_btn = create_icon_btn(FluentIcon.MAIL, "#FFFFFF")
        self.wa_share_btn.setToolTip("Share via Email")
        self.wa_share_btn.clicked.connect(lambda: self._on_share("wa"))
        
        self.ig_btn = create_icon_btn(FluentIcon.SAVE, "#FFFFFF")
        self.ig_btn.setToolTip("Save Image")
        self.ig_btn.clicked.connect(lambda: self._on_share("ig"))
        
        self.rec_btn = create_icon_btn(FluentIcon.LINK, "#FFFFFF")
        self.rec_btn.setToolTip("Copy Link")
        self.rec_btn.clicked.connect(self._on_recommend)
        
        srow.addStretch()
        srow.addWidget(self.x_btn)
        srow.addWidget(self.fb_btn)
        srow.addWidget(self.wa_share_btn)
        srow.addWidget(self.ig_btn)
        srow.addWidget(self.rec_btn)
        srow.addStretch()
        layout.addLayout(srow)
        
        if parent:
            self.adjustSize()
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def _on_telegram(self):
        import webbrowser
        webbrowser.open("https://t.me/+OsHHWTSv_bVkZTM0")

    def _on_whatsapp(self):
        import webbrowser
        webbrowser.open("https://wa.me/212663007212")

    def _on_donate(self):
        import webbrowser
        from urllib.parse import quote
        msg = "slm khoya khdmt b app dylk w bghit n supportik,"
        url = f"https://wa.me/212663007212?text={quote(msg)}"
        webbrowser.open(url)

    def _on_share(self, platform: str):
        import webbrowser
        from urllib.parse import quote
        
        msg = ("supportina bach nkmlo lkhdma ela l app, ana khdam b had l app w kt3awni bach njm3 w nsyft Bewerbungen, "
               "dkhl l goupe telegram w atfhm klchi, merci : https://t.me/+OsHHWTSv_bVkZTM0 w dkhl lien bach "
               "telechargiha direct : https://github.com/whbexc/Zugzwang/releases")
        app_url = "https://github.com/whbexc/Zugzwang/releases"
        
        url = ""
        if platform == "x":
            url = f"https://twitter.com/intent/tweet?text={quote(msg)}&url={quote(app_url)}"
        elif platform == "fb":
            url = f"https://www.facebook.com/sharer/sharer.php?u={quote(app_url)}&quote={quote(msg)}"
        elif platform == "wa":
            url = f"https://wa.me/?text={quote(msg)}"
            webbrowser.open(url)
        elif platform == "ig":
            # Instagram Fallback: Copy to clipboard and open IG
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(msg)
            self.rec_btn.setText("TEXT COPIED! OPENING INSTAGRAM...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.rec_btn.setText("COPY PROMO LINK & TEXT"))
            webbrowser.open("https://www.instagram.com/")

    def _on_recommend(self):
        from PySide6.QtGui import QClipboard, QGuiApplication
        from PySide6.QtCore import QTimer
        
        msg = ("supportina bach nkmlo lkhdma ela l app, ana khdam b had l app w kt3awni bach njm3 w nsyft Bewerbungen, "
               "dkhl l goupe telegram w atfhm klchi, merci : https://t.me/+OsHHWTSv_bVkZTM0 w dkhl lien bach "
               "telechargiha direct : https://github.com/whbexc/Zugzwang/releases")
        
        QGuiApplication.clipboard().setText(msg)
        self.rec_btn.setText("PROMO TEXT COPIED!")
        QTimer.singleShot(2500, lambda: self.rec_btn.setText("COPY PROMO LINK & TEXT"))

    def mousePressEvent(self, event):
        self.reject()
        super().mousePressEvent(event)

class MacSwitch(QWidget):
    """Premium macOS-style toggle switch with smooth animations."""
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        
        self._on_color = QColor("#0A84FF")
        self._thumb_x = 2.0
        self._anim = QPropertyAnimation(self, b"thumb_x", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutBack)

    def setOnColor(self, color: str | QColor):
        self._on_color = QColor(color)
        self.update()

    @Property(float)
    def thumb_x(self):
        return self._thumb_x

    @thumb_x.setter
    def thumb_x(self, x: float):
        self._thumb_x = x
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = checked
        self._anim.stop()
        self._anim.setEndValue(16.0 if checked else 2.0)
        self._anim.start()
        self.update()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.update()

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange:
            self.update()
        super().changeEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
    
            track_color = self._on_color if self._checked else QColor("#3A3A3C")
            if not self.isEnabled():
                track_color.setAlpha(128)
            painter.setBrush(QBrush(track_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, w, h, h/2, h/2)
    
            thumb_size = h - 4
            thumb_rect = QRectF(self._thumb_x, 2, thumb_size, thumb_size)
            painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
            painter.drawEllipse(thumb_rect.translated(0, 1))
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(thumb_rect)


class MacComboBoxDelegate(QStyledItemDelegate):
    """Custom delegate to draw dropdown items with a checkmark on the right (like FilterMenu)."""
    def __init__(self, parent_combo, parent=None):
        super().__init__(parent)
        self.parent_combo = parent_combo

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        is_hovered = bool(option.state & (QStyle.State_MouseOver | QStyle.State_Selected))
        
        # Determine if this item is currently selected in the combobox
        is_current = False
        if hasattr(self.parent_combo, "currentIndex") and self.parent_combo.currentIndex() == index.row():
            is_current = True
            
        # Text
        text = index.data(Qt.DisplayRole)
        text_color = QColor("#0A84FF") if is_current else (QColor("white") if is_hovered else QColor("#AEAEB2"))
        
        font = option.font
        font.setFamily("PT Root UI")
        font.setPointSize(13)
        font.setWeight(QFont.DemiBold if is_current else QFont.Normal)
        painter.setFont(font)
        
        text_rect = option.rect.adjusted(14, 0, -30, 0)
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        
        # Checkmark for current item
        if is_current:
            icon_rect = QRect(option.rect.right() - 26, option.rect.center().y() - 6, 12, 12)
            drawIcon(FluentIcon.COMPLETED, painter, icon_rect, fill="#0A84FF")
            
        painter.restore()

    def sizeHint(self, option, index):
        from PySide6.QtCore import QSize
        return QSize(option.rect.width(), 32)


class MacComboBox(QComboBox):
    """Premium macOS-style combo box replacing qfluentwidgets.ComboBox for consistent dropdowns."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.view().setItemDelegate(MacComboBoxDelegate(self, self.view()))
        
        # Force translucent background on the dropdown container to prevent square corners
        container = self.view().parentWidget()
        if container:
            container.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            container.setAttribute(Qt.WA_TranslucentBackground)
        
        self.view().setStyleSheet("""
            QListView {
                background: #2C2C2E;
                border: 1px solid #3A3A3C;
                border-radius: 8px;
                outline: 0;
            }
            QListView::item {
                border-radius: 4px;
                margin: 2px 4px;
            }
            QListView::item:selected {
                background: transparent;
            }
            QListView::item:hover {
                background: transparent;
            }
        """)

    def setCurrentText(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            super().setCurrentText(text)

class MacEditableComboBox(QComboBox):
    """Premium macOS-style editable combo box."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setFixedHeight(34)
        self.view().setItemDelegate(MacComboBoxDelegate(self, self.view()))
        
        # Force translucent background on the dropdown container to prevent square corners
        container = self.view().parentWidget()
        if container:
            container.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            container.setAttribute(Qt.WA_TranslucentBackground)
        
        self.view().setStyleSheet("""
            QListView {
                background: #2C2C2E;
                border: 1px solid #3A3A3C;
                border-radius: 8px;
                outline: 0;
            }
            QListView::item {
                border-radius: 4px;
                margin: 2px 4px;
            }
            QListView::item:selected {
                background: transparent;
            }
            QListView::item:hover {
                background: transparent;
            }
        """)

    def setCurrentText(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            super().setCurrentText(text)

class EmptyStateWidget(QWidget):
    """Reusable empty state layout with icon, title, description, and optional action button."""

    def __init__(self, icon: FluentIconBase, title: str, description: str, 
                 button_text: str = None, button_icon: FluentIconBase = None,
                 button_callback=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = IconWidget(icon)
        icon_lbl.setFixedSize(48, 48)
        icon_lbl.setStyleSheet("color: #3A3A3C; border: none;")
        layout.addWidget(icon_lbl, 0, Qt.AlignHCenter)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #E5E5EA; font-family: 'PT Root UI', sans-serif; font-size: 16px; font-weight: 600; border: none;")
        layout.addWidget(title_lbl, 0, Qt.AlignHCenter)

        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #8E8E93; font-family: 'PT Root UI', sans-serif; font-size: 13px; border: none;")
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl, 0, Qt.AlignHCenter)

        if button_text and button_callback:
            layout.addSpacing(16)
            from PySide6.QtWidgets import QPushButton
            btn = QPushButton(button_text)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            
            # Simple layout if no icon
            if not button_icon:
                btn.setStyleSheet("""
                    QPushButton { background: #0A84FF; color: white; border: none; border-radius: 8px; font-family: 'PT Root UI', sans-serif; font-size: 12px; font-weight: 600; padding: 0 24px; }
                    QPushButton:hover { background: #409CFF; }
                """)
            else:
                # With FluentIcon
                btn.setStyleSheet("""
                    QPushButton { background: #0A84FF; color: white; border: none; border-radius: 8px; font-family: 'PT Root UI', sans-serif; font-size: 12px; font-weight: 600; padding: 0 16px 0 36px; text-align: left; }
                    QPushButton:hover { background: #409CFF; }
                """)
                btn_icon = IconWidget(button_icon, btn)
                btn_icon.setFixedSize(16, 16)
                btn_icon.setStyleSheet("color: white; border: none; background: transparent;")
                btn_icon.move(12, 10)
                btn.setFixedWidth(btn.fontMetrics().horizontalAdvances(button_text)[0] + 60)

            btn.clicked.connect(button_callback)
            layout.addWidget(btn, 0, Qt.AlignHCenter)

from qfluentwidgets import FluentIcon
from PySide6.QtWidgets import QGraphicsDropShadowEffect

class ZugzwangDropdownItem(QWidget):
    clicked = Signal(str, int)

    def __init__(self, text: str, index: int, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.text = text
        self.index = index
        self.is_selected = is_selected
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(0)
        
        self.label = QLabel(text)
        weight = "600" if is_selected else "400"
        color = "#0A84FF" if is_selected else "#AEAEB2"
        self.label.setStyleSheet(f"color: {color}; font-family: 'PT Root UI', sans-serif; font-size: 13px; font-weight: {weight}; background: transparent; border: none;")
        layout.addWidget(self.label)
        
        layout.addStretch()
        
        if is_selected:
            check = IconWidget(FluentIcon.COMPLETED)
            check.setFixedSize(12, 12)
            check.setStyleSheet("color: #0A84FF; background: transparent; border: none;")
            layout.addWidget(check)

        self.setAttribute(Qt.WA_Hover)
        self._update_style(False)

    def _update_style(self, hovering: bool):
        bg = "#3A3A3C" if hovering else "transparent"
        text_color = "white" if hovering else ("#0A84FF" if self.is_selected else "#AEAEB2")
        self.label.setStyleSheet(self.label.styleSheet().replace("#AEAEB2", text_color).replace("#0A84FF", text_color).replace("white", text_color))
        self.setStyleSheet(f"background: {bg}; border: none;")

    def enterEvent(self, event):
        self._update_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.text, self.index)
        super().mouseReleaseEvent(event)

class ZugzwangDropdownMenu(QFrame):
    itemSelected = Signal(str, int)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background: #2C2C2E;
                border: 1px solid #3A3A3C;
                border-radius: 10px;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container)
        
        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(0, 6, 0, 6)
        self.content_layout.setSpacing(0)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 12)
        self.container.setGraphicsEffect(shadow)
        
    def add_item(self, text: str, index: int, is_selected: bool = False):
        item = ZugzwangDropdownItem(text, index, is_selected, self)
        item.clicked.connect(self._on_item_clicked)
        self.content_layout.addWidget(item)

    def _on_item_clicked(self, text: str, index: int):
        self.itemSelected.emit(text, index)
        self.close()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

class ZugzwangDropdown(QPushButton):
    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self._items = []
        self._current_index = -1
        self._is_open = False
        self._update_style()

    def addItems(self, items: list[str]):
        self._items.extend(items)
        if self._current_index == -1 and self._items:
            self._current_index = 0
            self.setText(self._items[0])

    def clear(self):
        self._items.clear()
        self._current_index = -1
        self.setText("")

    def count(self) -> int:
        return len(self._items)

    def itemText(self, idx: int) -> str:
        if 0 <= idx < len(self._items):
            return self._items[idx]
        return ""

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return ""

    def setCurrentText(self, text: str):
        if text in self._items:
            self._current_index = self._items.index(text)
            self.setText(text)

    def _update_style(self):
        is_blue = self._is_open
        color = "#0A84FF" if is_blue else "#FFFFFF"
        border_color = "#0A84FF" if is_blue else "#3A3A3C"
        chevron_color = "#0A84FF" if is_blue else "#8E8E93"
        bg_col = "#2C2C2E" if is_blue else "#1C1C1E"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_col};
                border: 1px solid {border_color};
                border-radius: 8px;
                color: {color};
                font-family: 'PT Root UI', sans-serif;
                font-size: 14px;
                font-weight: 500;
                padding: 0 12px;
                text-align: left;
                qproperty-iconSize: 10px 10px;
                spacing: 8px;
            }}
            QPushButton:hover {{
                background: #2C2C2E;
            }}
        """)
        
        chevron = FluentIcon.CHEVRON_DOWN_MED.icon(color=chevron_color)
        self.setIcon(chevron)
        self.setIconSize(QSize(10, 10))
        self.setLayoutDirection(Qt.RightToLeft)

    def show_menu(self):
        self._is_open = True
        self._update_style()
        
        menu = ZugzwangDropdownMenu(self.window())
        menu.setMinimumWidth(self.width())
        for i, text in enumerate(self._items):
            menu.add_item(text, i, i == self._current_index)
            
        menu.itemSelected.connect(self._on_item_selected)
        menu.closed.connect(self._on_menu_closed)
        
        # Position menu 
        pos = self.mapToGlobal(self.rect().bottomLeft())
        menu.move(pos.x(), pos.y() + 4)
        menu.show()

    def _on_item_selected(self, text: str, index: int):
        self._current_index = index
        self.setText(text)
        self.currentTextChanged.emit(text)

    def _on_menu_closed(self):
        self._is_open = False
        self._update_style()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_menu()
        super().mouseReleaseEvent(event)


from PySide6.QtWidgets import QLayout
from PySide6.QtCore import QPoint, QRect, QSize

class FlowLayout(QLayout):
    """Standard Qt Flow/Wrap layout that automatically wraps widgets."""
    def __init__(self, parent=None, margin=0, hSpacing=0, vSpacing=0):
        super().__init__(parent)
        self._h_space = hSpacing
        self._v_space = vSpacing
        self.setContentsMargins(margin, margin, margin, margin)
        self._item_list = []

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        line_height = 0
        for item in self._item_list:
            space_x = self._h_space
            space_y = self._v_space
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container)
        
        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(0, 6, 0, 6)
        self.content_layout.setSpacing(0)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 12)
        self.container.setGraphicsEffect(shadow)
        
    def add_item(self, text: str, index: int, is_selected: bool = False):
        item = ZugzwangDropdownItem(text, index, is_selected, self)
        item.clicked.connect(self._on_item_clicked)
        self.content_layout.addWidget(item)

    def _on_item_clicked(self, text: str, index: int):
        self.itemSelected.emit(text, index)
        self.close()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

class ZugzwangDropdown(QPushButton):
    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self._items = []
        self._current_index = -1
        self._is_open = False
        self._update_style()

    def addItems(self, items: list[str]):
        self._items.extend(items)
        if self._current_index == -1 and self._items:
            self._current_index = 0
            self.setText(self._items[0])

    def clear(self):
        self._items.clear()
        self._current_index = -1
        self.setText("")

    def count(self) -> int:
        return len(self._items)

    def itemText(self, idx: int) -> str:
        if 0 <= idx < len(self._items):
            return self._items[idx]
        return ""

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return ""

    def setCurrentText(self, text: str):
        if text in self._items:
            self._current_index = self._items.index(text)
            self.setText(text)

    def _update_style(self):
        is_blue = self._is_open
        color = "#0A84FF" if is_blue else "#FFFFFF"
        border_color = "#0A84FF" if is_blue else "#3A3A3C"
        chevron_color = "#0A84FF" if is_blue else "#8E8E93"
        bg_col = "#2C2C2E" if is_blue else "#1C1C1E"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_col};
                border: 1px solid {border_color};
                border-radius: 8px;
                color: {color};
                font-family: 'PT Root UI', sans-serif;
                font-size: 14px;
                font-weight: 500;
                padding: 0 12px;
                text-align: left;
                qproperty-iconSize: 10px 10px;
                spacing: 8px;
            }}
            QPushButton:hover {{
                background: #2C2C2E;
            }}
        """)
        
        chevron = FluentIcon.CHEVRON_DOWN_MED.icon(color=chevron_color)
        self.setIcon(chevron)
        self.setIconSize(QSize(10, 10))
        self.setLayoutDirection(Qt.RightToLeft)

    def show_menu(self):
        self._is_open = True
        self._update_style()
        
        menu = ZugzwangDropdownMenu(self.window())
        menu.setMinimumWidth(self.width())
        for i, text in enumerate(self._items):
            menu.add_item(text, i, i == self._current_index)
            
        menu.itemSelected.connect(self._on_item_selected)
        menu.closed.connect(self._on_menu_closed)
        
        # Position menu 
        pos = self.mapToGlobal(self.rect().bottomLeft())
        menu.move(pos.x(), pos.y() + 4)
        menu.show()

    def _on_item_selected(self, text: str, index: int):
        self._current_index = index
        self.setText(text)
        self.currentTextChanged.emit(text)

    def _on_menu_closed(self):
        self._is_open = False
        self._update_style()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_menu()
        super().mouseReleaseEvent(event)


from PySide6.QtWidgets import QLayout
from PySide6.QtCore import QPoint, QRect, QSize

class FlowLayout(QLayout):
    """Standard Qt Flow/Wrap layout that automatically wraps widgets."""
    def __init__(self, parent=None, margin=0, hSpacing=0, vSpacing=0):
        super().__init__(parent)
        self._h_space = hSpacing
        self._v_space = vSpacing
        self.setContentsMargins(margin, margin, margin, margin)
        self._item_list = []

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        if not hasattr(self, '_min_size_cache'):
            self._min_size_cache = {}
        for item in self._item_list:
            if item.isEmpty():
                continue
            item_id = id(item)
            if item_id not in self._min_size_cache:
                self._min_size_cache[item_id] = item.minimumSize()
            size = size.expandedTo(self._min_size_cache[item_id])
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        line_height = 0
        if not hasattr(self, '_size_cache'):
            self._size_cache = {}
            
        for item in self._item_list:
            if item.isEmpty():
                continue
            space_x = self._h_space
            space_y = self._v_space
            
            item_id = id(item)
            if item_id not in self._size_cache:
                self._size_cache[item_id] = item.sizeHint()
            hint = self._size_cache[item_id]
            
            next_x = x + hint.width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()

from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt

class GlassMenu(QMenu):
    """A translucent, glassmorphism context menu matching the macOS aesthetic of the app."""
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setStyleSheet("""
            QMenu {
                background: rgba(44, 44, 46, 0.90);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
                padding: 5px;
            }
            QMenu::item {
                background: transparent;
                padding: 6px 12px;
                border-radius: 6px;
                color: #FFFFFF;
                font-family: 'PT Root UI';
                font-size: 13px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background: rgba(255, 255, 255, 0.1);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 10px;
            }
        """)

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QEvent, QObject, QPoint

class GlassToolTip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self)
        self.label.setStyleSheet("""
            QLabel {
                background: rgba(44, 44, 46, 0.90);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 6px 12px;
                color: #FFFFFF;
                font-family: 'PT Root UI', sans-serif;
                font-size: 13px;
            }
        """)
        self.layout.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

class GlassToolTipFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tooltip = GlassToolTip()
        self.tooltip.hide()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip:
            text = obj.toolTip()
            if text:
                self.tooltip.setText(text)
                self.tooltip.adjustSize()
                try:
                    pos = event.globalPos()
                except AttributeError:
                    pos = obj.mapToGlobal(QPoint(0, obj.height()))
                self.tooltip.move(pos + QPoint(10, 10))
                self.tooltip.show()
                return True
        elif event.type() in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.WindowDeactivate, QEvent.Hide):
            self.tooltip.hide()
        return False

# 1.1.2.2
