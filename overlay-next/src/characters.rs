use std::{fs, path::Path};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CharacterEntry {
    pub character_id: String,
    pub name: String,
    pub world_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct PersistedCharacters {
    pub active_character_id: Option<String>,
    pub entries: Vec<CharacterEntry>,
}

pub fn load_characters(path: &Path) -> Result<PersistedCharacters> {
    if !path.exists() {
        return Ok(PersistedCharacters::default());
    }
    let text = fs::read_to_string(path)
        .with_context(|| format!("failed reading characters at {}", path.display()))?;
    let parsed = serde_json::from_str::<PersistedCharacters>(&text)
        .with_context(|| format!("invalid characters json at {}", path.display()))?;
    Ok(parsed)
}

pub fn save_characters(path: &Path, data: &PersistedCharacters) -> Result<()> {
    let payload = serde_json::to_string_pretty(data).context("failed serializing characters")?;
    fs::write(path, payload)
        .with_context(|| format!("failed writing characters at {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{CharacterEntry, PersistedCharacters};

    #[test]
    fn defaults_are_empty() {
        let data = PersistedCharacters::default();
        assert!(data.entries.is_empty());
        assert!(data.active_character_id.is_none());
    }

    #[test]
    fn character_entry_roundtrip_shape() {
        let entry = CharacterEntry {
            character_id: "54281234567890123".to_owned(),
            name: "AhornFPS".to_owned(),
            world_id: Some("17".to_owned()),
        };
        let raw = serde_json::to_string(&entry).expect("serialize");
        let parsed: CharacterEntry = serde_json::from_str(&raw).expect("deserialize");
        assert_eq!(parsed.character_id, "54281234567890123");
        assert_eq!(parsed.name, "AhornFPS");
        assert_eq!(parsed.world_id.as_deref(), Some("17"));
    }
}
