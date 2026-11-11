#!/usr/bin/env python3
"""
ZUGZWANG - Professional Demo Environment Launcher
Sets up an isolated, rich demo environment (~/.config/ZUGZWANG_DEMO) with:
- 3 Profiles (Softwareentwickler, Data Scientist, DevOps Engineer)
- Full Bewerbungsunterlagen (Deckblatt, Anschreiben, Lebenslauf, Zeugnisse) all ready & green
- 3 Configured Sender Pool Accounts with balanced quotas & rotation
- Pre-filled Send tab (Sender identity, App password, From Name, Subject, Body)
- 6 Realistic German Company Leads in the queue
- Fully activated Pro license (no popups)

Does NOT touch ~/.config/ZUGZWANG.
"""

import os
import sys
import uuid
import shutil
import sqlite3
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = Path.home() / ".config" / "ZUGZWANG_DEMO"


def create_sample_pdf(path: Path, title: str):
    """Write a minimal valid PDF byte sequence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 44 >> stream\n"
        b"BT /F1 12 Tf 72 712 Td (" + title.encode("ascii", "replace") + b") Tj ET\n"
        b"endstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000216 00000 n \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n310\n%%EOF\n"
    )
    path.write_bytes(content)


def compute_machine_and_license():
    """Derive stable machine_id and valid license key."""
    computer = os.environ.get("COMPUTERNAME", "").strip()
    user = os.environ.get("USERNAME", "").strip()
    home = str(Path.home()).strip()
    seed = f"{computer}|{user}|{home}|{os.name}|{uuid.getnode()}"
    raw_id = seed or f"fallback|{os.name}|{uuid.getnode()}"
    mid = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16].upper()

    salt_hash = "4848e7c8d786a16987ec133df5b7da6e4abe69460060d099bdfd90279cd9ec96"
    raw_payload = f"{mid}{salt_hash}"
    sig = hashlib.sha256(raw_payload.encode()).hexdigest()[:12].upper()
    blocks = [sig[i:i+4] for i in range(0, len(sig), 4)]
    key = f"ZUG-{'-'.join(blocks)}"
    return mid, key


def setup_demo_environment():
    print(f"[*] Initializing pristine demo environment at: {DEMO_DIR}")
    
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR, ignore_errors=True)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    data_dir = DEMO_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    docs_dir = DEMO_DIR / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create sample documents
    deckblatt_pdf = docs_dir / "Deckblatt_Alex_Richter.pdf"
    lebenslauf_pdf = docs_dir / "Lebenslauf_Alex_Richter.pdf"
    zeugnisse_pdf = docs_dir / "Zeugnisse_Alex_Richter.pdf"
    dossier_pdf = docs_dir / "Bewerbungsunterlagen_Alex_Richter.pdf"

    create_sample_pdf(deckblatt_pdf, "Deckblatt - Alex Richter")
    create_sample_pdf(lebenslauf_pdf, "Lebenslauf - Alex Richter")
    create_sample_pdf(zeugnisse_pdf, "Zeugnisse - Alex Richter")
    create_sample_pdf(dossier_pdf, "Vollstaendige Bewerbungsmappe - Alex Richter")

    mid, license_key = compute_machine_and_license()

    # Persist machine_id.txt
    (DEMO_DIR / "machine_id.txt").write_text(mid, encoding="utf-8")

    # 2. Pre-generate settings.json
    now_today = date.today().isoformat()
    sender_profiles = [
        {
            "id": "pool_acc_1",
            "email": "alex.richter.jobs@gmail.com",
            "password": "app_pwd_alpha_921",
            "name": "Alex Richter (Outreach)",
            "is_enabled": True,
            "daily_limit": 100,
            "sent_today": 18,
            "last_sent_date": now_today,
        },
        {
            "id": "pool_acc_2",
            "email": "alex.richter.tech@gmail.com",
            "password": "app_pwd_beta_419",
            "name": "Alex Richter (Direct)",
            "is_enabled": True,
            "daily_limit": 80,
            "sent_today": 12,
            "last_sent_date": now_today,
        },
        {
            "id": "pool_acc_3",
            "email": "alex.richter.career@gmail.com",
            "password": "app_pwd_gamma_771",
            "name": "Alex Richter (Careers)",
            "is_enabled": True,
            "daily_limit": 60,
            "sent_today": 5,
            "last_sent_date": now_today,
        },
    ]

    body_template = (
        "{{ANREDE}}\n\n"
        "mit großem Interesse bewerbe ich mich bei Ihnen als {{BERUF}}.\n\n"
        "Als erfahrener Entwickler mit fundierten Kenntnissen in moderner Softwarearchitektur, "
        "Python und performanten Systemen möchte ich Ihr Team tatkräftig unterstützen.\n\n"
        "Anbei sende ich Ihnen meine vollständigen Bewerbungsunterlagen zur Durchsicht.\n\n"
        "Über die Gelegenheit zu einem persönlichen Gespräch freue ich mich sehr.\n\n"
        "Mit freundlichen Grüßen\n\n"
        "Alex Richter\n"
        "alex.richter.bewerbung@gmail.com | +49 176 89201452 | München"
    )

    settings_payload = {
        "is_activated": True,
        "license_key": license_key,
        "machine_id": mid,
        "app_language": "de",
        "theme": "dark",
        "last_seen_version": "1.2.2",
        "email_smtp_host": "smtp.gmail.com",
        "email_smtp_port": "587",
        "email_smtp_user": "alex.richter.bewerbung@gmail.com",
        "email_smtp_pass": "app_pwd_primary_882",
        "email_from_name": "Alex Richter",
        "email_reply_to": "alex.richter.bewerbung@gmail.com",
        "email_subject": "Bewerbung als Softwareentwickler - Alex Richter",
        "email_body": body_template,
        "email_body_html": True,
        "email_interval": "45-60",
        "email_rotation_mode": "pairs",
        "email_rotation_interval": 45,
        "email_sender_profiles": sender_profiles,
        "bewerbung_export_mode": "full",
        "bewerbung_deckblatt_path": str(deckblatt_pdf),
        "bewerbung_lebenslauf_path": str(lebenslauf_pdf),
        "bewerbung_zeugnisse_paths": json.dumps([str(zeugnisse_pdf)]),
        "last_active_profile_id": "prof_dev",
    }

    settings_file = DEMO_DIR / "settings.json"
    settings_file.write_text(json.dumps(settings_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. SQLite Database: app_memory.db
    db_path = data_dir / "app_memory.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Profiles table
    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
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

    # Profile documents table
    c.execute("""
        CREATE TABLE IF NOT EXISTS profile_documents (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            added_at TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)

    # Settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Leads table
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            source_type TEXT,
            company_name TEXT,
            job_title TEXT,
            category TEXT,
            email TEXT,
            email_source_page TEXT,
            phone TEXT,
            website TEXT,
            contact_person TEXT,
            address TEXT,
            city TEXT,
            region TEXT,
            postal_code TEXT,
            country TEXT,
            rating REAL,
            review_count INTEGER,
            description TEXT,
            publication_date TEXT,
            source_url TEXT,
            maps_url TEXT,
            search_query TEXT,
            scraped_at TEXT,
            notes TEXT
        )
    """)

    # Letter state table with full schema
    c.execute("""
        CREATE TABLE IF NOT EXISTS letter_state (
            lead_id TEXT PRIMARY KEY,
            generated_at TEXT,
            edited_at TEXT,
            sent_at TEXT,
            letter_text TEXT,
            previous_text TEXT,
            last_saved_ts TEXT,
            is_discarded INTEGER DEFAULT 0,
            tracking_id TEXT,
            opened_at TEXT,
            open_count INTEGER DEFAULT 0,
            profile_id TEXT DEFAULT ''
        )
    """)

    # Store Profile Documents in DB
    now_iso = datetime.now().isoformat()
    prof_docs = [
        ("doc_db_1", "prof_dev", "deckblatt", deckblatt_pdf.name, str(deckblatt_pdf), now_iso, 0),
        ("doc_lv_1", "prof_dev", "lebenslauf", lebenslauf_pdf.name, str(lebenslauf_pdf), now_iso, 0),
        ("doc_zg_1", "prof_dev", "zeugnis", zeugnisse_pdf.name, str(zeugnisse_pdf), now_iso, 0),
    ]
    c.executemany("INSERT INTO profile_documents VALUES (?, ?, ?, ?, ?, ?, ?)", prof_docs)

    # Sender settings in SQLite
    db_settings = [
        ("sender_name", "Alex Richter"),
        ("sender_email", "alex.richter.bewerbung@gmail.com"),
        ("sender_phone", "+49 176 89201452"),
        ("sender_city", "München"),
        ("sender_beruf", "Softwareentwickler"),
        ("active_profile_id", "prof_dev"),
        ("bewerbung_deckblatt_path", str(deckblatt_pdf)),
        ("bewerbung_lebenslauf_path", str(lebenslauf_pdf)),
        ("bewerbung_zeugnisse_paths", json.dumps([str(zeugnisse_pdf)])),
    ]
    c.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", db_settings)

    # Templates
    template_dev = (
        "{{SENDER_NAME}}\n\n"
        "{{SENDER_EMAIL}} | {{SENDER_PHONE}}\n"
        "{{SENDER_CITY}}, {{DATUM}}\n\n\n"
        "zu Händen von <b>{{FIRMA}}</b>\n"
        "{{ADRESSE}}, {{PLZ}} {{ORT}}\n\n\n"
        "<b>Bewerbung als {{BERUF}}</b>\n\n"
        "<b>{{ANREDE}}</b>\n\n"
        "mit großem Interesse verfolge ich die technologische Ausrichtung und Innovationskraft von <b>{{FIRMA}}</b>. "
        "Als erfahrener Entwickler im Bereich moderner Python-Entwicklung, performanter Desktop-Architekturen und cloudbasierter Dienste "
        "möchte ich meine Begeisterung für sauberen, wartbaren Code in Ihr Entwicklungsteam einbringen.\n\n"
        "In meinen bisherigen Projekten habe ich skalierbare Anwendungen entworfen, anspruchsvolle UI/UX-Systeme mit Qt/PySide realisiert "
        "und automatisierte CI/CD-Pipelines etabliert. Zuverlässigkeit, strukturierte Teamarbeit und kontinuierliches Lernen stehen für mich an erster Stelle.\n\n"
        "Ich freue mich über die Einladung zu einem persönlichen Vorstellungsgespräch.\n\n"
        "Mit freundlichen Grüßen\n\n"
        "Alex Richter\n"
    )

    template_data = (
        "{{SENDER_NAME}}\n\n"
        "{{SENDER_EMAIL}} | {{SENDER_PHONE}}\n"
        "{{SENDER_CITY}}, {{DATUM}}\n\n\n"
        "<b>{{FIRMA}}</b>\n"
        "{{ADRESSE}}, {{PLZ}} {{ORT}}\n\n\n"
        "<b>Initiativbewerbung als Data Scientist</b>\n\n"
        "<b>{{ANREDE}}</b>\n\n"
        "Daten sind das Fundament zukunftsfähiger Unternehmensentscheidungen. Mit Freude bewerbe ich mich bei <b>{{FIRMA}}</b>, "
        "um analytische Methoden und Machine Learning Modelle direkt in Ihre Geschäftsprozesse zu integrieren.\n\n"
        "Mit freundlichen Grüßen\n\n"
        "Alex Richter\n"
    )

    template_devops = (
        "{{SENDER_NAME}}\n\n"
        "{{SENDER_EMAIL}} | {{SENDER_PHONE}}\n"
        "{{SENDER_CITY}}, {{DATUM}}\n\n\n"
        "<b>{{FIRMA}}</b>\n"
        "{{ADRESSE}}, {{PLZ}} {{ORT}}\n\n\n"
        "<b>Bewerbung als DevOps & Cloud Engineer</b>\n\n"
        "<b>{{ANREDE}}</b>\n\n"
        "effiziente Infrastruktur und unterbrechungsfreie Deployments sind der Schlüssel für moderne Softwareprodukte. "
        "Gerne unterstütze ich <b>{{FIRMA}}</b> bei der Automatisierung und Skalierung Ihrer Cloud-Systeme.\n\n"
        "Mit freundlichen Grüßen\n\n"
        "Alex Richter\n"
    )

    profiles = [
        ("prof_dev", "Softwareentwickler", now_iso, now_iso, 1, 0, template_dev, "Softwareentwickler", "Bewerbung als {{BERUF}} - Alex Richter", ""),
        ("prof_data", "Data Scientist", now_iso, now_iso, 0, 1, template_data, "Data Scientist", "Bewerbung als {{BERUF}} - Alex Richter", ""),
        ("prof_devops", "DevOps Engineer", now_iso, now_iso, 0, 2, template_devops, "DevOps Engineer", "Bewerbung als {{BERUF}} - Alex Richter", ""),
    ]
    c.executemany("INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", profiles)

    # Leads
    leads = [
        (
            "lead_01", "maps", "BMW Group", "Senior Python & Cloud Engineer", "Automotive / Tech",
            "karriere@bmwgroup.com", "https://bmwgroup.jobs", "+49 89 3820", "https://www.bmwgroup.com",
            "Dr. Markus Weber", "Petuelring 130", "München", "Bayern", "80788", "Deutschland",
            4.8, 1420, "Führender Premiumhersteller von Automobilen und Mobilitätsdienstleistungen.",
            "2026-10-18", "https://bmwgroup.jobs/de/python-engineer", "", "Python Developer München",
            now_iso, "Top-Arbeitgeber in Bayern, flexible Arbeitszeiten"
        ),
        (
            "lead_02", "maps", "Siemens AG", "Software Engineer - Industrial IoT", "Technology / Automation",
            "jobs.siemens@siemens.com", "https://jobs.siemens.com", "+49 30 3860", "https://www.siemens.com",
            "Frau Sabine Keller", "Werner-von-Siemens-Straße 1", "München", "Bayern", "80333", "Deutschland",
            4.7, 980, "Globales Technologieunternehmen mit Fokus auf Industrie und Infrastruktur.",
            "2026-10-19", "https://jobs.siemens.com/de/iot-dev", "", "Softwareentwickler Industrie München",
            now_iso, "Großes Team für industrielle Automatisierung"
        ),
        (
            "lead_03", "maps", "SAP SE", "Full Stack Software Developer", "Enterprise Software",
            "recruiting.germany@sap.com", "https://jobs.sap.com", "+49 6227 747474", "https://www.sap.com",
            "Herr Christian Bauer", "Dietmar-Hopp-Allee 16", "Walldorf", "Baden-Württemberg", "69190", "Deutschland",
            4.6, 2150, "Marktführer für Unternehmenssoftware und Cloud-Lösungen.",
            "2026-10-17", "https://jobs.sap.com/fullstack-dev", "", "Full Stack Developer",
            now_iso, "Hervorragende Weiterbildungsmöglichkeiten"
        ),
        (
            "lead_04", "maps", "Robert Bosch GmbH", "Python / Embedded Software Developer", "Engineering / Mobility",
            "bewerbung@bosch.com", "https://www.bosch.de/karriere", "+49 711 8110", "https://www.bosch.de",
            "Frau Dr. Julia Hoffmann", "Robert-Bosch-Platz 1", "Gerlingen-Schillerhöhe", "Baden-Württemberg", "70839", "Deutschland",
            4.7, 1830, "International führendes Technologie- und Dienstleistungsunternehmen.",
            "2026-10-16", "https://bosch.de/python-embedded", "", "Python Developer Stuttgart",
            now_iso, "Starke F&E Kultur"
        ),
        (
            "lead_05", "maps", "Celonis SE", "Core Platform Engineer", "SaaS / Process Mining",
            "careers@celonis.com", "https://www.celonis.com/careers", "+49 89 41617260", "https://www.celonis.com",
            "Herr Felix Sommer", "Theresienstraße 6", "München", "Bayern", "80333", "Deutschland",
            4.9, 410, "Pionier im Bereich Process Intelligence und Enterprise AI.",
            "2026-10-19", "https://celonis.com/careers/core-platform", "", "Platform Engineer München",
            now_iso, "Modernes Tech-Stack, dynamisches Umfeld"
        ),
        (
            "lead_06", "maps", "Personio SE & Co. KG", "Python Infrastructure Engineer", "HR Tech",
            "joinus@personio.de", "https://www.personio.de/karriere", "+49 89 12501005", "https://www.personio.de",
            "Frau Laura Becker", "Seidlstraße 24", "München", "Bayern", "80335", "Deutschland",
            4.8, 320, "Führende europäische HR-Software für den Mittelstand.",
            "2026-10-20", "https://personio.de/careers/infra", "", "Backend Developer München",
            now_iso, "Exzellente Kultur, zentrale Lage in München"
        ),
    ]
    c.executemany("INSERT INTO leads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", leads)

    # Pre-generate letter states for all leads so they are in 'ready' state
    letter_states = []
    for lead in leads:
        lid, _, comp, job, _, _, _, _, _, contact, addr, city, _, plz, _, _, _, _, _, _, _, _, _, _ = lead
        salutation = f"Sehr geehrte(r) {contact}," if contact else "Sehr geehrte Damen und Herren,"
        txt = template_dev.replace("{{FIRMA}}", comp).replace("{{BERUF}}", job).replace("{{ANREDE}}", salutation)
        txt = txt.replace("{{ADRESSE}}", addr).replace("{{PLZ}}", plz).replace("{{ORT}}", city)
        txt = txt.replace("{{SENDER_NAME}}", "Alex Richter").replace("{{SENDER_EMAIL}}", "alex.richter.bewerbung@gmail.com")
        txt = txt.replace("{{SENDER_PHONE}}", "+49 176 89201452").replace("{{SENDER_CITY}}", "München").replace("{{DATUM}}", "20. Oktober 2026")
        letter_states.append((
            lid, now_iso, "", "", txt, "", now_iso, 0, "", "", 0, "prof_dev"
        ))
    c.executemany("INSERT INTO letter_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", letter_states)

    conn.commit()
    conn.close()

    print("[+] Demo environment successfully populated:")
    print("    - Profiles: Softwareentwickler (Default), Data Scientist, DevOps Engineer")
    print("    - Application Papers: Deckblatt, Lebenslauf, Zeugnisse, Anschreiben (all ready)")
    print("    - Sender Pool: 3 configured accounts (Outreach, Direct, Careers) with rotation")
    print("    - Send Page: Pre-filled Identity, App password, Name, Subject, and Body")
    print("    - Leads Queue: 6 German technology companies (BMW, Siemens, SAP, Bosch, Celonis, Personio)")


def main():
    setup_demo_environment()
    print("\n[>] Launching ZUGZWANG in Demo Mode...\n")

    env = os.environ.copy()
    env["ZUGZWANG_DATA_DIR"] = str(DEMO_DIR)

    # Launch in clean child process
    subprocess.run([sys.executable, str(PROJECT_ROOT / "main.py")], env=env)


if __name__ == "__main__":
    main()

# 1.5.2
