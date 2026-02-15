@echo off
REM Build script for Better Planetside on Windows
REM Creates a standalone executable using PyInstaller
REM Auto-increments the version before building

setlocal enabledelayedexpansion

echo === Better Planetside Windows Build Script ===
echo.

REM ---------------------------------------------------------
REM 1. VERSION AUTO-INCREMENT
REM ---------------------------------------------------------

REM Check for Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH!
    pause
    exit /b 1
)

REM Read current version
for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set "CURRENT_VERSION=%%v"
echo Current version: !CURRENT_VERSION!

echo.
echo Which version component to increment?
echo   1^) Patch  ^(x.y.Z^)
echo   2^) Minor  ^(x.Y.0^)
echo   3^) Major  ^(X.0.0^)
echo   4^) Skip   ^(keep !CURRENT_VERSION!^)
set /p "CHOICE=Choice [1-4, default=1]: "

if not defined CHOICE set "CHOICE=1"

REM Bump version using helper script
python bump_version.py !CHOICE!

REM Read the new version
for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set "NEW_VERSION=%%v"
echo.
echo Building version: !NEW_VERSION!
echo.

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

REM ---------------------------------------------------------
REM 4. PACKAGE
REM ---------------------------------------------------------

set "ZIP_NAME=Better-Planetside-Windows-v!NEW_VERSION!.zip"

echo.
echo Packaging into %ZIP_NAME%...

REM Remove old ZIP if it exists
if exist "!ZIP_NAME!" del /f "!ZIP_NAME!"

REM Create ZIP archive
powershell -Command "Compress-Archive -Path 'dist\Better Planetside' -DestinationPath '!ZIP_NAME!'"

REM ---------------------------------------------------------
REM 5. CLEANUP
REM ---------------------------------------------------------

echo Cleaning up build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "build_env" rmdir /s /q "build_env"

echo.
echo === Build Complete ===
echo Version:  !NEW_VERSION!
echo Package:  !ZIP_NAME!
for %%A in ("!ZIP_NAME!") do echo Size:     %%~zA bytes
echo.

pause
endlocal
