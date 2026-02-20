# Overlay Event Performance Master Plan (Current Python + Web Overlay)

## Context and Direction
- `overlay-next/` (Rust port) is intentionally out of scope for this workstream.
- We will improve performance in the current runtime stack:
  - Event producers: `census_worker.py`, `Dior Client.py`
  - Event transport: `overlay_server.py`
  - Overlay runtime/render bridge: `overlay_window.py`
  - Frontend renderer: `web_overlay/index.html`, `web_overlay/dispatcher.js`, `web_overlay/websocket.js`
- Primary objective: reduce event latency and burst instability first, then improve rendering cost.

## Success Metrics (Must Be Measured)
- Median event latency (producer timestamp -> rendered timestamp): <= 100 ms
- P95 latency under burst (200+ events/min short spike): <= 200 ms
- Web overlay frame budget during bursts: <= 16.7 ms average (60 FPS target)
- No drop of critical events (`Kill`, `Death`, `Headshot`, `Revive Taken`, alert outcomes)
- Bounded queue growth with deterministic drop/coalesce policy for cosmetic events

## Phase 0: Baseline and Observability (No Logic Changes)
### Tasks
1. Add producer timestamp to every outbound overlay event (if missing) in `Dior Client.py` path that calls overlay emit/send.
2. Add queue and flush metrics to `overlay_server.py`:
   - current queue length
   - max queue length
   - events accepted/sec
   - events dropped/sec
   - flush batch size
3. Add receiver/render timing in JS:
   - websocket receive timestamp
   - dispatch start/end timestamp
   - render commit timestamp
4. Add metrics toggle in config (e.g. `overlay_perf_debug=true`) to avoid noisy logs by default.
5. Add a compact debug HUD in `web_overlay` showing key live metrics.

### Deliverables
- Metrics available in logs + optional HUD.
- A one-page baseline report with before numbers.

### Exit Criteria
- We can measure end-to-end latency and identify top burst sources by event type.

## Phase 1: Event Contract v2 (Events First)
### Tasks
1. Introduce structured event schema module (new `overlay_events.py`) with normalized fields:
   - `id` (uuid/monotonic id)
   - `type` (enum-like string)
   - `category` (`critical|normal|cosmetic|state`)
   - `priority` (int)
   - `ts_source_ms`
   - `ttl_ms`
   - `dedupe_key`
   - `coalesce_key`
   - `payload`
2. Implement adapter layer for legacy string events:
   - Legacy inputs mapped to v2 in one place only.
3. Define authoritative event taxonomy table (critical vs cosmetic).
4. Validate schema at dispatch boundary and reject malformed events safely.

### Deliverables
- `overlay_events.py`
- Mapping table doc (in this file appendix or separate markdown)
- Runtime compatible with both legacy and v2 during transition

### Exit Criteria
- All events reaching websocket path are normalized v2 objects.

## Phase 2: Server-Side Queue, Dedupe, and Coalesce
### Tasks
1. Replace ad hoc pending state in `overlay_server.py` with explicit queue manager:
   - separate lanes for `critical`, `normal`, `cosmetic`, `state`
2. Implement dedupe window (default 120-250 ms) by `dedupe_key`.
3. Implement coalescing for high-frequency event classes:
   - hitmarker/headshot-hitmarker bursts
   - repeated streak updates
   - rapid transient UI toggles
4. Implement bounded memory policy:
   - hard max queue size
   - drop oldest cosmetic first
   - never drop critical without explicit hard-fail logging
5. Add flush scheduler with target cadence (60 Hz max, adaptive fallback 30 Hz).

### Deliverables
- Deterministic queueing policy
- Event loss policy documented and testable

### Exit Criteria
- Queue remains bounded under synthetic bursts with acceptable latency.

## Phase 3: Wire Protocol Optimization (Batching)
### Tasks
1. Switch websocket payload format to batched envelopes:
   - `{tick_ts, seq, events:[...]}`
2. Batch by frame cadence, not per event push.
3. Add backward compatibility option (`legacy_ws_payload`) for rollback.
4. Compress repeated static fields by short keys/lookup ids where useful.

### Deliverables
- Stable batched protocol v2
- Toggleable fallback to current behavior

### Exit Criteria
- Network/churn overhead reduced; fewer websocket callbacks per second.

## Phase 4: JS Runtime Scheduler (Event Processing Layer)
### Tasks
1. In `web_overlay/dispatcher.js`, process inbound events via frame loop (`requestAnimationFrame`) only.
2. Separate handling paths:
   - state events: last-write-wins
   - transient events: queue + ttl + priority
3. Enforce TTL expiry before render to avoid stale burst artifacts.
4. Add object pooling for repeated transient nodes/effects.
5. Convert expensive per-event DOM writes into batched commit per frame.

### Deliverables
- Deterministic client-side scheduler
- Lower main-thread spikes during bursts

### Exit Criteria
- Stable frame-time under load with no runaway DOM churn.

## Phase 5: Event-Class Specific Optimizations
### Tasks
1. Hitmarker family:
   - merge burst events into one active indicator with intensity counter
2. Killfeed:
   - append buffer and commit on frame; cap visible entries
3. Streak/multikill:
   - update in-place if same coalesce key
4. Twitch/chat overlays:
   - cap visible messages and use pooled elements
5. Crosshair/state toggles:
   - state channel only, no transient spam

### Deliverables
- Per-feature tuning implemented and measured

### Exit Criteria
- P95 latency and frame targets met in realistic play sessions.

## Phase 6: Hardening, Tests, and Rollout
### Tasks
1. Add targeted tests for queue policy and dedupe/coalesce logic (Python unit tests near new queue manager).
2. Add replay harness for recorded event traces to regression-test latency/drops.
3. Add feature flags in config:
   - `event_pipeline_v2`
   - `ws_batching_v2`
   - `js_scheduler_v2`
4. Roll out in stages:
   - internal default off
   - canary on
   - full on after metrics pass
5. Prepare rollback procedure (toggle flags only, no code revert required).

### Deliverables
- Reproducible tests + replay traces
- Safe rollout/rollback path

### Exit Criteria
- v2 pipeline enabled by default with observed gains and no critical regressions.

## Implementation Order (Execution Sequence)
1. Phase 0 instrumentation
2. Phase 1 schema + adapter
3. Phase 2 queue/dedupe/coalesce
4. Phase 3 websocket batching
5. Phase 4 JS frame scheduler
6. Phase 5 event-class tuning
7. Phase 6 tests + staged rollout

## Parallel Track: Tauri Comparison (Decision Support, Not Mainline)
### Scope
- Build a minimal Tauri overlay spike in an isolated branch/workspace.
- Compare against the optimized current stack using the same event replay traces.
- Do not block Phase 0-6 delivery on this track.

### Required Comparison Scenarios
1. PlanetSide 2 borderless-windowed gameplay with burst events
2. Focus transitions (game <-> desktop <-> launcher)
3. Multi-monitor setup and different DPI scales
4. OBS/browser-source compatibility for the same payload stream

### Decision Gates
1. Overlay behavior parity:
   - transparent, topmost, click-through, no focus stealing
2. Performance parity or better:
   - median and P95 latency at least equal to current optimized path
   - stable frame times under burst
3. Reliability parity:
   - no critical event regressions during replay and live test runs

### Decision Outcomes
- Pass all gates: plan a staged migration path to Tauri renderer.
- Fail any gate: keep current stack and continue optimizing Python + web overlay.

## Risks and Mitigations
- Risk: Hidden dependencies on string event names.
  - Mitigation: adapter layer + dual-path logging before cutover.
- Risk: Over-coalescing removes user-expected feedback.
  - Mitigation: per-event-type allowlist; never coalesce critical events.
- Risk: Debug instrumentation adds overhead.
  - Mitigation: runtime flag gating and sampling mode.
- Risk: JS scheduler introduces order regressions.
  - Mitigation: sequence numbers + replay test fixtures.

## File-Level Worklist
- `census_worker.py`
  - audit event producers and normalize type names
- `Dior Client.py`
  - central event adapter boundary; timestamp and metadata injection
- `overlay_server.py`
  - queue manager, lane policy, batching, metrics
- `overlay_window.py`
  - bridge to web overlay only where needed; remove duplicated state pushes over time
- `web_overlay/websocket.js`
  - batch envelope receive and decode
- `web_overlay/dispatcher.js`
  - frame scheduler, ttl handling, coalesce behavior
- `web_overlay/index.html`
  - debug HUD toggle and perf panel
- `config.json` handling
  - new feature flags with safe defaults
- Tauri spike (separate branch/worktree)
  - window behavior parity tests + replay-driven perf comparison

## Definition of Done (Program Level)
- Event pipeline is v2 by default.
- Critical events are lossless in normal operation.
- Cosmetic burst behavior is bounded and smooth.
- Metrics prove improvement versus baseline.
- Rollback is config-only.

## Next Immediate Step
- Start Phase 0 by adding instrumentation hooks and a baseline capture script/report template.
