$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv .venv
    } else {
        python -m venv .venv
    }
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name PKB --icon assets/icon.ico --add-data "phone_keyboard/templates;phone_keyboard/templates" --add-data "assets;assets" --hidden-import PyQt6.QtSvg --hidden-import PyQt6.QtSvgWidgets run_desktop.py
Write-Host ""
Write-Host "Built: dist\PKB.exe"
