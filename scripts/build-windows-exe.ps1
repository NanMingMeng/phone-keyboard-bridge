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
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --console --name PhoneKeyboardBridge --add-data "phone_keyboard/templates;phone_keyboard/templates" run.py
Write-Host ""
Write-Host "Built: dist\PhoneKeyboardBridge.exe"
