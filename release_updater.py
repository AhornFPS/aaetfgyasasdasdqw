import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests


def _normalize_version(version: str) -> str:
    v = str(version or "").strip()
    if v.lower().startswith("v"):
        v = v[1:]
    return v


def _version_tuple(version: str) -> Tuple[int, ...]:
    parts = []
    for token in _normalize_version(version).split("."):
        digits = []
        for ch in token:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        parts.append(int("".join(digits) or "0"))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(candidate: str, current: str) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def detect_platform_key() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return "unknown"


@dataclass
class UpdateAsset:
    name: str
    url: str
    kind: str = "full"  # full | patch
    sha256: str = ""
    from_version: str = ""
    size: int = 0


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    release_url: str
    platform: str
    asset: Optional[UpdateAsset] = None
    notes: str = ""
    manifest_url: str = ""

    @property
    def has_update(self) -> bool:
        return self.asset is not None


class ReleaseUpdater:
    def __init__(
        self,
        owner: str,
        repo: str,
        current_version: str,
        user_data_dir: str,
        channel: str = "stable",
        token: str = "",
        timeout_sec: float = 20.0,
    ):
        self.owner = str(owner or "").strip()
        self.repo = str(repo or "").strip()
        self.current_version = _normalize_version(current_version)
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.channel = str(channel or "stable").strip().lower()
        self.token = str(token or "").strip()
        self.timeout_sec = float(timeout_sec)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request_json(self, url: str) -> Dict:
        response = requests.get(url, headers=self._headers(), timeout=self.timeout_sec)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} while requesting {url}")
        return response.json()

    def _request_bytes(self, url: str) -> bytes:
        response = requests.get(url, headers=self._headers(), timeout=self.timeout_sec)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} while requesting {url}")
        return response.content

    def _select_fallback_asset(self, release_assets: List[Dict], platform_key: str) -> Optional[UpdateAsset]:
        platform_tokens = {
            "windows": ("win", "windows"),
            "linux": ("linux", "appimage"),
            "macos": ("mac", "darwin", "osx"),
        }.get(platform_key, (platform_key,))

        candidates = []
        for item in release_assets:
            name = str(item.get("name", ""))
            lname = name.lower()
            if not name:
                continue
            if any(tok in lname for tok in platform_tokens):
                candidates.append(item)

        if not candidates:
            return None

        # Prefer archive/update artifacts over checksums/signatures.
        preferred = None
        for item in candidates:
            lname = str(item.get("name", "")).lower()
            if lname.endswith((".zip", ".appimage", ".exe", ".tar.gz", ".msi")):
                preferred = item
                break
        if not preferred:
            preferred = candidates[0]

        return UpdateAsset(
            name=str(preferred.get("name", "")),
            url=str(preferred.get("browser_download_url", "")),
            kind="full",
            sha256="",
            from_version="",
            size=int(preferred.get("size", 0) or 0),
        )

    def _select_manifest_asset(
        self,
        manifest: Dict,
        latest_version: str,
        platform_key: str,
    ) -> Optional[UpdateAsset]:
        assets = manifest.get("assets", [])
        if not isinstance(assets, list):
            return None

        min_supported = _normalize_version(str(manifest.get("min_supported", "")))
        can_use_patch = True
        if min_supported and _version_tuple(self.current_version) < _version_tuple(min_supported):
            can_use_patch = False

        def make_asset(entry: Dict) -> Optional[UpdateAsset]:
            if not isinstance(entry, dict):
                return None
            url = str(entry.get("url", "")).strip()
            name = str(entry.get("name", "")).strip()
            if not url or not name:
                return None
            return UpdateAsset(
                name=name,
                url=url,
                kind=str(entry.get("kind", "full")).strip().lower() or "full",
                sha256=str(entry.get("sha256", "")).strip().lower(),
                from_version=_normalize_version(str(entry.get("from_version", ""))),
                size=int(entry.get("size", 0) or 0),
            )

        parsed_assets = []
        for entry in assets:
            asset = make_asset(entry)
            if not asset:
                continue
            entry_platform = str(entry.get("platform", "")).strip().lower()
            if entry_platform and entry_platform != platform_key:
                continue
            entry_channel = str(entry.get("channel", "stable")).strip().lower()
            if entry_channel != self.channel:
                continue
            parsed_assets.append(asset)

        if can_use_patch:
            for asset in parsed_assets:
                if asset.kind == "patch" and asset.from_version == self.current_version:
                    return asset

        for asset in parsed_assets:
            if asset.kind == "full":
                return asset
        return None

    def check_for_update(self) -> Optional[UpdateInfo]:
        if not self.owner or not self.repo:
            raise RuntimeError("Updater repo owner/name is not configured.")

        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        release = self._request_json(api_url)

        latest_version = _normalize_version(str(release.get("tag_name") or release.get("name") or ""))
        if not latest_version:
            raise RuntimeError("Latest release does not contain a valid version tag/name.")

        if not is_newer_version(latest_version, self.current_version):
            return None

        platform_key = detect_platform_key()
        release_url = str(release.get("html_url", "")).strip()
        notes = str(release.get("body", "") or "")
        release_assets = release.get("assets", [])
        manifest_url = ""
        selected_asset = None

        if isinstance(release_assets, list):
            for item in release_assets:
                name = str(item.get("name", "")).lower().strip()
                if name == "manifest.json" or name.endswith(".manifest.json"):
                    manifest_url = str(item.get("browser_download_url", "")).strip()
                    break

        if manifest_url:
            manifest = json.loads(self._request_bytes(manifest_url).decode("utf-8"))
            manifest_version = _normalize_version(str(manifest.get("version", latest_version)))
            # Use manifest version if present and newer than current.
            if is_newer_version(manifest_version, self.current_version):
                latest_version = manifest_version
            selected_asset = self._select_manifest_asset(manifest, latest_version, platform_key)

        if not selected_asset:
            selected_asset = self._select_fallback_asset(release_assets if isinstance(release_assets, list) else [], platform_key)

        return UpdateInfo(
            current_version=self.current_version,
            latest_version=latest_version,
            release_url=release_url,
            platform=platform_key,
            asset=selected_asset,
            notes=notes,
            manifest_url=manifest_url,
        )

    def _hash_file(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _download_to_file(self, url: str, out_path: str):
        with requests.get(url, headers=self._headers(), timeout=self.timeout_sec, stream=True) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code} while downloading {url}")
            with open(out_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)

    def stage_update(self, update: UpdateInfo) -> Dict[str, str]:
        if not update or not update.asset:
            raise RuntimeError("No downloadable update asset available.")

        stage_dir = os.path.join(
            self.user_data_dir,
            "updates",
            "staging",
            update.latest_version,
        )
        os.makedirs(stage_dir, exist_ok=True)

        asset_path = os.path.join(stage_dir, update.asset.name)
        self._download_to_file(update.asset.url, asset_path)

        expected_sha = str(update.asset.sha256 or "").strip().lower()
        if expected_sha:
            actual_sha = self._hash_file(asset_path)
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"Checksum mismatch for {update.asset.name}: expected {expected_sha}, got {actual_sha}"
                )

        pending_data = {
            "current_version": update.current_version,
            "latest_version": update.latest_version,
            "platform": update.platform,
            "release_url": update.release_url,
            "manifest_url": update.manifest_url,
            "asset": {
                "name": update.asset.name,
                "url": update.asset.url,
                "kind": update.asset.kind,
                "sha256": update.asset.sha256,
                "from_version": update.asset.from_version,
                "size": int(update.asset.size or 0),
                "local_path": asset_path,
            },
        }
        pending_path = os.path.join(self.user_data_dir, "updates", "pending_update.json")
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_data, f, indent=2)

        return {"asset_path": asset_path, "pending_path": pending_path}
