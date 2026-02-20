# Better Planetside Overlay Next (Rust Rewrite)

This directory contains a full rewrite path for the overlay in **Rust**, designed to replace the current Python multi-process stack with a single high-performance runtime.

## Why Rust for this overlay

- **Native desktop integration** on Windows/Linux with transparent always-on-top windows.
- **Single binary architecture**: UI + event ingress in one process.
- **Low latency + low overhead** while handling frequent game events.
- **Safer concurrency** for ingesting websocket feeds and rendering at the same time.

## Current rewrite scope

- `eframe/egui` transparent overlay window.
- Integrated websocket event endpoint at `/events`.
- Real-time kill feed + session stat rendering from incoming JSON.
- Config auto-bootstrap under OS config directory.
- Loads legacy UI font (`BlackOpsOne-Regular.ttf`) from `assets/` when available.
- Includes basic character list management in the control panel (persisted to `characters.json`).

## Run

```bash
cd overlay-next
cargo run
```

Build artifact note:

- `overlay-next/target/` (including `target/debug`) is compiler output only and can grow to multiple GB.
- It is safe to remove anytime with `cargo clean` (next build will regenerate it).

Press `F1` in the overlay window to open the native control panel (`F2` toggles layout edit mode, `F3` toggles mouse passthrough, `Esc` closes panel/edit mode).

- Save/reload `config.json` and live-toggle core overlay settings.
- `Layout Edit Mode` draws draggable on-overlay boxes for feed/stats/streak/crosshair/chat placement.
- In layout edit mode, hold `Shift` while dragging feed/stats/streak/crosshair boxes to resize them.
- Dragging feed/stats/streak boxes snaps to screen edges and screen center (legacy move behavior).
- Panel exposes `Crosshair Dynamic Center` so crosshair can stay anchored to current screen center without forcing fixed X/Y.
- `Layout Edit Mode` also includes draggable anchors for legacy `event` and `hitmarker` global offsets.
- Panel includes a per-event legacy visual override editor (`legacy_visual_overrides` JSON by key).
- Override editor includes `Use Last Visual` to capture geometry from the most recent rendered legacy visual.
- Override editor includes `Save Last Visual` to instantly persist/update an override entry.
- In layout edit mode, a `Last Visual (...)` draggable box appears when available and writes movement back into that event override.
- In layout edit mode, hold `Shift` while dragging `Last Visual (...)` to resize override width/height.
- Mouse passthrough can be toggled in-panel (`mouse_passthrough`), and is auto-disabled while panel/layout edit mode is open.
- Worker/input fields can be edited in-app.
- Use `Apply Worker Changes` to live restart legacy bridge, Census worker, and Twitch worker with current settings.
- `Reload Config` in the panel also reapplies worker settings immediately.
- `Save Config` also reapplies workers when worker-related fields were edited in the panel.
- `ws_bind` changes are also applied by worker reapply (the local WS/HTTP ingest server is rebound live).
- Includes built-in debug actions (`Sample Kill`, `Sample Death`, `Sample Stats`, `Sample Chat`, `Sample Streak`, `Sample Event`).
- Debug section also shows runtime counters (queue/visual/feed/chat/texture-cache) and `Clear Texture Cache`.

By default, it also tries to bridge from the legacy Python overlay websocket at:

- `ws://127.0.0.1:31338/better_planetside`

You can disable or change this in the generated config file under your OS config dir:

- `better-planetside-overlay-next/config.json` -> `legacy_source_ws`
- Common tuning keys:
  - `opacity`, `scale`
  - `mouse_passthrough`
  - `event_queue_active`, `event_queue_max_len`, `event_queue_max_backlog_ms`
  - `kd_mode_revive`
  - `show_twitch_chat`
  - `chat_hold_seconds`
  - `max_chat_items`
  - `chat_anchor_offset_x`, `chat_anchor_offset_y`
  - `play_event_sounds`, `sound_master_volume`
  - `event_offset_x`, `event_offset_y`, `hitmarker_offset_x`, `hitmarker_offset_y`
  - `census_worker_enabled`, `census_service_id`, `census_character_id`
  - `census_multi_kill_window_secs`, `census_weapon_lookup_enabled`
  - `twitch_worker_enabled`, `twitch_channel`, `twitch_nick`
  - `twitch_ignore_special`, `twitch_ignore_users`
  - `game_monitor_enabled`, `game_process_names`, `game_poll_ms`
  - `auto_overlay_visibility`
  - `layout.feed.*`, `layout.stats.*`, `layout.streak.*`, `layout.crosshair.*`
  - `legacy_visual_overrides` (per-event visual overrides keyed by event name/type, lowercase; supports fallback matching such as `kill` for `kill vehicle`)
  - Set `chat_hold_seconds` to `0` for persistent chat lines (no auto-expire).

Example override:

```json
{
  "legacy_visual_overrides": {
    "headshot": {
      "filename": "Headshot.png",
      "sound_filename": "Headshot.ogg",
      "sound_volume": 0.9,
      "x": 520.0,
      "y": 220.0,
      "width": 260.0,
      "height": 140.0,
      "duration_ms": 1200,
      "glow_color": "#00f2ff"
    }
  }
}
```
- Runtime overlay state is persisted to:
  - `better-planetside-overlay-next/runtime_state.json`
  - Includes restored layout geometry (feed/stats/streak/crosshair/chat anchors) plus overlay mode state (`overlay_visible`, `scifi_enabled`) in addition to session/feed/chat data.
- Character list state is persisted to:
  - `better-planetside-overlay-next/characters.json`

Enable the native Twitch IRC worker by setting:

```json
{
  "twitch_worker_enabled": true,
  "twitch_channel": "your_channel_name"
}
```

Twitch parity note:

- Native worker now preserves Twitch author colors (IRC `color` tag) and renders colored author names in the Rust chat overlay.
- Legacy `twitch_message` payloads can also pass `color` / `author_color` for native colorized chat rendering.

Enable the native Census worker by setting:

```json
{
  "census_worker_enabled": true,
  "census_service_id": "s:yourServiceId",
  "census_character_id": "5428xxxxxxxxxxxx",
  "census_multi_kill_window_secs": 4.0,
  "census_weapon_lookup_enabled": true
}
```

If `census_service_id` / `census_character_id` are not set in config, `overlay-next`
also falls back to environment variables from process env or `.env` files:

- `CENSUS_SERVICE_ID` (or `PS2_CENSUS_SERVICE_ID`, `SERVICE_ID`)
- `CENSUS_CHARACTER_ID` (or `PS2_CHARACTER_ID`, `CHARACTER_ID`)

Current Census worker scope:

- Consumes `Death`, `GainExperience`, `PlayerLogin`, `PlayerLogout`, `MetagameEvent`,
  `PlayerFacilityCapture`, and `PlayerFacilityDefend` from the official push stream.
- Emits Rust overlay events for:
  - `kill`
  - `death`
  - `session_raw` (kills/deaths/hs/revives timing).
- Emits legacy-compatible overlay categories for visuals:
  - `hitmarker`
  - `event` (headshot/multi-kill/streak/support/teamkill/class/special weapon/alert events)
  - `streak`
- Honors legacy stats widget padding (`stats` payload `padding`) in native rendering.
- Supports legacy stats background image payload fields (`img_filename` / `img`) in native stats rendering.
- Honors legacy stats payload `scale` for box dimensions and padding.
- Uses legacy default impact behavior for event visuals: `Headshot` and `Death` impact by default when not explicitly overridden.
- Honors legacy `feed` payload geometry/options (`x`, `y`, `width`, `height`, `max_items`) in addition to `feed_config`.
- Supports serialized legacy `event` playback with queue/backlog controls; `hitmarker` remains immediate.
- `events_clear` now clears queued visuals and dedupe guard state.
- Emits login faction events (`Login VS` / `Login NC` / `Login TR` / `Login NSO`) on tracked `PlayerLogin`.
  - Faction resolution prefers `team_id` and falls back to `faction_id` payload fields when needed.
- Preserves streak state across revive flow (hide on death, re-show on revive) to match legacy death/revive behavior.
- Preserves legacy teamkill-death streak semantics (`is_tk_death`): teamkill death does not force reset on immediate follow-up kill.
- Includes attacker-side duplicate victim suppression (0.5s window) to avoid duplicate kill processing bursts.
- Includes specific vehicle event mappings loaded from `assets/experience.json`:
  - `Gunner Kill <Vehicle>`
  - `Kill <Vehicle>` (vehicle destruction)
- Adds cached weapon classification for unknown `attacker_weapon_id` values via Census item lookup
  (for example to detect `Knife Kill` / `Nade Kill` / additional `Spitfire Kill` cases).
  - Cache file: `better-planetside-overlay-next/weapon_event_cache.json`
  - HSR eligibility cache: `better-planetside-overlay-next/weapon_hsr_cache.json`
  - Lookups are applied lazily only for tracked-player-relevant death paths.
- Resolves character IDs to display names for kill/death overlay events with local cache persistence.
  - Cache file: `better-planetside-overlay-next/character_name_cache.json`
- Loads event templates from legacy `config.json` (`events` section) to emit
  `filename`/`sound_filename`/duration/position metadata for Rust-side legacy visuals.
- Legacy event template image arrays are supported (`img: ["a.png","b.png"]`)
  with runtime random selection per emission.
- Hitmarker visuals are now also template-driven from legacy event keys
  (`Hitmarker` / `Headshot Hitmarker`) including image/sound/duration/position.
- Template durations now follow legacy global queue behavior
  (`event_global_duration` / `event_queue_active`) with hitmarker-specific duration handling.
- Event template lookup is spacing/punctuation tolerant (for example `Road Kill`
  in config matches emitted `RoadKill`).
- Includes fallback aliases for common legacy names (for example `Revenge Kill`,
  `Roadkill Victim`, `Max Kill`, `Tankmine Kill` / `AP-Mine Kill`, `Revive`) when matching
  emitted Census event names.
- Uses subset fallback behavior for specific events (for example class kills, headshot death,
  vehicle variants): if a specific event has no configured image/sound in `config.json`,
  it falls back to the parent event.
- Includes compatibility world normalization for merge IDs (`17 -> 1`, `13 -> 10`) for
  alert/world matching logic.
- Includes support-event milestone emissions for tracked support actions
  (for example `Heal 1`, `Repair 1`, ...).
- Loads legacy `streak` config from `config.json` and emits full streak payloads
  (background image, text style/animation, generated knife ring/path offsets) so
  native Census mode keeps streak visuals without relying on Python-side streak rendering.
  - When streak `width`/`height` are not configured, background size is inferred from the streak image asset.
- HSR/DHS tracking now follows legacy weapon-category eligibility
  (only eligible weapon classes contribute to headshot ratio denominators).
- Teamkill victim events keep the streak display behavior while avoiding teamkill death stat inflation.
- This is an initial migration slice; full parity with Python `census_worker.py` is still in progress.

Then send events:

```bash
# example kill event
python - <<'PY'
import asyncio, json, websockets
from datetime import datetime, timezone

async def main():
    uri = "ws://127.0.0.1:38471/events"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "kill",
            "victim": "EnemyHeavy",
            "weapon": "Orion VS54",
            "headshot": True,
            "streak": 3,
            "at": datetime.now(timezone.utc).isoformat(),
        }))

asyncio.run(main())
PY
```

You can also ingest over HTTP during migration:

```bash
curl -X POST http://127.0.0.1:38471/ingest \
  -H "Content-Type: application/json" \
  -d '{"type":"session_raw","k":12,"d":4,"hs":3,"start":1700000000,"acc_t":180}'
```

## Event schema

Events are tagged JSON objects:

- `kill`
- `death`
- `session_snapshot`
- `session_raw`
- `twitch_message`

See `src/events.rs` for full field definitions.

## Legacy compatibility mode

`overlay-next` also accepts the legacy websocket envelope used by the current Python overlay:

```json
{
  "category": "feed",
  "data": { "html": "<b>Kill</b>" }
}
```

Supported legacy categories currently include:

- `stats`, `stats_clear`
- `feed`, `feed_config`, `feed_clear`
- `streak`
- `crosshair`, `crosshair_recoil`
- `event`, `hitmarker`, `events_clear`
- `overlay_visibility`, `scifi_mode`
- `worker_status` (internal runtime status telemetry)
  - Includes WS server on/off, active bind address, WS errors, and worker note/error details.
  - Includes game-monitor worker status (`game_monitor` / `game_error`).
- `twitch_message`
- `session_snapshot`, `session_raw`, `kill`, `death`

Legacy layout fields are also consumed where present (for example `x`, `y`, `width`, `height`, `box_width`, `box_height`, `max_items`).

Legacy event/hitmarker payloads can also carry sound metadata:

- `sound_filename`
- `sound_volume`
- `play_duplicate`
- `event_name`

Rust-side sound playback is disabled by default. Set `play_event_sounds=true` to enable it.

## Parity Gaps (Still Missing)

These are the remaining high-impact migration gaps to reach full app parity with the current Python stack:

- Full launcher/settings UI parity from `Dior Client.py` + `overlay_config_qt.py`
  (character management, event slot import/export, crosshair editor workflows, PS2 settings editor integration).
- Character management parity is only partially ported so far (basic local list persistence exists; full DB/search/profile workflows are still pending).
- Native game process/focus-driven overlay gating parity
  (current Rust runtime does not fully replicate Python-side process/focus control flow yet).
- Voice macro / voice-tab parity (recording, playback routing, legacy voice workflow controls).
- Discord Rich Presence parity (`discord_presence.py`) in the Rust runtime.
- Release/update UX parity (Python release updater and launcher-side update flow).
- Final decommissioning of legacy Python bridge once all ingestion/rendering flows are native.

## Migration Direction

1. Keep ingestion and overlay rendering fully native in Rust.
2. Port remaining launcher/config UX from Qt/Python into Rust-native UI surfaces.
3. Remove Python compatibility dependencies once parity checklist is complete.
