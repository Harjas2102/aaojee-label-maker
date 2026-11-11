@echo off
REM Double-click to run all automated tests.  Needs Python with Pillow.
REM This file must keep Windows (CRLF) line endings.
cd /d "%~dp0"
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo ERROR: Python was not found.  Install it from https://www.python.org/downloads/
    goto :end
)
%PY% -m pip install --quiet Pillow sv-ttk
%PY% tools\run_tests.py
:end
echo.
pause
