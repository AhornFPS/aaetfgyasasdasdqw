use std::{collections::HashMap, path::PathBuf};

use anyhow::{Context, Result};
use rusqlite::{params, Connection, OptionalExtension};

use crate::characters::CharacterEntry;

#[derive(Debug, Clone, Default)]
pub struct PlayerCacheEntry {
    pub character_id: String,
    pub name: String,
    pub world_id: Option<String>,
    pub faction_id: Option<i64>,
    pub outfit_tag: Option<String>,
    pub battle_rank: Option<i64>,
}

#[derive(Debug, Clone, Default)]
pub struct PlayerCacheMaps {
    pub names: HashMap<String, String>,
    pub outfits: HashMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct CharacterDatabase {
    path: PathBuf,
}

impl CharacterDatabase {
    pub fn open(path: PathBuf) -> Result<Self> {
        let db = Self { path };
        db.init_db()?;
        Ok(db)
    }

    pub fn open_default() -> Result<Self> {
        let base = dirs::config_dir()
            .context("unable to locate OS config directory for character db")?
            .join("better-planetside-overlay-next");
        std::fs::create_dir_all(&base)
            .with_context(|| format!("failed creating db dir at {}", base.display()))?;
        Self::open(base.join("ps2_master.db"))
    }

    fn conn(&self) -> Result<Connection> {
        Connection::open(&self.path)
            .with_context(|| format!("failed opening sqlite db at {}", self.path.display()))
    }

    fn init_db(&self) -> Result<()> {
        let conn = self.conn()?;
        conn.execute_batch(
            r#"
CREATE TABLE IF NOT EXISTS player_cache (
    character_id TEXT PRIMARY KEY,
    name TEXT,
    name_lower TEXT,
    faction_id INTEGER,
    world_id INTEGER,
    outfit_tag TEXT,
    battle_rank INTEGER,
    created_date TEXT,
    last_login TEXT,
    kills INTEGER,
    deaths INTEGER,
    score INTEGER,
    playtime INTEGER,
    m30_kills INTEGER,
    m30_deaths INTEGER,
    m30_score INTEGER,
    m30_time INTEGER
);
CREATE TABLE IF NOT EXISTS my_chars (
    character_id TEXT PRIMARY KEY,
    name TEXT
);
CREATE INDEX IF NOT EXISTS idx_player_cache_name_lower ON player_cache(name_lower);
"#,
        )
        .context("failed creating character tables")?;
        Ok(())
    }

    pub fn load_my_chars(&self) -> Result<Vec<CharacterEntry>> {
        let conn = self.conn()?;
        let mut stmt = conn
            .prepare(
                r#"
SELECT m.character_id, m.name, p.world_id
FROM my_chars m
LEFT JOIN player_cache p ON p.character_id = m.character_id
ORDER BY m.name COLLATE NOCASE
"#,
            )
            .context("failed preparing my_chars query")?;
        let rows = stmt
            .query_map([], |row| {
                let character_id: String = row.get(0)?;
                let name: String = row.get(1)?;
                let world_id_i64: Option<i64> = row.get(2)?;
                Ok(CharacterEntry {
                    character_id,
                    name,
                    world_id: world_id_i64.map(|v| v.to_string()),
                })
            })
            .context("failed querying my_chars")?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row.context("failed decoding my_chars row")?);
        }
        Ok(out)
    }

    pub fn load_my_chars_map(&self) -> Result<HashMap<String, String>> {
        let conn = self.conn()?;
        let mut stmt = conn
            .prepare("SELECT name, character_id FROM my_chars")
            .context("failed preparing my_chars map query")?;
        let rows = stmt
            .query_map([], |row| {
                let name: String = row.get(0)?;
                let character_id: String = row.get(1)?;
                Ok((name, character_id))
            })
            .context("failed querying my_chars map")?;
        let mut out = HashMap::new();
        for row in rows {
            let (name, character_id) = row.context("failed decoding my_chars map row")?;
            out.insert(name, character_id);
        }
        Ok(out)
    }

    pub fn sync_my_chars(&self, entries: &[CharacterEntry]) -> Result<()> {
        let mut conn = self.conn()?;
        let tx = conn
            .transaction()
            .context("failed starting sqlite transaction")?;
        tx.execute("DELETE FROM my_chars", [])
            .context("failed clearing my_chars table")?;
        for entry in entries {
            tx.execute(
                "INSERT OR REPLACE INTO my_chars (name, character_id) VALUES (?, ?)",
                params![entry.name, entry.character_id],
            )
            .with_context(|| format!("failed upserting my_char {}", entry.name))?;
            tx.execute(
                "INSERT OR IGNORE INTO player_cache (character_id, name, name_lower, world_id) VALUES (?, ?, ?, ?)",
                params![
                    entry.character_id,
                    entry.name,
                    entry.name.to_ascii_lowercase(),
                    parse_world_id(entry.world_id.as_deref()),
                ],
            )
            .with_context(|| format!("failed ensuring player_cache row for {}", entry.name))?;
        }
        tx.commit().context("failed committing my_chars sync")?;
        Ok(())
    }

    pub fn save_char_to_db(
        &self,
        cid: &str,
        name: &str,
        world_id: Option<&str>,
        faction_id: Option<i64>,
        rank: Option<i64>,
        outfit_tag: Option<&str>,
    ) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT OR REPLACE INTO player_cache (character_id, name, name_lower, faction_id, battle_rank, outfit_tag, world_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![
                cid,
                name,
                name.to_ascii_lowercase(),
                faction_id,
                rank,
                sanitize_optional_text(outfit_tag),
                parse_world_id(world_id),
            ],
        )
        .with_context(|| format!("failed upserting player_cache for {cid}"))?;
        conn.execute(
            "INSERT OR REPLACE INTO my_chars (name, character_id) VALUES (?, ?)",
            params![name, cid],
        )
        .with_context(|| format!("failed upserting my_chars for {name}"))?;
        Ok(())
    }

    pub fn remove_my_char(&self, name: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute("DELETE FROM my_chars WHERE name = ?1", params![name])
            .with_context(|| format!("failed deleting my_char by name {name}"))?;
        Ok(())
    }

    pub fn upsert_player_cache_entry(&self, entry: &PlayerCacheEntry) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT OR REPLACE INTO player_cache (character_id, name, name_lower, faction_id, battle_rank, outfit_tag, world_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![
                entry.character_id,
                entry.name,
                entry.name.to_ascii_lowercase(),
                entry.faction_id,
                entry.battle_rank,
                sanitize_optional_text(entry.outfit_tag.as_deref()),
                parse_world_id(entry.world_id.as_deref()),
            ],
        )
        .with_context(|| format!("failed upserting player_cache for {}", entry.character_id))?;
        Ok(())
    }

    pub fn load_player_cache(&self) -> Result<PlayerCacheMaps> {
        let conn = self.conn()?;
        let mut stmt = conn
            .prepare("SELECT character_id, name, outfit_tag FROM player_cache")
            .context("failed preparing player_cache query")?;
        let rows = stmt
            .query_map([], |row| {
                let character_id: String = row.get(0)?;
                let name: Option<String> = row.get(1)?;
                let outfit_tag: Option<String> = row.get(2)?;
                Ok((character_id, name, outfit_tag))
            })
            .context("failed querying player_cache")?;

        let mut maps = PlayerCacheMaps::default();
        for row in rows {
            let (character_id, name, outfit_tag) =
                row.context("failed decoding player_cache row")?;
            if let Some(name) = name
                .map(|value| value.trim().to_owned())
                .filter(|value| !value.is_empty())
            {
                maps.names.insert(character_id.clone(), name);
            }
            if let Some(tag) = outfit_tag
                .map(|value| value.trim().to_owned())
                .filter(|value| !value.is_empty())
            {
                maps.outfits.insert(character_id, tag);
            }
        }
        Ok(maps)
    }

    pub fn find_player_cache_entry(&self, character_id: &str) -> Result<Option<PlayerCacheEntry>> {
        let conn = self.conn()?;
        conn.query_row(
            r#"
SELECT character_id, name, world_id, faction_id, outfit_tag, battle_rank
FROM player_cache
WHERE character_id = ?1
LIMIT 1
"#,
            params![character_id],
            |row| {
                let character_id: String = row.get(0)?;
                let name: Option<String> = row.get(1)?;
                let world_id: Option<i64> = row.get(2)?;
                let faction_id: Option<i64> = row.get(3)?;
                let outfit_tag: Option<String> = row.get(4)?;
                let battle_rank: Option<i64> = row.get(5)?;
                Ok(PlayerCacheEntry {
                    character_id,
                    name: name.unwrap_or_default(),
                    world_id: world_id.map(|value| value.to_string()),
                    faction_id,
                    outfit_tag: sanitize_optional_text(outfit_tag.as_deref()),
                    battle_rank,
                })
            },
        )
        .optional()
        .context("failed looking up cached player profile")
    }

    pub fn count_player_cache(&self) -> Result<u64> {
        let conn = self.conn()?;
        conn.query_row("SELECT COUNT(*) FROM player_cache", [], |row| row.get(0))
            .context("failed counting player_cache rows")
    }

    pub fn find_player_name(&self, character_id: &str) -> Result<Option<String>> {
        let conn = self.conn()?;
        conn.query_row(
            "SELECT name FROM player_cache WHERE character_id=?1",
            params![character_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .context("failed looking up player name")
    }

    pub fn find_character_by_name(&self, name: &str) -> Result<Option<CharacterEntry>> {
        let needle = name.trim().to_ascii_lowercase();
        if needle.is_empty() {
            return Ok(None);
        }
        let conn = self.conn()?;
        conn.query_row(
            r#"
SELECT character_id, name, world_id
FROM player_cache
WHERE name_lower = ?1
LIMIT 1
"#,
            params![needle],
            |row| {
                let character_id: String = row.get(0)?;
                let resolved_name: String = row.get(1)?;
                let world_id: Option<i64> = row.get(2)?;
                Ok(CharacterEntry {
                    character_id,
                    name: resolved_name,
                    world_id: world_id.map(|v| v.to_string()),
                })
            },
        )
        .optional()
        .context("failed looking up cached character by name")
    }
}

fn parse_world_id(value: Option<&str>) -> Option<i64> {
    value
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .and_then(|v| v.parse::<i64>().ok())
}

fn sanitize_optional_text(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(ToOwned::to_owned)
}
