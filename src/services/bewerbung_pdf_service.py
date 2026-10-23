"""
ZUGZWANG - Bewerbung PDF Generation Service
Headless PDF rendering and Bewerbungsmappe assembly.
Pure business logic decoupled from Qt widgets to allow safe execution in background threads.
"""

from __future__ import annotations
import io
import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

import pypdf
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.platypus.flowables import KeepTogether
from reportlab.pdfgen import canvas

from ..core.config import config_manager, get_memory_db_path, get_exports_dir
from ..core.models import LeadRecord


def _clean_unicode(s: str) -> str:
    if not s:
        return ""
    return str(s).replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '').strip()


def _sanitize(v: str) -> str:
    v_clean = _clean_unicode(v)
    return re.sub(r'[<>:"/\\|?*]', '_', v_clean).strip()


def load_pdf_styling_settings() -> dict:
    """Load PDF styling configuration from SQLite settings table."""
    settings = {"font": "Helvetica", "size": "11", "leading": "14", "alignment": "Justified"}
    try:
        db_path = get_memory_db_path()
        conn = sqlite3.connect(db_path, timeout=10.0)
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'pdf_%'").fetchall()
        for k, v in rows:
            settings[k.replace("pdf_", "")] = v
        conn.close()
    except Exception:
        pass
    return settings


def load_sender_settings() -> dict:
    """Load sender profile information from SQLite settings table."""
    try:
        conn = sqlite3.connect(str(get_memory_db_path()), timeout=10.0)
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'sender_%'").fetchall()
        conn.close()
        return {row[0].replace("sender_", ""): row[1] for row in rows}
    except Exception:
        return {}


def get_signature_path() -> str:
    """Retrieve saved signature image path from database."""
    try:
        conn = sqlite3.connect(str(get_memory_db_path()), timeout=10.0)
        row = conn.execute("SELECT value FROM settings WHERE key = 'signature_image_path'").fetchone()
        conn.close()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""


def get_doc_order() -> list[str]:
    """Return ordered list of document keys for the application packet."""
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


def _safe_xml(val: str) -> str:
    if not val:
        return ""
    s = str(val)

    allowed_pattern = re.compile(r'<\s*(/?)\s*(b|i|u|strike|sub|sup|br)\s*(/?)>', re.IGNORECASE)
    tokens = []

    def save_tag(match):
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        is_self_closing = bool(match.group(3)) or tag_name == 'br'
        idx = len(tokens)
        if is_closing:
            tokens.append(f"</{tag_name}>")
        elif is_self_closing:
            tokens.append(f"<{tag_name}/>")
        else:
            tokens.append(f"<{tag_name}>")
        return f"@@TAG_{idx}@@"

    s_masked = allowed_pattern.sub(save_tag, s)
    s_escaped = re.sub(r'&(?!(?:amp|lt|gt|quot|apos);)', '&amp;', s_masked)
    s_escaped = s_escaped.replace('<', '&lt;').replace('>', '&gt;')

    for i, tag in enumerate(tokens):
        s_escaped = s_escaped.replace(f"@@TAG_{i}@@", tag)

    tag_stack = []
    tag_regex = re.compile(r'<(/?)(b|i|u|strike|sub|sup|br)/?>')
    cleaned_parts = []
    last_idx = 0
    for m in tag_regex.finditer(s_escaped):
        cleaned_parts.append(s_escaped[last_idx:m.start()])
        is_close = bool(m.group(1))
        tag = m.group(2)
        if tag == 'br':
            cleaned_parts.append('<br/>')
        elif not is_close:
            tag_stack.append(tag)
            cleaned_parts.append(f"<{tag}>")
        else:
            if tag in tag_stack:
                while tag_stack:
                    popped = tag_stack.pop()
                    cleaned_parts.append(f"</{popped}>")
                    if popped == tag:
                        break
        last_idx = m.end()
    cleaned_parts.append(s_escaped[last_idx:])
    while tag_stack:
        cleaned_parts.append(f"</{tag_stack.pop()}>")

    return "".join(cleaned_parts)


def render_letter_as_pdf_page(
    text: str,
    sender_name: str = "",
    signature_image_path: str = "",
    pdf_settings: dict | None = None,
) -> bytes:
    """Render cover letter text into a single PDF page byte stream using ReportLab."""
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=5 * mm,
    )

    pdf_cfg = pdf_settings or load_pdf_styling_settings()
    font_name = pdf_cfg.get("font", "Helvetica")
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

    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines):
        story.append(Paragraph(_safe_xml(lines[idx].strip().upper()), style_h1))
        idx += 1

    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines):
        story.append(Paragraph(_safe_xml(lines[idx].strip()), style_h2))
        idx += 1

    sig_val = signature_image_path or get_signature_path()
    eff_sender_name = sender_name
    if not eff_sender_name:
        sender_cfg = load_sender_settings()
        eff_sender_name = sender_cfg.get("name", "") or getattr(config_manager.settings, "email_from_name", "") or ""

    is_first_paragraph = True
    for i in range(idx, len(lines)):
        line = lines[i].strip()
        if not line:
            story.append(Spacer(1, 10))
        else:
            if is_first_paragraph:
                story.append(Paragraph(_safe_xml(line), style_right))
                is_first_paragraph = False
            elif "bewerbung um eine ausbildung" in line.lower() or "bewerbung als" in line.lower():
                style_subj = ParagraphStyle("Subj", parent=style_bold, fontSize=13, spaceAfter=2)
                story.append(Paragraph(_safe_xml(line), style_subj))
            elif "freundlichen" in line.lower() and "gr" in line.lower():
                story.append(Paragraph(_safe_xml(line), style_normal))
                story.append(Spacer(1, 2 * mm))

                identity_block = []
                if sig_val:
                    sig_path = Path(sig_val)
                    if sig_path.exists():
                        try:
                            with PILImage.open(str(sig_path)) as pil_img:
                                pil_img = pil_img.convert("RGBA")
                                bg = PILImage.new("RGBA", pil_img.size, (255, 255, 255, 255))
                                out = PILImage.alpha_composite(bg, pil_img)
                                rgb_img = out.convert("RGB")

                                img_buffer = io.BytesIO()
                                rgb_img.save(img_buffer, format="JPEG")
                                img_buffer.seek(0)

                                img = Image(img_buffer, width=55 * mm, height=20 * mm, kind="proportional")
                                img.hAlign = 'LEFT'
                                identity_block.append(img)
                        except Exception:
                            pass

                if eff_sender_name:
                    style_name = ParagraphStyle("Name", parent=style_bold, fontSize=13)
                    identity_block.append(Spacer(1, 1 * mm))
                    identity_block.append(Paragraph(_safe_xml(eff_sender_name), style_name))

                if identity_block:
                    story.append(KeepTogether(identity_block))
            else:
                story.append(Paragraph(_safe_xml(line), style_normal))

    try:
        doc.build(story)
        return buffer.getvalue()
    except Exception as build_err:
        fallback_buf = io.BytesIO()
        c = canvas.Canvas(fallback_buf, pagesize=A4)
        width, height = A4
        y = height - 20 * mm
        c.setFont("Helvetica", 10)
        for raw_line in text.splitlines():
            if y < 15 * mm:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 20 * mm
            clean_text = re.sub(r"<[^>]+>", "", str(raw_line))
            c.drawString(15 * mm, y, clean_text[:120])
            y -= 14
        c.save()
        return fallback_buf.getvalue()


def export_bewerbungsmappe(
    record: LeadRecord,
    letter_text: str,
    output_dir: Path | None = None,
    sender_settings: dict | None = None,
    pdf_settings: dict | None = None,
    signature_image_path: str = "",
    profile_id: str | None = None,
) -> list[Path]:
    """
    Assemble and write the Bewerbungsmappe PDFs without requiring any UI components.
    Returns a list of produced Path objects (1, 2, or 3 files depending on mode).
    Uses the specified or active profile's documents.
    """
    from .profile_service import get_active_profile_id, get_lebenslauf, get_zeugnisse, get_deckblatt
    target_prof_id = profile_id or get_active_profile_id()

    # Resolve documents scoped to target profile
    lv_doc = get_lebenslauf(target_prof_id)
    if lv_doc and Path(lv_doc.stored_path).exists():
        lv_path_str = lv_doc.stored_path
    else:
        lv_path_str = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
    has_lv = bool(lv_path_str and Path(lv_path_str).exists())

    db_doc = get_deckblatt(target_prof_id)
    if db_doc and Path(db_doc.stored_path).exists():
        db_path_str = db_doc.stored_path
    else:
        db_path_str = getattr(config_manager.settings, "bewerbung_deckblatt_path", "") or ""
    has_db = bool(db_path_str and Path(db_path_str).exists())

    has_letter = bool(letter_text and letter_text.strip())
    if not has_lv and not has_letter and not has_db:
        raise ValueError("No documents to export. Please load your Lebenslauf or enter cover letter text.")

    zeug_docs = get_zeugnisse(target_prof_id)
    if zeug_docs:
        zeug_paths = [d.stored_path for d in zeug_docs if Path(d.stored_path).exists()]
    else:
        zeug_paths_raw = getattr(config_manager.settings, "bewerbung_zeugnisse_paths", "[]") or "[]"
        try:
            zeug_paths = json.loads(zeug_paths_raw)
        except Exception:
            zeug_paths = []
        zeug_paths = [p for p in zeug_paths if p and Path(p).exists()]

    mode = getattr(config_manager.settings, "bewerbung_export_mode", "full")
    doc_order = get_doc_order()

    sender_cfg = sender_settings if sender_settings is not None else load_sender_settings()
    try:
        from . import profile_service
        target_prof = profile_service.get_profile(target_prof_id) if target_prof_id else profile_service.get_active_profile()
        prof_beruf = target_prof.effective_beruf if target_prof else ""
    except Exception:
        prof_beruf = ""
    beruf = prof_beruf or sender_cfg.get("beruf", "") or record.job_title or "Ausbildung"
    sender = sender_cfg.get("name", "") or getattr(config_manager.settings, "email_from_name", "") or "Bewerber"
    firma = record.company_name or ""

    b = _sanitize(beruf)
    s = _sanitize(sender)
    f = _sanitize(firma)
    out_dir = output_dir or get_exports_dir()

    base_name = f"Bewerbung als {b} - {s}"
    if f:
        base_name += f" @ {f}"
    if len(base_name) > 150:
        base_name = base_name[:146].strip()

    letter_bytes = (
        render_letter_as_pdf_page(
            letter_text,
            sender_name=sender,
            signature_image_path=signature_image_path,
            pdf_settings=pdf_settings,
        )
        if has_letter
        else None
    )

    def _append_pdf_from_bytes(writer: pypdf.PdfWriter, data: bytes):
        try:
            r = pypdf.PdfReader(io.BytesIO(data))
            for page in r.pages:
                writer.add_page(page)
        except Exception as e:
            pass

    def _append_pdf(writer: pypdf.PdfWriter, path: str):
        try:
            r = pypdf.PdfReader(path)
            if r.is_encrypted:
                return
            for page in r.pages:
                writer.add_page(page)
        except Exception:
            pass

    def _write(writer: pypdf.PdfWriter, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f_out:
            writer.write(f_out)
        return dest

    if mode == "full":
        w = pypdf.PdfWriter()
        has_pages = False
        for doc_key in doc_order:
            if doc_key == "deckblatt" and has_db:
                _append_pdf(w, db_path_str)
                has_pages = True
            elif doc_key == "anschreiben" and letter_bytes:
                _append_pdf_from_bytes(w, letter_bytes)
                has_pages = True
            elif doc_key == "lebenslauf" and has_lv:
                _append_pdf(w, lv_path_str)
                has_pages = True
            elif doc_key == "zeugnisse":
                for zp in zeug_paths:
                    _append_pdf(w, zp)
                    has_pages = True
        if has_pages:
            dest = out_dir / f"{base_name}.pdf"
            return [_write(w, dest)]
        return []

    elif mode == "letter_cv_certs":
        w1 = pypdf.PdfWriter()
        has_p1 = False
        for doc_key in doc_order:
            if doc_key == "deckblatt" and has_db:
                _append_pdf(w1, db_path_str)
                has_p1 = True
            elif doc_key == "anschreiben" and letter_bytes:
                _append_pdf_from_bytes(w1, letter_bytes)
                has_p1 = True
            elif doc_key == "lebenslauf" and has_lv:
                _append_pdf(w1, lv_path_str)
                has_p1 = True
        result = []
        if has_p1:
            dest1 = out_dir / f"{base_name}_AnschreibenLebenslauf.pdf"
            _write(w1, dest1)
            result.append(dest1)
        if zeug_paths:
            dest2 = out_dir / f"{base_name}_Zeugnisse.pdf"
            if not dest2.exists():
                w2 = pypdf.PdfWriter()
                for zp in zeug_paths:
                    _append_pdf(w2, zp)
                _write(w2, dest2)
            result.append(dest2)
        return result

    else:  # "separate"
        result = []
        for doc_key in doc_order:
            if doc_key == "deckblatt" and has_db:
                dest_d = out_dir / f"{base_name}_Deckblatt.pdf"
                if not dest_d.exists():
                    try:
                        shutil.copy2(db_path_str, str(dest_d))
                    except Exception:
                        w_d = pypdf.PdfWriter()
                        _append_pdf(w_d, db_path_str)
                        _write(w_d, dest_d)
                result.append(dest_d)
            elif doc_key == "anschreiben" and letter_bytes:
                w_a = pypdf.PdfWriter()
                _append_pdf_from_bytes(w_a, letter_bytes)
                dest_a = out_dir / f"{base_name}_Anschreiben.pdf"
                result.append(_write(w_a, dest_a))
            elif doc_key == "lebenslauf" and has_lv:
                dest_l = out_dir / f"{base_name}_Lebenslauf.pdf"
                if not dest_l.exists():
                    try:
                        shutil.copy2(lv_path_str, str(dest_l))
                    except Exception:
                        w_l = pypdf.PdfWriter()
                        _append_pdf(w_l, lv_path_str)
                        _write(w_l, dest_l)
                result.append(dest_l)
            elif doc_key == "zeugnisse" and zeug_paths:
                dest_z = out_dir / f"{base_name}_Zeugnisse.pdf"
                if not dest_z.exists():
                    w_z = pypdf.PdfWriter()
                    for zp in zeug_paths:
                        _append_pdf(w_z, zp)
                        _write(w_z, dest_z)
                result.append(dest_z)
        return result

# 1.5.0
