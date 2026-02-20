# Rust Port Execution Plan

## Phase 1 - Main UI Parity (Current Priority)
Goal: every Python main-window control exists in Rust UI, even if backend is TODO.

1. Lock navigation and tab hierarchy
- Status: done
- Files: `src/launcher/mod.rs`, `src/launcher/ui.rs`

2. Complete top-level pages with Python-equivalent controls
- Status: in progress
- Files: `src/launcher/dashboard.rs`, `src/launcher/game_launcher.rs`, `src/launcher/characters_page.rs`, `src/launcher/settings_page.rs`

3. Complete overlay sub-tab control surface
- Status: in progress
- Files: `src/launcher/identity.rs`, `src/launcher/events.rs`, `src/launcher/crosshair.rs`, `src/launcher/killstreak.rs`, `src/launcher/stats.rs`, `src/launcher/killfeed.rs`, `src/launcher/voice.rs`, `src/launcher/twitch.rs`, `src/launcher/obs.rs`

4. Enforce overlay click policy from main UI move mode
- Status: done (baseline)
- Files: `src/app.rs`, `src/launcher/identity.rs` (+ per-tab move buttons)

5. Record exact Python handler references for missing backend logic
- Status: in progress
- Files: all launcher tab files (TODO comments)

Exit criteria for Phase 1
- All major Python controls are visible in Rust.
- `cargo check` passes.
- Each non-implemented action has a TODO with Python source reference.

## Phase 2 - Behavior Wiring
Goal: make controls functional with parity logic.

1. Settings binding and persistence parity
- Files: `src/config.rs`, `src/app.rs`, launcher tabs

2. Event slot system parity (`+NEW/DELETE/RENAME/IMPORT/EXPORT`)
- Python refs: `Dior Client.py` slot functions, `overlay_config_qt.py`

3. Full implementation of per-tab save/test/move actions
- Python refs: `Dior Client.py` save/test handlers

4. Worker/runtime live updates
- Files: `src/control.rs`, `src/main.rs`, `src/app.rs`

Exit criteria for Phase 2
- All controls update runtime and persist correctly.
- No placeholder-only buttons remain on core paths.

## Phase 3 - Full Runtime Parity and Hardening
Goal: fully replace Python runtime path with Rust runtime path.

1. Complete launcher/character analytics behavior
2. OBS/twitch/voice platform parity (including Linux-specific paths)
3. Compatibility validation with existing ingest/websocket workflow
4. Test harness + parity checklist signoff

Exit criteria for Phase 3
- Feature parity accepted against Python app behavior.
- Regression checks and smoke tests pass.
