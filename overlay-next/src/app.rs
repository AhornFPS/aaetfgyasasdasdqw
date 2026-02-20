use std::{
    collections::{HashMap, VecDeque},
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
};

use chrono::{DateTime, Local, Utc};
use crossbeam_channel::Receiver;
use eframe::egui::{
    self, Align2, Color32, FontId, Margin, Pos2, Rect, RichText, Stroke, TextureHandle,
    TextureOptions, Vec2,
};
use serde_json::Value;

use crate::{
    audio::{AudioPlayer, AudioRequest},
    characters::{load_characters, save_characters, CharacterEntry, PersistedCharacters},
    config::{LegacyVisualOverride, OverlayConfig},
    control::WorkerControlMessage,
    dior_db::CharacterDatabase,
    events::{FeedItem, OverlayEvent},
    launcher::LauncherState,
    protocol::{IncomingMessage, LegacyEnvelope},
    state::{load_state, save_state, PersistedLayoutState, PersistedSessionStats, PersistedState},
    stats::{derive_session_stats, SessionRawStats},
};
use tokio::sync::mpsc::UnboundedSender;

#[derive(Debug, Clone, Default)]
struct SessionStats {
    kd: f32,
    kpm: f32,
    kph: f32,
    hsr: f32,
    dhsr: f32,
    kills: u32,
    deaths: u32,
    effective_deaths: u32,
    session_time_label: String,
    session_seconds: u64,
    last_update: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Default)]
struct CrosshairState {
    enabled: bool,
    recoil_level: f32,
    size: f32,
    pos: Option<Pos2>,
    filename: Option<String>,
    shadow: bool,
    expand_enabled: bool,
}

#[derive(Debug, Clone)]
struct FeedEntry {
    item: FeedItem,
    expires_at: Option<Instant>,
    fade_ms: u64,
}

#[derive(Debug, Clone)]
struct ChatEntry {
    author: String,
    text: String,
    color: Option<Color32>,
    at: DateTime<Utc>,
    expires_at: Option<Instant>,
}

#[derive(Debug, Clone)]
struct EventVisual {
    texture_key: Option<String>,
    label: String,
    pos: Pos2,
    size: Vec2,
    centered: bool,
    born_at: Instant,
    hide_at: Instant,
    fade_ms: u64,
    warn: bool,
    glow: Option<Color32>,
}

#[derive(Clone)]
struct QueuedLegacyEvent {
    category: String,
    data: Value,
    duration_ms: u64,
}

#[derive(Debug, Clone)]
struct OverlayFx {
    center: Pos2,
    started_at: Instant,
    duration_ms: u64,
    warn: bool,
    wave: bool,
}

#[derive(Debug, Clone, Default)]
struct PipPulse {
    active_until: Option<Instant>,
    warn_until: Option<Instant>,
}

#[derive(Debug, Clone)]
struct HudSignals {
    telemetry_left: String,
    telemetry_warn_until: Option<Instant>,
    event: PipPulse,
    hitmarker: PipPulse,
    feed: PipPulse,
    stats: PipPulse,
    streak: PipPulse,
    crosshair: PipPulse,
}

impl Default for HudSignals {
    fn default() -> Self {
        Self {
            telemetry_left: "AURAXIS LINK ONLINE".to_owned(),
            telemetry_warn_until: None,
            event: PipPulse::default(),
            hitmarker: PipPulse::default(),
            feed: PipPulse::default(),
            stats: PipPulse::default(),
            streak: PipPulse::default(),
            crosshair: PipPulse::default(),
        }
    }
}

#[derive(Debug, Clone)]
struct StreakState {
    visible: bool,
    bg_filename: Option<String>,
    bg_size: Vec2,
    pos: Pos2,
    count: u32,
    tx: f32,
    ty: f32,
    font_size: f32,
    color: Color32,
    glow_color: Option<Color32>,
    streak_glow: bool,
    bold: bool,
    knives: Vec<KnifeSprite>,
    anim_active: bool,
    anim_speed: f32,
}

#[derive(Debug, Clone)]
struct KnifeSprite {
    filename: Option<String>,
    size: f32,
    x_off: f32,
    y_off: f32,
    rotation_deg: f32,
}

impl Default for StreakState {
    fn default() -> Self {
        Self {
            visible: false,
            bg_filename: None,
            bg_size: Vec2::new(220.0, 220.0),
            pos: Pos2::new(100.0, 100.0),
            count: 0,
            tx: 0.0,
            ty: 0.0,
            font_size: 26.0,
            color: Color32::WHITE,
            glow_color: Some(Color32::from_rgb(0, 242, 255)),
            streak_glow: true,
            bold: false,
            knives: Vec::new(),
            anim_active: true,
            anim_speed: 50.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ActivePlayerPresence {
    pub last_seen_unix: f64,
    pub faction: String,
    pub world_id: String,
}

pub struct OverlayState {
    events: Receiver<IncomingMessage>,
    worker_control: Option<UnboundedSender<WorkerControlMessage>>,
    pub config: OverlayConfig,
    config_path: PathBuf,
    feed: Vec<FeedEntry>,
    chat: Vec<ChatEntry>,
    stats: SessionStats,
    pub stats_visible: bool,
    legacy_stats_line: Option<String>,
    stats_bg_filename: Option<String>,
    stats_offset: Vec2,
    stats_glow: bool,
    stats_glow_color: Option<Color32>,
    stats_padding: f32,
    streak: StreakState,
    pub overlay_visible: bool,
    pub scifi_enabled: bool,
    crosshair: CrosshairState,
    feed_origin: Pos2,
    feed_size: Vec2,
    stats_origin: Pos2,
    stats_box_size: Vec2,
    event_visuals: Vec<EventVisual>,
    legacy_event_queue: VecDeque<QueuedLegacyEvent>,
    legacy_event_busy_until: Option<Instant>,
    event_dedupe_until: HashMap<String, Instant>,
    overlay_fx: Vec<OverlayFx>,
    hud: HudSignals,
    asset_roots: Vec<PathBuf>,
    texture_cache: HashMap<String, Option<TextureHandle>>,

    pub audio: Option<AudioPlayer>,
    app_start: Instant,
    startup_quiet_until: Instant,

    worker_status_ws: bool,
    worker_status_ws_bind: Option<String>,
    worker_status_ws_error: Option<String>,
    worker_status_legacy: bool,
    worker_status_legacy_error: Option<String>,
    worker_status_twitch: bool,
    worker_status_twitch_error: Option<String>,
    worker_status_census: bool,
    worker_status_census_error: Option<String>,
    worker_status_game: bool,
    worker_status_game_error: Option<String>,
    worker_status_updated_at: Option<Instant>,
    game_running: bool,
    game_process: Option<String>,
    game_status_updated_at: Option<Instant>,
    pub worker_config_dirty: bool,

    pub character_db_path: PathBuf,
    characters_path: PathBuf,
    pub characters: Vec<CharacterEntry>,
    pub active_character_id: Option<String>,
    pub active_players: HashMap<String, ActivePlayerPresence>,
    pub name_cache: HashMap<String, String>,
    pub outfit_cache: HashMap<String, String>,
    pub db_player_count: u64,
    last_voice_trigger_at: Option<Instant>,

    state_path: PathBuf,
    state_dirty: bool,
    last_state_save: Instant,
    window_geometry_changed_at: Option<Instant>,
    pub launcher: LauncherState,
}

impl OverlayState {
    #[cfg(test)]
    pub fn new(
        events: Receiver<IncomingMessage>,
        config: OverlayConfig,
        config_path: PathBuf,
    ) -> Self {
        Self::new_with_control(events, config, config_path, None)
    }

    pub fn new_with_control(
        events: Receiver<IncomingMessage>,
        config: OverlayConfig,
        config_path: PathBuf,
        worker_control: Option<UnboundedSender<WorkerControlMessage>>,
    ) -> Self {
        let state_path = config_path.with_file_name("runtime_state.json");
        let character_db_path = config_path.with_file_name("ps2_master.db");
        let characters_path = config_path.with_file_name("characters.json");
        let stored_characters = load_characters(&characters_path).unwrap_or_default();
        let db_characters = CharacterDatabase::open(character_db_path.clone())
            .ok()
            .and_then(|db| db.load_my_chars().ok())
            .unwrap_or_default();
        let (initial_name_cache, initial_outfit_cache, initial_db_player_count) =
            CharacterDatabase::open(character_db_path.clone())
                .ok()
                .map(|db| {
                    let cache = db.load_player_cache().ok().unwrap_or_default();
                    let count = db.count_player_cache().ok().unwrap_or(0);
                    (cache.names, cache.outfits, count)
                })
                .unwrap_or_else(|| (HashMap::new(), HashMap::new(), 0));
        let initial_characters = if db_characters.is_empty() {
            stored_characters.entries.clone()
        } else {
            db_characters
        };
        let initial_active_character_id = stored_characters
            .active_character_id
            .clone()
            .filter(|id| {
                initial_characters
                    .iter()
                    .any(|entry| &entry.character_id == id)
            })
            .or_else(|| {
                config.census_character_id.clone().filter(|id| {
                    initial_characters
                        .iter()
                        .any(|entry| &entry.character_id == id)
                })
            })
            .or_else(|| {
                initial_characters
                    .first()
                    .map(|entry| entry.character_id.clone())
            });
        let audio = if config.play_event_sounds {
            Some(AudioPlayer::new())
        } else {
            None
        };
        let mut app = Self {
            events,
            worker_control,
            config,
            config_path,
            feed: Vec::new(),
            chat: Vec::new(),
            stats: SessionStats::default(),
            stats_visible: false,
            legacy_stats_line: None,
            stats_bg_filename: None,
            stats_offset: Vec2::ZERO,
            stats_glow: true,
            stats_glow_color: Some(Color32::from_rgb(0, 242, 255)),
            stats_padding: 8.0,
            streak: StreakState::default(),
            overlay_visible: true,
            scifi_enabled: true,
            crosshair: CrosshairState {
                size: 64.0,
                ..Default::default()
            },
            feed_origin: Pos2::new(40.0, 140.0),
            feed_size: Vec2::new(600.0, 550.0),
            stats_origin: Pos2::new(40.0, 60.0),
            stats_box_size: Vec2::new(450.0, 60.0),
            event_visuals: Vec::new(),
            legacy_event_queue: VecDeque::new(),
            legacy_event_busy_until: None,
            event_dedupe_until: HashMap::new(),
            overlay_fx: Vec::new(),
            hud: HudSignals::default(),
            asset_roots: detect_asset_roots(),
            texture_cache: HashMap::new(),

            audio,
            app_start: Instant::now(),
            startup_quiet_until: Instant::now() + Duration::from_millis(1300),

            worker_status_ws: false,
            worker_status_ws_bind: None,
            worker_status_ws_error: None,
            worker_status_legacy: false,
            worker_status_legacy_error: None,
            worker_status_twitch: false,
            worker_status_twitch_error: None,
            worker_status_census: false,
            worker_status_census_error: None,
            worker_status_game: false,
            worker_status_game_error: None,
            worker_status_updated_at: None,
            game_running: false,
            game_process: None,
            game_status_updated_at: None,
            worker_config_dirty: false,

            character_db_path,
            characters_path,
            characters: initial_characters,
            active_character_id: initial_active_character_id,
            active_players: HashMap::new(),
            name_cache: initial_name_cache,
            outfit_cache: initial_outfit_cache,
            db_player_count: initial_db_player_count,
            last_voice_trigger_at: None,
            state_path,
            state_dirty: false,
            last_state_save: Instant::now(),
            window_geometry_changed_at: None,
            launcher: LauncherState::default(),
        };
        app.sort_characters_for_ui();
        app.sync_census_character_from_active(false);
        app.apply_layout_from_config();
        app.launcher.voice_macros_enabled = app.config.voice_macros_active;
        app.launcher.obs.service_enabled = app.config.obs_service_enabled;
        app.launcher.obs.http_port = app.config.obs_http_port;
        app.launcher.obs.ws_port = app.config.obs_ws_port;
        app.restore_runtime_state();
        let active_world = app
            .active_character_id
            .as_ref()
            .and_then(|id| {
                app.characters
                    .iter()
                    .find(|entry| &entry.character_id == id)
            })
            .and_then(|entry| entry.world_id.clone());
        if let Some(active_world) = active_world {
            app.sync_dashboard_world_from_world_id(Some(active_world.as_str()), false);
        } else {
            let configured_world = app.config.world_id.clone();
            app.sync_dashboard_world_from_world_id(Some(configured_world.as_str()), false);
        }
        if app.config.auto_overlay_visibility {
            app.overlay_visible = false;
        }
        app
    }

    fn drain_events(&mut self) {
        while let Ok(message) = self.events.try_recv() {
            match message {
                IncomingMessage::OverlayEvent(event) => self.handle_overlay_event(event),
                IncomingMessage::Legacy(legacy) => self.handle_legacy_message(legacy),
            }
        }
    }

    fn prune_state(&mut self) {
        let now = Instant::now();
        let mut changed = false;
        let feed_before = self.feed.len();
        self.feed.retain(|entry| {
            entry
                .expires_at
                .map(|t| now < t + Duration::from_millis(entry.fade_ms.max(1)))
                .unwrap_or(true)
        });
        self.feed.truncate(self.config.max_feed_items);
        if self.feed.len() != feed_before {
            changed = true;
        }

        let chat_before = self.chat.len();
        self.chat
            .retain(|entry| entry.expires_at.map(|t| t > now).unwrap_or(true));
        self.chat.truncate(self.config.max_chat_items.max(1));
        if self.chat.len() != chat_before {
            changed = true;
        }
        self.event_visuals.retain(|visual| {
            now.duration_since(visual.hide_at).as_millis() < u128::from(visual.fade_ms)
        });
        self.event_dedupe_until.retain(|_, until| *until > now);
        self.overlay_fx.retain(|fx| {
            now.duration_since(fx.started_at).as_millis() < u128::from(fx.duration_ms)
        });
        if changed {
            self.sync_layout_into_config();
            self.mark_state_dirty();
        }
    }

    fn mark_state_dirty(&mut self) {
        self.state_dirty = true;
    }

    fn sync_launcher_window_geometry(&mut self, ctx: &egui::Context) {
        let (minimized, inner_rect, outer_rect) = ctx.input(|input| {
            let viewport = input.viewport();
            (viewport.minimized, viewport.inner_rect, viewport.outer_rect)
        });
        if minimized.unwrap_or(false) {
            return;
        }

        let mut changed = false;
        if let Some(inner) = inner_rect {
            let width = inner.width().clamp(640.0, 4096.0).round();
            let height = inner.height().clamp(480.0, 4096.0).round();
            if (self.config.launcher_window.width - width).abs() >= 1.0 {
                self.config.launcher_window.width = width;
                changed = true;
            }
            if (self.config.launcher_window.height - height).abs() >= 1.0 {
                self.config.launcher_window.height = height;
                changed = true;
            }
        }
        if let Some(outer) = outer_rect {
            let pos_x = outer.min.x.round();
            let pos_y = outer.min.y.round();
            if self
                .config
                .launcher_window
                .pos_x
                .map(|value| (value - pos_x).abs() >= 1.0)
                .unwrap_or(true)
            {
                self.config.launcher_window.pos_x = Some(pos_x);
                changed = true;
            }
            if self
                .config
                .launcher_window
                .pos_y
                .map(|value| (value - pos_y).abs() >= 1.0)
                .unwrap_or(true)
            {
                self.config.launcher_window.pos_y = Some(pos_y);
                changed = true;
            }
        }
        if changed {
            self.window_geometry_changed_at = Some(Instant::now());
        }
    }

    fn flush_window_geometry_if_due(&mut self, ctx: &egui::Context) {
        let Some(changed_at) = self.window_geometry_changed_at else {
            return;
        };
        let close_requested = ctx.input(|input| input.viewport().close_requested());
        if !close_requested && changed_at.elapsed() < Duration::from_millis(600) {
            return;
        }
        self.window_geometry_changed_at = None;
        self.request_settings_save();
    }

    pub fn persist_characters(&mut self) {
        let payload = PersistedCharacters {
            active_character_id: self.active_character_id.clone(),
            entries: self.characters.clone(),
        };
        if let Ok(db) = CharacterDatabase::open(self.character_db_path.clone()) {
            let _ = db.sync_my_chars(&payload.entries);
        }
        if save_characters(&self.characters_path, &payload).is_ok() {
            // Saved
        }
    }

    fn sort_characters_for_ui(&mut self) {
        self.characters.sort_by(|a, b| {
            a.name
                .to_ascii_lowercase()
                .cmp(&b.name.to_ascii_lowercase())
        });
    }

    fn choose_default_active_character(&self) -> Option<String> {
        self.characters
            .first()
            .map(|entry| entry.character_id.clone())
    }

    fn normalize_active_character(&mut self) {
        let active_valid = self
            .active_character_id
            .as_ref()
            .map(|id| {
                self.characters
                    .iter()
                    .any(|entry| &entry.character_id == id)
            })
            .unwrap_or(false);
        if !active_valid {
            self.active_character_id = self.choose_default_active_character();
        }
    }

    fn normalize_dashboard_world_id(world_id: &str) -> Option<String> {
        let trimmed = world_id.trim();
        if trimmed.is_empty() || trimmed == "0" {
            return None;
        }
        let normalized = match trimmed {
            "13" => "10",
            "17" => "1",
            _ => trimmed,
        };
        Some(normalized.to_owned())
    }

    fn sync_dashboard_world_from_world_id(&mut self, world_id: Option<&str>, request_save: bool) {
        let Some(normalized) = world_id.and_then(Self::normalize_dashboard_world_id) else {
            return;
        };
        let mut changed = false;
        if self.launcher.dashboard.selected_world_id != normalized {
            self.launcher.dashboard.selected_world_id = normalized.clone();
            changed = true;
        }
        if self.config.world_id != normalized {
            self.config.world_id = normalized;
            changed = true;
        }
        if changed && request_save {
            self.request_settings_save();
        }
    }

    fn sync_census_character_from_active(&mut self, request_save: bool) {
        self.normalize_active_character();
        self.config.census_character_id = self.active_character_id.clone();
        if request_save {
            self.request_settings_save();
        }
    }

    pub fn set_active_character_id(&mut self, active_character_id: Option<String>) {
        let previous = self.active_character_id.clone();
        self.active_character_id = active_character_id;
        self.sync_census_character_from_active(true);
        let active_world = self
            .active_character_id
            .as_ref()
            .and_then(|id| {
                self.characters
                    .iter()
                    .find(|entry| &entry.character_id == id)
            })
            .and_then(|entry| entry.world_id.clone());
        self.sync_dashboard_world_from_world_id(active_world.as_deref(), true);
        if previous != self.active_character_id {
            self.persist_characters();
        }
    }

    pub fn add_or_update_character(&mut self, entry: CharacterEntry) {
        if let Some(existing) = self
            .characters
            .iter_mut()
            .find(|value| value.character_id == entry.character_id)
        {
            *existing = entry.clone();
        } else {
            self.characters.push(entry.clone());
        }
        self.sort_characters_for_ui();
        self.active_character_id = Some(entry.character_id);
        self.sync_census_character_from_active(true);
        self.sync_dashboard_world_from_world_id(entry.world_id.as_deref(), true);
        self.persist_characters();
    }

    pub fn delete_active_character(&mut self) {
        let Some(active_id) = self.active_character_id.clone() else {
            return;
        };
        let removed = self
            .characters
            .iter()
            .find(|entry| entry.character_id == active_id)
            .cloned();
        self.characters
            .retain(|entry| entry.character_id != active_id);
        if let Some(removed) = removed {
            if let Ok(db) = CharacterDatabase::open(self.character_db_path.clone()) {
                let _ = db.remove_my_char(&removed.name);
            }
        }
        self.sort_characters_for_ui();
        self.active_character_id = self.choose_default_active_character();
        self.sync_census_character_from_active(true);
        let active_world = self
            .active_character_id
            .as_ref()
            .and_then(|id| {
                self.characters
                    .iter()
                    .find(|entry| &entry.character_id == id)
            })
            .and_then(|entry| entry.world_id.clone());
        self.sync_dashboard_world_from_world_id(active_world.as_deref(), true);
        self.persist_characters();
    }

    fn persist_runtime_state_if_due(&mut self) {
        if !self.state_dirty || self.last_state_save.elapsed() < Duration::from_secs(2) {
            return;
        }
        let snapshot = self.build_persisted_state();
        if save_state(&self.state_path, &snapshot).is_ok() {
            self.state_dirty = false;
            self.last_state_save = Instant::now();
        }
    }

    fn build_persisted_state(&self) -> PersistedState {
        let session = if self.stats_visible {
            Some(PersistedSessionStats {
                kd: self.stats.kd,
                kpm: self.stats.kpm,
                kph: self.stats.kph,
                hsr: self.stats.hsr,
                dhsr: self.stats.dhsr,
                kills: self.stats.kills,
                deaths: self.stats.deaths,
                effective_deaths: self.stats.effective_deaths,
                session_time_label: self.stats.session_time_label.clone(),
                session_seconds: self.stats.session_seconds,
                last_update: self.stats.last_update,
            })
        } else {
            None
        };

        PersistedState {
            session,
            feed: self
                .feed
                .iter()
                .take(32)
                .map(|entry| entry.item.label.clone())
                .collect(),
            chat: self
                .chat
                .iter()
                .take(32)
                .map(|entry| format!("{}: {}", entry.author, entry.text))
                .collect(),
            layout: Some(PersistedLayoutState {
                feed_origin: [self.feed_origin.x, self.feed_origin.y],
                feed_size: [self.feed_size.x, self.feed_size.y],
                stats_origin: [self.stats_origin.x, self.stats_origin.y],
                stats_size: [self.stats_box_size.x, self.stats_box_size.y],
                stats_offset: [self.stats_offset.x, self.stats_offset.y],
                stats_padding: self.stats_padding,
                streak_pos: [self.streak.pos.x, self.streak.pos.y],
                streak_bg_size: [self.streak.bg_size.x, self.streak.bg_size.y],
                crosshair_pos: self.crosshair.pos.map(|p| [p.x, p.y]),
                crosshair_size: self.crosshair.size,
            }),
            overlay_visible: self.overlay_visible,
            scifi_enabled: self.scifi_enabled,
        }
    }

    fn restore_runtime_state(&mut self) {
        let loaded = match load_state(&self.state_path) {
            Ok(state) => state,
            Err(_) => return,
        };

        if let Some(session) = loaded.session {
            self.stats = SessionStats {
                kd: session.kd,
                kpm: session.kpm,
                kph: session.kph,
                hsr: session.hsr,
                dhsr: session.dhsr,
                kills: session.kills,
                deaths: session.deaths,
                effective_deaths: session.effective_deaths,
                session_time_label: session.session_time_label,
                session_seconds: session.session_seconds,
                last_update: session.last_update,
            };
            self.stats_visible = true;
        }

        self.feed = loaded
            .feed
            .into_iter()
            .map(|label| FeedEntry {
                item: FeedItem {
                    label,
                    at: Utc::now(),
                },
                expires_at: None,
                fade_ms: 0,
            })
            .take(self.config.max_feed_items)
            .collect();

        self.chat = loaded
            .chat
            .into_iter()
            .map(|line| {
                let mut parts = line.splitn(2, ':');
                let author = parts.next().unwrap_or("chat").trim().to_owned();
                let text = parts.next().unwrap_or("").trim().to_owned();
                ChatEntry {
                    author,
                    text,
                    color: None,
                    at: Utc::now(),
                    expires_at: None,
                }
            })
            .take(self.config.max_chat_items.max(1))
            .collect();

        self.overlay_visible = loaded.overlay_visible;
        self.scifi_enabled = loaded.scifi_enabled;

        if let Some(layout) = loaded.layout {
            self.feed_origin = Pos2::new(layout.feed_origin[0], layout.feed_origin[1]);
            self.feed_size = Vec2::new(
                layout.feed_size[0].max(120.0),
                layout.feed_size[1].max(60.0),
            );
            self.stats_origin = Pos2::new(layout.stats_origin[0], layout.stats_origin[1]);
            self.stats_box_size = Vec2::new(
                layout.stats_size[0].max(120.0),
                layout.stats_size[1].max(30.0),
            );
            self.stats_offset = Vec2::new(layout.stats_offset[0], layout.stats_offset[1]);
            self.stats_padding = layout.stats_padding.max(0.0);
            self.streak.pos = Pos2::new(layout.streak_pos[0], layout.streak_pos[1]);
            self.streak.bg_size = Vec2::new(
                layout.streak_bg_size[0].max(24.0),
                layout.streak_bg_size[1].max(24.0),
            );
            self.crosshair.pos = layout.crosshair_pos.map(|p| Pos2::new(p[0], p[1]));
            self.crosshair.size = layout.crosshair_size.clamp(8.0, 512.0);
        }
    }

    fn apply_layout_from_config(&mut self) {
        self.feed_origin = Pos2::new(self.config.layout.feed.x, self.config.layout.feed.y);
        self.feed_size = Vec2::new(
            self.config.layout.feed.width.max(120.0),
            self.config.layout.feed.height.max(60.0),
        );
        self.stats_origin = Pos2::new(self.config.layout.stats.x, self.config.layout.stats.y);
        self.stats_box_size = Vec2::new(
            self.config.layout.stats.width.max(120.0),
            self.config.layout.stats.height.max(30.0),
        );
        self.stats_offset = Vec2::new(self.config.layout.stats.tx, self.config.layout.stats.ty);
        self.stats_padding = self.config.layout.stats.padding.max(0.0);
        self.streak.pos = Pos2::new(self.config.layout.streak.x, self.config.layout.streak.y);
        self.streak.bg_size = Vec2::new(
            self.config.layout.streak.width.max(24.0),
            self.config.layout.streak.height.max(24.0),
        );
        self.crosshair.pos = match (
            self.config.layout.crosshair.x,
            self.config.layout.crosshair.y,
        ) {
            (Some(x), Some(y)) => Some(Pos2::new(x, y)),
            _ => None,
        };
        self.crosshair.size = self.config.layout.crosshair.size.clamp(8.0, 512.0);
        self.launcher.crosshair_shadow_enabled = self.config.layout.crosshair.shadow;
        self.launcher.crosshair_expand_enabled = self.config.layout.crosshair.expand_enabled;
        self.crosshair.shadow = self.config.layout.crosshair.shadow;
        self.crosshair.expand_enabled = self.config.layout.crosshair.expand_enabled;
    }

    fn sync_layout_into_config(&mut self) {
        self.config.layout.feed.x = self.feed_origin.x;
        self.config.layout.feed.y = self.feed_origin.y;
        self.config.layout.feed.width = self.feed_size.x.max(120.0);
        self.config.layout.feed.height = self.feed_size.y.max(60.0);

        self.config.layout.stats.x = self.stats_origin.x;
        self.config.layout.stats.y = self.stats_origin.y;
        self.config.layout.stats.width = self.stats_box_size.x.max(120.0);
        self.config.layout.stats.height = self.stats_box_size.y.max(30.0);
        self.config.layout.stats.tx = self.stats_offset.x;
        self.config.layout.stats.ty = self.stats_offset.y;
        self.config.layout.stats.padding = self.stats_padding.max(0.0);

        self.config.layout.streak.x = self.streak.pos.x;
        self.config.layout.streak.y = self.streak.pos.y;
        self.config.layout.streak.width = self.streak.bg_size.x.max(24.0);
        self.config.layout.streak.height = self.streak.bg_size.y.max(24.0);

        self.config.layout.crosshair.size = self.crosshair.size.clamp(8.0, 512.0);
        self.config.layout.crosshair.x = self.crosshair.pos.map(|pos| pos.x);
        self.config.layout.crosshair.y = self.crosshair.pos.map(|pos| pos.y);
        self.config.layout.crosshair.shadow = self.launcher.crosshair_shadow_enabled;
        self.config.layout.crosshair.expand_enabled = self.launcher.crosshair_expand_enabled;
    }

    fn sync_audio_backend(&mut self) {
        if self.config.play_event_sounds {
            if self.audio.is_none() {
                self.audio = Some(AudioPlayer::new());
            }
        } else {
            self.audio = None;
        }
    }

    fn set_telemetry(&mut self, text: impl Into<String>, warn: bool) {
        if !self.scifi_enabled {
            return;
        }
        self.hud.telemetry_left = text.into();
        if warn {
            self.hud.telemetry_warn_until = Some(Instant::now() + Duration::from_millis(380));
        }
    }

    fn activate_system(&mut self, name: &str, warn: bool) {
        if !self.scifi_enabled || self.is_startup_replay() {
            return;
        }
        let pulse = match name {
            "event" => &mut self.hud.event,
            "hitmarker" => &mut self.hud.hitmarker,
            "feed" => &mut self.hud.feed,
            "stats" => &mut self.hud.stats,
            "streak" => &mut self.hud.streak,
            "crosshair" => &mut self.hud.crosshair,
            _ => return,
        };
        pulse.active_until = Some(Instant::now() + Duration::from_millis(320));
        if warn {
            pulse.warn_until = Some(Instant::now() + Duration::from_millis(320));
        }
    }

    fn is_startup_replay(&self) -> bool {
        Instant::now() < self.startup_quiet_until
    }

    fn clear_hud_pulses(&mut self) {
        self.hud.event = PipPulse::default();
        self.hud.hitmarker = PipPulse::default();
        self.hud.feed = PipPulse::default();
        self.hud.stats = PipPulse::default();
        self.hud.streak = PipPulse::default();
        self.hud.crosshair = PipPulse::default();
        self.hud.telemetry_warn_until = None;
    }

    fn push_feed(&mut self, item: FeedItem, expires_at: Option<Instant>) {
        self.feed.insert(
            0,
            FeedEntry {
                item,
                expires_at,
                fade_ms: if expires_at.is_some() { 320 } else { 0 },
            },
        );
        self.feed.truncate(self.config.max_feed_items);
        self.mark_state_dirty();
    }

    fn push_chat(
        &mut self,
        author: String,
        text: String,
        color: Option<Color32>,
        at: DateTime<Utc>,
        expires_at: Option<Instant>,
    ) {
        self.chat.insert(
            0,
            ChatEntry {
                author,
                text,
                color,
                at,
                expires_at,
            },
        );
        self.chat.truncate(self.config.max_chat_items.max(1));
        self.mark_state_dirty();
    }

    fn handle_overlay_event(&mut self, event: OverlayEvent) {
        if let OverlayEvent::SessionSnapshot {
            kd,
            kpm,
            hsr,
            kills,
            deaths,
            at,
        } = &event
        {
            self.stats = SessionStats {
                kd: *kd,
                kpm: *kpm,
                kph: *kpm * 60.0,
                hsr: *hsr,
                dhsr: self.stats.dhsr,
                kills: *kills,
                deaths: *deaths,
                effective_deaths: *deaths,
                session_time_label: self.stats.session_time_label.clone(),
                session_seconds: self.stats.session_seconds,
                last_update: Some(*at),
            };
            self.stats_visible = true;
            self.activate_system("stats", false);
            self.set_telemetry("COMBAT METRICS SYNCHRONIZED", false);
            self.mark_state_dirty();
        }

        if let OverlayEvent::SessionRaw {
            k,
            d,
            hs,
            hsrkill,
            dhs,
            dhs_eligible,
            start,
            acc_t,
            revives_received,
            kd_mode_revive,
            at,
        } = &event
        {
            let raw = SessionRawStats {
                k: *k,
                d: *d,
                hs: *hs,
                hsrkill: *hsrkill,
                dhs: *dhs,
                dhs_eligible: *dhs_eligible,
                start: *start,
                acc_t: *acc_t,
                revives_received: *revives_received,
                kd_mode_revive: *kd_mode_revive,
            };
            self.apply_session_raw(raw, at.unwrap_or_else(Utc::now));
        }

        if let OverlayEvent::TwitchMessage {
            author,
            text,
            color,
            at,
        } = &event
        {
            let hold = self.config.chat_hold_seconds;
            self.push_chat(
                author.clone(),
                text.clone(),
                color
                    .as_deref()
                    .and_then(parse_hex_color)
                    .or_else(|| Some(Color32::from_rgb(0, 242, 255))),
                *at,
                if hold <= 0.0 {
                    None
                } else {
                    Some(Instant::now() + Duration::from_secs_f32(hold.clamp(3.0, 60.0)))
                },
            );
            self.set_telemetry("TWITCH LINK ACTIVE", false);
        }

        if matches!(event, OverlayEvent::Kill { .. }) {
            self.activate_system("feed", false);
            self.set_telemetry("KILLFEED UPDATE", false);
        } else if matches!(event, OverlayEvent::Death { .. }) {
            self.activate_system("feed", true);
            self.set_telemetry("COMBAT ALERT: DEATH REGISTERED", true);
        }
        self.push_feed(FeedItem::from_event(&event), None);
    }

    fn handle_legacy_message(&mut self, legacy: LegacyEnvelope) {
        let category = legacy.category.to_ascii_lowercase();
        let data = &legacy.data;
        match category.as_str() {
            "feed" => self.handle_feed(data),
            "feed_config" => self.handle_feed(data),
            "feed_clear" => {
                self.feed.clear();
                self.mark_state_dirty();
            }
            "stats" => self.handle_stats(data),
            "stats_clear" => {
                self.legacy_stats_line = None;
                self.stats_bg_filename = None;
                self.stats_visible = false;
                self.mark_state_dirty();
            }
            "streak" => self.handle_streak(data),
            "crosshair" => self.handle_crosshair(data),
            "session_snapshot" => self.handle_legacy_session_snapshot(data),
            "session_raw" => self.handle_legacy_session_raw(data),
            "kill" => self.handle_legacy_kill(data),
            "death" => self.handle_legacy_death(data),
            "crosshair_recoil" => {
                if let Some(level) = data.get("level").and_then(value_to_f32) {
                    self.crosshair.recoil_level = level.clamp(0.0, 1.0);
                } else {
                    self.crosshair.recoil_level =
                        if data.get("active").and_then(Value::as_bool).unwrap_or(false) {
                            1.0
                        } else {
                            0.0
                        };
                }
            }
            "overlay_visibility" => {
                self.overlay_visible = data.get("visible").and_then(Value::as_bool).unwrap_or(true);
                if !self.overlay_visible {
                    self.overlay_fx.clear();
                    self.clear_hud_pulses();
                }
            }
            "scifi_mode" => {
                self.scifi_enabled = data.get("enabled").and_then(Value::as_bool).unwrap_or(true);
                if self.scifi_enabled {
                    self.set_telemetry("AURAXIS LINK ONLINE", false);
                } else {
                    self.overlay_fx.clear();
                    self.clear_hud_pulses();
                }
            }
            "worker_status" => self.handle_worker_status(data),
            "game_status" => self.handle_game_status(data),
            "twitch_message" => self.handle_twitch_message(data),
            "twitch_status" => self.handle_twitch_status(data),
            "voice_trigger" => self.handle_voice_trigger(data),
            "active_player_upsert" => self.handle_active_player_upsert(data),
            "active_player_remove" => self.handle_active_player_remove(data),
            "active_player_prune" => self.handle_active_player_prune(data),
            "player_cache_batch" => self.handle_player_cache_batch(data),
            "event" | "hitmarker" => self.push_legacy_visual(&category, data),
            "events_clear" => {
                self.event_visuals.clear();
                self.legacy_event_queue.clear();
                self.legacy_event_busy_until = None;
                self.event_dedupe_until.clear();
                self.overlay_fx.clear();
                self.hud.event = PipPulse::default();
                self.hud.hitmarker = PipPulse::default();
            }
            _ => {}
        }
    }

    fn apply_session_raw(&mut self, raw: SessionRawStats, at: DateTime<Utc>) {
        let derived = derive_session_stats(&raw, self.config.kd_mode_revive, at);
        self.stats = SessionStats {
            kd: derived.kd,
            kpm: derived.kpm,
            kph: derived.kph,
            hsr: derived.hsr,
            dhsr: derived.dhsr,
            kills: derived.kills,
            deaths: derived.deaths,
            effective_deaths: derived.effective_deaths,
            session_time_label: derived.session_time_label,
            session_seconds: derived.session_seconds,
            last_update: Some(at),
        };
        self.stats_visible = true;
        self.activate_system("stats", false);
        self.set_telemetry("COMBAT METRICS SYNCHRONIZED", false);
        self.mark_state_dirty();
    }

    fn handle_legacy_session_snapshot(&mut self, data: &Value) {
        self.stats.kd = data
            .get("kd")
            .and_then(value_to_f32)
            .unwrap_or(self.stats.kd);
        self.stats.kpm = data
            .get("kpm")
            .and_then(value_to_f32)
            .unwrap_or(self.stats.kpm);
        self.stats.kph = self.stats.kpm * 60.0;
        self.stats.hsr = data
            .get("hsr")
            .and_then(value_to_f32)
            .unwrap_or(self.stats.hsr);
        self.stats.dhsr = data
            .get("dhsr")
            .and_then(value_to_f32)
            .unwrap_or(self.stats.dhsr);
        if let Some(kills) = data.get("kills").and_then(Value::as_u64) {
            if let Ok(value) = u32::try_from(kills) {
                self.stats.kills = value;
            }
        }
        if let Some(deaths) = data.get("deaths").and_then(Value::as_u64) {
            if let Ok(value) = u32::try_from(deaths) {
                self.stats.deaths = value;
                self.stats.effective_deaths = value;
            }
        }
        self.stats.last_update = Some(
            data.get("at")
                .and_then(Value::as_str)
                .and_then(parse_utc_timestamp)
                .unwrap_or_else(Utc::now),
        );
        self.stats_visible = true;
        self.activate_system("stats", false);
        self.set_telemetry("COMBAT METRICS SYNCHRONIZED", false);
        self.mark_state_dirty();
    }

    fn handle_legacy_session_raw(&mut self, data: &Value) {
        let raw = parse_session_raw_from_value(data);
        let at = data
            .get("at")
            .and_then(Value::as_str)
            .and_then(parse_utc_timestamp)
            .unwrap_or_else(Utc::now);
        self.apply_session_raw(raw, at);
    }

    fn handle_legacy_kill(&mut self, data: &Value) {
        let victim = data
            .get("victim")
            .and_then(Value::as_str)
            .unwrap_or("target")
            .to_owned();
        let weapon = data
            .get("weapon")
            .and_then(Value::as_str)
            .map(|value| format!(" [{value}]"))
            .unwrap_or_default();
        let headshot = if data
            .get("headshot")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            " HS"
        } else {
            ""
        };
        self.push_feed(
            FeedItem {
                label: format!("KILL {victim}{weapon}{headshot}"),
                at: data
                    .get("at")
                    .and_then(Value::as_str)
                    .and_then(parse_utc_timestamp)
                    .unwrap_or_else(Utc::now),
            },
            None,
        );
        self.activate_system("feed", false);
        self.set_telemetry("KILLFEED UPDATE", false);
    }

    fn handle_legacy_death(&mut self, data: &Value) {
        let killer = data
            .get("killer")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
            .to_owned();
        self.push_feed(
            FeedItem {
                label: format!("DEATH killed by {killer}"),
                at: data
                    .get("at")
                    .and_then(Value::as_str)
                    .and_then(parse_utc_timestamp)
                    .unwrap_or_else(Utc::now),
            },
            None,
        );
        self.activate_system("feed", true);
        self.set_telemetry("COMBAT ALERT: DEATH REGISTERED", true);
    }

    fn handle_feed(&mut self, data: &Value) {
        let mut layout_changed = false;
        if let Some(x) = data.get("x").and_then(value_to_f32) {
            self.feed_origin.x = x;
            layout_changed = true;
        }
        if let Some(y) = data.get("y").and_then(value_to_f32) {
            self.feed_origin.y = y;
            layout_changed = true;
        }
        if let Some(w) = data.get("width").and_then(value_to_f32) {
            self.feed_size.x = w.max(120.0);
            layout_changed = true;
        }
        if let Some(h) = data.get("height").and_then(value_to_f32) {
            self.feed_size.y = h.max(60.0);
            layout_changed = true;
        }
        if let Some(max_items) = data.get("max_items").and_then(Value::as_u64) {
            if let Ok(max) = usize::try_from(max_items) {
                self.config.max_feed_items = max.max(1);
                layout_changed = true;
            }
        }
        if let Some(html) = data.get("html").and_then(Value::as_str) {
            let label = html_to_text(html);
            if !label.is_empty() {
                let lower = label.to_ascii_lowercase();
                let feed_type = classify_feed_text(&lower);
                let warn = feed_type == "death";
                let expires_at = if data
                    .get("auto_remove")
                    .and_then(Value::as_bool)
                    .unwrap_or(true)
                {
                    let hold_ms = data
                        .get("hold_ms")
                        .and_then(Value::as_u64)
                        .unwrap_or(10_000);
                    Some(Instant::now() + Duration::from_millis(hold_ms))
                } else {
                    None
                };
                self.push_feed(
                    FeedItem {
                        label,
                        at: Utc::now(),
                    },
                    expires_at,
                );
                self.activate_system("feed", warn);
                self.set_telemetry(
                    if warn {
                        "COMBAT ALERT: DEATH REGISTERED"
                    } else {
                        match feed_type {
                            "headshot" => "KILLFEED UPDATE: HEADSHOT",
                            "gunner" => "KILLFEED UPDATE: GUNNER",
                            "revive" => "KILLFEED UPDATE: REVIVE",
                            "kill" => "KILLFEED UPDATE: KILL",
                            _ => "KILLFEED UPDATE",
                        }
                    },
                    warn,
                );
            }
        }
        if layout_changed {
            self.sync_layout_into_config();
            self.mark_state_dirty();
        }
    }

    fn handle_stats(&mut self, data: &Value) {
        let scale = data
            .get("scale")
            .and_then(value_to_f32)
            .unwrap_or(1.0)
            .max(0.1);
        self.stats_bg_filename = data
            .get("img_filename")
            .and_then(Value::as_str)
            .or_else(|| data.get("img").and_then(Value::as_str))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned);
        if let Some(html) = data.get("html").and_then(Value::as_str) {
            let text = html_to_text(html);
            if !text.is_empty() {
                self.parse_stats_line(&text);
                self.legacy_stats_line = Some(text);
            }
        }
        if let Some(x) = data.get("x").and_then(value_to_f32) {
            self.stats_origin.x = x;
        }
        if let Some(y) = data.get("y").and_then(value_to_f32) {
            self.stats_origin.y = y;
        }
        self.stats_offset = Vec2::new(
            data.get("tx").and_then(value_to_f32).unwrap_or(0.0),
            data.get("ty").and_then(value_to_f32).unwrap_or(0.0),
        );
        self.stats_padding = data.get("padding").and_then(value_to_f32).unwrap_or(8.0) * scale;
        self.stats_visible = true;
        if let Some(w) = data.get("box_width").and_then(value_to_f32) {
            self.stats_box_size.x = (w * scale).max(120.0);
        }
        if let Some(h) = data.get("box_height").and_then(value_to_f32) {
            self.stats_box_size.y = (h * scale).max(30.0);
        }
        self.stats_glow = data.get("glow").and_then(Value::as_bool).unwrap_or(true);
        if let Some(glow) = data.get("glow_color").and_then(Value::as_str) {
            self.stats_glow_color = parse_hex_color(glow);
        }
        self.activate_system("stats", false);
        self.set_telemetry("COMBAT METRICS SYNCHRONIZED", false);
        self.sync_layout_into_config();
        self.mark_state_dirty();
    }

    fn handle_streak(&mut self, data: &Value) {
        if !data
            .get("visible")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            self.streak.visible = false;
            self.sync_layout_into_config();
            self.mark_state_dirty();
            return;
        }
        self.streak.visible = true;
        self.streak.bg_filename = data
            .get("bg_filename")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .filter(|name| !name.trim().is_empty());
        let scale = data
            .get("scale")
            .and_then(value_to_f32)
            .unwrap_or(1.0)
            .max(0.1);
        self.streak.bg_size = Vec2::new(
            data.get("bg_width")
                .and_then(value_to_f32)
                .unwrap_or(220.0)
                .max(80.0),
            data.get("bg_height")
                .and_then(value_to_f32)
                .unwrap_or(220.0)
                .max(80.0),
        ) * scale;
        self.streak.pos = Pos2::new(
            data.get("x").and_then(value_to_f32).unwrap_or(100.0),
            data.get("y").and_then(value_to_f32).unwrap_or(100.0),
        );
        self.streak.count = data
            .get("count")
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(1);
        self.streak.tx = data.get("tx").and_then(value_to_f32).unwrap_or(0.0);
        self.streak.ty = data.get("ty").and_then(value_to_f32).unwrap_or(0.0);
        self.streak.font_size = data
            .get("font_size")
            .and_then(value_to_f32)
            .unwrap_or(26.0)
            .max(10.0)
            * scale;
        self.streak.color = data
            .get("color")
            .and_then(Value::as_str)
            .and_then(parse_hex_color)
            .unwrap_or(Color32::WHITE);
        self.streak.glow_color = data
            .get("glow_color")
            .and_then(Value::as_str)
            .and_then(parse_hex_color);
        self.streak.streak_glow = data
            .get("streak_glow")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        self.streak.bold = data.get("bold").and_then(Value::as_bool).unwrap_or(false);
        self.streak.anim_active = data
            .get("anim_active")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        self.streak.anim_speed = data
            .get("anim_speed")
            .and_then(value_to_f32)
            .unwrap_or(50.0);
        self.streak.knives = data
            .get("knives")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .map(|item| KnifeSprite {
                        filename: item
                            .get("filename")
                            .and_then(Value::as_str)
                            .map(ToOwned::to_owned)
                            .filter(|v| !v.trim().is_empty()),
                        size: item
                            .get("size")
                            .and_then(value_to_f32)
                            .unwrap_or(90.0)
                            .max(8.0)
                            * scale,
                        x_off: item.get("x_off").and_then(value_to_f32).unwrap_or(0.0),
                        y_off: item.get("y_off").and_then(value_to_f32).unwrap_or(0.0),
                        rotation_deg: item.get("rotation").and_then(value_to_f32).unwrap_or(0.0),
                    })
                    .collect()
            })
            .unwrap_or_default();
        self.activate_system("streak", false);
        self.set_telemetry(format!("KILLSTREAK LOCKED: x{}", self.streak.count), false);
        self.sync_layout_into_config();
        self.mark_state_dirty();
    }

    fn handle_crosshair(&mut self, data: &Value) {
        self.crosshair.enabled = data
            .get("enabled")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let scale = data
            .get("scale")
            .and_then(value_to_f32)
            .unwrap_or(1.0)
            .max(0.1);
        if let Some(size) = data.get("size").and_then(value_to_f32) {
            self.crosshair.size = (size * scale).max(8.0);
        }
        if let Some(level) = data.get("recoil_level").and_then(value_to_f32) {
            self.crosshair.recoil_level = level.clamp(0.0, 1.0);
        } else if let Some(active) = data.get("recoil_active").and_then(Value::as_bool) {
            self.crosshair.recoil_level = if active { 1.0 } else { 0.0 };
        }
        self.crosshair.filename = data
            .get("filename")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);
        self.crosshair.shadow = data.get("shadow").and_then(Value::as_bool).unwrap_or(false);
        self.crosshair.expand_enabled = data
            .get("expand_enabled")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        let x = data.get("x").and_then(value_to_f32);
        let y = data.get("y").and_then(value_to_f32);
        self.crosshair.pos = match (x, y) {
            (Some(px), Some(py)) if px > 0.0 || py > 0.0 => Some(Pos2::new(px, py)),
            _ => None,
        };
        if self.crosshair.enabled {
            self.activate_system("crosshair", false);
        }
        self.sync_layout_into_config();
        self.mark_state_dirty();
    }

    fn handle_twitch_message(&mut self, data: &Value) {
        if let Some(max_items) = data.get("max_items").and_then(Value::as_u64) {
            if let Ok(max) = usize::try_from(max_items) {
                self.config.max_chat_items = max.max(1);
            }
        }
        let author = data
            .get("author")
            .and_then(Value::as_str)
            .unwrap_or("chat")
            .to_owned();
        let text = data
            .get("text")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .or_else(|| data.get("html").and_then(Value::as_str).map(html_to_text))
            .or_else(|| {
                data.get("message")
                    .and_then(Value::as_str)
                    .map(str::to_owned)
            })
            .unwrap_or_default()
            .trim()
            .to_owned();
        if text.is_empty() {
            return;
        }
        let color = data
            .get("color")
            .and_then(Value::as_str)
            .or_else(|| data.get("author_color").and_then(Value::as_str))
            .and_then(parse_hex_color)
            .or_else(|| Some(Color32::from_rgb(0, 242, 255)));
        let hold_raw = data
            .get("hold_seconds")
            .and_then(value_to_f32)
            .unwrap_or(self.config.chat_hold_seconds);
        let hold_secs = hold_raw.clamp(3.0, 60.0);
        let expiry = if hold_raw <= 0.0 {
            None
        } else {
            Some(Instant::now() + Duration::from_secs_f32(hold_secs))
        };
        self.push_chat(author.clone(), text.clone(), color, Utc::now(), expiry);
        self.push_feed(
            FeedItem {
                label: format!("TWITCH {}: {}", author, text),
                at: Utc::now(),
            },
            expiry,
        );
        self.set_telemetry("TWITCH LINK ACTIVE", false);
    }

    fn handle_twitch_status(&mut self, data: &Value) {
        let status = data
            .get("status")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or_default()
            .to_owned();
        if status.is_empty() {
            return;
        }
        if let Some(connected) = data.get("connected").and_then(Value::as_bool) {
            self.launcher.twitch.connected = connected;
        } else {
            let upper = status.to_ascii_uppercase();
            if upper.contains("CONNECTED") && !upper.contains("DISCONNECTED") {
                self.launcher.twitch.connected = true;
            }
            if upper.contains("DISCONNECTED")
                || upper.contains("ERROR")
                || upper.contains("RECONNECTING")
            {
                self.launcher.twitch.connected = false;
            }
        }
        self.launcher.twitch.status = Some(status);
    }

    fn handle_voice_trigger(&mut self, data: &Value) {
        let Some(trigger) = data
            .get("trigger")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        else {
            return;
        };
        self.trigger_auto_voice(trigger);
    }

    fn trigger_auto_voice(&mut self, trigger_key: &str) {
        if !self.config.voice_macros_active {
            return;
        }
        let selected = match trigger_key {
            "revived" => self.config.voice_macro_revived.trim(),
            "tk" => self.config.voice_macro_tk.trim(),
            "kill_infil" => self.config.voice_macro_kill_infil.trim(),
            "kill_max" => self.config.voice_macro_kill_max.trim(),
            "kill_high_kd" => self.config.voice_macro_kill_high_kd.trim(),
            "kill_hs" => self.config.voice_macro_kill_hs.trim(),
            _ => "OFF",
        };
        if selected.eq_ignore_ascii_case("off") {
            return;
        }
        let Some(digit) = selected
            .chars()
            .next()
            .filter(|ch| ch.is_ascii_digit())
            .map(|ch| ch.to_string())
        else {
            return;
        };

        let now = Instant::now();
        if self
            .last_voice_trigger_at
            .map(|last| now.duration_since(last) < Duration::from_millis(2500))
            .unwrap_or(false)
        {
            return;
        }
        self.last_voice_trigger_at = Some(now);
        self.launcher.voice_status =
            Some(format!("Auto voice triggered: V-{digit} ({trigger_key})"));
        dispatch_voice_hotkey(digit);
    }

    fn handle_active_player_upsert(&mut self, data: &Value) {
        let character_id = data
            .get("character_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty() && *value != "0")
            .map(ToOwned::to_owned);
        let Some(character_id) = character_id else {
            return;
        };
        let faction = data
            .get("faction")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("NSO")
            .to_owned();
        let world_id = data
            .get("world_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("0")
            .to_owned();
        let last_seen_unix = data
            .get("last_seen")
            .and_then(Value::as_f64)
            .unwrap_or_else(|| Utc::now().timestamp() as f64);
        let is_active_character = self
            .active_character_id
            .as_deref()
            .map(|value| value == character_id.as_str())
            .unwrap_or(false);
        self.active_players.insert(
            character_id.clone(),
            ActivePlayerPresence {
                last_seen_unix,
                faction,
                world_id: world_id.clone(),
            },
        );
        if is_active_character {
            self.sync_dashboard_world_from_world_id(Some(world_id.as_str()), true);
            if let Some(entry) = self
                .characters
                .iter_mut()
                .find(|entry| entry.character_id == character_id)
            {
                if entry.world_id.as_deref() != Some(world_id.as_str()) {
                    entry.world_id = Some(world_id);
                    self.persist_characters();
                }
            }
        }
    }

    fn handle_active_player_remove(&mut self, data: &Value) {
        if let Some(character_id) = data
            .get("character_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            self.active_players.remove(character_id);
        }
    }

    fn handle_active_player_prune(&mut self, data: &Value) {
        let Some(character_ids) = data.get("character_ids").and_then(Value::as_array) else {
            return;
        };
        for character_id in character_ids {
            if let Some(character_id) = character_id
                .as_str()
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                self.active_players.remove(character_id);
            }
        }
    }

    fn handle_player_cache_batch(&mut self, data: &Value) {
        if let Some(names) = data.get("names").and_then(Value::as_object) {
            for (character_id, name) in names {
                if let Some(name) = name
                    .as_str()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                {
                    self.name_cache
                        .insert(character_id.clone(), name.to_owned());
                }
            }
        }
        if let Some(outfits) = data.get("outfits").and_then(Value::as_object) {
            for (character_id, tag) in outfits {
                if let Some(tag) = tag
                    .as_str()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                {
                    self.outfit_cache
                        .insert(character_id.clone(), tag.to_owned());
                }
            }
        }
        if let Some(count) = data.get("db_player_count").and_then(Value::as_u64) {
            self.db_player_count = count;
        }
    }

    fn handle_game_status(&mut self, data: &Value) {
        if let Some(running) = data.get("running").and_then(Value::as_bool) {
            self.game_running = running;
            if self.config.auto_overlay_visibility {
                self.overlay_visible = running;
            }
        }
        self.game_process = data
            .get("process")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        self.game_status_updated_at = Some(Instant::now());
        if self.game_running {
            self.set_telemetry("PLANETSIDE 2 DETECTED", false);
        } else {
            self.set_telemetry("PLANETSIDE 2 NOT RUNNING", false);
        }
    }

    fn handle_worker_status(&mut self, data: &Value) {
        if let Some(value) = data.get("ws_server").and_then(Value::as_bool) {
            self.worker_status_ws = value;
        }
        self.worker_status_ws_bind = data
            .get("ws_bind")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        self.worker_status_ws_error = data
            .get("ws_error")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        if let Some(value) = data.get("legacy_bridge").and_then(Value::as_bool) {
            self.worker_status_legacy = value;
        }
        self.worker_status_legacy_error = data
            .get("legacy_error")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        if let Some(value) = data.get("twitch_worker").and_then(Value::as_bool) {
            self.worker_status_twitch = value;
        }
        self.worker_status_twitch_error = data
            .get("twitch_error")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        if !self.worker_status_twitch {
            self.launcher.twitch.connected = false;
            if let Some(reason) = self.worker_status_twitch_error.as_ref() {
                self.launcher.twitch.status = Some(format!("TWITCH: {reason}"));
            }
        }
        if let Some(value) = data.get("census_worker").and_then(Value::as_bool) {
            self.worker_status_census = value;
        }
        self.worker_status_census_error = data
            .get("census_error")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        if let Some(value) = data.get("game_monitor").and_then(Value::as_bool) {
            self.worker_status_game = value;
        }
        self.worker_status_game_error = data
            .get("game_error")
            .and_then(Value::as_str)
            .map(|value| value.to_owned());
        self.worker_status_updated_at = Some(Instant::now());
    }

    fn queue_legacy_event_if_needed(
        &mut self,
        category: &str,
        data: &Value,
        duration_ms: u64,
    ) -> bool {
        if !category.eq_ignore_ascii_case("event") || !self.config.event_queue_active {
            return false;
        }
        let now = Instant::now();
        if self
            .legacy_event_busy_until
            .map(|until| until > now)
            .unwrap_or(false)
        {
            self.legacy_event_queue.push_back(QueuedLegacyEvent {
                category: category.to_owned(),
                data: data.clone(),
                duration_ms,
            });
            self.trim_legacy_event_queue();
            return true;
        }
        false
    }

    fn trim_legacy_event_queue(&mut self) {
        let max_len = self.config.event_queue_max_len.clamp(10, 200);
        while self.legacy_event_queue.len() > max_len {
            self.legacy_event_queue.pop_front();
        }
        let max_backlog_ms = self.config.event_queue_max_backlog_ms.clamp(2_000, 60_000);
        let mut queued_ms: u64 = self
            .legacy_event_queue
            .iter()
            .map(|item| item.duration_ms)
            .sum();
        while self.legacy_event_queue.len() > 1 && queued_ms > max_backlog_ms {
            if let Some(oldest) = self.legacy_event_queue.pop_front() {
                queued_ms = queued_ms.saturating_sub(oldest.duration_ms);
            } else {
                break;
            }
        }
    }

    fn process_queued_legacy_events(&mut self) {
        if !self.config.event_queue_active {
            self.legacy_event_queue.clear();
            self.legacy_event_busy_until = None;
            return;
        }
        let now = Instant::now();
        if self
            .legacy_event_busy_until
            .map(|until| until > now)
            .unwrap_or(false)
        {
            return;
        }
        self.legacy_event_busy_until = None;
        if let Some(next) = self.legacy_event_queue.pop_front() {
            self.push_legacy_visual(&next.category, &next.data);
        }
    }

    fn find_visual_override(
        &self,
        override_key: &str,
        event_type: &str,
        category: &str,
    ) -> Option<LegacyVisualOverride> {
        let exact = override_key.trim().to_ascii_lowercase();
        let event = event_type.trim().to_ascii_lowercase();
        let category_key = category.trim().to_ascii_lowercase();
        let mut candidates = Vec::new();
        let mut push_unique = |value: String| {
            if !value.is_empty() && !candidates.iter().any(|existing| existing == &value) {
                candidates.push(value);
            }
        };
        push_unique(exact.clone());
        push_unique(event.clone());
        push_unique(
            exact
                .split_whitespace()
                .next()
                .unwrap_or_default()
                .trim()
                .to_owned(),
        );
        push_unique(
            event
                .split_whitespace()
                .next()
                .unwrap_or_default()
                .trim()
                .to_owned(),
        );
        push_unique(category_key);
        for key in candidates {
            if let Some(found) = self.config.legacy_visual_overrides.get(&key) {
                return Some(found.clone());
            }
        }
        None
    }

    fn push_legacy_visual(&mut self, category: &str, data: &Value) {
        let event_type = data
            .get("event_type")
            .and_then(Value::as_str)
            .unwrap_or(category)
            .to_owned();
        let override_key = data
            .get("event_name")
            .and_then(Value::as_str)
            .or_else(|| data.get("event_type").and_then(Value::as_str))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_ascii_lowercase())
            .unwrap_or_else(|| event_type.to_ascii_lowercase());
        let override_cfg = self.find_visual_override(&override_key, &event_type, category);
        let texture_key = data
            .get("filename")
            .and_then(Value::as_str)
            .or_else(|| {
                override_cfg
                    .as_ref()
                    .and_then(|cfg| cfg.filename.as_ref())
                    .map(String::as_str)
            })
            .map(ToOwned::to_owned)
            .filter(|name| !name.trim().is_empty());
        let scale = data
            .get("scale")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.scale))
            .unwrap_or(1.0)
            .max(0.1);
        let duration_ms = data
            .get("duration")
            .and_then(Value::as_u64)
            .or_else(|| data.get("duration_ms").and_then(Value::as_u64))
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.duration_ms))
            .unwrap_or(180)
            .max(60);
        let now = Instant::now();
        let play_duplicate = data
            .get("play_duplicate")
            .and_then(Value::as_bool)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.play_duplicate))
            .unwrap_or(true);
        if !play_duplicate {
            let dedupe_key = data
                .get("event_name")
                .and_then(Value::as_str)
                .or_else(|| data.get("event_type").and_then(Value::as_str))
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(|value| value.to_ascii_lowercase())
                .or_else(|| Some(format!("{category}:{}", event_type.to_ascii_lowercase())));
            if let Some(key) = dedupe_key {
                if self
                    .event_dedupe_until
                    .get(&key)
                    .map(|until| *until > now)
                    .unwrap_or(false)
                {
                    return;
                }
                self.event_dedupe_until.insert(
                    key,
                    now + Duration::from_millis(duration_ms.saturating_add(120)),
                );
            }
        }
        if self.queue_legacy_event_if_needed(category, data, duration_ms) {
            return;
        }

        self.play_legacy_event_sound(
            category,
            &event_type,
            duration_ms,
            data,
            override_cfg.as_ref(),
            play_duplicate,
        );
        let warn = event_type.eq_ignore_ascii_case("death");
        let glow_enabled = data
            .get("glow")
            .and_then(Value::as_bool)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.glow))
            .unwrap_or(true);
        let glow = if glow_enabled {
            data.get("glow_color")
                .and_then(Value::as_str)
                .or_else(|| {
                    override_cfg
                        .as_ref()
                        .and_then(|cfg| cfg.glow_color.as_ref())
                        .map(String::as_str)
                })
                .and_then(parse_hex_color)
                .or_else(|| Some(Color32::from_rgb(0, 242, 255)))
        } else {
            None
        };
        let (offset_x, offset_y) = if category.eq_ignore_ascii_case("hitmarker") {
            (
                self.config.hitmarker_offset_x,
                self.config.hitmarker_offset_y,
            )
        } else {
            (self.config.event_offset_x, self.config.event_offset_y)
        };
        let base_x = data
            .get("x")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.x))
            .unwrap_or(220.0);
        let base_y = data
            .get("y")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.y))
            .unwrap_or(220.0);
        let width = data
            .get("width")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.width))
            .unwrap_or(220.0)
            .max(32.0);
        let height = data
            .get("height")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.height))
            .unwrap_or(220.0)
            .max(32.0);
        let centered = data
            .get("centered")
            .and_then(Value::as_bool)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.centered))
            .unwrap_or(false);
        let visual_pos = Pos2::new(base_x + offset_x, base_y + offset_y);
        let visual_size = Vec2::new(width, height) * scale;
        let fade_ms = data
            .get("fade_ms")
            .and_then(Value::as_u64)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.fade_ms))
            .unwrap_or(320)
            .max(30);

        self.event_visuals.insert(
            0,
            EventVisual {
                texture_key,
                label: format!("{} {}", category.to_uppercase(), event_type),
                pos: visual_pos,
                size: visual_size,
                centered,
                born_at: now,
                hide_at: now + Duration::from_millis(duration_ms),
                fade_ms,
                warn,
                glow,
            },
        );
        if category.eq_ignore_ascii_case("event") && self.config.event_queue_active {
            self.legacy_event_busy_until = Some(now + Duration::from_millis(duration_ms));
        }

        let center = if centered {
            visual_pos
        } else {
            Pos2::new(
                visual_pos.x + visual_size.x * 0.5,
                visual_pos.y + visual_size.y * 0.5,
            )
        };
        let impact = data
            .get("impact")
            .and_then(Value::as_bool)
            .or_else(|| override_cfg.as_ref().and_then(|cfg| cfg.impact))
            .unwrap_or_else(|| {
                matches!(
                    event_type.to_ascii_lowercase().as_str(),
                    "headshot" | "death"
                )
            });
        if !self.is_startup_replay() {
            self.overlay_fx.push(OverlayFx {
                center,
                started_at: now,
                duration_ms: if impact { 420 } else { 260 },
                warn,
                wave: impact,
            });
        }
        let pip_name = if category.eq_ignore_ascii_case("hitmarker") {
            "hitmarker"
        } else {
            "event"
        };
        self.activate_system(pip_name, warn);
        self.set_telemetry(format!("EVENT: {}", event_type.to_ascii_uppercase()), warn);
    }

    fn play_legacy_event_sound(
        &self,
        category: &str,
        event_type: &str,
        duration_ms: u64,
        data: &Value,
        override_cfg: Option<&LegacyVisualOverride>,
        play_duplicate: bool,
    ) {
        let Some(audio) = self.audio.as_ref() else {
            return;
        };
        let filename = data
            .get("sound_filename")
            .and_then(Value::as_str)
            .or_else(|| {
                override_cfg
                    .and_then(|cfg| cfg.sound_filename.as_ref())
                    .map(String::as_str)
            })
            .map(str::trim)
            .unwrap_or("");
        if filename.is_empty() {
            return;
        }
        let Some(path) = resolve_asset_path(filename, &self.asset_roots) else {
            return;
        };

        let source_volume = data
            .get("sound_volume")
            .and_then(value_to_f32)
            .or_else(|| override_cfg.and_then(|cfg| cfg.sound_volume))
            .unwrap_or(1.0);
        let volume = (source_volume * self.config.sound_master_volume).clamp(0.0, 2.0);
        if volume <= 0.0 {
            return;
        }
        let dedupe_key = data
            .get("event_name")
            .and_then(Value::as_str)
            .or_else(|| data.get("event_type").and_then(Value::as_str))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_ascii_lowercase())
            .or_else(|| Some(format!("{category}:{}", event_type.to_ascii_lowercase())));

        audio.play(AudioRequest {
            path,
            volume,
            dedupe_key,
            play_duplicate,
            dedupe_window_ms: duration_ms.saturating_add(120),
        });
    }

    fn parse_stats_line(&mut self, text: &str) {
        if let Some(v) = parse_number_after(text, "KD") {
            self.stats.kd = v;
        }
        if let Some(v) = parse_number_after(text, "KPM") {
            self.stats.kpm = v;
            self.stats.kph = v * 60.0;
        }
        if let Some(v) = parse_number_after(text, "HSR") {
            self.stats.hsr = v;
        }
        if let Some(v) = parse_number_after(text, "DHSR") {
            self.stats.dhsr = v;
        }
        if let Some(v) = parse_number_after(text, "K") {
            self.stats.kills = v.max(0.0) as u32;
        }
        if let Some(v) = parse_number_after(text, "D") {
            self.stats.deaths = v.max(0.0) as u32;
            self.stats.effective_deaths = self.stats.deaths;
        }
        if let Some(time_label) = parse_time_label(text) {
            self.stats.session_time_label = time_label;
        }
        self.stats.last_update = Some(Utc::now());
    }

    fn draw_streak(&mut self, ctx: &egui::Context) {
        let streak = self.streak.clone();
        if !streak.visible {
            return;
        }
        let painter = ctx.layer_painter(egui::LayerId::new(
            egui::Order::Foreground,
            egui::Id::new("streak_layer"),
        ));
        let pulse_scale = if streak.anim_active {
            let t = self.app_start.elapsed().as_secs_f32();
            let hz = (streak.anim_speed / 120.0).clamp(0.15, 2.0);
            1.0 + (t * hz * std::f32::consts::TAU).sin() * 0.035
        } else {
            1.0
        };
        let bg_size = streak.bg_size * pulse_scale;
        let rect = Rect::from_min_size(streak.pos, bg_size);
        if let Some(bg) = &streak.bg_filename {
            if let Some(texture) = self.load_texture(ctx, bg) {
                painter.image(
                    texture.id(),
                    rect,
                    Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1.0, 1.0)),
                    Color32::WHITE,
                );
            }
        }

        let center = rect.center();
        for knife in &streak.knives {
            if let Some(filename) = &knife.filename {
                if let Some(texture) = self.load_texture(ctx, filename) {
                    let size = Vec2::splat(knife.size * pulse_scale);
                    let knife_center = Pos2::new(center.x + knife.x_off, center.y + knife.y_off);
                    draw_rotated_image(
                        &painter,
                        texture.id(),
                        knife_center,
                        size,
                        knife.rotation_deg,
                        Color32::WHITE,
                    );
                }
            }
        }

        let text = format!("{}", streak.count);
        let text_pos = Pos2::new(center.x + streak.tx, center.y + streak.ty);
        if streak.streak_glow {
            if let Some(glow) = streak.glow_color {
                for (dx, dy) in [(-1.0_f32, 0.0_f32), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)] {
                    painter.text(
                        Pos2::new(text_pos.x + dx, text_pos.y + dy),
                        Align2::CENTER_CENTER,
                        &text,
                        FontId::proportional(streak.font_size),
                        with_alpha(glow, 0.7),
                    );
                }
            }
        }
        if streak.bold {
            for (dx, dy) in [(-1.0_f32, 0.0_f32), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)] {
                painter.text(
                    Pos2::new(text_pos.x + dx, text_pos.y + dy),
                    Align2::CENTER_CENTER,
                    &text,
                    FontId::proportional(streak.font_size),
                    with_alpha(streak.color, 0.65),
                );
            }
        }
        painter.text(
            text_pos,
            Align2::CENTER_CENTER,
            text,
            FontId::proportional(streak.font_size),
            streak.color,
        );
    }

    fn draw_crosshair(&mut self, ctx: &egui::Context) {
        let crosshair = self.crosshair.clone();
        if !crosshair.enabled {
            return;
        }
        let center = crosshair.pos.unwrap_or_else(|| ctx.screen_rect().center());
        let color = if self.scifi_enabled {
            Color32::from_rgb(0, 242, 255)
        } else {
            Color32::WHITE
        };
        let painter = ctx.layer_painter(egui::LayerId::new(
            egui::Order::Foreground,
            egui::Id::new("crosshair_layer"),
        ));
        let mut drew_image = false;
        if let Some(filename) = &crosshair.filename {
            if let Some(texture) = self.load_texture(ctx, filename) {
                let size = Vec2::new(crosshair.size, crosshair.size);
                let rect = Rect::from_center_size(center, size);
                if crosshair.shadow {
                    let shadow_rect =
                        Rect::from_center_size(Pos2::new(center.x + 1.0, center.y + 1.0), size);
                    painter.image(
                        texture.id(),
                        shadow_rect,
                        Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1.0, 1.0)),
                        Color32::from_rgba_premultiplied(0, 0, 0, 160),
                    );
                }
                painter.image(
                    texture.id(),
                    rect,
                    Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1.0, 1.0)),
                    Color32::WHITE,
                );
                drew_image = true;
            }
        }
        if crosshair.expand_enabled {
            let recoil = crosshair.recoil_level.clamp(0.0, 1.0);
            let half_size = (crosshair.size * 0.5).clamp(8.0, 72.0);
            let gap = 4.0 + recoil * 14.0;
            let stroke = Stroke::new(2.0, color);
            painter.line_segment(
                [
                    Pos2::new(center.x - half_size, center.y),
                    Pos2::new(center.x - gap, center.y),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    Pos2::new(center.x + gap, center.y),
                    Pos2::new(center.x + half_size, center.y),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    Pos2::new(center.x, center.y - half_size),
                    Pos2::new(center.x, center.y - gap),
                ],
                stroke,
            );
            painter.line_segment(
                [
                    Pos2::new(center.x, center.y + gap),
                    Pos2::new(center.x, center.y + half_size),
                ],
                stroke,
            );
        } else if !drew_image {
            painter.circle_filled(center, 1.5, color);
        }
    }

    fn draw_event_visuals(&mut self, ctx: &egui::Context) {
        let now = Instant::now();
        let painter = ctx.layer_painter(egui::LayerId::new(
            egui::Order::Foreground,
            egui::Id::new("event_visuals"),
        ));
        for index in (0..self.event_visuals.len()).rev() {
            let visual = self.event_visuals[index].clone();
            let elapsed_fade_ms = now
                .checked_duration_since(visual.hide_at)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let alpha_mul = if now <= visual.hide_at {
                1.0
            } else {
                let remaining = visual.fade_ms.saturating_sub(elapsed_fade_ms);
                (remaining as f32 / visual.fade_ms as f32).clamp(0.0, 1.0)
            };
            if alpha_mul <= 0.0 {
                continue;
            }
            let rect = if visual.centered {
                Rect::from_center_size(visual.pos, visual.size)
            } else {
                Rect::from_min_size(visual.pos, visual.size)
            };
            let mut drew_texture = false;
            if let Some(key) = &visual.texture_key {
                if let Some(texture) = self.load_texture(ctx, key) {
                    painter.image(
                        texture.id(),
                        rect,
                        Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1.0, 1.0)),
                        with_alpha(Color32::WHITE, alpha_mul),
                    );
                    drew_texture = true;
                }
            }
            if !drew_texture {
                let fill = if visual.warn {
                    with_alpha(Color32::from_rgb(80, 16, 16), alpha_mul)
                } else {
                    with_alpha(Color32::from_rgb(24, 28, 34), alpha_mul)
                };
                painter.rect_filled(rect, 6.0, fill);
                painter.text(
                    rect.center(),
                    Align2::CENTER_CENTER,
                    &visual.label,
                    FontId::proportional(16.0),
                    with_alpha(Color32::WHITE, alpha_mul),
                );
            }
            if let Some(glow) = visual.glow {
                painter.rect_stroke(
                    rect.expand(1.0),
                    6.0,
                    Stroke::new(2.0, with_alpha(glow, alpha_mul)),
                );
            }
            if now.duration_since(visual.born_at).as_millis() < 120 {
                painter.rect_stroke(
                    rect.expand(5.0),
                    6.0,
                    Stroke::new(1.0, with_alpha(Color32::from_rgb(120, 220, 255), alpha_mul)),
                );
            }
        }
    }

    fn draw_overlay_fx(&self, ctx: &egui::Context) {
        if self.overlay_fx.is_empty() {
            return;
        }
        let now = Instant::now();
        let painter = ctx.layer_painter(egui::LayerId::new(
            egui::Order::Foreground,
            egui::Id::new("overlay_fx"),
        ));
        for fx in &self.overlay_fx {
            let elapsed = now.duration_since(fx.started_at).as_millis() as f32;
            let dur = fx.duration_ms as f32;
            if dur <= 0.0 {
                continue;
            }
            let t = (elapsed / dur).clamp(0.0, 1.0);
            let fade = (1.0 - t).powf(1.5);
            let base = if fx.warn {
                Color32::from_rgb(245, 86, 86)
            } else {
                Color32::from_rgb(0, 242, 255)
            };

            if fx.wave {
                let radius = 20.0 + 300.0 * t;
                painter.circle_stroke(fx.center, radius, Stroke::new(2.5, with_alpha(base, fade)));
                painter.circle_stroke(
                    fx.center,
                    radius * 0.6,
                    Stroke::new(1.5, with_alpha(base, (fade * 0.7).clamp(0.0, 1.0))),
                );
                if fx.warn {
                    let screen = ctx.screen_rect();
                    painter.rect_filled(
                        screen,
                        0.0,
                        with_alpha(
                            Color32::from_rgb(140, 20, 20),
                            (fade * 0.22).clamp(0.0, 0.25),
                        ),
                    );
                }
            } else {
                let len = 8.0 + 26.0 * t;
                let stroke = Stroke::new(2.0, with_alpha(base, fade));
                painter.line_segment(
                    [
                        Pos2::new(fx.center.x - len, fx.center.y),
                        Pos2::new(fx.center.x + len, fx.center.y),
                    ],
                    stroke,
                );
                painter.line_segment(
                    [
                        Pos2::new(fx.center.x, fx.center.y - len),
                        Pos2::new(fx.center.x, fx.center.y + len),
                    ],
                    stroke,
                );
            }
        }
    }

    fn draw_hud_signals(&self, ctx: &egui::Context, alpha: u8) {
        let now = Instant::now();
        let warn_active = self
            .hud
            .telemetry_warn_until
            .map(|t| t > now)
            .unwrap_or(false);
        let strip_fill = if warn_active {
            Color32::from_rgba_premultiplied(60, 18, 18, (alpha / 2).max(40))
        } else {
            Color32::from_rgba_premultiplied(10, 18, 26, (alpha / 2).max(34))
        };

        egui::Area::new(egui::Id::new("telemetry_strip"))
            .order(egui::Order::Foreground)
            .anchor(Align2::CENTER_TOP, [0.0, 8.0])
            .show(ctx, |ui| {
                egui::Frame::none()
                    .fill(strip_fill)
                    .inner_margin(Margin::symmetric(10.0, 6.0))
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.label(RichText::new(&self.hud.telemetry_left).small().color(
                                if warn_active {
                                    Color32::from_rgb(255, 164, 164)
                                } else {
                                    Color32::from_rgb(140, 220, 255)
                                },
                            ));
                            ui.add_space(18.0);
                            ui.label(
                                RichText::new(Local::now().format("%H:%M:%S").to_string())
                                    .small()
                                    .color(Color32::GRAY),
                            );
                        });
                    });
            });

        egui::Area::new(egui::Id::new("system_pips"))
            .order(egui::Order::Foreground)
            .anchor(Align2::CENTER_TOP, [0.0, 42.0])
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    self.draw_pip(ui, "EVT", &self.hud.event, now);
                    self.draw_pip(ui, "HIT", &self.hud.hitmarker, now);
                    self.draw_pip(ui, "KFD", &self.hud.feed, now);
                    self.draw_pip(ui, "STS", &self.hud.stats, now);
                    self.draw_pip(ui, "STR", &self.hud.streak, now);
                    self.draw_pip(ui, "CRS", &self.hud.crosshair, now);
                });
            });
    }

    fn draw_pip(&self, ui: &mut egui::Ui, label: &str, pulse: &PipPulse, now: Instant) {
        let active = pulse.active_until.map(|t| t > now).unwrap_or(false);
        let warn = pulse.warn_until.map(|t| t > now).unwrap_or(false);
        let fill = if warn {
            Color32::from_rgba_premultiplied(130, 35, 35, 220)
        } else if active {
            Color32::from_rgba_premultiplied(26, 90, 112, 220)
        } else {
            Color32::from_rgba_premultiplied(14, 18, 22, 140)
        };
        let txt = if warn {
            Color32::from_rgb(255, 188, 188)
        } else if active {
            Color32::from_rgb(190, 242, 255)
        } else {
            Color32::GRAY
        };

        egui::Frame::none()
            .fill(fill)
            .inner_margin(Margin::symmetric(6.0, 2.0))
            .show(ui, |ui| {
                ui.label(RichText::new(label).small().color(txt));
            });
    }

    fn load_texture(&mut self, ctx: &egui::Context, key: &str) -> Option<TextureHandle> {
        if let Some(existing) = self.texture_cache.get(key) {
            return existing.clone();
        }
        let texture = resolve_asset_path(key, &self.asset_roots)
            .as_deref()
            .and_then(load_color_image)
            .map(|image| ctx.load_texture(format!("asset://{key}"), image, TextureOptions::LINEAR));
        self.texture_cache.insert(key.to_owned(), texture.clone());
        texture
    }
}

pub struct OverlayApp {
    state: std::rc::Rc<std::cell::RefCell<OverlayState>>,
}

impl OverlayApp {
    pub fn new_with_control(
        events: Receiver<IncomingMessage>,
        config: OverlayConfig,
        config_path: PathBuf,
        worker_control: Option<UnboundedSender<WorkerControlMessage>>,
    ) -> Self {
        let state = OverlayState::new_with_control(events, config, config_path, worker_control);
        Self {
            state: std::rc::Rc::new(std::cell::RefCell::new(state)),
        }
    }
}

impl eframe::App for OverlayApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let mut state = self.state.borrow_mut();

        // 1. Common State Update (Events, Logic)
        state.update_state(ctx);

        // 2. Draw Launcher (Always active window)
        crate::launcher::ui::draw_launcher(&mut *state, ctx);

        // 3. Draw Overlay (If active)
        if state.overlay_visible {
            drop(state); // Drop borrow to allow viewport closure to borrow again

            let state_rc = self.state.clone();
            // Overlay must be click-through except while explicit move mode is active in main UI.
            let mouse_passthrough = {
                let borrowed = state_rc.borrow();
                if borrowed.launcher.overlay_move_mode {
                    false
                } else {
                    true
                }
            };
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("overlay_viewport"),
                egui::ViewportBuilder::default()
                    .with_title("Overlay")
                    .with_transparent(true)
                    .with_decorations(false)
                    .with_maximized(true)
                    .with_always_on_top()
                    .with_mouse_passthrough(mouse_passthrough)
                    .with_taskbar(false),
                move |ctx, _class| {
                    let mut state = state_rc.borrow_mut();
                    state.draw_overlay(ctx);
                },
            );
        }
    }
}

impl OverlayState {
    pub fn set_overlay_move_mode(&mut self, enabled: bool) {
        self.launcher.overlay_move_mode = enabled;
    }

    pub fn toggle_overlay_move_mode(&mut self) {
        self.launcher.overlay_move_mode = !self.launcher.overlay_move_mode;
    }

    pub fn request_settings_save(&mut self) {
        self.worker_config_dirty = true;
        self.mark_state_dirty();
    }

    pub fn save_settings_now(&mut self) -> Result<(), String> {
        self.sync_layout_into_config();
        self.config
            .save(&self.config_path)
            .map_err(|e| format!("save failed: {e}"))?;
        if let Some(tx) = &self.worker_control {
            tx.send(WorkerControlMessage::ApplyWorkers(self.config.clone()))
                .map_err(|e| format!("worker apply failed: {e}"))?;
        }
        self.worker_config_dirty = false;
        Ok(())
    }

    pub fn export_event_slot_to_disk(
        &self,
        slot_name: &str,
        overrides: &HashMap<String, LegacyVisualOverride>,
    ) -> Result<PathBuf, String> {
        let dir = self.config_path.with_file_name("event_slots");
        fs::create_dir_all(&dir).map_err(|e| format!("failed creating slot dir: {e}"))?;
        let safe = slot_name
            .chars()
            .map(|ch| {
                if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                    ch
                } else {
                    '_'
                }
            })
            .collect::<String>();
        let filename = if safe.is_empty() {
            "slot_default.json".to_owned()
        } else {
            format!("slot_{safe}.json")
        };
        let path = dir.join(filename);
        let payload = serde_json::to_string_pretty(overrides)
            .map_err(|e| format!("failed serializing slot: {e}"))?;
        fs::write(&path, payload).map_err(|e| format!("failed writing slot file: {e}"))?;
        Ok(path)
    }

    pub fn import_event_slot_from_disk(
        &self,
        slot_name: &str,
    ) -> Result<HashMap<String, LegacyVisualOverride>, String> {
        let dir = self.config_path.with_file_name("event_slots");
        let safe = slot_name
            .chars()
            .map(|ch| {
                if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                    ch
                } else {
                    '_'
                }
            })
            .collect::<String>();
        let filename = if safe.is_empty() {
            "slot_default.json".to_owned()
        } else {
            format!("slot_{safe}.json")
        };
        let path = dir.join(filename);
        let text =
            fs::read_to_string(&path).map_err(|e| format!("failed reading slot file: {e}"))?;
        serde_json::from_str::<HashMap<String, LegacyVisualOverride>>(&text)
            .map_err(|e| format!("failed parsing slot file: {e}"))
    }

    pub fn asset_exists(&self, filename: &str) -> bool {
        resolve_asset_path(filename, &self.asset_roots).is_some()
    }

    pub fn initialize_ps2_user_options(&mut self, high_settings: bool) -> Result<PathBuf, String> {
        let ps2_dir = self
            .config
            .ps2_path
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| "ps2_path is not set (Settings > BROWSE FOLDER)".to_owned())?;
        let source_rel = if high_settings {
            "Planetside 2 ini/UserOptions_high.ini"
        } else {
            "Planetside 2 ini/UserOptions_low.ini"
        };
        let source = resolve_asset_path(source_rel, &self.asset_roots)
            .ok_or_else(|| format!("missing asset profile: {source_rel}"))?;
        let target = PathBuf::from(ps2_dir).join("UserOptions.ini");
        fs::copy(&source, &target).map_err(|e| {
            format!(
                "failed copying {} -> {}: {e}",
                source.display(),
                target.display()
            )
        })?;
        Ok(target)
    }

    pub fn trigger_event_preview(&mut self, selected_event: Option<&str>) {
        let name = selected_event.unwrap_or("Kill");
        let key = name.to_ascii_lowercase();
        let cfg = self
            .config
            .legacy_visual_overrides
            .get(&key)
            .cloned()
            .unwrap_or_default();
        let category = if key.contains("hitmarker") {
            "hitmarker"
        } else {
            "event"
        };
        let data = serde_json::json!({
            "event_name": name,
            "event_type": key,
            "x": cfg.x.unwrap_or(640.0),
            "y": cfg.y.unwrap_or(300.0),
            "width": cfg.width.unwrap_or(220.0),
            "height": cfg.height.unwrap_or(110.0),
            "scale": cfg.scale.unwrap_or(1.0),
            "duration": cfg.duration_ms.unwrap_or(1500),
            "duration_ms": cfg.duration_ms.unwrap_or(1500),
            "fade_ms": cfg.fade_ms.unwrap_or(220),
            "img_filename": cfg.filename.unwrap_or_else(|| "Headshot.png".to_owned()),
            "glow": cfg.glow.unwrap_or(false),
            "glow_color": cfg.glow_color.unwrap_or_else(|| "#00f2ff".to_owned()),
            "play_duplicate": cfg.play_duplicate.unwrap_or(true),
            "impact": cfg.impact.unwrap_or(false),
            "centered": cfg.centered.unwrap_or(true),
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: category.to_owned(),
            data,
        });
    }

    pub fn trigger_stats_test_ui(&mut self) {
        let stats = &self.config.layout.stats;
        let data = serde_json::json!({
            "html": "KD: 2.35  KPM: 1.42  HSR: 28.4  DHSR: 17.1  K: 47  D: 20  Time: 00:33:10",
            "x": stats.x,
            "y": stats.y,
            "tx": stats.tx,
            "ty": stats.ty,
            "padding": stats.padding,
            "box_width": stats.width,
            "box_height": stats.height,
            "img_filename": stats.bg_filename.clone().unwrap_or_default(),
            "glow": stats.glow,
            "glow_color": stats.glow_color.clone().unwrap_or_else(|| "#00f2ff".to_owned()),
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: "stats".to_owned(),
            data,
        });
    }

    pub fn trigger_killfeed_test_ui(&mut self) {
        let data = serde_json::json!({
            "html": "KILL EnemyHeavy [Orion] HS",
            "x": self.config.layout.feed.x,
            "y": self.config.layout.feed.y,
            "width": self.config.layout.feed.width,
            "height": self.config.layout.feed.height,
            "max_items": self.config.max_feed_items,
            "auto_remove": self.config.feed_auto_remove,
            "hold_ms": self.config.feed_hold_seconds * 1000
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: "feed".to_owned(),
            data,
        });
    }

    pub fn trigger_crosshair_test_ui(&mut self) {
        let c = &self.config.layout.crosshair;
        let data = serde_json::json!({
            "enabled": true,
            "filename": c.filename.clone().unwrap_or_else(|| "crosshair.png".to_owned()),
            "size": c.size,
            "x": c.x.unwrap_or(0.0),
            "y": c.y.unwrap_or(0.0),
            "shadow": c.shadow,
            "expand_enabled": c.expand_enabled,
            "recoil_active": c.recoil
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: "crosshair".to_owned(),
            data,
        });
    }

    pub fn trigger_streak_test_ui(&mut self) {
        let s = &self.config.layout.streak;
        let data = serde_json::json!({
            "visible": s.active,
            "bg_filename": s.filename.clone().unwrap_or_else(|| "Skull small.png".to_owned()),
            "bg_width": s.width,
            "bg_height": s.height,
            "x": s.x,
            "y": s.y,
            "count": 5,
            "tx": 0.0,
            "ty": 0.0,
            "font_size": s.font_size,
            "color": s.color.clone(),
            "glow_color": s.glow_color.clone().unwrap_or_else(|| "#00f2ff".to_owned()),
            "streak_glow": s.streak_glow,
            "bold": s.bold,
            "anim_active": s.anim_active,
            "anim_speed": s.anim_speed,
            "scale": s.scale,
            "knives": []
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: "streak".to_owned(),
            data,
        });
    }

    pub fn trigger_twitch_test_msg(&mut self) {
        let data = serde_json::json!({
            "author": "TestUser",
            "text": "This is a Twitch test message.",
            "author_color": "#a970ff",
            "hold_seconds": self.config.chat_hold_seconds
        });
        self.handle_legacy_message(LegacyEnvelope {
            category: "twitch_message".to_owned(),
            data,
        });
    }

    pub fn start_twitch_connection(&mut self) {
        let channel = self
            .config
            .twitch_channel
            .as_deref()
            .map(str::trim)
            .unwrap_or_default();
        if channel.is_empty() {
            self.launcher.twitch.connected = false;
            self.launcher.twitch.status = Some("TWITCH: No channel specified.".to_owned());
            return;
        }
        if !self.config.twitch_worker_enabled {
            self.config.twitch_worker_enabled = true;
        }
        self.launcher.twitch.connected = false;
        self.launcher.twitch.status = Some(format!("TWITCH: Connecting to #{channel}..."));
        match self.save_settings_now() {
            Ok(()) => {}
            Err(err) => {
                self.launcher.twitch.status = Some(format!("TWITCH: connect apply failed: {err}"));
            }
        }
    }

    pub fn launch_crosshair_editor(&mut self) -> Result<(), String> {
        if let Some(path) = locate_workspace_file("crosshair_editor.py") {
            spawn_python_script(&path, &[])?;
            return Ok(());
        }
        Err("crosshair_editor.py not found in workspace".to_owned())
    }

    pub fn launch_ps2_settings_editor(&mut self) -> Result<(), String> {
        if let Some(path) = locate_workspace_file("ps2_settings_editor.py") {
            spawn_python_script(&path, &[])?;
            return Ok(());
        }
        let user_options = self
            .config
            .ps2_path
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .map(|dir| dir.join("UserOptions.ini"));
        if let Some(path) = user_options {
            if path.exists() {
                open_path_in_system(&path)?;
                return Ok(());
            }
        }
        Err("ps2_settings_editor.py and UserOptions.ini were not found".to_owned())
    }

    pub fn request_linux_voice_permissions(&mut self) -> Result<String, String> {
        #[cfg(target_os = "linux")]
        {
            let status = Command::new("xdotool")
                .args(["key", "shift"])
                .status()
                .map_err(|e| format!("xdotool launch failed: {e}"))?;
            if status.success() {
                return Ok("Sent test keypress with xdotool.".to_owned());
            }
            return Err("xdotool returned a non-zero exit status.".to_owned());
        }
        #[cfg(not(target_os = "linux"))]
        {
            Ok("Linux permission request is only relevant on Linux.".to_owned())
        }
    }

    pub fn play_audio_preview_by_name(
        &mut self,
        filename: &str,
        volume_percent: u8,
    ) -> Result<(), String> {
        let Some(audio) = self.audio.as_ref() else {
            return Err("Audio backend is not active.".to_owned());
        };
        let trimmed = filename.trim();
        if trimmed.is_empty() {
            return Err("No sound file selected.".to_owned());
        }
        let Some(path) = resolve_asset_path(trimmed, &self.asset_roots) else {
            return Err(format!("Sound file not found in assets: {trimmed}"));
        };
        let gain =
            ((volume_percent as f32) / 100.0 * self.config.sound_master_volume).clamp(0.0, 2.0);
        audio.play(AudioRequest {
            path,
            volume: gain,
            dedupe_key: Some(format!("preview:{trimmed}")),
            play_duplicate: true,
            dedupe_window_ms: 100,
        });
        Ok(())
    }

    pub fn check_for_updates_now(&self) -> Result<String, String> {
        let owner = "HornGaming";
        let repo = "Better-Planetside";
        let url = format!("https://api.github.com/repos/{owner}/{repo}/releases/latest");
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(8))
            .build()
            .map_err(|e| format!("http client init failed: {e}"))?;
        let response = client
            .get(url)
            .header("User-Agent", "better-planetside-overlay-next")
            .send()
            .map_err(|e| format!("update request failed: {e}"))?;
        if !response.status().is_success() {
            return Err(format!("update request returned {}", response.status()));
        }
        let root = response
            .json::<Value>()
            .map_err(|e| format!("invalid release payload: {e}"))?;
        let latest = root
            .get("tag_name")
            .and_then(Value::as_str)
            .or_else(|| root.get("name").and_then(Value::as_str))
            .unwrap_or("unknown");
        let current = env!("CARGO_PKG_VERSION");
        let latest_tuple = parse_version_tuple(latest);
        let current_tuple = parse_version_tuple(current);
        if latest_tuple > current_tuple {
            let release_url = root
                .get("html_url")
                .and_then(Value::as_str)
                .unwrap_or("https://github.com/HornGaming/Better-Planetside/releases");
            Ok(format!(
                "Update available: {latest} (current {current}). {release_url}"
            ))
        } else {
            Ok(format!("Up to date: {current} (latest {latest})"))
        }
    }

    fn update_state(&mut self, ctx: &egui::Context) {
        // Logic needs update for viewport?
        self.drain_events();
        self.sync_audio_backend();
        self.prune_state();
        self.prune_active_players();
        self.process_queued_legacy_events();
        self.sync_launcher_window_geometry(ctx);
        self.flush_window_geometry_if_due(ctx);
        if self.worker_config_dirty {
            let _ = self.save_settings_now();
        }
        self.persist_runtime_state_if_due();
        // ctx.set_zoom_factor(...) - applied per viewport usually
    }

    fn prune_active_players(&mut self) {
        let now_unix = Utc::now().timestamp() as f64;
        let stale_before = now_unix - 600.0;
        self.active_players
            .retain(|_, entry| entry.last_seen_unix >= stale_before);
    }

    fn draw_overlay(&mut self, ctx: &egui::Context) {
        ctx.set_zoom_factor(self.config.scale.clamp(0.6, 2.0));
        ctx.request_repaint_after(Duration::from_millis(33));

        let alpha = (255.0 * self.config.opacity.clamp(0.1, 1.0)) as u8;
        let overlay_move_mode = self.launcher.overlay_move_mode;

        // Always paint a transparent base panel so the overlay clear pass stays alpha.
        // In move mode we tint it slightly to make editing easier.
        let base_fill = if overlay_move_mode {
            if self.scifi_enabled {
                Color32::from_rgba_premultiplied(8, 14, 22, (alpha / 8).max(16))
            } else {
                Color32::from_rgba_premultiplied(0, 0, 0, (alpha / 10).max(12))
            }
        } else {
            Color32::TRANSPARENT
        };
        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(base_fill))
            .show(ctx, |_ui| {});

        if self.scifi_enabled {
            self.draw_hud_signals(ctx, alpha);
        }

        // Draw Overlay Components

        if self.config.show_session_stats && self.stats_visible {
            let stats_pos = self.stats_origin + self.stats_offset;
            let stats_stroke = if self.stats_glow {
                self.stats_glow_color
                    .map(|c| Stroke::new(1.5, with_alpha(c, 0.65)))
                    .unwrap_or_else(|| {
                        Stroke::new(1.5, with_alpha(Color32::from_rgb(0, 242, 255), 0.65))
                    })
            } else {
                Stroke::NONE
            };
            egui::Area::new(egui::Id::new("stats_area"))
                .order(egui::Order::Foreground)
                .fixed_pos(stats_pos)
                .show(ctx, |ui| {
                    egui::Frame::none()
                        .fill(Color32::from_rgba_premultiplied(
                            12,
                            20,
                            28,
                            (alpha / 2).max(30),
                        ))
                        .stroke(stats_stroke)
                        .inner_margin(Margin::same(self.stats_padding.max(0.0)))
                        .show(ui, |ui| {
                            if let Some(bg_key) = self.stats_bg_filename.clone() {
                                if let Some(texture) = self.load_texture(ctx, &bg_key) {
                                    let rect =
                                        Rect::from_min_size(ui.min_rect().min, self.stats_box_size);
                                    ui.painter().image(
                                        texture.id(),
                                        rect,
                                        Rect::from_min_max(
                                            Pos2::new(0.0, 0.0),
                                            Pos2::new(1.0, 1.0),
                                        ),
                                        with_alpha(Color32::WHITE, 0.8),
                                    );
                                }
                            }
                            ui.set_min_width(self.stats_box_size.x);
                            ui.set_max_width(self.stats_box_size.x);
                            ui.set_min_height(self.stats_box_size.y.max(30.0));
                            ui.label(RichText::new("Session").strong().color(Color32::LIGHT_BLUE));
                            if let Some(text) = &self.legacy_stats_line {
                                ui.label(text);
                            } else {
                                ui.label(format!(
                                    "KD {:.2}  KPM {:.2}  KPH {:.0}  HSR {:.1}%  DHSR {:.1}%  K {} / D {}{}",
                                    self.stats.kd,
                                    self.stats.kpm,
                                    self.stats.kph,
                                    self.stats.hsr,
                                    self.stats.dhsr,
                                    self.stats.kills,
                                    self.stats.deaths,
                                    if self.stats.effective_deaths != self.stats.deaths {
                                        format!(" (eff {})", self.stats.effective_deaths)
                                    } else {
                                        String::new()
                                    }
                                ));
                                if !self.stats.session_time_label.is_empty() {
                                    ui.label(
                                        RichText::new(format!(
                                            "TIME {}",
                                            self.stats.session_time_label
                                        ))
                                        .small()
                                        .color(Color32::GRAY),
                                    );
                                }
                            }
                        });
                });
        }

        if self.config.show_killfeed && (overlay_move_mode || !self.feed.is_empty()) {
            egui::Area::new(egui::Id::new("feed_area"))
                .order(egui::Order::Foreground)
                .fixed_pos(self.feed_origin)
                .show(ctx, |ui| {
                    egui::Frame::none()
                        .fill(if overlay_move_mode {
                            Color32::from_rgba_premultiplied(9, 14, 20, (alpha / 3).max(26))
                        } else {
                            Color32::TRANSPARENT
                        })
                        .stroke(if overlay_move_mode {
                            Stroke::new(1.0, Color32::from_rgba_premultiplied(0, 242, 255, 70))
                        } else {
                            Stroke::NONE
                        })
                        .inner_margin(Margin::same(8.0))
                        .show(ui, |ui| {
                            ui.set_min_width(self.feed_size.x);
                            ui.set_max_width(self.feed_size.x);
                            if overlay_move_mode {
                                ui.label(RichText::new("KILLFEED (MOVE MODE)").strong().underline());
                            }
                            if self.feed.is_empty() {
                                if overlay_move_mode {
                                    ui.label(
                                        RichText::new("No events yet.")
                                            .italics()
                                            .color(Color32::GRAY),
                                    );
                                }
                            } else {
                                egui::ScrollArea::vertical()
                                    .max_height(self.feed_size.y.max(40.0))
                                    .show(ui, |ui| {
                                        let now = Instant::now();
                                        for entry in &self.feed {
                                            let alpha_mul = entry
                                                .expires_at
                                                .map(|expires| {
                                                    let fade_start = expires;
                                                    let fade_dur =
                                                        Duration::from_millis(entry.fade_ms.max(1));
                                                    if now <= fade_start {
                                                        1.0
                                                    } else if now >= fade_start + fade_dur {
                                                        0.0
                                                    } else {
                                                        let rem = (fade_start + fade_dur) - now;
                                                        (rem.as_secs_f32() / fade_dur.as_secs_f32())
                                                            .clamp(0.0, 1.0)
                                                    }
                                                })
                                                .unwrap_or(1.0);
                                            ui.label(
                                                RichText::new(format!(
                                                    "{} | {}",
                                                    entry.item.at.format("%H:%M:%S"),
                                                    entry.item.label
                                                ))
                                                .color(with_alpha(Color32::WHITE, alpha_mul)),
                                            );
                                        }
                                    });
                            }
                        });
                });
        }

        if self.config.show_twitch_chat && !self.chat.is_empty() {
            egui::Area::new(egui::Id::new("chat_area"))
                .order(egui::Order::Foreground)
                .anchor(
                    Align2::RIGHT_BOTTOM,
                    [
                        self.config.chat_anchor_offset_x,
                        self.config.chat_anchor_offset_y,
                    ],
                )
                .show(ctx, |ui| {
                    egui::Frame::none()
                        .fill(if overlay_move_mode {
                            Color32::from_rgba_premultiplied(6, 10, 14, (alpha / 3).max(24))
                        } else {
                            Color32::TRANSPARENT
                        })
                        .stroke(if overlay_move_mode {
                            Stroke::new(1.0, Color32::from_rgba_premultiplied(0, 242, 255, 70))
                        } else {
                            Stroke::NONE
                        })
                        .inner_margin(Margin::same(8.0))
                        .show(ui, |ui| {
                            if overlay_move_mode {
                                ui.label(RichText::new("TWITCH CHAT (MOVE MODE)").strong().underline());
                            }
                            for entry in &self.chat {
                                ui.horizontal_wrapped(|ui| {
                                    ui.label(
                                        RichText::new(format!("{} ", entry.at.format("%H:%M:%S")))
                                            .small()
                                            .color(Color32::GRAY),
                                    );
                                    ui.label(
                                        RichText::new(format!("{}:", entry.author))
                                            .small()
                                            .strong()
                                            .color(entry.color.unwrap_or(Color32::LIGHT_BLUE)),
                                    );
                                    ui.label(RichText::new(&entry.text).small());
                                });
                            }
                        });
                });
        }

        self.draw_streak(ctx);
        self.draw_overlay_fx(ctx);
        self.draw_event_visuals(ctx);
        self.draw_crosshair(ctx);
    }
}

impl Drop for OverlayApp {
    fn drop(&mut self) {
        if let Ok(state) = self.state.try_borrow() {
            let snapshot = state.build_persisted_state();
            let _ = save_state(&state.state_path, &snapshot);
        }
    }
}

fn draw_rotated_image(
    painter: &egui::Painter,
    texture_id: egui::TextureId,
    center: Pos2,
    size: Vec2,
    rotation_deg: f32,
    tint: Color32,
) {
    let theta = rotation_deg.to_radians();
    let (s, c) = theta.sin_cos();
    let half = size * 0.5;
    let corners = [
        Vec2::new(-half.x, -half.y),
        Vec2::new(half.x, -half.y),
        Vec2::new(half.x, half.y),
        Vec2::new(-half.x, half.y),
    ];
    let rotate = |v: Vec2| -> Vec2 { Vec2::new(v.x * c - v.y * s, v.x * s + v.y * c) };

    let p0 = center + rotate(corners[0]);
    let p1 = center + rotate(corners[1]);
    let p2 = center + rotate(corners[2]);
    let p3 = center + rotate(corners[3]);

    let mut mesh = egui::epaint::Mesh::with_texture(texture_id);
    let base = mesh.vertices.len() as u32;
    mesh.vertices.push(egui::epaint::Vertex {
        pos: p0,
        uv: Pos2::new(0.0, 0.0),
        color: tint,
    });
    mesh.vertices.push(egui::epaint::Vertex {
        pos: p1,
        uv: Pos2::new(1.0, 0.0),
        color: tint,
    });
    mesh.vertices.push(egui::epaint::Vertex {
        pos: p2,
        uv: Pos2::new(1.0, 1.0),
        color: tint,
    });
    mesh.vertices.push(egui::epaint::Vertex {
        pos: p3,
        uv: Pos2::new(0.0, 1.0),
        color: tint,
    });
    mesh.indices
        .extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    painter.add(egui::Shape::mesh(mesh));
}

fn detect_asset_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("assets"));
        candidates.push(cwd.join("..").join("assets"));
        candidates.push(cwd.join("_internal").join("assets"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("assets"));
            candidates.push(exe_dir.join("..").join("assets"));
            candidates.push(exe_dir.join("_internal").join("assets"));
        }
    }
    for path in candidates {
        if path.is_dir() && !roots.iter().any(|existing| existing == &path) {
            roots.push(path);
        }
    }
    roots
}

fn resolve_asset_path(filename: &str, roots: &[PathBuf]) -> Option<PathBuf> {
    let clean = filename.trim().trim_start_matches(['/', '\\']);
    if clean.is_empty() {
        return None;
    }
    let rel = clean.replace('\\', "/");
    for root in roots {
        for candidate in [
            root.join(&rel),
            root.join("Images").join(&rel),
            root.join("Crosshair").join(&rel),
            root.join("Sounds").join(&rel),
        ] {
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn locate_workspace_file(filename: &str) -> Option<PathBuf> {
    let clean = filename.trim();
    if clean.is_empty() {
        return None;
    }
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join(clean));
        candidates.push(cwd.join("..").join(clean));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join(clean));
            candidates.push(exe_dir.join("..").join(clean));
        }
    }
    candidates.into_iter().find(|path| path.is_file())
}

fn spawn_python_script(path: &Path, args: &[&str]) -> Result<(), String> {
    let mut command = Command::new("python");
    command.arg(path);
    for arg in args {
        command.arg(arg);
    }
    command
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("failed launching {}: {e}", path.display()))
}

fn open_path_in_system(path: &Path) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("cmd");
        cmd.args(["/C", "start", "", &path.display().to_string()]);
        return cmd
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("failed opening {}: {e}", path.display()));
    }
    #[cfg(target_os = "linux")]
    {
        return Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("failed opening {}: {e}", path.display()));
    }
    #[cfg(target_os = "macos")]
    {
        return Command::new("open")
            .arg(path)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("failed opening {}: {e}", path.display()));
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        Err(format!(
            "opening files is unsupported on this platform: {}",
            path.display()
        ))
    }
}

fn parse_version_tuple(version: &str) -> (u32, u32, u32) {
    let normalized = version.trim().trim_start_matches(['v', 'V']);
    let mut parts = normalized.split('.');
    let major = parts
        .next()
        .and_then(|token| {
            token
                .chars()
                .take_while(|c| c.is_ascii_digit())
                .collect::<String>()
                .parse::<u32>()
                .ok()
        })
        .unwrap_or(0);
    let minor = parts
        .next()
        .and_then(|token| {
            token
                .chars()
                .take_while(|c| c.is_ascii_digit())
                .collect::<String>()
                .parse::<u32>()
                .ok()
        })
        .unwrap_or(0);
    let patch = parts
        .next()
        .and_then(|token| {
            token
                .chars()
                .take_while(|c| c.is_ascii_digit())
                .collect::<String>()
                .parse::<u32>()
                .ok()
        })
        .unwrap_or(0);
    (major, minor, patch)
}

fn load_color_image(path: &Path) -> Option<egui::ColorImage> {
    let img = image::open(path).ok()?.to_rgba8();
    let size = [
        usize::try_from(img.width()).ok()?,
        usize::try_from(img.height()).ok()?,
    ];
    let pixels = img.into_raw();
    Some(egui::ColorImage::from_rgba_unmultiplied(size, &pixels))
}

fn with_alpha(color: Color32, multiplier: f32) -> Color32 {
    let alpha = ((color.a() as f32) * multiplier).clamp(0.0, 255.0) as u8;
    Color32::from_rgba_premultiplied(color.r(), color.g(), color.b(), alpha)
}

fn parse_hex_color(value: &str) -> Option<Color32> {
    let hex = value.trim().trim_start_matches('#');
    if hex.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
    let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
    let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
    Some(Color32::from_rgb(r, g, b))
}

fn value_to_f32(value: &Value) -> Option<f32> {
    value.as_f64().map(|v| v as f32)
}

fn classify_feed_text(lower: &str) -> &'static str {
    if lower.contains("death") {
        "death"
    } else if lower.contains("headshot") {
        "headshot"
    } else if lower.contains("gunner") {
        "gunner"
    } else if lower.contains("revive") {
        "revive"
    } else if lower.contains("kill") {
        "kill"
    } else {
        "feed"
    }
}

fn parse_session_raw_from_value(data: &Value) -> SessionRawStats {
    fn u32_from(data: &Value, names: &[&str]) -> u32 {
        for name in names {
            if let Some(v) = data.get(*name).and_then(Value::as_u64) {
                if let Ok(out) = u32::try_from(v) {
                    return out;
                }
            }
        }
        0
    }
    fn f64_from(data: &Value, names: &[&str]) -> f64 {
        for name in names {
            if let Some(v) = data.get(*name).and_then(Value::as_f64) {
                return v;
            }
        }
        0.0
    }
    fn bool_from(data: &Value, name: &str) -> Option<bool> {
        data.get(name).and_then(Value::as_bool)
    }

    SessionRawStats {
        k: u32_from(data, &["k", "kills"]),
        d: u32_from(data, &["d", "deaths"]),
        hs: u32_from(data, &["hs"]),
        hsrkill: u32_from(data, &["hsrkill"]),
        dhs: u32_from(data, &["dhs"]),
        dhs_eligible: u32_from(data, &["dhs_eligible"]),
        start: f64_from(data, &["start"]),
        acc_t: f64_from(data, &["acc_t"]),
        revives_received: u32_from(data, &["revives_received"]),
        kd_mode_revive: bool_from(data, "kd_mode_revive"),
    }
}

fn parse_utc_timestamp(value: &str) -> Option<DateTime<Utc>> {
    chrono::DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
}

fn parse_number_after(text: &str, label: &str) -> Option<f32> {
    let needle = format!("{label}:");
    let mut start = 0usize;
    while let Some(rel_idx) = text[start..].find(&needle) {
        let idx = start + rel_idx;
        let is_boundary = idx == 0
            || !text[..idx]
                .chars()
                .last()
                .map(|ch| ch.is_ascii_alphanumeric() || ch == '_')
                .unwrap_or(false);
        if is_boundary {
            let rest = &text[(idx + needle.len())..];
            let token = rest.trim_start().split_whitespace().next()?;
            let token = token
                .trim_end_matches('%')
                .trim_end_matches('|')
                .trim_end_matches(',');
            if let Ok(value) = token.parse::<f32>() {
                return Some(value);
            }
        }
        start = idx + needle.len();
    }
    None
}

fn parse_time_label(text: &str) -> Option<String> {
    let marker = "TIME:";
    let idx = text.find(marker)?;
    let rest = text[(idx + marker.len())..].trim_start();
    let token = rest
        .split_whitespace()
        .next()?
        .trim_end_matches('|')
        .trim_end_matches(',');
    if token.contains(':') {
        Some(token.to_owned())
    } else {
        None
    }
}

fn html_to_text(input: &str) -> String {
    let mut plain = String::with_capacity(input.len());
    let mut in_tag = false;
    for ch in input.chars() {
        match ch {
            '<' => in_tag = true,
            '>' => in_tag = false,
            _ if !in_tag => plain.push(ch),
            _ => {}
        }
    }
    let plain = plain
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">");
    let mut compact = String::with_capacity(plain.len());
    let mut prev_space = false;
    for ch in plain.chars() {
        if ch.is_whitespace() {
            if !prev_space {
                compact.push(' ');
                prev_space = true;
            }
        } else {
            compact.push(ch);
            prev_space = false;
        }
    }
    compact.trim().to_owned()
}

#[cfg(not(test))]
fn dispatch_voice_hotkey(digit: String) {
    std::thread::spawn(move || {
        #[cfg(target_os = "windows")]
        {
            let script = format!(
                "$wshell = New-Object -ComObject WScript.Shell; $null = $wshell.SendKeys('v'); Start-Sleep -Milliseconds 50; $null = $wshell.SendKeys('{digit}')"
            );
            let _ = Command::new("powershell")
                .args(["-NoProfile", "-NonInteractive", "-Command", &script])
                .status();
            return;
        }
        #[cfg(target_os = "linux")]
        {
            let _ = Command::new("xdotool").args(["key", "v"]).status();
            std::thread::sleep(Duration::from_millis(50));
            let _ = Command::new("xdotool")
                .args(["key", digit.as_str()])
                .status();
            return;
        }
        #[cfg(not(any(target_os = "windows", target_os = "linux")))]
        {
            let _ = digit;
        }
    });
}

#[cfg(test)]
fn dispatch_voice_hotkey(_digit: String) {}

#[cfg(test)]
mod tests {
    use std::{
        path::PathBuf,
        time::{Duration, Instant},
    };

    use crossbeam_channel::unbounded;
    use eframe::egui::{Color32, Pos2, Rect, Vec2};
    use serde_json::{from_value, json};

    use crate::{
        characters::CharacterEntry,
        config::{LegacyVisualOverride, OverlayConfig},
        events::OverlayEvent,
        protocol::LegacyEnvelope,
    };

    use super::OverlayApp;

    use super::{
        dominant_layout_resize_delta, html_to_text, parse_number_after,
        parse_session_raw_from_value, snap_rect_min_to_screen,
    };

    #[test]
    fn parse_number_after_respects_label_boundaries() {
        let line = "KD: 2.50 | K: 25 | D: 10 | KPM: 1.4";
        assert_eq!(parse_number_after(line, "KD"), Some(2.5));
        assert_eq!(parse_number_after(line, "K"), Some(25.0));
        assert_eq!(parse_number_after(line, "D"), Some(10.0));
        assert_eq!(parse_number_after(line, "KPM"), Some(1.4));
    }

    #[test]
    fn html_to_text_collapses_tags_and_whitespace() {
        let input = "<div>  KD: <b>2.5</b>   &nbsp; K: 20 </div>";
        assert_eq!(html_to_text(input), "KD: 2.5 K: 20");
    }

    #[test]
    fn legacy_twitch_message_supports_html_and_color() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let message: LegacyEnvelope = from_value(json!({
            "category": "twitch_message",
            "data": {
                "author": "Viewer",
                "html": "<b>Hello</b> &amp; welcome",
                "color": "#1e90ff",
                "hold_seconds": 0
            }
        }))
        .expect("message should parse");

        app.handle_legacy_message(message);
        assert_eq!(app.chat.len(), 1);
        assert_eq!(app.chat[0].author, "Viewer");
        assert_eq!(app.chat[0].text, "Hello & welcome");
        assert_eq!(app.chat[0].color, Some(Color32::from_rgb(30, 144, 255)));
        assert!(app.chat[0].expires_at.is_none());
    }

    #[test]
    fn overlay_twitch_event_applies_author_color() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.handle_overlay_event(OverlayEvent::TwitchMessage {
            author: "Viewer".to_owned(),
            text: "hi".to_owned(),
            color: Some("#ffaa00".to_owned()),
            at: chrono::Utc::now(),
        });
        assert_eq!(app.chat.len(), 1);
        assert_eq!(app.chat[0].color, Some(Color32::from_rgb(255, 170, 0)));
    }

    #[test]
    fn twitch_status_message_updates_runtime_connection_state() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let connected: LegacyEnvelope = from_value(json!({
            "category": "twitch_status",
            "data": {
                "status": "CONNECTED: #horngaming",
                "connected": true
            }
        }))
        .expect("twitch status should parse");
        app.handle_legacy_message(connected);
        assert!(app.launcher.twitch.connected);
        assert_eq!(
            app.launcher.twitch.status.as_deref(),
            Some("CONNECTED: #horngaming")
        );

        let disconnected: LegacyEnvelope = from_value(json!({
            "category": "twitch_status",
            "data": {
                "status": "DISCONNECTED",
                "connected": false
            }
        }))
        .expect("twitch status should parse");
        app.handle_legacy_message(disconnected);
        assert!(!app.launcher.twitch.connected);
    }

    #[test]
    fn voice_trigger_message_uses_macro_binding() {
        let (_tx, rx) = unbounded();
        let mut config = OverlayConfig::default();
        config.voice_macros_active = true;
        config.voice_macro_revived = "5".to_owned();
        let mut app = OverlayApp::new(rx, config, PathBuf::from("config.json"));
        let trigger: LegacyEnvelope = from_value(json!({
            "category": "voice_trigger",
            "data": {
                "trigger": "revived"
            }
        }))
        .expect("voice trigger should parse");
        app.handle_legacy_message(trigger);
        assert_eq!(
            app.launcher.voice_status.as_deref(),
            Some("Auto voice triggered: V-5 (revived)")
        );
    }

    #[test]
    fn parse_session_raw_supports_kills_deaths_aliases() {
        let payload = json!({
            "kills": 12,
            "deaths": 5,
            "hs": 3,
            "revives_received": 1
        });
        let raw = parse_session_raw_from_value(&payload);
        assert_eq!(raw.k, 12);
        assert_eq!(raw.d, 5);
        assert_eq!(raw.hs, 3);
        assert_eq!(raw.revives_received, 1);
    }

    #[test]
    fn dominant_layout_resize_delta_prefers_larger_axis() {
        assert_eq!(dominant_layout_resize_delta(Vec2::new(12.0, 5.0)), 12.0);
        assert_eq!(dominant_layout_resize_delta(Vec2::new(4.0, -9.0)), -9.0);
    }

    #[test]
    fn dominant_layout_resize_delta_uses_x_when_tied() {
        assert_eq!(dominant_layout_resize_delta(Vec2::new(-7.0, 7.0)), -7.0);
    }

    #[test]
    fn active_player_upsert_syncs_dashboard_world_for_active_character() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.characters.push(CharacterEntry {
            character_id: "123".to_owned(),
            name: "Pilot".to_owned(),
            world_id: Some("10".to_owned()),
        });
        app.active_character_id = Some("123".to_owned());
        app.config.world_id = "10".to_owned();
        app.launcher.dashboard.selected_world_id = "10".to_owned();

        let upsert: LegacyEnvelope = from_value(json!({
            "category": "active_player_upsert",
            "data": {
                "character_id": "123",
                "faction": "TR",
                "world_id": "17",
                "last_seen": 1700000000.0
            }
        }))
        .expect("upsert message should parse");
        app.handle_legacy_message(upsert);

        assert_eq!(app.config.world_id, "1");
        assert_eq!(app.launcher.dashboard.selected_world_id, "1");
        assert_eq!(
            app.characters
                .iter()
                .find(|entry| entry.character_id == "123")
                .and_then(|entry| entry.world_id.as_deref()),
            Some("17")
        );
    }

    #[test]
    fn snap_rect_min_to_screen_snaps_edges_and_center() {
        let screen = Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(1920.0, 1080.0));
        let size = Vec2::new(400.0, 200.0);
        let left = snap_rect_min_to_screen(Pos2::new(14.0, 300.0), size, screen, 25.0);
        assert_eq!(left.x, 0.0);
        let center = snap_rect_min_to_screen(Pos2::new(770.0, 441.0), size, screen, 25.0);
        assert_eq!(center.x, 760.0);
        assert_eq!(center.y, 440.0);
    }

    #[test]
    fn snap_rect_min_to_screen_clamps_to_bounds() {
        let screen = Rect::from_min_max(Pos2::new(0.0, 0.0), Pos2::new(500.0, 300.0));
        let size = Vec2::new(220.0, 120.0);
        let out = snap_rect_min_to_screen(Pos2::new(900.0, -50.0), size, screen, 25.0);
        assert_eq!(out.x, 280.0);
        assert_eq!(out.y, 0.0);
    }

    #[test]
    fn legacy_event_honors_play_duplicate_false() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let message: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Headshot",
                "event_type": "headshot",
                "duration": 1200,
                "play_duplicate": false
            }
        }))
        .expect("legacy message should parse");

        app.handle_legacy_message(message.clone());
        assert_eq!(app.event_visuals.len(), 1);

        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
    }

    #[test]
    fn legacy_feed_payload_updates_geometry_and_max_items() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let initial_feed_len = app.feed.len();
        let message: LegacyEnvelope = from_value(json!({
            "category": "feed",
            "data": {
                "html": "<div>Enemy Down</div>",
                "x": 320,
                "y": 240,
                "width": 720,
                "height": 420,
                "max_items": 12,
                "auto_remove": false
            }
        }))
        .expect("legacy feed should parse");

        app.handle_legacy_message(message);
        assert_eq!(app.feed_origin.x, 320.0);
        assert_eq!(app.feed_origin.y, 240.0);
        assert_eq!(app.feed_size.x, 720.0);
        assert_eq!(app.feed_size.y, 420.0);
        assert_eq!(app.config.max_feed_items, 12);
        assert_eq!(app.feed.len(), initial_feed_len + 1);
    }

    #[test]
    fn legacy_stats_payload_tracks_image_and_stats_clear_resets_it() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let stats_msg: LegacyEnvelope = from_value(json!({
            "category":"stats",
            "data":{
                "html":"KD: 2.0",
                "img_filename":"Headshot Banner.png"
            }
        }))
        .expect("stats should parse");
        app.handle_legacy_message(stats_msg);
        assert_eq!(
            app.stats_bg_filename.as_deref(),
            Some("Headshot Banner.png")
        );
        let clear_msg: LegacyEnvelope = from_value(json!({
            "category":"stats_clear",
            "data":{"ts":1}
        }))
        .expect("stats_clear should parse");
        app.handle_legacy_message(clear_msg);
        assert!(app.stats_bg_filename.is_none());
        assert!(!app.stats_visible);
    }

    #[test]
    fn legacy_stats_scale_applies_to_box_and_padding() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let stats_msg: LegacyEnvelope = from_value(json!({
            "category":"stats",
            "data":{
                "html":"KD: 2.0",
                "box_width":200.0,
                "box_height":40.0,
                "padding":10.0,
                "scale":1.5
            }
        }))
        .expect("stats should parse");
        app.handle_legacy_message(stats_msg);
        assert_eq!(app.stats_box_size.x, 300.0);
        assert_eq!(app.stats_box_size.y, 60.0);
        assert_eq!(app.stats_padding, 15.0);
    }

    #[test]
    fn legacy_event_queue_serializes_event_visuals() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let ev1: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Kill",
                "event_type": "kill",
                "duration": 800
            }
        }))
        .expect("first legacy event should parse");
        let ev2: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Headshot",
                "event_type": "headshot",
                "duration": 800
            }
        }))
        .expect("second legacy event should parse");

        app.handle_legacy_message(ev1);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.legacy_event_queue.len(), 0);
        assert!(app.legacy_event_busy_until.is_some());

        app.handle_legacy_message(ev2);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.legacy_event_queue.len(), 1);

        app.legacy_event_busy_until = Some(Instant::now() - Duration::from_millis(1));
        app.process_queued_legacy_events();
        assert_eq!(app.legacy_event_queue.len(), 0);
        assert!(app.legacy_event_busy_until.is_some());
    }

    #[test]
    fn hitmarker_bypasses_legacy_event_queue() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let ev: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Kill",
                "event_type": "kill",
                "duration": 1200
            }
        }))
        .expect("legacy event should parse");
        let hitmarker: LegacyEnvelope = from_value(json!({
            "category": "hitmarker",
            "data": {
                "event_type": "hitmarker",
                "duration": 120
            }
        }))
        .expect("legacy hitmarker should parse");

        app.handle_legacy_message(ev);
        assert_eq!(app.event_visuals.len(), 1);
        assert!(app.legacy_event_busy_until.is_some());

        app.handle_legacy_message(hitmarker);
        assert_eq!(app.legacy_event_queue.len(), 0);
        assert_eq!(app.event_visuals.len(), 2);
    }

    #[test]
    fn legacy_visual_offsets_apply_to_event_and_hitmarker() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        app.config.event_offset_x = 11.0;
        app.config.event_offset_y = -7.0;
        app.config.hitmarker_offset_x = -5.0;
        app.config.hitmarker_offset_y = 9.0;

        let event_msg: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Kill",
                "event_type": "kill",
                "x": 100,
                "y": 200,
                "duration": 300
            }
        }))
        .expect("event should parse");
        app.handle_legacy_message(event_msg);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.event_visuals[0].pos.x, 111.0);
        assert_eq!(app.event_visuals[0].pos.y, 193.0);

        let hitmarker_msg: LegacyEnvelope = from_value(json!({
            "category": "hitmarker",
            "data": {
                "event_type": "hitmarker",
                "x": 40,
                "y": 80,
                "duration": 120
            }
        }))
        .expect("hitmarker should parse");
        app.handle_legacy_message(hitmarker_msg);
        assert_eq!(app.event_visuals.len(), 2);
        assert_eq!(app.event_visuals[0].pos.x, 35.0);
        assert_eq!(app.event_visuals[0].pos.y, 89.0);
    }

    #[test]
    fn worker_status_message_updates_panel_state() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let status_msg: LegacyEnvelope = from_value(json!({
            "category": "worker_status",
            "data": {
                "ws_server": true,
                "ws_bind": "127.0.0.1:38471",
                "ws_error": null,
                "legacy_bridge": true,
                "legacy_error": null,
                "twitch_worker": false,
                "twitch_error": "twitch_worker_enabled=false",
                "census_worker": true
            }
        }))
        .expect("status message should parse");

        app.handle_legacy_message(status_msg);
        assert!(app.worker_status_ws);
        assert_eq!(
            app.worker_status_ws_bind.as_deref(),
            Some("127.0.0.1:38471")
        );
        assert!(app.worker_status_ws_error.is_none());
        assert!(app.worker_status_legacy);
        assert!(app.worker_status_legacy_error.is_none());
        assert!(!app.worker_status_twitch);
        assert_eq!(
            app.worker_status_twitch_error.as_deref(),
            Some("twitch_worker_enabled=false")
        );
        assert!(app.worker_status_census);
        assert!(app.worker_status_updated_at.is_some());
    }

    #[test]
    fn worker_status_message_tracks_ws_error_text() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let status_msg: LegacyEnvelope = from_value(json!({
            "category": "worker_status",
            "data": {
                "ws_server": false,
                "ws_error": "invalid ws_bind: bad"
            }
        }))
        .expect("status message should parse");
        app.handle_legacy_message(status_msg);
        assert!(!app.worker_status_ws);
        assert_eq!(
            app.worker_status_ws_error.as_deref(),
            Some("invalid ws_bind: bad")
        );
    }

    #[test]
    fn worker_status_message_tracks_worker_notes() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let status_msg: LegacyEnvelope = from_value(json!({
            "category": "worker_status",
            "data": {
                "legacy_error": "legacy_source_ws is empty/disabled",
                "twitch_error": "twitch_channel is empty",
                "census_error": "missing census_service_id or census_character_id (config/.env)"
            }
        }))
        .expect("status message should parse");
        app.handle_legacy_message(status_msg);
        assert_eq!(
            app.worker_status_legacy_error.as_deref(),
            Some("legacy_source_ws is empty/disabled")
        );
        assert_eq!(
            app.worker_status_twitch_error.as_deref(),
            Some("twitch_channel is empty")
        );
        assert_eq!(
            app.worker_status_census_error.as_deref(),
            Some("missing census_service_id or census_character_id (config/.env)")
        );
    }

    #[test]
    fn game_status_message_updates_runtime_state() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let message: LegacyEnvelope = from_value(json!({
            "category": "game_status",
            "data": {
                "running": true,
                "process": "PlanetSide2_x64.exe"
            }
        }))
        .expect("game status should parse");
        app.handle_legacy_message(message);
        assert!(app.game_running);
        assert_eq!(app.game_process.as_deref(), Some("PlanetSide2_x64.exe"));
        assert!(app.game_status_updated_at.is_some());
    }

    #[test]
    fn auto_overlay_visibility_starts_hidden() {
        let (_tx, rx) = unbounded();
        let mut config = OverlayConfig::default();
        config.auto_overlay_visibility = true;
        let app = OverlayApp::new(rx, config, PathBuf::from("config.json"));
        assert!(!app.overlay_visible);
        assert!(app.config_ui_visible);
    }

    #[test]
    fn legacy_visual_override_applies_position_size_and_centered() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        app.config.legacy_visual_overrides.insert(
            "headshot".to_owned(),
            LegacyVisualOverride {
                filename: Some("Headshot.png".to_owned()),
                x: Some(333.0),
                y: Some(444.0),
                width: Some(120.0),
                height: Some(80.0),
                centered: Some(true),
                ..Default::default()
            },
        );
        let message: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{
                "event_name":"Headshot",
                "event_type":"headshot",
                "duration":300
            }
        }))
        .expect("event should parse");
        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.event_visuals[0].pos.x, 333.0);
        assert_eq!(app.event_visuals[0].pos.y, 444.0);
        assert_eq!(app.event_visuals[0].size.x, 120.0);
        assert_eq!(app.event_visuals[0].size.y, 80.0);
        assert!(app.event_visuals[0].centered);
        assert_eq!(
            app.event_visuals[0].texture_key.as_deref(),
            Some("Headshot.png")
        );
    }

    #[test]
    fn legacy_event_accepts_duration_ms_alias() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let message: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{
                "event_name":"Kill",
                "event_type":"kill",
                "duration_ms":900
            }
        }))
        .expect("event should parse");
        let now = Instant::now();
        app.handle_legacy_message(message);
        let busy_until = app
            .legacy_event_busy_until
            .expect("event should set queue busy deadline");
        assert!(busy_until > now + Duration::from_millis(850));
    }

    #[test]
    fn legacy_visual_override_falls_back_to_first_token_key() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        app.config.legacy_visual_overrides.insert(
            "kill".to_owned(),
            LegacyVisualOverride {
                x: Some(610.0),
                y: Some(330.0),
                ..Default::default()
            },
        );
        let message: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{
                "event_name":"Kill Vehicle",
                "event_type":"Kill Vehicle",
                "duration":300
            }
        }))
        .expect("event should parse");
        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.event_visuals[0].pos.x, 610.0);
        assert_eq!(app.event_visuals[0].pos.y, 330.0);
    }

    #[test]
    fn legacy_visual_override_falls_back_to_category_key() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        app.config.legacy_visual_overrides.insert(
            "event".to_owned(),
            LegacyVisualOverride {
                x: Some(777.0),
                y: Some(222.0),
                ..Default::default()
            },
        );
        let message: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{
                "event_name":"Completely Unmapped",
                "event_type":"Completely Unmapped",
                "duration":200
            }
        }))
        .expect("event should parse");
        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.event_visuals[0].pos.x, 777.0);
        assert_eq!(app.event_visuals[0].pos.y, 222.0);
    }

    #[test]
    fn hitmarker_visual_override_uses_hitmarker_category_key() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        app.config.legacy_visual_overrides.insert(
            "hitmarker".to_owned(),
            LegacyVisualOverride {
                x: Some(91.0),
                y: Some(72.0),
                width: Some(44.0),
                height: Some(36.0),
                ..Default::default()
            },
        );
        let message: LegacyEnvelope = from_value(json!({
            "category":"hitmarker",
            "data":{
                "event_type":"hitmarker",
                "duration":120
            }
        }))
        .expect("hitmarker should parse");
        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
        assert_eq!(app.event_visuals[0].pos.x, 91.0);
        assert_eq!(app.event_visuals[0].pos.y, 72.0);
        assert_eq!(app.event_visuals[0].size.x, 44.0);
        assert_eq!(app.event_visuals[0].size.y, 36.0);
    }

    #[test]
    fn store_last_visual_override_preserves_non_geometry_fields() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.legacy_visual_overrides.insert(
            "headshot".to_owned(),
            LegacyVisualOverride {
                filename: Some("Headshot.png".to_owned()),
                sound_filename: Some("Headshot.ogg".to_owned()),
                ..Default::default()
            },
        );
        app.last_visual_pos = Pos2::new(412.0, 188.0);
        app.last_visual_size = Vec2::new(250.0, 120.0);
        app.last_visual_centered = true;
        app.store_last_visual_override("headshot".to_owned());

        let entry = app
            .config
            .legacy_visual_overrides
            .get("headshot")
            .expect("override should exist");
        assert_eq!(entry.filename.as_deref(), Some("Headshot.png"));
        assert_eq!(entry.sound_filename.as_deref(), Some("Headshot.ogg"));
        assert_eq!(entry.x, Some(412.0));
        assert_eq!(entry.y, Some(188.0));
        assert_eq!(entry.width, Some(250.0));
        assert_eq!(entry.height, Some(120.0));
        assert_eq!(entry.centered, Some(true));
    }

    #[test]
    fn events_clear_resets_dedupe_guard() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_active = false;
        let message: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Headshot",
                "event_type": "headshot",
                "duration": 1200,
                "play_duplicate": false
            }
        }))
        .expect("legacy message should parse");
        let clear: LegacyEnvelope = from_value(json!({
            "category": "events_clear",
            "data": {"ts": 1}
        }))
        .expect("clear message should parse");

        app.handle_legacy_message(message.clone());
        let after_first = app.event_visuals.len();
        app.handle_legacy_message(message.clone());
        assert_eq!(app.event_visuals.len(), after_first);

        app.handle_legacy_message(clear);
        app.handle_legacy_message(message);
        assert_eq!(app.event_visuals.len(), 1);
    }

    #[test]
    fn play_duplicate_false_does_not_queue_duplicate_when_busy() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        let message: LegacyEnvelope = from_value(json!({
            "category": "event",
            "data": {
                "event_name": "Headshot",
                "event_type": "headshot",
                "duration": 1200,
                "play_duplicate": false
            }
        }))
        .expect("legacy message should parse");

        app.handle_legacy_message(message.clone());
        assert_eq!(app.event_visuals.len(), 1);
        assert!(app.legacy_event_busy_until.is_some());

        app.handle_legacy_message(message);
        assert_eq!(app.legacy_event_queue.len(), 0);
        assert_eq!(app.event_visuals.len(), 1);
    }

    #[test]
    fn legacy_event_queue_trims_by_max_len() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_max_len = 10;
        let first: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{"event_name":"E0","event_type":"e0","duration":1000}
        }))
        .expect("first event should parse");
        app.handle_legacy_message(first);

        for i in 1..=15 {
            let msg: LegacyEnvelope = from_value(json!({
                "category":"event",
                "data":{
                    "event_name": format!("E{i}"),
                    "event_type": format!("e{i}"),
                    "duration": 1000
                }
            }))
            .expect("queued event should parse");
            app.handle_legacy_message(msg);
        }

        assert!(app.legacy_event_queue.len() <= 10);
    }

    #[test]
    fn legacy_event_queue_trims_by_backlog_ms() {
        let (_tx, rx) = unbounded();
        let mut app = OverlayApp::new(rx, OverlayConfig::default(), PathBuf::from("config.json"));
        app.config.event_queue_max_len = 200;
        app.config.event_queue_max_backlog_ms = 2_000;
        let first: LegacyEnvelope = from_value(json!({
            "category":"event",
            "data":{"event_name":"E0","event_type":"e0","duration":1000}
        }))
        .expect("first event should parse");
        app.handle_legacy_message(first);

        for i in 1..=5 {
            let msg: LegacyEnvelope = from_value(json!({
                "category":"event",
                "data":{
                    "event_name": format!("B{i}"),
                    "event_type": format!("b{i}"),
                    "duration": 1000
                }
            }))
            .expect("queued event should parse");
            app.handle_legacy_message(msg);
        }

        let queued_ms: u64 = app
            .legacy_event_queue
            .iter()
            .map(|item| item.duration_ms)
            .sum();
        assert!(queued_ms <= 2_000);
        assert!(app.legacy_event_queue.len() <= 2);
    }
}
