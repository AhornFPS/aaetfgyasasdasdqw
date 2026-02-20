# UI Parity Playbook (Python -> Rust)

Rule #1: copy the Python app as closely as possible, both visuals and functionality.

This document is the working reference for porting each tab from the Python Qt app to Rust `egui`.

## Source Of Truth
- Python UI files in repo root (example: `dashboard_qt.py`, `launcher_qt.py`, `characters_qt.py`, `settings_qt.py`).
- Rust UI files in `overlay-next/src/launcher/`.
- If Rust behavior differs, Python wins unless there is a hard platform constraint.

## Parity Workflow (Use For Every Tab)
1. Locate the Python tab source file and identify the exact widget tree order.
2. Extract hard constants first:
   - fixed widths/heights
   - margins/spacing
   - font sizes/colors
   - row/column behavior
3. Port layout in the same vertical order before styling details.
4. Port interactions and state semantics (button toggles, sort behavior, defaults).
5. Validate side-by-side with same window size and resizing steps.
6. Fix geometry first, then typography/colors, then secondary polish.

## Dashboard Mapping (Reference Implementation)
Python source: `dashboard_qt.py`  
Rust source: `overlay-next/src/launcher/dashboard.rs`

### Layout Mapping
- Header row:
  - Python: KD button left, server controls right.
  - Rust: same row order and alignment.
- Graph:
  - Python: `TelemetryGraph.setFixedHeight(150)`.
  - Rust: graph height `150`.
- Graph mode row:
  - Python: left button `MODE: ...`, then separate centered total row.
  - Rust: same structure (fixed mode row + centered total row).
- Total players label:
  - Python: centered.
  - Rust: explicit centered draw in row rect.
- Faction row:
  - Python: `QHBoxLayout` with spacing `15`.
  - Rust: top-aligned horizontal row, spacing `15`, fixed per-column width.
- Faction panel body:
  - Python: centered text block, progress bar, then table.
  - Rust: same sequence and alignment.
- Table:
  - Python: min height `300`, headers `PLAYER/K/KPM/D/A/KD/KDA`, stat columns fixed and compact.
  - Rust: min height `300`, same header labels, same compact fixed geometry.

### Interaction Mapping
- KD mode toggle: equivalent toggle behavior.
- Graph mode toggle: equivalent `ALL PLAYERS`/`FACTIONS` behavior.
- Server dropdown: same world list/mapping.
- Faction tables:
  - Python headers are clickable and drive sort state.
  - Rust has clickable header cells and per-faction sort state.

## Egui Pitfalls Found (Important)
- Avoid `ui.columns(...)` for this dashboard block: it can introduce vertical expansion artifacts in scroll contexts.
- Avoid `allocate_ui_with_layout(..., vec2(width, 0.0))` for major row containers: can cause hidden spacing/gap behavior.
- Global button padding can break tiny header-cell alignment:
  - use custom painted/clickable header cells for compact column headers.
- Header and row column widths must be computed from the same base width.
- Use unique `ScrollArea` ids per faction to avoid id collision bugs.

## Reusable Rules For Other Tabs
- Build the same container order as Python first; do not optimize early.
- Keep explicit constants close to Python values before any responsive tweaks.
- For dense controls, prefer custom painted cells over default buttons if theme padding causes drift.
- Keep all row/column math in one place and share it between header and body.
- Keep visual and functional parity together: do not leave interactive headers static if Python supports interactions.

## Validation Checklist Per Tab
- Side-by-side screenshot at:
  - normal window size
  - narrower width
  - slightly larger width
- Check:
  - element order and alignment
  - spacing/margins
  - fixed-size controls
  - button text and casing
  - interaction behavior (toggle/sort/select)
- Runtime checks:
  - `cargo check`
  - manual resize behavior
  - no clipped borders/text

## Baseline App Behaviors Already Locked
- App opens on `Dashboard` by default.
- Main launcher window is not always-on-top.
- Overlay viewport remains always-on-top.
- Launcher window size/position persists across restarts.

