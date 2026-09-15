#!/usr/bin/env bash
# ZUGZWANG Linux Standalone Package Builder
# Usage: ./scripts/build_linux.sh

set -e

echo "=========================================================="
echo "    ZUGZWANG — Building Linux Standalone Package"
echo "=========================================================="

# 1. Clean previous builds
rm -rf build dist/ZUGZWANG dist/ZUGZWANG_Linux_*.tar.gz

# 2. Build standalone package and inject Chromium
echo "[1/3] Building ZUGZWANG and bundling Playwright Chromium..."
python3 build_with_browsers.py

# 3. Create .desktop launcher file for Linux desktop environments
echo "[2/3] Creating ZUGZWANG.desktop launcher..."
cat << 'EOF' > dist/ZUGZWANG/ZUGZWANG.desktop
[Desktop Entry]
Name=ZUGZWANG
Comment=AI-Powered Bewerbungs- & Lead-Automation
Exec=./ZUGZWANG
Icon=./assets/icon.ico
Terminal=false
Type=Application
Categories=Office;Network;Utility;
EOF
chmod +x dist/ZUGZWANG/ZUGZWANG.desktop

# 4. Create distributable tar.gz archive
echo "[3/3] Creating Linux distributable archive..."
cd dist
VERSION=$(python3 -c "import sys; sys.path.insert(0, '..'); from src.core.config import APP_VERSION; print(APP_VERSION)")
tar -czf "ZUGZWANG_Linux_${VERSION}.tar.gz" ZUGZWANG/
cd ..

echo "=========================================================="
echo "[SUCCESS] Built Linux package: dist/ZUGZWANG_Linux_${VERSION}.tar.gz"
echo "=========================================================="

# 1.1.2 build 10
