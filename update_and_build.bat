@echo off
setlocal
REM ============================================================
REM  update_and_build.bat  -  get the newest version and build it
REM  Double-click on the store PC.  Close Aaojee Label Maker first.
REM  Needs Git (https://git-scm.com/download/win) and Python.
REM ============================================================
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo Git is not installed.  Install it from https://git-scm.com/download/win
    goto :end
)

echo Getting the newest version from GitHub...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo Could not update.  Scroll up to read why.  Nothing was changed,
    echo and the program you have keeps working.
    goto :end
)
echo.

call "%~dp0build.bat"
exit /b

:end
echo.
pause
