from __future__ import annotations
import sys
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsOpacityEffect, QSizePolicy, QApplication
)
from PySide6.QtGui import QColor, Qt, QFont
from PySide6.QtCore import (
    QPropertyAnimation, QRect, QEasingCurve, QTimer, Signal,
    QObject, QEvent, QPoint, QSize
)
from qfluentwidgets import FluentIcon


import re

def _clean_title(text: str) -> str:
    if not text:
        return ""
    # Strip any leading symbols/bullets/emojis: ✗, ✓, ⚠, ×, ✕, etc.
    cleaned = re.sub(r"^[✗✓⚠×✕!•\-\s]+", "", text.strip())
    if not cleaned:
        cleaned = text.strip()
    words = cleaned.split(" ")
    if len(words) > 1 and all(w.istitle() or w.isupper() for w in words):
        return words[0].capitalize() + " " + " ".join(w.lower() for w in words[1:])
    return cleaned[0].upper() + cleaned[1:] if cleaned else ""


class ToastLabel(QLabel):
    """QLabel subclass that accurately computes word-wrapped sizeHint with width bounds."""
    def __init__(self, text: str = "", parent=None, max_width: int = 268):
        super().__init__(text, parent)
        self._max_width = max_width
        self.setWordWrap(True)

    def set_max_width(self, width: int):
        self._max_width = width

    def sizeHint(self) -> QSize:
        txt = self.text()
        if not txt:
            return QSize(0, 0)
        fm = self.fontMetrics()
        rect = fm.boundingRect(
            0, 0, self._max_width, 2000,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            txt
        )
        return QSize(self._max_width, max(rect.height(), 16))


class ToastNotificationManager(QObject):
    _instance = None

    @classmethod
    def instance(cls) -> ToastNotificationManager:
        if not cls._instance:
            cls._instance = ToastNotificationManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._host_window = None
        self.active_toasts: list[ToastNotification] = []

    def set_host_window(self, window):
        if self._host_window is not None and self._host_window != window:
            try:
                self._host_window.removeEventFilter(self)
            except Exception:
                pass
        self._host_window = window
        if window is not None:
            try:
                window.installEventFilter(self)
            except Exception:
                pass

    def get_host_window(self):
        # 1. Active cached host window
        if self._host_window is not None:
            try:
                if self._host_window.isVisible():
                    return self._host_window
            except RuntimeError:
                self._host_window = None

        # 2. Search QApplication top level widgets for MainWindow or FramelessWindow
        from qframelesswindow import FramelessWindow
        for w in QApplication.topLevelWidgets():
            if w.isWindow() and w.isVisible():
                if w.__class__.__name__ == "MainWindow" or isinstance(w, FramelessWindow):
                    self.set_host_window(w)
                    return w

        # 3. Fallback to activeWindow if valid window
        act = QApplication.activeWindow()
        if act and act.isWindow() and act.isVisible():
            self.set_host_window(act)
            return act

        # 4. Fallback to any visible top level window
        top_levels = [w for w in QApplication.topLevelWidgets() if w.isWindow() and w.isVisible()]
        if top_levels:
            self.set_host_window(top_levels[0])
            return top_levels[0]

        return None

    def eventFilter(self, obj, event):
        if obj == self._host_window and event.type() == QEvent.Type.Resize:
            self._reposition()
        return False

    def add(self, toast: ToastNotification):
        if toast not in self.active_toasts:
            self.active_toasts.append(toast)
        toast.closed.connect(lambda t=toast: self.remove(t))
        self._reposition()

    def remove(self, toast: ToastNotification):
        if toast in self.active_toasts:
            self.active_toasts.remove(toast)
            self._reposition()

    def _reposition(self):
        host = self.get_host_window()
        if not host:
            return

        host_rect = host.rect()
        padding_right = 24
        padding_top = 24
        spacing = 10
        y_offset = padding_top

        # Filter out closing toasts from positioning calculation
        visible_active = [t for t in self.active_toasts if not getattr(t, "is_closing", False)]

        for toast in visible_active:
            target_x = host_rect.width() - toast.width() - padding_right
            target_y = y_offset
            target_point = QPoint(target_x, target_y)

            toast.target_pos = target_point
            if toast.isVisible():
                toast.animate_to(target_point)
            else:
                toast.move(target_point)

            y_offset += toast.height() + spacing


class ToastNotification(QFrame):
    closed = Signal(object)

    def __init__(
        self,
        parent=None,
        title: str = "Notification",
        message: str = "",
        n_type: str = "info",
        duration: int = 4000,
        closable: bool = True,
        cancel_text: str | None = None
    ):
        host = ToastNotificationManager.instance().get_host_window()
        if host is not None:
            actual_parent = host
        elif parent is not None:
            actual_parent = parent.window() if hasattr(parent, "window") else parent
        else:
            actual_parent = None

        super().__init__(actual_parent)

        self.n_type = n_type
        self.is_closing = False
        self.is_cancelled = False
        self._move_anim = None
        self._shown_once = False

        self.setFixedWidth(400)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.setStyleSheet("""
            ToastNotification {
                background-color: #2C2C2E;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QLabel { background: transparent; border: none; letter-spacing: 0px; }
        """)

        # Fade in / fade out effect setup
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 13, 16, 13)
        root_layout.setSpacing(14)

        # Style based on notification type per specifications
        glyph_color = "#FFFFFF"
        badge_bg = "#0A84FF"  # default for info/progress
        icon = FluentIcon.INFO

        if n_type == "success":
            icon = FluentIcon.COMPLETED
            glyph_color = "#0A84FF"
            badge_bg = "#3A3A3C"
        elif n_type == "error":
            icon = FluentIcon.CLOSE
            glyph_color = "#E24B4A"
            badge_bg = "#3A3A3C"
            duration = 0
        elif n_type == "warning":
            icon = FluentIcon.INFO
            glyph_color = "#FF9F0A"
            badge_bg = "#3A3A3C"
        elif n_type == "custom":
            icon = FluentIcon.DOCUMENT
            glyph_color = "#FFFFFF"
            badge_bg = "#3A3A3C"
            duration = 0

        # Leading 40x40 icon badge with 9px radius
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(40, 40)
        self.icon_lbl.setStyleSheet(f"background-color: {badge_bg}; border-radius: 9px;")
        pix = icon.icon(color=QColor(glyph_color)).pixmap(20, 20)
        self.icon_lbl.setPixmap(pix)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Text section
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 2, 0, 2)
        text_layout.setSpacing(4)

        formatted_title = _clean_title(title) if title else ""
        self.title_lbl = ToastLabel(formatted_title, max_width=268)
        self.title_lbl.setStyleSheet(
            "color: #FFFFFF; font-family: -apple-system, 'SF Pro Text', 'PT Root UI', sans-serif; "
            "font-size: 15px; font-weight: 600;"
        )

        has_msg = bool(message and message.strip())
        self.msg_lbl = ToastLabel(message if has_msg else "", max_width=268)
        self.msg_lbl.setStyleSheet(
            "color: #8E8E93; font-family: -apple-system, 'SF Pro Text', 'PT Root UI', sans-serif; "
            "font-size: 13px; font-weight: 400;"
        )
        self.msg_lbl.setVisible(has_msg)

        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.msg_lbl)

        root_layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(text_layout, 1)

        # Trailing action (text-only action) or Close button
        self.cancel_btn = None
        self.close_btn = None

        if cancel_text:
            self._add_trailing_action(cancel_text)
        elif closable:
            self._add_close_button()

        # Initial target position (defaults to top-right safe position)
        self.target_pos = QPoint(0, 0)

        # Opacity animation
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        if duration > 0:
            QTimer.singleShot(duration, self.close_anim)

    def _add_trailing_action(self, text: str):
        self.cancel_btn = QPushButton(text)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setFixedHeight(28)
        is_destructive = text.lower() in ["cancel", "stop", "abort"]
        action_color = "#E24B4A" if is_destructive else "#0A84FF"
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {action_color};
                font-family: -apple-system, 'SF Pro Text', 'PT Root UI', sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 0 4px;
                margin: 0;
            }}
            QPushButton:hover {{ color: {action_color}; opacity: 0.8; }}
            QPushButton:pressed {{ color: {action_color}; opacity: 0.6; }}
            QPushButton:disabled {{ color: #636366; }}
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.layout().addWidget(self.cancel_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _add_close_button(self):
        self.close_btn = QPushButton()
        self.close_btn.setIcon(FluentIcon.CLOSE.icon(color=QColor("#8E8E93")))
        self.close_btn.setIconSize(QSize(12, 12))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.08); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.04); }
        """)
        self.close_btn.clicked.connect(self.close_anim)
        self.layout().addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)

    def _on_cancel(self):
        self.is_cancelled = True
        if self.cancel_btn:
            self.cancel_btn.setText("Stopping...")
            self.cancel_btn.setEnabled(False)

    def animate_to(self, target_point: QPoint):
        if self.target_pos == target_point and self.pos() == target_point:
            return
        self.target_pos = target_point
        if self.is_closing:
            return

        if self._move_anim is not None:
            self._move_anim.stop()

        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(target_point)
        anim.start()
        self._move_anim = anim

    def showEvent(self, event):
        super().showEvent(event)
        if self.is_closing:
            return
        self.move(self.target_pos)

        if not self._shown_once:
            self._shown_once = True
            self.anim.stop()
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(1.0)
            self.anim.start()

    def set_message(self, msg: str):
        prev_height = self.height()
        has_msg = bool(msg and msg.strip())
        self.msg_lbl.setText(msg if has_msg else "")
        self.msg_lbl.setVisible(has_msg)
        self.adjustSize()
        if self.height() != prev_height:
            ToastNotificationManager.instance()._reposition()

    def close_anim(self):
        if self.is_closing:
            return
        self.is_closing = True

        # Stop any active position animation
        if self._move_anim is not None:
            self._move_anim.stop()

        # Fade out in place
        self.anim.stop()
        self.anim.setStartValue(self.opacity_effect.opacity())
        self.anim.setEndValue(0.0)

        def _on_finished():
            self.closed.emit(self)
            self.close()
            self.deleteLater()

        self.anim.finished.connect(_on_finished)
        self.anim.start()

        # Trigger reposition for other active toasts immediately so they slide up smoothly
        ToastNotificationManager.instance()._reposition()

    # Drop-in replacement for InfoBar methods
    @classmethod
    def success(cls, title, content="", duration=4000, parent=None, **kwargs):
        return cls._show_toast(title, content, "success", duration, parent)

    @classmethod
    def error(cls, title, content="", duration=0, parent=None, **kwargs):
        return cls._show_toast(title, content, "error", duration, parent)

    @classmethod
    def warning(cls, title, content="", duration=4000, parent=None, **kwargs):
        return cls._show_toast(title, content, "warning", duration, parent)

    @classmethod
    def info(cls, title, content="", duration=4000, parent=None, **kwargs):
        return cls._show_toast(title, content, "info", duration, parent)

    @classmethod
    def custom(cls, parent, title, message, cancel_text=None, **kwargs):
        return cls._show_toast(title, message, "custom", 0, parent, cancel_text=cancel_text)

    @classmethod
    def _show_toast(cls, title, message, n_type, duration, parent=None, cancel_text=None, closable=True):
        toast = cls(
            parent=parent,
            title=title,
            message=message,
            n_type=n_type,
            duration=duration,
            closable=closable,
            cancel_text=cancel_text
        )
        toast.adjustSize()
        ToastNotificationManager.instance().add(toast)
        toast.show()
        toast.raise_()
        return toast

# 1.1.0
