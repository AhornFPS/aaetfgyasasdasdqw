# Better Planetside Rust Port Checklist

Goal: single Rust program with the same behavior as Python main app + overlay, with all controls in the main program UI.

## 1. UI Parity (Main Program First)
- [x] Add top-level tabs: `Dashboard`, `Launcher`, `Characters`, `Overlay`, `Settings`.
- [x] Keep overlay sub-tabs under `Overlay`: `Identity`, `Events`, `Killstreak`, `Crosshair`, `Stats`, `Killfeed`, `Voice`, `Twitch`, `OBS / Stream`.
- [x] Add UI placeholders for missing top-level pages from Python:
  - [x] `dashboard_qt.py` controls (`KD MODE`, server combo, graph mode button).
  - [x] `launcher_qt.py` controls (`INITIALIZE`, `SETTINGS EDITOR`).
  - [x] `characters_qt.py` controls (`SEARCH`, Overview/Weapon/Directives tabs).
  - [x] `settings_qt.py` controls (PS2 path, volume/device, background, discord, update, save).
- [x] Add missing overlay-tab control placeholders so all major Python buttons exist in Rust UI.
- [ ] Replace placeholder controls with real state bindings and persistence parity.

## 2. Overlay Input Rules
- [x] Enforce click-through overlay by default.
- [x] Add move mode switch in main UI.
- [x] Make overlay clickable only while move mode is active.
- [ ] Implement drag/move interactions for each movable overlay widget (feed/stats/streak/crosshair/twitch/events).
- [ ] Exit move mode automatically after save/cancel (parity with intended UX).

## 3. Settings Ownership (Main Program vs Overlay)
- [x] Start centralizing control entry points in main Rust launcher UI.
- [ ] Ensure no settings editor exists inside rendered overlay viewport.
- [ ] Route all setting changes through one config state + save pipeline (`OverlayConfig` + runtime state).
- [ ] Add regression tests for persistence round-trip against `config.json`.

## 4. Behavior Parity Work
- [ ] Map each placeholder button to corresponding Python handler behavior (reference in TODO comments in Rust files).
- [ ] Port event slot management (`+NEW`, `DELETE`, `RENAME`, `IMPORT`, `EXPORT`).
- [ ] Port full stats/killfeed/twitch/voice/crosshair editors (all fields and validation).
- [ ] Port launcher/game settings profile patching behavior.
- [ ] Port character analytics window behavior (tabs + data workers).

## 5. Integration Cleanup
- [ ] Remove dependency on separate Python web overlay process for normal runtime.
- [ ] Keep protocol compatibility for any external ingest endpoints needed (`/ingest`, ws bridge).
- [ ] Validate game-start/game-stop automation parity.

## 6. Validation
- [ ] Add a parity matrix (Python function -> Rust function/module).
- [ ] Add screenshot diff checklist for each tab.
- [ ] Add end-to-end manual script: launch app, toggle each subsystem, verify overlay movement + click-through behavior.
- [ ] Add basic automated tests for config toggles and move mode pass-through behavior.
