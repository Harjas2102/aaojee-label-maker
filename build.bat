@echo off
setlocal
REM ============================================================
REM  build.bat  -  Aaojee Label Maker  Windows EXE builder
REM  Double-click this file to build.  No setup needed.
REM  Prerequisites: Python 3.10+ installed.
REM
REM  NOTE: this file must keep Windows (CRLF) line endings.
REM  If it is edited on a Mac, re-save it with CRLF endings or
REM  Windows will misread it and the window will just close.
REM ============================================================

echo.
echo ============================================================
echo  Aaojee Label Maker  -  Build Script
echo ============================================================
echo.

REM ---- Move into the source\ folder (works no matter where you
REM      double-clicked this .bat from) --------------------------
cd /d "%~dp0source"

if not exist main.py (
    echo ERROR: Cannot find source\main.py
    echo Make sure build.bat is in the same folder as the source\ folder.
    goto :end
)

REM ---- Find Python ("python", or the "py" launcher) ----------
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo ERROR: Python was not found.
    echo Download Python from https://www.python.org/downloads/
    echo On the installer's first screen, tick: "Add Python to PATH"
    goto :end
)
echo Using:
%PY% --version
echo.

REM ---- Step 1: Install / update dependencies -----------------
echo Installing Python dependencies...
%PY% -m pip install --upgrade Pillow pywin32 pyinstaller sv-ttk
if errorlevel 1 (
    echo.
    echo ERROR: Installing dependencies failed.  Scroll up to read why.
    echo Check the internet connection and try again.
    goto :end
)
echo.

REM ---- Optional: pyodbc for the old-database (.mdb) importer --
REM      Not required for printing labels, so a failure here does
REM      not stop the build.
%PY% -m pip install --upgrade pyodbc
if errorlevel 1 (
    echo.
    echo WARNING: pyodbc did not install.  The program will still build
    echo and print labels, but "Import from Old Database" will not work.
)
echo.

REM ---- Step 2: Run PyInstaller --------------------------------
REM Remove the previous build output first, so an old exe can never
REM be mistaken for a successful new build.
if exist dist\AaojeeLabels.exe del /q dist\AaojeeLabels.exe

echo Building the executable...
REM --collect-data sv_ttk bundles the Windows 11 theme files (U-016)
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name AaojeeLabels --collect-data sv_ttk main.py

echo.
echo ============================================================

if not exist dist\AaojeeLabels.exe (
    echo  BUILD FAILED.
    echo.
    echo  Scroll up to read the error.  Common causes:
    echo    - The dependency install step failed above
    echo    - Antivirus blocking PyInstaller - temporarily disable and retry
    goto :end
)

echo  SUCCESS!
echo.
echo  Your executable is ready at:
echo     %CD%\dist\AaojeeLabels.exe
echo.

REM Copy the exe up to the project folder (next to build.bat)
copy /y dist\AaojeeLabels.exe "%~dp0AaojeeLabels.exe" >nul
if errorlevel 1 (
    echo  COULD NOT replace "%~dp0AaojeeLabels.exe".
    echo  The program is probably still open.  Close Aaojee Label Maker
    echo  and run build.bat again, or copy the file above by hand.
    goto :end
)
echo  Also copied here for easy access:
echo     %~dp0AaojeeLabels.exe
echo.
echo  You can now double-click AaojeeLabels.exe to run the program.

:end
echo ============================================================
echo.
pause
endlocal
