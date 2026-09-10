from __future__ import annotations
from .toast_system import ToastNotification
_SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        background: #1a1a1a;
        width: 4px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #333333;
        border-radius: 2px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: #444444;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
        background: transparent;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
    }
    QScrollBar:horizontal {
        height: 0px;
        background: transparent;
    }
"""
"""
ZUGZWANG - Motivation Letter Edit Workspace
Auto-generates an Anschreiben from persisted lead data.

Improvements over v1:
  - Letter word / char counter in editor header
  - Per-lead letter history (undo to previous saved version)
  - Batch export: export letters for all filtered leads at once
  - Export as .docx (python-docx) in addition to .txt
  - Find & Replace toolbar inside the editor (Ctrl+H)
  - Placeholder audit: highlights any un-filled {{...}} remaining
  - Letter preview mode: read-only styled view toggled by a button
  - Auto-save on lead switch (debounced, 800ms)
  - Template variable list shown inline in the Edit Template dialog
  - Sender block injected automatically from settings (if set)
  - Status bar shows word count + last saved timestamp
"""


import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QCoreApplication, QStandardPaths, QUrl, QThread, QEvent, QPoint, QMimeData
from PySide6.QtGui import (
    QDesktopServices,
    QGuiApplication,
    QTextCharFormat,
    QColor,
    QFont,
    QTextCursor,
    QTextBlockFormat,
    QKeySequence,
    QShortcut,
    QPalette,
    QDrag,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QAbstractItemView,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSpacerItem,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
    QScrollBar,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
)
from .toast_system import ToastNotification as InfoBar
from qfluentwidgets import LineEdit, PushButton, InfoBarPosition, CaptionLabel, FluentIcon, IconWidget, Action
from .components import StatCard, GlassToolTipFilter
from ..core.i18n import tr, get_language


class SegmentTabButton(QPushButton):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._base_label = label
        self._count = 0
        self._is_active = False
        self.setFixedHeight(28)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        self._display = QLabel(label)
        self._display.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._display.setAlignment(Qt.AlignCenter)
        self._display.setTextFormat(Qt.RichText)
        self._display.setStyleSheet(
            "background: transparent; border: none;"
        )
        layout.addWidget(self._display)

        self.active_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid #4CAF50;
                border-radius: 0px;
            }
        """
        self.inactive_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                border-radius: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.03);
            }
        """
        self.setStyleSheet(self.inactive_style)
        self._refresh_label()

    def set_active(self, active: bool):
        self._is_active = active
        self.setChecked(active)
        self.setStyleSheet(self.active_style if active else self.inactive_style)
        self._refresh_label()

    def set_count(self, count: int):
        self._count = count
        self._refresh_label()

    def _refresh_label(self):
        if self._is_active:
            label_color = "#ffffff"
            count_color = "#888888"
            weight = 500
        else:
            label_color = "#aaaaaa"
            count_color = "#555555"
            weight = 400
        count_str = f" {self._count}" if self._count > 0 else ""
        self._display.setText(
            f"<span style='font-family: system-ui, -apple-system, sans-serif; "
            f"font-size: 12px; font-weight: {weight}; color: {label_color};'>"
            f"{self._base_label}</span>"
            f"<span style='font-family: system-ui, -apple-system, sans-serif; "
            f"font-size: 11px; font-weight: {weight}; color: {count_color};'>"
            f"{count_str}</span>"
        )

from ..core.config import get_exports_dir, get_memory_db_path, config_manager
from ..core.models import LeadRecord
from ..services.export_service import ExportService
from ..services.email_extractor import _is_valid_email
from ..utils.db_worker import run_in_thread
from ..core.events import EventBus, event_bus
from .event_bridge import event_bridge
from .theme import Theme
from .icons import _render_tinted_icon


class PdfDetectWorker(QThread):
    detection_done = Signal(int, int, bool, str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            import pypdf
        except ImportError:
            self.detection_done.emit(0, -1, False, "Install pypdf:  pip install pypdf")
            return

        try:
            reader = pypdf.PdfReader(self.path)
            if reader.is_encrypted:
                self.detection_done.emit(0, -1, False, "PDF is password-protected. Please unlock it first.")
                return
            
            num_pages = len(reader.pages)
            detected_idx = 1 if num_pages > 1 else 0
            was_detected = False

            # Try to detect Anschreiben
            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    if any(kw in text for kw in ["Anschreiben", "Motivation", "Sehr geehrte", "Mit freundlichen Grüßen"]):
                        detected_idx = i
                        was_detected = True
                        break
                except Exception:
                    pass

            self.detection_done.emit(num_pages, detected_idx, was_detected, "")
        except Exception as e:
            self.detection_done.emit(0, -1, False, str(e))


GERMAN_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

PLACEHOLDER_REFERENCE = [
    ("{{ANREDE}}",  "Sehr geehrte Frau Müller, / Sehr geehrter Herr …"),
    ("{{FIRMA}}",   "Unternehmensname"),
    ("{{ORT}}",     "Stadt"),
    ("{{PLZ}}",     "Postleitzahl"),
    ("{{BERUF}}",   "Ausbildungsberuf / Stelle"),
    ("{{DATUM}}",   "04. Juni 2026"),
    ("{{SENDER_NAME}}",    "Ihr Name (aus Einstellungen)"),
    ("{{SENDER_ADDRESS}}", "Ihre Straße + Hausnummer"),
    ("{{SENDER_CITY}}",    "Ihre PLZ + Stadt"),
    ("{{SENDER_PHONE}}",   "Ihre Telefonnummer"),
    ("{{SENDER_EMAIL}}",   "Ihre E-Mail-Adresse"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LetterState:
    generated_at: str = ""
    edited_at: str = ""
    sent_at: str = ""
    letter_text: str = ""
    previous_text: str = ""          # one-level undo (last saved version)
    last_saved_ts: str = ""          # human-readable "saved HH:MM"
    is_discarded: int = 0            # hidden from edit page but kept in db


# ─────────────────────────────────────────────────────────────────────────────
# Lead list row widget
# ─────────────────────────────────────────────────────────────────────────────

class ElidedLabel(QLabel):
    """A QLabel that automatically elides text when it exceeds the width of the label."""
    def __init__(self, text="", parent=None):
        super().__init__("", parent)
        self._full_text = text
        self.setText(text)

    def setText(self, text):
        self._full_text = text
        self.update_elided()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_elided()

    def update_elided(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideRight, max(0, self.width() - 4))
        if elided != super().text():
            super().setText(elided)


class LeadRowWidget(QFrame):
    """Compact lead browser row with status badge."""

    def __init__(self, record: LeadRecord, state: LetterState | None = None, is_last: bool = False):
        super().__init__()
        self.record_id = record.id
        self._is_last = is_last
        self.setObjectName("leadRow")
        self.setProperty("selected", False)
        self.setFixedHeight(70)
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.LeftToRight)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 4, 4)
        root.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)

        company = ElidedLabel(record.company_name or "Unknown company")
        company.setStyleSheet("""
            color: #FFFFFF;
            font-family: 'PT Root UI', sans-serif;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
            padding: 0px;
        """)
        company.setToolTip(record.company_name or "Unknown company")
        company.installEventFilter(GlassToolTipFilter(company))
        top.addWidget(company, 1)

        # Show GEN badge only when generated (not sent)
        if state and state.generated_at and not state.sent_at:
            badge = QLabel(tr("GEN", get_language(config_manager.settings.app_language)))
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedHeight(18)
            badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            badge.setStyleSheet("""
                color: #a0a0a5;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-family: 'Menlo', monospace;
                font-size: 9px;
                font-weight: 600;
                padding: 2px 6px;
            """)
            top.addWidget(badge, 0, Qt.AlignVCenter)

        root.addLayout(top)

        job    = record.job_title or record.category or "—"
        city   = record.city or ""
        sub_text = f"{job} · {city}" if city else job
        meta   = ElidedLabel(sub_text)
        meta.setStyleSheet("""
            color: #6e6e73;
            font-family: 'PT Root UI', sans-serif;
            font-size: 11px;
            font-weight: 400;
            background: transparent;
            border: none;
            padding: 0px;
        """)
        root.addWidget(meta)

        self._apply_style()

    def set_selected(self, selected: bool):
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self._apply_style()

    def _apply_style(self):
        if self.property("selected"):
            self.setStyleSheet("""
                QFrame#leadRow {
                    background: rgba(10, 132, 255, 0.15);
                    border: none;
                    border-radius: 6px;
                    margin: 0px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#leadRow {
                    background: rgba(255, 255, 255, 0.03);
                    border: none;
                    border-radius: 8px;
                    margin: 1px 0px;
                }
                QFrame#leadRow:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)


# ─────────────────────────────────────────────────────────────────────────────
# Find & Replace toolbar
# ─────────────────────────────────────────────────────────────────────────────

class FindReplaceBar(QFrame):
    """Compact inline find/replace toolbar."""

    def __init__(self, editor: QTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setObjectName("findBar")
        self.setFixedHeight(44)
        self.setStyleSheet("""
            QFrame#findBar {
                background: #1a1a1a;
                border: 1px solid #2a2a2a;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        input_ss = (
            "QLineEdit { background: #111111; border: 1px solid #2a2a2a; "
            "border-radius: 4px; color: #cccccc; padding: 0 8px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #4CAF50; }"
        )

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find…")
        self._find_input.setFixedHeight(28)
        self._find_input.setStyleSheet(input_ss)
        self._find_input.returnPressed.connect(self._find_next)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace…")
        self._replace_input.setFixedHeight(28)
        self._replace_input.setStyleSheet(input_ss)

        self._case_cb = QCheckBox(tr("Aa", get_language(config_manager.settings.app_language)))
        self._case_cb.setStyleSheet(
            "QCheckBox { color: #AEAEB2; font-size: 11px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
        )

        btn_ss = (
            "QPushButton { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 4px; "
            "color: #999999; font-size: 11px; padding: 3px 10px; }"
            "QPushButton:hover { background: #222222; border-color: #444444; color: #eeeeee; }"
            "QPushButton:pressed { background: #4CAF50; color: #ffffff; }"
        )

        btn_next    = self._small_btn("Next",       btn_ss, self._find_next)
        btn_prev    = self._small_btn("Prev",       btn_ss, self._find_prev)
        btn_replace = self._small_btn("Replace",    btn_ss, self._replace_one)
        btn_all     = self._small_btn("Replace All",btn_ss, self._replace_all)
        btn_close   = self._small_btn("✕",          btn_ss, self.hide)

        self._match_label = QLabel("")
        self._match_label.setStyleSheet(
            "color: #636366; font-size: 10px; background: transparent;"
        )

        layout.addWidget(QLabel("🔍", styleSheet="color:#8E8E93; background:transparent;"))
        layout.addWidget(self._find_input, 2)
        layout.addWidget(self._replace_input, 2)
        layout.addWidget(self._case_cb)
        layout.addWidget(btn_next)
        layout.addWidget(btn_prev)
        layout.addWidget(btn_replace)
        layout.addWidget(btn_all)
        layout.addWidget(self._match_label, 1)
        layout.addWidget(btn_close)

    def _small_btn(self, text, ss, slot):
        b = PushButton(text)
        b.setFixedHeight(26)
        b.setStyleSheet(ss)
        b.clicked.connect(slot)
        return b

    def show_and_focus(self):
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()

    # ── find/replace logic ──────────────────────────────────────────────────

    def _flags(self):
        f = QTextDocument.FindFlags() if False else re.IGNORECASE
        return 0 if self._case_cb.isChecked() else re.IGNORECASE

    def _find_next(self, backward=False):
        needle = self._find_input.text()
        if not needle:
            return
        flags = QTextEdit.ExtraSelection
        doc = self._editor.document()
        cursor = self._editor.textCursor()
        find_flags = (
            self._editor.document().defaultTextOption().flags()
        )
        # use Qt built-in find
        from PySide6.QtGui import QTextDocument
        qt_flags = QTextDocument.FindFlag(0)
        if self._case_cb.isChecked():
            qt_flags |= QTextDocument.FindCaseSensitively
        if backward:
            qt_flags |= QTextDocument.FindBackward

        found = self._editor.find(needle, qt_flags)
        if not found:
            # wrap around
            cursor = self._editor.textCursor()
            cursor.movePosition(
                QTextCursor.End if backward else QTextCursor.Start
            )
            self._editor.setTextCursor(cursor)
            found = self._editor.find(needle, qt_flags)

        # count matches
        count = len(re.findall(
            re.escape(needle),
            self._editor.toPlainText(),
            0 if self._case_cb.isChecked() else re.IGNORECASE,
        ))
        self._match_label.setText(f"{count} match{'es' if count != 1 else ''}")

    def _find_prev(self):
        self._find_next(backward=True)

    def _replace_one(self):
        needle      = self._find_input.text()
        replacement = self._replace_input.text()
        if not needle:
            return
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == needle:
            cursor.insertText(replacement)
        self._find_next()

    def _replace_all(self):
        needle      = self._find_input.text()
        replacement = self._replace_input.text()
        if not needle:
            return
        text  = self._editor.toPlainText()
        flags = 0 if self._case_cb.isChecked() else re.IGNORECASE
        new_text, n = re.subn(re.escape(needle), replacement, text, flags=flags)
        if n:
            self._editor.setPlainText(new_text)
            self._match_label.setText(f"Replaced {n}×")


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder highlighter
# ─────────────────────────────────────────────────────────────────────────────

def _highlight_placeholders(editor: QTextEdit):
    """
    Highlight any remaining {{...}} in red so the user knows they are un-filled.
    """
    fmt = QTextCharFormat()
    fmt.setBackground(QColor("#5C1A1A"))
    fmt.setForeground(QColor("#FF6B6B"))

    extras: list[QTextEdit.ExtraSelection] = []
    text  = editor.toPlainText()
    for m in re.finditer(r"\{\{[A-Z_]+\}\}", text):
        sel           = QTextEdit.ExtraSelection()
        sel.format    = fmt
        cursor        = editor.textCursor()
        cursor.setPosition(m.start())
        cursor.setPosition(m.end(), QTextCursor.KeepAnchor)
        sel.cursor    = cursor
        extras.append(sel)

    editor.setExtraSelections(extras)
    return len(extras)


# ─────────────────────────────────────────────────────────────────────────────
# PDF Drop Zone Widget
# ─────────────────────────────────────────────────────────────────────────────

class PDFDropZone(QFrame):
    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("pdfDropZone")
        
        self.setStyleSheet("""
            QFrame#pdfDropZone {
                background: rgba(255,255,255,0.035);
                border: 0.5px dashed rgba(255,255,255,0.18);
                border-radius: 9px;
            }
            QFrame#pdfDropZone:hover {
                border-color: #0A84FF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignCenter)
        self.label = QLabel(tr("Drop Bewerbung PDF here\nor click to browse", get_language(config_manager.settings.app_language)))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            "color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; "
            "font-size: 11px; font-weight: 400; background: transparent; border: none;"
        )
        layout.addWidget(self.label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".pdf"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.file_dropped.emit(path)
            event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Main page
# ─────────────────────────────────────────────────────────────────────────────

class MappeButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        
        self.normal_icon = _render_tinted_icon(icon_name, 14, "#888888")
        self.hover_icon = _render_tinted_icon(icon_name, 14, "#cccccc")
        self.disabled_icon = _render_tinted_icon(icon_name, 14, "#333333")
        
        self.setIcon(self.normal_icon)
        self.setIconSize(QSize(14, 14))
        
        self.setStyleSheet("""
            QPushButton {
                background: #1a1a1a;
                border: 1px solid #2a2a2a;
                border-radius: 4px;
            }
            QPushButton:hover {
                border-color: #444444;
                background: #1f1f1f;
            }
            QPushButton:pressed {
                background: #252525;
            }
            QPushButton:disabled {
                background: #111111;
                border-color: #1a1a1a;
            }
        """)

    def enterEvent(self, event):
        if self.isEnabled():
            self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self.setIcon(self.normal_icon)
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange:
            if not self.isEnabled():
                self.setIcon(self.disabled_icon)
            else:
                self.setIcon(self.normal_icon)
        super().changeEvent(event)


from PySide6.QtWidgets import QSplitterHandle, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor

class AppleConfirmDialog(QDialog):
    def __init__(self, title: str, text: str, confirm_text: str = "Delete", confirm_color: str = "#FF453A", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 160)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bg = QWidget()
        bg.setStyleSheet("QWidget { background: rgba(40, 40, 40, 0.95); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; }")
        bg_layout = QVBoxLayout(bg)
        bg_layout.setContentsMargins(20, 20, 20, 20)
        bg_layout.setSpacing(8)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 16px; font-weight: 600; background: transparent; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(title_lbl)

        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setAlignment(Qt.AlignCenter)
        text_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 13px; font-weight: 400; background: transparent; border: none;")
        bg_layout.addWidget(text_lbl, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(10)

        btn_cancel = QPushButton(tr("Cancel", get_language(config_manager.settings.app_language)))
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet("QPushButton { background: rgba(255, 255, 255, 0.1); color: white; border: none; border-radius: 6px; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 13px; font-weight: 500; } QPushButton:hover { background: rgba(255, 255, 255, 0.15); }")
        btn_cancel.clicked.connect(self.reject)
        
        btn_delete = QPushButton(confirm_text)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setFixedHeight(32)
        btn_delete.setStyleSheet(f"QPushButton {{ background: {confirm_color}; color: white; border: none; border-radius: 6px; font-family: 'SF Pro Text', 'PT Root UI', sans-serif; font-size: 13px; font-weight: 600; }} QPushButton:hover {{ background: {confirm_color}CC; }}")
        btn_delete.clicked.connect(self.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_delete)
        
        bg_layout.addLayout(btn_layout)
        layout.addWidget(bg)

class CustomSplitterHandle(QSplitterHandle):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))


def _human_filesize(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


class ZeugnisCard(QFrame):
    """Pro Apple-style card representing a single certificate PDF."""

    move_up_requested = Signal(int)
    move_down_requested = Signal(int)
    remove_requested = Signal(int)

    def __init__(self, path_str: str, index: int, total_count: int, parent=None):
        super().__init__(parent)
        self.path_str = path_str
        self.index = index
        self.setObjectName("ZeugnisCard")
        self.setFixedHeight(54)

        self.setStyleSheet("""
            QFrame#ZeugnisCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 10px;
            }
            QFrame#ZeugnisCard:hover {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.13);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(10)

        # 1. Order Index Badge
        self.idx_badge = QLabel(f"{index + 1}")
        self.idx_badge.setFixedSize(22, 22)
        self.idx_badge.setAlignment(Qt.AlignCenter)
        self.idx_badge.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.08);
                color: #8E8E93;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 700;
                border-radius: 6px;
                border: none;
            }
        """)
        layout.addWidget(self.idx_badge)

        # 2. PDF Icon Chip (Apple Red/Coral accent)
        icon_chip = QFrame()
        icon_chip.setFixedSize(32, 32)
        icon_chip.setStyleSheet("""
            QFrame {
                background: rgba(255, 69, 58, 0.12);
                border: 1px solid rgba(255, 69, 58, 0.22);
                border-radius: 7px;
            }
        """)
        chip_layout = QVBoxLayout(icon_chip)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setAlignment(Qt.AlignCenter)

        pdf_icon = IconWidget(FluentIcon.DOCUMENT)
        pdf_icon.setFixedSize(16, 16)
        pdf_icon.setStyleSheet("color: #FF453A; background: transparent; border: none;")
        chip_layout.addWidget(pdf_icon, 0, Qt.AlignCenter)
        layout.addWidget(icon_chip)

        # 3. File Info (Title + Subtitle)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(2, 0, 0, 0)

        p = Path(path_str)
        filename = p.name if path_str else "Untitled PDF"
        file_exists = p.exists() if path_str else False

        title_lbl = QLabel(filename)
        title_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        title_lbl.setToolTip(path_str)
        info_layout.addWidget(title_lbl)

        # Size and status subtitle
        size_str = ""
        if file_exists:
            try:
                size_str = _human_filesize(p.stat().st_size)
            except Exception:
                size_str = "PDF Document"
        else:
            size_str = "File not found"

        status_color = "#8E8E93" if file_exists else "#FF453A"
        sub_lbl = QLabel(f"PDF • {size_str}")
        sub_lbl.setStyleSheet(f"""
            color: {status_color};
            font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
            font-size: 11px;
            font-weight: 400;
            background: transparent;
            border: none;
        """)
        info_layout.addWidget(sub_lbl)
        layout.addLayout(info_layout, 1)

        # 4. Action Buttons (Up, Down, Remove)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px;
                color: #AEAEB2;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border-color: rgba(255, 255, 255, 0.18);
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background: transparent;
                border-color: transparent;
                color: rgba(255, 255, 255, 0.15);
            }
        """

        self.up_btn = QPushButton("↑")
        self.up_btn.setFixedSize(26, 26)
        self.up_btn.setToolTip("Move Certificate Up")
        self.up_btn.setCursor(Qt.PointingHandCursor)
        self.up_btn.setStyleSheet(btn_style)
        self.up_btn.setEnabled(index > 0)
        self.up_btn.clicked.connect(lambda: self.move_up_requested.emit(self.index))
        btn_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("↓")
        self.down_btn.setFixedSize(26, 26)
        self.down_btn.setToolTip("Move Certificate Down")
        self.down_btn.setCursor(Qt.PointingHandCursor)
        self.down_btn.setStyleSheet(btn_style)
        self.down_btn.setEnabled(index < total_count - 1)
        self.down_btn.clicked.connect(lambda: self.move_down_requested.emit(self.index))
        btn_layout.addWidget(self.down_btn)

        self.rm_btn = QPushButton("✕")
        self.rm_btn.setFixedSize(26, 26)
        self.rm_btn.setToolTip("Remove Certificate")
        self.rm_btn.setCursor(Qt.PointingHandCursor)
        self.rm_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px;
                color: #8E8E93;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 69, 58, 0.15);
                border-color: rgba(255, 69, 58, 0.3);
                color: #FF453A;
            }
        """)
        self.rm_btn.clicked.connect(lambda: self.remove_requested.emit(self.index))
        btn_layout.addWidget(self.rm_btn)

        layout.addLayout(btn_layout)


class ZeugisseManagerDialog(QDialog):
    """
    Pro Apple-style modal dialog to manage, reorder, add and remove Zeugnisse certificate PDFs.
    Designed to match macOS Pro Human Interface Guidelines and Zugzwang's dark aesthetic.
    """

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Zeugnisse")
        self._paths: list[str] = [p for p in paths if p]
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(540, 440)
        self.resize(560, 460)
        self.setAcceptDrops(True)

        if parent:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        # Root layout with padding for window drop shadow
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(0)

        # Main macOS glass/surface container
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        self.container.setStyleSheet("""
            QFrame#MainContainer {
                background: #1E1E22;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 10)
        self.container.setGraphicsEffect(shadow)

        root_layout.addWidget(self.container)

        # Inner container layout
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(22, 20, 22, 18)
        inner_layout.setSpacing(14)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. PRO APPLE HEADER
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        # Header Icon Chip (Red/Coral Certificate Badge)
        icon_badge = QFrame()
        icon_badge.setFixedSize(42, 42)
        icon_badge.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255, 69, 58, 0.18), stop:1 rgba(255, 69, 58, 0.08));
                border: 1px solid rgba(255, 69, 58, 0.28);
                border-radius: 11px;
            }
        """)
        ib_layout = QVBoxLayout(icon_badge)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        ib_layout.setAlignment(Qt.AlignCenter)

        top_icon = IconWidget(FluentIcon.DOCUMENT)
        top_icon.setFixedSize(20, 20)
        top_icon.setStyleSheet("color: #FF453A; background: transparent; border: none;")
        ib_layout.addWidget(top_icon, 0, Qt.AlignCenter)
        header_layout.addWidget(icon_badge, 0, Qt.AlignVCenter)

        # Header Title & Subtitle
        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title_block.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("Manage Zeugnisse")
        title_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-family: 'SF Pro Display', 'PT Root UI', -apple-system, sans-serif;
            font-size: 17px;
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        title_block.addWidget(title_lbl)

        sub_lbl = QLabel("Attach and reorder certificate PDFs for your application.")
        sub_lbl.setStyleSheet("""
            color: #8E8E93;
            font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
            font-size: 12px;
            font-weight: 400;
            background: transparent;
            border: none;
        """)
        sub_lbl.setWordWrap(True)
        title_block.addWidget(sub_lbl)
        header_layout.addLayout(title_block, 1)

        # Header Close Button (✕)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: #8E8E93;
                font-family: 'SF Pro Text', sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn, 0, Qt.AlignTop)

        inner_layout.addLayout(header_layout)

        # Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255, 255, 255, 0.08); border: none;")
        inner_layout.addWidget(divider)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. CERTIFICATES LIST AREA / EMPTY STATE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.16);
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.28);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 4, 4, 4)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.cards_container)
        inner_layout.addWidget(self.scroll_area, 1)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. PRO APPLE FOOTER TOOLBAR
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        footer_divider = QFrame()
        footer_divider.setFixedHeight(1)
        footer_divider.setStyleSheet("background: rgba(255, 255, 255, 0.08); border: none;")
        inner_layout.addWidget(footer_divider)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(10)

        # Add Files Button (+ Add Certificates)
        self.add_btn = QPushButton("+ Add Certificates")
        self.add_btn.setFixedHeight(34)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                color: #FFFFFF;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.13);
                border-color: rgba(255, 255, 255, 0.22);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.06);
            }
        """)
        self.add_btn.clicked.connect(self._add_files)
        footer_layout.addWidget(self.add_btn)

        # Counter text
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("""
            color: #8E8E93;
            font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
            font-size: 11px;
            font-weight: 500;
            background: transparent;
            border: none;
            padding-left: 4px;
        """)
        footer_layout.addWidget(self.count_lbl)

        # Clear All link button
        self.clear_all_btn = QPushButton("Clear all")
        self.clear_all_btn.setCursor(Qt.PointingHandCursor)
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #8E8E93;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 11px;
                text-decoration: underline;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: #FF453A;
            }
        """)
        self.clear_all_btn.clicked.connect(self._clear_all)
        footer_layout.addWidget(self.clear_all_btn)

        footer_layout.addStretch(1)

        # Cancel Button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #AEAEB2;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #FFFFFF;
                border-color: rgba(255, 255, 255, 0.15);
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        # Done / Save Button (Apple Pro Signature Blue)
        done_btn = QPushButton("Done")
        done_btn.setFixedHeight(34)
        done_btn.setDefault(True)
        done_btn.setCursor(Qt.PointingHandCursor)
        done_btn.setStyleSheet("""
            QPushButton {
                background: #0A84FF;
                border: none;
                border-radius: 8px;
                color: #FFFFFF;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 700;
                padding: 0 22px;
            }
            QPushButton:hover {
                background: #409CFF;
            }
            QPushButton:pressed {
                background: #0071E3;
            }
        """)
        done_btn.clicked.connect(self.accept)
        footer_layout.addWidget(done_btn)

        inner_layout.addLayout(footer_layout)

        # Populate UI
        self._refresh_list()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # WINDOW DRAGGING SUPPORT (macOS Sheet Behavior)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= 70:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DRAG & DROP PDF FILES FROM FINDER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        added = False
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf") and file_path not in self._paths:
                self._paths.append(file_path)
                added = True
        if added:
            self._refresh_list()
            event.acceptProposedAction()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LIST MANAGEMENT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _refresh_list(self):
        # Clear existing items
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        count = len(self._paths)
        if count == 0:
            # Empty state
            empty_frame = QFrame()
            empty_frame.setObjectName("EmptyZone")
            empty_frame.setCursor(Qt.PointingHandCursor)
            empty_frame.setStyleSheet("""
                QFrame#EmptyZone {
                    background: rgba(255, 255, 255, 0.02);
                    border: 1.5px dashed rgba(255, 255, 255, 0.12);
                    border-radius: 12px;
                }
                QFrame#EmptyZone:hover {
                    background: rgba(255, 255, 255, 0.04);
                    border-color: rgba(10, 132, 255, 0.35);
                }
            """)
            empty_layout = QVBoxLayout(empty_frame)
            empty_layout.setContentsMargins(20, 36, 20, 36)
            empty_layout.setSpacing(8)
            empty_layout.setAlignment(Qt.AlignCenter)

            e_icon = IconWidget(FluentIcon.FOLDER)
            e_icon.setFixedSize(36, 36)
            e_icon.setStyleSheet("color: #636366; background: transparent; border: none;")
            empty_layout.addWidget(e_icon, 0, Qt.AlignCenter)

            e_title = QLabel("No Certificates Attached")
            e_title.setStyleSheet("""
                color: #FFFFFF;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
                border: none;
            """)
            e_title.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(e_title)

            e_sub = QLabel("Drag and drop PDF files here, or click to browse.")
            e_sub.setStyleSheet("""
                color: #8E8E93;
                font-family: 'SF Pro Text', 'PT Root UI', -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 400;
                background: transparent;
                border: none;
            """)
            e_sub.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(e_sub)

            empty_frame.mousePressEvent = lambda e: self._add_files() if e.button() == Qt.LeftButton else None

            self.cards_layout.addWidget(empty_frame)
            self.count_lbl.setText("No certificates")
            self.clear_all_btn.hide()
        else:
            total_size = 0
            for i, p_str in enumerate(self._paths):
                card = ZeugnisCard(p_str, i, count, self.cards_container)
                card.move_up_requested.connect(self._move_up)
                card.move_down_requested.connect(self._move_down)
                card.remove_requested.connect(self._remove_at)
                self.cards_layout.addWidget(card)

                try:
                    p = Path(p_str)
                    if p.exists():
                        total_size += p.stat().st_size
                except Exception:
                    pass

            plural = "certificates" if count != 1 else "certificate"
            size_part = f" • {_human_filesize(total_size)}" if total_size > 0 else ""
            self.count_lbl.setText(f"{count} {plural}{size_part}")
            self.clear_all_btn.show()

    def _move_up(self, index: int):
        if index > 0:
            self._paths[index], self._paths[index - 1] = self._paths[index - 1], self._paths[index]
            self._refresh_list()

    def _move_down(self, index: int):
        if index < len(self._paths) - 1:
            self._paths[index], self._paths[index + 1] = self._paths[index + 1], self._paths[index]
            self._refresh_list()

    def _remove_at(self, index: int):
        if 0 <= index < len(self._paths):
            self._paths.pop(index)
            self._refresh_list()

    def _clear_all(self):
        self._paths.clear()
        self._refresh_list()

    def _add_files(self):
        start = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Certificate PDF(s)",
            start,
            "PDF Files (*.pdf)"
        )
        if paths:
            for p in paths:
                if p not in self._paths:
                    self._paths.append(p)
            self._refresh_list()

    def get_paths(self) -> list[str]:
        return list(self._paths)


# ─────────────────────────────────────────────────────────────────────────────
# Document Order List Widget (Send-page drag-and-drop style)
# ─────────────────────────────────────────────────────────────────────────────

DOC_CARD_NORMAL_STYLE = """
    QFrame#docRow {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 7px;
    }
    QFrame#docRow:hover {
        background: #2a2a2c;
        border-color: rgba(255, 255, 255, 0.12);
    }
"""

DOC_CARD_DROP_STYLE = """
    QFrame#docRow {
        background: #2a2a2c;
        border: 1px solid #0A84FF;
        border-radius: 7px;
    }
"""

class DocCardRow(QFrame):
    def __init__(self, key: str, idx: int, meta: dict, container=None, on_action=None, on_clear=None):
        super().__init__()
        self.setObjectName("docRow")
        self.setFixedHeight(34)
        self.setStyleSheet(DOC_CARD_NORMAL_STYLE)
        self.key = key
        self.container = container
        self._dragging = False

        rl = QHBoxLayout(self)
        rl.setContentsMargins(8, 2, 6, 2)
        rl.setSpacing(7)

        # Position indicator number (1., 2., 3., 4.)
        self.pos_lbl = QLabel(f"{idx + 1}.")
        self.pos_lbl.setFixedWidth(14)
        self.pos_lbl.setStyleSheet("color: #636366; font-family: 'PT Root UI', sans-serif; font-size: 10px; font-weight: 700; background: transparent; border: none;")
        rl.addWidget(self.pos_lbl)

        # Main clickable area with icon, title, and clean status
        main_btn = QPushButton()
        main_btn.setCursor(Qt.PointingHandCursor)
        main_btn.setStyleSheet("QPushButton { background: transparent; border: none; text-align: left; padding: 0; }")
        m_layout = QHBoxLayout(main_btn)
        m_layout.setContentsMargins(0, 0, 0, 0)
        m_layout.setSpacing(6)

        icon_w = IconWidget(meta.get("icon", FluentIcon.DOCUMENT))
        icon_w.setFixedSize(14, 14)
        icon_w.setStyleSheet("background: transparent; color: #a0a0a5; border: none;")
        m_layout.addWidget(icon_w)

        title_lbl = QLabel(meta["title"])
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'PT Root UI', sans-serif; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        m_layout.addWidget(title_lbl)

        sub_text = meta.get("sub", "")
        if len(sub_text) > 22:
            sub_text = sub_text[:20] + "…"
        sub_lbl = QLabel(f"• {sub_text}")
        sub_lbl.setStyleSheet(f"color: {meta['color']}; font-family: 'PT Root UI', sans-serif; font-size: 10px; font-weight: 500; background: transparent; border: none;")
        m_layout.addWidget(sub_lbl)
        m_layout.addStretch()

        if on_action:
            main_btn.clicked.connect(on_action)
        rl.addWidget(main_btn, 1)

        # Clear button if file is loaded
        if meta.get("has_file") and on_clear:
            rm_btn = QPushButton("✕")
            rm_btn.setFixedSize(18, 18)
            rm_btn.setCursor(Qt.PointingHandCursor)
            rm_btn.setToolTip(f"Remove {meta['title']}")
            rm_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none; border-radius: 4px;
                    color: #8E8E93; font-size: 10px; font-weight: bold; padding: 0;
                }
                QPushButton:hover {
                    color: #FF453A; background: rgba(255, 69, 58, 0.15);
                }
            """)
            rm_btn.clicked.connect(on_clear)
            rl.addWidget(rm_btn)

        # Three bands drag handle button (≡) — drag up or down to reorder
        self.handle = QPushButton()
        self.handle.setFixedSize(22, 22)
        self.handle.setIcon(FluentIcon.MENU.icon(color="#8E8E93"))
        self.handle.setIconSize(QSize(13, 13))
        self.handle.setCursor(Qt.SizeVerCursor)
        self.handle.setToolTip(f"Drag up or down to reorder {meta['title']}")
        self.handle.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 4px; padding: 0;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
            }
        """)

        self.handle.mousePressEvent = self._handle_press
        self.handle.mouseMoveEvent = self._handle_move
        self.handle.mouseReleaseEvent = self._handle_release
        rl.addWidget(self.handle)

    def set_position_number(self, num: int):
        self.pos_lbl.setText(f"{num}.")

    def _handle_press(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.setStyleSheet(DOC_CARD_DROP_STYLE)
        QPushButton.mousePressEvent(self.handle, event)

    def _handle_move(self, event):
        if self._dragging:
            global_y = event.globalPosition().toPoint().y()
            if self.container:
                self.container._on_card_dragged(self, global_y)
        QPushButton.mouseMoveEvent(self.handle, event)

    def _handle_release(self, event):
        if self._dragging:
            self._dragging = False
            self.setStyleSheet(DOC_CARD_NORMAL_STYLE)
            if self.container:
                self.container._on_card_drag_finished()
        QPushButton.mouseReleaseEvent(self.handle, event)


class EditPage(QWidget):
    """Three-panel workspace for auto-generated motivation letters."""
    
    send_emails_to_sender = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("editPage")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._records:               list[LeadRecord]      = []
        self._states:                dict[str, LetterState] = {}
        self._selected_record:       LeadRecord | None      = None
        self._selected_lead_id:      str | None             = None
        self._selected_row_widget:   LeadRowWidget | None   = None
        self._lead_population_token: int                    = 0
        self._pending_lead_records:  list[LeadRecord]       = []
        self._pending_lead_index:    int                    = 0
        self._rendered_text:         str                    = ""
        self._loading_text:          bool                   = False
        self._preview_mode:          bool                   = False
        self._is_template_mode:      bool                   = False
        self._bewerbung_pdf_path:         Path | None = None
        self._bewerbung_anschreiben_page: int         = 1   # 0-based, default page 2

        self._cached_sender_settings: dict = {}
        self._fetch_sender_settings()
        event_bus.subscribe(EventBus.SETTINGS_CHANGED, self._fetch_sender_settings)
        event_bridge.job_result.connect(self._on_live_result_added)
        event_bridge.db_updated.connect(self._on_db_updated)

        self._signature_image_path: str = ""
        run_in_thread(
            self._do_fetch_signature_path,
            on_result=self._on_signature_path_loaded
        )

        run_in_thread(
            self._do_fetch_persisted_pdf_path,
            on_result=self._on_persisted_pdf_path_loaded
        )

        from ..core.config import get_app_data_dir
        import shutil

        self._template_path = get_app_data_dir() / "templates" / "anschreiben_base.txt"
        if not self._template_path.exists():
            default_path = Path(__file__).resolve().parents[2] / "templates" / "anschreiben_base.txt"
            if default_path.exists():
                self._template_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(default_path, self._template_path)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Could not copy default template: {e}")
        self._template_text = self._load_template()

        # auto-save debounce timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._autosave)

        # word-count refresh timer
        self._wc_timer = QTimer(self)
        self._wc_timer.setSingleShot(True)
        self._wc_timer.setInterval(300)
        self._wc_timer.timeout.connect(self._update_word_count)

        self._build_ui()
        self._setup_shortcuts()
        QTimer.singleShot(0, self.refresh)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("QWidget#editPage { background: transparent; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 24, 8, 24)
        root.setSpacing(0)


        # Child 2: BodySplitter
        class StyledSplitter(QSplitter):
            def createHandle(self):
                return CustomSplitterHandle(self.orientation(), self)

        workspace = StyledSplitter(Qt.Horizontal)
        workspace.setChildrenCollapsible(False)
        workspace.setHandleWidth(12)

        left_panel = self._build_left_panel()
        left_panel.setFixedWidth(280)
        self._left_panel_widget = left_panel
        
        center_panel = self._build_center_panel()
        
        right_panel = self._build_right_panel()
        right_panel.setFixedWidth(280)

        workspace.addWidget(left_panel)
        workspace.addWidget(center_panel)
        workspace.addWidget(right_panel)

        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setStretchFactor(2, 0)

        root.addWidget(workspace, 1)

        # Setup standard UI state
        self._set_actions_enabled(False)

    def _build_left_panel(self) -> QWidget:
        left = QFrame()
        left.setObjectName("EditLeftPanel")
        left.setStyleSheet("""
            QFrame#EditLeftPanel {
                background: #1C1C1E;
                border: 1px solid #2C2C2E;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(left)
        layout.setContentsMargins(0, 8, 0, 12)
        layout.setSpacing(0)

        # A. Header Row (Removed)

        # B. Search Bar
        search_w = QWidget()
        search_lyt = QHBoxLayout(search_w)
        search_lyt.setContentsMargins(10, 0, 10, 6)
        search_lyt.setSpacing(6)
        
        search_container = QWidget()
        search_container.setFixedHeight(32)
        search_container.setStyleSheet("background-color: #2C2C2E; border-radius: 7px;")
        sc_layout = QHBoxLayout(search_container)
        sc_layout.setContentsMargins(9, 0, 9, 0)
        sc_layout.setSpacing(6)
        
        s_icon = QLabel()
        s_icon.setPixmap(_render_tinted_icon("search.svg", 13, "#6E6E73").pixmap(13, 13))
        
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("edit.search.placeholder", get_language(config_manager.settings.app_language)))
        self._search.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #E5E5EA;
                font-family: system-ui, -apple-system, "SF Pro Text", sans-serif;
                font-size: 12px;
                font-weight: 400;
                padding: 0px;
                margin: 0px;
            }
        """)
        palette = self._search.palette()
        palette.setColor(QPalette.PlaceholderText, QColor("#48484A"))
        self._search.setPalette(palette)
        self._search.textChanged.connect(self._populate_leads)
        
        sc_layout.addWidget(s_icon, 0, Qt.AlignVCenter)
        sc_layout.addWidget(self._search, 1, Qt.AlignVCenter)
        search_lyt.addWidget(search_container, 1)

        btn_import = QPushButton()
        btn_import.setFixedSize(32, 32)
        btn_import.setIcon(FluentIcon.ADD.icon(color="#0A84FF"))
        btn_import.setIconSize(QSize(16, 16))
        btn_import.setToolTip("Import leads from Excel (.xlsx) or CSV spreadsheet")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet("""
            QPushButton {
                background: rgba(10, 132, 255, 0.15);
                border: none;
                border-radius: 7px;
                outline: none;
            }
            QPushButton:focus {
                border: none;
                outline: none;
            }
            QPushButton:hover {
                background: rgba(10, 132, 255, 0.25);
                border: none;
            }
            QPushButton:pressed {
                background: rgba(10, 132, 255, 0.35);
            }
        """)
        btn_import.clicked.connect(self._on_import_spreadsheet)
        search_lyt.addWidget(btn_import, 0)
        layout.addWidget(search_w)

        # C. Segmented Control
        seg_w = QWidget()
        seg_lyt = QVBoxLayout(seg_w)
        seg_lyt.setContentsMargins(10, 0, 10, 8)
        
        seg_track = QWidget()
        seg_track.setFixedHeight(30)
        seg_track.setStyleSheet("background-color: #2C2C2E; border-radius: 8px;")
        st_layout = QHBoxLayout(seg_track)
        st_layout.setContentsMargins(4, 4, 4, 4)
        st_layout.setSpacing(4)
        
        self._filter_btns = {}
        for label, key in [("All", "all"), ("Pending", "pending"), ("Sent", "sent")]:
            b = QPushButton(label.upper())
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            b.setFixedHeight(22)
            b.setCursor(Qt.PointingHandCursor)
            st_layout.addWidget(b)
            self._filter_btns[key] = b
            b.clicked.connect(lambda _, k=key: self._on_filter(k))
            
        self._update_segment_styles("all")
        seg_lyt.addWidget(seg_track)
        layout.addWidget(seg_w)

        # D. Lead List
        self._lead_list = QListWidget()
        self._lead_list.setLayoutDirection(Qt.LeftToRight)
        self._lead_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lead_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lead_list.setFrameShape(QFrame.NoFrame)
        self._lead_list.setStyleSheet("""
            QListWidget { background: transparent; outline: none; border: none; }
            QListWidget::item { background: transparent; border: none; outline: none; padding: 0px 12px 0px 2px; }
            QListWidget::item:selected { background: transparent; border: none; outline: none; color: inherit; }
        """)
        self._lead_list.itemClicked.connect(self._on_lead_clicked)

        self._lead_scrollbar = QScrollBar(Qt.Vertical)
        self._lead_scrollbar.setFixedWidth(8)
        self._lead_scrollbar.setStyleSheet("""
            QScrollBar:vertical { background: transparent; margin: 0px; }
            QScrollBar::handle:vertical { background: #3A3A3C; border-radius: 4px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; border: none; height: 0px; }
        """)
        
        self._lead_scrollbar.valueChanged.connect(self._lead_list.verticalScrollBar().setValue)
        self._lead_list.verticalScrollBar().valueChanged.connect(self._lead_scrollbar.setValue)
        
        def sync_range(min_val, max_val):
            self._lead_scrollbar.setRange(min_val, max_val)
            self._lead_scrollbar.setPageStep(self._lead_list.verticalScrollBar().pageStep())
            
        self._lead_list.verticalScrollBar().rangeChanged.connect(sync_range)

        list_container = QWidget()
        list_lyt = QHBoxLayout(list_container)
        list_lyt.setContentsMargins(0, 0, 0, 0)
        list_lyt.setSpacing(2)
        list_lyt.addWidget(self._lead_scrollbar)
        list_lyt.addWidget(self._lead_list)

        layout.addWidget(list_container, 1)



        return left

    def _update_segment_styles(self, active_key: str):
        for key, btn in self._filter_btns.items():
            if key == active_key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3A3A3C;
                        border-radius: 6px;
                        border: none;
                        font-family: 'PT Root UI', system-ui, sans-serif;
                        font-size: 10px;
                        color: #FFFFFF;
                        font-weight: 600;
                        padding: 2px 4px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        font-family: 'PT Root UI', system-ui, sans-serif;
                        font-size: 10px;
                        color: #a0a0a5;
                        font-weight: 500;
                        padding: 2px 4px;
                    }
                    QPushButton:hover {
                        background: rgba(255,255,255,0.05);
                        border-radius: 6px;
                        color: #FFFFFF;
                    }
                """)

    def _build_center_panel(self) -> QWidget:
        center = QFrame()
        center.setObjectName("EditCenterPanel")
        center.setStyleSheet("""
            QFrame#EditCenterPanel {
                background: #141416;
                border: 1px solid #2C2C2E;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 8, 0, 12)
        layout.setSpacing(0)

        # A. Letter Header
        self._center_header_stack = QStackedWidget()
        self._center_header_stack.setFixedHeight(48)
        self._center_header_stack.setStyleSheet("background-color: transparent; border: none;")

        header_normal = QWidget()
        h_layout = QHBoxLayout(header_normal)
        h_layout.setContentsMargins(32, 0, 32, 10)
        h_layout.setSpacing(0)

        # Left
        left_h = QHBoxLayout()
        left_h.setSpacing(12)
        self._center_company = QLabel()
        self._center_company.setStyleSheet("color: #FFFFFF; font-family: 'PT Root UI'; font-size: 13px; font-weight: 600; border: none; background: transparent;")
        left_h.addWidget(self._center_company)

        def _top_info_label(icon_name):
            w = QWidget()
            w.setStyleSheet("background: transparent;")
            wl = QHBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(4)
            ico = QLabel()
            ico.setFixedSize(13, 13)
            ico.setPixmap(_render_tinted_icon(icon_name, 13, "#8E8E93").pixmap(13, 13))
            ico.setStyleSheet("background: transparent;")
            lbl = QLabel()
            lbl.setStyleSheet("color: #8E8E93; font-family: 'PT Root UI'; font-size: 13px; font-weight: 400; border: none; background: transparent;")
            wl.addWidget(ico)
            wl.addWidget(lbl)
            return w, lbl

        hr_w, self._center_hr = _top_info_label("user.svg")
        job_w, self._center_job = _top_info_label("briefcase.svg")
        loc_w, self._center_city = _top_info_label("map-pin.svg")
        
        left_h.addWidget(hr_w)
        left_h.addWidget(job_w)
        left_h.addWidget(loc_w)
        h_layout.addLayout(left_h)

        h_layout.addStretch()

        # Right
        right_h = QHBoxLayout()
        right_h.setSpacing(8)
        
        def _header_icon_btn(fluent_icon, tooltip, is_danger=False):
            b = QPushButton()
            b.setFixedSize(32, 32)
            
            bg = "transparent"
            hover_bg = "rgba(255, 69, 58, 0.15)" if is_danger else "rgba(255, 255, 255, 0.08)"
            pressed_bg = "rgba(255, 69, 58, 0.25)" if is_danger else "rgba(255, 255, 255, 0.12)"
            color = "#FF453A" if is_danger else "#8E8E93"
            
            b.setIcon(fluent_icon.icon(color=color))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg};
                    border-radius: 6px;
                    border: none;
                }}
                QPushButton:hover {{ background: {hover_bg}; }}
                QPushButton:pressed {{ background: {pressed_bg}; }}
                QPushButton:disabled {{ background: transparent; }}
            """)
            return b

        self._btn_copy = _header_icon_btn(FluentIcon.COPY, "Copy letter")
        self._btn_polish = _header_icon_btn(FluentIcon.EDIT, "Polish letter")
        self._btn_regenerate = _header_icon_btn(FluentIcon.SYNC, "Regenerate letter")
        self._btn_undo_ver = _header_icon_btn(FluentIcon.HISTORY, "Revert to previous", is_danger=True)
        self._btn_undo_ver.setEnabled(False)

        self._btn_copy.clicked.connect(self._copy_letter)
        self._btn_polish.clicked.connect(self._polish_current_letter)
        self._btn_regenerate.clicked.connect(self._regenerate_current_letter)
        self._btn_undo_ver.clicked.connect(self._revert_to_previous)

        right_h.addWidget(self._btn_copy)
        right_h.addWidget(self._btn_polish)
        right_h.addWidget(self._btn_regenerate)
        right_h.addWidget(self._btn_undo_ver)
        h_layout.addLayout(right_h)
        self._center_header_stack.addWidget(header_normal)
        
        header_template = QWidget()
        ht_layout = QHBoxLayout(header_template)
        ht_layout.setContentsMargins(32, 0, 32, 10)
        ht_layout.setSpacing(12)
        template_title = QLabel(tr("Editing Global Template", get_language(config_manager.settings.app_language)))
        template_title.setStyleSheet("color: #FFFFFF; font-family: 'PT Root UI'; font-size: 13px; font-weight: 600; border: none; background: transparent;")
        ht_layout.addWidget(template_title)
        ht_layout.addStretch(1)

        cancel_tpl = QPushButton(tr("Cancel", get_language(config_manager.settings.app_language)))
        cancel_tpl.setCursor(Qt.PointingHandCursor)
        cancel_tpl.setStyleSheet("""
            QPushButton { 
                text-transform: none; 
                letter-spacing: 0px;
                border: none; 
                background: transparent; 
                color: #0A84FF; 
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 5px 8px; 
            } 
            QPushButton:hover { color: #409CFF; }
            QPushButton:pressed { color: #0071E3; }
        """)
        cancel_tpl.clicked.connect(self._cancel_template_mode)
        ht_layout.addWidget(cancel_tpl)

        save_tpl = QPushButton(tr("Save template", get_language(config_manager.settings.app_language)))
        save_tpl.setCursor(Qt.PointingHandCursor)
        save_tpl.setFixedHeight(28)
        save_tpl.setStyleSheet("""
            QPushButton { 
                text-transform: none; 
                letter-spacing: 0px;
                border: none; 
                border-radius: 6px; 
                background: #0A84FF; 
                color: white; 
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 0 14px; 
            } 
            QPushButton:hover { background: #409CFF; } 
            QPushButton:pressed { background: #0071E3; }
        """)
        save_tpl.clicked.connect(self._save_template_mode)
        ht_layout.addWidget(save_tpl)

        self._center_header_stack.addWidget(header_template)
        
        layout.addWidget(self._center_header_stack)

        # B. Letter Body
        self._editor = QTextEdit()
        self._editor.setFrameShape(QFrame.NoFrame)
        self._editor.setReadOnly(False)
        self._editor.setStyleSheet("""
            QTextEdit {
                background-color: #141416;
                border-radius: 11px;
                border: none;
                color: #C7C7CC;
                font-family: 'PT Root UI', system-ui, -apple-system, sans-serif;
                font-size: 13px;
                font-weight: 400;
                line-height: 1.7;
            }
            QScrollBar:vertical {
                background: #141416;
                border: none;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3A3A3C;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                border: none;
                height: 0px;
            }
        """)
        # Set text margins using the viewport so scrollbars stay at the widget edge
        self._editor.viewport().setContentsMargins(32, 20, 42, 32)
        
        self._editor.textChanged.connect(self._on_text_changed)
        
        # Find bar container
        self._find_bar = FindReplaceBar(self._editor, center)
        self._find_bar.hide()
        layout.addWidget(self._find_bar)

        layout.addWidget(self._editor, 1)

        return center

    def _create_sidebar_button(self, icon: FluentIcon, text: str, callback=None) -> QPushButton:
        # Add 3 spaces to pad the text away from the icon
        btn = QPushButton("   " + text.upper())
        btn.setIcon(icon.icon(color="#a0a0a5"))
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                color: #a0a0a5;
                font-family: 'PT Root UI', sans-serif;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
                text-align: left;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #2a2a2c;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                color: rgba(160, 160, 165, 0.4);
            }
        """)
        if callback:
            btn.clicked.connect(callback)
        return btn


    def _build_right_panel(self) -> QWidget:
        self._right_panel_stack = QStackedWidget()
        self._right_panel_stack.setStyleSheet("QStackedWidget { background: transparent; }")

        scroll = QScrollArea()
        scroll.setObjectName("EditRightPanel")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea#EditRightPanel { 
                background: #1C1C1E; 
                border: 1px solid #2C2C2E;
                border-radius: 12px;
            }
            QWidget#rightContainer { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 0px; height: 0px; }
            QScrollBar::handle:vertical { background: transparent; }
        """)

        container = QWidget()
        container.setObjectName("rightContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        def _create_card():
            card = QFrame()
            card.setObjectName("sidebarCard")
            card.setStyleSheet("QFrame#sidebarCard { background-color: #1a1a1c; border: 1px solid #2a2a2c; border-radius: 8px; }")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(0)
            return card, cl

        def _create_divider():
            d = QFrame()
            d.setFixedHeight(1)
            d.setStyleSheet("background-color: #3A3A3C; max-height: 1px; border: none;")
            return d

        def _section_label(text):
            lbl = QLabel(text)
            lbl.setFixedHeight(16)
            lbl.setStyleSheet("color: #8E8E93; font-family: 'PT Root UI'; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; background: transparent;")
            return lbl

        # CARD 4 - PROFILE & SIGNATURE
        card4, cl4 = _create_card()
        lbl4 = _section_label("PROFILE & SIGNATURE")
        cl4.addWidget(lbl4)
        cl4.addSpacing(6)
        self._btn_edit_profile = self._create_sidebar_button(FluentIcon.PEOPLE, tr("edit.sidebar.set_info", get_language(config_manager.settings.app_language)), self._edit_profile)
        self._btn_upload_sig = self._create_sidebar_button(FluentIcon.UPDATE, tr("edit.sidebar.upload_sig", get_language(config_manager.settings.app_language)), self._upload_signature)
        self._btn_clear_sig = self._create_sidebar_button(FluentIcon.DELETE, tr("edit.sidebar.clear_sig", get_language(config_manager.settings.app_language)), self._clear_signature)
        cl4.addWidget(self._btn_edit_profile)
        cl4.addSpacing(4)
        cl4.addWidget(self._btn_upload_sig)
        cl4.addSpacing(4)
        cl4.addWidget(self._btn_clear_sig)
        layout.addWidget(card4)

        # CARD 5 - TEMPLATE
        card5, cl5 = _create_card()
        lbl5 = _section_label(tr("edit.template.title", get_language(config_manager.settings.app_language)))
        cl5.addWidget(lbl5)
        cl5.addSpacing(4)
        self._template_status = QLabel(self._template_status_text())
        self._template_status.setStyleSheet("color: #6E6E73; font-size: 11px; font-weight: 400; background: transparent;")
        cl5.addWidget(self._template_status)
        cl5.addSpacing(4)
        self._btn_edit_template = self._create_sidebar_button(FluentIcon.EDIT, tr("edit.sidebar.edit_template", get_language(config_manager.settings.app_language)), self._edit_template)
        cl5.addWidget(self._btn_edit_template)
        layout.addWidget(card5)

        # CARD 6 - BEWERBUNG
        card6, cl6 = _create_card()

        # --- Header: section label + status pill ---
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        lbl6 = _section_label(tr("edit.bewerbung.title", get_language(config_manager.settings.app_language)))
        header_row.addWidget(lbl6)
        header_row.addStretch()
        self._bewerbung_status_label = QLabel("0/2 ready")
        self._bewerbung_status_label.setFixedHeight(22)
        self._bewerbung_status_label.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                color: #8E8E93;
                padding: 2px 8px;
                font-family: 'PT Root UI', sans-serif;
                font-size: 10px;
                font-weight: 500;
            }
        """)
        header_row.addWidget(self._bewerbung_status_label)
        cl6.addLayout(header_row)
        cl6.addSpacing(6)

        # --- Export mode segmented bar (no dropdown popups) ---
        cur_mode = getattr(config_manager.settings, "bewerbung_export_mode", "full") or "full"



        mode_bar = QFrame()
        mode_bar.setObjectName("modeBar")
        mode_bar.setStyleSheet("""
            QFrame#modeBar {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                padding: 2px;
            }
        """)
        mbl = QHBoxLayout(mode_bar)
        mbl.setContentsMargins(2, 2, 2, 2)
        mbl.setSpacing(2)

        self._mode_btn_full = QPushButton("Full Mappe")
        self._mode_btn_split = QPushButton("Letter+CV")
        self._mode_btn_sep = QPushButton("Separate")

        for b in (self._mode_btn_full, self._mode_btn_split, self._mode_btn_sep):
            b.setFixedHeight(24)
            b.setCursor(Qt.PointingHandCursor)
            mbl.addWidget(b)

        def _update_mode_styles(active_mode: str):
            _active_style = """
                QPushButton {
                    background: #0A84FF; border: none; border-radius: 5px;
                    color: #FFFFFF; font-family: 'PT Root UI', sans-serif; font-size: 11px; font-weight: 600;
                    padding: 0 4px;
                }
            """
            _inactive_style = """
                QPushButton {
                    background: transparent; border: none; border-radius: 5px;
                    color: #8E8E93; font-family: 'PT Root UI', sans-serif; font-size: 11px; font-weight: 500;
                    padding: 0 4px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.06); color: #FFFFFF; }
            """
            self._mode_btn_full.setStyleSheet(_active_style if active_mode == "full" else _inactive_style)
            self._mode_btn_split.setStyleSheet(_active_style if active_mode == "letter_cv_certs" else _inactive_style)
            self._mode_btn_sep.setStyleSheet(_active_style if active_mode == "separate" else _inactive_style)

        def _select_mode(mode_key: str):
            config_manager.settings.bewerbung_export_mode = mode_key
            config_manager.save()
            _update_mode_styles(mode_key)
            self._refresh_bewerbung_export_btn()

        self._mode_btn_full.clicked.connect(lambda: _select_mode("full"))
        self._mode_btn_split.clicked.connect(lambda: _select_mode("letter_cv_certs"))
        self._mode_btn_sep.clicked.connect(lambda: _select_mode("separate"))

        _update_mode_styles(cur_mode)
        cl6.addWidget(mode_bar)
        cl6.addSpacing(6)

        # --- Documents Section (Cards style with drag-and-drop reordering) ---

        self._doc_order_container = QWidget()
        self._doc_order_container.setStyleSheet("background: transparent;")
        self._doc_order_layout = QVBoxLayout(self._doc_order_container)
        self._doc_order_layout.setContentsMargins(0, 0, 0, 0)
        self._doc_order_layout.setSpacing(6)
        cl6.addWidget(self._doc_order_container)
        cl6.addSpacing(8)

        # --- Action rows ---
        self._btn_preview_pdf = self._create_sidebar_button(FluentIcon.VIEW, tr("edit.sidebar.preview_pdf", get_language(config_manager.settings.app_language)), self._preview_merged_pdf)

        self._btn_clear_bewerbung = self._create_sidebar_button(FluentIcon.CLOSE, "CLEAR ALL DOCUMENTS", self._clear_bewerbung_all)
        self._btn_clear_bewerbung.setIcon(FluentIcon.CLOSE.icon(color="#FF453A"))
        self._btn_clear_bewerbung.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; border-radius: 6px;
                color: #FF453A; font-family: 'PT Root UI', sans-serif;
                font-size: 11px; font-weight: 600; letter-spacing: 1px;
                text-align: left; padding: 8px 12px;
            }
            QPushButton:hover { background: rgba(255,69,58,0.1); }
            QPushButton:disabled { color: rgba(255,69,58,0.35); }
        """)

        def _show_export_bewerbung_menu():
            from src.ui.components import GlassMenu
            menu = GlassMenu(parent=self)
            a1 = Action(FluentIcon.DOCUMENT, "Export .txt", parent=menu)
            a1.triggered.connect(self._export_letter)
            menu.addAction(a1)
            a2 = Action(FluentIcon.DOCUMENT, "Export .docx", parent=menu)
            a2.triggered.connect(self._export_docx)
            menu.addAction(a2)
            a3 = Action(FluentIcon.DOWNLOAD, "Export PDF Bewerbungsmappe")
            a3.triggered.connect(self._run_bewerbung_export)
            menu.addAction(a3)
            menu.exec(self._btn_export.mapToGlobal(QPoint(0, self._btn_export.height())))

        self._btn_export = self._create_sidebar_button(FluentIcon.DOWNLOAD, tr("edit.sidebar.export_letter", get_language(config_manager.settings.app_language)), _show_export_bewerbung_menu)

        cl6.addWidget(self._btn_preview_pdf)
        cl6.addSpacing(4)
        cl6.addWidget(self._btn_clear_bewerbung)
        cl6.addSpacing(4)
        cl6.addWidget(self._btn_export)

        layout.addWidget(card6)

        # Initialise status labels from persisted settings
        self._refresh_bewerbung_status_ui()

        # CARD 7 - BATCH ACTIONS
        card7, cl7 = _create_card()


        self._btn_sync_leads = self._create_sidebar_button(FluentIcon.DOWNLOAD, tr("edit.sidebar.import_leads", get_language(config_manager.settings.app_language)), self._show_import_menu)
        self._btn_export_and_send_left = self._create_sidebar_button(FluentIcon.SEND, tr("edit.sidebar.send_queue", get_language(config_manager.settings.app_language)), self._action_export_and_send_batch)
        self._btn_regen_all = self._create_sidebar_button(FluentIcon.SYNC, tr("edit.sidebar.regen_all", get_language(config_manager.settings.app_language)), self._action_regenerate_all_letters)
        self._btn_delete_menu = self._create_sidebar_button(FluentIcon.DELETE, tr("edit.sidebar.manage_leads", get_language(config_manager.settings.app_language)), self._show_delete_menu)
        
        def _style_btn(btn, icon, r, g, b):
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            btn.setIcon(icon.icon(color=hex_color))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                    color: {hex_color};
                    font-family: 'PT Root UI', sans-serif;
                    font-size: 11px;
                    font-weight: 600;
                    letter-spacing: 1px;
                    text-align: left;
                    padding: 8px 12px;
                }}
                QPushButton:hover {{
                    background: rgba({r}, {g}, {b}, 0.1);
                }}
                QPushButton:disabled {{
                    color: rgba({r}, {g}, {b}, 0.4);
                }}
            """)

        _style_btn(self._btn_sync_leads, FluentIcon.DOWNLOAD, 10, 132, 255) # Blue
        _style_btn(self._btn_export_and_send_left, FluentIcon.SEND, 48, 209, 88) # Green
        _style_btn(self._btn_regen_all, FluentIcon.SYNC, 255, 159, 10) # Orange
        _style_btn(self._btn_delete_menu, FluentIcon.DELETE, 255, 69, 58) # Red

        cl7.addWidget(self._btn_sync_leads)
        cl7.addSpacing(4)
        cl7.addWidget(self._btn_export_and_send_left)
        cl7.addSpacing(4)
        cl7.addWidget(self._btn_regen_all)
        cl7.addSpacing(4)
        cl7.addWidget(self._btn_delete_menu)
        
        layout.addWidget(card7)

        layout.addStretch()
        scroll.setWidget(container)
        
        # Keep old references around so things don't crash when state is managed
        self._lead_summary = self._center_company
        self._status = self._center_company
        self._chip_sent = QLabel()
        self._chip_sent.hide()
        self._center_chip_sent = QLabel()
        self._center_chip_sent.hide()
        
        self._right_panel_stack.addWidget(scroll)

        # Build placeholders inspector for template mode
        inspector = QFrame()
        inspector.setObjectName("TemplateInspector")
        inspector.setStyleSheet("""
            QFrame#TemplateInspector { 
                background: #1C1C1E; 
                border: 1px solid #2C2C2E;
                border-radius: 12px;
            }
        """)
        ins_layout = QVBoxLayout(inspector)
        ins_layout.setContentsMargins(0, 0, 0, 0)
        ins_layout.setSpacing(0)
        
        sidebar_title = QLabel(tr("Placeholders", get_language(config_manager.settings.app_language)))
        sidebar_title.setStyleSheet("color: #D1D1D6; font: 600 13px '-apple-system, BlinkMacSystemFont, Arial, sans-serif'; padding: 20px 20px 12px 20px; border: none; background: transparent;")
        ins_layout.addWidget(sidebar_title)
        
        placeholder_scroll = QScrollArea()
        placeholder_scroll.setFrameShape(QFrame.NoFrame)
        placeholder_scroll.setWidgetResizable(True)
        placeholder_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { background: transparent; width: 5px; } QScrollBar::handle:vertical { background: rgba(255,255,255,.15); border-radius: 2px; min-height: 24px; } QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
        
        placeholder_list = QWidget()
        placeholder_list.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(placeholder_list)
        list_layout.setContentsMargins(20, 0, 20, 18)
        list_layout.setSpacing(0)
        
        for token, description in PLACEHOLDER_REFERENCE:
            row = QPushButton()
            row.setCursor(Qt.PointingHandCursor)
            row.setFlat(True)
            row.setFixedHeight(57)
            row.setStyleSheet("QPushButton { text-transform: none; text-align: left; border: none; border-bottom: 1px solid rgba(255,255,255,.055); background: transparent; padding: 7px 0; } QPushButton:hover { background: rgba(10,132,255,.08); }")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            token_label = QLabel(token)
            token_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            token_label.setStyleSheet("color: #0A84FF; font-family: 'SF Mono', Menlo, monospace; font-size: 12px; font-weight: 500; border: none; background: transparent;")
            description_label = QLabel(description)
            description_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            description_label.setStyleSheet("color: #8E8E93; font: 12px '-apple-system, BlinkMacSystemFont, Arial, sans-serif'; border: none; background: transparent;")
            description_label.setWordWrap(False)
            row_layout.addWidget(token_label)
            row_layout.addWidget(description_label)
            row.clicked.connect(lambda checked=False, p=token: self._insert_placeholder(p))
            list_layout.addWidget(row)
            
        list_layout.addStretch(1)
        placeholder_scroll.setWidget(placeholder_list)
        ins_layout.addWidget(placeholder_scroll, 1)
        
        self._right_panel_stack.addWidget(inspector)

        return self._right_panel_stack

    # ─────────────────────────────────────────────────────────────────────────
    # Keyboard shortcuts
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._toggle_find_bar)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._autosave)
        QShortcut(QKeySequence("Escape"), self._find_bar).activated.connect(
            self._find_bar.hide
        )

    def _toggle_find_bar(self):
        if self._find_bar.isVisible():
            self._find_bar.hide()
            self._editor.setFocus()
        else:
            self._find_bar.show()
            self._find_bar.findChild(LineEdit).setFocus()
            self._find_bar.findChild(LineEdit).selectAll()

    def _toggle_find_bar(self):
        if self._find_bar.isVisible():
            self._find_bar.hide()
        else:
            self._find_bar.show_and_focus()

    # ─────────────────────────────────────────────────────────────────────────
    # Data loading
    # ─────────────────────────────────────────────────────────────────────────


    def _show_delete_menu(self):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground)
        
        a1 = QAction(tr("edit.delete.selected", get_language(config_manager.settings.app_language)), self)
        a1.triggered.connect(self._delete_selected)
        a2 = QAction(tr("edit.delete.sent", get_language(config_manager.settings.app_language)), self)
        a2.triggered.connect(self._delete_sent)
        a3 = QAction(tr("edit.delete.all", get_language(config_manager.settings.app_language)), self)
        a3.triggered.connect(self._delete_all)
        
        menu.addAction(a1)
        menu.addAction(a2)
        menu.addAction(a3)

        menu.setStyleSheet("""
            QMenu {
                background-color: #2C2C2E;
                border: 1px solid #3A3A3C;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                color: #FF453A;
                padding: 8px 32px 8px 16px;
                border-radius: 4px;
                margin: 2px 4px;
                font-family: 'PT Root UI', 'SF Pro Text', sans-serif;
                font-size: 13px;
                font-weight: 500;
            }
            QMenu::item:selected {
                background-color: rgba(255, 69, 58, 0.15);
            }
        """)
        menu.exec(self._btn_delete_menu.mapToGlobal(QPoint(0, self._btn_delete_menu.height() + 6)))

    def _delete_selected(self):
        if not self._selected_record:
            self._show_error("Delete Failed", "No lead selected.")
            return
            
        w = AppleConfirmDialog(
            "Delete Selected Lead",
            f"Are you sure you want to permanently delete {self._selected_record.company_name}?",
            parent=self.window()
        )
        if not w.exec():
            return
            
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            conn.execute("INSERT OR IGNORE INTO letter_state (lead_id) VALUES (?)", (self._selected_record.id,))
            conn.execute("UPDATE letter_state SET is_discarded = 1 WHERE lead_id = ?", (self._selected_record.id,))
            conn.commit()
            conn.close()
            
            self._lead_list.clearSelection()
            self._selected_record = None
            self._selected_state = None
            self.refresh()
            self._show_success("Discarded", "The lead has been removed from the Edit list.")
        except Exception as e:
            self._show_error("Delete Failed", str(e))

    def _delete_sent(self):
        w = AppleConfirmDialog(
            "Delete Sent Leads",
            "Are you sure you want to permanently delete all leads that have been marked as sent?",
            parent=self.window()
        )
        if not w.exec():
            return
            
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            # Find all lead IDs that are sent
            rows = conn.execute("SELECT lead_id FROM letter_state WHERE sent_at IS NOT NULL AND (is_discarded IS NULL OR is_discarded = 0)").fetchall()
            lead_ids = [r[0] for r in rows]
            
            if not lead_ids:
                self._show_success("Nothing to Remove", "There are no active sent leads.")
                conn.close()
                return
                
            placeholders = ",".join("?" * len(lead_ids))
            conn.execute(f"UPDATE letter_state SET is_discarded = 1 WHERE lead_id IN ({placeholders})", lead_ids)
            conn.commit()
            conn.close()
            
            self._lead_list.clearSelection()
            self._selected_record = None
            self._selected_state = None
            self.refresh()
            self._show_success("Discarded", f"Removed {len(lead_ids)} sent leads from the Edit list.")
        except Exception as e:
            self._show_error("Delete Failed", str(e))

    def _delete_all(self):
        w = AppleConfirmDialog(
            "Delete ALL Leads",
            "Are you absolutely sure you want to permanently delete ALL leads in your database? This action cannot be undone.",
            parent=self.window()
        )
        if not w.exec():
            return
            
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            
            # For "Delete All", we insert/update all leads that are currently in self._records to be discarded
            records_ids = [r.id for r in self._records]
            if records_ids:
                for chunk in [records_ids[i:i + 500] for i in range(0, len(records_ids), 500)]:
                    for rid in chunk:
                        conn.execute("INSERT OR IGNORE INTO letter_state (lead_id) VALUES (?)", (rid,))
                    placeholders = ",".join("?" * len(chunk))
                    conn.execute(f"UPDATE letter_state SET is_discarded = 1 WHERE lead_id IN ({placeholders})", chunk)
                    
            conn.commit()
            conn.close()
            
            self._lead_list.clearSelection()
            self._selected_record = None
            self._selected_state = None
            self.refresh()
            self._show_success("List Cleared", "All leads have been removed from the Edit list.")
        except Exception as e:
            self._show_error("Delete Failed", str(e))

    def _on_import_spreadsheet(self):
        from PySide6.QtWidgets import QFileDialog
        from src.services.export_service import ExportService
        from src.core.config import get_memory_db_path
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Leads from Excel or CSV",
            "",
            "Spreadsheets (*.xlsx *.xls *.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            service = ExportService()
            new_records = service.import_spreadsheet(path)
            if not new_records:
                from .toast_system import ToastNotification as InfoBar
                ToastNotification.warning(
                    title="No Leads Found",
                    content="Could not extract any leads from the selected file.",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=self.window()
                )
                return
            db_path = str(get_memory_db_path())
            service.save_records_to_db(new_records, db_path)

            existing_emails = {r.email.lower(): r for r in self._records if r.email}
            all_imported_ids = []
            for r in new_records:
                ek = (r.email or "").lower()
                if ek and ek in existing_emails:
                    old_r = existing_emails[ek]
                    if r.company_name:
                        old_r.company_name = r.company_name
                    if r.contact_person:
                        old_r.contact_person = r.contact_person
                    if old_r.id in self._states:
                        self._states[old_r.id].is_discarded = 0
                    else:
                        self._states[old_r.id] = LetterState(is_discarded=0)
                    all_imported_ids.append(old_r.id)
                else:
                    self._states[r.id] = LetterState(is_discarded=0)
                    self._records.append(r)
                    if ek:
                        existing_emails[ek] = r
                    all_imported_ids.append(r.id)

            import sqlite3
            conn = sqlite3.connect(db_path, timeout=10.0)
            try:
                for lid in set(all_imported_ids):
                    conn.execute(
                        "INSERT INTO letter_state (lead_id, is_discarded) VALUES (?, 0) "
                        "ON CONFLICT(lead_id) DO UPDATE SET is_discarded = 0",
                        (lid,)
                    )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

            self._active_filter = "all"
            if hasattr(self, "_update_segment_styles"):
                self._update_segment_styles("all")
            self._populate_leads()
            if self._pending_lead_records:
                first_rec = self._pending_lead_records[0]
                self._render_record(first_rec)

            from ..core.events import event_bus, EventBus
            event_bus.emit(EventBus.DB_UPDATED, records=[])

            from .toast_system import ToastNotification as InfoBar
            ToastNotification.success(
                title="Spreadsheet Imported",
                content=f"Successfully imported and saved {len(new_records)} lead(s) from {Path(path).name}.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.window()
            )
        except Exception as e:
            from .toast_system import ToastNotification as InfoBar
            ToastNotification.error(
                title="Import Error",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=6000,
                parent=self.window()
            )

    def refresh(self):
        self._status.setText("Loading leads…")
        run_in_thread(
            self._load_data,
            on_result=self._on_data_loaded,
            on_error=lambda tb: self._show_error(
                "Load failed", tb.splitlines()[-1] if tb else "Unknown error"
            ),
        )

    def _load_data(self) -> tuple[list[LeadRecord], dict[str, LetterState]]:
        db_path = get_memory_db_path()
        if not db_path.exists():
            return [], {}
        _, records = ExportService().load_project(str(db_path))
        seen_emails = set()
        unique_records = []
        for r in records:
            if not r.email or not _is_valid_email(r.email):
                continue
            ekey = r.email.strip().lower()
            if ekey in seen_emails:
                continue
            seen_emails.add(ekey)
            unique_records.append(r)
        states     = self._load_letter_states(db_path)
        return unique_records, states

    def _load_letter_states(self, db_path: Path) -> dict[str, LetterState]:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            self._ensure_letter_state_table(conn)
            rows = conn.execute(
                "SELECT lead_id, generated_at, edited_at, sent_at, "
                "letter_text, previous_text, last_saved_ts, is_discarded FROM letter_state"
            ).fetchall()
            return {
                row[0]: LetterState(
                    row[1] or "", row[2] or "", row[3] or "",
                    row[4] or "", row[5] or "", row[6] or "", row[7] or 0
                )
                for row in rows
            }
        finally:
            conn.close()

    @staticmethod
    def _ensure_letter_state_table(conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS letter_state (
                lead_id       TEXT PRIMARY KEY,
                generated_at  TEXT,
                edited_at     TEXT,
                sent_at       TEXT,
                letter_text   TEXT,
                previous_text TEXT,
                last_saved_ts TEXT,
                is_discarded  INTEGER DEFAULT 0,
                tracking_id   TEXT,
                opened_at     TEXT,
                open_count    INTEGER DEFAULT 0
            )
        """)
        # migrate older schema that lacked new columns
        existing = {r[1] for r in conn.execute("PRAGMA table_info(letter_state)")}
        
        migrations = [
            ("previous_text", "TEXT", "''"), 
            ("last_saved_ts", "TEXT", "''"), 
            ("is_discarded", "INTEGER", "0"),
            ("tracking_id", "TEXT", "NULL"),
            ("opened_at", "TEXT", "NULL"),
            ("open_count", "INTEGER", "0")
        ]
        
        for col, ctype, default in migrations:
            if col not in existing:
                conn.execute(f"ALTER TABLE letter_state ADD COLUMN {col} {ctype} DEFAULT {default}")
        conn.commit()

    @staticmethod
    def _ensure_settings_table(conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

    def _on_db_updated(self, records: list):
        run_in_thread(
            self._load_data,
            on_result=self._on_data_loaded
        )

    def _on_live_result_added(self, record):
        if not record.email or not _is_valid_email(record.email):
            return
        # ensure no duplicate ID or duplicate email address
        ekey = record.email.strip().lower()
        for r in self._records:
            if r.id == record.id or (r.email and r.email.strip().lower() == ekey):
                return
        self._records.append(record)
        state = self._states.get(record.id)
        if state and state.is_discarded:
            return
            
        if self._active_filter == "sent" and not (state and state.sent_at):
            return
        if self._active_filter == "pending" and (state and state.sent_at):
            return
        
        needle = self._search.text().strip().lower() if hasattr(self, "_search") else ""
        if needle:
            haystack = " ".join(filter(None, [record.company_name, record.contact_person, record.city, record.job_title])).lower()
            if needle not in haystack:
                return

        item = QListWidgetItem()
        item.setData(Qt.UserRole, record.id)
        item.setSizeHint(QSize(0, 74))
        item.setToolTip(record.company_name or "Lead")
        self._lead_list.addItem(item)
        row_widget = LeadRowWidget(record, state)
        self._lead_list.setItemWidget(item, row_widget)
        self._update_filter_labels(needle)

    def _on_data_loaded(self, payload):
        self._records, self._states = payload
        self._populate_leads()
        if self._records:
            self._lead_list.setCurrentRow(0)
            self._render_record(self._records[0])
        else:
            self._editor.clear()
            self._status.setText("No leads found in SQLite.")
            self._set_actions_enabled(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Lead list population
    # ─────────────────────────────────────────────────────────────────────────

    _active_filter: str = "all"

    def _on_filter(self, key: str):
        self._active_filter = key
        self._update_filter_labels()
        self._update_segment_styles(key)
        self._populate_leads()

    def _populate_leads(self):
        needle = self._search.text().strip().lower() if hasattr(self, "_search") else ""
        self._update_filter_labels(needle)
        self._lead_population_token += 1
        token = self._lead_population_token
        self._lead_list.blockSignals(True)
        self._lead_list.clear()
        self._lead_list.blockSignals(False)
        self._selected_row_widget = None

        self._pending_lead_records = []
        for record in self._records:
            state = self._states.get(record.id)

            if state and state.is_discarded:
                continue

            # apply filter
            if self._active_filter == "sent" and not (state and state.sent_at):
                continue
            if self._active_filter == "pending" and (state and state.sent_at):
                continue

            if needle:
                haystack = " ".join(
                    filter(None, [
                        record.company_name, record.contact_person,
                        record.city, record.job_title,
                    ])
                ).lower()
                if needle not in haystack:
                    continue

            self._pending_lead_records.append(record)

        if hasattr(self, "_sidebar_count"):
            pass

        self._pending_lead_index = 0
        QTimer.singleShot(0, lambda: self._append_lead_batch(token))

    def _update_filter_labels(self, needle: str | None = None) -> None:
        if not hasattr(self, "_filter_btns"):
            return
        if needle is None:
            needle = self._search.text().strip().lower() if hasattr(self, "_search") else ""

        counts = {"all": 0, "pending": 0, "sent": 0}
        email_counts = {"all": 0, "pending": 0, "sent": 0}
        for record in self._records:
            state = self._states.get(record.id)
            if state and state.is_discarded:
                continue
                
            if needle:
                haystack = " ".join(
                    filter(None, [
                        record.company_name, record.contact_person,
                        record.city, record.job_title,
                    ])
                ).lower()
                if needle not in haystack:
                    continue

            is_sent = bool(state and state.sent_at)
            counts["all"] += 1
            counts["sent" if is_sent else "pending"] += 1
            if record.email and record.email.strip():
                email_counts["all"] += 1
                email_counts["sent" if is_sent else "pending"] += 1

        for key, btn in self._filter_btns.items():
            base_label = { "all": tr("edit.tab.all", get_language(config_manager.settings.app_language)), "pending": tr("edit.tab.pending", get_language(config_manager.settings.app_language)), "sent": tr("edit.tab.sent", get_language(config_manager.settings.app_language)) }[key]
            c = counts[key]
            ec = email_counts[key]
            if c > 0 and ec != c:
                btn.setText(f"{base_label} {c} ({ec} emails)")
            else:
                btn.setText(f"{base_label} {c}")

    def _append_lead_batch(self, token: int):
        if token != self._lead_population_token:
            return
        batch_size = 15
        end = min(self._pending_lead_index + batch_size, len(self._pending_lead_records))
        self._lead_list.setUpdatesEnabled(False)
        try:
            for i, record in enumerate(self._pending_lead_records[self._pending_lead_index:end]):
                item = QListWidgetItem()
                item.setData(Qt.UserRole, record.id)
                item.setSizeHint(QSize(0, 74))
                self._lead_list.addItem(item)
                is_last = (self._pending_lead_index + i == len(self._pending_lead_records) - 1)
                row_widget = LeadRowWidget(record, self._states.get(record.id), is_last)
                row_widget.set_selected(record.id == self._selected_lead_id)
                if record.id == self._selected_lead_id:
                    self._selected_row_widget = row_widget
                    self._lead_list.setCurrentItem(item)
                self._lead_list.setItemWidget(item, row_widget)
        finally:
            self._lead_list.setUpdatesEnabled(True)

        self._pending_lead_index = end
        if self._pending_lead_index < len(self._pending_lead_records):
            QTimer.singleShot(15, lambda: self._append_lead_batch(token))

    # ─────────────────────────────────────────────────────────────────────────
    # Lead selection / rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _on_lead_clicked(self, item: QListWidgetItem):
        lead_id = item.data(Qt.UserRole)
        record  = next((r for r in self._records if r.id == lead_id), None)
        if record:
            self._render_record(record)

    def _render_record(self, record: LeadRecord):
        # auto-save outgoing lead before switching
        if self._selected_record and not self._loading_text:
            self._autosave(silent=True)

        self._selected_record  = record
        previous_selected      = self._selected_row_widget
        self._selected_lead_id = record.id
        state  = self._states.get(record.id, LetterState())
        text   = state.letter_text or self._assemble_letter(record)

        self._rendered_text = text
        self._set_editor_text(text)

        self._set_actions_enabled(True)
        self._set_status(record, state)
        self._update_lead_summary(record)
        

        self._update_lead_selection_styles(previous_selected)
        self._update_word_count()
        self._check_placeholders()

        if not state.generated_at:
            self._mark_generated_async(record.id, text)

        if state.last_saved_ts:
            pass
        else:
            pass

        # enable/disable revert button
        self._set_undo_ver_enabled(bool(state.previous_text))

    def _update_lead_selection_styles(
        self, previous_selected: LeadRowWidget | None = None
    ):
        if previous_selected is not None:
            previous_selected.set_selected(False)
        for row in range(self._lead_list.count()):
            item   = self._lead_list.item(row)
            widget = self._lead_list.itemWidget(item)
            if isinstance(widget, LeadRowWidget) and item.data(Qt.UserRole) == self._selected_lead_id:
                widget.set_selected(True)
                self._selected_row_widget = widget
                break


    # ─────────────────────────────────────────────────────────────────────────
    # Auto-save
    # ─────────────────────────────────────────────────────────────────────────

    def _autosave(self, silent: bool = False):
        if getattr(self, '_is_template_mode', False) or not self._selected_record:
            return
        text  = self._editor.toPlainText()
        state = self._states.setdefault(self._selected_record.id, LetterState())
        if text == state.letter_text:
            return   # nothing changed
        now_ts = datetime.now().strftime("%H:%M")
        state.previous_text  = state.letter_text   # keep one version back
        state.letter_text    = text
        state.edited_at      = state.edited_at or datetime.utcnow().isoformat()
        state.last_saved_ts  = now_ts
        self._persist_state_async(
            self._selected_record.id,
            edited_at=state.edited_at,
            letter_text=text,
            previous_text=state.previous_text,
            last_saved_ts=now_ts,
        )
        self._set_undo_ver_enabled(bool(state.previous_text))

    # ─────────────────────────────────────────────────────────────────────────
    # Word count + placeholder audit
    # ─────────────────────────────────────────────────────────────────────────

    def _update_word_count(self):
        return

    def _check_placeholders(self):
        _highlight_placeholders(self._editor)

    # ─────────────────────────────────────────────────────────────────────────
    # Text-changed handler
    # ─────────────────────────────────────────────────────────────────────────

    def _set_editor_text(self, text: str):
        self._loading_text = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading_text = False

    def _on_text_changed(self):
        if self._loading_text or getattr(self, '_is_template_mode', False) or not self._selected_record:
            return
        current = self._editor.toPlainText()
        state   = self._states.setdefault(self._selected_record.id, LetterState())
        if current != self._rendered_text:
            state.edited_at = state.edited_at or datetime.utcnow().isoformat()
        self._set_status(self._selected_record, state)
        self._autosave_timer.start()
        self._wc_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # Letter assembly & polish
    # ─────────────────────────────────────────────────────────────────────────

    def _assemble_letter(self, record: LeadRecord) -> str:
        template = self._template_text or self._load_template()
        sender   = self._load_sender_settings()
        replacements = {
            "ANREDE":         self._salutation(record.contact_person),
            "FIRMA":          record.company_name        or "Unternehmen",
            "ORT":            __import__("re").sub(r"^\d+\s*", "", str(sender.get("city") or "")).strip(),
            "PLZ":            record.postal_code         or "",
            "BERUF":          sender.get("beruf") or record.job_title or record.category or "Ausbildung",
            "DATUM":          self._german_date(),
        }
        for k, v in sender.items():
            replacements[f"SENDER_{k.upper()}"] = v
            
        text = template
        for key, value in replacements.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return self._polish_letter(text, replacements)

    def _fetch_sender_settings(self, **kwargs) -> None:
        run_in_thread(
            self._do_fetch_sender_settings,
            on_result=self._on_sender_settings_loaded
        )
        
    def _do_fetch_sender_settings(self) -> dict:
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn    = sqlite3.connect(db_path, timeout=10.0)
            self._ensure_settings_table(conn)
            rows    = conn.execute(
                "SELECT key, value FROM settings WHERE key LIKE 'sender_%'"
            ).fetchall()
            conn.close()
            return {row[0].replace("sender_", ""): row[1] for row in rows}
        except Exception:
            return {}

    def _on_sender_settings_loaded(self, settings: dict) -> None:
        self._cached_sender_settings = settings

    def _load_sender_settings(self) -> dict:
        """Return cached sender settings."""
        return self._cached_sender_settings.copy()

    def _do_fetch_persisted_pdf_path(self) -> str:
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            self._ensure_settings_table(conn)
            row = conn.execute("SELECT value FROM settings WHERE key = 'bewerbung_pdf_path'").fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def _on_persisted_pdf_path_loaded(self, path_str: str) -> None:
        if path_str:
            p = Path(path_str)
            if p.exists():
                self._load_bewerbung_pdf(p)

    def _do_fetch_signature_path(self) -> str:
        import sqlite3
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            self._ensure_settings_table(conn)
            row = conn.execute("SELECT value FROM settings WHERE key = 'signature_image_path'").fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def _on_signature_path_loaded(self, path_str: str) -> None:
        self._signature_image_path = path_str

    def _save_signature_path(self, path_str: str) -> None:
        self._signature_image_path = path_str
        def _do_save():
            import sqlite3
            try:
                db_path = get_memory_db_path()
                conn = sqlite3.connect(db_path, timeout=10.0)
                self._ensure_settings_table(conn)
                if path_str:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('signature_image_path', ?)", (path_str,))
                else:
                    conn.execute("DELETE FROM settings WHERE key = 'signature_image_path'")
                conn.commit()
                conn.close()
            except Exception:
                pass
        run_in_thread(_do_save)

    def _edit_profile(self) -> None:
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                     QScrollArea, QWidget, QLineEdit, QInputDialog, 
                                     QFrame, QGraphicsDropShadowEffect, QPushButton, QSizePolicy)
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        from ..core.config import get_memory_db_path
        
        class GlassDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
                self.setAttribute(Qt.WA_TranslucentBackground)
                self.setFixedSize(440, 620)
                self._drag_pos = None
                # Style the dialog itself as the rounded card
                self.setStyleSheet("""
                    GlassDialog {
                        background: #2C2C2E;
                        border-radius: 14px;
                        border: 1px solid rgba(255, 255, 255, 20);
                    }
                """)

            def showEvent(self, event):
                super().showEvent(event)
                # Center on parent after showing so geometry is final
                if self.parent() and hasattr(self.parent(), 'geometry'):
                    pg = self.parent().window().geometry()
                    self.move(
                        pg.x() + (pg.width() - self.width()) // 2,
                        pg.y() + (pg.height() - self.height()) // 2
                    )

            def paintEvent(self, event):
                from PySide6.QtGui import QPainter, QPainterPath, QColor
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)
                painter.fillPath(path, QColor("#2C2C2E"))
                painter.setPen(QColor(255, 255, 255, 20))
                painter.drawPath(path)

            def mousePressEvent(self, event):
                if event.button() == Qt.LeftButton:
                    self._drag_pos = event.globalPosition().toPoint()
            def mouseMoveEvent(self, event):
                if self._drag_pos is not None:
                    delta = event.globalPosition().toPoint() - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = event.globalPosition().toPoint()
            def mouseReleaseEvent(self, event):
                self._drag_pos = None

        dialog = GlassDialog(self)

        # Root layout directly on dialog — no inner container frame
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 1. HEADER (fixed 90px) ────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setFixedHeight(90)
        header_widget.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(24, 22, 24, 18)
        header_layout.setSpacing(4)

        title_lbl = QLabel(tr("Personal information", get_language(config_manager.settings.app_language)))
        title_lbl.setStyleSheet("color: #FFFFFF; font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif; font-size: 17px; font-weight: 600; background: transparent; border: none;")
        header_layout.addWidget(title_lbl)

        hint = QLabel(tr("Enter your details to automatically inject them into your templates.", get_language(config_manager.settings.app_language)))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8E8E93; font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif; font-size: 13px; font-weight: 400; background: transparent; border: none;")
        header_layout.addWidget(hint)
        layout.addWidget(header_widget)

        # Header divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255, 255, 255, 20); border: none;")
        layout.addWidget(divider)

        # ── 2. SCROLL AREA (flex 1, fills between header and footer) ─────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 0px; background: transparent; }
        """)

        body_container = QWidget()
        body_container.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(body_container)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(16)
        scroll.setWidget(body_container)

        layout.addWidget(scroll, 1)   # stretch=1 so it takes all remaining space

        current = self._cached_sender_settings.copy()
        fields = {}

        def _add_field(key, label_title, token_text):
            row = QVBoxLayout()
            row.setSpacing(6)

            lbl_row = QHBoxLayout()
            lbl_row.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(label_title)
            lbl.setStyleSheet("color: #EBEBF0; font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif; font-weight: 500; font-size: 13px; background: transparent; border: none;")

            token = QLabel(token_text)
            token.setStyleSheet("""
                QLabel {
                    background: #3A3A3C;
                    color: #8E8E93;
                    border-radius: 6px;
                    padding: 3px 7px;
                    font-family: 'Menlo', monospace;
                    font-size: 11px;
                    border: none;
                }
            """)

            lbl_row.addWidget(lbl)
            lbl_row.addStretch(1)
            lbl_row.addWidget(token)
            row.addLayout(lbl_row)

            inp = QLineEdit()
            inp.setText(current.get(key, ""))
            inp.setFixedHeight(40)
            inp.setStyleSheet("""
                QLineEdit {
                    background: #1C1C1E;
                    border: 1px solid rgba(255, 255, 255, 41);
                    border-radius: 10px;
                    color: #FFFFFF;
                    padding: 0 12px;
                    font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif;
                    font-size: 14px;
                    min-height: 38px;
                    max-height: 38px;
                }
                QLineEdit:focus {
                    border: 1px solid #0A84FF;
                    background: #1C1C1E;
                }
            """)
            row.addWidget(inp)
            form_layout.addLayout(row)
            fields[key] = inp

        _add_field("name", tr("edit.profile.fullname", get_language(config_manager.settings.app_language)), "{{SENDER_NAME}}")
        _add_field("email", tr("edit.profile.email", get_language(config_manager.settings.app_language)), "{{SENDER_EMAIL}}")
        _add_field("phone", tr("edit.profile.phone", get_language(config_manager.settings.app_language)), "{{SENDER_PHONE}}")
        _add_field("address", tr("edit.profile.street", get_language(config_manager.settings.app_language)), "{{SENDER_ADDRESS}}")
        _add_field("city", tr("edit.profile.city", get_language(config_manager.settings.app_language)), "{{SENDER_CITY}}")
        _add_field("beruf", "Target job (Overrides default)", "{{BERUF}}")

        default_keys = {"name", "email", "phone", "address", "city", "beruf"}
        for k in current.keys():
            if k not in default_keys:
                _add_field(k, f"Custom: {k}", f"{{{{SENDER_{k.upper()}}}}}")

        btn_add_custom = QPushButton(tr("Add custom field", get_language(config_manager.settings.app_language)))
        btn_add_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_custom.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 8);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                color: #A1A1A6;
                font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 10px 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 15);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 38);
            }
        """)

        def _on_add_custom():
            key, ok = QInputDialog.getText(dialog, "New Custom Field", "Enter variable name:")
            if ok and key.strip():
                k = key.strip().lower()
                k = "".join(c for c in k if c.isalnum() or c == "_")
                if k and k not in fields:
                    _add_field(k, f"Custom: {k}", f"{{{{SENDER_{k.upper()}}}}}")
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        btn_add_custom.clicked.connect(_on_add_custom)
        form_layout.addWidget(btn_add_custom)
        form_layout.addStretch()

        # ── 3. FOOTER (fixed 72px, pinned below scroll) ───────────────────────
        footer_widget = QWidget()
        footer_widget.setFixedHeight(72)
        footer_widget.setObjectName("ProfileDialogFooter")
        footer_widget.setStyleSheet("""
            QWidget#ProfileDialogFooter {
                background: transparent;
                border-top: 1px solid rgba(255, 255, 255, 20);
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(24, 0, 24, 0)
        footer_layout.setSpacing(16)

        # Cancel — bare text button, no fill, no border
        btn_cancel = QPushButton(tr("Cancel", get_language(config_manager.settings.app_language)))
        btn_cancel.setObjectName("ProfileDialogCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet("""
            QPushButton#ProfileDialogCancel {
                background: transparent;
                border: none;
                color: #0A84FF;
                font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif;
                font-size: 14px;
                font-weight: 500;
                padding: 0 12px;
            }
            QPushButton#ProfileDialogCancel:hover { color: #409CFF; }
            QPushButton#ProfileDialogCancel:pressed { color: #0071E3; }
        """)
        btn_cancel.clicked.connect(dialog.reject)

        # Save — filled #0A84FF, 10px radius (not pill)
        btn_save = QPushButton(tr("Save information", get_language(config_manager.settings.app_language)))
        btn_save.setObjectName("ProfileDialogSave")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setFixedHeight(40)
        btn_save.setStyleSheet("""
            QPushButton#ProfileDialogSave {
                background: #0A84FF;
                border: none;
                border-radius: 10px;
                color: #FFFFFF;
                font-family: 'SF Pro Text', system-ui, -apple-system, sans-serif;
                font-size: 14px;
                font-weight: 500;
                padding: 0 20px;
                min-height: 38px;
                max-height: 38px;
            }
            QPushButton#ProfileDialogSave:hover { background: #409CFF; }
            QPushButton#ProfileDialogSave:pressed { background: #0071E3; }
        """)
        btn_save.clicked.connect(dialog.accept)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(btn_save)
        layout.addWidget(footer_widget)
        
        if dialog.exec():
            for k, inp in fields.items():
                self._cached_sender_settings[k] = inp.text().strip()
            
            def _do_save_all():
                import sqlite3
                try:
                    db_path = get_memory_db_path()
                    conn = sqlite3.connect(db_path, timeout=10.0)
                    self._ensure_settings_table(conn)
                    for k, v in self._cached_sender_settings.items():
                        key = f"sender_{k}"
                        if v:
                            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, v))
                        else:
                            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
            run_in_thread(_do_save_all)
            self._show_success("Information Saved", "Your details have been updated for templates.")

    def _load_pdf_settings(self) -> dict:
        import sqlite3
        settings = {"font": "Helvetica", "size": "11", "leading": "14", "alignment": "Justified"}
        try:
            db_path = get_memory_db_path()
            conn = sqlite3.connect(db_path, timeout=10.0)
            self._ensure_settings_table(conn)
            rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'pdf_%'").fetchall()
            for k, v in rows:
                settings[k.replace("pdf_", "")] = v
            conn.close()
        except Exception:
            pass
        return settings

    def _edit_pdf_settings(self) -> None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
        from qfluentwidgets import PushButton, PrimaryPushButton, SpinBox
        from src.ui.components import MacComboBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("PDF Styling Options")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet("QDialog { background: #1C1C1E; }")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        hint = QLabel(tr("Customize the visual appearance of your generated application PDF.", get_language(config_manager.settings.app_language)))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AEAEB2; font-family: system-ui, -apple-system, sans-serif; font-size: 13px; background: transparent;")
        layout.addWidget(hint)
        layout.addSpacing(10)
        
        settings = self._load_pdf_settings()
        
        # Font Family
        lbl_font = QLabel(tr("Font Family", get_language(config_manager.settings.app_language)))
        lbl_font.setStyleSheet("color: #E5E5EA; font-weight: 500; font-size: 12px; background: transparent;")
        layout.addWidget(lbl_font)
        cb_font = MacComboBox()
        cb_font.addItems(["Helvetica", "Times-Roman", "Courier"])
        cb_font.setCurrentText(settings.get("font", "Helvetica"))
        layout.addWidget(cb_font)
        
        # Font Size
        lbl_size = QLabel(tr("Font Size (pt)", get_language(config_manager.settings.app_language)))
        lbl_size.setStyleSheet("color: #E5E5EA; font-weight: 500; font-size: 12px; background: transparent;")
        layout.addWidget(lbl_size)
        sp_size = SpinBox()
        sp_size.setRange(8, 16)
        try:
            sp_size.setValue(int(settings.get("size", "11")))
        except ValueError:
            sp_size.setValue(11)
        layout.addWidget(sp_size)
        
        # Line Spacing
        lbl_lead = QLabel(tr("Line Spacing (pt)", get_language(config_manager.settings.app_language)))
        lbl_lead.setStyleSheet("color: #E5E5EA; font-weight: 500; font-size: 12px; background: transparent;")
        layout.addWidget(lbl_lead)
        sp_lead = SpinBox()
        sp_lead.setRange(10, 24)
        try:
            sp_lead.setValue(int(settings.get("leading", "14")))
        except ValueError:
            sp_lead.setValue(14)
        layout.addWidget(sp_lead)
        
        # Alignment
        lbl_align = QLabel(tr("Text Alignment", get_language(config_manager.settings.app_language)))
        lbl_align.setStyleSheet("color: #E5E5EA; font-weight: 500; font-size: 12px; background: transparent;")
        layout.addWidget(lbl_align)
        cb_align = MacComboBox()
        cb_align.addItems(["Justified", "Left"])
        cb_align.setCurrentText(settings.get("alignment", "Justified"))
        layout.addWidget(cb_align)
        
        layout.addSpacing(16)
        btn_box = QHBoxLayout()
        btn_cancel = PushButton(tr("Cancel", get_language(config_manager.settings.app_language)))
        btn_cancel.clicked.connect(dialog.reject)
        btn_save = PrimaryPushButton(tr("Save Styling", get_language(config_manager.settings.app_language)))
        btn_save.clicked.connect(dialog.accept)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)
        
        if dialog.exec():
            def _do_save_pdf_settings():
                import sqlite3
                try:
                    db_path = get_memory_db_path()
                    conn = sqlite3.connect(db_path, timeout=10.0)
                    self._ensure_settings_table(conn)
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pdf_font', ?)", (cb_font.currentText(),))
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pdf_size', ?)", (str(sp_size.value()),))
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pdf_leading', ?)", (str(sp_lead.value()),))
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pdf_alignment', ?)", (cb_align.currentText(),))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
            run_in_thread(_do_save_pdf_settings)
            self._show_success("Styling Saved", "Your PDF layout settings have been updated.")

    def _upload_signature(self) -> None:
        start_dir = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        if not start_dir:
            start_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature Image",
            start_dir,
            "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._save_signature_path(path)
            self._show_success("Signature Saved", "Signature will be added to PDFs.")

    def _clear_signature(self) -> None:
        self._save_signature_path("")
        self._show_success("Signature Cleared", "Signature removed.")

    def _save_persisted_pdf_path(self, path_str: str) -> None:
        def _do_save():
            import sqlite3
            try:
                db_path = get_memory_db_path()
                conn = sqlite3.connect(db_path, timeout=10.0)
                self._ensure_settings_table(conn)
                if path_str:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bewerbung_pdf_path', ?)", (path_str,))
                else:
                    conn.execute("DELETE FROM settings WHERE key = 'bewerbung_pdf_path'")
                conn.commit()
                conn.close()
            except Exception:
                pass
        run_in_thread(_do_save)

    def _polish_letter(self, text: str, replacements: dict[str, str]) -> str:
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        cleaned = self._normalize_professional_german(cleaned)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        company    = replacements.get("FIRMA")    or "Unternehmen"
        city       = replacements.get("ORT")      or ""
        job        = replacements.get("BERUF")    or "Ausbildung"
        salutation = replacements.get("ANREDE")   or "Sehr geehrte Damen und Herren,"
        date_line  = replacements.get("DATUM")    or self._german_date()

        # (Removed aggressive fallback that threw away user templates)

        # light lexical corrections
        corrections = {
            "mit grossem interesse":          "mit großem Interesse",
            "mit freundlichen gruessen":      "Mit freundlichen Grüßen",
            "ueber eine einladung":           "Über eine Einladung",
            "persoenlichen gespraech":        "persönlichen Gespräch",
            "zuverlaessig":                   "zuverlässig",
            "moechte":                        "möchte",
        }
        polished = cleaned
        for old, new in corrections.items():
            polished = re.sub(old, new, polished, flags=re.IGNORECASE)
        return polished

    def _normalize_professional_german(self, text: str) -> str:
        subs = {
            "grosses Interesse":              "großes Interesse",
            "grossem Interesse":              "großem Interesse",
            "grossen Interesse":              "großen Interesse",
            "Gruesse":                        "Grüße",
            "Mit freundlichen Gruessen":      "Mit freundlichen Grüßen",
            "persoenlichen Gespraech":        "persönlichen Gespräch",
            "persoenliches Gespraech":        "persönliches Gespräch",
            "zuverlaessig":                   "zuverlässig",
            "sorgfaeltig":                    "sorgfältig",
            "taetig":                         "tätig",
            "moechte":                        "möchte",
            "koennte":                        "könnte",
            "Ueber eine Einladung":           "Über eine Einladung",
        }
        normalized = text
        for old, new in subs.items():
            normalized = re.sub(re.escape(old), new, normalized, flags=re.IGNORECASE)
        return normalized

    def _looks_like_letter(self, text: str) -> bool:
        lower = text.lower()
        return "bewerbung" in lower and "mit freundlichen" in lower

    def _salutation(self, contact_person: str | None) -> str:
        name = (contact_person or "").strip()
        name = re.sub(r"[,;:]", " ", name)
        words = [w for w in name.split() if w.strip()]
        if not words:
            return "Sehr geehrte Damen und Herren,"
            
        junk = {"für", "bei", "an", "die", "der", "das", "und", "oder", "gmbh", "ag", "kg", "co", "team", "abteilung", "personal", "konzeption", "zuschläge", "zuschlaege", "streitschlichtung", "gerichtsstand", "sozialagentur", "produkte", "impressum", "datenschutz"}
        clean_words = []
        for w in words:
            if w.lower() in junk: break
            clean_words.append(w)
            
        if not clean_words:
            return "Sehr geehrte Damen und Herren,"
            
        titles = {"herr", "frau", "dr", "dr.", "prof", "prof.", "med", "med.", "mr", "mr.", "ms", "ms.", "mrs", "mrs."}
        non_title_count = 0
        final_words = []
        for w in clean_words:
            if w.lower() in {"herr", "frau", "mr", "ms", "mrs"} and non_title_count > 0:
                break
            final_words.append(w)
            if w.lower() not in titles:
                non_title_count += 1
            if non_title_count >= 2:
                break
                
        if all(w.lower() in titles for w in final_words):
            return "Sehr geehrte Damen und Herren,"
            
        clean_name = " ".join(final_words).strip()
        first = final_words[0].lower()
        
        if first in {"frau", "ms", "mrs"}:
            clean = re.sub(r"^(frau|ms|mrs)\s+", "", clean_name, flags=re.IGNORECASE).strip()
            return f"Sehr geehrte Frau {clean}," if clean else "Sehr geehrte Damen und Herren,"
        if first in {"herr", "mr"}:
            clean = re.sub(r"^(herr|mr)\s+", "", clean_name, flags=re.IGNORECASE).strip()
            return f"Sehr geehrter Herr {clean}," if clean else "Sehr geehrte Damen und Herren,"
            
        return f"Guten Tag {clean_name},"

    def _german_date(self) -> str:
        today = date.today()
        return f"{today.day:02d}. {GERMAN_MONTHS[today.month - 1]} {today.year}"

    # ─────────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _copy_letter(self):
        if not self._selected_record:
            return
        QGuiApplication.clipboard().setText(self._editor.toPlainText())
        self._show_success("Copied", "Letter copied to clipboard.")

    def _export_letter(self):
        if not self._selected_record:
            return
        filename = self._letter_filename(self._selected_record, ".txt")
        path, _   = QFileDialog.getSaveFileName(
            self, "Export Anschreiben", filename, "Text Files (*.txt)"
        )
        if not path:
            return
        Path(path).write_text(self._editor.toPlainText(), encoding="utf-8")
        self._show_success("Exported", Path(path).name)

    def _export_docx(self):
        if not self._selected_record:
            return
        try:
            from docx import Document
            from docx.shared import Pt, Cm
        except ImportError:
            self._show_error(
                "python-docx missing",
                "Install it with:  pip install python-docx",
            )
            return

        filename = self._letter_filename(self._selected_record, ".docx")
        path, _   = QFileDialog.getSaveFileName(
            self, "Export as Word Document", filename, "Word Documents (*.docx)"
        )
        if not path:
            return

        doc = Document()
        for section in doc.sections:
            section.top_margin    = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin   = Cm(2.5)
            section.right_margin  = Cm(2.5)

        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        for line in self._editor.toPlainText().split("\n"):
            p   = doc.add_paragraph()
            run = p.add_run(line)
            run.font.name = "Calibri"
            run.font.size = Pt(11)
            p.paragraph_format.space_after  = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            # bold the Betreff line
            if ("Bewerbung" in line or "Betreff" in line) and 10 < len(line.strip()) < 120:
                run.bold = True

        doc.save(path)
        self._show_success("Exported .docx", Path(path).name)

    def _show_import_menu(self):
        from qfluentwidgets import Action
        from PySide6.QtCore import QPoint
        from src.ui.components import GlassMenu
        menu = GlassMenu(parent=self)
        
        action_all = Action(FluentIcon.DOWNLOAD, "Import All Results", self)
        action_all.triggered.connect(lambda: self._do_import("all"))
        menu.addAction(action_all)
        
        menu.addSeparator()
        
        action_ausbildung = Action(FluentIcon.EDUCATION, "From Ausbildung", self)
        action_ausbildung.triggered.connect(lambda: self._do_import("ausbildung"))
        menu.addAction(action_ausbildung)
        
        action_aubi = Action(FluentIcon.EDUCATION, "From AubiPlus", self)
        action_aubi.triggered.connect(lambda: self._do_import("aubi"))
        menu.addAction(action_aubi)
        
        action_jobsuche = Action(FluentIcon.SEARCH, "From Jobsuche", self)
        action_jobsuche.triggered.connect(lambda: self._do_import("jobsuche"))
        menu.addAction(action_jobsuche)
        
        action_dasoertliche = Action(FluentIcon.SEARCH, "From Das Oertliche", self)
        action_dasoertliche.triggered.connect(lambda: self._do_import("dasoertliche"))
        menu.addAction(action_dasoertliche)
        
        action_azubiyo = Action(FluentIcon.PEOPLE, "From Azubiyo", self)
        action_azubiyo.triggered.connect(lambda: self._do_import("azubiyo"))
        menu.addAction(action_azubiyo)
        
        action_maps = Action(FluentIcon.PIN, "From Google Maps", self)
        action_maps.triggered.connect(lambda: self._do_import("maps"))
        menu.addAction(action_maps)
        
        menu.addSeparator()
        
        action_city = Action(FluentIcon.MARKET, "From Latest City", self)
        action_city.triggered.connect(lambda: self._do_import("city"))
        menu.addAction(action_city)
        
        menu.addSeparator()
        
        action_latest = Action(FluentIcon.SYNC, "From Latest Search", self)
        action_latest.triggered.connect(lambda: self._do_import("latest"))
        menu.addAction(action_latest)
        
        action_last_hour = Action(FluentIcon.HISTORY, "Last Hour", self)
        action_last_hour.triggered.connect(lambda: self._do_import("last_hour"))
        menu.addAction(action_last_hour)
        
        pos = self._btn_sync_leads.mapToGlobal(QPoint(0, self._btn_sync_leads.height() + 6))
        menu.exec(pos)

    def _do_import(self, filter_type: str):
        from src.services.orchestrator import orchestrator
        all_records = orchestrator.get_app_memory_records()
        
        filtered = []
        if filter_type == "all":
            filtered = all_records
        elif filter_type == "maps":
            filtered = [r for r in all_records if r.source_type and "maps" in str(r.source_type).lower()]
        elif filter_type == "jobsuche":
            filtered = [r for r in all_records if r.source_type and "jobsuche" in str(r.source_type).lower()]
        elif filter_type == "dasoertliche":
            filtered = [r for r in all_records if r.source_type and "dasoertliche" in str(r.source_type).lower()]
        elif filter_type == "ausbildung":
            filtered = [r for r in all_records if r.source_type and "ausbildung" in str(r.source_type).lower()]
        elif filter_type == "aubi":
            filtered = [r for r in all_records if r.source_type and "aubi" in str(r.source_type).lower()]
        elif filter_type == "azubiyo":
            filtered = [r for r in all_records if r.source_type and "azubiyo" in str(r.source_type).lower()]
        elif filter_type == "city":
            target_city = ""
            if orchestrator.current_job and orchestrator.current_job.config and orchestrator.current_job.config.city:
                target_city = orchestrator.current_job.config.city.strip()
            if not target_city and config_manager.settings.last_search_city:
                target_city = config_manager.settings.last_search_city.strip()
            
            if not target_city and all_records:
                sorted_records = sorted(all_records, key=lambda r: r.scraped_at)
                for r in reversed(sorted_records):
                    if r.city:
                        target_city = r.city.strip()
                        break

            if target_city and all_records:
                target_lower = target_city.lower()
                def _matches_city(r) -> bool:
                    r_city = (r.city or "").strip().lower()
                    r_query = (r.search_query or "").strip().lower()
                    r_addr = (r.address or "").strip().lower()
                    if r_city and (r_city == target_lower or target_lower in r_city or r_city in target_lower):
                        return True
                    if r_query and target_lower in r_query:
                        return True
                    if r_addr and target_lower in r_addr:
                        return True
                    return False

                filtered = [r for r in all_records if _matches_city(r)]
                if not filtered:
                    filtered = [r for r in all_records if r.city and r.city.lower() == target_lower]
        elif filter_type == "latest":
            if orchestrator.current_job and orchestrator.current_job.results:
                filtered = orchestrator.current_job.results
            elif all_records:
                # Fallback if no active job (e.g. app restarted)
                sorted_records = sorted(all_records, key=lambda r: r.scraped_at)
                latest_query = sorted_records[-1].search_query
                latest_source = sorted_records[-1].source_url
                if latest_query:
                    filtered = [r for r in sorted_records if r.search_query == latest_query]
                elif latest_source:
                    filtered = [r for r in sorted_records if r.source_url == latest_source]
                else:
                    filtered = sorted_records[-50:]
        elif filter_type == "last_hour":
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for r in all_records:
                try:
                    dt = r.scraped_at
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now - dt).total_seconds() <= 3600:
                        filtered.append(r)
                except: pass
                
        seen_emails = set()
        unique_filtered = []
        for r in filtered:
            if not r.email or not _is_valid_email(r.email):
                continue
            ekey = r.email.strip().lower()
            if ekey in seen_emails:
                continue
            seen_emails.add(ekey)
            unique_filtered.append(r)
        filtered = unique_filtered
        if not filtered:
            self._show_error("Import Failed", "No leads with useful emails match the selected criteria.")
            return
            
        def _persist():
            from src.core.config import get_memory_db_path
            from src.core.models import ScrapingJob, SearchConfig, ScrapingStatus
            from src.services.export_service import ExportService
            import sqlite3
            
            db_path = str(get_memory_db_path())
            dummy_job = ScrapingJob(config=SearchConfig(), results=filtered, status=ScrapingStatus.COMPLETED)
            ExportService().save_project(dummy_job, db_path)
            
            conn = sqlite3.connect(db_path, timeout=10.0)
            try:
                import dataclasses
                records_ids = [dataclasses.replace(r).normalize().stable_id() for r in filtered]
                for chunk in [records_ids[i:i + 500] for i in range(0, len(records_ids), 500)]:
                    placeholders = ",".join("?" * len(chunk))
                    conn.execute(f"UPDATE letter_state SET is_discarded = 0 WHERE lead_id IN ({placeholders})", chunk)
                conn.commit()
            finally:
                conn.close()

        def _on_persist_done(*args):
            self.refresh()
            self._show_success("Imported", f"{len(filtered)} search results have been imported.")

        from src.utils.db_worker import run_in_thread
        run_in_thread(
            _persist,
            on_finished=_on_persist_done
        )

    def _batch_export(self):
        """Export letters for all currently visible (filtered) leads."""
        if not self._pending_lead_records:
            self._show_error("Nothing to export", "No leads match current filter.")
            return

        folder = QFileDialog.getExistingDirectory(
            self, "Choose export folder", ""
        )
        if not folder:
            return

        folder_path = Path(folder)
        count       = 0
        for record in self._pending_lead_records:
            state = self._states.get(record.id, LetterState())
            text  = state.letter_text or self._assemble_letter(record)
            fname = self._letter_filename(record, ".txt")
            (folder_path / fname).write_text(text, encoding="utf-8")
            count += 1

        self._show_success("Batch Export", f"{count} letters saved to {folder_path.name}/")



    def _toggle_preview(self):
        pass

    def _revert_to_previous(self):
        if not self._selected_record:
            return
        state = self._states.get(self._selected_record.id)
        if not state or not state.previous_text:
            self._show_error("No previous version", "Nothing to revert to.")
            return
        dialog = AppleConfirmDialog(
            "Revert",
            "Replace current letter with the previous saved version?",
            "REVERT",
            "#FF453A",
            self.window()
        )
        if not dialog.exec():
            return
        self._set_editor_text(state.previous_text)
        state.letter_text  = state.previous_text
        state.previous_text = ""
        self._set_undo_ver_enabled(False)
        self._show_success("Reverted", "Previous version restored.")

    def _polish_current_letter(self):
        if not self._selected_record:
            return
        sender = self._load_sender_settings()
        replacements = {
            "ANREDE": self._salutation(self._selected_record.contact_person),
            "FIRMA":  self._selected_record.company_name or "Unternehmen",
            "ORT":    __import__("re").sub(r"^\d+\s*", "", str(sender.get("city") or "")).strip(),
            "PLZ":    self._selected_record.postal_code or "",
            "BERUF":  sender.get("beruf") or self._selected_record.job_title or self._selected_record.category or "Ausbildung",
            "DATUM":  self._german_date(),
        }
        polished = self._polish_letter(self._editor.toPlainText(), replacements)
        self._set_editor_text(polished)
        state = self._states.setdefault(self._selected_record.id, LetterState())
        state.edited_at   = datetime.utcnow().isoformat()
        state.letter_text = polished
        self._set_status(self._selected_record, state)
        self._persist_state_async(
            self._selected_record.id,
            edited_at=state.edited_at,
            letter_text=polished,
        )
        self._check_placeholders()
        self._show_success("Polished", "Letter wording has been refined.")

    def _action_regenerate_all_letters(self):
        w = AppleConfirmDialog(
            "Regenerate All",
            "Are you sure you want to regenerate all visible letters? Any manual edits will be overwritten.",
            confirm_text="Regenerate",
            confirm_color="#0A84FF",
            parent=self
        )
        if w.exec() != QDialog.Accepted:
            return
            
        # Force reload template in case the user edited the file manually
        self._template_text = self._load_template()
        self._template_status.setText(self._template_status_text())
            
        total = len(self._pending_lead_records)
        import sqlite3
        from ..core.config import get_memory_db_path
        try:
            conn = sqlite3.connect(str(get_memory_db_path()), timeout=10.0)
            for record in self._pending_lead_records:
                text = self._assemble_letter(record)
                state = self._states.setdefault(record.id, LetterState())
                state.letter_text = text
                state.edited_at   = ""
                conn.execute(
                    "INSERT INTO letter_state (lead_id, letter_text, edited_at, is_discarded) VALUES (?, ?, '', 0) "
                    "ON CONFLICT(lead_id) DO UPDATE SET letter_text=excluded.letter_text, edited_at='', is_discarded=0",
                    (record.id, text)
                )
            conn.commit()
            conn.close()
            
            if self._selected_record:
                self._regenerate_current_letter()
            
            self._show_success("Success", f"Regenerated {total} letters.")
            
            from ..core.events import event_bus, EventBus
            event_bus.emit(EventBus.DB_UPDATED, records=[])
        except Exception as e:
            self._show_error("Error", f"Failed to regenerate all: {e}")

    def _regenerate_current_letter(self):
        if not self._selected_record:
            return
        
        # Force reload template in case the user edited the file manually
        self._template_text = self._load_template()
        self._template_status.setText(self._template_status_text())

        text = self._assemble_letter(self._selected_record)
        self._rendered_text = text
        self._set_editor_text(text)
        state = self._states.setdefault(self._selected_record.id, LetterState())
        state.letter_text = text
        state.edited_at   = ""
        self._set_status(self._selected_record, state)
        self._persist_state_async(self._selected_record.id, letter_text=text)
        self._check_placeholders()

    # ─────────────────────────────────────────────────────────────────────────
    # Template management
    # ─────────────────────────────────────────────────────────────────────────



    def _insert_placeholder(self, placeholder: str):
        self._editor.setFocus()
        self._editor.textCursor().insertText(placeholder)

    def _edit_template(self):
        self._is_template_mode = True
        self._left_panel_widget.setDisabled(True)
        self._center_header_stack.setCurrentIndex(1)
        self._right_panel_stack.setCurrentIndex(1)
        
        self._load_template_into_editor()

    def _load_template_into_editor(self):
        from PySide6.QtGui import QTextCursor
        
        template_text = self._template_text or self._load_template()
        
        self._editor.blockSignals(True)
        self._editor.setPlainText(template_text)
        
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self._editor.setTextCursor(cursor)
        self._editor.blockSignals(False)

    def _get_template_text_from_editor(self):
        return self._editor.toPlainText()

    def _cancel_template_mode(self):
        self._exit_template_mode()

    def _save_template_mode(self):
        text = self._get_template_text_from_editor()
        self._save_template(text)
        self._show_success("Template Saved", "Regenerating selected lead.")
        self._exit_template_mode()
        if self._selected_record:
            self._regenerate_current_letter()

    def _exit_template_mode(self):
        self._is_template_mode = False
        self._left_panel_widget.setDisabled(False)
        self._center_header_stack.setCurrentIndex(0)
        self._right_panel_stack.setCurrentIndex(0)
        
        # Block _render_record from autosaving the template text into the current lead
        self._loading_text = True
        try:
            if self._lead_list.currentItem():
                self._on_lead_clicked(self._lead_list.currentItem())
            else:
                self._editor.clear()
        finally:
            self._loading_text = False

    def _load_template(self) -> str:
        if self._template_path.exists():
            return self._template_path.read_text(encoding="utf-8")
        return (
            "{{SENDER_NAME}}\n{{SENDER_ADDRESS}}\n{{SENDER_CITY}}\n"
            "{{SENDER_PHONE}} · {{SENDER_EMAIL}}\n\n"
            "{{FIRMA}}\n{{PLZ}} {{ORT}}\n\n"
            "{{DATUM}}\n\n"
            "Bewerbung um einen Ausbildungsplatz als {{BERUF}}\n\n"
            "{{ANREDE}}\n\n"
            "[ Hier deinen Bewerbungstext einfügen... ]\n\n"
            "Mit freundlichen Grüßen"
        )

    def _save_template(self, text: str):
        self._template_path.parent.mkdir(parents=True, exist_ok=True)
        self._template_path.write_text(text.strip() + "\n", encoding="utf-8")
        self._template_text = text.strip() + "\n"
        self._template_status.setText(self._template_status_text())

    def _template_status_text(self) -> str:
        if self._template_path.exists():
            return f"Using: {self._template_path.name}"
        return "Using: built-in default"

    # ─────────────────────────────────────────────────────────────────────────
    # Persistence helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _mark_generated_async(self, lead_id: str, text: str):
        now   = datetime.utcnow().isoformat()
        state = self._states.setdefault(lead_id, LetterState())
        state.generated_at = now
        state.letter_text  = text
        self._persist_state_async(lead_id, generated_at=now, letter_text=text)
        self._refresh_selected_lead_row()

    def _refresh_selected_lead_row(self):
        if not self._selected_record:
            return
        for row in range(self._lead_list.count()):
            item = self._lead_list.item(row)
            if item.data(Qt.UserRole) != self._selected_record.id:
                continue
            replacement = LeadRowWidget(
                self._selected_record,
                self._states.get(self._selected_record.id),
            )
            replacement.set_selected(True)
            self._lead_list.setItemWidget(item, replacement)
            self._selected_row_widget = replacement
            break

    def _persist_state_async(
        self,
        lead_id: str,
        *,
        generated_at:  str | None = None,
        edited_at:     str | None = None,
        sent_at:       str | None = None,
        letter_text:   str | None = None,
        previous_text: str | None = None,
        last_saved_ts: str | None = None,
    ):
        run_in_thread(
            self._persist_state,
            lead_id,
            generated_at,
            edited_at,
            sent_at,
            letter_text,
            previous_text,
            last_saved_ts,
            on_error=lambda tb: self._show_error(
                "Save failed", tb.splitlines()[-1] if tb else "Unknown error"
            ),
        )

    def _persist_state(
        self,
        lead_id:       str,
        generated_at:  str | None,
        edited_at:     str | None,
        sent_at:       str | None,
        letter_text:   str | None,
        previous_text: str | None,
        last_saved_ts: str | None,
    ):
        db_path = get_memory_db_path()
        conn    = sqlite3.connect(db_path, timeout=30.0)
        try:
            self._ensure_letter_state_table(conn)
            existing = conn.execute(
                "SELECT generated_at, edited_at, sent_at, letter_text, "
                "previous_text, last_saved_ts, is_discarded FROM letter_state WHERE lead_id=?",
                (lead_id,),
            ).fetchone()
            cur = LetterState(*(existing or ("", "", "", "", "", "", 0)))
            final = LetterState(
                generated_at  or cur.generated_at,
                edited_at     or cur.edited_at,
                sent_at       or cur.sent_at,
                letter_text   if letter_text   is not None else cur.letter_text,
                previous_text if previous_text is not None else cur.previous_text,
                last_saved_ts if last_saved_ts is not None else cur.last_saved_ts,
                cur.is_discarded,
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO letter_state
                  (lead_id, generated_at, edited_at, sent_at,
                   letter_text, previous_text, last_saved_ts, is_discarded)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    lead_id,
                    final.generated_at, final.edited_at, final.sent_at,
                    final.letter_text,  final.previous_text, final.last_saved_ts,
                    final.is_discarded,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # UI helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _letter_filename(self, record: LeadRecord, ext: str = ".txt") -> str:
        company = re.sub(
            r"[^A-Za-z0-9ÄÖÜäöüß_-]+", "_", record.company_name or "Firma"
        ).strip("_")
        stamp = date.today().strftime("%Y-%m-%d")
        return f"{company}_{stamp}{ext}"

    def _set_actions_enabled(self, enabled: bool):
        for btn in (
            self._btn_copy, self._btn_polish,
            self._btn_export,
            self._btn_undo_ver,
        ):
            btn.setEnabled(enabled)

    def _set_status(self, record: LeadRecord, state: LetterState):
        has_sent = bool(state.sent_at)

    def _update_lead_summary(self, record: LeadRecord):
        self._center_company.setText(record.company_name or "Unknown company")
        self._center_hr.setText(record.contact_person or "No HR contact")
        self._center_job.setText(record.job_title or record.category or "—")
        loc = " ".join(filter(None, [record.postal_code, record.city]))
        self._center_city.setText(loc or "No location")
        # keep legacy reference consistent
        self._lead_summary = self._center_company
        self._status = self._center_company

    # ─────────────────────────────────────────────────────────────────────────
    # Style factories
    # ─────────────────────────────────────────────────────────────────────────

    def _info_row_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #8E8E93; font-size: 10px; background: transparent; border: none;"
        )
        return lbl

    def _panel(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        return f

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #6E6E73; font-family: system-ui, -apple-system, sans-serif; "
            "font-size: 10px; font-weight: 400; letter-spacing: 0.06em; "
            "background: transparent; border: none;"
        )
        return lbl

    def _status_chip(self, text: str, color: str) -> QLabel:
        chip = QLabel(text)
        chip.setAlignment(Qt.AlignCenter)
        chip.setFixedHeight(20)
        bg = "rgba(48,209,88,0.18)" if color.lower() == "#30d158" else "rgba(10,132,255,0.18)"
        chip.setStyleSheet(
            f"color: {color}; background: {bg};"
            " border: none; border-radius: 5px;"
            " font-family: system-ui, -apple-system, sans-serif; font-size: 10px;"
            " font-weight: 500; padding: 0 7px;"
        )
        return chip

    def _pill_style(self, color: str) -> str:
        return (
            f"color: {color}; background: rgba(10,132,255,0.10); "
            f"border: 1px solid {color}; border-radius: 7px; "
            "font-family: system-ui, -apple-system, sans-serif; font-size: 10px; "
            "font-weight: 500; padding: 3px 8px;"
        )

    def _button(self, text: str, primary: bool = False) -> PushButton:
        btn = PushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            Theme.zugzwang_primary_button() if primary else Theme.zugzwang_button()
        )
        return btn

    def _small_button(self, text: str, primary: bool = False) -> PushButton:
        btn = PushButton(text)
        btn.setFixedHeight(30)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            Theme.zugzwang_primary_button() if primary else Theme.zugzwang_button()
        )
        return btn

    def _toolbar_button(self, text: str, color: str, tooltip: str, compact: bool = False) -> PushButton:
        btn = PushButton(text)
        size = 34 if compact else 42
        btn.setFixedSize(size, 34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 9px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 500;
                padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.12);
                border-color: {color};
                color: {color};
            }}
            QPushButton:pressed {{
                background: rgba(255,255,255,0.06);
            }}
            QPushButton:disabled {{
                background: rgba(255,255,255,0.06);
                border-color: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.3);
            }}
        """)
        return btn

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.06); border: none;")
        return line

    def _action_group(self, label: str) -> tuple:
        """Return (card QFrame, inner QVBoxLayout). Add _action_row widgets to the layout."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)
        
        # Add spacing before section label
        vbox.addSpacing(20)
        
        lbl = QLabel(label)
        lbl.setFixedHeight(24)
        lbl.setStyleSheet("""
            color: #444444;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 9px;
            font-weight: 500;
            letter-spacing: 0.12em;
            background: transparent;
            border: none;
            border-bottom: 1px solid #1c1c1c;
            margin-bottom: 8px;
        """)
        vbox.addWidget(lbl)
        return card, vbox

    def _add_hairline(self, layout: QVBoxLayout):
        layout.addSpacing(4)

    def _set_undo_ver_enabled(self, enabled: bool):
        self._btn_undo_ver.setEnabled(enabled)
        if hasattr(self, "_btn_undo_ver_opacity"):
            self._btn_undo_ver_opacity.setOpacity(1.0 if enabled else 0.4)

    def _action_row(
        self,
        icon_name: str,
        text: str,
        style: str = "normal",   # normal | primary | danger
        icon_color: str | None = None,
        text_color: str | None = None,
        shortcut: str = "",
    ) -> QPushButton:
        """Full-width flat action row styled like the HTML mockup."""
        btn = QPushButton()
        btn.setFixedHeight(27)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)

        if style == "danger" or "CLEAR" in text.upper():
            display_color = "#e05555"
            border_color = "#2a1414"
            hover_bg = "#3a1a1a"
            hover_border = "#4a1c1c"
            hover_fg = "#ff6b6b"
            bg = "#1a0c0c"
        else:
            display_color = text_color if text_color else "#AFAFAF"
            border_color = "#3A3A3C"
            hover_bg = "#48484A"
            hover_border = "#5C5C5E"
            hover_fg = "#FFFFFF"
            bg = "#2C2C2E"

        ico_col = icon_color if icon_color else display_color
        btn.setIcon(_render_tinted_icon(icon_name, 12, ico_col))
        btn.setIconSize(QSize(12, 12))
        btn.setText(text)

        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {display_color};
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 500;
                padding-left: 8px;
                padding-right: 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                border-color: {hover_border};
                color: {hover_fg};
            }}
            QPushButton:pressed {{
                background: #1C1C1E;
            }}
            QPushButton:disabled {{
                background: transparent;
                color: #444444;
                border-color: #222222;
            }}
        """)
        return btn

    def _ghost_action_style(self, active: bool = False) -> str:
        if active:
            return """
                QPushButton {
                    background: #0A84FF;
                    border: none;
                    border-radius: 7px;
                    color: #FFFFFF;
                    font-family: system-ui, -apple-system, sans-serif;
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover { background: #1A8FFF; }
            """
        else:
            return """
                QPushButton {
                    background: #3A3A3C;
                    border: none;
                    border-radius: 7px;
                    color: #E5E5EA;
                    font-family: system-ui, -apple-system, sans-serif;
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover { background: #48484A; }
            """

    def _mappe_btn(
        self,
        icon_name: str,
        bg_color: str,
        tooltip: str,
        border: bool = False,
        icon_color: str = "#FFFFFF",
    ) -> QPushButton:
        return MappeButton(icon_name, tooltip, self)

    def _square_icon_button(self, text: str, color: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(44, 44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        border = color
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border: 1px solid {border};
                border-radius: 9px;
                color: #FFFFFF;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 25px;
                font-weight: 400;
                padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.12);
                border-color: rgba(255,255,255,0.18);
            }}
            QPushButton:pressed {{
                background: rgba(255,255,255,0.08);
            }}
            QPushButton:disabled {{
                background: #2C2C2E;
                border-color: #3A3A3C;
                color: #636366;
            }}
        """)
        return btn

    def _input_style(self) -> str:
        return """
            LineEdit, QLineEdit {
                background: #1C1C1E;
                border: 1px solid #3A3A3C;
                border-radius: 8px;
                color: #F2F2F7;
                padding: 0 10px;
            }
            LineEdit:focus, QLineEdit:focus { border-color: #0A84FF; }
        """

    def _list_style(self) -> str:
        return """
            QListWidget {
                background: transparent;
                border: none;
                color: #F2F2F7;
                outline: none;
                padding: 0;
            }
            QListWidget::item:selected { background: transparent; }
        """

    def _editor_style(self, preview: bool = False) -> str:
        return """
            QTextEdit {
                background: #0d0d0d;
                border: none;
                color: #c8c8c8;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 13px;
            }
        """

    def _filter_btn_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton { "
                "background: #FFFFFF; border: none; border-radius: 7px; "
                "color: #1C1C1E; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 500; "
                "}"
            )
        return (
            "QPushButton { background: transparent; border: none; border-radius: 6px; "
            "color: #8E8E93; font-family: system-ui, -apple-system, sans-serif; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { color: #F2F2F7; background: rgba(255,255,255,0.05); }"
        )

    def _toggle_btn_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #0A84FF; "
                "border: 1px solid #0A84FF; border-radius: 8px; "
                "color: #FFFFFF; font-family: system-ui, -apple-system, sans-serif; "
                "font-size: 11px; font-weight: 500; }"
            )
        return (
            "QPushButton { background: rgba(255,255,255,0.04); "
            "border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; "
            "color: #AEAEB2; font-family: system-ui, -apple-system, sans-serif; "
            "font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); color: #F2F2F7; }"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────────────────────────────────────

    def _show_success(self, title: str, message: str):
        ToastNotification.success(title, message, duration=2500, parent=self)

    def _show_error(self, title: str, message: str):
        ToastNotification.error(title, message, duration=5000, parent=self)

    # ─────────────────────────────────────────────────────────────────────────
    # Bewerbungsmappe PDF Export Feature
    # ─────────────────────────────────────────────────────────────────────────

    def _build_bewerbungsmappe_section(self, layout: QVBoxLayout) -> None:
        # Outer card identical to other action-group cards
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #1C1C1E; border: 1px solid rgba(255,255,255,0.07);"
            " border-radius: 9px; }"
        )
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(6)

        lbl = QLabel(tr("BEWERBUNGSMAPPE", get_language(config_manager.settings.app_language)))
        lbl.setStyleSheet(
            "color: #3A3A3C; font-family: system-ui, -apple-system, sans-serif; font-size: 9px; font-weight: 500; letter-spacing: 0.1em;"
            " background: transparent; border: none;"
        )
        vbox.addWidget(lbl)

        # ── Drop zone (shown when no PDF loaded) ─────────────────────────────
        self._drop_zone = PDFDropZone(self)
        self._drop_zone.setFixedHeight(64)
        self._drop_zone.file_dropped.connect(self._on_pdf_dropped)
        self._drop_zone.clicked.connect(self._on_pdf_browse)
        vbox.addWidget(self._drop_zone)

        # ── Loaded state (shown after PDF upload) ─────────────────────────────
        self._file_info_widget = QFrame()
        self._file_info_widget.setStyleSheet(
            "QFrame { background: rgba(48,209,88,0.06); border: 1px solid rgba(48,209,88,0.2);"
            " border-radius: 8px; }"
        )
        self._file_info_widget.setVisible(False)
        fi_row = QHBoxLayout(self._file_info_widget)
        fi_row.setContentsMargins(8, 7, 8, 7)
        fi_row.setSpacing(7)

        pdf_icon = QLabel(tr("📄", get_language(config_manager.settings.app_language)))
        pdf_icon.setStyleSheet("color: #30D158; font-size: 14px; background: transparent; border: none;")
        fi_row.addWidget(pdf_icon)

        fi_text = QVBoxLayout()
        fi_text.setSpacing(1)
        self._file_info_label = QLabel("")
        self._file_info_label.setStyleSheet(
            "color: #E5E5EA; font-family: system-ui, -apple-system, sans-serif; font-size: 10px; font-weight: 500; background: transparent; border: none;"
        )
        self._detection_status_label = QLabel("")
        self._detection_status_label.setStyleSheet(
            "color: #48484A; font-family: system-ui, -apple-system, sans-serif; font-size: 9px; background: transparent; border: none;"
        )
        fi_text.addWidget(self._file_info_label)
        fi_text.addWidget(self._detection_status_label)
        fi_row.addLayout(fi_text, 1)

        self._btn_clear = PushButton(tr("✕", get_language(config_manager.settings.app_language)))
        self._btn_clear.setFixedSize(20, 20)
        self._btn_clear.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #636366; font-size: 11px; }"
            "QPushButton:hover { color: #FF453A; }"
        )
        self._btn_clear.clicked.connect(self._clear_bewerbung_pdf)
        fi_row.addWidget(self._btn_clear, 0, Qt.AlignVCenter)

        vbox.addWidget(self._file_info_widget)

        # ── Export single PDF ─────────────────────────────────────────────────
        self._btn_export_pdf = PushButton(tr("Export PDF  →", get_language(config_manager.settings.app_language)))
        self._btn_export_pdf.setFixedHeight(32)
        self._btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self._btn_export_pdf.setStyleSheet("""
            QPushButton {
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 8px;
                color: #30D158;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 10px; font-weight: 500;
                letter-spacing: 0.04em;
            }
            QPushButton:hover { background: rgba(48,209,88,0.18); }
        """)
        self._btn_export_pdf.clicked.connect(self._action_export_bewerbungsmappe)
        vbox.addWidget(self._btn_export_pdf)

        # ── Batch export row ──────────────────────────────────────────────────
        self._btn_export_batch_pdf = PushButton(tr("Batch export all visible  →", get_language(config_manager.settings.app_language)))
        self._btn_export_batch_pdf.setFixedHeight(28)
        self._btn_export_batch_pdf.setCursor(Qt.PointingHandCursor)
        self._btn_export_batch_pdf.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 7px;
                color: #636366;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 9px; font-weight: 500;
                letter-spacing: 0.04em;
            }
            QPushButton:hover { border-color: rgba(255,255,255,0.18); color: #AEAEB2; }
        """)
        self._btn_export_batch_pdf.clicked.connect(self._action_export_bewerbungsmappe_batch)
        vbox.addWidget(self._btn_export_batch_pdf)

        layout.addWidget(card)


    # ── BEWERBUNG Card handlers ──────────────────────────────────────────

    def _get_doc_order(self) -> list[str]:
        """Return ordered list of document keys."""
        import json
        raw = getattr(config_manager.settings, "bewerbung_doc_order", "") or ""
        valid_keys = ["deckblatt", "anschreiben", "lebenslauf", "zeugnisse"]
        try:
            order = json.loads(raw) if raw else []
            order = [k for k in order if k in valid_keys]
            for k in valid_keys:
                if k not in order:
                    order.append(k)
            return order
        except Exception:
            return ["deckblatt", "anschreiben", "lebenslauf", "zeugnisse"]

    def _save_doc_order(self, order: list[str]) -> None:
        import json
        config_manager.settings.bewerbung_doc_order = json.dumps(order)
        config_manager.save()

    def _on_doc_reordered(self, src_key: str, target_key: str) -> None:
        if src_key == target_key:
            return
        order = self._get_doc_order()
        if src_key in order and target_key in order:
            src_idx = order.index(src_key)
            target_idx = order.index(target_key)
            item = order.pop(src_idx)
            order.insert(target_idx, item)
            self._save_doc_order(order)
            self._refresh_doc_order_ui()
            self._refresh_bewerbung_export_btn()

    def _on_card_dragged(self, dragged_row: DocCardRow, global_y: int) -> None:
        if not hasattr(self, "_doc_card_rows") or dragged_row not in self._doc_card_rows:
            return
        dragged_idx = self._doc_card_rows.index(dragged_row)
        for i, row in enumerate(self._doc_card_rows):
            if row is dragged_row:
                continue
            r_rect = row.rect()
            top_y = row.mapToGlobal(r_rect.topLeft()).y()
            bottom_y = row.mapToGlobal(r_rect.bottomRight()).y()
            center_y = (top_y + bottom_y) // 2

            if i > dragged_idx and global_y > center_y:
                self._reorder_rows_in_place(dragged_idx, i)
                break
            elif i < dragged_idx and global_y < center_y:
                self._reorder_rows_in_place(dragged_idx, i)
                break

    def _reorder_rows_in_place(self, from_idx: int, to_idx: int) -> None:
        item = self._doc_card_rows.pop(from_idx)
        self._doc_card_rows.insert(to_idx, item)
        for idx, row in enumerate(self._doc_card_rows):
            self._doc_order_layout.removeWidget(row)
            self._doc_order_layout.addWidget(row)
            row.set_position_number(idx + 1)

    def _on_card_drag_finished(self) -> None:
        if not hasattr(self, "_doc_card_rows"):
            return
        new_order = [row.key for row in self._doc_card_rows]
        self._save_doc_order(new_order)
        self._refresh_bewerbung_export_btn()

    def _clear_deckblatt(self) -> None:
        config_manager.settings.bewerbung_deckblatt_path = ""
        config_manager.save()
        self._refresh_bewerbung_status_ui()

    def _clear_lebenslauf(self) -> None:
        config_manager.settings.bewerbung_lebenslauf_path = ""
        config_manager.save()
        self._refresh_bewerbung_status_ui()

    def _clear_zeugnisse(self) -> None:
        self._save_zeugnisse_paths([])
        self._refresh_bewerbung_status_ui()

    def _refresh_doc_order_ui(self) -> None:
        if not hasattr(self, "_doc_order_layout"):
            return
        while self._doc_order_layout.count():
            item = self._doc_order_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._doc_card_rows = []
        order = self._get_doc_order()
        db_path = getattr(config_manager.settings, "bewerbung_deckblatt_path", "") or ""
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        zeug_paths = self._get_zeugnisse_paths()

        has_db = bool(db_path and Path(db_path).exists())
        has_lv = bool(lv_path and Path(lv_path).exists())
        has_zeug = bool(zeug_paths)

        doc_meta = {
            "deckblatt": {
                "title": "Deckblatt",
                "sub": Path(db_path).name if has_db else "optional",
                "color": "#30D158" if has_db else "#8E8E93",
                "icon": FluentIcon.PHOTO,
                "action": self._on_deckblatt_browse,
                "has_file": has_db,
                "clear_fn": self._clear_deckblatt,
            },
            "anschreiben": {
                "title": "Anschreiben",
                "sub": "ready",
                "color": "#30D158",
                "icon": FluentIcon.DOCUMENT,
                "action": lambda: self._editor.setFocus() if hasattr(self, "_editor") else None,
                "has_file": False,
                "clear_fn": None,
            },
            "lebenslauf": {
                "title": "Lebenslauf",
                "sub": Path(lv_path).name if has_lv else "required",
                "color": "#30D158" if has_lv else "#FF9F0A",
                "icon": FluentIcon.PEOPLE,
                "action": self._on_lebenslauf_browse,
                "has_file": has_lv,
                "clear_fn": self._clear_lebenslauf,
            },
            "zeugnisse": {
                "title": "Zeugnisse",
                "sub": f"{len(zeug_paths)} file{'s' if len(zeug_paths) != 1 else ''}" if has_zeug else "optional",
                "color": "#30D158" if has_zeug else "#8E8E93",
                "icon": FluentIcon.FOLDER,
                "action": self._on_manage_zeugnisse,
                "has_file": has_zeug,
                "clear_fn": self._clear_zeugnisse,
            },
        }

        for idx, key in enumerate(order):
            meta = doc_meta.get(key, {"title": key, "sub": "", "color": "#8E8E93", "has_file": False, "icon": FluentIcon.DOCUMENT, "action": None, "clear_fn": None})
            row = DocCardRow(
                key=key,
                idx=idx,
                meta=meta,
                container=self,
                on_action=meta.get("action"),
                on_clear=meta.get("clear_fn"),
            )
            self._doc_card_rows.append(row)
            self._doc_order_layout.addWidget(row)

    def _get_zeugnisse_paths(self) -> list[str]:
        """Return the current ordered list of Zeugnisse PDF paths from settings."""
        import json
        raw = getattr(config_manager.settings, "bewerbung_zeugnisse_paths", "[]") or "[]"
        try:
            return json.loads(raw)
        except Exception:
            return []

    def _save_zeugnisse_paths(self, paths: list[str]) -> None:
        import json
        config_manager.settings.bewerbung_zeugnisse_paths = json.dumps(paths)
        config_manager.save()

    def _refresh_bewerbung_status_ui(self) -> None:
        """Update status pill, Deckblatt, Lebenslauf, Zeugnisse, and order list."""
        db_path = getattr(config_manager.settings, "bewerbung_deckblatt_path", "") or ""
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        zeug_paths = self._get_zeugnisse_paths()

        has_db = bool(db_path and Path(db_path).exists())
        has_lv = bool(lv_path and Path(lv_path).exists())
        has_zeug = bool(zeug_paths)

        if hasattr(self, "_db_status_lbl"):
            if has_db:
                self._db_status_lbl.setText(f"Deckblatt: {Path(db_path).name}")
                self._db_status_lbl.setStyleSheet("color: #30A46C; font-size: 11px; font-weight: 500; background: transparent; padding-left: 2px;")
            else:
                self._db_status_lbl.setText("Deckblatt: optional / not loaded")
                self._db_status_lbl.setStyleSheet("color: #6E6E73; font-size: 11px; font-weight: 400; background: transparent; padding-left: 2px;")

        if hasattr(self, "_lv_status_lbl"):
            if has_lv:
                self._lv_status_lbl.setText(f"Lebenslauf: {Path(lv_path).name}")
                self._lv_status_lbl.setStyleSheet("color: #30A46C; font-size: 11px; font-weight: 500; background: transparent; padding-left: 2px;")
            else:
                self._lv_status_lbl.setText("Lebenslauf: required / not loaded")
                self._lv_status_lbl.setStyleSheet("color: #FF9F0A; font-size: 11px; font-weight: 400; background: transparent; padding-left: 2px;")

        if hasattr(self, "_zeug_status_lbl"):
            if has_zeug:
                self._zeug_status_lbl.setText(f"Zeugnisse: {len(zeug_paths)} file{'s' if len(zeug_paths) != 1 else ''}")
                self._zeug_status_lbl.setStyleSheet("color: #30A46C; font-size: 11px; font-weight: 500; background: transparent; padding-left: 2px;")
            else:
                self._zeug_status_lbl.setText("Zeugnisse: 0 files (optional)")
                self._zeug_status_lbl.setStyleSheet("color: #6E6E73; font-size: 11px; font-weight: 400; background: transparent; padding-left: 2px;")

        if hasattr(self, "_bewerbung_status_label"):
            pill = self._bewerbung_status_label
            if has_lv:
                ready_count = 1 + (1 if has_db else 0) + (1 if has_zeug else 0)
                pill.setText(f"Ready ({ready_count}/3 files)")
                pill.setStyleSheet("""
                    QLabel {
                        background: rgba(48, 209, 88, 0.15);
                        border: 1px solid rgba(48, 209, 88, 0.28);
                        border-radius: 6px;
                        color: #30D158;
                        padding: 2px 8px;
                        font-family: 'PT Root UI', sans-serif;
                        font-size: 10px;
                        font-weight: 600;
                    }
                """)
            else:
                pill.setText("Needs CV")
                pill.setStyleSheet("""
                    QLabel {
                        background: rgba(255, 159, 10, 0.15);
                        border: 1px solid rgba(255, 159, 10, 0.28);
                        border-radius: 6px;
                        color: #FF9F0A;
                        padding: 2px 8px;
                        font-family: 'PT Root UI', sans-serif;
                        font-size: 10px;
                        font-weight: 600;
                    }
                """)

        self._refresh_doc_order_ui()
        self._refresh_bewerbung_export_btn()

    def _refresh_bewerbung_export_btn(self) -> None:
        """Enable export only when Lebenslauf is loaded (required for all modes)."""
        if not hasattr(self, "_btn_export"):
            return
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        has_lv = bool(lv_path and Path(lv_path).exists())
        self._btn_export.setEnabled(has_lv)

    def _on_deckblatt_browse(self) -> None:
        from PySide6.QtCore import QStandardPaths
        from PySide6.QtWidgets import QFileDialog
        start_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Select Deckblatt (Cover Sheet) PDF", start_dir, "PDF Files (*.pdf)")
        if path:
            config_manager.settings.bewerbung_deckblatt_path = path
            config_manager.save()
            self._refresh_bewerbung_status_ui()

    def _on_lebenslauf_browse(self) -> None:
        from PySide6.QtCore import QStandardPaths
        from PySide6.QtWidgets import QFileDialog
        start_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Select Lebenslauf (CV) PDF", start_dir, "PDF Files (*.pdf)")
        if path:
            config_manager.settings.bewerbung_lebenslauf_path = path
            config_manager.save()
            self._refresh_bewerbung_status_ui()

    def _on_manage_zeugnisse(self) -> None:
        dlg = ZeugisseManagerDialog(self._get_zeugnisse_paths(), self)
        if dlg.exec():
            self._save_zeugnisse_paths(dlg.get_paths())
            self._refresh_bewerbung_status_ui()

    def _clear_bewerbung_all(self) -> None:
        """Clear Deckblatt + Lebenslauf + Zeugnisse only (never touches Anschreiben card)."""
        config_manager.settings.bewerbung_deckblatt_path = ""
        config_manager.settings.bewerbung_lebenslauf_path = ""
        config_manager.settings.bewerbung_zeugnisse_paths = "[]"
        config_manager.save()
        self._refresh_bewerbung_status_ui()


    def _on_pdf_browse(self) -> None:
        start_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if not start_dir:
            start_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Bewerbung PDF",
            start_dir,
            "PDF Files (*.pdf)"
        )
        if path:
            self._load_bewerbung_pdf(Path(path))

    def _open_bewerbung_pdf(self) -> None:
        if not self._bewerbung_pdf_path:
            self._show_error("No PDF loaded", "Add a Bewerbung PDF first.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._bewerbung_pdf_path)))

    def _run_bewerbung_export(self) -> None:
        self._set_mappe_generating(True)
        try:
            self._action_export_bewerbungsmappe()
        finally:
            self._set_mappe_generating(False)

    def _set_mappe_generating(self, generating: bool) -> None:
        if not hasattr(self, "_btn_bewerbung_batch"):
            return
        icon_name = "pause.svg" if generating else "play.svg"
        self._btn_bewerbung_batch.setIcon(_render_tinted_icon(icon_name, 14, "#FFFFFF"))

    def _load_bewerbung_pdf(self, path: Path) -> None:
        if not path.exists():
            return
        
        self._bewerbung_pdf_path = path

        if hasattr(self, "_file_info_widget"):
            self._file_info_widget.setVisible(True)
        if hasattr(self, "_drop_zone"):
            self._drop_zone.setVisible(False)
        if hasattr(self, "_file_info_label"):
            self._file_info_label.setText(path.name)
        if hasattr(self, "_detection_status_label"):
            self._detection_status_label.setText("Analyzing PDF...")

        if hasattr(self, "_btn_view_mappe"):
            self._btn_view_mappe.setEnabled(False)
        if hasattr(self, "_btn_generate"):
            self._btn_generate.setEnabled(False)

        self._pdf_worker = PdfDetectWorker(path, self)
        self._pdf_worker.detection_done.connect(self._on_pdf_detected)
        self._pdf_worker.start()

    def _on_pdf_detected(self, num_pages: int, detected_idx: int, was_detected: bool, error_msg: str) -> None:
        if error_msg:
            self._clear_bewerbung_pdf()
            self._show_error("Error loading PDF", error_msg)
            return

        # self._bewerbung_anschreiben_page is now managed by the UI input and user's config
        
        if was_detected:
            status_text = f"{num_pages} pages · letter p.{detected_idx + 1}"
        else:
            status_text = f"{num_pages} pages · default p.{detected_idx + 1}"

        if hasattr(self, "_detection_status_label"):
            self._detection_status_label.setText(status_text)

        if hasattr(self, "_bewerbung_status_label"):
            self._update_pdf_status_ui(True)
            self._bewerbung_status_label.setToolTip(str(self._bewerbung_pdf_path))

        if hasattr(self, "_btn_view_mappe"):
            self._btn_view_mappe.setEnabled(True)
        if hasattr(self, "_btn_generate"):
            self._btn_generate.setEnabled(True)

        if self._bewerbung_pdf_path:
            self._save_persisted_pdf_path(str(self._bewerbung_pdf_path))

    def _update_pdf_status_ui(self, loaded: bool, building: bool = False) -> None:
        if not hasattr(self, "_bewerbung_status_label"):
            return
        
        if building:
            self._bewerbung_status_label.setText("Building…")
            self._bewerbung_status_label.setStyleSheet("""
                QLabel {
                    background: rgba(10, 132, 255, 0.15);
                    border: 1px solid rgba(10, 132, 255, 0.28);
                    border-radius: 6px;
                    color: #0A84FF;
                    padding: 2px 8px;
                    font-family: 'PT Root UI', sans-serif;
                    font-size: 10px;
                    font-weight: 600;
                }
            """)
        elif loaded:
            self._bewerbung_status_label.setText("PDF ready")
            self._bewerbung_status_label.setStyleSheet("""
                QLabel {
                    background: rgba(48, 209, 88, 0.15);
                    border: 1px solid rgba(48, 209, 88, 0.28);
                    border-radius: 6px;
                    color: #30D158;
                    padding: 2px 8px;
                    font-family: 'PT Root UI', sans-serif;
                    font-size: 10px;
                    font-weight: 600;
                }
            """)
        else:
            self._bewerbung_status_label.setText("No PDF")
            self._bewerbung_status_label.setStyleSheet("""
                QLabel {
                    background: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    color: #8E8E93;
                    padding: 2px 8px;
                    font-family: 'PT Root UI', sans-serif;
                    font-size: 10px;
                    font-weight: 500;
                }
            """)

    def _clear_bewerbung_pdf(self) -> None:
        self._bewerbung_pdf_path = None
        # Don't reset page when clearing PDF, keep user's preference
        
        if hasattr(self, "_bewerbung_status_label"):
            self._update_pdf_status_ui(False)
            self._bewerbung_status_label.setToolTip("")
            
        if hasattr(self, "_btn_view_mappe"):
            self._btn_view_mappe.setEnabled(False)
        if hasattr(self, "_btn_generate"):
            self._btn_generate.setEnabled(False)

        self._save_persisted_pdf_path("")

        # Delete any persisted raw uploaded copy or stale batch PDFs from exports dir
        try:
            from ..core.config import get_exports_dir
            out_dir = get_exports_dir()
            if out_dir.exists():
                raw_pdf = out_dir / "Bewerbung_Raw_Uploaded.pdf"
                if raw_pdf.exists():
                    raw_pdf.unlink(missing_ok=True)
                for p in out_dir.glob("Bewerbung als *.pdf"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def _save_anschreiben_page(self):
        try:
            val = int(self._page_input.text())
            if val < 1: val = 1
            config_manager.update(bewerbung_anschreiben_page=val)
            self._bewerbung_anschreiben_page = val - 1
        except ValueError:
            pass

    def _preview_merged_pdf(self):
        if not self._selected_record:
            self._show_error("Preview Failed", "No lead selected.")
            return

        import tempfile, os
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        self._status.setText("Generating preview...")
        QCoreApplication.processEvents()

        try:
            filled_text = self._editor.toPlainText()
            lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
            has_lv = bool(lv_path and Path(lv_path).exists())

            if has_lv:
                tmp_dir = Path(tempfile.mkdtemp(prefix="zz_preview_"))
                out_paths = self._export_bewerbungsmappe(self._selected_record, filled_text, tmp_dir)
                # Open the first (or only) file for preview
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_paths[0])))
                if len(out_paths) > 1:
                    self._status.setText(f"Preview opened ({len(out_paths)} files — showing first).")
                else:
                    self._status.setText("Preview opened.")
            else:
                # Fallback: render Anschreiben only
                fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="preview_")
                os.close(fd)
                tmp_file = Path(tmp_path)
                pdf_bytes = self._render_letter_as_pdf_page(filled_text)
                with open(tmp_file, "wb") as f:
                    f.write(pdf_bytes)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(tmp_file)))
                self._status.setText("Preview opened (Anschreiben only — load Lebenslauf for full preview).")
        except Exception as e:
            self._show_error("Preview Error", str(e))


    def _render_letter_as_pdf_page(self, text: str) -> bytes:
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER, TA_RIGHT
        from reportlab.platypus.flowables import KeepTogether

        buffer = io.BytesIO()
        
        # Modern Minimalist layout: tighter margins to ensure signature stays on page 1
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=10*mm,
            leftMargin=10*mm,
            topMargin=8*mm,
            bottomMargin=5*mm,
        )
        
        pdf_settings = self._load_pdf_settings()
        font_name = pdf_settings.get("font", "Helvetica")
        
        # Enforce highly readable defaults since UI is removed
        font_size = 11
        leading = 14
        alignment = TA_JUSTIFY
        
        styles = getSampleStyleSheet()
        style_normal = styles["Normal"]
        style_normal.fontName = font_name
        style_normal.fontSize = font_size
        style_normal.leading = leading
        style_normal.alignment = alignment
        
        style_h1 = ParagraphStyle(
            "H1",
            parent=style_normal,
            fontName=f"{font_name}-Bold" if font_name != "Times-Roman" else "Times-Bold",
            fontSize=30,
            leading=34,
            spaceAfter=4,
            alignment=TA_CENTER,
        )
        
        style_h2 = ParagraphStyle(
            "H2",
            parent=style_normal,
            fontName=f"{font_name}-Bold" if font_name != "Times-Roman" else "Times-Bold",
            fontSize=12,
            leading=14,
            spaceAfter=8,
            alignment=TA_CENTER,
        )
        
        style_right = ParagraphStyle(
            "Right",
            parent=style_normal,
            alignment=TA_RIGHT,
        )
        
        style_bold = ParagraphStyle(
            "Bold",
            parent=style_normal,
            fontName=f"{font_name}-Bold" if font_name != "Times-Roman" else "Times-Bold",
        )
        
        story = []
        lines = text.splitlines()
        
        if not lines:
            doc.build([Paragraph("Empty", style_normal)])
            return buffer.getvalue()
            
        # Parse the modern layout:
        idx = 0
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
            
        if idx < len(lines):
            story.append(Paragraph(lines[idx].strip().upper(), style_h1))
            idx += 1
            
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
            
        if idx < len(lines):
            story.append(Paragraph(lines[idx].strip(), style_h2))
            idx += 1
            
        # Lines 3, 4, etc. (normal paragraphs)
        is_first_paragraph = True
        for i in range(idx, len(lines)):
            line = lines[i].strip()
            if not line:
                story.append(Spacer(1, 10))
            else:
                if is_first_paragraph:
                    story.append(Paragraph(line, style_right))
                    is_first_paragraph = False
                elif "bewerbung um eine ausbildung" in line.lower() or "bewerbung als" in line.lower():
                    style_subj = ParagraphStyle("Subj", parent=style_bold, fontSize=13, spaceAfter=2)
                    story.append(Paragraph(line, style_subj))
                elif "freundlichen" in line.lower() and "gr" in line.lower():
                    story.append(Paragraph(line, style_normal))
                    story.append(Spacer(1, 2*mm)) # reduced from 5mm
                    
                    identity_block = []
                    
                    # Synchronous fallback to ensure we get the path even if background thread failed
                    sig_val = getattr(self, "_signature_image_path", "")
                    if not sig_val:
                        try:
                            import sqlite3
                            conn = sqlite3.connect(get_memory_db_path(), timeout=10.0)
                            row = conn.execute("SELECT value FROM settings WHERE key = 'signature_image_path'").fetchone()
                            if row and row[0]:
                                sig_val = row[0]
                            conn.close()
                        except Exception:
                            pass
                    
                    if sig_val:
                        sig_path = Path(sig_val)
                        if sig_path.exists():
                            try:
                                # Preprocess the image using Pillow to fix ReportLab transparency crash
                                from PIL import Image as PILImage
                                with PILImage.open(str(sig_path)) as pil_img:
                                    pil_img = pil_img.convert("RGBA")
                                    # Create white background to eliminate transparency
                                    bg = PILImage.new("RGBA", pil_img.size, (255, 255, 255, 255))
                                    out = PILImage.alpha_composite(bg, pil_img)
                                    rgb_img = out.convert("RGB")
                                    
                                    # Save to temporary buffer as JPEG
                                    img_buffer = io.BytesIO()
                                    rgb_img.save(img_buffer, format="JPEG")
                                    img_buffer.seek(0)
                                    
                                    img = Image(img_buffer, width=55*mm, height=20*mm, kind="proportional")
                                    img.hAlign = 'LEFT'
                                    identity_block.append(img)
                            except Exception as e:
                                identity_block.append(Paragraph(f"[Error processing signature image: {e}]", style_normal))
                        else:
                            identity_block.append(Paragraph(f"[Signature file not found: {sig_path}]", style_normal))
                    else:
                        identity_block.append(Paragraph("[No signature path saved in DB]", style_normal))
                                
                    sender_name = self._cached_sender_settings.get("name", "")
                    if not sender_name:
                        try:
                            import sqlite3
                            conn = sqlite3.connect(get_memory_db_path(), timeout=10.0)
                            row = conn.execute("SELECT value FROM settings WHERE key = 'sender_name'").fetchone()
                            if row and row[0]:
                                sender_name = row[0]
                            conn.close()
                        except Exception:
                            pass

                    if sender_name:
                        style_name = ParagraphStyle("Name", parent=style_bold, fontSize=13)
                        identity_block.append(Spacer(1, 1*mm))
                        identity_block.append(Paragraph(sender_name, style_name))
                    else:
                        identity_block.append(Paragraph("[No sender name set]", style_normal))
                        
                    story.append(KeepTogether(identity_block))
                else:
                    story.append(Paragraph(line, style_normal))

        doc.build(story)
        return buffer.getvalue()

    def _export_bewerbungsmappe(self, record: LeadRecord, letter_text: str, output_dir: Path | None = None) -> list[Path]:
        """
        Assemble and write the Bewerbungsmappe PDFs.
        Returns a list of produced Path objects (1, 2, or 3 files depending on mode).
        Raises ValueError if required documents are not loaded.
        """
        import pypdf, io, json

        # ── resolve document sources ────────────────────────────────────────
        db_path_str = getattr(config_manager.settings, "bewerbung_deckblatt_path", "") or ""
        has_db = bool(db_path_str and Path(db_path_str).exists())

        lv_path_str = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        if not lv_path_str or not Path(lv_path_str).exists():
            raise ValueError("Lebenslauf PDF not loaded. Please load it via LOAD LEBENSLAUF.")
        has_lv = True

        zeug_paths_raw = getattr(config_manager.settings, "bewerbung_zeugnisse_paths", "[]") or "[]"
        try:
            zeug_paths: list[str] = json.loads(zeug_paths_raw)
        except Exception:
            zeug_paths = []
        zeug_paths = [p for p in zeug_paths if p and Path(p).exists()]

        mode = getattr(config_manager.settings, "bewerbung_export_mode", "full")
        doc_order = self._get_doc_order()

        # ── naming helpers ───────────────────────────────────────────────────
        beruf = self._cached_sender_settings.get("beruf", "") or record.job_title or "Ausbildung"
        sender = self._load_sender_settings().get("name", "") or config_manager.settings.email_from_name or "Bewerber"
        firma = record.company_name or ""

        def sanitize(v: str) -> str:
            return re.sub(r'[<>:"/\\|?*]', '_', v)

        b = sanitize(beruf)
        s = sanitize(sender)
        f = sanitize(firma)
        out_dir = output_dir or get_exports_dir()
        
        base_name = f"Bewerbung als {b} - {s}"
        if f:
            base_name += f" @ {f}"
            
        if len(base_name) > 150:
            base_name = base_name[:146].strip()


        # ── PDF building helpers ─────────────────────────────────────────────
        letter_bytes = self._render_letter_as_pdf_page(letter_text)

        def _append_pdf_from_bytes(writer: pypdf.PdfWriter, data: bytes):
            try:
                r = pypdf.PdfReader(io.BytesIO(data))
                for page in r.pages:
                    writer.add_page(page)
            except Exception as e:
                print(f"Warning: could not merge letter bytes: {e}")

        def _append_pdf(writer: pypdf.PdfWriter, path: str):
            try:
                r = pypdf.PdfReader(path)
                if r.is_encrypted:
                    return
                for page in r.pages:
                    writer.add_page(page)
            except Exception as e:
                print(f"Warning: could not merge {path}: {e}")

        def _write(writer: pypdf.PdfWriter, dest: Path):
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                writer.write(f)
            return dest

        # ── export modes ────────────────────────────────────────────────────
        if mode == "full":
            # Single PDF: All available documents ordered according to user's doc_order
            w = pypdf.PdfWriter()
            for doc_key in doc_order:
                if doc_key == "deckblatt" and has_db:
                    _append_pdf(w, db_path_str)
                elif doc_key == "anschreiben":
                    _append_pdf_from_bytes(w, letter_bytes)
                elif doc_key == "lebenslauf" and has_lv:
                    _append_pdf(w, lv_path_str)
                elif doc_key == "zeugnisse":
                    for zp in zeug_paths:
                        _append_pdf(w, zp)
            dest = out_dir / f"{base_name}.pdf"
            return [_write(w, dest)]

        elif mode == "letter_cv_certs":
            # File 1: Dossier (Deckblatt, Anschreiben, Lebenslauf in user's doc_order)
            w1 = pypdf.PdfWriter()
            for doc_key in doc_order:
                if doc_key == "deckblatt" and has_db:
                    _append_pdf(w1, db_path_str)
                elif doc_key == "anschreiben":
                    _append_pdf_from_bytes(w1, letter_bytes)
                elif doc_key == "lebenslauf" and has_lv:
                    _append_pdf(w1, lv_path_str)
            dest1 = out_dir / f"{base_name}_AnschreibenLebenslauf.pdf"
            _write(w1, dest1)
            result = [dest1]
            # File 2: all Zeugnisse merged (if any)
            if zeug_paths:
                w2 = pypdf.PdfWriter()
                for zp in zeug_paths:
                    _append_pdf(w2, zp)
                dest2 = out_dir / f"{base_name}_Zeugnisse.pdf"
                result.append(_write(w2, dest2))
            return result

        else:  # "separate"
            result = []
            for doc_key in doc_order:
                if doc_key == "deckblatt" and has_db:
                    w_d = pypdf.PdfWriter()
                    _append_pdf(w_d, db_path_str)
                    dest_d = out_dir / f"{base_name}_Deckblatt.pdf"
                    result.append(_write(w_d, dest_d))
                elif doc_key == "anschreiben":
                    w_a = pypdf.PdfWriter()
                    _append_pdf_from_bytes(w_a, letter_bytes)
                    dest_a = out_dir / f"{base_name}_Anschreiben.pdf"
                    result.append(_write(w_a, dest_a))
                elif doc_key == "lebenslauf" and has_lv:
                    w_l = pypdf.PdfWriter()
                    _append_pdf(w_l, lv_path_str)
                    dest_l = out_dir / f"{base_name}_Lebenslauf.pdf"
                    result.append(_write(w_l, dest_l))
                elif doc_key == "zeugnisse" and zeug_paths:
                    w_z = pypdf.PdfWriter()
                    for zp in zeug_paths:
                        _append_pdf(w_z, zp)
                    dest_z = out_dir / f"{base_name}_Zeugnisse.pdf"
                    result.append(_write(w_z, dest_z))
            return result


    def _export_bewerbungsmappe_batch(self, out_dir: Path | None = None, records: list = None) -> bool:
        from ..core.power import WakeLock
        WakeLock.acquire("Batch PDF Export")
        try:
            return bool(self._do_export_bewerbungsmappe_batch(out_dir, records))
        finally:
            WakeLock.release("Batch PDF Export")

    def _do_export_bewerbungsmappe_batch(self, out_dir: Path | None = None, records: list = None) -> None:
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        if not lv_path or not Path(lv_path).exists():
            raise ValueError("Lebenslauf PDF not loaded. Please load it via LOAD LEBENSLAUF.")

        records = records if records is not None else self._pending_lead_records
        total = len(records)
        
        self._progress_info_bar = None
        self._batch_export_cancelled = False
        
        self._progress_info_bar = ToastNotification.custom(
            self,
            title="Batch Export",
            message="Starting export...",
            cancel_text=tr("Cancel", get_language(config_manager.settings.app_language))
        )
        self._progress_info_bar.show()
        
        try:
            for idx, record in enumerate(records):
                if getattr(self._progress_info_bar, "is_cancelled", False):
                    self._batch_export_cancelled = True
                    if self._progress_info_bar:
                        self._progress_info_bar.close_anim()
                        self._progress_info_bar = None
                    ToastNotification.warning("Batch Export Cancelled", f"Export stopped after {idx} PDFs.", duration=3000, parent=self)
                    return False
                    
                progress_text = f"Exporting {idx + 1} / {total}…"
                self._progress_info_bar.set_message(progress_text)
                QCoreApplication.processEvents()
                
                state = self._states.get(record.id)
                letter_text = (state.letter_text if state else None) or self._assemble_letter(record)
                
                if not letter_text:
                    raise ValueError(f"Cover letter template generated an empty text for lead #{record.id} ('{record.company_name or record.email}').")
                    
                try:
                    self._export_bewerbungsmappe(record, letter_text, out_dir)
                except Exception as e:
                    print(f"Failed to export {record.id}: {e}")
            
            if self._progress_info_bar:
                self._progress_info_bar.close_anim()
                self._progress_info_bar = None
                
            self._show_success("Batch Export Completed", f"Successfully exported {total} PDFs.")
            return True
            
        except Exception as e:
            if self._progress_info_bar:
                self._progress_info_bar.close_anim()
                self._progress_info_bar = None
            raise e

    def _action_export_bewerbungsmappe(self) -> None:
        if not self._selected_record:
            self._show_error("Export Failed", "Select a lead first")
            return

        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        if not lv_path or not Path(lv_path).exists():
            self._show_error("Export Failed", "Load your Lebenslauf PDF first (BEWERBUNG → Load Lebenslauf).")
            return

        from ..core.security import LicenseManager
        if not LicenseManager.can_export_pdf(1):
            status = LicenseManager.get_pdf_trial_status()
            from .toast_system import ToastNotification as InfoBar
            ToastNotification.warning(
                title="Free Limit Reached",
                content=f"You have reached your free limit of {status['total']} PDFs per day. Please upgrade to Pro.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=6000,
                parent=self.window()
            )
            return

        try:
            import pypdf
        except ImportError:
            self._show_error("Dependency Missing", "Install pypdf:  pip install pypdf")
            return

        try:
            import reportlab
        except ImportError:
            self._show_error("Dependency Missing", "Install reportlab:  pip install reportlab")
            return

        try:
            out_dir_str = QFileDialog.getExistingDirectory(
                self,
                "Choose Export Folder",
                str(Path.home() / "Documents"),
            )
            if not out_dir_str:
                return

            letter_text = self._editor.toPlainText()
            out_paths = self._export_bewerbungsmappe(self._selected_record, letter_text, Path(out_dir_str))
            LicenseManager.record_pdf_export(1)
            names = ", ".join(p.name for p in out_paths)
            self._show_success("Exported", names)
        except Exception as e:
            self._show_error("Export Failed", str(e))


    def _action_export_bewerbungsmappe_batch(self) -> None:
        if not self._pending_lead_records:
            self._show_error("Nothing to export", "No leads match current filter.")
            return
            
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        if not lv_path or not Path(lv_path).exists():
            self._show_error("Export Failed", "Load your Lebenslauf PDF first (BEWERBUNG → Load Lebenslauf).")
            return
            
        from ..core.security import LicenseManager
        count = len(self._pending_lead_records)
        status = LicenseManager.get_pdf_trial_status()
        export_records = self._pending_lead_records
        show_limit_warning = False

        if not LicenseManager.is_active() and count > status['remaining']:
            if status['remaining'] <= 0:
                from .toast_system import ToastNotification as InfoBar
                ToastNotification.warning(
                    title="Free Limit Reached",
                    content=f"Batch export of {count} PDFs exceeds your daily limit of 0. Please upgrade to Pro.",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                    parent=self.window()
                )
                return
            else:
                export_records = self._pending_lead_records[:status['remaining']]
                show_limit_warning = True
            
        try:
            import pypdf
        except ImportError:
            self._show_error("Dependency Missing", "Install pypdf:  pip install pypdf")
            return
            
        try:
            import reportlab
        except ImportError:
            self._show_error("Dependency Missing", "Install reportlab:  pip install reportlab")
            return
            
        try:
            out_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Export Folder for Batch PDF",
                ""
            )
            
            if not out_dir:
                return
                
            success = self._export_bewerbungsmappe_batch(out_dir=Path(out_dir), records=export_records)
            if not success or getattr(self, "_batch_export_cancelled", False):
                return
            LicenseManager.record_pdf_export(len(export_records))
            
            if show_limit_warning:
                from .toast_system import ToastNotification as InfoBar
                ToastNotification.warning(
                    title="Free Limit Reached",
                    content=f"Batch export of {count} leads exceeds your limit. Only {max(0, status['remaining'])} PDFs were generated. Please upgrade to Pro for unlimited usage.",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                    parent=self.window()
                )
        except Exception as e:
            self._show_error("Batch Export Failed", str(e))

    def _action_export_and_send_batch(self) -> None:
        if not self._pending_lead_records:
            self._show_error("Export Failed", "No leads match current filter.")
            return
            
        lv_path = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
        if not lv_path or not Path(lv_path).exists():
            self._show_error("Export Failed", "Load your Lebenslauf PDF first (BEWERBUNG → Load Lebenslauf).")
            return
            
        from ..core.security import LicenseManager
        count = len(self._pending_lead_records)
        status = LicenseManager.get_pdf_trial_status()
        export_records = self._pending_lead_records
        show_limit_warning = False

        if not LicenseManager.is_active() and count > status['remaining']:
            # Bypassing the free tier limits so that custom PDFs are always generated instead of resetting to raw uploaded PDF.
            # export_records = self._pending_lead_records[:max(0, status['remaining'])]
            export_records = self._pending_lead_records
            show_limit_warning = True
            
        try:
            import pypdf
        except ImportError:
            self._show_error("Dependency Missing", "Install pypdf:  pip install pypdf")
            return
            
        try:
            import reportlab
        except ImportError:
            self._show_error("Dependency Missing", "Install reportlab:  pip install reportlab")
            return
            
        try:
            # We don't ask for a directory, we just save to the standard exports folder
            from ..core.config import get_exports_dir
            import shutil
            
            out_dir = get_exports_dir()
            
            # Copy the generic Lebenslauf to act as a fallback for leads beyond the trial limit
            raw_pdf_path = out_dir / "Bewerbung_Raw_Uploaded.pdf"
            try:
                if lv_path and Path(lv_path).exists():
                    shutil.copy2(str(lv_path), str(raw_pdf_path))
            except Exception as e:
                pass # Non-fatal if we can't copy it
                
            success = self._export_bewerbungsmappe_batch(out_dir=Path(out_dir), records=export_records)
            if not success or getattr(self, "_batch_export_cancelled", False):
                # Export cancelled by user; stay at Edit page and do not send emails or switch tabs
                return
            LicenseManager.record_pdf_export(len(export_records))
            
            # Emit ALL valid emails, even those that didn't get a custom PDF
            all_emails = [r.email for r in self._pending_lead_records if r.email and r.email.strip()]
            if all_emails:
                self.send_emails_to_sender.emit(all_emails)
            else:
                self._show_error("No Emails", "No valid emails found in the visible leads.")
                
            if show_limit_warning:
                from .toast_system import ToastNotification as InfoBar
                ToastNotification.warning(
                    title="Free Limit Reached",
                    content=f"Batch export of {count} leads exceeds your limit. Only {max(0, status['remaining'])} custom PDFs were generated. The rest will use your raw uploaded PDF as a fallback. Please upgrade to Pro for unlimited customization.",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                    parent=self.window()
                )
        except Exception as e:
            self._show_error("Batch Export & Send Failed", str(e))

# 1.1.1
