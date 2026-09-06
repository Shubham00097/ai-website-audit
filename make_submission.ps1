# make_submission.ps1
# A6: Submission automation script
# Purges __pycache__, .pytest_cache, creates zip, verifies size < 50MB

$ErrorActionPreference = "Stop"

Write-Host "[*] Cleaning __pycache__ directories..."
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "[+] Cleaned __pycache__"

Write-Host "[*] Cleaning .pytest_cache..."
Get-ChildItem -Path . -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force
Write-Host "[+] Cleaned .pytest_cache"

Write-Host "[*] Cleaning *.pyc files..."
Get-ChildItem -Path . -Recurse -Filter "*.pyc" | Remove-Item -Force
Write-Host "[+] Cleaned .pyc files"

$zipName = "brand-ai-readiness-audit-submission.zip"
$zipPath = Join-Path (Get-Location) $zipName

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Write-Host "[*] Creating submission zip: $zipName"
# Exclude common non-submission files
$excludeDirs = @("__pycache__", ".pytest_cache", ".git", "node_modules", ".venv", "venv")
$tempDir = Join-Path $env:TEMP "submission_staging"
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
Copy-Item -Path . -Destination $tempDir -Recurse -Force

# Remove excluded directories from staging
foreach ($dir in $excludeDirs) {
    Get-ChildItem -Path $tempDir -Recurse -Directory -Filter $dir -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# Remove the zip itself if it got copied
$stagingZip = Join-Path $tempDir $zipName
if (Test-Path $stagingZip) { Remove-Item $stagingZip -Force }

Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -Force

# Cleanup staging
Remove-Item $tempDir -Recurse -Force

# Verify size
$sizeBytes = (Get-Item $zipPath).Length
$sizeMB = [math]::Round($sizeBytes / 1MB, 2)

Write-Host ""
Write-Host "[*] Submission zip created: $zipName"
Write-Host "[*] Size: $sizeMB MB"

if ($sizeMB -gt 50) {
    Write-Host "[ERROR] Submission exceeds 50MB limit!" -ForegroundColor Red
    exit 1
} else {
    Write-Host "[+] Size OK (under 50MB)" -ForegroundColor Green
}

# Verify no __pycache__ in zip
$zipContent = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
$pycacheEntries = $zipContent.Entries | Where-Object { $_.FullName -like "*__pycache__*" }
$zipContent.Dispose()

if ($pycacheEntries.Count -gt 0) {
    Write-Host "[ERROR] __pycache__ found in zip!" -ForegroundColor Red
    $pycacheEntries | ForEach-Object { Write-Host "  - $($_.FullName)" }
    exit 1
} else {
    Write-Host "[+] No __pycache__ in zip" -ForegroundColor Green
}

Write-Host ""
Write-Host "[*] Submission ready: $zipPath"
