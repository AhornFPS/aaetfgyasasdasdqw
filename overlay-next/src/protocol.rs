use anyhow::{anyhow, Result};
use serde::Deserialize;
use serde_json::Value;

use crate::events::OverlayEvent;

#[derive(Debug, Clone, Deserialize)]
pub struct LegacyEnvelope {
    pub category: String,
    #[serde(default)]
    pub data: Value,
}

#[derive(Debug, Clone)]
pub enum IncomingMessage {
    OverlayEvent(OverlayEvent),
    Legacy(LegacyEnvelope),
}

pub fn parse_incoming_message(text: &str) -> Result<IncomingMessage> {
    if let Ok(event) = serde_json::from_str::<OverlayEvent>(text) {
        return Ok(IncomingMessage::OverlayEvent(event));
    }

    if let Ok(legacy) = serde_json::from_str::<LegacyEnvelope>(text) {
        return Ok(IncomingMessage::Legacy(legacy));
    }

    Err(anyhow!(
        "payload did not match overlay event or legacy envelope"
    ))
}

#[cfg(test)]
mod tests {
    use super::{parse_incoming_message, IncomingMessage};

    #[test]
    fn parses_overlay_event_payload() {
        let payload = r#"{
            "type":"kill",
            "victim":"EnemyHeavy",
            "weapon":"Orion VS54",
            "headshot":true,
            "streak":3,
            "at":"2026-02-18T00:00:00Z"
        }"#;

        let parsed = parse_incoming_message(payload).expect("expected overlay event parse");
        assert!(matches!(parsed, IncomingMessage::OverlayEvent(_)));
    }

    #[test]
    fn parses_overlay_session_raw_payload() {
        let payload = r#"{
            "type":"session_raw",
            "k":15,
            "d":6,
            "hs":4,
            "hsrkill":10,
            "dhs":1,
            "dhs_eligible":5,
            "start":1700000000.0,
            "acc_t":120.0,
            "revives_received":1,
            "kd_mode_revive":true
        }"#;

        let parsed = parse_incoming_message(payload).expect("expected overlay event parse");
        assert!(matches!(parsed, IncomingMessage::OverlayEvent(_)));
    }

    #[test]
    fn parses_legacy_payload() {
        let payload = r#"{
            "category":"feed",
            "data":{"html":"<b>Kill</b>","x":100,"y":200}
        }"#;

        let parsed = parse_incoming_message(payload).expect("expected legacy parse");
        match parsed {
            IncomingMessage::Legacy(env) => {
                assert_eq!(env.category, "feed");
                assert_eq!(env.data["x"], 100);
            }
            _ => panic!("expected legacy envelope"),
        }
    }

    #[test]
    fn rejects_unrecognized_payload() {
        let payload = r#"{"hello":"world"}"#;
        let parsed = parse_incoming_message(payload);
        assert!(parsed.is_err());
    }
}
