@echo off
REM Double-click to run all automated tests.  Needs Python with Pillow.
cd /d "%~dp0"
python -m pip install --quiet Pillow sv-ttk
python toolsun_tests.py
echo.
pause
