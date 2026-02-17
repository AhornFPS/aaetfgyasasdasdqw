#!/usr/bin/env python3
"""Generate a sanitized config.json used for release packaging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXCLUDED_TOP_LEVEL_KEYS = {
    "email",
    "main_background_path",
    "ps2_path",
    "pw",
    "twitch",
    "updates",
    "watch_folder",
    "window_size",
    "audio_device",
    "obs_service",
    "scifi_overlay_active",
    "auto_voice",
}


def _load_source_config(source_path: Path) -> dict[str, Any]:
    if not source_path.exists():
        return {}
    with source_path.open("r", encoding="utf-8") as source_file:
        loaded = json.load(source_file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Source config is not a JSON object: {source_path}")
    return loaded


def _sanitize_config(source_config: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(source_config)
    for key in EXCLUDED_TOP_LEVEL_KEYS:
        sanitized.pop(key, None)
    return sanitized


def _write_config(output_path: Path, config_obj: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(config_obj, output_file, indent=4, ensure_ascii=True)
        output_file.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate sanitized release config.json")
    parser.add_argument("--source", default="config.json", help="Source config path")
    parser.add_argument(
        "--output",
        default="release_payload/config.json",
        help="Output path for sanitized release config",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    output_path = Path(args.output)

    source_config = _load_source_config(source_path)
    sanitized_config = _sanitize_config(source_config)
    _write_config(output_path, sanitized_config)

    removed_keys = sorted(EXCLUDED_TOP_LEVEL_KEYS.intersection(source_config.keys()))
    removed_text = ", ".join(removed_keys) if removed_keys else "none"
    print(f"Generated {output_path} (removed keys: {removed_text})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
