@echo off
REM Build script for Better Planetside on Windows
REM Creates a standalone executable using PyInstaller
REM Auto-increments the version before building

setlocal enabledelayedexpansion

echo === Better Planetside Windows Build Script ===
echo.

REM ---------------------------------------------------------
REM 1. VERSION AUTO-INCREMENT (using Python for reliability)
REM ---------------------------------------------------------

REM Check for Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH!
    exit /b 1
)

REM Read current version
for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set "CURRENT_VERSION=%%v"
echo Current version: !CURRENT_VERSION!

echo.
echo Which version component to increment?
echo   1) Patch  (x.y.Z)
echo   2) Minor  (x.Y.0)
echo   3) Major  (X.0.0)
echo   4) Skip   (keep !CURRENT_VERSION!)
set /p "CHOICE=Choice [1-4, default=1]: "

if not defined CHOICE set "CHOICE=1"

REM Use Python to safely increment and write the version
python -c "
import re
parts = '%CURRENT_VERSION%'.split('.')
major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
choice = '%CHOICE%'
if choice == '2':
    minor += 1; patch = 0
elif choice == '3':
    major += 1; minor = 0; patch = 0
elif choice == '4':
    pass
else:
    patch += 1
new_ver = f'{major}.{minor}.{patch}'
with open('version.py', 'w') as f:
    f.write('\"\"\"' + chr(10))
    f.write('Single source of truth for the application version.' + chr(10))
    f.write('Updated automatically by build scripts (build-linux.sh / build-windows.bat).' + chr(10))
    f.write('Format: MAJOR.MINOR.PATCH' + chr(10))
    f.write('\"\"\"' + chr(10))
    f.write(f'VERSION = \"{new_ver}\"' + chr(10))
print(new_ver)
"

REM Read the new version
for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set "NEW_VERSION=%%v"
echo Building version: !NEW_VERSION!

REM ---------------------------------------------------------
REM 2. BUILD ENVIRONMENT
REM ---------------------------------------------------------

REM Check if we're in a virtual environment
if defined VIRTUAL_ENV (
    echo Using existing virtual environment: %VIRTUAL_ENV%
) else (
    if not exist "build_env" (
        echo Creating virtual environment...
        python -m venv build_env
    )
    echo Activating virtual environment...
    call build_env\Scripts\activate.bat
)

REM Install build dependencies
echo Installing build dependencies...
pip install --upgrade pip
pip install pyinstaller

REM Install application dependencies
echo Installing application dependencies...
pip install -r requirements.txt

REM ---------------------------------------------------------
REM 3. BUILD
REM ---------------------------------------------------------

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Build with PyInstaller
echo Building executable...
pyinstaller "Better Planetside.spec" --clean

echo.
echo === Build Complete ===
echo Version: !NEW_VERSION!
echo Executable location: dist\Better Planetside\Better Planetside.exe
echo.

REM Optional: Create ZIP archive
echo To create a distributable archive, run:
echo   powershell Compress-Archive -Path "dist\Better Planetside" -DestinationPath "Better-Planetside-Windows-v!NEW_VERSION!.zip"
echo.

pause
endlocal
