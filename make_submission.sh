#!/usr/bin/env bash
set -euo pipefail

echo "[*] Cleaning __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "[+] Cleaned __pycache__"

echo "[*] Cleaning .pytest_cache..."
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
echo "[+] Cleaned .pytest_cache"

echo "[*] Cleaning *.pyc files..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "[+] Cleaned .pyc files"

zipName="brand-ai-readiness-audit-submission.zip"
zipPath="$(pwd)/$zipName"

if [ -f "$zipPath" ]; then
    rm -f "$zipPath"
fi

echo "[*] Creating submission zip: $zipName"

tempDir="$(mktemp -d)"
cp -a . "$tempDir/"

# Remove excluded directories from staging
for dir in "__pycache__" ".pytest_cache" ".git" "node_modules" ".venv" "venv"; do
    find "$tempDir" -type d -name "$dir" -exec rm -rf {} + 2>/dev/null || true
done

# Remove the zip itself if it got copied
stagingZip="$tempDir/$zipName"
rm -f "$stagingZip"

cd "$tempDir"
zip -r "$zipPath" . -x ".*" 2>/dev/null
cd - > /dev/null

rm -rf "$tempDir"

# Verify size
sizeBytes=$(stat --format=%s "$zipPath")
sizeMB=$(printf "%.2f" "$(echo "scale=6; $sizeBytes / 1048576" | bc)")

echo ""
echo "[*] Submission zip created: $zipName"
echo "[*] Size: $sizeMB MB"

if (( $(echo "$sizeMB > 50" | bc -l) )); then
    echo "[ERROR] Submission exceeds 50MB limit!"
    exit 1
else
    echo "[+] Size OK (under 50MB)"
fi

# Verify no __pycache__ in zip
pycacheEntries=$(unzip -l "$zipPath" | grep "__pycache__" || true)

if [ -n "$pycacheEntries" ]; then
    echo "[ERROR] __pycache__ found in zip!"
    echo "$pycacheEntries"
    exit 1
else
    echo "[+] No __pycache__ in zip"
fi

echo ""
echo "[*] Submission ready: $zipPath"
