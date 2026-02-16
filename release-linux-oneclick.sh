#!/usr/bin/env bash
set -euo pipefail

# One-click Linux release helper:
# 1) Pull latest code (expects manifest.windows.json from Windows step)
# 2) Build Linux artifacts
# 3) Generate combined manifest (imports windows entries + linux entry)
# 4) Upload AppImage + linux tar + manifest.json to release repo

RELEASE_REPO="${RELEASE_REPO:-cedric12354/Better-Planetside}"
CHANNEL="${CHANNEL:-stable}"
MIN_SUPPORTED="${MIN_SUPPORTED:-}"
TAG="${TAG:-}"
SKIP_BUILD="${SKIP_BUILD:-0}"
AUTO_CREATE_RELEASE="${AUTO_CREATE_RELEASE:-1}"
WINDOWS_MANIFEST="${WINDOWS_MANIFEST:-manifest.windows.json}"

usage() {
  cat <<EOF
Usage: ./release-linux-oneclick.sh [options]

Options:
  --release-repo OWNER/REPO     Default: ${RELEASE_REPO}
  --channel NAME                Default: ${CHANNEL}
  --min-supported VERSION       Optional manifest min_supported
  --tag TAG                     Default: v<version.py>
  --windows-manifest PATH       Default: manifest.windows.json
  --skip-build                  Forwarded to create-appimage.sh
  --no-create-release           Do not auto-create release if missing
  --help                        Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-repo)
      RELEASE_REPO="$2"
      shift 2
      ;;
    --channel)
      CHANNEL="$2"
      shift 2
      ;;
    --min-supported)
      MIN_SUPPORTED="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --windows-manifest)
      WINDOWS_MANIFEST="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --no-create-release)
      AUTO_CREATE_RELEASE=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "ERROR: git not found."; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "ERROR: gh CLI not found."; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERROR: python not found."; exit 1; }

echo "=== Linux One-Click Release ==="
echo "Repo: ${RELEASE_REPO}"
echo

echo "Pulling latest code..."


if [[ -z "$TAG" ]]; then
  if [[ ! -f "version.py" ]]; then
    echo "ERROR: version.py not found and --tag not provided."
    exit 1
  fi
  VERSION="$(grep -oP 'VERSION = "\K[0-9]+\.[0-9]+\.[0-9]+' version.py || true)"
  if [[ -z "$VERSION" ]]; then
    echo "ERROR: Could not read VERSION from version.py. Provide --tag."
    exit 1
  fi
  TAG="v${VERSION}"
fi

if [[ ! -f "$WINDOWS_MANIFEST" ]]; then
  echo "ERROR: Windows manifest not found: $WINDOWS_MANIFEST"
  echo "Run release-windows-oneclick.bat first and push manifest.windows.json."
  exit 1
fi

echo "Ensuring release ${TAG} exists in ${RELEASE_REPO}..."
if ! gh release view "$TAG" --repo "$RELEASE_REPO" >/dev/null 2>&1; then
  if [[ "$AUTO_CREATE_RELEASE" == "1" ]]; then
    gh release create "$TAG" --repo "$RELEASE_REPO" --title "$TAG" --notes "Automated release bootstrap"
  else
    echo "ERROR: Release ${TAG} not found."
    exit 1
  fi
fi

cmd=(
  bash ./create-appimage.sh
  --release-repo "$RELEASE_REPO"
  --channel "$CHANNEL"
  --tag "$TAG"
  --import-manifest "$WINDOWS_MANIFEST"
  --upload-release
)

if [[ -n "$MIN_SUPPORTED" ]]; then
  cmd+=(--min-supported "$MIN_SUPPORTED")
fi

if [[ "$SKIP_BUILD" == "1" ]]; then
  cmd+=(--skip-build)
fi

echo "Building/uploading Linux artifacts and combined manifest..."
"${cmd[@]}"

echo
echo "Linux release step finished for ${TAG}."
echo
