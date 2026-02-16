#!/usr/bin/env bash
set -euo pipefail

# Wrapper for combined Linux + Windows release upload flow.
# It calls create-appimage.sh with Windows full + patch assets and --upload-release.
#
# Example:
#   ./release-with-windows-patch.sh \
#     --tag v1.2.0 \
#     --windows-full /path/to/Better-Planetside-Windows-v1.2.0.zip \
#     --windows-patch /path/to/Better-Planetside-1.1.0-to-1.2.0.patch.zip \
#     --windows-patch-from 1.1.0

RELEASE_REPO="${RELEASE_REPO:-cedric12354/Better-Planetside}"
CHANNEL="${CHANNEL:-stable}"
MIN_SUPPORTED="${MIN_SUPPORTED:-}"
SKIP_BUILD="${SKIP_BUILD:-0}"

TAG=""
WINDOWS_FULL=""
WINDOWS_PATCH=""
WINDOWS_PATCH_FROM=""

usage() {
  cat <<EOF
Usage: ./release-with-windows-patch.sh [options]

Required:
  --windows-full PATH           Windows full ZIP path
  --windows-patch PATH          Windows patch ZIP path
  --windows-patch-from VERSION  Patch source version (e.g. 1.1.0)

Optional:
  --tag TAG                     Release tag (default: v<version.py>)
  --release-repo OWNER/REPO     Default: ${RELEASE_REPO}
  --channel NAME                Default: ${CHANNEL}
  --min-supported VERSION       Manifest min_supported value
  --skip-build                  Forwarded to create-appimage.sh
  --help                        Show this help

Environment alternatives:
  RELEASE_REPO, CHANNEL, MIN_SUPPORTED, SKIP_BUILD
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="$2"
      shift 2
      ;;
    --windows-full)
      WINDOWS_FULL="$2"
      shift 2
      ;;
    --windows-patch)
      WINDOWS_PATCH="$2"
      shift 2
      ;;
    --windows-patch-from)
      WINDOWS_PATCH_FROM="$2"
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

if [[ -z "$WINDOWS_FULL" || -z "$WINDOWS_PATCH" || -z "$WINDOWS_PATCH_FROM" ]]; then
  echo "ERROR: Missing required arguments."
  usage
  exit 1
fi

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

if [[ ! -f "$WINDOWS_FULL" ]]; then
  echo "ERROR: Windows full asset not found: $WINDOWS_FULL"
  exit 1
fi

if [[ ! -f "$WINDOWS_PATCH" ]]; then
  echo "ERROR: Windows patch asset not found: $WINDOWS_PATCH"
  exit 1
fi

if [[ ! -f "./create-appimage.sh" ]]; then
  echo "ERROR: ./create-appimage.sh not found."
  exit 1
fi

cmd=(
  bash ./create-appimage.sh
  --release-repo "$RELEASE_REPO"
  --channel "$CHANNEL"
  --tag "$TAG"
  --windows-full "$WINDOWS_FULL"
  --windows-patch "$WINDOWS_PATCH"
  --windows-patch-from "$WINDOWS_PATCH_FROM"
  --upload-release
)

if [[ -n "$MIN_SUPPORTED" ]]; then
  cmd+=(--min-supported "$MIN_SUPPORTED")
fi

if [[ "$SKIP_BUILD" == "1" ]]; then
  cmd+=(--skip-build)
fi

echo "Running combined release upload..."
"${cmd[@]}"
echo "Done."
