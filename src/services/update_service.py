"""
ZUGZWANG - Update Service
Integrates with GitHub Releases to check for and download updates.
"""

import os
import sys
import httpx
import logging
import re
import socket
from PySide6.QtCore import QObject, Signal, QThread
from ..core.config import config_manager

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)(.*)$")
_BUILD_RE = re.compile(r"(?:build|\bb)[\s:#-]?\s*(\d+)", re.IGNORECASE)



def _parse_version_parts(raw: str) -> tuple[tuple[int, ...], str]:
    text = (raw or "").strip()
    match = _VERSION_RE.match(text)
    if not match:
        return (0,), ""
    numeric = tuple(int(part) for part in match.group(1).split("."))
    suffix = re.sub(r"[\s\-_.]+", "", match.group(2).strip().lower())
    return numeric, suffix


def _is_build_suffix(s: str) -> bool:
    return bool(re.match(r"^(?:build|b)\d*$", s.strip().lower()))


def _compare_suffixes(current_suffix: str, latest_suffix: str) -> int:
    if current_suffix == latest_suffix:
        return 0

    c_is_build = _is_build_suffix(current_suffix)
    l_is_build = _is_build_suffix(latest_suffix)

    # Build suffixes (e.g. build10, b10) represent a newer build than an un-suffixed base version
    if not current_suffix and l_is_build:
        return -1  # latest (build10) is newer than current (base stable)
    if not latest_suffix and c_is_build:
        return 1   # current (build10) is newer than latest (base stable)

    # A version without suffix is a final stable release.
    # A version with a pre-release suffix (beta, alpha, rc) is older than stable.
    if current_suffix and not latest_suffix:
        return -1  # current (beta) is older than latest (stable)
    if latest_suffix and not current_suffix:
        return 1   # current (stable) is newer than latest (beta)

    # Both have suffixes. Split into text and numeric parts (e.g. 'beta', 6 or 'build', 10)
    def split_sub(s):
        match = re.match(r"^([a-zA-Z]+)(\d*)$", s)
        if match:
            return match.group(1), int(match.group(2)) if match.group(2) else 0
        return s, 0

    c_tag, c_val = split_sub(current_suffix)
    l_tag, l_val = split_sub(latest_suffix)
    if c_tag != l_tag:
        if c_is_build and not l_is_build:
            return 1
        if l_is_build and not c_is_build:
            return -1
        return 1 if c_tag > l_tag else -1
    if c_val != l_val:
        return 1 if c_val > l_val else -1
    return 0


def _compare_versions(current: str, latest: str) -> int:
    """
    Compare app versions with support for pre-release suffixes (e.g., 1.1.0 Beta6 vs 1.1.1).
    Returns:
      1  -> current is newer
      0  -> same
     -1  -> latest is newer
    """
    current_num, current_suffix = _parse_version_parts(current)
    latest_num, latest_suffix = _parse_version_parts(latest)

    max_len = max(len(current_num), len(latest_num))
    current_num += (0,) * (max_len - len(current_num))
    latest_num += (0,) * (max_len - len(latest_num))

    if current_num > latest_num:
        return 1
    if current_num < latest_num:
        return -1

    return _compare_suffixes(current_suffix, latest_suffix)


def _extract_release_build(release_data: dict) -> int:
    for field in ("name", "body", "tag_name"):
        text = str(release_data.get(field, "") or "")
        match = _BUILD_RE.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return 0
    return 0

class UpdateWorker(QThread):
    """Background worker for update checks and downloads."""
    check_finished = Signal(bool, str, str, str)  # is_available, version, download_url, release_notes
    download_progress = Signal(int)
    download_finished = Signal(str)  # local_path
    error = Signal(str)

    def __init__(self, mode="check", url=None):
        super().__init__()
        self.mode = mode
        self.url = url

    def run(self):
        try:
            if self.mode == "check":
                self._check_for_updates()
            elif self.mode == "download":
                self._download_update()
        except (httpx.HTTPError, socket.gaierror, OSError) as e:
            if self.mode == "check":
                logger.info(f"Update check skipped: {e}")
                self.check_finished.emit(False, "", "", "")
                return
            logger.error(f"Update download error: {str(e)}")
            self.error.emit(str(e))
        except Exception as e:
            logger.error(f"Update error: {str(e)}")
            if self.mode == "check":
                self.check_finished.emit(False, "", "", "")
            else:
                self.error.emit(str(e))

    def _check_for_updates(self):
        from ..core.config import APP_BUILD, APP_VERSION
        s = config_manager.settings
        repo_url = s.git_repo_url
        if not repo_url or "github.com/" not in repo_url:
            self.check_finished.emit(False, "", "", "")
            return

        # Extract user/repo from URL
        parts = repo_url.split("github.com/")[-1].split("/")
        if len(parts) < 2:
            self.check_finished.emit(False, "", "", "")
            return
            
        repo_path = f"{parts[0]}/{parts[1]}".replace(".git", "")
        api_url = f"https://api.github.com/repos/{repo_path}/releases/latest"
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(api_url)
            if response.status_code != 200:
                self.check_finished.emit(False, "", "", "")
                return
                
            data = response.json()
            latest_version = data.get("tag_name", "").lstrip("vV").strip()
            latest_build = _extract_release_build(data)
            release_notes = str(data.get("body", "") or "").strip()
            current_version = APP_VERSION.lstrip("vV").strip()
            current_build = APP_BUILD

            # Only notify when GitHub has a version strictly newer than what is installed.
            # Same version + same/older build → silent, no popup.
            if not latest_version:
                self.check_finished.emit(False, "", "", "")
                return

            version_cmp = _compare_versions(current_version, latest_version)
            if version_cmp > 0:
                self.check_finished.emit(False, "", "", "")
                return
            if version_cmp == 0 and latest_build <= current_build:
                self.check_finished.emit(False, "", "", "")
                return

            # Find the platform-specific asset
            assets = data.get("assets", [])
            download_url = ""
            import platform
            system = platform.system().lower()
            
            for asset in assets:
                name = asset.get("name", "").lower()
                if system == "windows" and (name.endswith(".exe") or name.endswith(".msi") or (name.endswith(".zip") and "win" in name)):
                    download_url = asset.get("browser_download_url", "")
                    break
                elif system == "darwin" and (name.endswith(".dmg") or (name.endswith(".zip") and ("mac" in name or "darwin" in name or "zugzwang" in name))):
                    download_url = asset.get("browser_download_url", "")
                    break
                elif system == "linux" and (name.endswith(".tar.gz") or name.endswith(".appimage") or name.endswith(".deb")) and ("linux" in name or "zugzwang" in name):
                    download_url = asset.get("browser_download_url", "")
                    break
            
            if not download_url:
                # Fallback to the first asset or release HTML page
                if assets and assets[0].get("browser_download_url"):
                    download_url = assets[0]["browser_download_url"]
                else:
                    download_url = data.get("html_url", "")
            
            if download_url:
                display_version = latest_version
                if latest_build > 0:
                    display_version = f"{latest_version} (build {latest_build})"
                self.check_finished.emit(True, display_version, download_url, release_notes)
                return
        
        self.check_finished.emit(False, "", "", "")

    def _download_update(self):
        from ..core.config import get_app_data_dir
        target_dir = os.path.join(str(get_app_data_dir()), "temp")
        os.makedirs(target_dir, exist_ok=True)
        local_path = os.path.join(target_dir, os.path.basename(self.url))
        
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            with client.stream("GET", self.url) as response:
                content_len = response.headers.get("Content-Length")
                total = int(content_len) if content_len and content_len.isdigit() else 0
                downloaded = 0
                with open(local_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = min(100, int((downloaded / total) * 100))
                            self.download_progress.emit(pct)
                        else:
                            approx = min(95, int(downloaded / (30 * 1024 * 1024) * 100))
                            self.download_progress.emit(approx)
        
        self.download_finished.emit(local_path)

class UpdateService(QObject):
    """Facade for update operations."""
    update_available = Signal(str, str, str) # version, url, release_notes
    no_update_available = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.latest_version = ""
        self.download_url = ""
        self.release_notes = ""

    def check(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = UpdateWorker(mode="check")
        self.worker.check_finished.connect(self._on_check_finished)
        self.worker.start()

    def _on_check_finished(self, available, ver, url, notes=""):
        if available:
            self.latest_version = ver
            self.download_url = url
            self.release_notes = notes or ""
            self.update_available.emit(ver, url, self.release_notes)
        else:
            self.no_update_available.emit()

    def start_download(self, url, progress_callback, finished_callback, error_callback):
        self.worker = UpdateWorker(mode="download", url=url)
        self.worker.download_progress.connect(progress_callback)
        self.worker.download_finished.connect(finished_callback)
        self.worker.error.connect(error_callback)
        self.worker.start()

    @staticmethod
    def apply_update(path):
        import subprocess
        import platform
        system = platform.system().lower()
        
        try:
            if system == "windows":
                os.startfile(path)
            elif system == "darwin":
                if path.endswith(".zip") or path.endswith(".dmg"):
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            logger.error(f"Failed to open update file: {e}")
            
        sys.exit(0)

# 1.1.2.2
