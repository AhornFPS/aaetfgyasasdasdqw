use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum OverlayEvent {
    Kill {
        victim: String,
        weapon: Option<String>,
        headshot: bool,
        streak: u32,
        at: DateTime<Utc>,
    },
    Death {
        killer: String,
        at: DateTime<Utc>,
    },
    SessionSnapshot {
        kd: f32,
        kpm: f32,
        hsr: f32,
        kills: u32,
        deaths: u32,
        at: DateTime<Utc>,
    },
    SessionRaw {
        #[serde(default)]
        k: u32,
        #[serde(default)]
        d: u32,
        #[serde(default)]
        hs: u32,
        #[serde(default)]
        hsrkill: u32,
        #[serde(default)]
        dhs: u32,
        #[serde(default)]
        dhs_eligible: u32,
        #[serde(default)]
        start: f64,
        #[serde(default)]
        acc_t: f64,
        #[serde(default)]
        revives_received: u32,
        #[serde(default)]
        kd_mode_revive: Option<bool>,
        #[serde(default)]
        at: Option<DateTime<Utc>>,
    },
    TwitchMessage {
        author: String,
        text: String,
        #[serde(default)]
        color: Option<String>,
        at: DateTime<Utc>,
    },
}

#[derive(Debug, Clone)]
pub struct FeedItem {
    pub label: String,
    pub at: DateTime<Utc>,
}

impl FeedItem {
    pub fn from_event(event: &OverlayEvent) -> Self {
        match event {
            OverlayEvent::Kill {
                victim,
                weapon,
                headshot,
                streak,
                at,
            } => {
                let mut label = format!("KILL {victim}");
                if let Some(weapon) = weapon {
                    label.push_str(&format!(" [{weapon}]"));
                }
                if *headshot {
                    label.push_str(" HS");
                }
                if *streak > 1 {
                    label.push_str(&format!(" x{streak}"));
                }
                Self { label, at: *at }
            }
            OverlayEvent::Death { killer, at } => Self {
                label: format!("DEATH killed by {killer}"),
                at: *at,
            },
            OverlayEvent::SessionSnapshot {
                kd,
                kpm,
                hsr,
                kills,
                deaths,
                at,
            } => Self {
                label: format!(
                    "SESSION K/D {kd:.2} | KPM {kpm:.2} | HSR {hsr:.1}% | {kills}/{deaths}"
                ),
                at: *at,
            },
            OverlayEvent::SessionRaw {
                k,
                d,
                hs,
                hsrkill,
                at,
                ..
            } => {
                let hsr_base = if *hsrkill > 0 { *hsrkill } else { *k };
                let hsr = if hsr_base > 0 {
                    (*hs as f32 / hsr_base as f32) * 100.0
                } else {
                    0.0
                };
                Self {
                    label: format!("SESSION RAW K {} D {} HSR {:.1}%", k, d, hsr),
                    at: at.unwrap_or_else(Utc::now),
                }
            }
            OverlayEvent::TwitchMessage {
                author, text, at, ..
            } => Self {
                label: format!("TWITCH {author}: {text}"),
                at: *at,
            },
        }
    }
}
