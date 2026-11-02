@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" goto run
echo Creating virtual environment...
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
:run
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" run.py --open-qr
goto end
:fail
echo.
echo Install failed. Make sure Python 3.10+ is installed and on PATH.
pause
:end
