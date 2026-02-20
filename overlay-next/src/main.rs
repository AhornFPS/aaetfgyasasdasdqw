mod app;
mod audio;
mod census;
mod characters;
mod config;
mod control;
mod dior_db;
mod events;
mod launcher;
mod protocol;
mod state;
mod stats;
mod workers;

use std::{
    collections::HashMap,
    fs,
    net::SocketAddr,
    path::{Path, PathBuf},
    time::Duration,
};

use anyhow::{Context, Result};
use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use crossbeam_channel::Sender;
use futures_util::StreamExt;
use protocol::{parse_incoming_message, IncomingMessage};
use serde_json::{json, Value};
use sysinfo::{ProcessesToUpdate, System};
use tokio::{net::TcpListener, time::sleep};
use tokio::{sync::mpsc, task::JoinHandle};
use tokio_tungstenite::connect_async;
use tracing::{error, info, warn};

use crate::{
    app::OverlayApp,
    census::{spawn_census_worker, CensusWorkerConfig},
    config::OverlayConfig,
    control::WorkerControlMessage,
    dior_db::CharacterDatabase,
    protocol::LegacyEnvelope,
    workers::{spawn_twitch_worker, TwitchWorkerConfig},
};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let (config, config_path) = OverlayConfig::load_or_create()?;
    let (tx, rx) = crossbeam_channel::unbounded::<IncomingMessage>();

    let (worker_control_tx, worker_control_rx) = mpsc::unbounded_channel::<WorkerControlMessage>();
    tokio::spawn(run_worker_manager(
        config.clone(),
        tx.clone(),
        worker_control_rx,
    ));

    let startup_width = config.launcher_window.width.clamp(640.0, 4096.0);
    let startup_height = config.launcher_window.height.clamp(480.0, 4096.0);
    let mut viewport = egui::ViewportBuilder::default()
        .with_transparent(true)
        .with_decorations(true)
        .with_mouse_passthrough(false)
        .with_resizable(true)
        .with_inner_size([startup_width, startup_height])
        .with_title("Better Planetside Launcher");
    if let (Some(x), Some(y)) = (config.launcher_window.pos_x, config.launcher_window.pos_y) {
        viewport = viewport.with_position(egui::pos2(x, y));
    }

    let native_options = eframe::NativeOptions {
        viewport,
        renderer: eframe::Renderer::Glow,
        ..Default::default()
    };

    eframe::run_native(
        "Better Planetside Overlay Next",
        native_options,
        Box::new(move |cc| {
            configure_egui_fonts(&cc.egui_ctx);
            crate::launcher::theme::apply_theme(&cc.egui_ctx);
            Ok(Box::new(OverlayApp::new_with_control(
                rx,
                config,
                config_path,
                Some(worker_control_tx),
            )))
        }),
    )
    .map_err(|err| anyhow::anyhow!("failed starting overlay window: {err}"))?;

    Ok(())
}

fn configure_egui_fonts(ctx: &egui::Context) {
    let mut fonts = egui::FontDefinitions::default();
    let mut loaded_any = false;

    if let Some(bytes) = load_font_file("BlackOpsOne-Regular.ttf") {
        fonts.font_data.insert(
            "black_ops_one".to_owned(),
            egui::FontData::from_owned(bytes),
        );
        fonts
            .families
            .entry(egui::FontFamily::Proportional)
            .or_default()
            .insert(0, "black_ops_one".to_owned());
        loaded_any = true;
    }

    if !loaded_any {
        return;
    }

    ctx.set_fonts(fonts);

    // Keep sizing close to the existing look while switching to the legacy typeface.
    let mut style = (*ctx.style()).clone();
    style.text_styles.insert(
        egui::TextStyle::Heading,
        egui::FontId::new(28.0, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Body,
        egui::FontId::new(18.0, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Button,
        egui::FontId::new(18.0, egui::FontFamily::Proportional),
    );
    style.text_styles.insert(
        egui::TextStyle::Small,
        egui::FontId::new(14.0, egui::FontFamily::Proportional),
    );
    ctx.set_style(style);
    info!("loaded custom UI font: BlackOpsOne-Regular.ttf");
}

fn load_font_file(filename: &str) -> Option<Vec<u8>> {
    for path in font_candidate_paths(filename) {
        if !path.is_file() {
            continue;
        }
        match fs::read(&path) {
            Ok(bytes) => return Some(bytes),
            Err(err) => warn!(?err, path = %path.display(), "failed reading font file"),
        }
    }
    None
}

fn font_candidate_paths(filename: &str) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        paths.push(cwd.join("assets").join(filename));
        paths.push(cwd.join("..").join("assets").join(filename));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            paths.push(exe_dir.join("assets").join(filename));
            paths.push(exe_dir.join("..").join("assets").join(filename));
        }
    }
    paths
}

fn env_or_dotenv(key: &str, dotenv: &HashMap<String, String>) -> Option<String> {
    std::env::var(key)
        .ok()
        .or_else(|| dotenv.get(key).cloned())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn census_character_from_db_fallback() -> Option<String> {
    let db = CharacterDatabase::open_default().ok()?;
    let entries = db.load_my_chars().ok()?;
    entries
        .into_iter()
        .map(|entry| entry.character_id.trim().to_owned())
        .find(|character_id| !character_id.is_empty())
}

fn load_dotenv_fallback() -> HashMap<String, String> {
    for path in dotenv_candidate_paths() {
        if !path.is_file() {
            continue;
        }
        match parse_dotenv_file(&path) {
            Ok(values) => {
                info!(path = %path.display(), entries = values.len(), "loaded .env fallback");
                return values;
            }
            Err(err) => {
                warn!(?err, path = %path.display(), "failed parsing .env fallback file");
            }
        }
    }
    HashMap::new()
}

fn dotenv_candidate_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        paths.push(cwd.join(".env"));
        paths.push(cwd.join("..").join(".env"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            paths.push(exe_dir.join(".env"));
            paths.push(exe_dir.join("..").join(".env"));
        }
    }
    paths
}

fn parse_dotenv_file(path: &Path) -> Result<HashMap<String, String>> {
    let mut out = HashMap::new();
    let text =
        fs::read_to_string(path).with_context(|| format!("failed reading {}", path.display()))?;
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let line = line.strip_prefix("export ").unwrap_or(line);
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if key.is_empty() {
            continue;
        }
        let value = value.trim().trim_matches('"').trim_matches('\'').to_owned();
        out.insert(key.to_owned(), value);
    }
    Ok(out)
}

#[derive(Default)]
struct WorkerHandles {
    ws_server: Option<JoinHandle<()>>,
    legacy_bridge: Option<JoinHandle<()>>,
    twitch_worker: Option<JoinHandle<()>>,
    census_worker: Option<JoinHandle<()>>,
    game_monitor: Option<JoinHandle<()>>,
}

#[derive(Debug, Clone, Default)]
struct WorkerRuntimeStatus {
    ws_server: bool,
    ws_bind: Option<String>,
    ws_error: Option<String>,
    legacy_bridge: bool,
    legacy_error: Option<String>,
    twitch_worker: bool,
    twitch_error: Option<String>,
    census_worker: bool,
    census_error: Option<String>,
    game_monitor: bool,
    game_error: Option<String>,
}

impl WorkerHandles {
    fn abort_all(&mut self) {
        abort_handle(&mut self.ws_server);
        abort_handle(&mut self.legacy_bridge);
        abort_handle(&mut self.twitch_worker);
        abort_handle(&mut self.census_worker);
        abort_handle(&mut self.game_monitor);
    }
}

async fn run_worker_manager(
    mut config: OverlayConfig,
    tx: Sender<IncomingMessage>,
    mut control_rx: mpsc::UnboundedReceiver<WorkerControlMessage>,
) {
    let mut handles = WorkerHandles::default();
    let mut dotenv = load_dotenv_fallback();
    let status = apply_worker_config(&mut handles, &config, &dotenv, &tx);
    publish_worker_status(&tx, status);
    while let Some(message) = control_rx.recv().await {
        match message {
            WorkerControlMessage::ApplyWorkers(next_config) => {
                config = next_config;
                dotenv = load_dotenv_fallback();
                let status = apply_worker_config(&mut handles, &config, &dotenv, &tx);
                publish_worker_status(&tx, status);
            }
        }
    }
    handles.abort_all();
}

fn apply_worker_config(
    handles: &mut WorkerHandles,
    config: &OverlayConfig,
    dotenv: &HashMap<String, String>,
    tx: &Sender<IncomingMessage>,
) -> WorkerRuntimeStatus {
    handles.abort_all();
    let mut status = WorkerRuntimeStatus::default();

    let ws_bind = config.ws_bind.trim();
    if ws_bind.is_empty() {
        warn!("ws_bind is empty; ws server disabled");
        status.ws_error = Some("ws_bind is empty".to_owned());
    } else if !is_valid_ws_bind(ws_bind) {
        warn!(bind = %ws_bind, "ws_bind is invalid; ws server disabled");
        status.ws_error = Some(format!("invalid ws_bind: {ws_bind}"));
    } else {
        let ws_bind = ws_bind.to_owned();
        status.ws_bind = Some(ws_bind.clone());
        let tx_server = tx.clone();
        let tx_status = tx.clone();
        handles.ws_server = Some(tokio::spawn(async move {
            if let Err(err) = run_ws_server(&ws_bind, tx_server).await {
                error!(?err, bind = %ws_bind, "ws server crashed");
                let _ = tx_status.send(IncomingMessage::Legacy(LegacyEnvelope {
                    category: "worker_status".to_owned(),
                    data: json!({
                        "ws_server": false,
                        "ws_bind": ws_bind,
                        "ws_error": err.to_string(),
                    }),
                }));
            }
        }));
        status.ws_server = true;
    }

    if let Some(legacy_url) = config
        .legacy_source_ws
        .clone()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
    {
        let tx_legacy = tx.clone();
        handles.legacy_bridge = Some(tokio::spawn(async move {
            run_legacy_bridge(legacy_url, tx_legacy).await;
        }));
        status.legacy_bridge = true;
    } else {
        info!("legacy bridge disabled (legacy_source_ws is null)");
        status.legacy_error = Some("legacy_source_ws is empty/disabled".to_owned());
    }

    if config.twitch_worker_enabled {
        if let Some(channel) = config
            .twitch_channel
            .clone()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
        {
            handles.twitch_worker = Some(spawn_twitch_worker(
                TwitchWorkerConfig {
                    channel,
                    nick: config.twitch_nick.clone(),
                    ignore_special: config.twitch_ignore_special,
                    ignore_users: config.twitch_ignore_users.clone(),
                },
                tx.clone(),
            ));
            status.twitch_worker = true;
        } else {
            warn!("twitch worker enabled but twitch_channel is empty");
            status.twitch_error = Some("twitch_channel is empty".to_owned());
        }
    } else {
        info!("twitch worker disabled (twitch_worker_enabled=false)");
        status.twitch_error = Some("twitch_worker_enabled=false".to_owned());
    }

    if config.census_worker_enabled {
        let service_id = config
            .census_service_id
            .clone()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .or_else(|| env_or_dotenv("CENSUS_SERVICE_ID", dotenv))
            .or_else(|| env_or_dotenv("PS2_CENSUS_SERVICE_ID", dotenv))
            .or_else(|| env_or_dotenv("SERVICE_ID", dotenv));
        let character_id = config
            .census_character_id
            .clone()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .or_else(|| env_or_dotenv("CENSUS_CHARACTER_ID", dotenv))
            .or_else(|| env_or_dotenv("PS2_CHARACTER_ID", dotenv))
            .or_else(|| env_or_dotenv("CHARACTER_ID", dotenv))
            .or_else(census_character_from_db_fallback);
        if let Some(service_id) = service_id {
            if let Some(character_id) = character_id {
                handles.census_worker = Some(spawn_census_worker(
                    CensusWorkerConfig {
                        service_id,
                        character_id,
                        multi_kill_window_secs: config.census_multi_kill_window_secs,
                        weapon_lookup_enabled: config.census_weapon_lookup_enabled,
                        kd_mode_revive: config.kd_mode_revive,
                    },
                    tx.clone(),
                ));
                status.census_worker = true;
            } else {
                warn!(
                    "census worker enabled but no tracked character is configured \
                    (config/.env empty and db fallback has no my_chars rows)"
                );
                status.census_error =
                    Some("missing census_character_id (config/.env/db my_chars)".to_owned());
            }
        } else {
            warn!(
                "census worker enabled but census_service_id is empty \
                (config and .env fallback not set)"
            );
            status.census_error = Some("missing census_service_id (config/.env)".to_owned());
        }
    } else {
        info!("census worker disabled (census_worker_enabled=false)");
        status.census_error = Some("census_worker_enabled=false".to_owned());
    }

    if config.game_monitor_enabled {
        let process_names = config.game_process_names.clone();
        let poll_ms = config.game_poll_ms;
        let tx_game = tx.clone();
        handles.game_monitor = Some(tokio::spawn(async move {
            run_game_monitor(process_names, poll_ms, tx_game).await;
        }));
        status.game_monitor = true;
    } else {
        info!("game monitor disabled (game_monitor_enabled=false)");
        status.game_error = Some("game_monitor_enabled=false".to_owned());
    }
    status
}

fn is_valid_ws_bind(value: &str) -> bool {
    value.parse::<SocketAddr>().is_ok()
}

fn abort_handle(handle: &mut Option<JoinHandle<()>>) {
    if let Some(task) = handle.take() {
        task.abort();
    }
}

fn publish_worker_status(tx: &Sender<IncomingMessage>, status: WorkerRuntimeStatus) {
    let payload = json!({
        "ws_server": status.ws_server,
        "ws_bind": status.ws_bind,
        "ws_error": status.ws_error,
        "legacy_bridge": status.legacy_bridge,
        "legacy_error": status.legacy_error,
        "twitch_worker": status.twitch_worker,
        "twitch_error": status.twitch_error,
        "census_worker": status.census_worker,
        "census_error": status.census_error,
        "game_monitor": status.game_monitor,
        "game_error": status.game_error,
        "at": Utc::now().to_rfc3339(),
    });
    let _ = tx.send(IncomingMessage::Legacy(LegacyEnvelope {
        category: "worker_status".to_owned(),
        data: payload,
    }));
}

#[cfg(test)]
mod tests {
    use super::{is_valid_ws_bind, parse_dotenv_file};
    use std::{fs, path::PathBuf, time::SystemTime};

    #[test]
    fn parse_dotenv_supports_comments_export_and_quotes() {
        let unique = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .expect("clock should be valid")
            .as_nanos();
        let path: PathBuf = std::env::temp_dir().join(format!("bp_overlay_env_{unique}.env"));
        let body = r#"
# comment
export CENSUS_SERVICE_ID=s:abc123
CENSUS_CHARACTER_ID="54281234567890123"
EMPTY=
"#;
        fs::write(&path, body).expect("should write temp env file");
        let parsed = parse_dotenv_file(&path).expect("should parse dotenv");
        fs::remove_file(&path).ok();

        assert_eq!(
            parsed.get("CENSUS_SERVICE_ID").map(String::as_str),
            Some("s:abc123")
        );
        assert_eq!(
            parsed.get("CENSUS_CHARACTER_ID").map(String::as_str),
            Some("54281234567890123")
        );
        assert_eq!(parsed.get("EMPTY").map(String::as_str), Some(""));
    }

    #[test]
    fn validates_ws_bind_addresses() {
        assert!(is_valid_ws_bind("127.0.0.1:38471"));
        assert!(is_valid_ws_bind("0.0.0.0:9000"));
        assert!(!is_valid_ws_bind("127.0.0.1"));
        assert!(!is_valid_ws_bind("bad:address"));
        assert!(!is_valid_ws_bind(""));
    }
}

async fn run_ws_server(bind: &str, tx: Sender<IncomingMessage>) -> Result<()> {
    let tx_events = tx.clone();
    let tx_legacy = tx.clone();
    let tx_ingest = tx.clone();
    let tx_ingest_events = tx.clone();
    let app = Router::new()
        .route(
            "/events",
            get({
                let tx = tx_events.clone();
                move |ws: WebSocketUpgrade| {
                    let tx = tx.clone();
                    async move { ws.on_upgrade(move |socket| handle_socket(socket, tx)) }
                }
            }),
        )
        .route(
            "/better_planetside",
            get(move |ws: WebSocketUpgrade| {
                let tx = tx_legacy.clone();
                async move { ws.on_upgrade(move |socket| handle_socket(socket, tx)) }
            }),
        )
        .route(
            "/ingest",
            post({
                let tx = tx_ingest.clone();
                move |payload: Json<Value>| {
                    let tx = tx.clone();
                    async move { ingest_payload(payload, tx).await }
                }
            }),
        )
        .route(
            "/ingest/events",
            post({
                let tx = tx_ingest_events.clone();
                move |payload: Json<Value>| {
                    let tx = tx.clone();
                    async move { ingest_payload(payload, tx).await }
                }
            }),
        )
        .route("/health", get(|| async { "ok" }));

    let addr: SocketAddr = bind
        .parse()
        .with_context(|| format!("invalid ws bind address: {bind}"))?;
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("failed binding ws listener on {addr}"))?;

    info!("event socket listening on ws://{addr}/events");
    info!("legacy socket listening on ws://{addr}/better_planetside");
    info!("http ingest available at http://{addr}/ingest");
    axum::serve(listener, app)
        .await
        .context("axum serve failed")?;
    Ok(())
}

async fn handle_socket(mut socket: WebSocket, tx: Sender<IncomingMessage>) {
    while let Some(message_result) = socket.recv().await {
        match message_result {
            Ok(Message::Text(text)) => match parse_incoming_message(&text) {
                Ok(message) => {
                    if tx.send(message).is_err() {
                        error!("overlay receiver dropped; closing ws socket");
                        break;
                    }
                }
                Err(err) => {
                    warn!(?err, payload = %text, "ignored unknown payload");
                }
            },
            Ok(Message::Close(_)) => break,
            Ok(_) => {}
            Err(err) => {
                error!(?err, "socket receive error");
                break;
            }
        }
    }
}

async fn run_legacy_bridge(url: String, tx: Sender<IncomingMessage>) {
    loop {
        match connect_async(&url).await {
            Ok((mut stream, _response)) => {
                info!("connected to legacy source {url}");
                while let Some(next) = stream.next().await {
                    match next {
                        Ok(tokio_tungstenite::tungstenite::Message::Text(text)) => {
                            match parse_incoming_message(&text) {
                                Ok(message) => {
                                    if tx.send(message).is_err() {
                                        error!(
                                            "overlay receiver dropped; shutting down legacy bridge"
                                        );
                                        return;
                                    }
                                }
                                Err(err) => {
                                    warn!(?err, payload = %text, "legacy bridge dropped unknown payload");
                                }
                            }
                        }
                        Ok(tokio_tungstenite::tungstenite::Message::Close(_)) => break,
                        Ok(_) => {}
                        Err(err) => {
                            warn!(?err, "legacy bridge read error");
                            break;
                        }
                    }
                }
                warn!("legacy bridge disconnected, retrying");
            }
            Err(err) => {
                warn!(?err, "failed to connect to legacy source, retrying");
            }
        }

        sleep(Duration::from_secs(2)).await;
    }
}

async fn run_game_monitor(process_names: Vec<String>, poll_ms: u64, tx: Sender<IncomingMessage>) {
    let watch_list: Vec<String> = process_names
        .into_iter()
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| !value.is_empty())
        .collect();
    if watch_list.is_empty() {
        warn!("game monitor enabled but game_process_names is empty");
        return;
    }

    let interval_ms = poll_ms.clamp(250, 10_000);
    let mut system = System::new_all();
    let mut last_running: Option<bool> = None;
    let mut last_process: Option<String> = None;
    loop {
        system.refresh_processes(ProcessesToUpdate::All, true);
        let mut matched = None;
        for process in system.processes().values() {
            let process_name = process.name().to_string_lossy().to_ascii_lowercase();
            let exe_name = process
                .exe()
                .and_then(|path| path.file_name())
                .map(|name| name.to_string_lossy().to_ascii_lowercase());
            let is_match = watch_list.iter().any(|candidate| {
                *candidate == process_name
                    || exe_name
                        .as_ref()
                        .map(|value| value == candidate)
                        .unwrap_or(false)
            });
            if is_match {
                matched = Some(process.name().to_string_lossy().to_string());
                break;
            }
        }

        let running = matched.is_some();
        let changed =
            last_running.map(|value| value != running).unwrap_or(true) || last_process != matched;
        if changed {
            let _ = tx.send(IncomingMessage::Legacy(LegacyEnvelope {
                category: "game_status".to_owned(),
                data: json!({
                    "running": running,
                    "process": matched,
                    "at": Utc::now().to_rfc3339(),
                }),
            }));
            last_running = Some(running);
            last_process = matched;
        }
        sleep(Duration::from_millis(interval_ms)).await;
    }
}

async fn ingest_payload(payload: Json<Value>, tx: Sender<IncomingMessage>) -> StatusCode {
    let text = payload.0.to_string();
    match parse_incoming_message(&text) {
        Ok(message) => {
            if tx.send(message).is_ok() {
                StatusCode::ACCEPTED
            } else {
                StatusCode::SERVICE_UNAVAILABLE
            }
        }
        Err(_) => StatusCode::BAD_REQUEST,
    }
}
