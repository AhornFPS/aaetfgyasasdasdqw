import asyncio
import json
import time
import threading
import os
from time import sleep

import websockets
import requests  # Important for faction check during login

# --- FIX: Import central path logic ---
from dior_utils import get_asset_path

# --- CONSTANTS & MAPPINGS ---

PS2_DETECTION = {
    "CATEGORIES": {"Knife": "Knife Kill", "Grenade": "Nade Kill"},
    "NAMES": {"SpitFire Turret": "Spitfire Kill", "Spitfire Auto-Turret": "Spitfire Kill"},
    "SPECIAL_IDS": {
        "802512": "Spitfire Kill", "802514": "Spitfire Kill", "802515": "Spitfire Kill",
        "802516": "Spitfire Kill", "802517": "Spitfire Kill", "802518": "Spitfire Kill",
        "6005426": "Spitfire Kill", "6005427": "Spitfire Kill", "6009294": "Spitfire Kill",
        "650": "Mine Kill", "6005961": "Mine Kill", "6005962": "Mine Kill",
        "1045": "Mine Kill", "1044": "Mine Kill", "6005422": "Mine Kill"
    }
}

LOADOUT_MAP = {
    "infil": ["1", "8", "15", "28"],
    "la": ["3", "10", "17", "29"],
    "medic": ["4", "11", "18", "30"],
    "engi": ["5", "12", "19", "31"],
    "heavy": ["6", "13", "20", "32"],
    "max": ["7", "14", "21", "45"]
}

HSR_WEAPON_CATEGORY = {
    "AI MAX (Left)", "AI MAX (Right)", "Amphibious Rifle", "Anti-Materiel Rifle", "Assault Rifle",
    "Carbine", "Heavy Weapon", "Hybrid Rifle", "LMG", "Pistol", "Scout Rifle", "Shotgun",
    "SMG", "Sniper Rifle", "Amphibious Sidearm", "Knife"
}

PS2_EXP_DETECTION = {
    "Revive": ["7", "53"],
    "Heal": ["4", "51"],
    "Resupply": ["34", "55"],
    "Point Control": ["272", "556", "557"],
    "Sunderer Spawn": ["233"],
    "Squad Spawn": ["56", "220"],
    "Base Capture": ["19", "598"],
    "Break Construction": ["604", "616", "628"],
    "RoadKill": ["26"],
    "Transport Assist": ["201", "230", "268", "350", "664"],
    "Domination": ["10"],
    "Revenge": ["11"],
    "Killstreak Stop": ["8"],
    "Bounty Kill": ["593"],
    "Gunner Kill": ["373", "314", "146", "148", "149", "150", "154", "155", "515", "681"]
}


class CensusWorker:
    def __init__(self, controller, service_id):
        self.c = controller
        self.s_id = service_id
        self.loop = None
        self.websocket = None
        self.msg_queue = None  # Buffer for incoming messages
        self.event_cache = set()
        self.event_history = []
        self.recent_deaths = []
        self.recent_deaths_max = 100
        self.gunner_match_delay = 0.2
        self.recent_deaths_lock = threading.Lock()
        self.recent_deaths_lock = threading.Lock()
        self.vehicle_gunner_kill_map, self.vehicle_destruction_map = self._load_vehicle_kill_maps()

        # --- SUPPORT TRACKING (MOVED HERE) ---
        self.support_streaks = {
            "Heal": 0,
            "Revive Given": 0,
            "Revive Taken": 0,
            "Resupply": 0,
            "Repair": 0
        }
        self.is_dead_state = False

    def _load_vehicle_kill_maps(self):
        gunner_map = {}
        destruction_map = {}
        path = get_asset_path("experience.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.c.add_log(f"ERR: Failed to load experience.json: {e}")
            return gunner_map, destruction_map

        excluded = ("Infantry", "Engineer Turret", "Engi Turret", "Phalanx", "Drop Pod", "Spitfire", "HIVE", "Construction")

        for entry in data.get("experience_list", []):
            desc = entry.get("description") or ""
            exp_id = str(entry.get("experience_id", "")).strip()
            if not exp_id: continue

            # 1. GUNNER KILLS
            if "Kill by" in desc and "Gunner" in desc and not desc.startswith("Player Kill by"):
                vehicle = desc.split(" Kill by ", 1)[0].strip()
                if not any(tag in vehicle for tag in excluded):
                    gunner_map[exp_id] = vehicle
            
            # 2. VEHICLE DESTRUCTION (Driver/Solo)
            # Pattern: "Vehicle Destruction - Flash"
            elif desc.startswith("Vehicle Destruction - "):
                vehicle_part = desc.split(" - ", 1)[1].strip()
                if not any(tag in vehicle_part for tag in excluded):
                    destruction_map[exp_id] = vehicle_part

        return gunner_map, destruction_map

    def start(self):
        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            
            # Create the queue inside the loop's thread
            self.msg_queue = asyncio.Queue()
            
            # Start the processor as a background task
            loop.create_task(self.processor())
            
            # Run the listener as the main task
            loop.run_until_complete(self.listener())

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    # --- HELPER: EVENT SUBSET TRIGGER ---
    def _trigger_subset_event(self, parent_event, specific_event):
        """
        Triggers a specific event (e.g., 'Kill Sunderer') if configured (img/snd),
        otherwise triggers the parent event (e.g., 'Vehicle Kill').
        """
        triggered_specific = False
        if specific_event:
            # Check Config
            evt_cfg = self.c.config.get("events", {}).get(specific_event, {})
            has_img = evt_cfg.get("img", "") != ""
            has_snd = evt_cfg.get("snd", "") != ""
            
            if has_img or has_snd:
                self.c.trigger_overlay_event(specific_event)
                triggered_specific = True
        
        # Fallback to Parent
        if not triggered_specific:
            self.c.trigger_overlay_event(parent_event)

    # --- HELPER: CENTRAL TRACKING LOGIC ---
    def _process_stat_event(self, category, is_revive_taken=False):
        """
        Increments support events and resets on respawn.
        Triggers base event (e.g., 'Heal') AND milestone (e.g., 'Heal 100').
        """
        

        # 2. Count (if category exists)
        if category in self.support_streaks:
            self.support_streaks[category] += 1
            count = self.support_streaks[category]

            # 3. Fire events
            # A) Base Event (so e.g. every revive triggers a sound if configured)
            self.c.trigger_overlay_event(category)

            # B) Milestone Event (e.g., "Heal 100")
            # We just fire it. The overlay ignores it if nothing is in the config.
            milestone_event = f"{category} {count}"
            self.c.trigger_overlay_event(milestone_event)

            if count > 0 and (count % 10 == 0 or count in [25, 50, 100, 250]):
                self.c.add_log(f"STREAK: {milestone_event}")
        else:
            # For events without counter (e.g., Base Capture) just trigger
            self.c.trigger_overlay_event(category)

    def _get_stat_obj(self, cid, tid, world_id):
        # 1. Determine the faction of the CURRENT event
        current_faction_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")

        if cid not in self.c.session_stats:
            # NEW ENTRY
            self.c.session_stats[cid] = {
                "id": cid,
                "name": self.c.name_cache.get(cid, "Searching..."),
                "faction": current_faction_name,  # Set faction based on event
                "k": 0, "d": 0, "a": 0, "hs": 0, "hsrkill": 0,
                "dhs": 0, "dhs_eligible": 0, # Death Headshot Tracking
                "revives_received": 0,
                "start": time.time(),
                "acc_t": 0, # Accumulated time in seconds
                "last_kill_time": time.time(),
                "world_id": str(world_id)
            }
        else:
            # EXISTING ENTRY
            obj = self.c.session_stats[cid]
            # Resume if paused
            if obj.get("start", 0) == 0:
                obj["start"] = time.time()
                self.c.add_log(f"TIMER: Session resumed for {obj.get('name')}")

            if obj["faction"] == "NSO" and current_faction_name != "NSO":
                obj["faction"] = current_faction_name

        return self.c.session_stats[cid]

    async def listener(self):
        """Websocket listener that only puts raw messages into the queue."""
        uri = f"wss://push.planetside2.com/streaming?environment=ps2&service-id={self.s_id}"

        while True:
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20, close_timeout=10) as websocket:
                    self.websocket = websocket

                    # SUBSCRIBE
                    msg = {
                        "service": "event", "action": "subscribe",
                        "characters": ["all"], "worlds": ["all"],
                        "eventNames": ["Death", "GainExperience", "PlayerLogin", "PlayerLogout", "MetagameEvent"]
                    }
                    await websocket.send(json.dumps(msg))
                    self.c.add_log("Websocket: GLOBAL MONITORING ACTIVE (All Servers)")

                    async for message in websocket:
                        # Add message to queue without processing
                        self.msg_queue.put_nowait(message)

                        if getattr(self.c, "needs_reconnect", False):
                            self.c.needs_reconnect = False
                            await websocket.close()
                            break

            except Exception as e:
                self.c.add_log(f"Websocket Reconnect: {e}")
                await asyncio.sleep(5)

    async def processor(self):
        """Async worker that processes messages from the queue using current logic."""
        while True:
            message = await self.msg_queue.get()
            try:
                data = json.loads(message)
                if "payload" in data:
                    p = data["payload"]
                    e_name = p.get("event_name")
                    payload_world = str(p.get("world_id", "0"))
                    # --- COMPATIBILITY LAYER ---
                    if payload_world == "17": payload_world = "1"
                    if payload_world == "13": payload_world = "10"

                    # DUPLIKAT FILTER (Improved)
                    if e_name == "GainExperience":
                        uid = f"EXP_{p.get('timestamp')}_{p.get('character_id')}_{p.get('experience_id')}_{p.get('other_id')}"
                    elif e_name == "Death":
                        uid = f"DTH_{p.get('timestamp')}_{p.get('character_id')}_{p.get('attacker_character_id')}_{p.get('attacker_weapon_id')}"
                    elif e_name == "MetagameEvent":
                        uid = f"MTG_{p.get('timestamp')}_{p.get('world_id')}_{p.get('metagame_event_id')}_{p.get('metagame_event_state_name')}"
                    else:
                        uid = f"{e_name}_{p.get('timestamp')}_{p.get('character_id', '0')}_{p.get('attacker_character_id', '0')}"

                    if uid in self.event_cache:
                        self.msg_queue.task_done()
                        continue
                    self.event_cache.add(uid)
                    self.event_history.append(uid)
                    if len(self.event_history) > 1000:  # Increased to 1000 for better safety
                        self.event_cache.discard(self.event_history.pop(0))

                    # Local helper for stat objects (adapted to use method)
                    def get_stat_obj(cid, tid):
                        return self._get_stat_obj(cid, tid, p.get("world_id", "0"))

                    # 1. LOGIN / LOGOUT
                    if e_name == "PlayerLogin":
                        c_id = p.get("character_id")
                        for name, saved_id in self.c.char_data.items():
                            if saved_id == c_id:
                                # RESET logic if character actually changed
                                if self.c.last_tracked_id and self.c.last_tracked_id != c_id:
                                    self.c.reset_streak_state()
                                
                                self.c.current_character_id = c_id
                                self.c.last_tracked_id = c_id
                                self.c.current_selected_char_name = name
                                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                                if hasattr(self.c, 'ovl_config_win'):
                                    QMetaObject.invokeMethod(self.c.ovl_config_win.char_combo, "setCurrentText",
                                                             Qt.ConnectionType.QueuedConnection, Q_ARG(str, name))
                                if payload_world != "0" and payload_world != str(self.c.current_world_id):
                                    s_name = self.c.get_server_name_by_id(payload_world)
                                    self.c.switch_server(s_name, payload_world)

                                # Resume or Start Timer
                                if c_id in self.c.session_stats:
                                    s_obj = self.c.session_stats[c_id]
                                    if s_obj.get("start", 0) == 0:
                                        s_obj["start"] = time.time()
                                        self.c.add_log(f"TIMER: Resumed session for {name}")
                                else:
                                    # Start NEW session immediately on login
                                    self._get_stat_obj(c_id, "0", payload_world)
                                    self.c.add_log(f"TIMER: Session started for {name} (at Login)")

                                def trigger_login_event(cid_val):
                                    try:
                                        u = f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/character/?character_id={cid_val}&c:show=faction_id"
                                        r = requests.get(u, timeout=3).json()
                                        f_id = "0"
                                        if r.get("returned", 0) > 0:
                                            f_id = r["character_list"][0].get("faction_id", "0")
                                        f_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(f_id), "NSO")
                                        self.c.trigger_overlay_event(f"Login {f_tag}")
                                        self.c.add_log(f"AUTO-TRACK: {name} logged in ({f_tag}).")
                                    except: pass
                                threading.Thread(target=trigger_login_event, args=(c_id,), daemon=True).start()
                                break
                    elif e_name == "PlayerLogout":
                        cid = p.get("character_id")
                        
                        # Fix: Remove from active counting immediately
                        if cid in self.c.active_players:
                            del self.c.active_players[cid]
                        if cid == self.c.current_character_id:
                            # Pause Timer
                            if cid in self.c.session_stats:
                                s_obj = self.c.session_stats[cid]
                                if s_obj.get("start", 0) > 0:
                                    elapsed = time.time() - s_obj["start"]
                                    s_obj["acc_t"] = s_obj.get("acc_t", 0) + elapsed
                                    s_obj["start"] = 0 # Paused
                                    self.c.add_log(f"TIMER: Session paused. Accumulated: {int(s_obj['acc_t'])}s")
                            
                            self.c.current_character_id = ""
                            self.c.add_log("AUTO-TRACK: Logged out.")

                    # 2. SERVER FILTER / PLAYER TRACKING (only track XP events and only the active side, other can be ignored)
                    track_id = p.get("character_id")   # or p.get("attacker_character_id")
                    if track_id and track_id != "0" and e_name == "GainExperience":
                        tid = p.get("team_id") # or p.get("attacker_team_id")
                        f_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                        w_id = str(p.get("world_id", "0"))
                        self.c.active_players[track_id] = (time.time(), f_name, w_id)
                        if track_id not in self.c.name_cache:
                            self.c.id_queue.put(track_id)

                    # 3. EVENT PROCESSING (Dispatch)
                    if e_name == "Death":
                        self._handle_death(p, p.get("world_id", "0"))
                        self._store_recent_death(p, p.get("world_id", "0"))
                    elif e_name == "GainExperience":
                        self._handle_experience(p, get_stat_obj)
                    elif e_name == "MetagameEvent":
                        self._handle_metagame(p)

            except Exception as e:
                self.c.add_log(f"Processor Error: {e}")

            self.msg_queue.task_done()

    def _store_recent_death(self, p, world_id):
        ts = 0
        try:
            ts = int(p.get("timestamp", "0"))
        except:
            ts = 0
        with self.recent_deaths_lock:
            self.recent_deaths.append({
                "payload": p,
                "world_id": world_id,
                "timestamp": ts,
                "gunner_matched": False
            })
            if len(self.recent_deaths) > self.recent_deaths_max:
                self.recent_deaths = self.recent_deaths[-self.recent_deaths_max:]

    def _handle_death(self, p, world_id):
        def get_stat_obj(cid, tid):
            return self._get_stat_obj(cid, tid, world_id)

        killer_id = p.get("attacker_character_id")
        victim_id = p.get("character_id")
        my_id = self.c.current_character_id
        is_hs = (p.get("is_headshot") == "1")
        weapon_id = p.get("attacker_weapon_id")

        # Helper: Is it a teamkill? (Suicide does not count as TK here)
        is_tk = (p.get("attacker_team_id") == p.get("team_id")) and (killer_id != victim_id)

        # -------------------------------------------------
        # 1. GLOBAL STATS (Dashboard)
        # -------------------------------------------------
        # ONLY count if it is NOT a teamkill!
        if not is_tk:
            w_info = self.c.item_db.get(weapon_id, {})
            cat = w_info.get("type", "Unknown")
            is_hs_weapon = cat in HSR_WEAPON_CATEGORY

            if killer_id and killer_id != "0" and killer_id != victim_id:
                k_obj = get_stat_obj(killer_id, p.get("attacker_team_id"))
                k_obj["k"] += 1
                k_obj["last_kill_time"] = time.time()

                if is_hs_weapon:
                    k_obj["hsrkill"] += 1
                    if is_hs: k_obj["hs"] += 1

            if victim_id and victim_id != "0":
                v_obj = get_stat_obj(victim_id, p.get("team_id"))
                v_obj["d"] += 1
                if is_hs_weapon:
                    if is_hs: v_obj["dhs"] += 1

        # -------------------------------------------------
        # 2. MY EVENTS (Overlay)
        # -------------------------------------------------
        if my_id:
            # Icon preparation
            icon_html = ""
            if is_hs:
                hs_icon = self.c.config.get("killfeed", {}).get("hs_icon", "Headshot.png")
                hs_path = get_asset_path(hs_icon).replace("\\", "/")
                if os.path.exists(hs_path):
                    # NEW: HS Icon Size from Config
                    hs_size = self.c.config.get("killfeed", {}).get("hs_icon_size", 19)
                    icon_html = f'<img src="{hs_path}" width="{hs_size}" height="{hs_size}" style="vertical-align: middle;">&nbsp;'

            w_info = self.c.item_db.get(weapon_id, {})
            category = w_info.get("type", "Unknown")
            
            # NEW: Font Size from Config (Robust)
            kf_cfg_raw = self.c.config.get("killfeed", {})
            kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
            kf_font = kf_cfg.get("font_size", 19)
            base_style = f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; margin-bottom: 2px; text-align: right;"

            # === A) I KILLED ===
            if killer_id == my_id and victim_id != my_id:
                curr_time = time.time()
                # Spam protection (Sometimes API sends twice)
                if getattr(self.c, "last_victim_id", None) == victim_id and (
                        curr_time - getattr(self.c, "last_victim_time", 0)) < 0.5:
                    return
                self.c.last_victim_id = victim_id
                self.c.last_victim_time = curr_time

                v_name = self.c.name_cache.get(victim_id, "Unknown")
                raw_tag = getattr(self.c, "outfit_cache", {}).get(victim_id, "")
                v_tag = f"[{raw_tag}] " if raw_tag else ""

                # --- CASE 1: TEAMKILL (I kill teammate) ---
                if is_tk:
                    self.c.trigger_auto_voice("tk")
                    self.c.trigger_overlay_event("Team Kill")

                    # Special feed entry
                    msg = f"""<div style="{base_style}">
                            <span style="color: #ffaa00;">⚠️ TEAMKILL </span>
                            <span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span> 
                            </div>"""

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

                    # IMPORTANT: Return here so no streak/multi-kill logic runs!
                    return

                    # --- CASE 2: NORMAL KILL (Enemy) ---
                else:
                    # Streak Logic
                    if self.c.config.get("streak", {}).get("active", True):
                        # --- NEW: RESPAWN CHECK ---
                        # If we were dead and NOT revived -> Respawn -> Reset!
                        # EXCEPTION: Teamkills (is_tk_death)
                        if self.c.is_dead and not self.c.was_revived and not getattr(self.c, "is_tk_death", False):
                            self.c.add_log("STREAK: Respawn detected (New Kill). Resetting.")
                            self.c.killstreak_count = 0
                            self.c.streak_factions = []
                            self.c.streak_slot_map = []
                            # Reset Support Streak
                            for k in self.support_streaks:
                                self.support_streaks[k] = 0
                        
                        # Clear TK flag, we just successfully killed (back alive)
                        self.c.is_tk_death = False

                        if self.c.killstreak_count == 0:
                            self.c.killstreak_count = 1
                            self.c.streak_factions = []
                            self.c.streak_slot_map = []
                        else:
                            self.c.killstreak_count += 1

                        v_team = p.get("team_id")
                        v_fac = {"1": "VS", "2": "NC", "3": "TR"}.get(str(v_team), "NSO")
                        self.c.streak_factions.append(v_fac)
                        self.c.streak_slot_map.append(self.c._get_random_slot())
                        self.c.is_dead = False
                        self.c.was_revived = False
                        self.c.update_streak_display()

                    # Multi Kill Logic
                    if curr_time - getattr(self.c, "last_kill_time", 0) <= self.c.streak_timeout:
                        self.c.kill_counter += 1
                    else:
                        self.c.kill_counter = 1
                    self.c.last_kill_time = curr_time

                    # EVENT DETERMINATION (QUEUE LOGIC START)
                    base_events = []
                    weapon_name = w_info.get("name", "Unknown")

                    if weapon_id in PS2_DETECTION["SPECIAL_IDS"]:
                        base_events.append(PS2_DETECTION["SPECIAL_IDS"][weapon_id])
                    elif category in PS2_DETECTION["CATEGORIES"]:
                        base_events.append(PS2_DETECTION["CATEGORIES"][category])
                    elif weapon_name in PS2_DETECTION["NAMES"]:
                        base_events.append(PS2_DETECTION["NAMES"][weapon_name])

                    if is_hs and "Headshot" not in base_events:
                        base_events.append("Headshot")

                    # Streak Events
                    streak_event = None
                    streak_map = {
                        12: "Squad Wiper", 24: "Double Squad Wipe",
                        36: "Squad Lead's Nightmare", 48: "One Man Platoon"
                    }
                    if self.c.killstreak_count in streak_map:
                        streak_event = streak_map[self.c.killstreak_count]

                    # Multi Events
                    multi_event = None
                    if self.c.kill_counter > 1:
                        multi_map = {
                            2: "Double Kill", 3: "Multi Kill", 4: "Mega Kill",
                            5: "Ultra Kill", 6: "Monster Kill", 7: "Ludacris Kill",
                            9: "Holy Shit"
                        }
                        if self.c.kill_counter in multi_map:
                            multi_event = multi_map[self.c.kill_counter]

                    # QUEUE ON OR OFF?
                    is_queue_active = self.c.config.get("event_queue_active", True)

                    # Trigger hitmarker first
                    self.c.trigger_overlay_event("Hitmarker")

                    if is_queue_active:
                        for evt in base_events: self.c.trigger_overlay_event(evt)
                        if multi_event: self.c.trigger_overlay_event(multi_event)
                        if streak_event: self.c.trigger_overlay_event(streak_event)
                    else:
                        final_event = None
                        if streak_event:
                            final_event = streak_event
                        elif multi_event:
                            final_event = multi_event
                        elif base_events:
                            final_event = base_events[0]
                        if final_event: self.c.trigger_overlay_event(final_event)



                    # Build Killfeed message (Normal)
                    s_vic = self.c.session_stats.get(victim_id, {})
                    try:
                        # Calculate real KD (respecting Revive Mode)
                        raw_d = s_vic.get('d', 1)
                        if self.c.kd_mode_revive:
                            raw_d = max(0, raw_d - s_vic.get('revives_received', 0))
                        kd_str = f"{(s_vic.get('k', 0) / max(1, raw_d)):.1f}"
                    except:
                        kd_str = "0.0"

                    msg = f"""<div style="{base_style}">
                            {icon_html}<span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span> 
                            <span style="color: #aaaaaa; font-size: 16px;"> ({kd_str})</span></div>"""

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

                    # Voice & Class Event Checks
                    v_load = p.get("character_loadout_id")
                    kd_val = float(kd_str)

                    # 1. CLASS DETECTION (Overlay Event)
                    class_event_name = "Kill"  # Default
                    detected_class = None

                    if v_load in LOADOUT_MAP["infil"]:   detected_class = "Kill Infil"
                    elif v_load in LOADOUT_MAP["la"]:    detected_class = "Kill Light Assault"
                    elif v_load in LOADOUT_MAP["medic"]: detected_class = "Kill Medic"
                    elif v_load in LOADOUT_MAP["engi"]:  detected_class = "Kill Engineer"
                    elif v_load in LOADOUT_MAP["heavy"]: detected_class = "Kill Heavy"
                    elif v_load in LOADOUT_MAP["max"]:   detected_class = "Kill MAX"

                    # 2. SUBSET LOGIC: Check if specific event is configured
                    if detected_class:
                        self._trigger_subset_event("Kill", detected_class)
                    else:
                        self.c.trigger_overlay_event("Kill")

                    # 4. VOICE MACROS (Keep existing logic + add others if needed later)
                    if v_load in LOADOUT_MAP["max"]:
                        self.c.trigger_auto_voice("kill_max")
                    if v_load in LOADOUT_MAP["infil"]:
                        self.c.trigger_auto_voice("kill_infil")
                    
                    if kd_val >= 2.0:
                        self.c.trigger_auto_voice("kill_high_kd")
                    elif is_hs:
                        self.c.trigger_auto_voice("kill_hs")

            # === B) I WAS KILLED (VICTIM) ===
            elif victim_id == my_id:
                # --- UPDATE: SET DEAD STATE ---
                self.is_dead_state = True

                # --- 1. CHECK DOUBLE DEATH (FIX FOR PERSISTENT STREAK) ---
                # If we are already marked as "dead" (i.e., not revived)
                # and die again, it was a respawn without kill/XP -> Streak is GONE.
                if self.c.is_dead and not self.c.was_revived:
                     self.c.add_log("STREAK: Double Death recognized (No Revive in between) -> Force Reset.")
                     self.c.killstreak_count = 0
                     self.c.streak_factions = []
                     self.c.streak_slot_map = []
                     # Reset Support Streak
                     for k in self.support_streaks:
                         self.support_streaks[k] = 0

                # --- 2. SAVE STATUS (BACKUP) ---
                if self.c.killstreak_count > 0:
                    self.c.saved_streak = self.c.killstreak_count
                    self.c.saved_factions = getattr(self.c, 'streak_factions', [])
                    self.c.saved_slots = getattr(self.c, 'streak_slot_map', [])
                else:
                    self.c.saved_streak = 0
                    self.c.saved_factions = []
                    self.c.saved_slots = []

                # --- 3. RESET DECISION ---
                if is_tk:
                    # CASE A: TEAMKILL -> NO RESET!
                    self.c.add_log("STREAK: Teamkill recognized - keep streak!")
                    self.c.is_tk_death = True
                    # We do NOT set the counter to 0.
                    # We do NOT empty the lists.
                    # The streak remains visible in the overlay.
                    
                    self.c.trigger_overlay_event("Team Kill Victim")

                else:
                    # CASE B: NORMAL DEATH / SUICIDE
                    self.c.is_tk_death = False
                    self.c.add_log("DEBUG: Handling Death -> Hiding Streak.")
                    self.c.hide_streak_display()

                    if killer_id == my_id:
                        self.c.trigger_overlay_event("Suicide")
                    else:
                        # --- NEU: Headshot Death Check ---
                        if is_hs:
                            self._trigger_subset_event("Death", "Headshot Death")
                        else:
                            self.c.trigger_overlay_event("Death")

                # --- 3. UPDATE STATUS ---
                self.c.is_dead = True
                self.c.was_revived = False
                self.c.add_log(f"DEBUG: Death State Set. Streak Count: {self.c.killstreak_count}")
                # self.c.update_streak_display()

                # --- 4. KILLFEED INFO ---
                if killer_id and killer_id != "0":
                    k_name = self.c.name_cache.get(killer_id, "Unknown")
                    raw_tag = getattr(self.c, "outfit_cache", {}).get(killer_id, "")
                    k_tag = f"[{raw_tag}] " if raw_tag else ""

                    # Get killer's KD
                    k_vic = self.c.session_stats.get(killer_id, {})
                    try:
                        raw_k_d = k_vic.get('d', 1)
                        if self.c.kd_mode_revive:
                            raw_k_d = max(0, raw_k_d - k_vic.get('revives_received', 0))
                        
                        k_kd = f"{(k_vic.get('k', 0) / max(1, raw_k_d)):.1f}"
                    except:
                        k_kd = "0.0"

                    

                    # TEAMKILL DISPLAY CHECK
                    if is_tk:
                        msg = f"""<div style="{base_style}">
                                            <span style="color: #ffaa00;">⚠️ TK BY </span>
                                            <span style="color: #888;">{k_tag}</span><span style="color: #ffffff;">{k_name}</span>
                                            </div>"""
                    else:
                        msg = f"""<div style="{base_style}">
                                            {icon_html}<span style="color: #888;">{k_tag}</span><span style="color: #ff4444;">{k_name}</span>
                                            <span style="color: #aaa; font-size: 16px;"> ({k_kd})</span></div>"""

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _handle_experience(self, p, get_stat_obj):
        exp_id = str(p.get("experience_id", "0"))
        other_id = p.get("other_id")
        char_id = p.get("character_id")

        # --- FEATURE: LATE START ACTIVATION (Auto-Detect Character) ---
        # Robust check: If incoming XP belongs to ANY of my characters, auto-switch to it!
        char_in_db = char_id in self.c.char_data.values()
        if char_in_db and char_id != self.c.current_character_id:
            for name, saved_id in self.c.char_data.items():
                if saved_id == char_id:
                    t_id = p.get("team_id", "0")
                    f_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(t_id), "NSO")

                    # RESET logic if character actually changed
                    if self.c.last_tracked_id and self.c.last_tracked_id != char_id:
                        self.c.reset_streak_state()

                    self.c.current_character_id = char_id
                    self.c.last_tracked_id = char_id
                    self.c.current_selected_char_name = name

                    # Update GUI dropdown safely
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    if hasattr(self.c, 'ovl_config_win'):
                        QMetaObject.invokeMethod(self.c.ovl_config_win.char_combo, "setCurrentText",
                                                 Qt.ConnectionType.QueuedConnection,
                                                 Q_ARG(str, name))

                    # Auto-Server Switch
                    world_id = str(p.get("world_id", self.c.current_world_id))
                    if world_id != str(self.c.current_world_id):
                        s_name = self.c.get_server_name_by_id(world_id)
                        self.c.switch_server(s_name, world_id)

                    # Resume Timer if in session stats
                    if char_id in self.c.session_stats:
                        s_obj = self.c.session_stats[char_id]
                        if s_obj.get("start", 0) == 0:
                            s_obj["start"] = time.time()
                            self.c.add_log(f"TIMER: Resumed session for {name} (Late Join)")

                    self.c.trigger_overlay_event(f"Login {f_tag}")
                    self.c.add_log(f"AUTO-TRACK: {name} recognized as active ({f_tag} - Late Join).")
                    break

        my_id = self.c.current_character_id

        # --- FROM HERE: NORMAL XP LOGIC ---
        if exp_id in ["2", "3", "371", "372"]:
            a_obj = get_stat_obj(char_id, p.get("team_id"))
            a_obj["a"] += 1
            if my_id and char_id == my_id:
                self.c.trigger_overlay_event("Assist")
        if exp_id in ["7", "53"]:
            r_obj = get_stat_obj(other_id, p.get("team_id"))
            # INSTEAD of subtracting deaths, we increment revives
            # if r_obj["d"] > 0: r_obj["d"] -= 1
            r_obj["revives_received"] = r_obj.get("revives_received", 0) + 1



        # A) EVENTS THAT HAPPEN TO ME
        if my_id and other_id == my_id:
            if exp_id == "26":
                self.c.trigger_overlay_event("Get RoadKilled")

            if exp_id in ["7", "53"]:
                self.c.was_revived = True
                self.c.is_dead = False
                self.is_dead_state = False
                self.c.is_tk_death = False  # Wiederbelebt -> Kein TK-Status mehr nötig
                
                # Do NOT restore streak (as we no longer delete it on death!)
                # We only update the display if it was hidden.
                self.c.update_streak_display()

                self.c.trigger_overlay_event("Revive Taken")
                self.c.trigger_auto_voice("revived")

                if self.c.config.get("killfeed", {}).get("show_revives", True):
                    m_name = self.c.name_cache.get(char_id, "Medic")

                    # NEW: Font Size from Config (Robust)
                    kf_cfg_raw = self.c.config.get("killfeed", {})
                    kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
                    kf_font = kf_cfg.get("font_size", 19)
                    base_style = f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; margin-bottom: 2px; text-align: right;"

                    msg = f'<div style="{base_style}"><span style="color: #00ff00;">✚ REVIVED BY </span>{m_name}</div>'

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

        # B) EVENTS THAT I DO
        if my_id and char_id == my_id:
            try:
                self.c.myTeamId = int(p.get("team_id", 0))
                self.c.myWorldID = int(p.get("world_id", 0))
                self.c.currentZone = int(p.get("zone_id", 0))

                self.c.myWorldID = int(p.get("world_id", 0))

                payload_world = str(p.get("world_id", "0"))

                # --- COMPATIBILITY LAYER ---
                if payload_world == "17": payload_world = "1"
                if payload_world == "13": payload_world = "10"

                if payload_world != "0" and payload_world != str(self.c.current_world_id):
                    s_name = self.c.get_server_name_by_id(payload_world)
                    self.c.switch_server(s_name, payload_world)
            except:
                pass

            # --- NEW COUNTING LOGIC ---
            # Instead of firing directly, we forward it to _process_stat_event.

            # 1. GUNNER KILLS (Gunner Seat)
            if exp_id in self.vehicle_gunner_kill_map:
                v_name = self.vehicle_gunner_kill_map[exp_id]
                self._trigger_subset_event("Gunner Vehicle Destruction", f"Gunner Kill {v_name}")
                self._emit_gunner_vehicle_killfeed(v_name)

            # 2. VEHICLE DESTRUCTION (Driver/Solo)
            if exp_id in self.vehicle_destruction_map:
                v_name = self.vehicle_destruction_map[exp_id]
                self._trigger_subset_event("Vehicle Destruction", f"Kill {v_name}")
                self._emit_vehicle_killfeed(v_name)

            if exp_id in ["7", "53"]:
                # Increment & trigger Revive Given
                self._process_stat_event("Revive Given")
            else:
                # Check all other support events (Heal, Resupply, etc.) from the list
                for event_name, id_list in PS2_EXP_DETECTION.items():
                    if exp_id in id_list:
                        self._process_stat_event(event_name)
                        if event_name == "Gunner Kill":
                            self._emit_gunner_killfeed_from_victim(p.get("other_id"))
                        break

    def _try_add_gunner_killfeed(self, gunner_id, exp_ts, retries=0):
        """
        Recursively tries to find the gunner kill.
        """
        if not gunner_id or gunner_id == "0":
            return

        match_entry = None

        # 1. ATTEMPT: Search in existing deaths
        with self.recent_deaths_lock:
            for entry in self.recent_deaths:
                d_p = entry["payload"]

                # Ignore already processed
                if entry.get("gunner_matched"):
                    continue

                # LOGIK: Der Angreifer (Attacker) im Death-Event muss unser Gunner sein
                if d_p.get("attacker_character_id") == gunner_id:
                    # Optional: Time check (Kill should be close to the XP event, +/- 10 sec)
                    # Often not necessary here, as recent_deaths is short anyway.

                    entry["gunner_matched"] = True
                    match_entry = entry
                    break

        # 2. ERFOLG
        if match_entry:
            self.c.add_log(f"DEBUG: Gunner kill found! (Retries left: {retries})")
            self._emit_gunner_killfeed(match_entry["payload"])
            return

        # 3. FAILURE -> RETRY OR ABORT
        if retries > 0:
            # Not there yet? Wait 0.5 seconds and try again (recursion)
            # We use threading.Timer to avoid blocking the main loop
            threading.Timer(
                0.5,
                self._try_add_gunner_killfeed,
                args=(gunner_id, exp_ts, retries - 1)
            ).start()
        else:
            # Still no matching death after 5 seconds (10 * 0.5)
            # This happens if the gunner e.g. only destroyed a vehicle (no death event for occupants)
            # or the death event was lost.
            self.c.add_log(f"DEBUG: Gunner Kill Time-Out. ID: {gunner_id}")
            pass

    def _emit_gunner_killfeed(self, p):
        if not self.c.config.get("killfeed", {}).get("active", True):
            return
        if not self.c.overlay_win:
            return

        victim_id = p.get("character_id")
        if not victim_id or victim_id == "0":
            return

        is_hs = (p.get("is_headshot") == "1")


        icon_html = ""
        if is_hs:
            hs_icon = self.c.config.get("killfeed", {}).get("hs_icon", "Headshot.png")
            hs_path = get_asset_path(hs_icon).replace("\\", "/")
            if os.path.exists(hs_path):
                hs_size = self.c.config.get("killfeed", {}).get("hs_icon_size", 19)
                icon_html = f'<img src="{hs_path}" width="{hs_size}" height="{hs_size}" style="vertical-align: middle;">&nbsp;'

        kf_cfg_raw = self.c.config.get("killfeed", {})
        kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
        kf_font = kf_cfg.get("font_size", 19)
        base_style = (
            f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; "
            "text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"
        )

        v_name = self.c.name_cache.get(victim_id, "Unknown")
        raw_tag = getattr(self.c, "outfit_cache", {}).get(victim_id, "")
        v_tag = f"[{raw_tag}] " if raw_tag else ""

        s_vic = self.c.session_stats.get(victim_id, {})
        try:
            raw_d = s_vic.get('d', 1)
            if self.c.kd_mode_revive:
                raw_d = max(0, raw_d - s_vic.get('revives_received', 0))
            kd_str = f"{(s_vic.get('k', 0) / max(1, raw_d)):.1f}"
        except:
            kd_str = "0.0"


        msg = f"""<div style="{base_style}">
                <span style="color: #ff8c00;">GUNNER </span>
                {icon_html}<span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span>
                <span style="color: #aaaaaa; font-size: 16px;"> ({kd_str})</span></div>"""

        self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _emit_gunner_killfeed_from_victim(self, victim_id):
        if not self.c.config.get("killfeed", {}).get("active", True):
            return
        if not self.c.config.get("killfeed", {}).get("show_gunner", True):
            return
        if not self.c.overlay_win:
            return
        if not victim_id or victim_id == "0":
            return

        kf_cfg_raw = self.c.config.get("killfeed", {})
        kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
        kf_font = kf_cfg.get("font_size", 19)
        base_style = (
            f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; "
            "text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"
        )

        v_name = self.c.name_cache.get(victim_id, "Unknown")
        raw_tag = getattr(self.c, "outfit_cache", {}).get(victim_id, "")
        v_tag = f"[{raw_tag}] " if raw_tag else ""

        msg = f"""<div style="{base_style}">
                <span style="color: #ff8c00;">GUNNER KILL </span>
                <span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span>
                </div>"""

        self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _emit_gunner_vehicle_killfeed(self, vehicle_name):
        if not self.c.config.get("killfeed", {}).get("active", True):
            return
        if not self.c.config.get("killfeed", {}).get("show_gunner", True):
            return
        if not self.c.overlay_win:
            return
        if not vehicle_name:
            return

        kf_cfg_raw = self.c.config.get("killfeed", {})
        kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
        kf_font = kf_cfg.get("font_size", 19)
        base_style = (
            f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; "
            "text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"
        )

        msg = f"""<div style="{base_style}">
                <span style="color: #ff8c00;">GUNNER KILL </span>
                <span style="color: #ffffff;">{vehicle_name}</span>
                </div>"""

        self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _emit_vehicle_killfeed(self, vehicle_name):
        if not self.c.config.get("killfeed", {}).get("active", True):
            return
        if not self.c.config.get("killfeed", {}).get("show_vehicle", True):
            return
        if not self.c.overlay_win:
            return
        if not vehicle_name:
            return

        kf_cfg_raw = self.c.config.get("killfeed", {})
        kf_cfg = kf_cfg_raw if isinstance(kf_cfg_raw, dict) else {}
        kf_font = kf_cfg.get("font_size", 19)
        base_style = (
            f"font-family: 'Black Ops One', sans-serif; font-size: {kf_font}px; "
            "text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"
        )

        msg = f"""<div style="{base_style}">
                <span style="color: #ff8c00;">VEHICLE DESTROYED </span>
                <span style="color: #ffffff;">{vehicle_name}</span>
                </div>"""

        self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _handle_metagame(self, p):
        state = p.get("metagame_event_state_name")
        if state != "ended": return
        try:
            world = int(p.get("world_id", 0))
            zone = int(p.get("zone_id", 0))
            if world != getattr(self.c, 'myWorldID', 0) or zone != getattr(self.c, 'currentZone', 0): return

            VS, TR, NC = float(p.get("faction_vs", 0)), float(p.get("faction_tr", 0)), float(p.get("faction_nc", 0))
            my_team = self.c.myTeamId
            won = (my_team == 1 and VS > TR and VS > NC) or (my_team == 2 and NC > TR and NC > VS) or (
                    my_team == 3 and TR > VS and TR > NC)

            if won:
                self.c.trigger_overlay_event("Alert Win")
                self.c.add_log("EVENT: Alert Win!")
            else:
                self.c.trigger_overlay_event("Alert End")
                self.c.add_log("EVENT: Alert End!")
        except:
            pass
