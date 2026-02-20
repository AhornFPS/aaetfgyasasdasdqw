#!/usr/bin/env python3
"""
Overlay trace replay/analyzer.

Input format: JSONL rows produced by overlay trace export, e.g.:
{"ts_server_trace_ms": 1771538461347, "lane":"normal", "category":"event", "data": {...}, "meta": {...}}
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter

import websockets

# Allow running from repo root or directly from tools/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from overlay_events import normalize_overlay_event


def iter_rows(path):
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            category = str(row.get("category") or "").strip()
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else None
            if category:
                yield line_no, row, category, data, meta


def _extract_ts_ms(row, data):
    for key in ("ts_server_trace_ms", "ts_server_rx_ms", "ts_source_ms"):
        try:
            v = int((row or {}).get(key))
            if v > 0:
                return v
        except Exception:
            pass
        try:
            v = int((data or {}).get(key))
            if v > 0:
                return v
        except Exception:
            pass
    return None


def load_trace_events(path, max_events=0):
    events = []
    for _, row, category, data, meta in iter_rows(path):
        events.append(
            {
                "ts_ms": _extract_ts_ms(row, data),
                "message": {"category": category, "data": data, **({"meta": meta} if meta else {})},
            }
        )
        if max_events and len(events) >= max_events:
            break
    return events


def analyze_trace(path):
    lane_counts = Counter()
    type_counts = Counter()
    dedupe_candidates = 0
    total = 0

    for seq, (_, _, category, data, _) in enumerate(iter_rows(path), start=1):
        evt = normalize_overlay_event(category, data, seq=seq)
        lane_counts[evt["category"]] += 1
        type_counts[evt["type"]] += 1
        if evt["dedupe_key"]:
            dedupe_candidates += 1
        total += 1

    print(f"trace: {path}")
    print(f"events_total: {total}")
    print("lanes:")
    for lane in ("state", "critical", "normal", "cosmetic"):
        print(f"  {lane}: {lane_counts[lane]}")
    print(f"dedupe_candidates: {dedupe_candidates}")
    print("top_types:")
    for t, n in type_counts.most_common(10):
        print(f"  {t}: {n}")


async def _replay_events(clients, events, speed):
    if not events:
        return 0

    sent = 0
    prev_ts = events[0]["ts_ms"]
    for evt in events:
        ts_ms = evt["ts_ms"]
        if prev_ts is not None and ts_ms is not None:
            dt_ms = max(0, ts_ms - prev_ts)
            await asyncio.sleep(dt_ms / 1000.0 / speed)
        prev_ts = ts_ms

        if not clients:
            break

        msg = json.dumps(evt["message"], ensure_ascii=True)
        websockets.broadcast(clients, msg)
        sent += 1
    return sent


async def serve_replay(args):
    events = load_trace_events(args.trace, max_events=args.max_events)
    if not events:
        print("No valid events found in trace.")
        return 1

    clients = set()
    client_ready = asyncio.Event()

    async def ws_handler(websocket):
        path = getattr(websocket, "path", None)
        if path is None and hasattr(websocket, "request"):
            path = websocket.request.path
        if path != args.path:
            await websocket.close(1008, "Invalid Path")
            return

        clients.add(websocket)
        client_ready.set()
        print(f"client connected: {getattr(websocket, 'remote_address', None)}")
        try:
            await websocket.wait_closed()
        finally:
            clients.discard(websocket)
            print("client disconnected")

    print(f"trace: {args.trace}")
    print(f"events_loaded: {len(events)}")
    print(f"ws_listen: ws://{args.host}:{args.port}{args.path}")
    print(f"speed: {args.speed}x")
    print("waiting for client...")

    async with websockets.serve(ws_handler, args.host, args.port):
        await client_ready.wait()

        run_idx = 0
        while True:
            run_idx += 1
            sent = await _replay_events(clients, events, args.speed)
            print(f"replay_run={run_idx} sent={sent}")

            if not args.loop:
                break
            if args.loop_delay > 0:
                await asyncio.sleep(args.loop_delay)
            while not clients:
                await asyncio.sleep(0.1)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Replay/analyze overlay event trace JSONL.")
    ap.add_argument("trace", help="Path to JSONL trace file")
    ap.add_argument("--analyze", action="store_true", help="Print lane/type summary and exit")
    ap.add_argument("--host", default="127.0.0.1", help="WS bind host for replay mode")
    ap.add_argument("--port", type=int, default=31339, help="WS bind port for replay mode")
    ap.add_argument("--path", default="/better_planetside", help="WS path (must match overlay)")
    ap.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (e.g. 2.0)")
    ap.add_argument("--max-events", type=int, default=0, help="Replay only first N events (0=all)")
    ap.add_argument("--loop", action="store_true", help="Loop replay continuously")
    ap.add_argument("--loop-delay", type=float, default=1.0, help="Delay in seconds between loop runs")
    args = ap.parse_args()

    if not os.path.isfile(args.trace):
        print(f"Trace file not found: {args.trace}")
        return 2
    if args.speed <= 0:
        print("--speed must be > 0")
        return 2

    if args.analyze:
        analyze_trace(args.trace)
        return 0

    return asyncio.run(serve_replay(args))


if __name__ == "__main__":
    raise SystemExit(main())
