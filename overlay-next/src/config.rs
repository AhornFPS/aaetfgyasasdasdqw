use std::{collections::HashMap, fs, path::PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FeedLayoutConfig {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl Default for FeedLayoutConfig {
    fn default() -> Self {
        Self {
            x: 40.0,
            y: 140.0,
            width: 600.0,
            height: 550.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct StatsLayoutConfig {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub tx: f32,
    pub ty: f32,
    pub padding: f32,
    #[serde(default)]
    pub bg_filename: Option<String>,
    #[serde(default)]
    pub glow: bool,
    #[serde(default)]
    pub glow_color: Option<String>,
    #[serde(default)]
    pub font_name: String,
    #[serde(default)]
    pub label_color: Option<String>,
    #[serde(default)]
    pub value_color: Option<String>,
    #[serde(default)]
    pub show_k: bool,
    #[serde(default)]
    pub show_d: bool,
    #[serde(default)]
    pub show_hsr: bool,
    #[serde(default)]
    pub show_kpm: bool,
    #[serde(default)]
    pub show_kph: bool,
    #[serde(default)]
    pub show_time: bool,
    #[serde(default)]
    pub show_dhsr: bool,
    #[serde(default)]
    pub show_kd: bool,
}

impl Default for StatsLayoutConfig {
    fn default() -> Self {
        Self {
            x: 40.0,
            y: 60.0,
            width: 450.0,
            height: 60.0,
            tx: 0.0,
            ty: 0.0,
            padding: 8.0,
            bg_filename: None,
            glow: true,
            glow_color: None,
            font_name: "Black Ops One".to_owned(),
            label_color: Some("#00f2ff".to_owned()),
            value_color: Some("#ffffff".to_owned()),
            show_k: true,
            show_d: true,
            show_hsr: true,
            show_kpm: true,
            show_kph: true,
            show_time: true,
            show_dhsr: true,
            show_kd: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct StreakLayoutConfig {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    #[serde(default)]
    pub active: bool,
    #[serde(default)]
    pub filename: Option<String>,
    #[serde(default)]
    pub scale: f32,
    #[serde(default)]
    pub font_size: f32,
    #[serde(default)]
    pub color: String,
    #[serde(default)]
    pub bold: bool,
    #[serde(default)]
    pub anim_active: bool,
    #[serde(default)]
    pub anim_speed: f32,
    #[serde(default)]
    pub streak_glow: bool,
    #[serde(default)]
    pub glow_color: Option<String>,
    #[serde(default)]
    pub show_knives: bool,
    #[serde(default)]
    pub knife_tr: Option<String>,
    #[serde(default)]
    pub knife_nc: Option<String>,
    #[serde(default)]
    pub knife_vs: Option<String>,
    #[serde(default)]
    pub knife_nso: Option<String>,
    #[serde(default)]
    pub knives_per_ring: u32,
    #[serde(default)]
    pub ring_spacing: f32,
}

impl Default for StreakLayoutConfig {
    fn default() -> Self {
        Self {
            x: 100.0,
            y: 100.0,
            width: 220.0,
            height: 220.0,
            active: true,
            filename: Some("Skull small.png".to_owned()),
            scale: 1.0,
            font_size: 26.0,
            color: "#ffffff".to_owned(),
            bold: false,
            anim_active: true,
            anim_speed: 50.0,
            streak_glow: true,
            glow_color: Some("#00f2ff".to_owned()),
            show_knives: true,
            knife_tr: None,
            knife_nc: None,
            knife_vs: None,
            knife_nso: None,
            knives_per_ring: 50,
            ring_spacing: 22.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct CrosshairLayoutConfig {
    pub x: Option<f32>,
    pub y: Option<f32>,
    pub size: f32,
    #[serde(default)]
    pub active: bool,
    #[serde(default)]
    pub filename: Option<String>,
    #[serde(default)]
    pub rotation: f32,
    #[serde(default)]
    pub recoil: bool,
    #[serde(default)]
    pub shadow: bool,
    #[serde(default)]
    pub expand_enabled: bool,
}

impl Default for CrosshairLayoutConfig {
    fn default() -> Self {
        Self {
            x: None,
            y: None,
            size: 64.0,
            active: true,
            filename: None,
            rotation: 0.0,
            recoil: false,
            shadow: false,
            expand_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LayoutConfig {
    pub feed: FeedLayoutConfig,
    pub stats: StatsLayoutConfig,
    pub streak: StreakLayoutConfig,
    pub crosshair: CrosshairLayoutConfig,
}

impl Default for LayoutConfig {
    fn default() -> Self {
        Self {
            feed: FeedLayoutConfig::default(),
            stats: StatsLayoutConfig::default(),
            streak: StreakLayoutConfig::default(),
            crosshair: CrosshairLayoutConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct LegacyVisualOverride {
    pub filename: Option<String>,
    pub sound_filename: Option<String>,
    pub sound_volume: Option<f32>,
    pub x: Option<f32>,
    pub y: Option<f32>,
    pub width: Option<f32>,
    pub height: Option<f32>,
    pub scale: Option<f32>,
    pub duration_ms: Option<u64>,
    pub fade_ms: Option<u64>,
    pub centered: Option<bool>,
    pub glow: Option<bool>,
    pub glow_color: Option<String>,
    pub play_duplicate: Option<bool>,
    pub impact: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LauncherWindowConfig {
    pub width: f32,
    pub height: f32,
    pub pos_x: Option<f32>,
    pub pos_y: Option<f32>,
}

impl Default for LauncherWindowConfig {
    fn default() -> Self {
        Self {
            width: 1024.0,
            height: 768.0,
            pos_x: None,
            pos_y: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct OverlayConfig {
    pub ws_bind: String,
    pub legacy_source_ws: Option<String>,
    #[serde(default)]
    pub world_id: String,
    pub opacity: f32,
    pub scale: f32,
    pub show_killfeed: bool,
    pub show_session_stats: bool,
    pub max_feed_items: usize,
    #[serde(default)]
    pub feed_show_revives: bool,
    #[serde(default)]
    pub feed_show_gunner: bool,
    #[serde(default)]
    pub feed_show_vehicle: bool,
    #[serde(default)]
    pub feed_auto_remove: bool,
    #[serde(default)]
    pub feed_hold_seconds: u64,
    #[serde(default)]
    pub feed_font_name: String,
    #[serde(default)]
    pub feed_headshot_icon: Option<String>,
    #[serde(default)]
    pub feed_headshot_scale: f32,
    pub kd_mode_revive: bool,
    pub show_twitch_chat: bool,
    pub mouse_passthrough: bool,
    pub chat_hold_seconds: f32,
    pub max_chat_items: usize,
    pub chat_anchor_offset_x: f32,
    pub chat_anchor_offset_y: f32,
    pub play_event_sounds: bool,
    pub sound_master_volume: f32,
    pub event_offset_x: f32,
    pub event_offset_y: f32,
    pub hitmarker_offset_x: f32,
    pub hitmarker_offset_y: f32,
    pub event_queue_active: bool,
    #[serde(default)]
    pub event_global_duration_ms: u64,
    pub event_queue_max_len: usize,
    pub event_queue_max_backlog_ms: u64,
    pub census_worker_enabled: bool,
    pub census_service_id: Option<String>,
    pub census_character_id: Option<String>,
    pub census_multi_kill_window_secs: f32,
    pub census_weapon_lookup_enabled: bool,
    pub twitch_worker_enabled: bool,
    pub twitch_channel: Option<String>,
    pub twitch_nick: Option<String>,
    pub twitch_ignore_special: bool,
    pub twitch_ignore_users: Vec<String>,
    #[serde(default)]
    pub obs_service_enabled: bool,
    #[serde(default)]
    pub obs_http_port: u16,
    #[serde(default)]
    pub obs_ws_port: u16,
    #[serde(default)]
    pub twitch_always_on: bool,
    #[serde(default)]
    pub twitch_overlay_opacity: u8,
    #[serde(default)]
    pub twitch_font_size: u32,
    #[serde(default)]
    pub twitch_overlay_x: i32,
    #[serde(default)]
    pub twitch_overlay_y: i32,
    #[serde(default)]
    pub twitch_overlay_width: i32,
    #[serde(default)]
    pub twitch_overlay_height: i32,
    #[serde(default)]
    pub twitch_silence_alert_active: bool,
    #[serde(default)]
    pub twitch_silence_timeout_secs: u64,
    #[serde(default)]
    pub twitch_silence_sounds: Vec<String>,
    #[serde(default)]
    pub twitch_silence_sound_active: Option<String>,
    #[serde(default)]
    pub twitch_silence_volume: u8,
    #[serde(default)]
    pub voice_macros_active: bool,
    #[serde(default)]
    pub voice_macro_revived: String,
    #[serde(default)]
    pub voice_macro_tk: String,
    #[serde(default)]
    pub voice_macro_kill_infil: String,
    #[serde(default)]
    pub voice_macro_kill_max: String,
    #[serde(default)]
    pub voice_macro_kill_high_kd: String,
    #[serde(default)]
    pub voice_macro_kill_hs: String,
    pub game_monitor_enabled: bool,
    pub game_process_names: Vec<String>,
    pub game_poll_ms: u64,
    pub auto_overlay_visibility: bool,
    #[serde(default)]
    pub ps2_path: Option<String>,
    #[serde(default)]
    pub main_background_path: Option<String>,
    #[serde(default)]
    pub discord_presence_active: bool,
    #[serde(default)]
    pub launcher_window: LauncherWindowConfig,
    pub layout: LayoutConfig,
    pub legacy_visual_overrides: HashMap<String, LegacyVisualOverride>,
    #[serde(default)]
    pub event_slot_names: Vec<String>,
    #[serde(default)]
    pub event_active_slot: usize,
    #[serde(default)]
    pub event_slot_profiles: HashMap<String, HashMap<String, LegacyVisualOverride>>,
}

impl Default for OverlayConfig {
    fn default() -> Self {
        Self {
            ws_bind: "127.0.0.1:38471".to_owned(),
            legacy_source_ws: Some("ws://127.0.0.1:31338/better_planetside".to_owned()),
            world_id: "10".to_owned(),
            opacity: 0.92,
            scale: 1.0,
            show_killfeed: true,
            show_session_stats: true,
            max_feed_items: 8,
            feed_show_revives: true,
            feed_show_gunner: true,
            feed_show_vehicle: true,
            feed_auto_remove: true,
            feed_hold_seconds: 8,
            feed_font_name: "Black Ops One".to_owned(),
            feed_headshot_icon: None,
            feed_headshot_scale: 1.0,
            kd_mode_revive: true,
            show_twitch_chat: true,
            mouse_passthrough: true,
            chat_hold_seconds: 15.0,
            max_chat_items: 8,
            chat_anchor_offset_x: -24.0,
            chat_anchor_offset_y: -24.0,
            play_event_sounds: false,
            sound_master_volume: 1.0,
            event_offset_x: 0.0,
            event_offset_y: 0.0,
            hitmarker_offset_x: 0.0,
            hitmarker_offset_y: 0.0,
            event_queue_active: true,
            event_global_duration_ms: 3000,
            event_queue_max_len: 48,
            event_queue_max_backlog_ms: 10_000,
            census_worker_enabled: false,
            census_service_id: None,
            census_character_id: None,
            census_multi_kill_window_secs: 4.0,
            census_weapon_lookup_enabled: true,
            twitch_worker_enabled: false,
            twitch_channel: None,
            twitch_nick: None,
            twitch_ignore_special: false,
            twitch_ignore_users: Vec::new(),
            obs_service_enabled: false,
            obs_http_port: 31337,
            obs_ws_port: 31338,
            twitch_always_on: false,
            twitch_overlay_opacity: 30,
            twitch_font_size: 12,
            twitch_overlay_x: 50,
            twitch_overlay_y: 300,
            twitch_overlay_width: 350,
            twitch_overlay_height: 400,
            twitch_silence_alert_active: false,
            twitch_silence_timeout_secs: 600,
            twitch_silence_sounds: Vec::new(),
            twitch_silence_sound_active: None,
            twitch_silence_volume: 100,
            voice_macros_active: true,
            voice_macro_revived: "OFF".to_owned(),
            voice_macro_tk: "OFF".to_owned(),
            voice_macro_kill_infil: "OFF".to_owned(),
            voice_macro_kill_max: "OFF".to_owned(),
            voice_macro_kill_high_kd: "OFF".to_owned(),
            voice_macro_kill_hs: "OFF".to_owned(),
            game_monitor_enabled: true,
            game_process_names: vec![
                "PlanetSide2_x64.exe".to_owned(),
                "PlanetSide2.exe".to_owned(),
            ],
            game_poll_ms: 1_500,
            auto_overlay_visibility: false,
            ps2_path: None,
            main_background_path: None,
            discord_presence_active: false,
            launcher_window: LauncherWindowConfig::default(),
            layout: LayoutConfig::default(),
            legacy_visual_overrides: HashMap::new(),
            event_slot_names: Vec::new(),
            event_active_slot: 0,
            event_slot_profiles: HashMap::new(),
        }
    }
}

impl OverlayConfig {
    pub fn load_or_create() -> Result<(Self, PathBuf)> {
        let config_dir = dirs::config_dir()
            .context("unable to locate OS config directory")?
            .join("better-planetside-overlay-next");
        fs::create_dir_all(&config_dir)
            .with_context(|| format!("failed creating config dir at {}", config_dir.display()))?;

        let config_path = config_dir.join("config.json");
        if !config_path.exists() {
            let default = Self::default();
            default.save(&config_path)?;
            return Ok((default, config_path));
        }

        let text = fs::read_to_string(&config_path)
            .with_context(|| format!("failed reading {}", config_path.display()))?;
        let config = serde_json::from_str::<Self>(&text)
            .with_context(|| format!("invalid json in {}", config_path.display()))?;
        Ok((config, config_path))
    }

    pub fn save(&self, path: &PathBuf) -> Result<()> {
        let payload = serde_json::to_string_pretty(self).context("failed serializing config")?;
        fs::write(path, payload).with_context(|| format!("failed writing {}", path.display()))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::OverlayConfig;

    #[test]
    fn parses_legacy_config_without_layout_section() {
        let raw = r#"{
            "ws_bind": "127.0.0.1:38471",
            "show_killfeed": true
        }"#;
        let parsed: OverlayConfig = serde_json::from_str(raw).expect("config should parse");
        assert!(parsed.mouse_passthrough);
        assert_eq!(parsed.layout.feed.x, 40.0);
        assert_eq!(parsed.layout.stats.width, 450.0);
        assert_eq!(parsed.layout.crosshair.size, 64.0);
        assert_eq!(parsed.launcher_window.width, 1024.0);
        assert_eq!(parsed.launcher_window.height, 768.0);
        assert_eq!(parsed.launcher_window.pos_x, None);
        assert_eq!(parsed.launcher_window.pos_y, None);
        assert!(parsed.legacy_visual_overrides.is_empty());
    }

    #[test]
    fn parses_legacy_visual_override_fields() {
        let raw = r##"{
            "legacy_visual_overrides": {
                "headshot": {
                    "filename": "Headshot.png",
                    "sound_filename": "Headshot.ogg",
                    "sound_volume": 0.8,
                    "x": 500,
                    "y": 200,
                    "width": 240,
                    "height": 120,
                    "scale": 1.2,
                    "duration_ms": 900,
                    "fade_ms": 200,
                    "centered": true,
                    "glow": true,
                    "glow_color": "#00f2ff",
                    "play_duplicate": false,
                    "impact": true
                }
            }
        }"##;
        let parsed: OverlayConfig = serde_json::from_str(raw).expect("config should parse");
        let headshot = parsed
            .legacy_visual_overrides
            .get("headshot")
            .expect("headshot override should exist");
        assert_eq!(headshot.filename.as_deref(), Some("Headshot.png"));
        assert_eq!(headshot.sound_filename.as_deref(), Some("Headshot.ogg"));
        assert_eq!(headshot.sound_volume, Some(0.8));
        assert_eq!(headshot.duration_ms, Some(900));
        assert_eq!(headshot.fade_ms, Some(200));
        assert_eq!(headshot.play_duplicate, Some(false));
        assert_eq!(headshot.impact, Some(true));
    }
}
