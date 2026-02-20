use std::{fs, path::Path};

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PersistedSessionStats {
    pub kd: f32,
    pub kpm: f32,
    pub kph: f32,
    pub hsr: f32,
    pub dhsr: f32,
    pub kills: u32,
    pub deaths: u32,
    pub effective_deaths: u32,
    pub session_time_label: String,
    pub session_seconds: u64,
    pub last_update: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PersistedLayoutState {
    pub feed_origin: [f32; 2],
    pub feed_size: [f32; 2],
    pub stats_origin: [f32; 2],
    pub stats_size: [f32; 2],
    pub stats_offset: [f32; 2],
    pub stats_padding: f32,
    pub streak_pos: [f32; 2],
    pub streak_bg_size: [f32; 2],
    pub crosshair_pos: Option<[f32; 2]>,
    pub crosshair_size: f32,
}

impl Default for PersistedLayoutState {
    fn default() -> Self {
        Self {
            feed_origin: [40.0, 140.0],
            feed_size: [600.0, 550.0],
            stats_origin: [40.0, 60.0],
            stats_size: [450.0, 60.0],
            stats_offset: [0.0, 0.0],
            stats_padding: 8.0,
            streak_pos: [100.0, 100.0],
            streak_bg_size: [220.0, 220.0],
            crosshair_pos: None,
            crosshair_size: 64.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PersistedState {
    pub session: Option<PersistedSessionStats>,
    pub feed: Vec<String>,
    pub chat: Vec<String>,
    pub layout: Option<PersistedLayoutState>,
    pub overlay_visible: bool,
    pub scifi_enabled: bool,
}

impl Default for PersistedState {
    fn default() -> Self {
        Self {
            session: None,
            feed: Vec::new(),
            chat: Vec::new(),
            layout: None,
            overlay_visible: true,
            scifi_enabled: true,
        }
    }
}

pub fn load_state(path: &Path) -> Result<PersistedState> {
    if !path.exists() {
        return Ok(PersistedState::default());
    }
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed reading runtime state at {}", path.display()))?;
    let parsed = serde_json::from_str::<PersistedState>(&text)
        .with_context(|| format!("invalid runtime state json at {}", path.display()))?;
    Ok(parsed)
}

pub fn save_state(path: &Path, state: &PersistedState) -> Result<()> {
    let payload =
        serde_json::to_string_pretty(state).context("failed serializing runtime state")?;
    fs::write(path, payload)
        .with_context(|| format!("failed writing runtime state at {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{PersistedLayoutState, PersistedState};

    #[test]
    fn layout_defaults_match_overlay_defaults() {
        let layout = PersistedLayoutState::default();
        assert_eq!(layout.feed_origin, [40.0, 140.0]);
        assert_eq!(layout.feed_size, [600.0, 550.0]);
        assert_eq!(layout.stats_origin, [40.0, 60.0]);
        assert_eq!(layout.stats_size, [450.0, 60.0]);
        assert_eq!(layout.streak_pos, [100.0, 100.0]);
        assert_eq!(layout.crosshair_size, 64.0);
    }

    #[test]
    fn persisted_state_defaults_to_visible_scifi_enabled() {
        let state = PersistedState::default();
        assert!(state.overlay_visible);
        assert!(state.scifi_enabled);
    }
}
