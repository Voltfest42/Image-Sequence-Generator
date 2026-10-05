# Builds dist\ImageSequenceGenerator.exe (single file, no console window).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if (-not (Test-Path assets\icon.ico)) { .\.venv\Scripts\python.exe make_icon.py }

.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name ImageSequenceGenerator `
    --icon assets\icon.ico `
    --add-data "assets\icon.ico;assets" `
    --collect-data customtkinter `
    --collect-submodules OpenEXR `
    --exclude-module matplotlib --exclude-module scipy --exclude-module pandas `
    app.py

Write-Host "`nBuilt: $PSScriptRoot\dist\ImageSequenceGenerator.exe"
