# Phase 6 Rollout Notes

## Feature Flags
- `event_pipeline_v2`:
  - `true`: queued lane pipeline + batching path
  - `false`: legacy immediate send path (metrics still emitted)
- `js_scheduler_v2`:
  - `true`: frame-based JS scheduler
  - `false`: immediate JS dispatch path
- `overlay_ws_batching_v2`:
  - `true`: websocket batch envelopes
  - `false`: per-event websocket payload

## Recommended Defaults (current)
- `event_pipeline_v2 = true`
- `js_scheduler_v2 = true`
- `overlay_ws_batching_v2 = true`

## Rollback Matrix
- Suspect server queue issue:
  - set `event_pipeline_v2 = false`
- Suspect frontend scheduler issue:
  - set `js_scheduler_v2 = false`
- Suspect websocket batch issue:
  - set `overlay_ws_batching_v2 = false`

Each flag can be toggled independently for bisecting regressions.

## Verification Checklist
1. `events_out_total` tracks `events_in_total` (within expected coalesce/dedupe behavior)
2. `dropped_total` remains near zero under normal gameplay
3. `events_out_normal` and `events_out_critical` continue increasing during bursts
4. `events_out_cosmetic` can lag without affecting core UX
5. No visual regressions in killfeed/streak/event overlays

## Replay Harness
- Run all Phase 6 checks:
  - `python tools/run_phase6_checks.py`
- Compare latency snapshots side-by-side:
  - capture Python snapshot first:
  - `python tools/capture_python_latency_snapshot.py --duration 8 --max-events 2000 --warmup-ms 1000 --max-latency-ms 5000`
  - `python tools/compare_latency_snapshots.py --group tauri:"C:\Users\HornGaming\AppData\Roaming\com.betterplanetside.taurispike\tauri_spike\*.json"`
  - with two groups:
  - `python tools/compare_latency_snapshots.py --group python:"C:\Users\HornGaming\AppData\Roaming\BetterPlanetside\latency_snapshots_python\*.json" --group tauri:"C:\Users\HornGaming\AppData\Roaming\com.betterplanetside.taurispike\tauri_spike\*.json" --details`
- Analyze a captured trace:
  - `python tools/replay_overlay_trace.py "C:\Users\HornGaming\AppData\Roaming\BetterPlanetside\overlay_trace.jsonl" --analyze`
- Replay trace once at original timing:
  - `python tools/replay_overlay_trace.py "C:\Users\HornGaming\AppData\Roaming\BetterPlanetside\overlay_trace.jsonl"`
- Replay at faster speed (example 4x):
  - `python tools/replay_overlay_trace.py "C:\Users\HornGaming\AppData\Roaming\BetterPlanetside\overlay_trace.jsonl" --speed 4`
- Loop replay continuously:
  - `python tools/replay_overlay_trace.py "C:\Users\HornGaming\AppData\Roaming\BetterPlanetside\overlay_trace.jsonl" --loop --loop-delay 0.5`
