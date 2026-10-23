"""
ZUGZWANG - Profile Service
Manages multi-profile support for the Bewerbung (Edit) workspace.
Handles SQLite schema, migrations, profile CRUD, document storage, and active profile state.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Optional, List
import uuid

from ..core.config import get_memory_db_path, get_app_data_dir, config_manager
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Profile:
    id: str
    name: str
    created_at: str
    updated_at: str
    is_default: bool
    sort_order: int
    template_text: str = ""
    beruf: str = ""
    email_subject: str = ""
    email_body: str = ""

    @property
    def effective_beruf(self) -> str:
        """Returns the target profession / job title for this profile.
        If an explicit beruf is set, use it. Otherwise, if name is not 'Default', use name.
        Strips redundant 'Ausbildung zum/zur/als' prefixes if present for cleaner placeholder replacement.
        """
        raw = (self.beruf or "").strip()
        if not raw and self.name and self.name.strip().lower() != "default":
            raw = self.name.strip()
        raw = re.sub(r'^(?:Ausbildung\s+(?:zum|zur|als)\s+)', '', raw, flags=re.IGNORECASE).strip()
        return raw



@dataclass
class ProfileDocument:
    id: str
    profile_id: str
    doc_type: str  # 'lebenslauf', 'zeugnis', 'deckblatt'
    file_name: str
    stored_path: str
    added_at: str
    sort_order: int = 0


def _get_connection(conn: sqlite3.Connection | None = None) -> tuple[sqlite3.Connection, bool]:
    """Helper to get a connection and a flag indicating whether it should be closed by caller."""
    if conn is not None:
        return conn, False
    db_path = get_memory_db_path()
    c = sqlite3.connect(str(db_path), timeout=20.0)
    c.execute("PRAGMA foreign_keys = ON")
    return c, True


def get_profile_storage_dir(profile_id: str, doc_type: str = "") -> Path:
    """Return the dedicated storage directory for a profile's documents."""
    base = get_app_data_dir() / "profiles" / profile_id
    if doc_type:
        d = base / doc_type
    else:
        d = base
    d.mkdir(parents=True, exist_ok=True)
    return d


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Ensure profiles tables exist and run idempotent migrations."""
    c, should_close = _get_connection(conn)
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                template_text TEXT DEFAULT '',
                beruf TEXT DEFAULT '',
                email_subject TEXT DEFAULT '',
                email_body TEXT DEFAULT ''
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS profile_documents (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                added_at TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_prof_docs_prof_id ON profile_documents(profile_id)")

        # Ensure profiles has beruf, email_subject, email_body columns
        prof_cols = {r[1] for r in c.execute("PRAGMA table_info(profiles)").fetchall()}
        if prof_cols and "beruf" not in prof_cols:
            try:
                c.execute("ALTER TABLE profiles ADD COLUMN beruf TEXT DEFAULT ''")
            except Exception as e:
                logger.debug(f"Could not alter profiles with beruf: {e}")
        if prof_cols and "email_subject" not in prof_cols:
            try:
                c.execute("ALTER TABLE profiles ADD COLUMN email_subject TEXT DEFAULT ''")
            except Exception as e:
                logger.debug(f"Could not alter profiles with email_subject: {e}")
        if prof_cols and "email_body" not in prof_cols:
            try:
                c.execute("ALTER TABLE profiles ADD COLUMN email_body TEXT DEFAULT ''")
            except Exception as e:
                logger.debug(f"Could not alter profiles with email_body: {e}")

        # Ensure letter_state has profile_id column
        state_cols = {r[1] for r in c.execute("PRAGMA table_info(letter_state)").fetchall()}
        if state_cols and "profile_id" not in state_cols:
            try:
                c.execute("ALTER TABLE letter_state ADD COLUMN profile_id TEXT DEFAULT NULL")
            except Exception as e:
                logger.debug(f"Could not alter letter_state with profile_id: {e}")

        # Check if Default profile exists
        row = c.execute("SELECT COUNT(*) FROM profiles").fetchone()
        count = row[0] if row else 0
        if count == 0:
            now = datetime.utcnow().isoformat()
            
            # Load template text
            template_text = ""
            tpl_path = get_app_data_dir() / "templates" / "anschreiben_base.txt"
            if tpl_path.exists():
                try:
                    template_text = tpl_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not template_text:
                bundle_tpl = Path(__file__).resolve().parents[2] / "templates" / "anschreiben_base.txt"
                if bundle_tpl.exists():
                    try:
                        template_text = bundle_tpl.read_text(encoding="utf-8")
                    except Exception:
                        pass

            c.execute("""
                INSERT INTO profiles (id, name, created_at, updated_at, is_default, sort_order, template_text)
                VALUES (?, ?, ?, ?, 1, 0, ?)
            """, ("default", "Default", now, now, template_text))

            # Migrate existing Lebenslauf
            lv_path_str = getattr(config_manager.settings, "bewerbung_lebenslauf_path", "") or ""
            if lv_path_str and Path(lv_path_str).exists():
                _store_single_doc(c, "default", "lebenslauf", lv_path_str)

            # Migrate existing Zeugnisse
            zeug_raw = getattr(config_manager.settings, "bewerbung_zeugnisse_paths", "[]") or "[]"
            try:
                zeug_paths = json.loads(zeug_raw)
            except Exception:
                zeug_paths = []
            for idx, zp in enumerate(zeug_paths):
                if zp and Path(zp).exists():
                    _store_multi_doc(c, "default", "zeugnis", zp, sort_order=idx)

            # Migrate existing Deckblatt
            db_path_str = getattr(config_manager.settings, "bewerbung_deckblatt_path", "") or ""
            if db_path_str and Path(db_path_str).exists():
                _store_single_doc(c, "default", "deckblatt", db_path_str)

            # Tag existing letter_state entries with 'default'
            if "profile_id" in state_cols or True:
                try:
                    c.execute("UPDATE letter_state SET profile_id = 'default' WHERE profile_id IS NULL")
                except Exception:
                    pass

            config_manager.settings.last_active_profile_id = "default"
            config_manager.save()

        c.commit()
    finally:
        if should_close:
            c.close()


def _store_single_doc(conn: sqlite3.Connection, profile_id: str, doc_type: str, source_path: str) -> Optional[ProfileDocument]:
    src = Path(source_path)
    if not src.exists():
        return None
    dest_dir = get_profile_storage_dir(profile_id, doc_type)
    dest_file = dest_dir / src.name
    try:
        shutil.copy2(src, dest_file)
    except Exception:
        dest_file = src

    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    now = datetime.utcnow().isoformat()
    # Remove old doc of same type for this profile
    conn.execute("DELETE FROM profile_documents WHERE profile_id = ? AND doc_type = ?", (profile_id, doc_type))
    conn.execute("""
        INSERT INTO profile_documents (id, profile_id, doc_type, file_name, stored_path, added_at, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (doc_id, profile_id, doc_type, src.name, str(dest_file), now))
    return ProfileDocument(doc_id, profile_id, doc_type, src.name, str(dest_file), now, 0)


def _store_multi_doc(conn: sqlite3.Connection, profile_id: str, doc_type: str, source_path: str, sort_order: int = 0) -> Optional[ProfileDocument]:
    src = Path(source_path)
    if not src.exists():
        return None
    dest_dir = get_profile_storage_dir(profile_id, doc_type)
    dest_file = dest_dir / src.name
    try:
        shutil.copy2(src, dest_file)
    except Exception:
        dest_file = src

    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO profile_documents (id, profile_id, doc_type, file_name, stored_path, added_at, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, profile_id, doc_type, src.name, str(dest_file), now, sort_order))
    return ProfileDocument(doc_id, profile_id, doc_type, src.name, str(dest_file), now, sort_order)


def get_profiles(conn: sqlite3.Connection | None = None) -> list[Profile]:
    """Return all profiles sorted by sort_order and creation date."""
    init_db(conn)
    c, should_close = _get_connection(conn)
    try:
        rows = c.execute("""
            SELECT id, name, created_at, updated_at, is_default, sort_order, template_text, beruf, email_subject, email_body
            FROM profiles
            ORDER BY sort_order ASC, created_at ASC
        """).fetchall()
        return [
            Profile(
                id=r[0],
                name=r[1],
                created_at=r[2],
                updated_at=r[3],
                is_default=bool(r[4]),
                sort_order=r[5],
                template_text=r[6] or "",
                beruf=r[7] or "" if len(r) > 7 else "",
                email_subject=r[8] or "" if len(r) > 8 else "",
                email_body=r[9] or "" if len(r) > 9 else "",
            )
            for r in rows
        ]
    finally:
        if should_close:
            c.close()


def get_profile(profile_id: str, conn: sqlite3.Connection | None = None) -> Optional[Profile]:
    """Retrieve profile by ID."""
    init_db(conn)
    c, should_close = _get_connection(conn)
    try:
        r = c.execute("""
            SELECT id, name, created_at, updated_at, is_default, sort_order, template_text, beruf, email_subject, email_body
            FROM profiles WHERE id = ?
        """, (profile_id,)).fetchone()
        if not r:
            return None
        return Profile(
            id=r[0],
            name=r[1],
            created_at=r[2],
            updated_at=r[3],
            is_default=bool(r[4]),
            sort_order=r[5],
            template_text=r[6] or "",
            beruf=r[7] or "" if len(r) > 7 else "",
            email_subject=r[8] or "" if len(r) > 8 else "",
            email_body=r[9] or "" if len(r) > 9 else "",
        )
    finally:
        if should_close:
            c.close()


def get_default_profile(conn: sqlite3.Connection | None = None) -> Profile:
    """Return the default profile."""
    init_db(conn)
    c, should_close = _get_connection(conn)
    try:
        r = c.execute("""
            SELECT id, name, created_at, updated_at, is_default, sort_order, template_text, beruf, email_subject, email_body
            FROM profiles WHERE is_default = 1 LIMIT 1
        """).fetchone()
        if r:
            return Profile(
                r[0], r[1], r[2], r[3], bool(r[4]), r[5],
                r[6] or "",
                r[7] or "" if len(r) > 7 else "",
                r[8] or "" if len(r) > 8 else "",
                r[9] or "" if len(r) > 9 else ""
            )
        profiles = get_profiles(c)
        if profiles:
            return profiles[0]
        # Emergency fallback
        return Profile("default", "Default", "", "", True, 0, "", "", "", "")
    finally:
        if should_close:
            c.close()


def get_active_profile(conn: sqlite3.Connection | None = None) -> Profile:
    """Return currently active profile based on settings."""
    init_db(conn)
    last_id = getattr(config_manager.settings, "last_active_profile_id", "") or ""
    if last_id:
        p = get_profile(last_id, conn)
        if p:
            return p
    default_p = get_default_profile(conn)
    config_manager.settings.last_active_profile_id = default_p.id
    config_manager.save()
    return default_p


def get_active_profile_id(conn: sqlite3.Connection | None = None) -> str:
    """Convenience method returning the active profile's ID."""
    return get_active_profile(conn).id


def set_active_profile_id(profile_id: str) -> None:
    """Persist active profile id."""
    config_manager.settings.last_active_profile_id = profile_id
    config_manager.save()


set_active_profile = set_active_profile_id


def create_profile(name: str, template_text: str = "", beruf: str = "", email_subject: str = "", email_body: str = "", conn: sqlite3.Connection | None = None) -> Profile:
    """Create a new named profile."""
    clean_name = name.strip()
    clean_beruf = beruf.strip()
    if not clean_name:
        raise ValueError("Profile name cannot be empty.")
    if len(clean_name) > 30:
        clean_name = clean_name[:30].strip()

    c, should_close = _get_connection(conn)
    try:
        existing = c.execute("SELECT id FROM profiles WHERE LOWER(name) = LOWER(?)", (clean_name,)).fetchone()
        if existing:
            raise ValueError(f"A profile named '{clean_name}' already exists.")

        max_order_row = c.execute("SELECT MAX(sort_order) FROM profiles").fetchone()
        next_order = (max_order_row[0] or 0) + 1 if max_order_row else 1

        prof_id = f"prof_{uuid.uuid4().hex[:10]}"
        now = datetime.utcnow().isoformat()

        c.execute("""
            INSERT INTO profiles (id, name, created_at, updated_at, is_default, sort_order, template_text, beruf, email_subject, email_body)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """, (prof_id, clean_name, now, now, next_order, template_text, clean_beruf, email_subject, email_body))
        c.commit()

        # Create profile directory
        get_profile_storage_dir(prof_id)

        set_active_profile_id(prof_id)
        return Profile(prof_id, clean_name, now, now, False, next_order, template_text, clean_beruf, email_subject, email_body)
    finally:
        if should_close:
            c.close()


def update_profile(
    profile_id: str,
    new_name: str | None = None,
    new_beruf: str | None = None,
    new_email_subject: str | None = None,
    new_email_body: str | None = None,
    conn: sqlite3.Connection | None = None
) -> Profile:
    """Update profile name, target job (beruf), and/or email payload."""
    c, should_close = _get_connection(conn)
    try:
        now = datetime.utcnow().isoformat()
        if new_name is not None:
            clean_name = new_name.strip()
            if not clean_name:
                raise ValueError("Profile name cannot be empty.")
            if len(clean_name) > 30:
                clean_name = clean_name[:30].strip()
            existing = c.execute("SELECT id FROM profiles WHERE LOWER(name) = LOWER(?) AND id != ?", (clean_name, profile_id)).fetchone()
            if existing:
                raise ValueError(f"A profile named '{clean_name}' already exists.")
            c.execute("UPDATE profiles SET name = ?, updated_at = ? WHERE id = ?", (clean_name, now, profile_id))

        if new_beruf is not None:
            c.execute("UPDATE profiles SET beruf = ?, updated_at = ? WHERE id = ?", (new_beruf.strip(), now, profile_id))

        if new_email_subject is not None:
            c.execute("UPDATE profiles SET email_subject = ?, updated_at = ? WHERE id = ?", (new_email_subject, now, profile_id))

        if new_email_body is not None:
            c.execute("UPDATE profiles SET email_body = ?, updated_at = ? WHERE id = ?", (new_email_body, now, profile_id))

        c.commit()
        p = get_profile(profile_id, c)
        if not p:
            raise ValueError(f"Profile {profile_id} not found.")
        return p
    finally:
        if should_close:
            c.close()


def rename_profile(profile_id: str, new_name: str, new_beruf: str | None = None, conn: sqlite3.Connection | None = None) -> Profile:
    """Rename an existing profile and optionally update its target job (beruf)."""
    return update_profile(profile_id, new_name=new_name, new_beruf=new_beruf, conn=conn)


def duplicate_profile(profile_id: str, conn: sqlite3.Connection | None = None) -> Profile:
    """Duplicate a profile with its template, documents, and email payload."""
    c, should_close = _get_connection(conn)
    try:
        source_p = get_profile(profile_id, c)
        if not source_p:
            raise ValueError(f"Source profile {profile_id} not found.")

        # Determine unique duplicate name
        base_name = f"{source_p.name} copy"
        candidate_name = base_name
        counter = 2
        while c.execute("SELECT 1 FROM profiles WHERE LOWER(name) = LOWER(?)", (candidate_name,)).fetchone():
            candidate_name = f"{base_name} {counter}"
            counter += 1

        new_id = f"prof_{uuid.uuid4().hex[:10]}"
        now = datetime.utcnow().isoformat()
        max_order_row = c.execute("SELECT MAX(sort_order) FROM profiles").fetchone()
        next_order = (max_order_row[0] or 0) + 1 if max_order_row else 1

        c.execute("""
            INSERT INTO profiles (id, name, created_at, updated_at, is_default, sort_order, template_text, beruf, email_subject, email_body)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """, (new_id, candidate_name, now, now, next_order, source_p.template_text, source_p.beruf, source_p.email_subject, source_p.email_body))

        # Copy documents
        docs = get_profile_documents(profile_id, conn=c)
        for doc in docs:
            src_file = Path(doc.stored_path)
            new_doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            if src_file.exists():
                dest_dir = get_profile_storage_dir(new_id, doc.doc_type)
                dest_path = dest_dir / src_file.name
                try:
                    shutil.copy2(src_file, dest_path)
                    stored_path = str(dest_path)
                except Exception:
                    stored_path = doc.stored_path
            else:
                stored_path = doc.stored_path

            c.execute("""
                INSERT INTO profile_documents (id, profile_id, doc_type, file_name, stored_path, added_at, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_doc_id, new_id, doc.doc_type, doc.file_name, stored_path, now, doc.sort_order))

        c.commit()
        set_active_profile_id(new_id)
        return Profile(new_id, candidate_name, now, now, False, next_order, source_p.template_text, source_p.beruf, source_p.email_subject, source_p.email_body)
    finally:
        if should_close:
            c.close()


def save_email_payload(profile_id: str, subject: str, body: str, conn: sqlite3.Connection | None = None) -> None:
    """Save email subject and body for a specific profile."""
    c, should_close = _get_connection(conn)
    try:
        now = datetime.utcnow().isoformat()
        c.execute("""
            UPDATE profiles SET email_subject = ?, email_body = ?, updated_at = ? WHERE id = ?
        """, (subject, body, now, profile_id))
        c.commit()
    finally:
        if should_close:
            c.close()


def get_email_payload(profile_id: str, conn: sqlite3.Connection | None = None) -> tuple[str, str]:
    """Retrieve saved email subject and body for a specific profile."""
    p = get_profile(profile_id, conn)
    if p and (p.email_subject or p.email_body):
        return (p.email_subject or "", p.email_body or "")
    return ("", "")


def get_default_email_payload(profile: Profile | None = None) -> tuple[str, str]:
    """Generate default email subject and body tailored to the profile."""
    subject = "Bewerbung um einen Ausbildungsplatz als {{BERUF}}"
    body = (
        "{{ANREDE}}\n\n"
        "gerne möchte ich mich bei {{FIRMA}} um einen Ausbildungsplatz als {{BERUF}} bewerben. "
        "Im Anhang finden Sie meine vollständigen Bewerbungsunterlagen als PDF-Datei.\n\n"
        "Bei Rückfragen stehe ich Ihnen jederzeit gerne zur Verfügung. Ich freue mich, von Ihnen zu hören!\n\n"
        "Mit freundlichen Grüßen\n\n"
        "{{SENDER_NAME}}"
    )
    return (subject, body)


def delete_profile(profile_id: str, conn: sqlite3.Connection | None = None) -> None:
    """Delete profile and all its files. Switch to default if active."""
    c, should_close = _get_connection(conn)
    try:
        p = get_profile(profile_id, c)
        if not p:
            return
        if p.is_default:
            raise ValueError("Default profile cannot be deleted.")

        active_id = get_active_profile_id(c)
        if active_id == profile_id:
            def_p = get_default_profile(c)
            set_active_profile_id(def_p.id)

        # Delete database entries
        c.execute("DELETE FROM profile_documents WHERE profile_id = ?", (profile_id,))
        c.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        c.commit()

        # Delete physical directory
        prof_dir = get_app_data_dir() / "profiles" / profile_id
        if prof_dir.exists():
            shutil.rmtree(prof_dir, ignore_errors=True)
    finally:
        if should_close:
            c.close()


def get_profile_documents(profile_id: str, doc_type: str | None = None, conn: sqlite3.Connection | None = None) -> list[ProfileDocument]:
    """Retrieve documents for a profile."""
    init_db(conn)
    c, should_close = _get_connection(conn)
    try:
        if doc_type:
            rows = c.execute("""
                SELECT id, profile_id, doc_type, file_name, stored_path, added_at, sort_order
                FROM profile_documents
                WHERE profile_id = ? AND doc_type = ?
                ORDER BY sort_order ASC, added_at ASC
            """, (profile_id, doc_type)).fetchall()
        else:
            rows = c.execute("""
                SELECT id, profile_id, doc_type, file_name, stored_path, added_at, sort_order
                FROM profile_documents
                WHERE profile_id = ?
                ORDER BY sort_order ASC, added_at ASC
            """, (profile_id,)).fetchall()

        return [
            ProfileDocument(
                id=r[0],
                profile_id=r[1],
                doc_type=r[2],
                file_name=r[3],
                stored_path=r[4],
                added_at=r[5],
                sort_order=r[6],
            )
            for r in rows
        ]
    finally:
        if should_close:
            c.close()


def get_lebenslauf(profile_id: str, conn: sqlite3.Connection | None = None) -> Optional[ProfileDocument]:
    """Return the CV document for the specified profile."""
    docs = get_profile_documents(profile_id, doc_type="lebenslauf", conn=conn)
    return docs[0] if docs else None


def get_zeugnisse(profile_id: str, conn: sqlite3.Connection | None = None) -> list[ProfileDocument]:
    """Return certificate documents for the specified profile."""
    return get_profile_documents(profile_id, doc_type="zeugnis", conn=conn)


def get_deckblatt(profile_id: str, conn: sqlite3.Connection | None = None) -> Optional[ProfileDocument]:
    """Return the Deckblatt document for the specified profile."""
    docs = get_profile_documents(profile_id, doc_type="deckblatt", conn=conn)
    return docs[0] if docs else None


def set_lebenslauf(profile_id: str, source_path: str, conn: sqlite3.Connection | None = None) -> Optional[ProfileDocument]:
    """Store or replace Lebenslauf PDF for the profile."""
    c, should_close = _get_connection(conn)
    try:
        doc = _store_single_doc(c, profile_id, "lebenslauf", source_path)
        c.commit()
        return doc
    finally:
        if should_close:
            c.close()


def clear_lebenslauf(profile_id: str, conn: sqlite3.Connection | None = None) -> None:
    """Remove Lebenslauf for the profile."""
    c, should_close = _get_connection(conn)
    try:
        # Also clean up disk file
        doc = get_lebenslauf(profile_id, c)
        if doc and Path(doc.stored_path).exists():
            try:
                Path(doc.stored_path).unlink(missing_ok=True)
            except Exception:
                pass
        c.execute("DELETE FROM profile_documents WHERE profile_id = ? AND doc_type = 'lebenslauf'", (profile_id,))
        c.commit()
    finally:
        if should_close:
            c.close()


def set_deckblatt(profile_id: str, source_path: str, conn: sqlite3.Connection | None = None) -> Optional[ProfileDocument]:
    """Store or replace Deckblatt PDF for the profile."""
    c, should_close = _get_connection(conn)
    try:
        doc = _store_single_doc(c, profile_id, "deckblatt", source_path)
        c.commit()
        return doc
    finally:
        if should_close:
            c.close()


def clear_deckblatt(profile_id: str, conn: sqlite3.Connection | None = None) -> None:
    """Remove Deckblatt for the profile."""
    c, should_close = _get_connection(conn)
    try:
        doc = get_deckblatt(profile_id, c)
        if doc and Path(doc.stored_path).exists():
            try:
                Path(doc.stored_path).unlink(missing_ok=True)
            except Exception:
                pass
        c.execute("DELETE FROM profile_documents WHERE profile_id = ? AND doc_type = 'deckblatt'", (profile_id,))
        c.commit()
    finally:
        if should_close:
            c.close()


def set_zeugnisse_paths(profile_id: str, paths: list[str], conn: sqlite3.Connection | None = None) -> list[ProfileDocument]:
    """Update and order Zeugnisse documents for the profile."""
    c, should_close = _get_connection(conn)
    try:
        existing_docs = {d.stored_path: d for d in get_zeugnisse(profile_id, c)}
        c.execute("DELETE FROM profile_documents WHERE profile_id = ? AND doc_type = 'zeugnis'", (profile_id,))

        dest_dir = get_profile_storage_dir(profile_id, "zeugnis")
        new_docs = []
        now = datetime.utcnow().isoformat()

        for idx, p_str in enumerate(paths):
            p = Path(p_str)
            if not p.exists():
                # Record missing file record
                doc_id = f"doc_{uuid.uuid4().hex[:10]}"
                c.execute("""
                    INSERT INTO profile_documents (id, profile_id, doc_type, file_name, stored_path, added_at, sort_order)
                    VALUES (?, ?, 'zeugnis', ?, ?, ?, ?)
                """, (doc_id, profile_id, p.name, str(p), now, idx))
                new_docs.append(ProfileDocument(doc_id, profile_id, "zeugnis", p.name, str(p), now, idx))
                continue

            # Check if file is already inside the profile directory
            try:
                is_internal = p.resolve().is_relative_to(dest_dir.resolve())
            except Exception:
                is_internal = False

            if is_internal:
                dest_file = p
            else:
                dest_file = dest_dir / p.name
                # Avoid collision if different source has same name
                if dest_file.exists() and dest_file.resolve() != p.resolve():
                    dest_file = dest_dir / f"{p.stem}_{uuid.uuid4().hex[:6]}{p.suffix}"
                try:
                    shutil.copy2(p, dest_file)
                except Exception:
                    dest_file = p

            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            c.execute("""
                INSERT INTO profile_documents (id, profile_id, doc_type, file_name, stored_path, added_at, sort_order)
                VALUES (?, ?, 'zeugnis', ?, ?, ?, ?)
            """, (doc_id, profile_id, dest_file.name, str(dest_file), now, idx))
            new_docs.append(ProfileDocument(doc_id, profile_id, "zeugnis", dest_file.name, str(dest_file), now, idx))

        c.commit()
        return new_docs
    finally:
        if should_close:
            c.close()


def clear_zeugnisse(profile_id: str, conn: sqlite3.Connection | None = None) -> None:
    """Clear all Zeugnisse for the profile."""
    c, should_close = _get_connection(conn)
    try:
        z_docs = get_zeugnisse(profile_id, c)
        for d in z_docs:
            p = Path(d.stored_path)
            if p.exists():
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
        c.execute("DELETE FROM profile_documents WHERE profile_id = ? AND doc_type = 'zeugnis'", (profile_id,))
        c.commit()
    finally:
        if should_close:
            c.close()


def clear_all_documents(profile_id: str, conn: sqlite3.Connection | None = None) -> None:
    """Clear Deckblatt, Lebenslauf, and Zeugnisse for the profile."""
    clear_deckblatt(profile_id, conn)
    clear_lebenslauf(profile_id, conn)
    clear_zeugnisse(profile_id, conn)


def save_template_text(profile_id: str, text: str, conn: sqlite3.Connection | None = None) -> None:
    """Save Anschreiben template text for a profile."""
    c, should_close = _get_connection(conn)
    try:
        now = datetime.utcnow().isoformat()
        c.execute("""
            UPDATE profiles SET template_text = ?, updated_at = ? WHERE id = ?
        """, (text, now, profile_id))
        c.commit()
    finally:
        if should_close:
            c.close()


def get_template_text(profile_id: str, conn: sqlite3.Connection | None = None) -> str:
    """Retrieve Anschreiben template text for a profile."""
    p = get_profile(profile_id, conn)
    if p and p.template_text:
        return p.template_text
    # Fallback to default template if empty
    return (
        "{{SENDER_NAME}}\n{{SENDER_ADDRESS}}\n{{SENDER_CITY}}\n"
        "{{SENDER_PHONE}} · {{SENDER_EMAIL}}\n\n"
        "{{FIRMA}}\n{{ADRESSE}}\n{{PLZ}} {{ORT}}\n\n"
        "{{DATUM}}\n\n"
        "Bewerbung um einen Ausbildungsplatz als {{BERUF}}\n\n"
        "{{ANREDE}}\n\n"
        "Mit großem Interesse bewerbe ich mich bei Ihnen als {{BERUF}}.\n\n"
        "Mit freundlichen Grüßen"
    )

# 1.5.0
