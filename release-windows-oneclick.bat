@echo off
setlocal enableextensions enabledelayedexpansion

REM One-click Windows release helper:
REM 1) Build Windows artifact (via build-windows.bat)
REM 2) Generate manifest.windows.json + manifest.json (full + optional patch)
REM 3) Upload Windows assets to release repo
REM 4) Commit/push version + manifests to code repo

set "RELEASE_REPO=cedric12354/Better-Planetside"
set "CODE_REPO_URL=https://github.com/AhornFPS/Better-Planetside"
set "CHANNEL=stable"
set "MIN_SUPPORTED="
set "WINDOWS_PATCH_PATH="
set "WINDOWS_PATCH_FROM="
set "AUTO_CREATE_RELEASE=1"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--release-repo" (
    set "RELEASE_REPO=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--code-repo-url" (
    set "CODE_REPO_URL=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--channel" (
    set "CHANNEL=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--min-supported" (
    set "MIN_SUPPORTED=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--patch" (
    set "WINDOWS_PATCH_PATH=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--patch-from" (
    set "WINDOWS_PATCH_FROM=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--no-create-release" (
    set "AUTO_CREATE_RELEASE=0"
    shift
    goto parse_args
)
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help

echo ERROR: Unknown argument: %~1
goto help

:help
echo Usage: release-windows-oneclick.bat [options]
echo.
echo Options:
echo   --release-repo OWNER/REPO   Default: cedric12354/Better-Planetside
echo   --code-repo-url URL         Default: https://github.com/AhornFPS/Better-Planetside
echo   --channel NAME              Default: stable
echo   --min-supported VERSION     Optional manifest min_supported
echo   --patch PATH                Optional Windows patch zip path
echo   --patch-from VERSION        Required when --patch is set
echo   --no-create-release         Do not auto-create release if missing
echo.
echo Example:
echo   release-windows-oneclick.bat --patch Better-Planetside-1.1.0-to-1.2.0.patch.zip --patch-from 1.1.0
exit /b 1

:args_done
if defined WINDOWS_PATCH_PATH (
    if not defined WINDOWS_PATCH_FROM (
        echo ERROR: --patch requires --patch-from
        exit /b 1
    )
)

where python >nul 2>&1 || (echo ERROR: python not found in PATH.& exit /b 1)
where git >nul 2>&1 || (echo ERROR: git not found in PATH.& exit /b 1)
where gh >nul 2>&1 || (echo ERROR: gh CLI not found in PATH.& exit /b 1)

echo === Windows One-Click Release ===
echo Repo: !RELEASE_REPO!
echo Code repo: !CODE_REPO_URL!
echo.

set "NON_INTERACTIVE=1"

call build-windows.bat
if errorlevel 1 (
    echo ERROR: build-windows.bat failed.
    exit /b 1
)

for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set "VERSION=%%v"
if not defined VERSION (
    echo ERROR: Could not read VERSION from version.py
    exit /b 1
)

set "TAG=v!VERSION!"
set "ZIP_NAME=Better-Planetside-Windows-v!VERSION!.zip"
set "INSTALLER_NAME=BetterPlanetside-Installer-v!VERSION!.exe"
set "HAS_INSTALLER=0"
set "BASE_URL=https://github.com/!RELEASE_REPO!/releases/download/!TAG!"
set "MS_ARG="
if defined MIN_SUPPORTED set "MS_ARG=--min-supported !MIN_SUPPORTED!"

if not exist "!ZIP_NAME!" (
    echo ERROR: Expected Windows zip not found: !ZIP_NAME!
    exit /b 1
)

if exist "!INSTALLER_NAME!" (
    set "HAS_INSTALLER=1"
    echo Found installer: !INSTALLER_NAME!
) else (
    echo WARNING: Installer not found: !INSTALLER_NAME!
    echo Proceeding without installer upload.
)

if defined WINDOWS_PATCH_PATH (
    if not exist "!WINDOWS_PATCH_PATH!" (
        echo ERROR: Windows patch not found: !WINDOWS_PATCH_PATH!
        exit /b 1
    )
)

echo Generating manifest.windows.json...
if defined WINDOWS_PATCH_PATH (
    python generate_release_manifest.py --version !VERSION! !MS_ARG! --base-url "!BASE_URL!" --asset "!CHANNEL!,windows,full,!ZIP_NAME!" --asset "!CHANNEL!,windows,patch,!WINDOWS_PATCH_PATH!,!WINDOWS_PATCH_FROM!" --output manifest.windows.json
) else (
    python generate_release_manifest.py --version !VERSION! !MS_ARG! --base-url "!BASE_URL!" --asset "!CHANNEL!,windows,full,!ZIP_NAME!" --output manifest.windows.json
)
if errorlevel 1 (
    echo ERROR: Failed to generate manifest.windows.json
    exit /b 1
)

copy /y "manifest.windows.json" "manifest.json" >nul
if errorlevel 1 (
    echo ERROR: Failed to create manifest.json from manifest.windows.json
    exit /b 1
)

echo Ensuring release !TAG! exists in !RELEASE_REPO!...
gh release view !TAG! --repo !RELEASE_REPO! >nul 2>&1
if errorlevel 1 (
    if "!AUTO_CREATE_RELEASE!"=="1" (
        gh release create !TAG! --repo !RELEASE_REPO! --title !TAG! --notes "Automated release bootstrap"
        if errorlevel 1 (
            echo ERROR: Could not create release !TAG!
            exit /b 1
        )
    ) else (
        echo ERROR: Release !TAG! not found. Create it first or remove --no-create-release.
        exit /b 1
    )
)

echo Uploading Windows assets to release...
if defined WINDOWS_PATCH_PATH (
    if "!HAS_INSTALLER!"=="1" (
        gh release upload !TAG! "!ZIP_NAME!" "!INSTALLER_NAME!" "!WINDOWS_PATCH_PATH!" "manifest.windows.json" "manifest.json" --repo !RELEASE_REPO! --clobber
    ) else (
        gh release upload !TAG! "!ZIP_NAME!" "!WINDOWS_PATCH_PATH!" "manifest.windows.json" "manifest.json" --repo !RELEASE_REPO! --clobber
    )
) else (
    if "!HAS_INSTALLER!"=="1" (
        gh release upload !TAG! "!ZIP_NAME!" "!INSTALLER_NAME!" "manifest.windows.json" "manifest.json" --repo !RELEASE_REPO! --clobber
    ) else (
        gh release upload !TAG! "!ZIP_NAME!" "manifest.windows.json" "manifest.json" --repo !RELEASE_REPO! --clobber
    )
)
if errorlevel 1 (
    echo ERROR: Failed to upload Windows assets.
    exit /b 1
)

echo Committing release metadata to code repo...
git add version.py manifest.windows.json manifest.json
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "release: !TAG! (windows metadata)"
    if errorlevel 1 (
        echo ERROR: git commit failed.
        exit /b 1
    )
) else (
    echo No staged changes to commit.
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%b"
if not defined CURRENT_BRANCH (
    echo ERROR: Could not determine current git branch.
    exit /b 1
)
if /I "!CURRENT_BRANCH!"=="HEAD" (
    echo ERROR: Detached HEAD detected. Checkout a branch before pushing.
    exit /b 1
)

echo Pushing !CURRENT_BRANCH! to !CODE_REPO_URL!...
git push "!CODE_REPO_URL!" "HEAD:!CURRENT_BRANCH!"
if errorlevel 1 (
    echo ERROR: git push failed.
    exit /b 1
)
echo Windows assets uploaded and metadata pushed.

echo.
echo Windows release step finished for !TAG!.


