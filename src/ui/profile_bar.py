"""
ZUGZWANG - Profile Bar & Profile Management Dialogs
Horizontal profile selector bar and native macOS dark dialogs for multi-profile Bewerbung workspace.
"""

from __future__ import annotations
from typing import Optional, Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QMenu, QDialog, QLineEdit, QSizePolicy, QApplication
)

try:
    from qfluentwidgets import FluentIcon
    def _create_add_icon(color: str) -> QIcon:
        return FluentIcon.ADD.icon(color=color)
except Exception:
    from .icons import _render_tinted_icon
    def _create_add_icon(color: str) -> QIcon:
        return _render_tinted_icon("plus.svg", 14, color)


from ..services import profile_service
from ..services.profile_service import Profile
from ..core.config import config_manager
from ..core.events import event_bus, EventBus
from ..core.i18n import tr, get_language
from ..core.logger import get_logger

logger = get_logger(__name__)


class ProfileNameDialog(QDialog):
    """Native macOS dark style modal dialog for creating or editing a profile."""

    def __init__(self, mode: str = "create", initial_name: str = "", initial_beruf: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = mode
        self._initial_name = initial_name
        self._initial_beruf = initial_beruf
        self._confirmed_name = ""
        self._confirmed_beruf = ""
        self._lang = getattr(parent, "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))

        win_title = tr("profiles.create_title", self._lang) if mode == "create" else tr("profiles.rename_title", self._lang)
        self.setWindowTitle(win_title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 275)

        if parent:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        container = QFrame(self)
        container.setObjectName("ProfileDialogContainer")
        container.setStyleSheet("""
            QFrame#ProfileDialogContainer {
                background: #1E1E22;
                border: 0.5px solid #3A3A3C;
                border-radius: 12px;
            }
        """)
        root_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        # Title
        title = QLabel(win_title)
        title.setStyleSheet("color: #FFFFFF; font-family: system-ui, -apple-system, sans-serif; font-size: 15px; font-weight: 600; background: transparent;")
        layout.addWidget(title)

        sub = QLabel(tr("profiles.dialog_sub", self._lang))
        sub.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 12px; background: transparent;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Input Name
        self.input = QLineEdit()
        self.input.setMaxLength(30)
        self.input.setPlaceholderText(tr("profiles.placeholder", self._lang))
        self.input.setText(initial_name)
        self.input.setFixedHeight(32)
        self.input.setStyleSheet("""
            QLineEdit {
                background: #2C2C2E;
                border: 0.5px solid #3A3A3C;
                border-radius: 7px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 13px;
                padding: 0 10px;
            }
            QLineEdit:focus {
                border: 1px solid #0A84FF;
            }
        """)
        self.input.textChanged.connect(self._clear_error)
        self.input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self.input)

        # Input Beruf (Target profession / Ausbildungsberuf)
        beruf_lbl = QLabel(tr("profiles.target_job_label", self._lang))
        beruf_lbl.setStyleSheet("color: #A1A1A6; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 500; background: transparent; margin-top: 4px;")
        layout.addWidget(beruf_lbl)

        self.beruf_input = QLineEdit()
        self.beruf_input.setMaxLength(50)
        self.beruf_input.setPlaceholderText(tr("profiles.target_job_placeholder", self._lang))
        self.beruf_input.setText(initial_beruf)
        self.beruf_input.setFixedHeight(32)
        self.beruf_input.setStyleSheet("""
            QLineEdit {
                background: #2C2C2E;
                border: 0.5px solid #3A3A3C;
                border-radius: 7px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 13px;
                padding: 0 10px;
            }
            QLineEdit:focus {
                border: 1px solid #0A84FF;
            }
        """)
        self.beruf_input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self.beruf_input)

        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #FF453A; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; background: transparent;")
        self.error_lbl.setVisible(False)
        layout.addWidget(self.error_lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch(1)

        self.btn_cancel = QPushButton(tr("dialog.cancel", self._lang))
        self.btn_cancel.setFixedSize(80, 30)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #2C2C2E;
                border: 0.5px solid #3A3A3C;
                border-radius: 7px;
                color: #E5E5EA;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #3A3A3C;
                color: #FFFFFF;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        confirm_label = tr("profiles.btn_save", self._lang) if mode == "rename" else tr("profiles.btn_create", self._lang)
        self.btn_confirm = QPushButton(confirm_label)
        self.btn_confirm.setFixedSize(80, 30)
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: #0A84FF;
                border: none;
                border-radius: 7px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #0071E3;
            }
        """)
        self.btn_confirm.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)
        self.input.setFocus()
        self.input.selectAll()

    def _clear_error(self):
        self.error_lbl.setVisible(False)
        self.error_lbl.setText("")

    def _on_confirm(self):
        name = self.input.text().strip()
        if not name:
            self.error_lbl.setText(tr("profiles.error_empty", self._lang))
            self.error_lbl.setVisible(True)
            return

        existing_profiles = profile_service.get_profiles()
        for p in existing_profiles:
            if p.name.lower() == name.lower():
                if self.mode == "rename" and p.name.lower() == self._initial_name.lower():
                    continue
                self.error_lbl.setText(tr("profiles.error_exists", self._lang))
                self.error_lbl.setVisible(True)
                return

        self._confirmed_name = name
        self._confirmed_beruf = self.beruf_input.text().strip()
        self.accept()

    def get_name(self) -> str:
        return self._confirmed_name

    def get_beruf(self) -> str:
        return self._confirmed_beruf

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class ProfileDeleteDialog(QDialog):
    """Confirmation modal for profile deletion."""

    def __init__(self, profile_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.profile_name = profile_name
        self._lang = getattr(parent, "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))

        self.setWindowTitle(tr("profiles.delete_title", self._lang))
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(400, 190)

        if parent:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        container = QFrame(self)
        container.setObjectName("DeleteContainer")
        container.setStyleSheet("""
            QFrame#DeleteContainer {
                background: #1E1E22;
                border: 0.5px solid #3A3A3C;
                border-radius: 12px;
            }
        """)
        root_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        del_title = tr("profiles.delete_confirm", self._lang).replace("{name}", profile_name)
        title = QLabel(del_title)
        title.setStyleSheet("color: #FFFFFF; font-family: system-ui, -apple-system, sans-serif; font-size: 15px; font-weight: 600; background: transparent;")
        layout.addWidget(title)

        body = QLabel(tr("profiles.delete_warning", self._lang))
        body.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 12px; line-height: 1.4; background: transparent;")
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch(1)

        btn_cancel = QPushButton(tr("dialog.cancel", self._lang))
        btn_cancel.setFixedSize(80, 30)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #2C2C2E;
                border: 0.5px solid #3A3A3C;
                border-radius: 7px;
                color: #E5E5EA;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #3A3A3C;
                color: #FFFFFF;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_delete = QPushButton(tr("profiles.btn_delete", self._lang))
        btn_delete.setFixedSize(80, 30)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #FF453A;
                border: none;
                border-radius: 7px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #D70015;
            }
        """)
        btn_delete.clicked.connect(self.accept)
        btn_layout.addWidget(btn_delete)

        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class ProfilePill(QPushButton):
    """Pill button representing a single profile."""

    profile_clicked = Signal(str)
    rename_requested = Signal(str)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, profile: Profile, is_active: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.profile = profile
        self.is_active = is_active

        display_name = profile.name
        if len(display_name) > 24:
            display_name = display_name[:22].strip() + "…"
        self.setText(display_name)
        self.setToolTip(profile.name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)

        self._apply_style()
        self.clicked.connect(lambda: self.profile_clicked.emit(self.profile.id))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_style(self):
        if self.is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #0A84FF;
                    border: none;
                    border-radius: 6px;
                    color: #FFFFFF;
                    font-family: system-ui, -apple-system, sans-serif;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #0071E3;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 6px;
                    color: #AEAEB2;
                    font-family: system-ui, -apple-system, sans-serif;
                    font-size: 12px;
                    font-weight: 500;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #FFFFFF;
                }
            """)

    def _show_context_menu(self, pos: QPoint):
        from .components import ZugzwangDropdownMenu
        lang = getattr(self.parent(), "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))
        
        menu = ZugzwangDropdownMenu(self.window())
        menu.add_item(
            tr("profiles.action_edit_profile", lang),
            callback=lambda: self.rename_requested.emit(self.profile.id)
        )
        menu.add_item(
            tr("profiles.action_duplicate", lang),
            callback=lambda: self.duplicate_requested.emit(self.profile.id)
        )
        menu.add_divider()
        menu.add_item(
            tr("profiles.action_delete", lang),
            is_disabled=self.profile.is_default,
            is_destructive=not self.profile.is_default,
            callback=lambda: self.delete_requested.emit(self.profile.id)
        )

        global_pos = self.mapToGlobal(pos)
        menu.move(global_pos)
        menu.show()


class ProfileAddButton(QPushButton):
    """Plus button for creating profiles with crisp icon and smooth hover states."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProfileAddBtn")
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        lang = getattr(parent, "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))
        self.setToolTip(tr("profiles.tooltip_add", lang))

        self._icon_normal = _create_add_icon("#D1D1D6")
        self._icon_hover = _create_add_icon("#0A84FF")

        self.setIcon(self._icon_normal)
        self.setIconSize(QSize(13, 13))
        self.setStyleSheet("""
            QPushButton#ProfileAddBtn {
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton#ProfileAddBtn:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QPushButton#ProfileAddBtn:pressed {
                background: rgba(255, 255, 255, 0.06);
            }
        """)

    def enterEvent(self, event):
        self.setIcon(self._icon_hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icon_normal)
        super().leaveEvent(event)


class ProfileBar(QFrame):
    """Horizontal profile bar with edge-to-edge background spanning the middle section."""

    profile_switched = Signal(str)  # profile_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setObjectName("ProfileBarRoot")
        self.setStyleSheet("""
            QFrame#ProfileBarRoot {
                background-color: #1C1C1E;
                border: 1px solid #2C2C2E;
                border-radius: 12px;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignCenter)

        # Scroll area with center alignment
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 3px;
                background: transparent;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #3A3A3C;
                border-radius: 1px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
                background: transparent;
            }
        """)

        # Centered wrapper widget
        self.wrapper = QWidget()
        self.wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QHBoxLayout(self.wrapper)
        wrapper_layout.setContentsMargins(12, 4, 12, 4)
        wrapper_layout.setAlignment(Qt.AlignCenter)

        # The pill track container (transparent inside edge-to-edge root)
        self.track = QFrame()
        self.track.setObjectName("ProfileTrack")
        self.track.setStyleSheet("""
            QFrame#ProfileTrack {
                background: transparent;
                border: none;
            }
        """)

        self.track_layout = QHBoxLayout(self.track)
        self.track_layout.setContentsMargins(0, 0, 0, 0)
        self.track_layout.setSpacing(4)
        self.track_layout.setAlignment(Qt.AlignCenter)

        wrapper_layout.addWidget(self.track)
        self.scroll_area.setWidget(self.wrapper)
        main_layout.addWidget(self.scroll_area)

        # '+' Button with crisp vector icon
        self.btn_add = ProfileAddButton(self)
        self.btn_add.clicked.connect(self._on_add_profile)

        self._profile_pills: list[ProfilePill] = []
        self._profiles: list[Profile] = []
        self._active_id: str = ""


        self.reload_profiles()

    def reload_profiles(self):
        """Reload profile list from database and re-render pills."""
        # Clear existing items in track
        while self.track_layout.count():
            item = self.track_layout.takeAt(0)
            w = item.widget()
            if w and w != self.btn_add:
                w.deleteLater()

        self._profile_pills.clear()
        self._profiles = profile_service.get_profiles()
        self._active_id = profile_service.get_active_profile_id()

        for prof in self._profiles:
            is_active = (prof.id == self._active_id)
            pill = ProfilePill(prof, is_active=is_active)
            pill.profile_clicked.connect(self._on_pill_clicked)
            pill.rename_requested.connect(self._on_rename_profile)
            pill.duplicate_requested.connect(self._on_duplicate_profile)
            pill.delete_requested.connect(self._on_delete_profile)
            self._profile_pills.append(pill)
            self.track_layout.addWidget(pill)

        # Subtle separator before [+]
        sep = QFrame()
        sep.setFixedSize(1, 14)
        sep.setStyleSheet("background: #3A3A3C; border: none;")
        self.track_layout.addWidget(sep)

        # Add '+' button inside the track
        self.track_layout.addWidget(self.btn_add)

    def switch_to_index(self, index: int):
        """Switch to profile by index (0-indexed). Used for Cmd+1..9 shortcuts."""
        if 0 <= index < len(self._profiles):
            target = self._profiles[index]
            self._on_pill_clicked(target.id)

    def _on_pill_clicked(self, profile_id: str):
        if profile_id == self._active_id:
            return
        event_bus.emit(EventBus.PROFILE_SWITCHED, profile_id=profile_id)
        self.profile_switched.emit(profile_id)

    def set_active_profile(self, profile_id: str):
        """Update active profile without re-fetching entire list if not needed."""
        self._active_id = profile_id
        for pill in self._profile_pills:
            is_active = (pill.profile.id == profile_id)
            pill.is_active = is_active
            pill._apply_style()

    def _on_add_profile(self):
        dlg = ProfileNameDialog(mode="create", parent=self.window())
        if dlg.exec():
            name = dlg.get_name()
            beruf = dlg.get_beruf()
            if name:
                try:
                    new_prof = profile_service.create_profile(name, beruf=beruf)
                    self.reload_profiles()
                    event_bus.emit(EventBus.PROFILE_SWITCHED, profile_id=new_prof.id)
                    self.profile_switched.emit(new_prof.id)
                except Exception as e:
                    logger.error(f"Failed to create profile: {e}")

    def _on_rename_profile(self, profile_id: str):
        prof = profile_service.get_profile(profile_id)
        if not prof:
            return
        dlg = ProfileNameDialog(mode="rename", initial_name=prof.name, initial_beruf=prof.beruf, parent=self.window())
        if dlg.exec():
            new_name = dlg.get_name()
            new_beruf = dlg.get_beruf()
            if new_name:
                try:
                    profile_service.update_profile(profile_id, new_name=new_name, new_beruf=new_beruf)
                    self.reload_profiles()
                    if profile_id == self._active_id:
                        event_bus.emit(EventBus.PROFILE_SWITCHED, profile_id=profile_id)
                        self.profile_switched.emit(profile_id)
                except Exception as e:
                    logger.error(f"Failed to update profile: {e}")

    def _on_duplicate_profile(self, profile_id: str):
        try:
            cloned = profile_service.duplicate_profile(profile_id)
            self.reload_profiles()
            event_bus.emit(EventBus.PROFILE_SWITCHED, profile_id=cloned.id)
            self.profile_switched.emit(cloned.id)
        except Exception as e:
            logger.error(f"Failed to duplicate profile: {e}")

    def _on_delete_profile(self, profile_id: str):
        prof = profile_service.get_profile(profile_id)
        if not prof or prof.is_default:
            return
        dlg = ProfileDeleteDialog(prof.name, parent=self.window())
        if dlg.exec():
            try:
                active_before = profile_service.get_active_profile_id()
                profile_service.delete_profile(profile_id)
                new_active = profile_service.get_active_profile_id()
                self.reload_profiles()
                if active_before == profile_id:
                    event_bus.emit(EventBus.PROFILE_SWITCHED, profile_id=new_active)
                    self.profile_switched.emit(new_active)
            except Exception as e:
                logger.error(f"Failed to delete profile: {e}")

# 1.5.0
