use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionRawStats {
    #[serde(default)]
    pub k: u32,
    #[serde(default)]
    pub d: u32,
    #[serde(default)]
    pub hs: u32,
    #[serde(default)]
    pub hsrkill: u32,
    #[serde(default)]
    pub dhs: u32,
    #[serde(default)]
    pub dhs_eligible: u32,
    #[serde(default)]
    pub start: f64,
    #[serde(default)]
    pub acc_t: f64,
    #[serde(default)]
    pub revives_received: u32,
    #[serde(default)]
    pub kd_mode_revive: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct SessionDerivedStats {
    pub kd: f32,
    pub kpm: f32,
    pub kph: f32,
    pub hsr: f32,
    pub dhsr: f32,
    pub kills: u32,
    pub deaths: u32,
    pub effective_deaths: u32,
    pub session_seconds: u64,
    pub session_time_label: String,
}

pub fn derive_session_stats(
    raw: &SessionRawStats,
    kd_mode_revive_default: bool,
    now: DateTime<Utc>,
) -> SessionDerivedStats {
    let kills = raw.k;
    let deaths = raw.d;
    let revives = raw.revives_received;

    let kd_mode_revive = raw.kd_mode_revive.unwrap_or(kd_mode_revive_default);
    let effective_deaths = if kd_mode_revive {
        deaths.saturating_sub(revives)
    } else {
        deaths
    };
    let kd = kills as f32 / effective_deaths.max(1) as f32;

    let hsr_base = if raw.hsrkill > 0 { raw.hsrkill } else { kills };
    let hsr = if hsr_base > 0 {
        (raw.hs as f32 / hsr_base as f32) * 100.0
    } else {
        0.0
    };

    let dhsr_base = if raw.dhs_eligible > 0 {
        raw.dhs_eligible
    } else {
        deaths
    };
    let dhsr = (raw.dhs as f32 / dhsr_base.max(1) as f32) * 100.0;

    let now_ts = now.timestamp() as f64;
    let total_sec = if raw.start > 0.0 {
        (raw.acc_t + (now_ts - raw.start)).max(0.0)
    } else {
        raw.acc_t.max(0.0)
    };
    let duration_min = total_sec / 60.0;
    let kpm = if duration_min > 0.0 {
        kills as f32 / duration_min as f32
    } else {
        0.0
    };
    let kph = kpm * 60.0;
    let session_seconds = total_sec.floor() as u64;
    let session_time_label = format_session_time(session_seconds);

    SessionDerivedStats {
        kd,
        kpm,
        kph,
        hsr,
        dhsr,
        kills,
        deaths,
        effective_deaths,
        session_seconds,
        session_time_label,
    }
}

fn format_session_time(total_seconds: u64) -> String {
    let seconds = total_seconds % 60;
    let total_minutes = total_seconds / 60;
    let minutes = total_minutes % 60;
    let hours = total_minutes / 60;
    if hours > 0 {
        format!("{hours:02}:{minutes:02}:{seconds:02}")
    } else {
        format!("{minutes:02}:{seconds:02}")
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::{derive_session_stats, SessionRawStats};

    #[test]
    fn derives_expected_metrics_with_revive_mode() {
        let raw = SessionRawStats {
            k: 30,
            d: 12,
            hs: 15,
            hsrkill: 0,
            dhs: 2,
            dhs_eligible: 8,
            start: 1_700_000_000.0,
            acc_t: 600.0,
            revives_received: 3,
            kd_mode_revive: Some(true),
        };
        let now = chrono::Utc.timestamp_opt(1_700_000_600, 0).unwrap();
        let derived = derive_session_stats(&raw, true, now);

        assert_eq!(derived.effective_deaths, 9);
        assert!((derived.kd - 3.3333).abs() < 0.01);
        assert!((derived.kpm - 1.5).abs() < 0.01);
        assert!((derived.kph - 90.0).abs() < 0.01);
        assert!((derived.hsr - 50.0).abs() < 0.01);
        assert!((derived.dhsr - 25.0).abs() < 0.01);
        assert_eq!(derived.session_time_label, "20:00");
    }

    #[test]
    fn derives_time_with_hours_format() {
        let raw = SessionRawStats {
            k: 1,
            d: 1,
            hs: 0,
            hsrkill: 0,
            dhs: 0,
            dhs_eligible: 0,
            start: 0.0,
            acc_t: 3_721.0,
            revives_received: 0,
            kd_mode_revive: None,
        };
        let now = chrono::Utc.timestamp_opt(1_700_000_000, 0).unwrap();
        let derived = derive_session_stats(&raw, true, now);
        assert_eq!(derived.session_time_label, "01:02:01");
    }
}
