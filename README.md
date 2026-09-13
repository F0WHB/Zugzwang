<p align="center">
  <img src="src/ui/assets/logo-mark.png" alt="ZUGZWANG" width="100">
</p>

<h1 align="center">ZUGZWANG</h1>

<p align="center">
  <b>Find German companies hiring right now. Extract HR contacts. Send tailored outreach.</b><br>
  <i>All in 3 clicks. Zero spreadsheets. Zero manual searching.</i>
</p>

<p align="center">
  <a href="https://github.com/whbexc/Zugzwang/releases"><img alt="Download" src="https://img.shields.io/badge/Download-Latest%20Release%20(v1.1.1)-0A84FF?style=for-the-badge&logo=apple&logoColor=white"></a>
  <img alt="Platform" src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-30D158?style=for-the-badge">
  <img alt="Privacy" src="https://img.shields.io/badge/Data-100%25%20Local-FF9F0A?style=for-the-badge">
</p>

---

## ⚡ 3-Minute Quickstart (No Technical Skills Needed)

ZUGZWANG is a desktop app designed to put your application & outreach workflow on autopilot.

```
 [1. Search Target] ──▶ [2. Auto-Extract HR Emails] ──▶ [3. One-Click Send]
   "IT in Munich"          Deep crawls company websites     Personalized & human-paced
```

### 1. Download & Open
- **[👉 Download the Latest Version Here](https://github.com/whbexc/Zugzwang/releases)**
- **Windows**: Double-click `ZUGZWANG_Setup_1.1.1.exe` and install.
- **macOS**: Unzip `ZUGZWANG_macOS_1.1.1.zip`, drag to **Applications**.  
  *(If macOS says unverified, run this once in Terminal: `xattr -cr /Applications/ZUGZWANG.app`)*

### 2. Find Leads in 10 Seconds
1. Go to the **Search** tab.
2. Select your sources (e.g. *Bundesagentur für Arbeit*, *Ausbildung.de*, *Google Maps*).
3. Type your target keyword (e.g. `Fachinformatiker`) and city (e.g. `Hamburg`).
4. Click **Start Scraping**.

### 3. Send Outreach Effortlessly
1. Head over to the **Send** tab.
2. Enter your email credentials (works seamlessly with Gmail App Passwords).
3. Attach your resume/CV and hit **Send All**.
4. ZUGZWANG simulates human pauses between emails so your account stays 100% safe.

---

## 💡 Why ZUGZWANG?

| The Painful Manual Way | The ZUGZWANG Way |
| :--- | :--- |
| Browsing 50+ job portals and tabs daily | One unified search across all top German platforms |
| Digging through *Impressum* & *Kontakt* pages for emails | Automated deep scanner grabs verified HR contacts |
| Copying and pasting data into messy Excel sheets | Clean in-app database with one-click export (Excel/CSV) |
| Sending emails manually and risking spam flags | Smart queue with anti-ban humanized timing & auto-breaks |
| Paying monthly subscriptions for scraper tools | **Free, standalone desktop app running entirely on your machine** |

---

## 📸 Sneak Peek

<div align="center">

| 1. Instant Lead Discovery | 2. Verified Contact Results |
|:---:|:---:|
| <img src="screenshot_search_clean.png" width="420" alt="Search"> | <img src="screenshot_results_clean.png" width="420" alt="Results"> |

| 3. Application & Cover Letter Editor | 4. Automated Safe Broadcast |
|:---:|:---:|
| <img src="screenshot_edit_clean.png" width="420" alt="Editor"> | <img src="screenshot_send_clean.png" width="420" alt="Email Sender"> |

</div>

---

## 🔒 100% Private & Local

- **No Cloud Tracking**: Your candidate data, leads, contacts, and emails stay on your hard drive.
- **Direct Connection**: Emails are sent straight from your machine via SMTP. No third-party servers see your messages.
- **Anti-Lockout Protection**: Built-in coffee breaks (pauses between batches) and random delays protect your sender reputation.

---

## 🛠️ For Developers (Run from Source)

If you'd rather run the source code directly:

```bash
# 1. Clone & enter
git clone https://github.com/whbexc/Zugzwang.git
cd Zugzwang

# 2. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1

# 3. Install requirements & Playwright browser
pip install -r requirements.txt
playwright install chromium

# 4. Launch app
python main.py
```

---

## 📝 Recent Updates

- **v1.1.1**:
  - 🚀 Optimized headless Chromium setup for frictionless launch across macOS and Windows.
  - 🛠️ Fixed UI notification toasts in the broadcast engine.
  - ⚡ Enhanced deep *Impressum* detection accuracy for German company domains.

---

<p align="center">
  <sub>Built for productivity and high-impact German market outreach.</sub><br>
  <sub><b>ZUGZWANG</b> &copy; 2026. All rights reserved.</sub>
</p>
