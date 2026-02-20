use std::{
    collections::{HashMap, HashSet, VecDeque},
    fs,
    path::PathBuf,
    time::Duration,
};

use chrono::{TimeZone, Utc};
use crossbeam_channel::Sender;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::task::JoinHandle;
use tokio::time::sleep;
use tokio_tungstenite::connect_async;
use tracing::{info, warn};

use crate::{
    characters::CharacterEntry,
    dior_db::{CharacterDatabase, PlayerCacheEntry},
    events::OverlayEvent,
    protocol::{IncomingMessage, LegacyEnvelope},
};

const REVIVE_EXPERIENCE_IDS: &[&str] = &["7", "53"];
const ASSIST_EXPERIENCE_IDS: &[&str] = &["2", "3", "371", "372"];
const GET_ROADKILLED_EXPERIENCE_ID: &str = "26";
const EXPERIENCE_EVENT_IDS: &[(&str, &[&str])] = &[
    ("Heal", &["4", "51"]),
    ("Resupply", &["34", "55"]),
    ("Point Control", &["272", "556", "557"]),
    ("Sunderer Spawn", &["233"]),
    ("Squad Spawn", &["56", "220"]),
    ("Base Capture", &["19", "598"]),
    ("RoadKill", &["26"]),
    ("Break Construction", &["604", "616", "628"]),
    ("Transport Assist", &["201", "230", "268", "350", "664"]),
    ("Domination", &["10"]),
    ("Revenge", &["11"]),
    ("Killstreak Stop", &["8"]),
    ("Bounty Kill", &["593"]),
    (
        "Gunner Kill",
        &[
            "373", "314", "146", "148", "149", "150", "154", "155", "515", "681",
        ],
    ),
];
const HSR_WEAPON_CATEGORIES: &[&str] = &[
    "AI MAX (Left)",
    "AI MAX (Right)",
    "Amphibious Rifle",
    "Anti-Materiel Rifle",
    "Assault Rifle",
    "Carbine",
    "Heavy Weapon",
    "Hybrid Rifle",
    "LMG",
    "Pistol",
    "Scout Rifle",
    "Shotgun",
    "SMG",
    "Sniper Rifle",
    "Amphibious Sidearm",
    "Knife",
];

#[derive(Debug, Clone, Default)]
struct VehicleEventMaps {
    gunner_kill: HashMap<String, String>,
    vehicle_kill: HashMap<String, String>,
    repair_ids: HashSet<String>,
}

impl VehicleEventMaps {
    fn is_empty(&self) -> bool {
        self.gunner_kill.is_empty() && self.vehicle_kill.is_empty() && self.repair_ids.is_empty()
    }
}

#[derive(Debug, Clone, Default)]
struct FacilityMap {
    names: HashMap<String, String>,
}

impl FacilityMap {
    fn is_empty(&self) -> bool {
        self.names.is_empty()
    }
}

#[derive(Debug, Clone, Default)]
struct EventCatalog {
    templates: HashMap<String, EventTemplate>,
    canonical_templates: HashMap<String, EventTemplate>,
}

#[derive(Debug, Clone)]
struct StreakTemplate {
    active: bool,
    bg_filename: Option<String>,
    x: f32,
    y: f32,
    tx: f32,
    ty: f32,
    scale: f32,
    font_size: f32,
    color: String,
    bold: bool,
    anim_active: bool,
    anim_speed: f32,
    streak_glow: bool,
    glow_color: String,
    show_knives: bool,
    knife_size: f32,
    knife_tr: Option<String>,
    knife_nc: Option<String>,
    knife_vs: Option<String>,
    knife_nso: Option<String>,
    custom_path: Vec<(f32, f32)>,
    bg_width: f32,
    bg_height: f32,
    knives_per_ring: u32,
    ring_spacing: f32,
}

impl Default for StreakTemplate {
    fn default() -> Self {
        Self {
            active: true,
            bg_filename: None,
            x: 120.0,
            y: 120.0,
            tx: 0.0,
            ty: 0.0,
            scale: 1.0,
            font_size: 28.0,
            color: "#ffffff".to_owned(),
            bold: false,
            anim_active: true,
            anim_speed: 50.0,
            streak_glow: true,
            glow_color: "#00f2ff".to_owned(),
            show_knives: true,
            knife_size: 90.0,
            knife_tr: None,
            knife_nc: None,
            knife_vs: None,
            knife_nso: None,
            custom_path: Vec::new(),
            bg_width: 220.0,
            bg_height: 220.0,
            knives_per_ring: 50,
            ring_spacing: 22.0,
        }
    }
}

#[derive(Debug, Clone)]
struct EventTemplate {
    images: Vec<String>,
    sounds: Vec<String>,
    sound_volume: f32,
    duration_ms: u64,
    x: f32,
    y: f32,
    scale: f32,
    play_duplicate: bool,
    impact: bool,
}

impl EventCatalog {
    fn template(&self, event_name: &str) -> Option<&EventTemplate> {
        let key = event_name.to_ascii_lowercase();
        self.templates.get(&key).or_else(|| {
            let canonical = canonical_event_key(event_name);
            self.canonical_templates.get(&canonical).or_else(|| {
                canonical_event_aliases(&canonical)
                    .iter()
                    .find_map(|alias| self.canonical_templates.get(*alias))
            })
        })
    }

    fn has_specific_config(&self, event_name: &str) -> bool {
        self.template(event_name)
            .map(|t| !t.images.is_empty() || !t.sounds.is_empty())
            .unwrap_or(false)
    }
}

#[derive(Debug)]
struct WeaponClassifier {
    service_id: String,
    enabled: bool,
    cache: HashMap<String, Option<String>>,
    hsr_cache: HashMap<String, bool>,
    cache_path: Option<PathBuf>,
    hsr_cache_path: Option<PathBuf>,
    dirty_inserts: usize,
    client: Option<reqwest::blocking::Client>,
}

#[derive(Debug, Clone, Default)]
struct WeaponLookup {
    event_name: Option<String>,
    hsr_eligible: bool,
}

impl WeaponClassifier {
    fn new(service_id: &str, enabled: bool) -> Self {
        let service_id = service_id.trim().to_owned();
        let cache_path = if enabled {
            locate_weapon_cache_path()
        } else {
            None
        };
        let hsr_cache_path = if enabled {
            locate_weapon_hsr_cache_path()
        } else {
            None
        };
        let mut cache = HashMap::new();
        let mut hsr_cache = HashMap::new();
        if let Some(path) = &cache_path {
            if let Ok(text) = fs::read_to_string(path) {
                if let Ok(raw) = serde_json::from_str::<HashMap<String, String>>(&text) {
                    for (weapon_id, event_name) in raw {
                        cache.insert(weapon_id, Some(event_name));
                    }
                }
            }
        }
        if let Some(path) = &hsr_cache_path {
            if let Ok(text) = fs::read_to_string(path) {
                if let Ok(raw) = serde_json::from_str::<HashMap<String, bool>>(&text) {
                    hsr_cache = raw;
                }
            }
        }
        let client = if !enabled || service_id.is_empty() {
            None
        } else {
            reqwest::blocking::Client::builder()
                .timeout(Duration::from_millis(900))
                .build()
                .ok()
        };
        Self {
            service_id,
            enabled,
            cache,
            hsr_cache,
            cache_path,
            hsr_cache_path,
            dirty_inserts: 0,
            client,
        }
    }

    fn lookup(&mut self, weapon_id: &str) -> WeaponLookup {
        if let Some(cached) = self.cache.get(weapon_id).cloned() {
            if let Some(hsr_eligible) = self.hsr_cache.get(weapon_id).copied() {
                return WeaponLookup {
                    event_name: cached,
                    hsr_eligible,
                };
            }
            let fetched = self.fetch_weapon_lookup(weapon_id);
            let had_event = cached.is_some();
            let event_name = cached.or(fetched.event_name);
            self.cache.insert(weapon_id.to_owned(), event_name.clone());
            self.hsr_cache
                .insert(weapon_id.to_owned(), fetched.hsr_eligible);
            if !had_event && event_name.is_some() {
                self.dirty_inserts = self.dirty_inserts.saturating_add(1);
                if self.dirty_inserts >= 8 {
                    self.persist_cache();
                    self.dirty_inserts = 0;
                }
            }
            return WeaponLookup {
                event_name,
                hsr_eligible: fetched.hsr_eligible,
            };
        }
        let detected = self.fetch_weapon_lookup(weapon_id);
        self.cache
            .insert(weapon_id.to_owned(), detected.event_name.clone());
        self.hsr_cache
            .insert(weapon_id.to_owned(), detected.hsr_eligible);
        if detected.event_name.is_some() {
            self.dirty_inserts = self.dirty_inserts.saturating_add(1);
            if self.dirty_inserts >= 8 {
                self.persist_cache();
                self.dirty_inserts = 0;
            }
        }
        detected
    }

    fn fetch_weapon_lookup(&self, weapon_id: &str) -> WeaponLookup {
        if !self.enabled {
            return WeaponLookup::default();
        }
        if weapon_id.trim().is_empty() || weapon_id == "0" {
            return WeaponLookup::default();
        }
        let Some(client) = self.client.as_ref() else {
            return WeaponLookup::default();
        };
        let url = format!(
            "https://census.daybreakgames.com/{}/get/ps2:v2/item?item_id={weapon_id}&c:resolve=item_type&c:show=item_id,name.en,item_type_id",
            self.service_id
        );
        let Some(response) = client.get(url).send().ok() else {
            return WeaponLookup::default();
        };
        let Some(root) = response.json::<Value>().ok() else {
            return WeaponLookup::default();
        };
        parse_weapon_lookup_payload(&root)
    }

    fn persist_cache(&self) {
        if !self.enabled {
            return;
        }
        let Some(path) = &self.cache_path else {
            return;
        };
        let serializable: HashMap<String, String> = self
            .cache
            .iter()
            .filter_map(|(weapon_id, event_name)| {
                event_name
                    .as_ref()
                    .map(|event_name| (weapon_id.clone(), event_name.clone()))
            })
            .collect();
        if serializable.is_empty() {
            return;
        }
        if let Ok(text) = serde_json::to_string_pretty(&serializable) {
            if let Err(err) = fs::write(path, text) {
                warn!(?err, path = %path.display(), "failed writing weapon classifier cache");
            }
        }
        if let Some(hsr_path) = &self.hsr_cache_path {
            if let Ok(text) = serde_json::to_string_pretty(&self.hsr_cache) {
                if let Err(err) = fs::write(hsr_path, text) {
                    warn!(
                        ?err,
                        path = %hsr_path.display(),
                        "failed writing weapon hsr classifier cache"
                    );
                }
            }
        }
    }
}

#[derive(Debug)]
struct CharacterResolver {
    service_id: String,
    memo: HashMap<String, PlayerCacheEntry>,
    db: Option<CharacterDatabase>,
    client: Option<reqwest::blocking::Client>,
}

impl CharacterResolver {
    fn new(service_id: &str) -> Self {
        let service_id = service_id.trim().to_owned();
        let db = CharacterDatabase::open_default().ok();
        let mut memo = HashMap::new();
        if let Some(db) = db.as_ref() {
            if let Ok(cache) = db.load_player_cache() {
                for (character_id, name) in cache.names {
                    memo.insert(
                        character_id.clone(),
                        PlayerCacheEntry {
                            character_id,
                            name,
                            ..Default::default()
                        },
                    );
                }
            }
        }
        let client = if service_id.is_empty() {
            None
        } else {
            reqwest::blocking::Client::builder()
                .timeout(Duration::from_millis(900))
                .build()
                .ok()
        };
        Self {
            service_id,
            memo,
            db,
            client,
        }
    }

    fn resolve_name(&mut self, character_id: &str) -> Option<String> {
        self.resolve_profile(character_id)
            .map(|profile| profile.name)
    }

    fn resolve_profile(&mut self, character_id: &str) -> Option<PlayerCacheEntry> {
        let character_id = character_id.trim();
        if character_id.is_empty() || character_id == "0" {
            return None;
        }
        if let Some(profile) = self.memo.get(character_id) {
            if !profile.name.trim().is_empty() {
                return Some(profile.clone());
            }
        }
        if let Some(db) = self.db.as_ref() {
            if let Ok(Some(profile)) = db.find_player_cache_entry(character_id) {
                if !profile.name.trim().is_empty() {
                    self.memo.insert(character_id.to_owned(), profile.clone());
                    return Some(profile);
                }
            }
            if let Ok(Some(name)) = db.find_player_name(character_id) {
                let profile = PlayerCacheEntry {
                    character_id: character_id.to_owned(),
                    name,
                    ..Default::default()
                };
                self.memo.insert(character_id.to_owned(), profile.clone());
                return Some(profile);
            }
        }
        let profile = self.fetch_character_profile(character_id)?;
        if let Some(db) = self.db.as_ref() {
            let _ = db.upsert_player_cache_entry(&profile);
        }
        self.memo.insert(character_id.to_owned(), profile.clone());
        Some(profile)
    }

    fn fetch_character_profile(&self, character_id: &str) -> Option<PlayerCacheEntry> {
        let client = self.client.as_ref()?;
        let url = format!(
            "https://census.daybreakgames.com/{}/get/ps2:v2/character?character_id={character_id}&c:show=character_id,name.first,faction_id,world_id,battle_rank&c:resolve=outfit",
            self.service_id
        );
        let response = client.get(url).send().ok()?;
        let root = response.json::<Value>().ok()?;
        parse_character_profile_payload(&root)
    }
}

impl Drop for CharacterResolver {
    fn drop(&mut self) {}
}

impl Drop for WeaponClassifier {
    fn drop(&mut self) {
        if self.dirty_inserts > 0 {
            self.persist_cache();
            self.dirty_inserts = 0;
        }
    }
}

fn load_tracked_character_ids(seed_character_id: &str) -> HashSet<String> {
    let mut tracked = HashSet::new();
    let seeded = seed_character_id.trim();
    if !seeded.is_empty() {
        tracked.insert(seeded.to_owned());
    }
    if let Ok(db) = CharacterDatabase::open_default() {
        if let Ok(chars) = db.load_my_chars_map() {
            for cid in chars.values() {
                let cid = cid.trim();
                if !cid.is_empty() {
                    tracked.insert(cid.to_owned());
                }
            }
        }
    }
    tracked
}

fn payload_event_name(payload: &Value) -> &str {
    payload
        .get("event_name")
        .and_then(Value::as_str)
        .unwrap_or_default()
}

fn payload_character_id(payload: &Value) -> Option<&str> {
    payload
        .get("character_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty() && *value != "0")
}

fn auto_activate_character_id(payload: &Value, tracked: &HashSet<String>) -> Option<String> {
    if tracked.is_empty() {
        return None;
    }
    let event_name = payload_event_name(payload);
    let Some(character_id) = payload_character_id(payload) else {
        return None;
    };
    if !tracked.contains(character_id) {
        return None;
    }
    // Python parity: late-start activation is keyed off login and own XP traffic.
    if event_name == "PlayerLogin" || event_name == "GainExperience" {
        return Some(character_id.to_owned());
    }
    None
}

const ACTIVE_PLAYER_TRACK_EVENT: &str = "GainExperience";
const ACTIVE_PLAYER_STALE_SECS: f64 = 600.0;
const ID_QUEUE_BATCH_MAX: usize = 30;
const ID_QUEUE_FLUSH_SECS: f64 = 5.0;

#[derive(Debug, Clone)]
struct ActivePlayerEntry {
    last_seen_unix: f64,
}

#[derive(Debug)]
struct CensusSideChannel {
    service_id: String,
    db: Option<CharacterDatabase>,
    active_players: HashMap<String, ActivePlayerEntry>,
    id_queue: VecDeque<String>,
    id_queue_set: HashSet<String>,
    known_name_ids: HashSet<String>,
    cache_client: Option<reqwest::blocking::Client>,
    last_cache_flush_unix: f64,
}

impl CensusSideChannel {
    fn new(service_id: &str) -> Self {
        let service_id = service_id.trim().to_owned();
        let db = CharacterDatabase::open_default().ok();
        let mut known_name_ids = HashSet::new();
        if let Some(db) = db.as_ref() {
            if let Ok(cache) = db.load_player_cache() {
                for character_id in cache.names.keys() {
                    known_name_ids.insert(character_id.clone());
                }
            }
        }
        let cache_client = if service_id.is_empty() {
            None
        } else {
            reqwest::blocking::Client::builder()
                .timeout(Duration::from_secs(5))
                .build()
                .ok()
        };
        Self {
            service_id,
            db,
            active_players: HashMap::new(),
            id_queue: VecDeque::new(),
            id_queue_set: HashSet::new(),
            known_name_ids,
            cache_client,
            last_cache_flush_unix: 0.0,
        }
    }

    fn process_payload(&mut self, payload: &Value, now_unix: f64) -> Vec<IncomingMessage> {
        let mut out = Vec::new();
        match payload_event_name(payload) {
            ACTIVE_PLAYER_TRACK_EVENT => {
                if let Some(track_id) = payload_character_id(payload) {
                    let world_id = world_id_from_payload(payload).unwrap_or(0).to_string();
                    let faction =
                        faction_tag_from_team_id(value_to_u32(payload.get("team_id")).unwrap_or(0))
                            .to_owned();
                    self.active_players.insert(
                        track_id.to_owned(),
                        ActivePlayerEntry {
                            last_seen_unix: now_unix,
                        },
                    );
                    out.push(IncomingMessage::Legacy(LegacyEnvelope {
                        category: "active_player_upsert".to_owned(),
                        data: json!({
                            "character_id": track_id,
                            "faction": faction,
                            "world_id": world_id,
                            "last_seen": now_unix,
                        }),
                    }));
                    self.queue_unknown_id(track_id);
                }
            }
            "PlayerLogout" => {
                if let Some(cid) = payload_character_id(payload) {
                    self.active_players.remove(cid);
                    out.push(IncomingMessage::Legacy(LegacyEnvelope {
                        category: "active_player_remove".to_owned(),
                        data: json!({ "character_id": cid }),
                    }));
                }
            }
            "PlayerFacilityCapture" | "PlayerFacilityDefend" => {
                if let Some(cid) = payload_character_id(payload) {
                    self.queue_unknown_id(cid);
                }
            }
            _ => {}
        }
        self.prune_stale_players(now_unix, &mut out);
        out.extend(self.flush_id_queue_if_due(now_unix));
        out
    }

    fn queue_unknown_id(&mut self, character_id: &str) {
        if character_id.is_empty()
            || character_id == "0"
            || self.known_name_ids.contains(character_id)
            || self.id_queue_set.contains(character_id)
        {
            return;
        }
        self.id_queue.push_back(character_id.to_owned());
        self.id_queue_set.insert(character_id.to_owned());
    }

    fn prune_stale_players(&mut self, now_unix: f64, out: &mut Vec<IncomingMessage>) {
        let stale_before = now_unix - ACTIVE_PLAYER_STALE_SECS;
        let mut removed = Vec::new();
        self.active_players.retain(|character_id, entry| {
            let keep = entry.last_seen_unix >= stale_before;
            if !keep {
                removed.push(character_id.clone());
            }
            keep
        });
        if !removed.is_empty() {
            out.push(IncomingMessage::Legacy(LegacyEnvelope {
                category: "active_player_prune".to_owned(),
                data: json!({ "character_ids": removed }),
            }));
        }
    }

    fn flush_id_queue_if_due(&mut self, now_unix: f64) -> Vec<IncomingMessage> {
        if self.id_queue.is_empty() {
            return Vec::new();
        }
        let flush_due = self.id_queue.len() >= ID_QUEUE_BATCH_MAX
            || self.last_cache_flush_unix <= 0.0
            || (now_unix - self.last_cache_flush_unix) >= ID_QUEUE_FLUSH_SECS;
        if !flush_due {
            return Vec::new();
        }
        self.last_cache_flush_unix = now_unix;

        let mut batch = Vec::new();
        while batch.len() < ID_QUEUE_BATCH_MAX {
            let Some(next) = self.id_queue.pop_front() else {
                break;
            };
            self.id_queue_set.remove(&next);
            if !next.is_empty() && next != "0" {
                batch.push(next);
            }
        }
        if batch.is_empty() {
            return Vec::new();
        }

        let profiles = self.fetch_character_batch_profiles(&batch);
        if profiles.is_empty() {
            return Vec::new();
        }

        let mut names = serde_json::Map::new();
        let mut outfits = serde_json::Map::new();
        for profile in profiles {
            self.known_name_ids.insert(profile.character_id.clone());
            names.insert(
                profile.character_id.clone(),
                Value::String(profile.name.clone()),
            );
            if let Some(tag) = profile.outfit_tag.clone() {
                outfits.insert(profile.character_id.clone(), Value::String(tag));
            }
            if let Some(db) = self.db.as_ref() {
                let _ = db.upsert_player_cache_entry(&profile);
            }
        }
        let db_player_count = self
            .db
            .as_ref()
            .and_then(|db| db.count_player_cache().ok())
            .unwrap_or(0);

        vec![IncomingMessage::Legacy(LegacyEnvelope {
            category: "player_cache_batch".to_owned(),
            data: json!({
                "names": names,
                "outfits": outfits,
                "db_player_count": db_player_count,
            }),
        })]
    }

    fn fetch_character_batch_profiles(&self, ids: &[String]) -> Vec<PlayerCacheEntry> {
        if ids.is_empty() || self.service_id.is_empty() {
            return Vec::new();
        }
        let Some(client) = self.cache_client.as_ref() else {
            return Vec::new();
        };
        let joined = ids.join(",");
        let url = format!(
            "https://census.daybreakgames.com/{}/get/ps2:v2/character/?character_id={joined}&c:show=character_id,name.first,faction_id,battle_rank,world_id&c:resolve=outfit",
            self.service_id
        );
        let Some(response) = client.get(url).send().ok() else {
            return Vec::new();
        };
        let Some(root) = response.json::<Value>().ok() else {
            return Vec::new();
        };
        parse_character_profile_list_payload(&root)
    }
}

fn special_weapon_event_name(weapon_id: &str) -> Option<&'static str> {
    match weapon_id {
        "802512" | "802514" | "802515" | "802516" | "802517" | "802518" | "6005426" | "6005427"
        | "6009294" => Some("Spitfire Kill"),
        "650" | "6005961" | "6005962" | "1045" | "1044" | "6005422" => Some("Mine Kill"),
        _ => None,
    }
}

fn class_kill_event_name(loadout_id: &str) -> Option<&'static str> {
    match loadout_id {
        "1" | "8" | "15" | "28" => Some("Kill Infil"),
        "3" | "10" | "17" | "29" => Some("Kill Light Assault"),
        "4" | "11" | "18" | "30" => Some("Kill Medic"),
        "5" | "12" | "19" | "31" => Some("Kill Engineer"),
        "6" | "13" | "20" | "32" => Some("Kill Heavy"),
        "7" | "14" | "21" | "45" => Some("Kill MAX"),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct CensusWorkerConfig {
    pub service_id: String,
    pub character_id: String,
    pub multi_kill_window_secs: f32,
    pub weapon_lookup_enabled: bool,
    pub kd_mode_revive: bool,
}

#[derive(Debug, Clone, Default)]
struct EncounterStats {
    k: u32,
    d: u32,
    revives_received: u32,
}

#[derive(Debug, Clone, Default)]
struct SessionAccumulator {
    k: u32,
    d: u32,
    hs: u32,
    hsrkill: u32,
    dhs: u32,
    dhs_eligible: u32,
    revives_received: u32,
    start_unix: f64,
    acc_t: f64,
    killstreak_count: u32,
    kill_counter: u32,
    last_kill_ts: f64,
    last_victim_id: Option<String>,
    last_victim_ts: f64,
    is_dead: bool,
    was_revived: bool,
    is_tk_death: bool,
    heal_count: u32,
    resupply_count: u32,
    revive_given_count: u32,
    revive_taken_count: u32,
    repair_count: u32,
    streak_factions: Vec<String>,
    streak_slot_map: Vec<u32>,
    next_streak_slot: u32,
    my_team_id: u32,
    my_world_id: u32,
    current_zone: u32,
    kd_mode_revive: bool,
    encounter_stats: HashMap<String, EncounterStats>,
}

impl SessionAccumulator {
    fn ensure_started(&mut self, now_unix: f64) {
        if self.start_unix <= 0.0 {
            self.start_unix = now_unix.max(1.0);
        }
    }

    fn pause(&mut self, now_unix: f64) {
        if self.start_unix > 0.0 {
            self.acc_t += (now_unix - self.start_unix).max(0.0);
            self.start_unix = 0.0;
        }
    }

    fn as_session_raw_event(&self) -> OverlayEvent {
        OverlayEvent::SessionRaw {
            k: self.k,
            d: self.d,
            hs: self.hs,
            hsrkill: self.hsrkill,
            dhs: self.dhs,
            dhs_eligible: self.dhs_eligible,
            start: self.start_unix,
            acc_t: self.acc_t,
            revives_received: self.revives_received,
            kd_mode_revive: None,
            at: Some(Utc::now()),
        }
    }

    fn reset_support_streaks(&mut self) {
        self.heal_count = 0;
        self.resupply_count = 0;
        self.revive_given_count = 0;
        self.revive_taken_count = 0;
        self.repair_count = 0;
    }

    fn reset_streak_state(&mut self) {
        self.killstreak_count = 0;
        self.kill_counter = 0;
        self.streak_factions.clear();
        self.streak_slot_map.clear();
        self.next_streak_slot = 0;
        self.reset_support_streaks();
    }

    fn record_streak_faction(&mut self, faction: &str) {
        self.streak_factions.push(faction.to_owned());
        self.streak_slot_map.push(self.next_streak_slot);
        self.next_streak_slot = self.next_streak_slot.saturating_add(1);
        if self.streak_factions.len() > 500 {
            let drop_count = self.streak_factions.len().saturating_sub(500);
            self.streak_factions.drain(0..drop_count);
        }
        if self.streak_slot_map.len() > 500 {
            let drop_count = self.streak_slot_map.len().saturating_sub(500);
            self.streak_slot_map.drain(0..drop_count);
        }
    }

    fn record_encounter_death(&mut self, attacker_id: &str, victim_id: &str) {
        let attacker_id = attacker_id.trim();
        let victim_id = victim_id.trim();
        if !attacker_id.is_empty() && attacker_id != "0" && attacker_id != victim_id {
            let attacker = self
                .encounter_stats
                .entry(attacker_id.to_owned())
                .or_default();
            attacker.k = attacker.k.saturating_add(1);
        }
        if !victim_id.is_empty() && victim_id != "0" {
            let victim = self
                .encounter_stats
                .entry(victim_id.to_owned())
                .or_default();
            victim.d = victim.d.saturating_add(1);
        }
    }

    fn record_encounter_revive(&mut self, revived_id: &str) {
        let revived_id = revived_id.trim();
        if revived_id.is_empty() || revived_id == "0" {
            return;
        }
        let revived = self
            .encounter_stats
            .entry(revived_id.to_owned())
            .or_default();
        revived.revives_received = revived.revives_received.saturating_add(1);
    }

    fn encounter_kd(&self, character_id: &str) -> Option<f32> {
        let stats = self.encounter_stats.get(character_id)?;
        if stats.k == 0 {
            return None;
        }
        let effective_d = if self.kd_mode_revive {
            stats.d.saturating_sub(stats.revives_received)
        } else {
            stats.d
        };
        Some(stats.k as f32 / effective_d.max(1) as f32)
    }
}

pub fn spawn_census_worker(
    config: CensusWorkerConfig,
    tx: Sender<IncomingMessage>,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        run_census_loop(config, tx).await;
    })
}

async fn run_census_loop(config: CensusWorkerConfig, tx: Sender<IncomingMessage>) {
    let uri = format!(
        "wss://push.planetside2.com/streaming?environment=ps2&service-id={}",
        config.service_id
    );
    let tracked_character_ids = load_tracked_character_ids(&config.character_id);
    let mut active_character_id = config.character_id.trim().to_owned();
    if active_character_id.is_empty() {
        active_character_id = tracked_character_ids
            .iter()
            .next()
            .cloned()
            .unwrap_or_default();
    }
    let mut sessions: HashMap<String, SessionAccumulator> = HashMap::new();
    let mut event_cache = HashSet::new();
    let mut event_order = VecDeque::new();
    let mut side_channel = CensusSideChannel::new(&config.service_id);
    let mut weapon_classifier =
        WeaponClassifier::new(&config.service_id, config.weapon_lookup_enabled);
    let mut character_resolver = CharacterResolver::new(&config.service_id);
    let vehicle_events = load_vehicle_event_maps();
    let facility_map = load_facility_map();
    let event_catalog = load_event_catalog();
    let streak_template = load_streak_template();
    if vehicle_events.is_empty() {
        warn!("vehicle experience mapping unavailable; specific vehicle events disabled");
    } else {
        info!(
            gunner_kill = vehicle_events.gunner_kill.len(),
            vehicle_kill = vehicle_events.vehicle_kill.len(),
            repair = vehicle_events.repair_ids.len(),
            "loaded vehicle experience mappings"
        );
    }
    if facility_map.is_empty() {
        warn!("facility mapping unavailable; facility context updates limited");
    } else {
        info!(
            facilities = facility_map.names.len(),
            "loaded facility mappings"
        );
    }
    if event_catalog.templates.is_empty() {
        warn!("event template catalog unavailable; using generic event visuals");
    } else {
        info!(
            event_templates = event_catalog.templates.len(),
            "loaded overlay event templates"
        );
    }
    info!(
        streak_active = streak_template.active,
        streak_show_knives = streak_template.show_knives,
        streak_has_custom_path = !streak_template.custom_path.is_empty(),
        "loaded streak template"
    );
    if !config.weapon_lookup_enabled {
        info!("weapon lookup classifier disabled (census_weapon_lookup_enabled=false)");
    }
    info!(
        tracked_characters = tracked_character_ids.len(),
        active_character_id = %if active_character_id.is_empty() { "<none>" } else { active_character_id.as_str() },
        "initialized census tracking roster"
    );
    if tracked_character_ids.is_empty() {
        warn!(
            "no tracked characters loaded from config/db; census events will be ignored until a tracked character is configured"
        );
    }

    loop {
        match connect_async(&uri).await {
            Ok((mut socket, _response)) => {
                info!("connected to census stream");
                let subscribe = json!({
                    "service": "event",
                    "action": "subscribe",
                    "characters": ["all"],
                    "worlds": ["all"],
                    "eventNames": ["Death", "GainExperience", "PlayerLogin", "PlayerLogout", "MetagameEvent", "PlayerFacilityCapture", "PlayerFacilityDefend"]
                });
                if socket
                    .send(tokio_tungstenite::tungstenite::Message::Text(
                        subscribe.to_string(),
                    ))
                    .await
                    .is_err()
                {
                    warn!("failed to send census subscribe payload");
                }

                while let Some(next) = socket.next().await {
                    let text = match next {
                        Ok(tokio_tungstenite::tungstenite::Message::Text(text)) => text,
                        Ok(tokio_tungstenite::tungstenite::Message::Close(_)) => break,
                        Ok(_) => continue,
                        Err(err) => {
                            warn!(?err, "census stream read error");
                            break;
                        }
                    };

                    let payload = match serde_json::from_str::<Value>(&text) {
                        Ok(root) => root.get("payload").cloned(),
                        Err(_) => None,
                    };
                    let Some(payload) = payload else {
                        continue;
                    };

                    let Some(uid) = payload_uid(&payload) else {
                        continue;
                    };
                    if event_cache.contains(&uid) {
                        continue;
                    }
                    event_cache.insert(uid.clone());
                    event_order.push_back(uid);
                    if event_order.len() > 1000 {
                        if let Some(old) = event_order.pop_front() {
                            event_cache.remove(&old);
                        }
                    }

                    let now_unix = event_timestamp_unix(&payload).unwrap_or_else(now_unix);
                    let side_messages = side_channel.process_payload(&payload, now_unix);
                    for message in side_messages {
                        if tx.send(message).is_err() {
                            warn!("overlay receiver dropped; stopping census worker");
                            return;
                        }
                    }
                    if let Some(next_active) =
                        auto_activate_character_id(&payload, &tracked_character_ids)
                    {
                        if active_character_id != next_active {
                            info!(
                                from = %if active_character_id.is_empty() {
                                    "<none>"
                                } else {
                                    active_character_id.as_str()
                                },
                                to = %next_active,
                                event = payload_event_name(&payload),
                                "switching active tracked character from census payload"
                            );
                            active_character_id = next_active;
                        }
                    }
                    if active_character_id.is_empty() {
                        continue;
                    }
                    let session = sessions.entry(active_character_id.clone()).or_default();
                    session.kd_mode_revive = config.kd_mode_revive;
                    let messages = extract_messages_for_payload_with_classifier(
                        &payload,
                        &active_character_id,
                        now_unix,
                        config.multi_kill_window_secs,
                        session,
                        &vehicle_events,
                        &facility_map,
                        Some(&mut weapon_classifier),
                        Some(&mut character_resolver),
                        &event_catalog,
                        &streak_template,
                    );
                    for message in messages {
                        if tx.send(message).is_err() {
                            warn!("overlay receiver dropped; stopping census worker");
                            return;
                        }
                    }
                    if payload_event_name(&payload) == "PlayerLogout"
                        && payload_character_id(&payload) == Some(active_character_id.as_str())
                    {
                        active_character_id.clear();
                    }
                }
                warn!("census stream disconnected, retrying");
            }
            Err(err) => {
                warn!(?err, "failed connecting to census stream");
            }
        }
        sleep(Duration::from_secs(5)).await;
    }
}

#[cfg(test)]
fn extract_messages_for_payload(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    multi_kill_window_secs: f32,
    session: &mut SessionAccumulator,
    vehicle_events: &VehicleEventMaps,
    facility_map: &FacilityMap,
    event_catalog: &EventCatalog,
) -> Vec<IncomingMessage> {
    extract_messages_for_payload_with_classifier(
        payload,
        character_id,
        now_unix,
        multi_kill_window_secs,
        session,
        vehicle_events,
        facility_map,
        None,
        None,
        event_catalog,
        &StreakTemplate::default(),
    )
}

fn extract_messages_for_payload_with_classifier(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    multi_kill_window_secs: f32,
    session: &mut SessionAccumulator,
    vehicle_events: &VehicleEventMaps,
    facility_map: &FacilityMap,
    weapon_classifier: Option<&mut WeaponClassifier>,
    character_resolver: Option<&mut CharacterResolver>,
    event_catalog: &EventCatalog,
    streak_template: &StreakTemplate,
) -> Vec<IncomingMessage> {
    let event_name = payload
        .get("event_name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    match event_name {
        "Death" => extract_death_messages(
            payload,
            character_id,
            now_unix,
            multi_kill_window_secs,
            session,
            weapon_classifier,
            character_resolver,
            event_catalog,
            streak_template,
        ),
        "GainExperience" => extract_experience_messages(
            payload,
            character_id,
            now_unix,
            session,
            vehicle_events,
            event_catalog,
            streak_template,
        ),
        "MetagameEvent" => extract_metagame_messages(payload, session, event_catalog),
        "PlayerFacilityCapture" | "PlayerFacilityDefend" => {
            extract_facility_messages(payload, character_id, session, facility_map)
        }
        "PlayerLogin" => {
            extract_login_messages(payload, character_id, now_unix, session, event_catalog)
        }
        "PlayerLogout" => extract_logout_messages(payload, character_id, now_unix, session),
        _ => Vec::new(),
    }
}

fn extract_login_messages(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    session: &mut SessionAccumulator,
    event_catalog: &EventCatalog,
) -> Vec<IncomingMessage> {
    let cid = payload
        .get("character_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if cid != character_id {
        return Vec::new();
    }
    if let Some(world) = world_id_from_payload(payload) {
        session.my_world_id = world;
    }
    session.ensure_started(now_unix);
    let faction_tag = resolve_login_faction_tag(payload);
    vec![
        IncomingMessage::OverlayEvent(session.as_session_raw_event()),
        build_event_message(&format!("Login {faction_tag}"), event_catalog),
    ]
}

fn resolve_login_faction_tag(payload: &Value) -> &'static str {
    let team_or_faction = value_to_u32(payload.get("team_id"))
        .filter(|value| *value != 0)
        .or_else(|| value_to_u32(payload.get("faction_id")))
        .or_else(|| {
            payload
                .get("character")
                .and_then(|value| value.get("faction_id"))
                .and_then(|value| match value {
                    Value::String(_) | Value::Number(_) => value_to_u32(Some(value)),
                    _ => None,
                })
        })
        .unwrap_or(0);
    faction_tag_from_team_id(team_or_faction)
}

fn extract_logout_messages(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    session: &mut SessionAccumulator,
) -> Vec<IncomingMessage> {
    let cid = payload
        .get("character_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if cid != character_id {
        return Vec::new();
    }
    session.pause(now_unix);
    vec![IncomingMessage::OverlayEvent(
        session.as_session_raw_event(),
    )]
}

fn extract_death_messages(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    multi_kill_window_secs: f32,
    session: &mut SessionAccumulator,
    mut weapon_classifier: Option<&mut WeaponClassifier>,
    mut character_resolver: Option<&mut CharacterResolver>,
    event_catalog: &EventCatalog,
    streak_template: &StreakTemplate,
) -> Vec<IncomingMessage> {
    let attacker_id = payload
        .get("attacker_character_id")
        .and_then(Value::as_str)
        .unwrap_or("0");
    let victim_id = payload
        .get("character_id")
        .and_then(Value::as_str)
        .unwrap_or("0");
    let is_headshot = parse_one_bool(payload.get("is_headshot"));
    let is_teamkill = payload
        .get("attacker_team_id")
        .and_then(Value::as_str)
        .zip(payload.get("team_id").and_then(Value::as_str))
        .map(|(a, b)| a == b && attacker_id != victim_id)
        .unwrap_or(false);
    let attacker_weapon_id = payload
        .get("attacker_weapon_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty() && *value != "0");
    let victim_loadout_id = payload
        .get("character_loadout_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty() && *value != "0")
        .map(ToOwned::to_owned);
    let at = timestamp_to_utc(event_timestamp_unix(payload).unwrap_or(now_unix));
    if let Some(world) = world_id_from_payload(payload) {
        session.my_world_id = world;
    }
    if let Some(zone) = value_to_u32(payload.get("zone_id")) {
        session.current_zone = zone;
    }

    let mut out = Vec::new();
    session.record_encounter_death(attacker_id, victim_id);

    if attacker_id == character_id
        && attacker_id != "0"
        && victim_id != "0"
        && victim_id != character_id
    {
        if session.last_victim_id.as_deref() == Some(victim_id)
            && (now_unix - session.last_victim_ts) < 0.5
        {
            return out;
        }
        session.last_victim_id = Some(victim_id.to_owned());
        session.last_victim_ts = now_unix;
        if let Some(team) = value_to_u32(payload.get("attacker_team_id")) {
            session.my_team_id = team;
        }
        if is_teamkill {
            push_voice_trigger(&mut out, "tk");
            push_event(&mut out, event_catalog, "Team Kill");
            return out;
        }
        let weapon_lookup = attacker_weapon_id
            .map(|weapon_id| lookup_weapon_effects(weapon_id, &mut weapon_classifier))
            .unwrap_or_default();

        session.ensure_started(now_unix);
        if session.is_dead && !session.was_revived && !session.is_tk_death {
            session.reset_streak_state();
        }
        session.is_dead = false;
        session.was_revived = false;
        session.is_tk_death = false;

        session.killstreak_count = session.killstreak_count.saturating_add(1);
        if now_unix - session.last_kill_ts <= f64::from(multi_kill_window_secs.max(0.1)) {
            session.kill_counter = session.kill_counter.saturating_add(1).max(1);
        } else {
            session.kill_counter = 1;
        }
        session.last_kill_ts = now_unix;
        if let Some(victim_team_id) = value_to_u32(payload.get("team_id")) {
            session.record_streak_faction(faction_tag_from_team_id(victim_team_id));
        } else {
            session.record_streak_faction("NSO");
        }

        session.k = session.k.saturating_add(1);
        if weapon_lookup.hsr_eligible {
            session.hsrkill = session.hsrkill.saturating_add(1);
        }
        if is_headshot && weapon_lookup.hsr_eligible {
            session.hs = session.hs.saturating_add(1);
        }

        out.push(IncomingMessage::OverlayEvent(OverlayEvent::Kill {
            victim: resolved_character_name(victim_id, &mut character_resolver),
            weapon: attacker_weapon_id.map(ToOwned::to_owned),
            headshot: is_headshot,
            streak: session.killstreak_count,
            at,
        }));
        out.push(IncomingMessage::OverlayEvent(
            session.as_session_raw_event(),
        ));
        out.push(build_hitmarker_message(is_headshot, event_catalog));
        if is_headshot {
            push_event(&mut out, event_catalog, "Headshot");
        }
        if let Some(name) = multi_event_name(session.kill_counter) {
            push_event(&mut out, event_catalog, name);
        }
        if let Some(name) = streak_event_name(session.killstreak_count) {
            push_event(&mut out, event_catalog, name);
        }
        if let Some(name) = weapon_lookup.event_name.as_ref() {
            push_event(&mut out, event_catalog, name);
        }
        if let Some(loadout_id) = victim_loadout_id.as_deref() {
            if let Some(name) = class_kill_event_name(loadout_id) {
                push_subset_event(&mut out, event_catalog, "Kill", name);
            } else {
                push_event(&mut out, event_catalog, "Kill");
            }
        } else {
            push_event(&mut out, event_catalog, "Kill");
        }
        if matches!(victim_loadout_id.as_deref(), Some("7" | "14" | "21" | "45")) {
            push_voice_trigger(&mut out, "kill_max");
        }
        if matches!(victim_loadout_id.as_deref(), Some("1" | "8" | "15" | "28")) {
            push_voice_trigger(&mut out, "kill_infil");
        }
        if session.encounter_kd(victim_id).unwrap_or(0.0) >= 2.0 {
            push_voice_trigger(&mut out, "kill_high_kd");
        } else if is_headshot {
            push_voice_trigger(&mut out, "kill_hs");
        }
        out.push(streak_display_message(
            session.killstreak_count,
            true,
            session,
            streak_template,
        ));
    }

    if victim_id == character_id && victim_id != "0" {
        if session.is_dead && !session.was_revived && !session.is_tk_death {
            session.reset_streak_state();
        }
        if let Some(team) = value_to_u32(payload.get("team_id")) {
            session.my_team_id = team;
        }
        session.ensure_started(now_unix);
        if !is_teamkill {
            let weapon_lookup = attacker_weapon_id
                .map(|weapon_id| lookup_weapon_effects(weapon_id, &mut weapon_classifier))
                .unwrap_or_default();
            session.d = session.d.saturating_add(1);
            if weapon_lookup.hsr_eligible {
                session.dhs_eligible = session.dhs_eligible.saturating_add(1);
                if is_headshot {
                    session.dhs = session.dhs.saturating_add(1);
                }
            }
        }

        out.push(IncomingMessage::OverlayEvent(OverlayEvent::Death {
            killer: resolved_character_name(attacker_id, &mut character_resolver),
            at,
        }));
        out.push(IncomingMessage::OverlayEvent(
            session.as_session_raw_event(),
        ));

        session.is_dead = true;
        session.was_revived = false;

        if !is_teamkill {
            session.is_tk_death = false;
            out.push(streak_display_message(0, false, session, streak_template));
            if attacker_id == character_id {
                push_event(&mut out, event_catalog, "Suicide");
            } else if is_headshot {
                push_subset_event(&mut out, event_catalog, "Death", "Headshot Death");
            } else {
                push_event(&mut out, event_catalog, "Death");
            }
        } else {
            session.is_tk_death = true;
            push_event(&mut out, event_catalog, "Team Kill Victim");
            if session.killstreak_count > 0 {
                out.push(streak_display_message(
                    session.killstreak_count,
                    true,
                    session,
                    streak_template,
                ));
            }
        }
    }

    out
}

fn resolved_character_name(
    character_id: &str,
    resolver: &mut Option<&mut CharacterResolver>,
) -> String {
    resolver
        .as_deref_mut()
        .and_then(|lookup| lookup.resolve_name(character_id))
        .unwrap_or_else(|| character_id.to_owned())
}

fn lookup_weapon_effects(
    weapon_id: &str,
    classifier: &mut Option<&mut WeaponClassifier>,
) -> WeaponLookup {
    let mut lookup = classifier
        .as_deref_mut()
        .map(|lookup| lookup.lookup(weapon_id))
        .unwrap_or_default();
    if let Some(event_name) = special_weapon_event_name(weapon_id) {
        lookup.event_name = Some(event_name.to_owned());
    }
    if lookup.event_name.as_deref() == Some("Knife Kill") {
        lookup.hsr_eligible = true;
    }
    lookup
}

fn extract_experience_messages(
    payload: &Value,
    character_id: &str,
    now_unix: f64,
    session: &mut SessionAccumulator,
    vehicle_events: &VehicleEventMaps,
    event_catalog: &EventCatalog,
    streak_template: &StreakTemplate,
) -> Vec<IncomingMessage> {
    let exp_id = payload
        .get("experience_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let char_id = payload
        .get("character_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let other_id = payload
        .get("other_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let mut out = Vec::new();
    if REVIVE_EXPERIENCE_IDS.contains(&exp_id) {
        session.record_encounter_revive(other_id);
    }

    if REVIVE_EXPERIENCE_IDS.contains(&exp_id) && other_id == character_id {
        session.ensure_started(now_unix);
        session.revives_received = session.revives_received.saturating_add(1);
        session.was_revived = true;
        session.is_dead = false;
        session.is_tk_death = false;
        let revive_taken_count = increment_support_counter(session, "Revive Taken");
        out.push(IncomingMessage::OverlayEvent(
            session.as_session_raw_event(),
        ));
        push_event(&mut out, event_catalog, "Revive Taken");
        push_voice_trigger(&mut out, "revived");
        if session.killstreak_count > 0 {
            out.push(streak_display_message(
                session.killstreak_count,
                true,
                session,
                streak_template,
            ));
        }
        if let Some(count) = revive_taken_count {
            push_event(&mut out, event_catalog, format!("Revive Taken {count}"));
        }
    }

    if char_id == character_id {
        if let Some(team) = value_to_u32(payload.get("team_id")) {
            session.my_team_id = team;
        }
        if let Some(world) = world_id_from_payload(payload) {
            session.my_world_id = world;
        }
        if let Some(zone) = value_to_u32(payload.get("zone_id")) {
            session.current_zone = zone;
        }

        if let Some(vehicle) = vehicle_events.gunner_kill.get(exp_id) {
            push_subset_event(
                &mut out,
                event_catalog,
                "Gunner Vehicle Destruction",
                &format!("Gunner Kill {vehicle}"),
            );
        }
        if let Some(vehicle) = vehicle_events.vehicle_kill.get(exp_id) {
            push_subset_event(
                &mut out,
                event_catalog,
                "Vehicle Destruction",
                &format!("Kill {vehicle}"),
            );
        }
        if vehicle_events.repair_ids.contains(exp_id) {
            push_event(&mut out, event_catalog, "Repair");
            if let Some(count) = increment_support_counter(session, "Repair") {
                push_event(&mut out, event_catalog, format!("Repair {count}"));
            }
        }

        if REVIVE_EXPERIENCE_IDS.contains(&exp_id) {
            let revive_given_count = increment_support_counter(session, "Revive Given");
            push_event(&mut out, event_catalog, "Revive Given");
            if let Some(count) = revive_given_count {
                push_event(&mut out, event_catalog, format!("Revive Given {count}"));
            }
        } else if ASSIST_EXPERIENCE_IDS.contains(&exp_id) {
            push_event(&mut out, event_catalog, "Assist");
        } else if let Some(name) = mapped_experience_event_name(exp_id) {
            push_event(&mut out, event_catalog, name);
            if let Some(count) = increment_support_counter(session, name) {
                push_event(&mut out, event_catalog, format!("{name} {count}"));
            }
        }
    }

    if other_id == character_id && exp_id == GET_ROADKILLED_EXPERIENCE_ID {
        push_event(&mut out, event_catalog, "Get RoadKilled");
    }

    out
}

fn extract_facility_messages(
    payload: &Value,
    character_id: &str,
    session: &mut SessionAccumulator,
    facility_map: &FacilityMap,
) -> Vec<IncomingMessage> {
    let cid = payload
        .get("character_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if cid != character_id {
        return Vec::new();
    }

    if let Some(world) = world_id_from_payload(payload) {
        session.my_world_id = world;
    }
    if let Some(zone) = value_to_u32(payload.get("zone_id")) {
        session.current_zone = zone;
    }
    if let Some(facility_id) = payload.get("facility_id").and_then(Value::as_str) {
        let name = facility_map
            .names
            .get(facility_id)
            .cloned()
            .unwrap_or_else(|| format!("Facility {facility_id}"));
        info!(
            character_id = cid,
            facility_id,
            facility_name = %name,
            world_id = session.my_world_id,
            zone_id = session.current_zone,
            "facility context update"
        );
    }

    Vec::new()
}

fn extract_metagame_messages(
    payload: &Value,
    session: &SessionAccumulator,
    event_catalog: &EventCatalog,
) -> Vec<IncomingMessage> {
    let state = payload
        .get("metagame_event_state_name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !state.eq_ignore_ascii_case("ended") {
        return Vec::new();
    }

    let world = world_id_from_payload(payload).unwrap_or(0);
    let zone = value_to_u32(payload.get("zone_id")).unwrap_or(0);
    if world == 0 || zone == 0 {
        return Vec::new();
    }
    if session.my_world_id == 0 || session.current_zone == 0 || session.my_team_id == 0 {
        return Vec::new();
    }
    if world != session.my_world_id || zone != session.current_zone {
        return Vec::new();
    }

    let vs = value_to_f64(payload.get("faction_vs")).unwrap_or(0.0);
    let tr = value_to_f64(payload.get("faction_tr")).unwrap_or(0.0);
    let nc = value_to_f64(payload.get("faction_nc")).unwrap_or(0.0);
    let won = match session.my_team_id {
        1 => vs > tr && vs > nc,
        2 => nc > tr && nc > vs,
        3 => tr > vs && tr > nc,
        _ => false,
    };

    vec![build_event_message(
        if won { "Alert Win" } else { "Alert End" },
        event_catalog,
    )]
}

fn mapped_experience_event_name(exp_id: &str) -> Option<&'static str> {
    for (name, ids) in EXPERIENCE_EVENT_IDS {
        if ids.contains(&exp_id) {
            return Some(*name);
        }
    }
    None
}

fn increment_support_counter(session: &mut SessionAccumulator, event_name: &str) -> Option<u32> {
    let counter = match event_name {
        "Heal" => &mut session.heal_count,
        "Resupply" => &mut session.resupply_count,
        "Revive Given" => &mut session.revive_given_count,
        "Revive Taken" => &mut session.revive_taken_count,
        "Repair" => &mut session.repair_count,
        _ => return None,
    };
    *counter = counter.saturating_add(1);
    Some(*counter)
}

fn load_vehicle_event_maps() -> VehicleEventMaps {
    let Some(path) = locate_experience_json() else {
        return VehicleEventMaps::default();
    };

    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed to read experience mapping file");
            return VehicleEventMaps::default();
        }
    };

    let root = match serde_json::from_str::<Value>(&text) {
        Ok(root) => root,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed to parse experience mapping file");
            return VehicleEventMaps::default();
        }
    };

    parse_vehicle_event_maps(&root)
}

fn load_facility_map() -> FacilityMap {
    let Some(path) = locate_bases_json() else {
        return FacilityMap::default();
    };

    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed to read facility mapping file");
            return FacilityMap::default();
        }
    };

    let root = match serde_json::from_str::<Value>(&text) {
        Ok(root) => root,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed to parse facility mapping file");
            return FacilityMap::default();
        }
    };

    let mut map = FacilityMap::default();
    let Some(entries) = root.as_object() else {
        return map;
    };
    for (facility_id, value) in entries {
        let name = value
            .get("name")
            .and_then(Value::as_str)
            .or_else(|| value.as_str())
            .map(str::trim)
            .unwrap_or_default();
        if !name.is_empty() {
            map.names.insert(facility_id.clone(), name.to_owned());
        }
    }
    map
}

fn parse_vehicle_event_maps(root: &Value) -> VehicleEventMaps {
    let mut maps = VehicleEventMaps::default();
    let excluded = [
        "Infantry",
        "Engineer Turret",
        "Engi Turret",
        "Phalanx",
        "Drop Pod",
        "Spitfire",
        "HIVE",
        "Construction",
    ];
    let contains_excluded = |value: &str| excluded.iter().any(|needle| value.contains(needle));

    let Some(entries) = root.get("experience_list").and_then(Value::as_array) else {
        return maps;
    };

    for entry in entries {
        let Some(exp_id) = entry
            .get("experience_id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
        else {
            continue;
        };
        let description = entry
            .get("description")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default();
        if description.is_empty() {
            continue;
        }

        if description.contains("Repair") {
            maps.repair_ids.insert(exp_id.clone());
        }

        if description.contains("Kill by")
            && description.contains("Gunner")
            && !description.starts_with("Player Kill by")
        {
            if let Some((vehicle, _)) = description.split_once(" Kill by ") {
                let vehicle = vehicle.trim();
                if !vehicle.is_empty() && !contains_excluded(vehicle) {
                    maps.gunner_kill.insert(exp_id.clone(), vehicle.to_owned());
                }
            }
        } else if let Some(vehicle) = description.strip_prefix("Vehicle Destruction - ") {
            let vehicle = vehicle.trim();
            if !vehicle.is_empty() && !contains_excluded(vehicle) {
                maps.vehicle_kill.insert(exp_id, vehicle.to_owned());
            }
        }
    }

    maps
}

fn locate_experience_json() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("assets").join("experience.json"));
        candidates.push(cwd.join("..").join("assets").join("experience.json"));
        candidates.push(cwd.join("_internal").join("assets").join("experience.json"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("assets").join("experience.json"));
            candidates.push(exe_dir.join("..").join("assets").join("experience.json"));
            candidates.push(
                exe_dir
                    .join("_internal")
                    .join("assets")
                    .join("experience.json"),
            );
        }
    }

    candidates.into_iter().find(|path| path.is_file())
}

fn locate_bases_json() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("assets").join("bases.json"));
        candidates.push(cwd.join("..").join("assets").join("bases.json"));
        candidates.push(cwd.join("_internal").join("assets").join("bases.json"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("assets").join("bases.json"));
            candidates.push(exe_dir.join("..").join("assets").join("bases.json"));
            candidates.push(exe_dir.join("_internal").join("assets").join("bases.json"));
        }
    }

    candidates.into_iter().find(|path| path.is_file())
}

fn load_event_catalog() -> EventCatalog {
    let Some(path) = locate_config_json() else {
        return EventCatalog::default();
    };
    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed reading event config");
            return EventCatalog::default();
        }
    };
    let root = match serde_json::from_str::<Value>(&text) {
        Ok(root) => root,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed parsing event config");
            return EventCatalog::default();
        }
    };
    parse_event_catalog(&root)
}

fn load_streak_template() -> StreakTemplate {
    let Some(path) = locate_config_json() else {
        return StreakTemplate::default();
    };
    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed reading streak config");
            return StreakTemplate::default();
        }
    };
    let root = match serde_json::from_str::<Value>(&text) {
        Ok(root) => root,
        Err(err) => {
            warn!(?err, path = %path.display(), "failed parsing streak config");
            return StreakTemplate::default();
        }
    };
    parse_streak_template(&root)
}

fn parse_event_catalog(root: &Value) -> EventCatalog {
    let mut catalog = EventCatalog::default();
    let global_duration = json_u64(root.get("event_global_duration"))
        .unwrap_or(3_000)
        .max(60);
    let queue_active = root
        .get("event_queue_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let Some(events) = root.get("events").and_then(Value::as_object) else {
        return catalog;
    };

    for (event_name, event_cfg) in events {
        let Some(map) = event_cfg.as_object() else {
            continue;
        };
        let images = map.get("img").map(parse_sound_names).unwrap_or_default();
        let sounds = map.get("snd").map(parse_sound_names).unwrap_or_default();
        let sound_volume = json_f32(map.get("volume")).unwrap_or(1.0).clamp(0.0, 2.0);
        let duration_ms = compute_template_duration_ms(
            event_name,
            json_u64(map.get("duration")),
            global_duration,
            queue_active,
        )
        .max(60);
        let x = json_f32(map.get("x")).unwrap_or(640.0);
        let y = json_f32(map.get("y")).unwrap_or(220.0);
        let scale = json_f32(map.get("scale")).unwrap_or(1.0).max(0.1);
        let play_duplicate = map
            .get("play_duplicate")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        let impact = map
            .get("impact")
            .and_then(Value::as_bool)
            .unwrap_or_else(|| default_event_impact(event_name));
        let template = EventTemplate {
            images,
            sounds,
            sound_volume,
            duration_ms,
            x,
            y,
            scale,
            play_duplicate,
            impact,
        };
        let key = event_name.to_ascii_lowercase();
        catalog.templates.insert(key, template.clone());
        catalog
            .canonical_templates
            .entry(canonical_event_key(event_name))
            .or_insert_with(|| template.clone());
        if event_name.eq_ignore_ascii_case("Ludicrous Kill") {
            catalog
                .templates
                .insert("ludacris kill".to_owned(), template.clone());
            catalog
                .canonical_templates
                .entry(canonical_event_key("ludacris kill"))
                .or_insert_with(|| template.clone());
        } else if event_name.eq_ignore_ascii_case("Ludacris Kill") {
            catalog
                .templates
                .insert("ludicrous kill".to_owned(), template.clone());
            catalog
                .canonical_templates
                .entry(canonical_event_key("ludicrous kill"))
                .or_insert_with(|| template.clone());
        }
    }

    catalog
}

fn compute_template_duration_ms(
    event_name: &str,
    specific_duration: Option<u64>,
    global_duration: u64,
    queue_active: bool,
) -> u64 {
    let lower = event_name.to_ascii_lowercase();
    let specific = specific_duration.unwrap_or(0);
    if lower == "hitmarker" || lower == "headshot hitmarker" {
        if specific > 0 {
            return specific;
        }
        return if lower == "headshot hitmarker" {
            170
        } else {
            120
        };
    }
    if !queue_active {
        return global_duration.max(60);
    }
    if specific > 0 {
        specific
    } else {
        global_duration.max(60)
    }
}

fn canonical_event_key(name: &str) -> String {
    name.chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .map(|ch| ch.to_ascii_lowercase())
        .collect()
}

fn canonical_event_aliases(canonical: &str) -> &'static [&'static str] {
    match canonical {
        "revenge" => &["revengekill"],
        "revengekill" => &["revenge"],
        "getroadkilled" => &["roadkillvictim"],
        "roadkillvictim" => &["getroadkilled"],
        "minekill" => &["tankminekill", "apminekill"],
        "tankminekill" => &["minekill"],
        "apminekill" => &["minekill"],
        "revive" => &["revivetaken", "revivegiven"],
        "revivetaken" => &["revive"],
        "revivegiven" => &["revive"],
        "killmax" => &["maxkill"],
        "maxkill" => &["killmax"],
        _ => &[],
    }
}

fn parse_streak_template(root: &Value) -> StreakTemplate {
    let asset_roots = detect_asset_roots();
    parse_streak_template_with_asset_roots(root, &asset_roots)
}

fn parse_streak_template_with_asset_roots(root: &Value, asset_roots: &[PathBuf]) -> StreakTemplate {
    let mut template = StreakTemplate::default();
    let Some(streak) = root.get("streak").and_then(Value::as_object) else {
        return template;
    };
    template.active = streak
        .get("active")
        .and_then(Value::as_bool)
        .unwrap_or(template.active);
    template.bg_filename = streak
        .get("img")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned);
    template.x = json_f32(streak.get("x")).unwrap_or(template.x);
    template.y = json_f32(streak.get("y")).unwrap_or(template.y);
    template.tx = json_f32(streak.get("tx")).unwrap_or(template.tx);
    template.ty = json_f32(streak.get("ty")).unwrap_or(template.ty);
    template.scale = json_f32(streak.get("scale"))
        .unwrap_or(template.scale)
        .max(0.1);
    template.font_size = json_f32(streak.get("size"))
        .unwrap_or(template.font_size)
        .max(8.0);
    template.color = streak
        .get("color")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .unwrap_or(template.color);
    template.bold = streak
        .get("bold")
        .and_then(Value::as_bool)
        .unwrap_or(template.bold);
    template.anim_active = streak
        .get("anim_active")
        .and_then(Value::as_bool)
        .unwrap_or(template.anim_active);
    template.anim_speed = json_f32(streak.get("speed"))
        .unwrap_or(template.anim_speed)
        .max(1.0);
    template.streak_glow = streak
        .get("streak_glow")
        .and_then(Value::as_bool)
        .or_else(|| streak.get("knife_glow").and_then(Value::as_bool))
        .unwrap_or(template.streak_glow);
    template.glow_color = streak
        .get("glow_color")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .unwrap_or(template.glow_color);
    template.show_knives = streak
        .get("show_knives")
        .and_then(Value::as_bool)
        .unwrap_or(template.show_knives);
    template.knife_size = json_f32(streak.get("knife_size"))
        .or_else(|| json_f32(streak.get("knife_size_px")))
        .unwrap_or(template.knife_size)
        .max(8.0);
    template.knife_tr = streak
        .get("knife_tr")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned);
    template.knife_nc = streak
        .get("knife_nc")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned);
    template.knife_vs = streak
        .get("knife_vs")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned);
    template.knife_nso = streak
        .get("knife_nso")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned);
    template.custom_path = parse_custom_path(streak.get("custom_path"));
    let width_cfg = json_f32(streak.get("width")).filter(|value| *value > 0.0);
    let height_cfg = json_f32(streak.get("height")).filter(|value| *value > 0.0);
    let inferred = if width_cfg.is_none() || height_cfg.is_none() {
        template
            .bg_filename
            .as_deref()
            .and_then(|name| asset_image_size(name, asset_roots))
    } else {
        None
    };
    template.bg_width = width_cfg
        .or_else(|| inferred.map(|(w, _)| w))
        .unwrap_or(template.bg_width)
        .max(80.0);
    template.bg_height = height_cfg
        .or_else(|| inferred.map(|(_, h)| h))
        .unwrap_or(template.bg_height)
        .max(80.0);
    template.knives_per_ring = json_u64(streak.get("knives_per_ring"))
        .and_then(|v| u32::try_from(v).ok())
        .unwrap_or(template.knives_per_ring)
        .max(1);
    template.ring_spacing = json_f32(streak.get("ring_spacing"))
        .unwrap_or(template.ring_spacing)
        .max(4.0);
    template
}

#[cfg(test)]
fn classify_weapon_payload(root: &Value) -> Option<String> {
    parse_weapon_lookup_payload(root).event_name
}

fn parse_weapon_lookup_payload(root: &Value) -> WeaponLookup {
    let Some(item) = root
        .get("item_list")
        .and_then(Value::as_array)
        .and_then(|list| list.first())
    else {
        return WeaponLookup::default();
    };
    let item_name = item
        .get("name")
        .and_then(|name| name.get("en"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let item_type_name = item
        .get("item_type")
        .and_then(|item_type| item_type.get("name"))
        .and_then(Value::as_str)
        .unwrap_or_default();

    WeaponLookup {
        event_name: classify_weapon_text(item_name, item_type_name),
        hsr_eligible: is_hsr_weapon_category(item_type_name),
    }
}

#[cfg(test)]
fn parse_character_payload(root: &Value) -> Option<String> {
    let entry = root
        .get("character_list")
        .and_then(Value::as_array)
        .and_then(|list| list.first())?;
    entry
        .get("name")
        .and_then(|name| name.get("first"))
        .and_then(Value::as_str)
        .or_else(|| entry.get("name.first").and_then(Value::as_str))
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(ToOwned::to_owned)
}

fn parse_character_profile_payload(root: &Value) -> Option<PlayerCacheEntry> {
    parse_character_profile_list_payload(root)
        .into_iter()
        .next()
}

fn parse_character_profile_list_payload(root: &Value) -> Vec<PlayerCacheEntry> {
    let Some(entries) = root.get("character_list").and_then(Value::as_array) else {
        return Vec::new();
    };
    entries
        .iter()
        .filter_map(|entry| {
            let character_id = json_text(entry, &["character_id"])?;
            let name = json_text(entry, &["name.first", "name/first"])?;
            let world_id = json_text(entry, &["world_id"]);
            let faction_id = json_i64(entry.get("faction_id"));
            let battle_rank = entry
                .get("battle_rank")
                .and_then(|rank| rank.get("value"))
                .and_then(|value| json_i64(Some(value)))
                .or_else(|| json_i64(entry.get("battle_rank.value")));
            let outfit_tag = entry
                .get("outfit")
                .and_then(|outfit| outfit.get("alias"))
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|tag| !tag.is_empty())
                .map(ToOwned::to_owned);
            Some(PlayerCacheEntry {
                character_id,
                name,
                world_id,
                faction_id,
                outfit_tag,
                battle_rank,
            })
        })
        .collect()
}

fn json_text(root: &Value, paths: &[&str]) -> Option<String> {
    for path in paths {
        if path.contains('/') {
            let mut current = root;
            let mut ok = true;
            for key in path.split('/') {
                let Some(next) = current.get(key) else {
                    ok = false;
                    break;
                };
                current = next;
            }
            if ok {
                if let Some(text) = current
                    .as_str()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                {
                    return Some(text.to_owned());
                }
            }
        } else if let Some(text) = root
            .get(*path)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            return Some(text.to_owned());
        }
    }
    None
}

fn json_i64(value: Option<&Value>) -> Option<i64> {
    value.and_then(|v| {
        if let Some(n) = v.as_i64() {
            return Some(n);
        }
        v.as_str().and_then(|raw| raw.trim().parse::<i64>().ok())
    })
}

fn classify_weapon_text(item_name: &str, item_type_name: &str) -> Option<String> {
    let name = item_name.to_ascii_lowercase();
    let type_name = item_type_name.to_ascii_lowercase();
    if name.contains("spitfire") || type_name.contains("spitfire") {
        return Some("Spitfire Kill".to_owned());
    }
    if type_name.contains("knife") || name.contains("knife") {
        return Some("Knife Kill".to_owned());
    }
    if type_name.contains("grenade") || name.contains("grenade") {
        return Some("Nade Kill".to_owned());
    }
    None
}

fn is_hsr_weapon_category(item_type_name: &str) -> bool {
    HSR_WEAPON_CATEGORIES
        .iter()
        .any(|entry| entry.eq_ignore_ascii_case(item_type_name.trim()))
}

fn locate_config_json() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("config.json"));
        candidates.push(cwd.join("..").join("config.json"));
        candidates.push(cwd.join("_internal").join("config.json"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("config.json"));
            candidates.push(exe_dir.join("..").join("config.json"));
            candidates.push(exe_dir.join("_internal").join("config.json"));
        }
    }
    candidates.into_iter().find(|path| path.is_file())
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

fn asset_image_size(filename: &str, roots: &[PathBuf]) -> Option<(f32, f32)> {
    let path = resolve_asset_path(filename, roots)?;
    let (w, h) = image::image_dimensions(path).ok()?;
    Some((w as f32, h as f32))
}

fn locate_weapon_cache_path() -> Option<PathBuf> {
    let base = dirs::config_dir()?.join("better-planetside-overlay-next");
    if fs::create_dir_all(&base).is_err() {
        return None;
    }
    Some(base.join("weapon_event_cache.json"))
}

fn locate_weapon_hsr_cache_path() -> Option<PathBuf> {
    let base = dirs::config_dir()?.join("better-planetside-overlay-next");
    if fs::create_dir_all(&base).is_err() {
        return None;
    }
    Some(base.join("weapon_hsr_cache.json"))
}

fn parse_sound_names(value: &Value) -> Vec<String> {
    match value {
        Value::String(name) => vec![name.trim().to_owned()]
            .into_iter()
            .filter(|name| !name.is_empty())
            .collect(),
        Value::Array(items) => items
            .iter()
            .filter_map(Value::as_str)
            .map(str::trim)
            .filter(|name| !name.is_empty())
            .map(ToOwned::to_owned)
            .collect(),
        _ => Vec::new(),
    }
}

fn default_event_impact(event_name: &str) -> bool {
    matches!(
        event_name.to_ascii_lowercase().as_str(),
        "headshot" | "death"
    )
}

fn choose_sound_name(sounds: &[String]) -> Option<String> {
    if sounds.is_empty() {
        return None;
    }
    if sounds.len() == 1 {
        return Some(sounds[0].clone());
    }
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.subsec_nanos() as usize)
        .unwrap_or(0);
    let idx = nanos % sounds.len();
    Some(sounds[idx].clone())
}

fn choose_image_name(images: &[String]) -> Option<String> {
    choose_sound_name(images)
}

fn json_f32(value: Option<&Value>) -> Option<f32> {
    value
        .and_then(Value::as_f64)
        .map(|v| v as f32)
        .or_else(|| value.and_then(Value::as_i64).map(|v| v as f32))
}

fn json_u64(value: Option<&Value>) -> Option<u64> {
    value.and_then(Value::as_u64).or_else(|| {
        value
            .and_then(Value::as_i64)
            .and_then(|v| u64::try_from(v).ok())
    })
}

fn parse_custom_path(value: Option<&Value>) -> Vec<(f32, f32)> {
    let Some(items) = value.and_then(Value::as_array) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for item in items {
        let Some(pair) = item.as_array() else {
            continue;
        };
        if pair.len() < 2 {
            continue;
        }
        let x = json_f32(pair.first()).unwrap_or(0.0);
        let y = json_f32(pair.get(1)).unwrap_or(0.0);
        out.push((x, y));
    }
    out
}

fn faction_tag_from_team_id(team_id: u32) -> &'static str {
    match team_id {
        1 => "VS",
        2 => "NC",
        3 => "TR",
        _ => "NSO",
    }
}

fn build_hitmarker_message(headshot: bool, catalog: &EventCatalog) -> IncomingMessage {
    let name = if headshot {
        "Headshot Hitmarker"
    } else {
        "Hitmarker"
    };
    if let Some(template) = catalog.template(name) {
        let image = choose_image_name(&template.images);
        let sound = choose_sound_name(&template.sounds);
        return IncomingMessage::Legacy(LegacyEnvelope {
            category: "hitmarker".to_owned(),
            data: json!({
                "event_name": name,
                "event_type": name.to_ascii_lowercase(),
                "duration": template.duration_ms,
                "centered": false,
                "x": template.x,
                "y": template.y,
                "scale": template.scale,
                "filename": image,
                "sound_filename": sound,
                "sound_volume": template.sound_volume,
                "play_duplicate": template.play_duplicate,
                "impact": template.impact
            }),
        });
    }
    IncomingMessage::Legacy(LegacyEnvelope {
        category: "hitmarker".to_owned(),
        data: json!({
            "event_name": if headshot { "Headshot Hitmarker" } else { "Hitmarker" },
            "event_type": if headshot { "headshot hitmarker" } else { "hitmarker" },
            "duration": if headshot { 170 } else { 120 },
            "centered": true,
            "x": 640,
            "y": 360,
            "width": if headshot { 180 } else { 140 },
            "height": if headshot { 180 } else { 140 },
            "impact": headshot
        }),
    })
}

fn push_event(out: &mut Vec<IncomingMessage>, catalog: &EventCatalog, name: impl AsRef<str>) {
    out.push(build_event_message(name.as_ref(), catalog));
}

fn push_voice_trigger(out: &mut Vec<IncomingMessage>, trigger: &str) {
    out.push(build_voice_trigger_message(trigger));
}

fn build_voice_trigger_message(trigger: &str) -> IncomingMessage {
    IncomingMessage::Legacy(LegacyEnvelope {
        category: "voice_trigger".to_owned(),
        data: json!({
            "trigger": trigger,
            "at": Utc::now().to_rfc3339(),
        }),
    })
}

fn push_subset_event(
    out: &mut Vec<IncomingMessage>,
    catalog: &EventCatalog,
    parent_event: &str,
    specific_event: &str,
) {
    if catalog.has_specific_config(specific_event) {
        push_event(out, catalog, specific_event);
    } else {
        push_event(out, catalog, parent_event);
    }
}

fn build_event_message(name: &str, catalog: &EventCatalog) -> IncomingMessage {
    if let Some(template) = catalog.template(name) {
        let image = choose_image_name(&template.images);
        let sound = choose_sound_name(&template.sounds);
        return IncomingMessage::Legacy(LegacyEnvelope {
            category: "event".to_owned(),
            data: json!({
                "event_name": name,
                "event_type": name.to_ascii_lowercase(),
                "duration": template.duration_ms,
                "centered": false,
                "x": template.x,
                "y": template.y,
                "scale": template.scale,
                "filename": image,
                "sound_filename": sound,
                "sound_volume": template.sound_volume,
                "play_duplicate": template.play_duplicate,
                "impact": template.impact
            }),
        });
    }
    IncomingMessage::Legacy(LegacyEnvelope {
        category: "event".to_owned(),
        data: json!({
            "event_name": name,
            "event_type": name.to_ascii_lowercase(),
            "duration": 1800,
            "centered": true,
            "x": 640,
            "y": 220,
            "width": 360,
            "height": 140,
            "impact": default_event_impact(name)
        }),
    })
}

fn streak_display_message(
    count: u32,
    visible: bool,
    session: &SessionAccumulator,
    template: &StreakTemplate,
) -> IncomingMessage {
    if !visible || !template.active {
        return IncomingMessage::Legacy(LegacyEnvelope {
            category: "streak".to_owned(),
            data: json!({
                "visible": false
            }),
        });
    }
    let knives = if template.show_knives && count > 0 {
        build_streak_knives(session, template)
    } else {
        Vec::new()
    };
    IncomingMessage::Legacy(LegacyEnvelope {
        category: "streak".to_owned(),
        data: json!({
            "visible": true,
            "bg_filename": template.bg_filename.clone().unwrap_or_default(),
            "bg_width": ((template.bg_width * template.scale).round() as i64).max(80),
            "bg_height": ((template.bg_height * template.scale).round() as i64).max(80),
            "x": template.x,
            "y": template.y,
            "scale": 1.0,
            "count": count.max(1),
            "tx": template.tx,
            "ty": template.ty,
            "font_size": (template.font_size * template.scale).max(8.0),
            "color": template.color,
            "bold": template.bold,
            "anim_active": template.anim_active,
            "anim_speed": template.anim_speed,
            "streak_glow": template.streak_glow,
            "glow_color": template.glow_color,
            "knives": knives,
        }),
    })
}

fn build_streak_knives(session: &SessionAccumulator, template: &StreakTemplate) -> Vec<Value> {
    let mut out = Vec::new();
    let entries = session
        .streak_factions
        .len()
        .min(session.streak_slot_map.len());
    if entries == 0 {
        return out;
    }

    let bg_w = (template.bg_width * template.scale).max(80.0);
    let bg_h = (template.bg_height * template.scale).max(80.0);
    let knives_per_ring = template.knives_per_ring.max(1) as f32;
    let has_custom_path = template.custom_path.len() > 2;

    let custom_segments = if has_custom_path {
        let mut segments = Vec::new();
        let mut total = 0.0_f32;
        for i in 0..template.custom_path.len() {
            let (x1, y1) = template.custom_path[i];
            let (x2, y2) = template.custom_path[(i + 1) % template.custom_path.len()];
            let dx = x2 - x1;
            let dy = y2 - y1;
            let seg_len = (dx * dx + dy * dy).sqrt();
            segments.push(((x1, y1), (x2, y2), seg_len, total));
            total += seg_len;
        }
        Some((segments, total.max(0.0)))
    } else {
        None
    };

    for i in 0..entries {
        let faction = &session.streak_factions[i];
        let slot = session.streak_slot_map[i] as f32;
        let ring_idx = (slot / knives_per_ring).floor();
        let pos_in_ring = slot % knives_per_ring;
        let ring_scale = 1.0 + (ring_idx * 0.28);

        let Some(filename) = streak_knife_filename(template, faction).map(ToOwned::to_owned) else {
            continue;
        };

        let (x_off, y_off, rotation_deg) =
            if let Some((segments, total_len)) = custom_segments.as_ref() {
                if *total_len > 0.0 {
                    let target = (pos_in_ring / knives_per_ring) * *total_len;
                    let mut point = (0.0_f32, 0.0_f32);
                    for (p1, p2, seg_len, start_len) in segments {
                        if *seg_len <= 0.0 {
                            continue;
                        }
                        if target >= *start_len && target <= *start_len + *seg_len {
                            let t = (target - *start_len) / *seg_len;
                            point = (p1.0 + t * (p2.0 - p1.0), p1.1 + t * (p2.1 - p1.1));
                            break;
                        }
                    }
                    let x = point.0 * ring_scale;
                    let y = point.1 * ring_scale;
                    (x, y, y.atan2(x).to_degrees() + 90.0)
                } else {
                    (0.0, 0.0, 0.0)
                }
            } else {
                let angle = (pos_in_ring * (360.0 / knives_per_ring)) - 90.0;
                let rad = angle.to_radians();
                let sin_v = rad.sin();
                let narrow = if sin_v > 0.0 {
                    1.0 - (0.15 * sin_v)
                } else {
                    1.0
                };
                let sx = (bg_w * 0.5) - 15.0;
                let sy = (bg_h * 0.5) - 15.0;
                let radius_x = (sx + (ring_idx * template.ring_spacing)) * narrow;
                let radius_y = sy + (ring_idx * template.ring_spacing);
                let x = radius_x * rad.cos();
                let y = -20.0 + radius_y * rad.sin();
                (x, y, angle + 90.0)
            };

        out.push(json!({
            "filename": filename,
            "x_off": x_off,
            "y_off": y_off,
            "rotation": rotation_deg,
            "size": template.knife_size,
            "faction": faction,
        }));
    }
    out
}

fn streak_knife_filename<'a>(template: &'a StreakTemplate, faction: &str) -> Option<&'a str> {
    let specific = match faction.to_ascii_uppercase().as_str() {
        "TR" => template.knife_tr.as_deref(),
        "NC" => template.knife_nc.as_deref(),
        "VS" => template.knife_vs.as_deref(),
        "NSO" => template.knife_nso.as_deref(),
        _ => None,
    };
    specific
        .or(template.knife_tr.as_deref())
        .or(template.knife_nc.as_deref())
        .or(template.knife_vs.as_deref())
        .or(template.knife_nso.as_deref())
}

fn multi_event_name(counter: u32) -> Option<&'static str> {
    match counter {
        2 => Some("Double Kill"),
        3 => Some("Multi Kill"),
        4 => Some("Mega Kill"),
        5 => Some("Ultra Kill"),
        6 => Some("Monster Kill"),
        7 => Some("Ludacris Kill"),
        9 => Some("Holy Shit"),
        _ => None,
    }
}

fn streak_event_name(streak: u32) -> Option<&'static str> {
    match streak {
        12 => Some("Squad Wiper"),
        24 => Some("Double Squad Wipe"),
        36 => Some("Squad Lead's Nightmare"),
        48 => Some("One Man Platoon"),
        _ => None,
    }
}

fn payload_uid(payload: &Value) -> Option<String> {
    let event_name = payload.get("event_name").and_then(Value::as_str)?;
    let timestamp = payload
        .get("timestamp")
        .and_then(value_to_string)
        .unwrap_or_else(|| "0".to_owned());
    let uid = match event_name {
        "GainExperience" => format!(
            "EXP_{timestamp}_{}_{}_{}",
            payload
                .get("character_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("experience_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("other_id")
                .and_then(Value::as_str)
                .unwrap_or("0")
        ),
        "Death" => format!(
            "DTH_{timestamp}_{}_{}_{}",
            payload
                .get("character_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("attacker_character_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("attacker_weapon_id")
                .and_then(Value::as_str)
                .unwrap_or("0")
        ),
        "MetagameEvent" => format!(
            "MTG_{timestamp}_{}_{}_{}",
            world_id_from_payload(payload).unwrap_or(0),
            payload
                .get("metagame_event_id")
                .and_then(value_to_string)
                .unwrap_or_else(|| "0".to_owned()),
            payload
                .get("metagame_event_state_name")
                .and_then(value_to_string)
                .unwrap_or_else(|| "unknown".to_owned())
        ),
        "PlayerFacilityCapture" | "PlayerFacilityDefend" => format!(
            "FAC_{event_name}_{timestamp}_{}_{}_{}_{}",
            payload
                .get("character_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("facility_id")
                .and_then(value_to_string)
                .unwrap_or_else(|| "0".to_owned()),
            world_id_from_payload(payload).unwrap_or(0),
            payload
                .get("zone_id")
                .and_then(value_to_string)
                .unwrap_or_else(|| "0".to_owned())
        ),
        _ => format!(
            "{event_name}_{timestamp}_{}_{}",
            payload
                .get("character_id")
                .and_then(Value::as_str)
                .unwrap_or("0"),
            payload
                .get("attacker_character_id")
                .and_then(Value::as_str)
                .unwrap_or("0")
        ),
    };
    Some(uid)
}

fn value_to_string(value: &Value) -> Option<String> {
    match value {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

fn event_timestamp_unix(payload: &Value) -> Option<f64> {
    payload
        .get("timestamp")
        .and_then(Value::as_str)
        .and_then(|s| s.parse::<f64>().ok())
        .or_else(|| payload.get("timestamp").and_then(Value::as_f64))
}

fn value_to_f64(value: Option<&Value>) -> Option<f64> {
    value
        .and_then(Value::as_str)
        .and_then(|s| s.parse::<f64>().ok())
        .or_else(|| value.and_then(Value::as_f64))
        .or_else(|| value.and_then(Value::as_i64).map(|v| v as f64))
}

fn value_to_u32(value: Option<&Value>) -> Option<u32> {
    value
        .and_then(Value::as_str)
        .and_then(|s| s.parse::<u32>().ok())
        .or_else(|| {
            value
                .and_then(Value::as_u64)
                .and_then(|v| u32::try_from(v).ok())
        })
}

fn normalize_world_id(world_id: u32) -> u32 {
    match world_id {
        17 => 1,
        13 => 10,
        _ => world_id,
    }
}

fn world_id_from_payload(payload: &Value) -> Option<u32> {
    value_to_u32(payload.get("world_id")).map(normalize_world_id)
}

fn now_unix() -> f64 {
    Utc::now().timestamp() as f64
}

fn timestamp_to_utc(timestamp: f64) -> chrono::DateTime<Utc> {
    let sec = timestamp.floor() as i64;
    Utc.timestamp_opt(sec, 0).single().unwrap_or_else(Utc::now)
}

fn parse_one_bool(value: Option<&Value>) -> bool {
    match value {
        Some(Value::String(s)) => s == "1" || s.eq_ignore_ascii_case("true"),
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_i64().unwrap_or(0) == 1,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use serde_json::json;

    use super::{
        auto_activate_character_id, build_event_message, build_hitmarker_message,
        choose_sound_name, classify_weapon_payload, classify_weapon_text,
        compute_template_duration_ms, default_event_impact, extract_messages_for_payload,
        extract_messages_for_payload_with_classifier, is_hsr_weapon_category,
        parse_character_payload, parse_character_profile_list_payload, parse_event_catalog,
        parse_sound_names, parse_streak_template, parse_streak_template_with_asset_roots,
        parse_vehicle_event_maps, parse_weapon_lookup_payload, payload_uid, push_subset_event,
        resolve_login_faction_tag, streak_display_message, CensusSideChannel, CharacterResolver,
        EventCatalog, EventTemplate, FacilityMap, IncomingMessage, OverlayEvent, PlayerCacheEntry,
        SessionAccumulator, StreakTemplate, VehicleEventMaps, WeaponClassifier,
    };

    fn catalog_with(events: &[&str]) -> EventCatalog {
        let mut catalog = EventCatalog::default();
        for name in events {
            catalog.templates.insert(
                name.to_ascii_lowercase(),
                EventTemplate {
                    images: vec!["Headshot Banner.png".to_owned()],
                    sounds: Vec::new(),
                    sound_volume: 1.0,
                    duration_ms: 1800,
                    x: 640.0,
                    y: 220.0,
                    scale: 1.0,
                    play_duplicate: true,
                    impact: false,
                },
            );
        }
        catalog
    }

    #[test]
    fn kill_emits_hitmarker_and_streak_and_session_raw() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "1",
            "attacker_weapon_id": "7234",
            "attacker_team_id": "1",
            "team_id": "2"
        });

        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::OverlayEvent(OverlayEvent::Kill { streak: 1, .. })
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("hitmarker")
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("streak")
        )));
        assert_eq!(session.killstreak_count, 1);
    }

    #[test]
    fn teamkill_emits_voice_tk_trigger() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "attacker_team_id": "2",
            "team_id": "2"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| {
            matches!(
                m,
                IncomingMessage::Legacy(env)
                if env.category == "voice_trigger"
                    && env.data.get("trigger").and_then(|v| v.as_str()) == Some("tk")
            )
        }));
    }

    #[test]
    fn revive_taken_emits_voice_revived_trigger() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000001",
            "experience_id": "7",
            "character_id": "300",
            "other_id": "100",
            "team_id": "2",
            "world_id": "10"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| {
            matches!(
                m,
                IncomingMessage::Legacy(env)
                if env.category == "voice_trigger"
                    && env.data.get("trigger").and_then(|v| v.as_str()) == Some("revived")
            )
        }));
    }

    #[test]
    fn class_and_high_kd_kill_emit_voice_triggers() {
        let mut session = SessionAccumulator::default();
        session.kd_mode_revive = true;
        session.encounter_stats.insert(
            "200".to_owned(),
            super::EncounterStats {
                k: 4,
                d: 1,
                revives_received: 0,
            },
        );
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "character_loadout_id": "7",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| {
            matches!(
                m,
                IncomingMessage::Legacy(env)
                if env.category == "voice_trigger"
                    && env.data.get("trigger").and_then(|v| v.as_str()) == Some("kill_max")
            )
        }));
        assert!(out.iter().any(|m| {
            matches!(
                m,
                IncomingMessage::Legacy(env)
                if env.category == "voice_trigger"
                    && env.data.get("trigger").and_then(|v| v.as_str()) == Some("kill_high_kd")
            )
        }));
    }

    #[test]
    fn kill_streak_payload_contains_generated_knife_for_victim_faction() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "0",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        let template = StreakTemplate {
            knife_tr: Some("Knife TR Small.png".to_owned()),
            knife_nc: Some("Knife NC Small.png".to_owned()),
            knife_vs: Some("Knife VS Small.png".to_owned()),
            ..Default::default()
        };
        let out = extract_messages_for_payload_with_classifier(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            None,
            None,
            &EventCatalog::default(),
            &template,
        );
        let streak = out
            .iter()
            .find_map(|message| match message {
                IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("streak") => {
                    Some(env.data.clone())
                }
                _ => None,
            })
            .expect("streak payload should be present");
        let knives = streak["knives"]
            .as_array()
            .expect("knives should be serialized");
        assert_eq!(knives.len(), 1);
        assert_eq!(knives[0]["filename"].as_str(), Some("Knife NC Small.png"));
        assert_eq!(knives[0]["faction"].as_str(), Some("NC"));
    }

    #[test]
    fn duplicate_same_victim_within_half_second_is_ignored() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "0",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        let out1 = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        let out2 = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.3,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(!out1.is_empty());
        assert!(out2.is_empty());
        assert_eq!(session.k, 1);
        assert_eq!(session.killstreak_count, 1);
    }

    #[test]
    fn death_hides_streak_without_immediate_reset() {
        let mut session = SessionAccumulator {
            killstreak_count: 5,
            kill_counter: 3,
            heal_count: 2,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "1"
        });

        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out
            .iter()
            .any(|m| matches!(m, IncomingMessage::OverlayEvent(OverlayEvent::Death { .. }))));
        assert!(out.iter().any(|m| match m {
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("streak") => {
                env.data["visible"].as_bool() == Some(false)
            }
            _ => false,
        }));
        assert_eq!(session.killstreak_count, 5);
        assert_eq!(session.kill_counter, 3);
        assert_eq!(session.heal_count, 2);
    }

    #[test]
    fn double_death_resets_streak_and_support_counters() {
        let mut session = SessionAccumulator {
            killstreak_count: 5,
            kill_counter: 3,
            heal_count: 2,
            resupply_count: 4,
            revive_given_count: 1,
            revive_taken_count: 1,
            repair_count: 9,
            is_dead: true,
            was_revived: false,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "1"
        });
        let _ = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(session.killstreak_count, 0);
        assert_eq!(session.kill_counter, 0);
        assert_eq!(session.heal_count, 0);
        assert_eq!(session.resupply_count, 0);
        assert_eq!(session.revive_given_count, 0);
        assert_eq!(session.revive_taken_count, 0);
        assert_eq!(session.repair_count, 0);
    }

    #[test]
    fn normal_death_emits_death_event() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "1"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Death")
        )));
    }

    #[test]
    fn death_headshot_ratio_only_tracks_hsr_eligible_weapons() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "1",
            "attacker_weapon_id": "9000",
            "attacker_team_id": "2",
            "team_id": "1"
        });
        let mut classifier = WeaponClassifier::new("", false);
        classifier.cache.insert("9000".to_owned(), None);
        classifier.hsr_cache.insert("9000".to_owned(), false);
        let _ = extract_messages_for_payload_with_classifier(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            Some(&mut classifier),
            None,
            &EventCatalog::default(),
            &StreakTemplate::default(),
        );
        assert_eq!(session.d, 1);
        assert_eq!(session.dhs_eligible, 0);
        assert_eq!(session.dhs, 0);
    }

    #[test]
    fn revive_taken_updates_session_and_event() {
        let mut session = SessionAccumulator {
            killstreak_count: 4,
            is_dead: true,
            was_revived: false,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000001",
            "character_id": "999",
            "other_id": "100",
            "experience_id": "7"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(session.revives_received, 1);
        assert!(session.was_revived);
        assert!(!session.is_dead);
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Revive Taken")
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("streak")
                && env.data["visible"].as_bool() == Some(true)
                && env.data["count"].as_u64() == Some(4)
        )));
    }

    #[test]
    fn logout_pauses_accumulated_time() {
        let mut session = SessionAccumulator {
            start_unix: 1000.0,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "PlayerLogout",
            "timestamp": "1010",
            "character_id": "100"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1010.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(out.len(), 1);
        assert_eq!(session.start_unix, 0.0);
        assert!((session.acc_t - 10.0).abs() < f64::EPSILON);
    }

    #[test]
    fn login_emits_faction_login_event() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "PlayerLogin",
            "timestamp": "1010",
            "character_id": "100",
            "team_id": "2",
            "world_id": "17"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1010.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Login NC")
        )));
        assert_eq!(session.my_world_id, 1);
    }

    #[test]
    fn login_faction_tag_falls_back_to_faction_id() {
        let payload = json!({
            "event_name": "PlayerLogin",
            "character_id": "100",
            "team_id": "0",
            "faction_id": "3"
        });
        assert_eq!(resolve_login_faction_tag(&payload), "TR");
    }

    #[test]
    fn experience_id_mapping_emits_expected_event() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000001",
            "character_id": "100",
            "experience_id": "593"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Bounty Kill")
        )));
    }

    #[test]
    fn support_event_emits_milestone_counter() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000001",
            "character_id": "100",
            "experience_id": "4"
        });
        let out1 = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        let out2 = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_002.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out1.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Heal 1")
        )));
        assert!(out2.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Heal 2")
        )));
    }

    #[test]
    fn attacker_teamkill_emits_team_kill_only() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "2"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Team Kill")
        )));
        assert!(!out
            .iter()
            .any(|m| matches!(m, IncomingMessage::OverlayEvent(OverlayEvent::Kill { .. }))));
    }

    #[test]
    fn victim_teamkill_keeps_streak_but_sets_dead_state() {
        let mut session = SessionAccumulator {
            killstreak_count: 6,
            is_dead: false,
            was_revived: true,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "2"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Team Kill Victim")
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("streak")
                && env.data["visible"].as_bool() == Some(true)
                && env.data["count"].as_u64() == Some(6)
        )));
        assert_eq!(session.killstreak_count, 6);
        assert_eq!(session.d, 0);
        assert_eq!(session.dhs_eligible, 0);
        assert!(session.is_dead);
        assert!(!session.was_revived);
        assert!(session.is_tk_death);
    }

    #[test]
    fn kill_after_teamkill_death_keeps_streak() {
        let mut session = SessionAccumulator {
            killstreak_count: 6,
            kill_counter: 2,
            is_dead: true,
            was_revived: false,
            is_tk_death: true,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000002",
            "attacker_character_id": "100",
            "character_id": "201",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "3"
        });
        let _ = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_002.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(session.killstreak_count, 7);
        assert!(!session.is_dead);
        assert!(!session.was_revived);
        assert!(!session.is_tk_death);
    }

    #[test]
    fn double_death_does_not_reset_when_teamkill_flag_is_set() {
        let mut session = SessionAccumulator {
            killstreak_count: 5,
            kill_counter: 3,
            heal_count: 2,
            is_dead: true,
            was_revived: false,
            is_tk_death: true,
            ..Default::default()
        };
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000003",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "1"
        });
        let _ = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_003.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(session.killstreak_count, 5);
        assert_eq!(session.kill_counter, 3);
        assert_eq!(session.heal_count, 2);
    }

    #[test]
    fn attacker_kill_emits_special_and_class_events() {
        let mut session = SessionAccumulator::default();
        let catalog = catalog_with(&["Kill Heavy"]);
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "character_loadout_id": "6",
            "attacker_weapon_id": "650",
            "is_headshot": "1",
            "attacker_team_id": "2",
            "team_id": "3"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &catalog,
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Mine Kill")
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Kill Heavy")
        )));
        assert!(!out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Kill")
        )));
    }

    #[test]
    fn parses_vehicle_experience_mappings() {
        let root = json!({
            "experience_list": [
                {
                    "experience_id": "901",
                    "description": "Flash Kill by Vanguard Gunner"
                },
                {
                    "experience_id": "902",
                    "description": "Vehicle Destruction - Lightning"
                },
                {
                    "experience_id": "903",
                    "description": "Player Kill by Sunderer Gunner"
                },
                {
                    "experience_id": "904",
                    "description": "Vehicle Destruction - Phalanx"
                },
                {
                    "experience_id": "905",
                    "description": "MAX Repair"
                }
            ]
        });
        let maps = parse_vehicle_event_maps(&root);
        assert_eq!(
            maps.gunner_kill.get("901").map(String::as_str),
            Some("Flash")
        );
        assert_eq!(
            maps.vehicle_kill.get("902").map(String::as_str),
            Some("Lightning")
        );
        assert!(!maps.gunner_kill.contains_key("903"));
        assert!(!maps.vehicle_kill.contains_key("904"));
        assert!(maps.repair_ids.contains("905"));
    }

    #[test]
    fn gain_experience_emits_specific_vehicle_events() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000010",
            "character_id": "100",
            "experience_id": "901"
        });
        let mut maps = VehicleEventMaps::default();
        maps.gunner_kill
            .insert("901".to_owned(), "Flash".to_owned());
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_010.0,
            4.0,
            &mut session,
            &maps,
            &FacilityMap::default(),
            &catalog_with(&["Gunner Kill Flash"]),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Gunner Kill Flash")
        )));
    }

    #[test]
    fn metagame_ended_emits_alert_win_for_matching_world_zone() {
        let mut session = SessionAccumulator::default();
        let maps = VehicleEventMaps::default();
        let gain_exp = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000010",
            "character_id": "100",
            "experience_id": "4",
            "team_id": "2",
            "world_id": "17",
            "zone_id": "2"
        });
        let _ = extract_messages_for_payload(
            &gain_exp,
            "100",
            1_700_000_010.0,
            4.0,
            &mut session,
            &maps,
            &FacilityMap::default(),
            &EventCatalog::default(),
        );

        let metagame = json!({
            "event_name": "MetagameEvent",
            "timestamp": "1700000011",
            "metagame_event_state_name": "ended",
            "world_id": "17",
            "zone_id": "2",
            "faction_vs": "10",
            "faction_tr": "20",
            "faction_nc": "70"
        });
        let out = extract_messages_for_payload(
            &metagame,
            "100",
            1_700_000_011.0,
            4.0,
            &mut session,
            &maps,
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Alert Win")
        )));
    }

    #[test]
    fn world_merge_ids_are_normalized_in_session_context() {
        let mut session = SessionAccumulator::default();
        let maps = VehicleEventMaps::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000010",
            "character_id": "100",
            "experience_id": "4",
            "team_id": "2",
            "world_id": "17",
            "zone_id": "2"
        });
        let _ = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_010.0,
            4.0,
            &mut session,
            &maps,
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert_eq!(session.my_world_id, 1);
    }

    #[test]
    fn facility_event_updates_world_zone_without_overlay_event() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "PlayerFacilityCapture",
            "timestamp": "1700000012",
            "character_id": "100",
            "facility_id": "201",
            "world_id": "13",
            "zone_id": "2"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_012.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.is_empty());
        assert_eq!(session.my_world_id, 10);
        assert_eq!(session.current_zone, 2);
    }

    #[test]
    fn facility_uid_uses_normalized_world_id() {
        let payload = json!({
            "event_name": "PlayerFacilityDefend",
            "timestamp": "1700000013",
            "character_id": "100",
            "facility_id": "201",
            "world_id": "17",
            "zone_id": "2"
        });
        let uid = payload_uid(&payload).expect("expected uid");
        assert_eq!(uid, "FAC_PlayerFacilityDefend_1700000013_100_201_1_2");
    }

    #[test]
    fn roadkill_exp_emits_roadkill_for_attacker() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000014",
            "character_id": "100",
            "other_id": "200",
            "experience_id": "26"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_014.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("RoadKill")
        )));
    }

    #[test]
    fn roadkill_exp_emits_get_roadkilled_for_victim() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000015",
            "character_id": "200",
            "other_id": "100",
            "experience_id": "26"
        });
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_015.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Get RoadKilled")
        )));
    }

    #[test]
    fn repair_exp_emits_repair_with_counter() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "GainExperience",
            "timestamp": "1700000016",
            "character_id": "100",
            "experience_id": "6"
        });
        let mut maps = VehicleEventMaps::default();
        maps.repair_ids.insert("6".to_owned());
        let out = extract_messages_for_payload(
            &payload,
            "100",
            1_700_000_016.0,
            4.0,
            &mut session,
            &maps,
            &FacilityMap::default(),
            &EventCatalog::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Repair")
        )));
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Repair 1")
        )));
    }

    #[test]
    fn subset_falls_back_to_parent_when_specific_not_configured() {
        let root = json!({
            "events": {
                "Kill": {"img":"Kill.png"},
                "Kill Heavy": {"img":""}
            }
        });
        let catalog = parse_event_catalog(&root);
        let mut out = Vec::new();
        push_subset_event(&mut out, &catalog, "Kill", "Kill Heavy");
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Kill")
        )));
    }

    #[test]
    fn subset_uses_specific_when_image_or_sound_configured() {
        let root = json!({
            "events": {
                "Kill": {"img":"Kill.png"},
                "Kill Heavy": {"snd":"Headshot.ogg"}
            }
        });
        let catalog = parse_event_catalog(&root);
        let mut out = Vec::new();
        push_subset_event(&mut out, &catalog, "Kill", "Kill Heavy");
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::Legacy(env) if env.category.eq_ignore_ascii_case("event")
                && env.data["event_name"].as_str() == Some("Kill Heavy")
        )));
    }

    #[test]
    fn build_event_uses_template_payload_when_available() {
        let root = json!({
            "events": {
                "Headshot": {
                    "img": "Headshot Banner.png",
                    "snd": "Headshot.ogg",
                    "duration": 2000,
                    "x": 700,
                    "y": 120,
                    "scale": 0.75,
                    "volume": 0.6,
                    "play_duplicate": false,
                    "impact": true
                }
            }
        });
        let catalog = parse_event_catalog(&root);
        let msg = build_event_message("Headshot", &catalog);
        match msg {
            IncomingMessage::Legacy(env) => {
                assert_eq!(env.data["filename"].as_str(), Some("Headshot Banner.png"));
                assert_eq!(env.data["sound_filename"].as_str(), Some("Headshot.ogg"));
                assert_eq!(env.data["duration"].as_u64(), Some(2000));
                assert_eq!(env.data["play_duplicate"].as_bool(), Some(false));
                assert_eq!(env.data["impact"].as_bool(), Some(true));
            }
            _ => panic!("expected legacy message"),
        }
    }

    #[test]
    fn template_duration_uses_global_and_hitmarker_rules() {
        assert_eq!(
            compute_template_duration_ms("Kill", Some(0), 3000, true),
            3000
        );
        assert_eq!(
            compute_template_duration_ms("Kill", Some(900), 3000, true),
            900
        );
        assert_eq!(
            compute_template_duration_ms("Kill", Some(900), 3000, false),
            3000
        );
        assert_eq!(
            compute_template_duration_ms("Hitmarker", Some(90), 3000, false),
            90
        );
        assert_eq!(
            compute_template_duration_ms("Headshot Hitmarker", Some(0), 3000, true),
            170
        );
    }

    #[test]
    fn build_event_matches_template_with_spacing_alias() {
        let root = json!({
            "events": {
                "Road Kill": {
                    "img": "Road Kill.png"
                }
            }
        });
        let catalog = parse_event_catalog(&root);
        let msg = build_event_message("RoadKill", &catalog);
        match msg {
            IncomingMessage::Legacy(env) => {
                assert_eq!(env.data["filename"].as_str(), Some("Road Kill.png"));
            }
            _ => panic!("expected legacy message"),
        }
    }

    #[test]
    fn build_event_matches_template_with_legacy_name_alias() {
        let root = json!({
            "events": {
                "Revenge Kill": { "img": "Revenge_Kill.png" },
                "Roadkill Victim": { "img": "Roadkill_Victim.png" },
                "Max Kill": { "img": "Max_Kill.png" },
                "Tankmine Kill": { "img": "Tankmine_Kill.png" }
            }
        });
        let catalog = parse_event_catalog(&root);

        let revenge = build_event_message("Revenge", &catalog);
        let roadkill_victim = build_event_message("Get RoadKilled", &catalog);
        let kill_max = build_event_message("Kill MAX", &catalog);
        let mine_kill = build_event_message("Mine Kill", &catalog);
        let revive_taken = build_event_message("Revive Taken", &catalog);

        let read_filename = |msg: IncomingMessage| -> Option<String> {
            match msg {
                IncomingMessage::Legacy(env) => env.data["filename"].as_str().map(str::to_owned),
                _ => None,
            }
        };

        assert_eq!(read_filename(revenge), Some("Revenge_Kill.png".to_owned()));
        assert_eq!(
            read_filename(roadkill_victim),
            Some("Roadkill_Victim.png".to_owned())
        );
        assert_eq!(read_filename(kill_max), Some("Max_Kill.png".to_owned()));
        let mine = read_filename(mine_kill).expect("mine alias should resolve");
        assert!(mine == "Tankmine_Kill.png");
        assert_eq!(read_filename(revive_taken), None);
    }

    #[test]
    fn build_event_matches_revive_alias_for_legacy_config() {
        let root = json!({
            "events": {
                "Revive": { "img": "Revive.png" }
            }
        });
        let catalog = parse_event_catalog(&root);
        let revive_taken = build_event_message("Revive Taken", &catalog);
        let revive_given = build_event_message("Revive Given", &catalog);
        let read_filename = |msg: IncomingMessage| -> Option<String> {
            match msg {
                IncomingMessage::Legacy(env) => env.data["filename"].as_str().map(str::to_owned),
                _ => None,
            }
        };
        assert_eq!(read_filename(revive_taken), Some("Revive.png".to_owned()));
        assert_eq!(read_filename(revive_given), Some("Revive.png".to_owned()));
    }

    #[test]
    fn hitmarker_uses_template_payload_when_available() {
        let root = json!({
            "events": {
                "Headshot Hitmarker": {
                    "img": "Headshot_Hitmarker.png",
                    "snd": "Headshot.ogg",
                    "duration": 210,
                    "x": 820,
                    "y": 420,
                    "scale": 1.2,
                    "volume": 0.5,
                    "play_duplicate": false,
                    "impact": true
                }
            }
        });
        let catalog = parse_event_catalog(&root);
        let msg = build_hitmarker_message(true, &catalog);
        match msg {
            IncomingMessage::Legacy(env) => {
                assert_eq!(env.category, "hitmarker");
                assert_eq!(
                    env.data["filename"].as_str(),
                    Some("Headshot_Hitmarker.png")
                );
                assert_eq!(env.data["sound_filename"].as_str(), Some("Headshot.ogg"));
                assert_eq!(env.data["duration"].as_u64(), Some(210));
                assert_eq!(env.data["x"].as_f64(), Some(820.0));
                assert_eq!(env.data["y"].as_f64(), Some(420.0));
                let scale = env.data["scale"].as_f64().expect("scale should be present");
                assert!((scale - 1.2).abs() < 1e-4);
                assert_eq!(env.data["play_duplicate"].as_bool(), Some(false));
            }
            _ => panic!("expected legacy message"),
        }
    }

    #[test]
    fn template_impact_defaults_to_headshot_and_death_when_unspecified() {
        let root = json!({
            "events": {
                "Headshot": { "img": "Headshot Banner.png" },
                "Death": { "img": "Death Banner.png" },
                "Assist": { "img": "Assist Banner.png" }
            }
        });
        let catalog = parse_event_catalog(&root);
        let headshot = build_event_message("Headshot", &catalog);
        let death = build_event_message("Death", &catalog);
        let assist = build_event_message("Assist", &catalog);
        match headshot {
            IncomingMessage::Legacy(env) => assert_eq!(env.data["impact"].as_bool(), Some(true)),
            _ => panic!("expected legacy message"),
        }
        match death {
            IncomingMessage::Legacy(env) => assert_eq!(env.data["impact"].as_bool(), Some(true)),
            _ => panic!("expected legacy message"),
        }
        match assist {
            IncomingMessage::Legacy(env) => assert_eq!(env.data["impact"].as_bool(), Some(false)),
            _ => panic!("expected legacy message"),
        }
    }

    #[test]
    fn fallback_event_payload_sets_default_impact() {
        let catalog = EventCatalog::default();
        let headshot = build_event_message("Headshot", &catalog);
        let kill = build_event_message("Kill", &catalog);
        match headshot {
            IncomingMessage::Legacy(env) => assert_eq!(env.data["impact"].as_bool(), Some(true)),
            _ => panic!("expected legacy message"),
        }
        match kill {
            IncomingMessage::Legacy(env) => assert_eq!(env.data["impact"].as_bool(), Some(false)),
            _ => panic!("expected legacy message"),
        }
        assert!(default_event_impact("Death"));
        assert!(!default_event_impact("Assist"));
    }

    #[test]
    fn classify_weapon_text_detects_knife_and_grenade() {
        assert_eq!(
            classify_weapon_text("NS-44L Showdown", "Knife"),
            Some("Knife Kill".to_owned())
        );
        assert_eq!(
            classify_weapon_text("Frag Grenade", "Explosive Grenade"),
            Some("Nade Kill".to_owned())
        );
        assert_eq!(
            classify_weapon_text("Spitfire Auto-Turret", "Deployable"),
            Some("Spitfire Kill".to_owned())
        );
    }

    #[test]
    fn classify_weapon_payload_reads_item_list_shape() {
        let payload = json!({
            "item_list": [
                {
                    "name": {"en":"Frag Grenade"},
                    "item_type": {"name":"Explosive Grenade"}
                }
            ]
        });
        assert_eq!(
            classify_weapon_payload(&payload),
            Some("Nade Kill".to_owned())
        );
    }

    #[test]
    fn parse_weapon_lookup_payload_detects_hsr_eligibility() {
        let payload = json!({
            "item_list": [
                {
                    "name": {"en":"GD-7F"},
                    "item_type": {"name":"Carbine"}
                }
            ]
        });
        let lookup = parse_weapon_lookup_payload(&payload);
        assert!(lookup.hsr_eligible);
        assert_eq!(lookup.event_name, None);
    }

    #[test]
    fn hsr_eligibility_category_match_is_case_insensitive() {
        assert!(is_hsr_weapon_category("lmg"));
        assert!(is_hsr_weapon_category("Knife"));
        assert!(!is_hsr_weapon_category("Explosive Grenade"));
    }

    #[test]
    fn hsr_stats_only_increment_for_hsr_eligible_weapons() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "1",
            "attacker_weapon_id": "7234",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        let mut classifier = WeaponClassifier::new("", false);
        classifier.cache.insert("7234".to_owned(), None);
        classifier.hsr_cache.insert("7234".to_owned(), true);
        let out = extract_messages_for_payload_with_classifier(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            Some(&mut classifier),
            None,
            &EventCatalog::default(),
            &StreakTemplate::default(),
        );
        assert!(!out.is_empty());
        assert_eq!(session.k, 1);
        assert_eq!(session.hsrkill, 1);
        assert_eq!(session.hs, 1);

        let payload2 = json!({
            "event_name": "Death",
            "timestamp": "1700000002",
            "attacker_character_id": "100",
            "character_id": "201",
            "is_headshot": "1",
            "attacker_weapon_id": "9000",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        classifier.cache.insert("9000".to_owned(), None);
        classifier.hsr_cache.insert("9000".to_owned(), false);
        let _ = extract_messages_for_payload_with_classifier(
            &payload2,
            "100",
            1_700_000_002.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            Some(&mut classifier),
            None,
            &EventCatalog::default(),
            &StreakTemplate::default(),
        );
        assert_eq!(session.k, 2);
        assert_eq!(session.hsrkill, 1);
        assert_eq!(session.hs, 1);
    }

    #[test]
    fn parse_sound_names_supports_string_and_array() {
        let one = json!("Headshot.ogg");
        let many = json!(["a.ogg", "b.ogg", ""]);
        assert_eq!(parse_sound_names(&one), vec!["Headshot.ogg".to_owned()]);
        assert_eq!(
            parse_sound_names(&many),
            vec!["a.ogg".to_owned(), "b.ogg".to_owned()]
        );
    }

    #[test]
    fn build_event_supports_image_array_templates() {
        let root = json!({
            "events": {
                "Spitfire Kill": {
                    "img": ["Spitty1.png", "Spitty2.png"]
                }
            }
        });
        let catalog = parse_event_catalog(&root);
        let msg = build_event_message("Spitfire Kill", &catalog);
        match msg {
            IncomingMessage::Legacy(env) => {
                let filename = env.data["filename"]
                    .as_str()
                    .expect("filename should be selected");
                assert!(filename == "Spitty1.png" || filename == "Spitty2.png");
            }
            _ => panic!("expected legacy message"),
        }
    }

    #[test]
    fn parse_streak_template_reads_legacy_fields() {
        let root = json!({
            "streak": {
                "img": "Skull small.png",
                "active": true,
                "x": 402,
                "y": 856,
                "tx": 0,
                "ty": -45,
                "scale": 0.9,
                "size": 46,
                "speed": 100,
                "show_knives": true,
                "knife_tr": "Knife TR Small.png",
                "knife_nc": "Knife NC Small.png",
                "knife_vs": "Knife VS Small.png",
                "custom_path": [[10, -96], [37, -84], [57, -64]],
                "streak_glow": false,
                "glow_color": "#00f2ff"
            }
        });
        let template = parse_streak_template(&root);
        assert!(template.active);
        assert_eq!(template.bg_filename.as_deref(), Some("Skull small.png"));
        assert_eq!(template.x, 402.0);
        assert_eq!(template.y, 856.0);
        assert_eq!(template.ty, -45.0);
        assert_eq!(template.scale, 0.9);
        assert_eq!(template.font_size, 46.0);
        assert_eq!(template.anim_speed, 100.0);
        assert_eq!(template.knife_vs.as_deref(), Some("Knife VS Small.png"));
        assert_eq!(template.custom_path.len(), 3);
        assert!(!template.streak_glow);
    }

    #[test]
    fn parse_streak_template_infers_bg_size_from_image_asset() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock should be valid")
            .as_nanos();
        let asset_root = std::env::temp_dir().join(format!("bp_streak_assets_{unique}"));
        let images_dir = asset_root.join("Images");
        std::fs::create_dir_all(&images_dir).expect("should create image asset dir");
        let image_path = images_dir.join("Skull small.png");
        let image = image::RgbaImage::from_pixel(320, 180, image::Rgba([255, 0, 0, 255]));
        image
            .save(&image_path)
            .expect("should write sample streak image");

        let root = json!({
            "streak": {
                "img": "Skull small.png",
                "scale": 1.0
            }
        });
        let template = parse_streak_template_with_asset_roots(&root, &[asset_root.clone()]);
        assert_eq!(template.bg_width, 320.0);
        assert_eq!(template.bg_height, 180.0);

        std::fs::remove_file(image_path).ok();
        std::fs::remove_dir_all(asset_root).ok();
    }

    #[test]
    fn streak_display_message_uses_template_knives() {
        let mut session = SessionAccumulator::default();
        session.streak_factions = vec!["VS".to_owned(), "NC".to_owned(), "TR".to_owned()];
        session.streak_slot_map = vec![0, 1, 2];

        let template = StreakTemplate {
            bg_filename: Some("Skull small.png".to_owned()),
            knife_tr: Some("Knife TR Small.png".to_owned()),
            knife_nc: Some("Knife NC Small.png".to_owned()),
            knife_vs: Some("Knife VS Small.png".to_owned()),
            ..Default::default()
        };

        let msg = streak_display_message(3, true, &session, &template);
        let IncomingMessage::Legacy(env) = msg else {
            panic!("expected legacy streak payload");
        };
        assert_eq!(env.category, "streak");
        assert_eq!(env.data["visible"].as_bool(), Some(true));
        assert_eq!(env.data["count"].as_u64(), Some(3));
        assert_eq!(env.data["bg_filename"].as_str(), Some("Skull small.png"));
        let knives = env.data["knives"]
            .as_array()
            .expect("knives should be array");
        assert_eq!(knives.len(), 3);
        assert_eq!(
            knives
                .first()
                .and_then(|item| item.get("filename"))
                .and_then(|value| value.as_str()),
            Some("Knife VS Small.png")
        );
    }

    #[test]
    fn parse_character_payload_reads_first_name() {
        let payload = json!({
            "character_list": [
                {
                    "name": {"first":"EnemyHeavy"}
                }
            ]
        });
        assert_eq!(
            parse_character_payload(&payload),
            Some("EnemyHeavy".to_owned())
        );
    }

    #[test]
    fn auto_activate_character_picks_login_for_tracked_id() {
        let mut tracked = HashSet::new();
        tracked.insert("100".to_owned());
        let payload = json!({
            "event_name": "PlayerLogin",
            "character_id": "100"
        });
        assert_eq!(
            auto_activate_character_id(&payload, &tracked).as_deref(),
            Some("100")
        );
    }

    #[test]
    fn auto_activate_character_picks_gain_experience_for_tracked_id() {
        let mut tracked = HashSet::new();
        tracked.insert("100".to_owned());
        let payload = json!({
            "event_name": "GainExperience",
            "character_id": "100",
            "other_id": "200"
        });
        assert_eq!(
            auto_activate_character_id(&payload, &tracked).as_deref(),
            Some("100")
        );
    }

    #[test]
    fn auto_activate_character_ignores_untracked_or_irrelevant_events() {
        let mut tracked = HashSet::new();
        tracked.insert("100".to_owned());
        let untracked = json!({
            "event_name": "PlayerLogin",
            "character_id": "999"
        });
        let wrong_event = json!({
            "event_name": "Death",
            "character_id": "100"
        });
        assert!(auto_activate_character_id(&untracked, &tracked).is_none());
        assert!(auto_activate_character_id(&wrong_event, &tracked).is_none());
    }

    #[test]
    fn parse_character_profile_list_payload_reads_multiple_entries() {
        let payload = json!({
            "character_list": [
                {
                    "character_id": "100",
                    "name": { "first": "Alpha" },
                    "world_id": "10",
                    "faction_id": "3",
                    "battle_rank": { "value": "50" },
                    "outfit": { "alias": "TAG" }
                },
                {
                    "character_id": "200",
                    "name": { "first": "Bravo" },
                    "world_id": "1",
                    "faction_id": "1"
                }
            ]
        });
        let profiles = parse_character_profile_list_payload(&payload);
        assert_eq!(profiles.len(), 2);
        assert_eq!(profiles[0].character_id, "100");
        assert_eq!(profiles[0].name, "Alpha");
        assert_eq!(profiles[0].outfit_tag.as_deref(), Some("TAG"));
        assert_eq!(profiles[1].character_id, "200");
        assert_eq!(profiles[1].name, "Bravo");
    }

    #[test]
    fn side_channel_emits_active_player_upsert_for_gain_experience() {
        let mut side = CensusSideChannel::new("");
        let payload = json!({
            "event_name": "GainExperience",
            "character_id": "100",
            "team_id": "1",
            "world_id": "17"
        });
        let out = side.process_payload(&payload, 1_700_000_000.0);
        assert!(out.iter().any(|msg| matches!(
            msg,
            IncomingMessage::Legacy(env)
            if env.category == "active_player_upsert"
                && env.data["character_id"].as_str() == Some("100")
                && env.data["faction"].as_str() == Some("VS")
                && env.data["world_id"].as_str() == Some("1")
        )));
    }

    #[test]
    fn kill_event_uses_resolved_victim_name() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "100",
            "character_id": "200",
            "is_headshot": "0",
            "attacker_team_id": "1",
            "team_id": "2"
        });
        let mut resolver = CharacterResolver::new("");
        resolver.memo.insert(
            "200".to_owned(),
            PlayerCacheEntry {
                character_id: "200".to_owned(),
                name: "EnemyHeavy".to_owned(),
                ..Default::default()
            },
        );
        let out = extract_messages_for_payload_with_classifier(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            None,
            Some(&mut resolver),
            &EventCatalog::default(),
            &StreakTemplate::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::OverlayEvent(OverlayEvent::Kill { victim, .. }) if victim == "EnemyHeavy"
        )));
    }

    #[test]
    fn death_event_uses_resolved_killer_name() {
        let mut session = SessionAccumulator::default();
        let payload = json!({
            "event_name": "Death",
            "timestamp": "1700000001",
            "attacker_character_id": "300",
            "character_id": "100",
            "is_headshot": "0",
            "attacker_team_id": "2",
            "team_id": "1"
        });
        let mut resolver = CharacterResolver::new("");
        resolver.memo.insert(
            "300".to_owned(),
            PlayerCacheEntry {
                character_id: "300".to_owned(),
                name: "SneakyLA".to_owned(),
                ..Default::default()
            },
        );
        let out = extract_messages_for_payload_with_classifier(
            &payload,
            "100",
            1_700_000_001.0,
            4.0,
            &mut session,
            &VehicleEventMaps::default(),
            &FacilityMap::default(),
            None,
            Some(&mut resolver),
            &EventCatalog::default(),
            &StreakTemplate::default(),
        );
        assert!(out.iter().any(|m| matches!(
            m,
            IncomingMessage::OverlayEvent(OverlayEvent::Death { killer, .. }) if killer == "SneakyLA"
        )));
    }

    #[test]
    fn choose_sound_name_returns_member_from_list() {
        let sounds = vec!["a.ogg".to_owned(), "b.ogg".to_owned(), "c.ogg".to_owned()];
        let picked = choose_sound_name(&sounds).expect("sound should be picked");
        assert!(sounds.contains(&picked));
    }
}
pub fn lookup_character_by_name(
    service_id: &str,
    name: &str,
    db_path: Option<PathBuf>,
) -> std::result::Result<CharacterEntry, String> {
    let db = match db_path {
        Some(path) => CharacterDatabase::open(path).ok(),
        None => CharacterDatabase::open_default().ok(),
    };
    if let Some(db) = db.as_ref() {
        if let Ok(Some(cached)) = db.find_character_by_name(name) {
            return Ok(cached);
        }
    }

    let lower = name.to_lowercase();
    let url = format!(
        "https://census.daybreakgames.com/s:{}/get/ps2:v2/character?name.first_lower={}&c:resolve=world,outfit&c:show=character_id,name.first,world_id,faction_id,battle_rank",
        service_id,
        lower
    );

    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    let resp = client.get(&url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Census API error: {}", resp.status()));
    }

    let root: serde_json::Value = resp.json().map_err(|e| e.to_string())?;

    if let Some(list) = root.get("character_list").and_then(|v| v.as_array()) {
        if let Some(first) = list.first() {
            let id = first
                .get("character_id")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            let name_val = first
                .get("name")
                .and_then(|n| n.get("first"))
                .and_then(|v| v.as_str())
                .unwrap_or(name)
                .to_string();
            let world_id = first
                .get("world_id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());

            let entry = CharacterEntry {
                character_id: id,
                name: name_val,
                world_id,
            };
            if let Some(db) = db.as_ref() {
                let faction_id = first
                    .get("faction_id")
                    .and_then(|v| v.as_str())
                    .and_then(|raw| raw.parse::<i64>().ok())
                    .or_else(|| first.get("faction_id").and_then(Value::as_i64));
                let rank = first
                    .get("battle_rank")
                    .and_then(|rank| rank.get("value"))
                    .and_then(Value::as_i64);
                let outfit_tag = first
                    .get("outfit")
                    .and_then(|outfit| outfit.get("alias"))
                    .and_then(Value::as_str);
                let _ = db.save_char_to_db(
                    &entry.character_id,
                    &entry.name,
                    entry.world_id.as_deref(),
                    faction_id,
                    rank,
                    outfit_tag,
                );
            }
            return Ok(entry);
        }
    }

    Err(format!("Character '{}' not found", name))
}
