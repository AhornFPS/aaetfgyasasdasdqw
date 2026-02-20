# Tauri Spike (Isolated)

This is an isolated Tauri testbed for parity checks against the current overlay pipeline.

## Goals
- Transparent always-on-top window behavior
- Click-through toggle behavior
- Basic websocket ingest from existing overlay event endpoint

## Layout
- `frontend/`: static HTML/JS UI for event stream smoke testing
- `src-tauri/`: Tauri host app (Rust)

## Run (Dev)
1. Install Tauri CLI (one-time):
   - `cargo install tauri-cli --version "^2.0.0"`
2. From this folder:
   - `cd overlay-next/tauri-spike`
   - `cargo tauri dev`

If `cargo tauri` is not installed, use:
- `cargo run --manifest-path src-tauri/Cargo.toml`

## Expected Smoke Test
1. Window opens as transparent always-on-top.
2. Event counter increments when websocket events arrive from `ws://127.0.0.1:31338/better_planetside`.
3. Click-through toggle button switches between:
   - click-through ON (overlay ignores mouse)
   - click-through OFF (overlay receives mouse)

