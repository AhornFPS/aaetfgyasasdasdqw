pub mod characters_page;
pub mod crosshair;
pub mod dashboard;
pub mod events;
pub mod game_launcher;
pub mod identity;
pub mod killfeed;
pub mod killstreak;
pub mod obs;
pub mod settings_page;
pub mod stats;
pub mod theme;
pub mod twitch;
pub mod ui;
pub mod voice;

use crate::characters::CharacterEntry;
use crate::config::LegacyVisualOverride;
use crate::dior_db::PlayerCacheEntry;
use std::collections::HashMap;
use std::sync::mpsc::Receiver;
use std::time::Instant;

pub struct LauncherState {
    pub active_top_tab: TopLevelTab,
    pub active_tab: LauncherTab,
    pub overlay_move_mode: bool,
    pub voice_macros_enabled: bool,
    pub crosshair_shadow_enabled: bool,
    pub crosshair_expand_enabled: bool,
    pub dashboard: DashboardTabState,
    pub twitch: TwitchTabState,
    pub obs: ObsTabState,
    pub launcher_status: Option<String>,
    pub settings_status: Option<String>,
    pub voice_status: Option<String>,
    pub stats_status: Option<String>,
    pub crosshair_status: Option<String>,
    pub killstreak_status: Option<String>,
    pub characters: CharactersTabState,
    pub identity: IdentityTabState,
    pub events: EventsTabState,
}

impl Default for LauncherState {
    fn default() -> Self {
        Self {
            active_top_tab: TopLevelTab::Dashboard,
            active_tab: LauncherTab::Identity,
            overlay_move_mode: false,
            voice_macros_enabled: true,
            crosshair_shadow_enabled: false,
            crosshair_expand_enabled: true,
            dashboard: DashboardTabState::default(),
            twitch: TwitchTabState::default(),
            obs: ObsTabState::default(),
            launcher_status: None,
            settings_status: None,
            voice_status: None,
            stats_status: None,
            crosshair_status: None,
            killstreak_status: None,
            characters: CharactersTabState::default(),
            identity: IdentityTabState::default(),
            events: EventsTabState::default(),
        }
    }
}

pub struct DashboardTabState {
    pub selected_world_id: String,
    pub graph_show_factions: bool,
    pub tr_sort: DashboardSortState,
    pub nc_sort: DashboardSortState,
    pub vs_sort: DashboardSortState,
    pub pop_history: Vec<u32>,
    pub tr_history: Vec<u32>,
    pub nc_history: Vec<u32>,
    pub vs_history: Vec<u32>,
    pub last_history_sample: Instant,
}

impl Default for DashboardTabState {
    fn default() -> Self {
        Self {
            selected_world_id: "10".to_owned(),
            graph_show_factions: false,
            tr_sort: DashboardSortState::default(),
            nc_sort: DashboardSortState::default(),
            vs_sort: DashboardSortState::default(),
            pop_history: vec![0; 100],
            tr_history: vec![0; 100],
            nc_history: vec![0; 100],
            vs_history: vec![0; 100],
            last_history_sample: Instant::now(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DashboardSortColumn {
    Player,
    K,
    Kpm,
    D,
    A,
    Kd,
    Kda,
}

#[derive(Debug, Clone, Copy)]
pub struct DashboardSortState {
    pub column: DashboardSortColumn,
    pub ascending: bool,
}

impl Default for DashboardSortState {
    fn default() -> Self {
        Self {
            column: DashboardSortColumn::K,
            ascending: false,
        }
    }
}

#[derive(Default)]
pub struct TwitchTabState {
    pub ignore_users_input: String,
    pub silence_sound_input: String,
    pub status: Option<String>,
    pub connected: bool,
}

pub struct ObsTabState {
    pub service_enabled: bool,
    pub http_port: u16,
    pub ws_port: u16,
    pub http_port_input: String,
    pub ws_port_input: String,
    pub copy_feedback: Option<String>,
}

impl Default for ObsTabState {
    fn default() -> Self {
        Self {
            service_enabled: false,
            http_port: 31337,
            ws_port: 31338,
            http_port_input: "31337".to_owned(),
            ws_port_input: "31338".to_owned(),
            copy_feedback: None,
        }
    }
}

pub struct CharactersTabState {
    pub query: String,
    pub status: Option<String>,
    pub search_result: Option<Receiver<Result<CharacterEntry, String>>>,
    pub selected_tab: CharactersSubTab,
    pub selected_character: Option<CharacterEntry>,
    pub selected_profile: Option<PlayerCacheEntry>,
}

impl Default for CharactersTabState {
    fn default() -> Self {
        Self {
            query: String::new(),
            status: None,
            search_result: None,
            selected_tab: CharactersSubTab::Overview,
            selected_character: None,
            selected_profile: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum CharactersSubTab {
    #[default]
    Overview,
    WeaponStats,
    Directives,
}

#[derive(Default)]
pub struct EventsTabState {
    pub selected_category: String,      // e.g. "Kill"
    pub selected_event: Option<String>, // e.g. "Kill Infil"
    pub slot_names: Vec<String>,
    pub active_slot: usize,
    pub rename_input: String,
    pub status: Option<String>,
    pub slot_profiles: HashMap<String, HashMap<String, LegacyVisualOverride>>,
}

pub struct IdentityTabState {
    pub new_char_input: String,
    pub search_status: Option<String>,
    pub search_result: Option<Receiver<Result<CharacterEntry, String>>>,
    pub debug_overlay: bool, // Local state for debug toggle if needed, or stick to app state
}

impl Default for IdentityTabState {
    fn default() -> Self {
        Self {
            new_char_input: String::new(),
            search_status: None,
            search_result: None,
            debug_overlay: false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TopLevelTab {
    #[default]
    Dashboard,
    Launcher,
    Characters,
    Overlay,
    Settings,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LauncherTab {
    #[default]
    Identity,
    Events,
    Killstreak,
    Crosshair,
    Stats,
    Killfeed,
    Voice,
    Twitch,
    Obs,
}

impl LauncherTab {
    pub fn label(&self) -> &'static str {
        match self {
            LauncherTab::Identity => "Identity",
            LauncherTab::Events => "Events",
            LauncherTab::Killstreak => "Killstreak",
            LauncherTab::Crosshair => "Crosshair",
            LauncherTab::Stats => "Stats",
            LauncherTab::Killfeed => "Killfeed",
            LauncherTab::Voice => "Voice",
            LauncherTab::Twitch => "Twitch",
            LauncherTab::Obs => "OBS / Stream",
        }
    }
}
