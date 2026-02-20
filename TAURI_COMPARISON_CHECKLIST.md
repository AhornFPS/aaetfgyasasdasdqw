# Tauri Overlay Comparison Checklist

## Goal
Use the same replay/live scenarios to compare:
- current optimized Python + web overlay
- Tauri-based overlay spike

## Test Scenarios
1. Borderless-windowed gameplay with burst events
2. Focus switches (game <-> desktop <-> launcher)
3. Multi-monitor + mixed DPI
4. OBS/browser-source compatibility

## Behavior Parity (Pass/Fail)
- Transparent window
- Topmost behavior
- Click-through behavior
- No focus steal
- Correct scaling/position
- Overlay state recovery after alt-tab

## Performance Metrics (same run duration)
- Median e2e latency
- P95 e2e latency
- `events_in_total` vs `events_out_total`
- `dropped_total`
- `deduped_total`
- Flush rate and average batch size
- Frame stability (HUD dispatch/e2e averages)

## Run Template
Use one table row per run:

| Runtime | Scenario | FPS Target | Median E2E (ms) | P95 E2E (ms) | Dropped | Deduped | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| Current | Burst | 120 |  |  |  |  |  |
| Tauri | Burst | 120 |  |  |  |  |  |

## Decision Rule
- Migrate only if Tauri passes behavior parity and is equal/better on median + P95 latency with no critical regressions.
- Otherwise keep current stack and continue incremental optimization.
