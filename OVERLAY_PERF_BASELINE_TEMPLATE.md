# Overlay Performance Baseline Report

## Test Metadata
- Date:
- Branch:
- Build/runtime:
- Config profile:
- `overlay_perf_debug`:
- Scenario:

## Load Profile
- Session duration:
- Approx events/min:
- Peak burst window:
- Resolution / monitor count:
- Game mode:

## Client Metrics (HUD)
- `dispatch_ms` last/avg:
- `e2e_ms` last/avg:
- `ws_to_js_ms` last/avg:

## Server Metrics (`perf_stats`)
- `events_in_total`:
- `events_out_total`:
- `flush_count`:
- `last_flush_size`:
- `max_pending_state`:
- `max_pending_transient`:
- `coalesce_replaced`:
- `dropped_total`:
- `dropped_transient_overflow`:
- `events_in_state` / `events_out_state`:
- `events_in_critical` / `events_out_critical`:
- `events_in_normal` / `events_out_normal`:
- `events_in_cosmetic` / `events_out_cosmetic`:
- `deduped_total`:
- `dropped_cosmetic_total`:
- `dropped_normal_total`:
- `dedupe_window_ms`:
- `max_transient_pending_cfg`:
- `ws_batching_v2`:
- `batch_flush_count` / `legacy_flush_count`:
- `last_batch_size`:

## Observations
- Visual stutter:
- Missing critical events:
- Focus/z-order issues:
- Notes:

## Comparison Notes (Current vs Tauri Spike)
- Current stack result:
- Tauri spike result:
- Decision gate outcome:
