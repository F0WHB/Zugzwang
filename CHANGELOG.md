# Changelog

All notable changes and technical release notes for ZUGZWANG are documented in this file.

---

## 1.1.2 (Build 10)

### In-App Update Engine
- **Full In-App Software Update Workflow** — Integrated a complete in-app modal experience for discovering, previewing, and installing updates without forcing external browser redirects. Features live progress percentage, release notes viewer, and automated handoff to the platform updater.
- **Dynamic Settings Card State** — The Settings update card automatically switches to a prominent "UPDATE NOW" call-to-action when updates are detected, and shows active verification details when running the latest build.
- **Resilient HTTP Download Stream** — Hardened update asset streaming against non-standard or missing `Content-Length` headers, preventing unexpected download exceptions.

### UI & Bug Fixes
- **Manual Recipient Localization Resolution** — Fixed `AttributeError: 'ManualRecipientDialog' object has no attribute '_language'` when opening the manual recipient dialog in the Send tab.
- **Native Pro-Apple Attachments & Zeugnisse Dialog** — Re-architected certificate management with an interactive macOS card modal, featuring drag-and-drop reordering, fluid physics animations, instant PDF previewing, and inline document removal.
- **Redesigned macOS Toast Notification System** — Introduced a floating native macOS card (`#2C2C2E`, 14px radius, 0.5px border, 400px fixed width, zero shadow) with role-colored badges, clean typography, smooth physics animations, and persistent top-right window anchoring.
- **Edit Workspace Visual Polish & Signature Cleanliness** — Modernized the editor layout with refined typography and spacing, streamlined profile and sender credential cards, and ensured signature previews and rendered letter identities remain pristine without template message bleed.
- **FilterMenu Scroll Area & Typography** — Integrated `QScrollArea` inside `FilterMenu` to enable fluid scrolling for large city/source lists, removed horizontal scrollbar clutter, and increased table font size by 2px for improved data density and readability.
- **Settings Card Typography Polish** — Increased font size of settings cards titles from 10px to 12px, enforced PT Root UI font with uppercase transform for consistent card headers, and corrected button style factory references.

### Sending Engine & Attachments
- **Fail-Proof Lead PDF & Attachment Pipeline** — Overhauled email message construction with case-insensitive and wildcard recipient lead queries, fuzzy PDF candidate matching in the exports directory, and direct fallback to loaded Lebenslauf to completely eliminate `FileNotFoundError` during campaign dispatches.
- **Non-Destructive Multi-Attachment Delivery** — Manual attachments added in the Send tab now safely complement dynamically generated lead cover letters and dossiers instead of suppressing them.
- **Dynamic On-The-Fly Certificate Merging** — In `letter_cv_certs` mode, certificates are automatically compiled in-memory from saved settings if pre-rendered Zeugnisse files are not present on disk, ensuring certificates are never dropped.
- **Safe Sent-PDF Lifecycle Management** — Rebuilt cleanup routines to prevent premature deletion of company files when multiple leads from the same organization exist in the sending queue.
- **Unified Outreach Trial Quota** — Standardized trial limits across the platform to 20 Anschreiben cover letters and 20 email deliveries, eliminating quota discrepancies between exports and campaign outreach.
- **Email Sender Toast Notification Integration** — Corrected `InfoBarPosition` import and anchor references in `email_sender_page.py` ensuring non-blocking delivery status popups.

### PDF Generation & Reliability
- **Safe XML Character Escaping in ReportLab** — Resolved ReportLab `Paragraph` parser crashes caused by unescaped XML/HTML entities (`&`, `<`, `>`, tags, and placeholders like `<br>`, `<Ansprechpartner>`, `GmbH & Co. KG`) via strict `_safe_xml()` escaping.
- **Robust Canvas Fallback Renderer** — Integrated a resilient ReportLab Canvas fallback so document generation never crashes or swallows PDFs during batch export.
- **Live In-Flight Editor State Synchronization** — Active in-flight editor text is automatically captured during batch exports for the currently selected lead, guaranteeing unsaved edits are never lost.
- **Watchdog Memory Fault Resolution** — Eliminated unsafe cross-thread stack frame inspections (`sys._current_frames`) on Apple Silicon / macOS ARM64 to guarantee complete runtime stability.
- **Zero-Lag Asyncio & SQLite Performance** — Removed runtime frame inspection overhead from release builds, restoring native C-speed execution and fluid responsiveness during high-throughput scraping runs.
- **Smart Update Version Comparison Engine** — Re-engineered version comparator to strict SemVer standards, ensuring pre-release versions reliably detect and prompt for stable upgrade releases.

### Scraping Engine
- **Headed CAPTCHA Solver Bridge** — Fixed event callback parameter handling so the real browser window launches immediately, focuses in front, and synchronizes cookies seamlessly when security challenges appear on Jobsuche or Google Maps.
- **Jobsuche Scraper Re-Architecture** — Major extraction overhaul of `jobsuche_scraper.py` with multi-tier API/DOM fallback paths, enhanced deep detail extraction, and robust pagination handling.
- **Google Maps Real-Time Scraper Streaming** — Re-architected lead extraction from blocking batches to concurrent streaming via `asyncio.as_completed`, displaying discovered leads in the UI instantly without freezing.
- **Website Crawler Deep Enrichment** — Enhanced `website_crawler.py` with expanded heuristic discovery for careers, imprint, and direct contact endpoints.

---

## 1.1.0 Beta5.1

### UI
- **Project Obsidian UI Overhaul** — Full aesthetic refactor aligning the entire application (Settings, Dashboard, Monitor, Edit) with Apple macOS System Preferences dark theme standards (`#1C1C1E`).
- **Unified Component Outlines** — Standardized all card borders (SectionCards and small metric cards) to a consistent, subtle `0.5px solid rgba(255, 255, 255, 0.1)` across all views.
- **Activation & Licensing Dialog Polish** — Rebuilt with native glassmorphism styling, synchronized button icon colors with label typography, dedicated grey 'Reset to Trial', and vibrant green 'Activate' CTA.
- **Dashboard Action Hierarchy** — Streamlined dashboard controls with a primary green 'Support Us' action and removed redundant export triggers.
- **Monitor Page Seamless Integration** — Background linked directly to the global Obsidian palette, removing clunky inner card shadows for a clean flat surface.
- **Destructive Action Safety** — Distinct solid red warning buttons for high-risk operations (such as 'Purge Sent') to prevent inadvertent data loss.
- **Search History Dropdown macOS Ghost Shadow** — Eliminated the rectangular bounding box on macOS transparent popups; redesigned 'Clear History' into a clean, centered text-link.
- **macOS Apple Dock Icon Polish** — Scaled down squircle icon to 82% canvas width with standard Apple Dock padding to match the exact visual weight and dimensions of native macOS app icons.
- **Edit Page Redesign** — Comprehensive rewrite of the editor UI for better responsiveness, cleaner spacing, and strict adherence to the premium macOS dark theme.
- **Visual Polish** — Fixed dark artifacting behind popup text and resolved UI layout overflows across the Settings and Email Sender pages.
- **Intrusive Popup Removal** — Removed hard-blocking 'Activate Pro' dialogs from all export and email functions, replacing them with elegant non-blocking banners.
- **Recipient Queue Inline Editing & Manual Add Dialog** — Added solid in-row editor rendering for recipient modifications and a custom-styled manual recipient addition dialog.

### Scraping Engine
- **Azubiyo & Das Örtliche Scrapers** — New extraction engines tailored for dual study programs and local German regional directories.
- **Ausbildung.de Pagination & Engine Upgrade** — Rebuilt extraction engine supporting robust URL-based radius parameters and true infinite-scroll pagination for limitless lead extraction.
- **Radius Accuracy** — Search URLs precisely match their configured catchment area across all data sources.
- **Smart Decision-Maker NLP Extraction** — Automatically detects and extracts German names from role titles (*Pflegedienstleitung*, *Ansprechpartner für Bewerbungen*, *HR Manager*) across Impressum and team pages.
- **Multi-Email Extraction with Zero Duplicates** — Scraper captures unique department and employee email addresses from employer websites while dropping duplicate email addresses across listings.
- **Extended Multi-Browser Engine** — Overhauled browser automation with native detection and execution support for Safari, Brave, Arc, Dia, and custom Chromium/WebKit installations.
- **Scraping Latency Optimizations** — Reduced search latency by stripping out legacy hardcoded delays and streamlining intelligent browser timeouts.
- **Jobsuche Filter & CAPTCHA Recovery** — Strengthened Jobsuche filter, radius, Detailansicht, and Kontakt/CAPTCHA recovery behavior with duplicate headed CAPTCHA solver suppression and cleaner per-job shutdown handling.
- **Packaged Google Maps Search Fallback** — Hardened search fallback mechanisms for Google Maps extraction in standalone bundled environments.

### Sending Engine
- **Gmail Anti-Lockdown Protection** — Comprehensive SMTP throttling engine featuring a safe 45s+ velocity floor, human-like randomized jitter (+5-18s), automatic 2.5-minute micro-batch coffee breaks every 12 emails, and smart 5-minute backoff on server rate-limit and throttling responses (codes 421, 450, 451, 452, 550).
- **Send Tab Attachment Isolation** — Manually attached files in the Send tab are strictly isolated, preventing unexpected Anschreiben PDFs from being automatically merged into outbound emails.
- **Pre-Send DNS Domain Verification** — Verifies recipient email domain DNS resolution before sending campaigns to filter out dead or unreachable domains and protect sender reputation.
- **Always-On HTML Email Styling & Inline Signature Embedding** — Automatically formats outbound emails with crisp paragraphs, clean bullet lists, German grammar placeholder replacements (*'in Ihrer Einrichtung'*), and embeds handwritten blue signatures inline at the bottom of the message.
- **Dynamic Anschreiben Personalization** — Generates tailored, personalized cover letters for every individual lead in the campaign queue.
- **Auto-Clamped Broadcasting & Fail-Forward Exports** — Mass email broadcasts automatically clamp to remaining quotas, seamlessly falling back to raw uploaded resumes when daily custom PDF limits are reached without halting the workflow.
- **Sender Profiles with Autofill** — Saved Gmail identities and credentials with automatic profile switching and field auto-fill.
- **Message-Aware Resend Logic** — Resend logic allows sending to the same email address when the message content has changed while preventing accidental exact duplicates.
- **Fresh-Session Delivery Hardening** — Establishes fresh, isolated SMTP sessions per recipient to ensure delivery reliability.

### Reliability & Storage
- **Automated Sent-PDF & Attachment Disk Cleanup** — Automatically deletes company-specific generated cover letters from disk immediately after SMTP delivery confirmation to keep export directories slim while permanently preserving uploaded CV templates and lead spreadsheets; deleting an uploaded PDF in the editor immediately purges raw copies and cached batch PDFs from disk.
- **macOS Sleep Prevention (`WakeLock`)** — Automatically prevents Mac and Windows systems from sleeping during long scraping jobs, PDF batch generation, and email outreach broadcasts.
- **Consecutive Multi-Search Reliability** — Eliminates the need to restart the application between consecutive searches through isolated worker event loops and bounded 5-second browser session teardowns.
- **Atomic Settings Persistence & State Recovery** — Atomic settings persistence with backup recovery for license state, SMTP setup, send drafts, sender profiles, and machine ID recovery from local hardware files.
- **One-Time Upgrade State Migration** — Safely resets stale cached local UI/app state across version updates while strictly preserving scraped leads, sent-email history, drafts, and Pro activation.
- **Internal App Build Tracking** — Independent build version tracking allowing hotfix deployments even when visible release strings remain identical.
- **Telemetry Noise Reduction** — Aggressively filtered low-level PyPDF warning noise ('Ignoring wrong pointing object') and internal startup traces from user activity streams.
- **Startup Resource Optimization** — Reduced startup and dashboard refresh pressure to improve Google Maps launch responsiveness and avoid false temporary freeze behavior.

<!-- 1.1.2.2 -->
