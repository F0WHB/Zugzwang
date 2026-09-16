#!/usr/bin/env bash
# ==============================================================================
# Deploy ZUGZWANG showcase website to https://zugzwang49.github.io
# Usage: ./scripts/deploy_site.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCS_DIR="$ROOT_DIR/docs"
REPO_URL="https://github.com/zugzwang49/zugzwang49.github.io.git"
TEMP_DIR=$(mktemp -d)

echo ">>> Preparing site deployment from $DOCS_DIR..."

if [ ! -d "$DOCS_DIR" ]; then
    echo "Error: docs/ directory not found at $DOCS_DIR"
    exit 1
fi

# Copy all files from docs/ to temp folder
cp -r "$DOCS_DIR"/* "$TEMP_DIR/"
cp "$DOCS_DIR"/.nojekyll "$TEMP_DIR/" 2>/dev/null || touch "$TEMP_DIR/.nojekyll"

cd "$TEMP_DIR"
git init -b main
git config user.name "ZUGZWANG Bot"
git config user.email "deploy@zugzwang.local"
git add .
git commit -m "Deploy ZUGZWANG showcase site"

echo ">>> Pushing to $REPO_URL (main branch)..."
git remote add origin "$REPO_URL"
git push -u -f origin main

# Cleanup
rm -rf "$TEMP_DIR"

echo "---------------------------------------------------------"
echo ">>> Successfully deployed!"
echo ">>> Your website is live at: https://zugzwang49.github.io/"
echo "---------------------------------------------------------"
