#!/usr/bin/env python3
"""
Capture a Python-overlay latency snapshot from live websocket events.

Output schema matches the Tauri spike snapshot format so
`tools/compare_latency_snapshots.py` can compare groups directly.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import websockets


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    idx = int((p / 100.0) * len(s))
    idx = max(0, min(len(s) - 1, idx))
    return s[idx]


def summarize(samples: List[float]) -> Dict[str, Optional[float]]:
    if not samples:
        return {"count": 0, "last_ms": None, "p50_ms": None, "p95_ms": None}
    return {
        "count": len(samples),
        "last_ms": round(samples[-1]),
        "p50_ms": round(percentile(samples, 50) or 0),
        "p95_ms": round(percentile(samples, 95) or 0),
    }


def ws_candidates(host: str, ports: List[int], paths: List[str]) -> List[str]:
    out = []
    for port in ports:
        for path in paths:
            out.append(f"ws://{host}:{port}{path}")
    return out


def iter_wire_events(msg: str):
    try:
        payload = json.loads(msg)
    except Exception:
        return
    if isinstance(payload, dict) and payload.get("kind") == "batch":
        events = payload.get("events")
        if isinstance(events, list):
            for evt in events:
                if isinstance(evt, dict):
                    yield evt
        return
    if isinstance(payload, dict):
        yield payload


async def capture_snapshot(
    urls: List[str],
    duration_s: float,
    max_events: int,
    warmup_ms: int,
    max_latency_ms: int,
) -> Tuple[str, Dict[str, object]]:
    last_err = None
    for url in urls:
        try:
            async with websockets.connect(url) as ws:
                src_samples: List[float] = []
                rx_samples: List[float] = []
                total_events = 0
                sampled_events = 0
                dropped_stale = 0
                started = time.time()
                started_ms = int(started * 1000)

                while True:
                    if duration_s > 0 and (time.time() - started) >= duration_s:
                        break
                    if max_events > 0 and total_events >= max_events:
                        break

                    timeout_s = 1.0
                    if duration_s > 0:
                        remain = duration_s - (time.time() - started)
                        if remain <= 0:
                            break
                        timeout_s = min(timeout_s, max(0.05, remain))

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
                    except asyncio.TimeoutError:
                        continue

                    now_ms = int(time.time() * 1000)
                    for evt in iter_wire_events(msg):
                        data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
                        ts_source = int(data.get("ts_source_ms") or 0)
                        ts_rx = int(data.get("ts_server_rx_ms") or 0)
                        total_events += 1

                        # Ignore startup replay bursts and stale state payloads.
                        if warmup_ms > 0 and (now_ms - started_ms) < warmup_ms:
                            continue

                        sampled = False
                        if ts_source > 0:
                            d = max(0, now_ms - ts_source)
                            if max_latency_ms <= 0 or d <= max_latency_ms:
                                src_samples.append(d)
                                sampled = True
                            else:
                                dropped_stale += 1
                        if ts_rx > 0:
                            d = max(0, now_ms - ts_rx)
                            if max_latency_ms <= 0 or d <= max_latency_ms:
                                rx_samples.append(d)
                                sampled = True
                            else:
                                dropped_stale += 1

                        if sampled:
                            sampled_events += 1
                        if max_events > 0 and total_events >= max_events:
                            break

                snap = {
                    "captured_at_ms": int(time.time() * 1000),
                    "event_count": int(total_events),
                    "sampled_event_count": int(sampled_events),
                    "dropped_stale_samples": int(dropped_stale),
                    "warmup_ms": int(warmup_ms),
                    "max_latency_ms": int(max_latency_ms),
                    "source_latency": summarize(src_samples),
                    "server_rx_latency": summarize(rx_samples),
                    "ws_endpoint": url,
                }
                return url, snap
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Could not connect to any websocket endpoint: {last_err}")


def default_output_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "BetterPlanetside" / "latency_snapshots_python"
    else:
        base = Path("latency_snapshots_python")
    base.mkdir(parents=True, exist_ok=True)
    ts_ms = int(time.time() * 1000)
    return base / f"latency_snapshot_{ts_ms}.json"


def ts_iso_utc(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000.0))


def parse_csv_ints(value: str) -> List[int]:
    out: List[int] = []
    for chunk in (value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.append(int(chunk))
    return out


def parse_csv_paths(value: str) -> List[str]:
    out: List[str] = []
    for chunk in (value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith("/"):
            chunk = "/" + chunk
        out.append(chunk)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture Python overlay latency snapshot from live WS feed.")
    ap.add_argument("--host", default="127.0.0.1", help="Websocket host")
    ap.add_argument(
        "--ports",
        default="31338,31339",
        help="Comma-separated ports to try in order",
    )
    ap.add_argument(
        "--paths",
        default="/better_planetside,/events",
        help="Comma-separated websocket paths to try in order",
    )
    ap.add_argument(
        "--duration",
        type=float,
        default=8.0,
        help="Capture duration in seconds (set 0 to disable duration stop)",
    )
    ap.add_argument(
        "--max-events",
        type=int,
        default=2000,
        help="Stop after this many events (0 disables event limit)",
    )
    ap.add_argument(
        "--warmup-ms",
        type=int,
        default=1000,
        help="Ignore events during startup warmup period (default: 1000)",
    )
    ap.add_argument(
        "--max-latency-ms",
        type=int,
        default=5000,
        help="Discard stale latency samples above this value (default: 5000, 0 disables)",
    )
    ap.add_argument(
        "--out",
        default="",
        help="Output JSON file path (default: %%APPDATA%%/BetterPlanetside/latency_snapshots_python/...)",
    )
    args = ap.parse_args()

    ports = parse_csv_ints(args.ports)
    paths = parse_csv_paths(args.paths)
    urls = ws_candidates(args.host, ports, paths)

    url, snapshot = asyncio.run(
        capture_snapshot(
            urls=urls,
            duration_s=float(args.duration),
            max_events=int(args.max_events),
            warmup_ms=max(0, int(args.warmup_ms)),
            max_latency_ms=max(0, int(args.max_latency_ms)),
        )
    )

    ts_ms = int(time.time() * 1000)
    payload = {
        "snapshot": snapshot,
        "ts_iso": ts_iso_utc(ts_ms),
        "ts_ms": ts_ms,
    }

    out_path = Path(args.out) if args.out else default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    print(f"Captured from: {url}")
    print(f"Saved snapshot: {out_path}")
    print(
        "Source p50/p95:",
        snapshot["source_latency"]["p50_ms"],
        "/",
        snapshot["source_latency"]["p95_ms"],
        "ms",
    )
    print(
        "Server-rx p50/p95:",
        snapshot["server_rx_latency"]["p50_ms"],
        "/",
        snapshot["server_rx_latency"]["p95_ms"],
        "ms",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
