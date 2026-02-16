"""
Generate a release manifest with SHA256 checksums for Better Planetside updater.

Usage example:
  python generate_release_manifest.py \
    --version 1.2.0 \
    --min-supported 1.1.0 \
    --base-url https://github.com/cedric12354/Better-Planetside/releases/download/v1.2.0 \
    --asset stable,windows,full,Better-Planetside-Windows-v1.2.0.zip \
    --asset stable,windows,patch,Better-Planetside-1.1.0-to-1.2.0.patch.zip,1.1.0 \
    --asset stable,linux,full,Better_Planetside-x86_64.AppImage \
    --output manifest.json
"""

import argparse
import hashlib
import json
import os
from typing import Dict, List, Tuple


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_asset_spec(spec: str) -> Tuple[str, str, str, str, str]:
    """
    Parse "channel,platform,kind,path[,from_version]".
    Returns: channel, platform, kind, file_path, from_version
    """
    parts = [p.strip() for p in str(spec or "").split(",")]
    if len(parts) not in (4, 5):
        raise ValueError(
            "Invalid --asset format. Expected 'channel,platform,kind,path[,from_version]'"
        )

    channel, platform, kind, file_path = parts[:4]
    from_version = parts[4] if len(parts) == 5 else ""
    kind = kind.lower()
    if kind not in ("full", "patch"):
        raise ValueError(f"Invalid asset kind '{kind}'. Use 'full' or 'patch'.")
    if kind == "patch" and not from_version:
        raise ValueError("Patch assets require from_version in --asset spec.")
    return channel, platform.lower(), kind, file_path, from_version


def build_asset_entry(
    channel: str,
    platform: str,
    kind: str,
    file_path: str,
    from_version: str,
    base_url: str,
) -> Dict:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Asset file not found: {file_path}")

    file_name = os.path.basename(file_path)
    sha = sha256_file(file_path)
    size = os.path.getsize(file_path)

    if base_url:
        base = base_url.rstrip("/")
        url = f"{base}/{file_name}"
    else:
        url = file_name

    entry = {
        "channel": channel,
        "platform": platform,
        "kind": kind,
        "name": file_name,
        "url": url,
        "sha256": sha,
        "size": size,
    }
    if kind == "patch":
        entry["from_version"] = from_version
    return entry


def main():
    parser = argparse.ArgumentParser(description="Generate updater manifest with SHA256 checksums.")
    parser.add_argument("--version", required=True, help="Target release version, e.g. 1.2.0")
    parser.add_argument("--min-supported", default="", help="Minimum version eligible for patch updates.")
    parser.add_argument("--base-url", default="", help="Optional base download URL for asset links.")
    parser.add_argument("--output", default="manifest.json", help="Output manifest path.")
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        help="Asset definition: channel,platform,kind,path[,from_version]",
    )
    args = parser.parse_args()

    if not args.asset:
        raise ValueError("At least one --asset entry is required.")

    assets: List[Dict] = []
    for spec in args.asset:
        channel, platform, kind, file_path, from_version = parse_asset_spec(spec)
        assets.append(
            build_asset_entry(
                channel=channel,
                platform=platform,
                kind=kind,
                file_path=file_path,
                from_version=from_version,
                base_url=args.base_url,
            )
        )

    manifest = {
        "version": str(args.version).strip(),
        "min_supported": str(args.min_supported).strip() if args.min_supported else "",
        "assets": assets,
    }

    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written: {out_path}")
    print(f"Assets: {len(assets)}")


if __name__ == "__main__":
    main()
