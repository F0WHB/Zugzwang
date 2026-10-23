"""
ZUGZWANG - Sender Pool Dialog
Modal dialog to manage multiple SMTP sender accounts and rotation settings.
Senior Grade macOS Aesthetic 3.0.
"""

from __future__ import annotations
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QCursor, QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea
)

from src.ui.components import MacSwitch, MacComboBox, ZugzwangDialog
from ..services import sender_pool_service
from ..services.sender_pool_service import SenderAccount
from ..core.config import config_manager
from ..core.i18n import tr, get_language
from ..core.logger import get_logger

logger = get_logger(__name__)


class VectorCloseButton(QPushButton):
    """Crisp vector close button with smooth circular hover backdrop."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Close")
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(255, 255, 255, 40 if self._hover else 20))
        p.setPen(Qt.NoPen)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        pen = QPen(QColor(255, 255, 255 if self._hover else 210), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        d = 4.2
        p.drawLine(cx - d, cy - d, cx + d, cy + d)
        p.drawLine(cx + d, cy - d, cx - d, cy + d)


class VectorDeleteButton(QPushButton):
    """Crisp vector delete button with soft red hover highlight."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Remove account from pool")
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover:
            p.setBrush(QColor(255, 69, 58, 35))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        pen = QPen(QColor('#FF453A' if self._hover else '#8E8E93'), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        d = 4.0
        p.drawLine(cx - d, cy - d, cx + d, cy + d)
        p.drawLine(cx + d, cy - d, cx - d, cy + d)


class AccountRowWidget(QFrame):
    """Row widget representing a single sender account in the pool."""

    changed = Signal()
    deleted = Signal(str)

    def __init__(self, account: SenderAccount, parent: QWidget | None = None):
        super().__init__(parent)
        self.account = account
        self.setFixedHeight(58)
        self.setStyleSheet("""
            AccountRowWidget {
                background: #252528;
                border: 1px solid #333336;
                border-radius: 10px;
            }
            AccountRowWidget:hover {
                border-color: #3E3E42;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        self._lang = getattr(parent, "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))

        # 1. MacSwitch for enabled state
        self.switch = MacSwitch(self)
        self.switch.setOnColor("#30D158")
        self.switch.setChecked(account.is_enabled)
        self.switch.setToolTip(tr("sender_pool.toggle_tooltip", self._lang))
        self.switch.toggled.connect(self._on_toggle_enabled)
        layout.addWidget(self.switch, 0)

        # 2. Account Details
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(2)

        self.lbl_email = QLabel(account.email)
        self.lbl_email.setStyleSheet(
            "color: #FFFFFF; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; "
            "font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        info_col.addWidget(self.lbl_email)

        display_name = account.name or tr("sender_pool.primary_sender", self._lang)
        cap_info = f"{display_name}  •  {tr('sender_pool.daily_cap', self._lang)}: {account.daily_limit} {tr('sender_pool.emails', self._lang)}  •  {tr('sender_pool.sent_today', self._lang)}: {account.sent_today}"
        self.lbl_sub = QLabel(cap_info)
        self.lbl_sub.setStyleSheet(
            "color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; "
            "font-size: 11px; background: transparent; border: none;"
        )
        info_col.addWidget(self.lbl_sub)
        layout.addLayout(info_col, 1)

        # 3. Test Button
        self.btn_test = QPushButton(tr("sender_pool.btn_test", self._lang))
        self.btn_test.setFixedHeight(28)
        self.btn_test.setMinimumWidth(68)
        self.btn_test.setFocusPolicy(Qt.NoFocus)
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.setStyleSheet("""
            QPushButton {
                background: #2C2C2E;
                color: #CED3DE;
                border: 1px solid #3A3A3C;
                outline: none;
                border-radius: 6px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: #3A3A3C;
                color: #FFFFFF;
                border-color: #48484A;
            }
            QPushButton:focus {
                outline: none;
            }
        """)
        self.btn_test.clicked.connect(self._on_test_clicked)
        layout.addWidget(self.btn_test, 0)

        # 4. Delete Button
        self.btn_del = VectorDeleteButton(self)
        self.btn_del.setToolTip(tr("sender_pool.delete_tooltip", self._lang))
        self.btn_del.clicked.connect(lambda: self.deleted.emit(self.account.id))
        layout.addWidget(self.btn_del, 0)

    def _on_toggle_enabled(self, checked: bool):
        self.account.is_enabled = checked
        sender_pool_service.update_sender_account(self.account)
        self.changed.emit()

    def _on_test_clicked(self):
        self.btn_test.setText("...")
        self.btn_test.setEnabled(False)
        s = config_manager.settings
        host = s.email_smtp_host or "smtp.gmail.com"
        port = int(s.email_smtp_port or 587)
        use_ssl = bool(s.email_smtp_ssl)

        from ..utils.db_worker import run_in_thread
        run_in_thread(
            sender_pool_service.test_smtp_account,
            self.account,
            host=host,
            port=port,
            use_ssl=use_ssl,
            on_result=self._on_test_result
        )

    def _on_test_result(self, result: tuple[bool, str]):
        self.btn_test.setEnabled(True)
        ok, msg = result
        if ok:
            self.btn_test.setText(tr("sender_pool.ready", self._lang))
            self.btn_test.setStyleSheet("""
                QPushButton {
                    background: rgba(48, 209, 88, 0.16);
                    color: #30D158;
                    border: none;
                    outline: none;
                    border-radius: 6px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 10px;
                }
                QPushButton:focus {
                    outline: none;
                }
            """)
        else:
            self.btn_test.setText(tr("sender_pool.failed", self._lang))
            self.btn_test.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 69, 58, 0.16);
                    color: #FF453A;
                    border: none;
                    outline: none;
                    border-radius: 6px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 10px;
                }
                QPushButton:focus {
                    outline: none;
                }
            """)
            dlg = ZugzwangDialog(
                tr("sender_pool.test_failed", self._lang),
                f"{tr('sender_pool.account', self._lang)}: {self.account.email}\n\n{tr('sender_pool.error', self._lang)}: {msg}",
                self.window(),
                single_button=True,
                width=380
            )
            dlg.exec()


class SenderPoolDialog(QDialog):
    """Modal dialog for managing the multi-sender pool and rotation policy."""

    pool_updated = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._language = getattr(parent, "_language", None) or get_language(getattr(getattr(config_manager, "settings", None), "app_language", None))
        self.setWindowTitle(tr("sender_pool.window_title", self._language))
        self.setFixedSize(620, 620)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        if parent:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        container = QFrame(self)
        container.setObjectName("PoolDialogContainer")
        container.setStyleSheet("""
            QFrame#PoolDialogContainer {
                background: #1C1C1E;
                border: 1px solid #3A3A3C;
                border-radius: 16px;
            }
        """)
        root_layout.addWidget(container)

        main_lyt = QVBoxLayout(container)
        main_lyt.setContentsMargins(22, 20, 22, 18)
        main_lyt.setSpacing(14)

        # ── Header ──
        head_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel(tr("sender_pool.title", self._language))
        title.setStyleSheet("color: #FFFFFF; font-family: system-ui, -apple-system, sans-serif; font-size: 18px; font-weight: 700; background: transparent; border: none;")
        title_box.addWidget(title)

        sub = QLabel(tr("sender_pool.subtitle", self._language))
        sub.setStyleSheet("color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 12px; background: transparent; border: none;")
        title_box.addWidget(sub)
        head_row.addLayout(title_box, 1)

        btn_close = VectorCloseButton(self)
        btn_close.clicked.connect(self.accept)
        head_row.addWidget(btn_close, 0, Qt.AlignTop)
        main_lyt.addLayout(head_row)

        # ── Rotation Policy Selector ──
        mode_box = QVBoxLayout()
        mode_box.setSpacing(6)
        lbl_rot = QLabel(tr("sender_pool.rotation_strategy", self._language))
        lbl_rot.setStyleSheet("color: #636366; font-family: system-ui, sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 1.1px; background: transparent; border: none;")
        mode_box.addWidget(lbl_rot)

        self.cmb_rotation = MacComboBox()
        self.cmb_rotation.addItem(tr("sender_pool.rot_pairs", self._language), "pairs")
        self.cmb_rotation.addItem(tr("sender_pool.rot_single", self._language), "single")
        self.cmb_rotation.addItem(tr("sender_pool.rot_batch5", self._language), "batch5")
        self.cmb_rotation.addItem(tr("sender_pool.rot_none", self._language), "none")
        self.cmb_rotation.setStyleSheet("""
            QComboBox {
                background: #252528;
                color: #FFFFFF;
                border: 1px solid #333336;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #3E3E42;
            }
        """)
        current_mode = getattr(config_manager.settings, "email_rotation_mode", "pairs")
        idx = self.cmb_rotation.findData(current_mode)
        if idx >= 0:
            self.cmb_rotation.setCurrentIndex(idx)
        self.cmb_rotation.currentIndexChanged.connect(self._on_rotation_changed)
        mode_box.addWidget(self.cmb_rotation)
        main_lyt.addLayout(mode_box)

        # ── Accounts List Scroll Area ──
        acc_box = QVBoxLayout()
        acc_box.setSpacing(6)
        lbl_accounts = QLabel(tr("sender_pool.configured_accounts", self._language))
        lbl_accounts.setStyleSheet("color: #636366; font-family: system-ui, sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 1.1px; background: transparent; border: none;")
        acc_box.addWidget(lbl_accounts)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3A3A3C;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #48484A;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
        """)

        self.accounts_container = QWidget()
        self.accounts_container.setStyleSheet("background: transparent;")
        self.accounts_layout = QVBoxLayout(self.accounts_container)
        self.accounts_layout.setContentsMargins(0, 0, 8, 0)
        self.accounts_layout.setSpacing(8)
        self.accounts_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self.accounts_container)
        acc_box.addWidget(scroll, 1)
        main_lyt.addLayout(acc_box, 1)

        # ── Add New Account Card ──
        add_card = QFrame()
        add_card.setStyleSheet("""
            QFrame {
                background: #252528;
                border: 1px solid #333336;
                border-radius: 10px;
            }
        """)
        add_lyt = QVBoxLayout(add_card)
        add_lyt.setContentsMargins(14, 12, 14, 12)
        add_lyt.setSpacing(10)

        lbl_add_title = QLabel(tr("sender_pool.add_title", self._language))
        lbl_add_title.setStyleSheet("color: #636366; font-size: 10px; font-weight: 700; letter-spacing: 1.1px; background: transparent; border: none;")
        add_lyt.addWidget(lbl_add_title)

        # Inputs Row 1: Email & Password
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText(tr("sender_pool.placeholder_email", self._language))
        self.input_email.setFixedHeight(34)
        self.input_email.setStyleSheet(self._input_style())
        r1.addWidget(self.input_email, 1)

        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText(tr("sender_pool.placeholder_pass", self._language))
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setFixedHeight(34)
        self.input_pass.setStyleSheet(self._input_style())
        r1.addWidget(self.input_pass, 1)
        add_lyt.addLayout(r1)

        # Inputs Row 2: Name & Add Button
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText(tr("sender_pool.placeholder_name", self._language))
        self.input_name.setFixedHeight(34)
        self.input_name.setStyleSheet(self._input_style())
        r2.addWidget(self.input_name, 1)

        self.btn_add = QPushButton(tr("sender_pool.btn_add", self._language))
        self.btn_add.setFixedHeight(34)
        self.btn_add.setFixedWidth(115)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #0A84FF;
                color: #FFFFFF;
                border: none;
                border-radius: 7px;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #0071E3;
            }
        """)
        self.btn_add.clicked.connect(self._on_add_account)
        r2.addWidget(self.btn_add, 0)
        add_lyt.addLayout(r2)

        main_lyt.addWidget(add_card)

        # ── Bottom Bar ──
        bot_row = QHBoxLayout()
        bot_row.setContentsMargins(0, 4, 0, 0)
        self.lbl_pool_status = QLabel("")
        self.lbl_pool_status.setStyleSheet("""
            QLabel {
                background: rgba(48, 209, 88, 0.12);
                border: none;
                color: #30D158;
                border-radius: 8px;
                padding: 6px 12px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        bot_row.addWidget(self.lbl_pool_status, 1)

        btn_done = QPushButton(tr("sender_pool.btn_done", self._language))
        btn_done.setFixedHeight(32)
        btn_done.setFixedWidth(84)
        btn_done.setCursor(Qt.PointingHandCursor)
        btn_done.setStyleSheet("""
            QPushButton {
                background: #0A84FF;
                border: none;
                color: #FFFFFF;
                border-radius: 8px;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #0071E3;
            }
        """)
        btn_done.clicked.connect(self.accept)
        bot_row.addWidget(btn_done, 0)
        main_lyt.addLayout(bot_row)

        self._load_accounts_ui()

    def _input_style(self) -> str:
        return """
            QLineEdit {
                background: #1C1C1E;
                color: #FFFFFF;
                border: 1px solid #3A3A3C;
                border-radius: 7px;
                padding: 0 10px;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #0A84FF;
            }
        """

    def _load_accounts_ui(self):
        while self.accounts_layout.count():
            item = self.accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = sender_pool_service.get_sender_accounts()
        for acc in accounts:
            row = AccountRowWidget(acc, self.accounts_container)
            row.changed.connect(self._on_pool_changed)
            row.deleted.connect(self._on_delete_account)
            self.accounts_layout.addWidget(row)

        enabled_count = len([a for a in accounts if a.is_enabled])
        total_cap = sum(a.daily_limit for a in accounts if a.is_enabled)
        mode = self.cmb_rotation.currentData()
        mode_label = self.cmb_rotation.currentText().split("—")[0].strip()
        if "(" in mode_label:
            mode_label = mode_label.split("(")[0].strip()
        mode_text = tr("sender_pool.rot_none", self._language) if mode == "none" else mode_label
        self.lbl_pool_status.setText(f"● {enabled_count} {tr('sender_pool.status_active', self._language)}  •  {tr('sender_pool.capacity', self._language)}: ~{total_cap}/{tr('sender_pool.emails_per_day', self._language)}  •  {mode_text}")
        self.pool_updated.emit()

    def _on_rotation_changed(self):
        mode = self.cmb_rotation.currentData()
        config_manager.settings.email_rotation_mode = mode
        config_manager.save()
        self._load_accounts_ui()

    def _on_pool_changed(self):
        self._load_accounts_ui()

    def _on_delete_account(self, account_id: str):
        sender_pool_service.delete_sender_account(account_id)
        self._load_accounts_ui()

    def _on_add_account(self):
        email = self.input_email.text().strip()
        pwd = self.input_pass.text()
        name = self.input_name.text().strip()

        if not email or "@" not in email:
            ZugzwangDialog(
                tr("sender_pool.invalid_email_title", self._language),
                tr("sender_pool.invalid_email_msg", self._language),
                self,
                single_button=True,
                width=360
            ).exec()
            return
        if not pwd:
            ZugzwangDialog(
                tr("sender_pool.missing_password_title", self._language),
                tr("sender_pool.missing_password_msg", self._language),
                self,
                single_button=True,
                width=380
            ).exec()
            return

        sender_pool_service.add_sender_account(email, pwd, name=name, daily_limit=100)
        self.input_email.clear()
        self.input_pass.clear()
        self.input_name.clear()
        self._load_accounts_ui()

# 1.5.0
