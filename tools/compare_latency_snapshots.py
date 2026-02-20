#!/usr/bin/env python3
"""
Compare latency snapshot JSON files side-by-side.

Input format is the Tauri spike snapshot schema:
{
  "snapshot": {
    "source_latency": {"count": 200, "p50_ms": 3, "p95_ms": 10, ...},
    "server_rx_latency": {"count": 200, "p50_ms": 3, "p95_ms": 10, ...},
    "event_count": 1124,
    "ws_endpoint": "ws://..."
  },
  "ts_iso": "...",
  "ts_ms": 1771547551048
}
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class SnapshotRow:
    path: str
    ts_ms: int
    ts_iso: str
    event_count: int
    ws_endpoint: str
    src_count: int
    src_p50: Optional[float]
    src_p95: Optional[float]
    rx_count: int
    rx_p50: Optional[float]
    rx_p95: Optional[float]


def _num(v) -> Optional[float]:
    try:
        x = float(v)
        if x != x:  # NaN
            return None
        return x
    except Exception:
        return None


def load_snapshot(path: str) -> Optional[SnapshotRow]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None

    snap = doc.get("snapshot") if isinstance(doc, dict) else None
    if not isinstance(snap, dict):
        return None

    src = snap.get("source_latency") if isinstance(snap.get("source_latency"), dict) else {}
    rx = snap.get("server_rx_latency") if isinstance(snap.get("server_rx_latency"), dict) else {}
    ts_ms = int(doc.get("ts_ms") or 0)
    ts_iso = str(doc.get("ts_iso") or "")
    return SnapshotRow(
        path=path,
        ts_ms=ts_ms,
        ts_iso=ts_iso,
        event_count=int(snap.get("event_count") or 0),
        ws_endpoint=str(snap.get("ws_endpoint") or ""),
        src_count=int(src.get("count") or 0),
        src_p50=_num(src.get("p50_ms")),
        src_p95=_num(src.get("p95_ms")),
        rx_count=int(rx.get("count") or 0),
        rx_p50=_num(rx.get("p50_ms")),
        rx_p95=_num(rx.get("p95_ms")),
    )


def expand_group_spec(spec: str) -> Tuple[str, List[str]]:
    if ":" not in spec:
        raise ValueError(f"Invalid --group '{spec}'. Expected 'label:glob'.")
    label, pattern = spec.split(":", 1)
    label = label.strip()
    pattern = pattern.strip()
    if not label or not pattern:
        raise ValueError(f"Invalid --group '{spec}'. Expected 'label:glob'.")
    paths = sorted(glob.glob(pattern))
    return label, paths


def summarize_group(rows: List[SnapshotRow]) -> Dict[str, object]:
    def series(attr: str) -> List[float]:
        vals: List[float] = []
        for r in rows:
            v = getattr(r, attr)
            if v is not None:
                vals.append(float(v))
        return vals

    src_p50 = series("src_p50")
    src_p95 = series("src_p95")
    rx_p50 = series("rx_p50")
    rx_p95 = series("rx_p95")
    events = [r.event_count for r in rows if r.event_count > 0]
    endpoints = sorted({r.ws_endpoint for r in rows if r.ws_endpoint})
    return {
        "snapshots": len(rows),
        "event_count_avg": round(statistics.mean(events), 2) if events else None,
        "src_p50_avg": round(statistics.mean(src_p50), 2) if src_p50 else None,
        "src_p95_avg": round(statistics.mean(src_p95), 2) if src_p95 else None,
        "rx_p50_avg": round(statistics.mean(rx_p50), 2) if rx_p50 else None,
        "rx_p95_avg": round(statistics.mean(rx_p95), 2) if rx_p95 else None,
        "src_p95_max": round(max(src_p95), 2) if src_p95 else None,
        "rx_p95_max": round(max(rx_p95), 2) if rx_p95 else None,
        "endpoints": endpoints,
    }


def fmt(v: object) -> str:
    if v is None:
        return "-"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare latency snapshot JSON groups side-by-side.")
    ap.add_argument(
        "--group",
        action="append",
        default=[],
        help="Group input as 'label:glob'. Example: --group tauri:'C:/.../tauri_spike/*.json'",
    )
    ap.add_argument(
        "--details",
        action="store_true",
        help="Print per-snapshot rows after group summary.",
    )
    args = ap.parse_args()

    if not args.group:
        ap.error("at least one --group is required")

    grouped: Dict[str, List[SnapshotRow]] = {}
    rejected = 0

    for spec in args.group:
        try:
            label, paths = expand_group_spec(spec)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 2
        rows: List[SnapshotRow] = []
        for p in paths:
            row = load_snapshot(p)
            if row is None:
                rejected += 1
                continue
            rows.append(row)
        rows.sort(key=lambda r: (r.ts_ms, r.path))
        grouped.setdefault(label, []).extend(rows)

    print("Latency Snapshot Comparison")
    print("===========================")
    if rejected:
        print(f"Rejected files: {rejected}")

    for label, rows in grouped.items():
        s = summarize_group(rows)
        print(f"\n[{label}]")
        print(f"  snapshots:      {fmt(s['snapshots'])}")
        print(f"  event_count_avg:{fmt(s['event_count_avg'])}")
        print(f"  src p50 avg:    {fmt(s['src_p50_avg'])} ms")
        print(f"  src p95 avg:    {fmt(s['src_p95_avg'])} ms")
        print(f"  src p95 max:    {fmt(s['src_p95_max'])} ms")
        print(f"  rx  p50 avg:    {fmt(s['rx_p50_avg'])} ms")
        print(f"  rx  p95 avg:    {fmt(s['rx_p95_avg'])} ms")
        print(f"  rx  p95 max:    {fmt(s['rx_p95_max'])} ms")
        if s["endpoints"]:
            print(f"  endpoints:      {', '.join(s['endpoints'])}")

        if args.details and rows:
            print("  details:")
            for r in rows:
                name = os.path.basename(r.path)
                print(
                    f"    - {name} | {r.ts_iso or r.ts_ms} | "
                    f"src p50/p95={fmt(r.src_p50)}/{fmt(r.src_p95)} | "
                    f"rx p50/p95={fmt(r.rx_p50)}/{fmt(r.rx_p95)} | events={r.event_count}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

