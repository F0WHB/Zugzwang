<p align="center">
  <img src="src/ui/assets/logo-mark.png" alt="ZUGZWANG" width="110">
</p>

<h1 align="center">ZUGZWANG</h1>

<p align="center">
  <b>Find jobs. Extract HR emails. Send applications. All in one click.</b>
</p>

<p align="center">
  <a href="https://github.com/whbexc/Zugzwang/releases"><img alt="Download" src="https://img.shields.io/badge/Download-Latest_Release-0A84FF?style=for-the-badge"></a>
</p>

---

## 🚀 Quick Start

ZUGZWANG automates your entire job search and application process in Germany. No coding required.

### 1. Download & Install
- **[Download the latest release here](https://github.com/whbexc/Zugzwang/releases)**.
- **Windows**: Run the `.exe` installer.
- **macOS**: Unzip and drag to Applications. *(If macOS blocks it, open Terminal and run `xattr -cr /Applications/ZUGZWANG.app`)*

### 2. Search for Jobs
Open the app, go to **Search**, and type what you are looking for (e.g., "Software Developer in Berlin"). ZUGZWANG will automatically scrape Google Maps, Ausbildung.de, and official job boards to find companies hiring right now.

### 3. Send Your CV
Go to the **Send** tab. ZUGZWANG has already found the HR emails for you. Just connect your email, attach your CV, and hit **Send All**. The app will safely email everyone one by one.

---

## ✨ Why use this?
- **Zero Excel Sheets**: Everything is saved inside the app.
- **Automatic Emails**: It finds hidden emails on company websites automatically.
- **Safe Sending**: It mimics human typing and takes breaks so your email doesn't get banned.
- **100% Private**: Runs entirely on your computer. Your data never goes to a cloud server.

---

## 📸 Screenshots

| Dashboard | Search |
|-----------|--------|
| <img src="screenshot_dashboard_clean.png" width="400"> | <img src="screenshot_search_clean.png" width="400"> |

| Results | Email Sender |
|---------|--------------|
| <img src="screenshot_results_clean.png" width="400"> | <img src="screenshot_send_clean.png" width="400"> |

---

## 🛠️ Need to run from source?
Are you a developer? Just run:
```bash
git clone https://github.com/whbexc/Zugzwang.git
cd Zugzwang
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
python main.py
```
