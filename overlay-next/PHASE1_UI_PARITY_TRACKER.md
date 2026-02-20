# Phase 1 UI Parity Tracker

Status legend: `done`, `in_progress`, `todo`

Reference guide: `UI_PARITY_PLAYBOOK.md` (Python->Rust layout/behavior workflow and dashboard baseline mapping).

## Top-Level Pages
- `Dashboard` (`dashboard_qt.py`): `in_progress`
- `Launcher` (`launcher_qt.py`): `in_progress`
- `Characters` (`characters_qt.py`): `in_progress`
- `Settings` (`settings_qt.py`): `in_progress`

## Overlay Sub-Tabs
- `Identity`: `in_progress`
- `Events`: `in_progress`
- `Killstreak`: `in_progress`
- `Crosshair`: `in_progress`
- `Stats`: `in_progress`
- `Killfeed`: `in_progress`
- `Voice`: `in_progress`
- `Twitch`: `in_progress`
- `OBS / Stream`: `in_progress`

## Critical Interaction Constraints
- Overlay click-through default: `done`
- Clickable only during move mode: `done` (baseline toggle wiring)
- Per-widget move interaction parity: `todo`

## Immediate Remaining UI Gaps (Phase 1)
- Add any missing button labels from Python tabs that are not yet visible in Rust.
- Add missing combo/slider placeholders where Python has explicit controls.
- Normalize button labels to Python wording where feasible.
- Keep TODO references to Python handlers beside each placeholder action.
- Remove duplicate temporary controls once each Python-equivalent control is wired to real state.

## File-by-File Progress (Phase 1 Start)
- `src/launcher/ui.rs`: `done` (top-level nav + overlay sub-nav)
- `src/launcher/mod.rs`: `done` (top-level tab state + move mode flag)
- `src/app.rs`: `done` (overlay click-through default, move-mode override)
- `src/launcher/events.rs`: `in_progress` (added slot buttons + image/sound add/del placeholders)
- `src/launcher/crosshair.rs`: `in_progress` (label parity update + button text parity)
- `src/launcher/dashboard.rs`: `in_progress`
- `src/launcher/game_launcher.rs`: `in_progress`
- `src/launcher/characters_page.rs`: `in_progress`
- `src/launcher/settings_page.rs`: `in_progress`
- `src/launcher/identity.rs`: `in_progress`
- `src/launcher/killstreak.rs`: `in_progress`
- `src/launcher/stats.rs`: `in_progress`
- `src/launcher/killfeed.rs`: `in_progress`
- `src/launcher/voice.rs`: `in_progress`
- `src/launcher/twitch.rs`: `in_progress`
- `src/launcher/obs.rs`: `in_progress`
