#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible wrapper for Linux release.
# Note: Windows assets are no longer accepted here.

RELEASE_REPO="${RELEASE_REPO:-cedric12354/Better-Planetside}"
CHANNEL="${CHANNEL:-stable}"
MIN_SUPPORTED="${MIN_SUPPORTED:-}"
SKIP_BUILD="${SKIP_BUILD:-0}"
AUTO_CREATE_RELEASE="${AUTO_CREATE_RELEASE:-1}"

TAG=""

usage() {
  cat <<EOF
Usage: ./release-with-windows-patch.sh [options]

Optional:
  --tag TAG                     Release tag (default: v<version.py>)
  --release-repo OWNER/REPO     Default: ${RELEASE_REPO}
  --channel NAME                Default: ${CHANNEL}
  --min-supported VERSION       Manifest min_supported value
  --skip-build                  Forwarded to create-appimage.sh
  --no-create-release           Do not auto-create release if missing
  --help                        Show this help

Environment alternatives:
  RELEASE_REPO, CHANNEL, MIN_SUPPORTED, SKIP_BUILD, AUTO_CREATE_RELEASE
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="$2"
      shift 2
      ;;
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
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --no-create-release)
      AUTO_CREATE_RELEASE=0
      shift
      ;;
    --windows-full|--windows-patch|--windows-patch-from)
      echo "ERROR: $1 is no longer supported here."
      echo "Run release-windows-oneclick.bat for Windows assets, and release-linux-oneclick.sh for Linux assets."
      exit 1
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

if [[ ! -f "./release-linux-oneclick.sh" ]]; then
  echo "ERROR: ./release-linux-oneclick.sh not found."
  exit 1
fi

cmd=(
  bash ./release-linux-oneclick.sh
  --release-repo "$RELEASE_REPO"
  --channel "$CHANNEL"
  --tag "$TAG"
)

if [[ -n "$MIN_SUPPORTED" ]]; then
  cmd+=(--min-supported "$MIN_SUPPORTED")
fi

if [[ "$SKIP_BUILD" == "1" ]]; then
  cmd+=(--skip-build)
fi

if [[ "$AUTO_CREATE_RELEASE" == "0" ]]; then
  cmd+=(--no-create-release)
fi

echo "Running Linux release upload..."
"${cmd[@]}"
echo "Done."
