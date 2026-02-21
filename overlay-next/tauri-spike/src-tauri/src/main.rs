#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::Manager;

#[derive(Clone, Copy, Debug)]
struct WindowedBounds {
    x: i32,
    y: i32,
    w: u32,
    h: u32,
}

static LAST_WINDOWED_BOUNDS: OnceLock<Mutex<Option<WindowedBounds>>> = OnceLock::new();

fn bounds_store() -> &'static Mutex<Option<WindowedBounds>> {
    LAST_WINDOWED_BOUNDS.get_or_init(|| Mutex::new(None))
}

#[tauri::command]
fn set_clickthrough(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    window
        .set_ignore_cursor_events(enabled)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn set_overlay_mode(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;

    // Re-apply overlay window traits on every toggle; on Windows these can
    // drift when switching click-through states.
    window.set_decorations(false).map_err(|e| e.to_string())?;
    window.set_shadow(false).map_err(|e| e.to_string())?;
    window.set_always_on_top(true).map_err(|e| e.to_string())?;
    let _ = window.set_skip_taskbar(true);

    if enabled {
        if let (Ok(pos), Ok(size)) = (window.outer_position(), window.outer_size()) {
            if let Ok(mut slot) = bounds_store().lock() {
                *slot = Some(WindowedBounds {
                    x: pos.x,
                    y: pos.y,
                    w: size.width,
                    h: size.height,
                });
            }
        }
        window.set_fullscreen(false).map_err(|e| e.to_string())?;
        window.set_resizable(false).map_err(|e| e.to_string())?;
        if let Ok(Some(monitor)) = window.current_monitor() {
            let mpos = monitor.position();
            let msize = monitor.size();
            window
                .set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(
                    mpos.x, mpos.y,
                )))
                .map_err(|e| e.to_string())?;
            window
                .set_size(tauri::Size::Physical(tauri::PhysicalSize::new(
                    msize.width,
                    msize.height,
                )))
                .map_err(|e| e.to_string())?;
        }
    } else {
        window.set_fullscreen(false).map_err(|e| e.to_string())?;
        window.set_resizable(true).map_err(|e| e.to_string())?;
        if let Ok(mut slot) = bounds_store().lock() {
            if let Some(saved) = slot.take() {
                let _ = window.set_position(tauri::Position::Physical(
                    tauri::PhysicalPosition::new(saved.x, saved.y),
                ));
                let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize::new(
                    saved.w, saved.h,
                )));
            }
        }
    }

    Ok(())
}

#[tauri::command]
fn get_overlay_service_ports(app: tauri::AppHandle) -> serde_json::Value {
    let mut http_port: i64 = 31337;
    let mut ws_port: i64 = 31338;
    let mut source = "default";

    let mut candidates: Vec<PathBuf> = if cfg!(debug_assertions) {
        local_dev_config_candidates()
    } else {
        packaged_config_candidates(&app)
    };
    dedupe_paths(&mut candidates);

    for cfg_path in candidates {
        let Ok(raw) = fs::read_to_string(&cfg_path) else {
            continue;
        };
        let Ok(doc) = serde_json::from_str::<serde_json::Value>(&raw) else {
            continue;
        };
        if let Some(obs) = doc.get("obs_service").and_then(|v| v.as_object()) {
            if let Some(v) = obs.get("port").and_then(|v| v.as_i64()) {
                http_port = v;
            }
            if let Some(v) = obs.get("ws_port").and_then(|v| v.as_i64()) {
                ws_port = v;
            }
            source = "config";
            break;
        }
    }

    serde_json::json!({
        "http_port": http_port,
        "ws_port": ws_port,
        "source": source
    })
}

fn local_dev_config_candidates() -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        for dir in cwd.ancestors().take(10) {
            candidates.push(dir.join("config.json"));
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            for dir in exe_dir.ancestors().take(10) {
                candidates.push(dir.join("config.json"));
            }
        }
    }
    candidates
}

fn packaged_config_candidates(app: &tauri::AppHandle) -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(appdata) = std::env::var("APPDATA") {
        candidates.push(PathBuf::from(appdata).join("BetterPlanetside").join("config.json"));
    }
    if let Ok(xdg_config_home) = std::env::var("XDG_CONFIG_HOME") {
        candidates.push(
            PathBuf::from(xdg_config_home)
                .join("BetterPlanetside")
                .join("config.json"),
        );
    }
    if let Ok(home) = std::env::var("HOME") {
        candidates.push(
            PathBuf::from(home)
                .join(".config")
                .join("BetterPlanetside")
                .join("config.json"),
        );
    }
    if let Ok(own_dir) = app.path().app_data_dir() {
        if let Some(parent) = own_dir.parent() {
            candidates.push(parent.join("BetterPlanetside").join("config.json"));
        }
    }
    candidates
}

fn dedupe_paths(paths: &mut Vec<PathBuf>) {
    let mut unique: Vec<PathBuf> = Vec::new();
    for path in paths.drain(..) {
        if !unique.iter().any(|p| p == &path) {
            unique.push(path);
        }
    }
    *paths = unique;
}

#[tauri::command]
fn save_latency_snapshot(
    app: tauri::AppHandle,
    snapshot: serde_json::Value,
) -> Result<String, String> {
    let base_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir failed: {e}"))?;
    let out_dir = base_dir.join("tauri_spike");
    fs::create_dir_all(&out_dir).map_err(|e| format!("mkdir failed: {e}"))?;

    let ts_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| format!("clock failed: {e}"))?
        .as_millis();
    let file_name = format!("latency_snapshot_{}.json", ts_ms);
    let out_path = out_dir.join(file_name);

    let mut payload = serde_json::Map::new();
    payload.insert("ts_ms".to_string(), serde_json::Value::from(ts_ms as u64));
    payload.insert(
        "ts_iso".to_string(),
        serde_json::Value::from(chrono_like_iso_utc(ts_ms as u64)),
    );
    payload.insert("snapshot".to_string(), snapshot);

    let bytes = serde_json::to_vec_pretty(&serde_json::Value::Object(payload))
        .map_err(|e| format!("serialize failed: {e}"))?;
    fs::write(&out_path, bytes).map_err(|e| format!("write failed: {e}"))?;

    Ok(out_path.to_string_lossy().to_string())
}

fn chrono_like_iso_utc(ts_ms: u64) -> String {
    // Keep this dependency-free for the spike.
    // Format: YYYY-MM-DDTHH:MM:SSZ based on system local conversion fallback.
    // For parity logs, millisecond epoch is primary source of truth.
    let secs = (ts_ms / 1000) as i64;
    let tm = time::OffsetDateTime::from_unix_timestamp(secs)
        .unwrap_or(time::OffsetDateTime::UNIX_EPOCH)
        .to_offset(time::UtcOffset::UTC);
    tm.format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            set_clickthrough,
            set_overlay_mode,
            get_overlay_service_ports,
            save_latency_snapshot
        ])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_always_on_top(true);
                let _ = window.set_decorations(false);
                let _ = window.set_shadow(false);
                let _ = window.set_skip_taskbar(true);
                let _ = window.set_ignore_cursor_events(true);
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri spike");
}
