import asyncio
import json
import time
import threading
import os
import websockets
import requests  # Wichtig für den Faction-Check beim Login

# --- FIX: Import der zentralen Pfad-Logik ---
from dior_utils import get_asset_path

# --- KONSTANTEN & MAPPINGS ---

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
    "Point Control": ["15", "16", "272", "556", "557"],
    "Sunderer Spawn": ["233"],
    "Base Capture": ["19", "598"],
    "Break Construction": ["604", "616", "628"],
    "Alert End": ["328"],
    "RoadKill": ["26"],
    "Domination": ["10"],
    "Revenge": ["11"],
    "Killstreak Stop": ["8"],
    "Bounty Kill": ["593"],
    "Gunner Assist": ["373", "314", "146", "148", "149", "150", "154", "155", "515", "681"]
}


class CensusWorker:
    def __init__(self, controller, service_id):
        self.c = controller
        self.s_id = service_id
        self.loop = None
        self.websocket = None
        self.event_cache = set()
        self.event_history = []

        # --- SUPPORT TRACKING (HIERHER VERSCHOBEN) ---
        self.support_streaks = {
            "Heal": 0,
            "Revive Given": 0,
            "Revive Taken": 0,
            "Resupply": 0,
            "Repair": 0
        }
        self.is_dead_state = False

    def start(self):
        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(self.listener())

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    # --- HELPER: ZENTRALE TRACKING LOGIK ---
    def _process_stat_event(self, category, is_revive_taken=False):
        """
        Zählt Support-Events hoch und resettet bei Respawn.
        Triggert Basis-Event (z.B. 'Heal') UND Meilenstein (z.B. 'Heal 100').
        """

        # 1. Reset Check
        # Wenn 'is_revive_taken' True ist, wurden wir wiederbelebt -> KEIN Reset der Streaks.
        # Wenn 'is_revive_taken' False ist (z.B. wir heilen jemanden), aber 'is_dead_state' noch True ist,
        # bedeutet das, wir sind respawned (Tod -> Spawn -> Heal) -> RESET.

        if is_revive_taken:
            # Wir leben wieder (durch Revive) -> Status resetten, aber Zähler behalten
            self.is_dead_state = False
        elif self.is_dead_state:
            # Wir machen was (Heal/Ammo), obwohl wir "tot" waren -> Respawn erkannt -> RESET
            self.c.add_log("SYS: Respawn detected via Action. Resetting Support Streaks.")
            for k in self.support_streaks:
                self.support_streaks[k] = 0
            self.is_dead_state = False

        # 2. Zählen (falls Kategorie existiert)
        if category in self.support_streaks:
            self.support_streaks[category] += 1
            count = self.support_streaks[category]

            # 3. Events feuern
            # A) Basis Event (damit z.B. bei jedem Revive Sound kommt, falls eingestellt)
            self.c.trigger_overlay_event(category)

            # B) Meilenstein Event (z.B. "Heal 100")
            # Wir feuern es einfach ab. Das Overlay ignoriert es, wenn nichts in der Config steht.
            milestone_event = f"{category} {count}"
            self.c.trigger_overlay_event(milestone_event)

            # Kleines Log für Debugging bei Runden Zahlen
            if count > 0 and (count % 10 == 0 or count in [25, 50, 100, 250]):
                self.c.add_log(f"STREAK: {milestone_event}")
        else:
            # Für Events ohne Counter (z.B. Base Capture) einfach nur triggern
            self.c.trigger_overlay_event(category)

    async def listener(self):
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

                    def get_stat_obj(cid, tid):
                        # 1. Ermittle die Fraktion des AKTUELLEN Events
                        current_faction_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")

                        if cid not in self.c.session_stats:
                            # NEUER EINTRAG
                            self.c.session_stats[cid] = {
                                "id": cid,
                                "name": self.c.name_cache.get(cid, "Searching..."),
                                "faction": current_faction_name,  # Setze Fraktion basierend auf Event
                                "k": 0, "d": 0, "a": 0, "hs": 0, "hsrkill": 0,
                                "revives_received": 0,
                                "start": time.time(),
                                "last_kill_time": time.time(),
                                "world_id": str(p.get("world_id", "0"))
                            }
                        else:
                            # BESTEHENDER EINTRAG
                            # Check: Ist der Spieler als "NSO" gespeichert, kämpft aber gerade für eine echte Fraktion?
                            obj = self.c.session_stats[cid]
                            if obj["faction"] == "NSO" and current_faction_name != "NSO":
                                obj["faction"] = current_faction_name

                        return self.c.session_stats[cid]

                    async for message in websocket:
                        if getattr(self.c, "needs_reconnect", False):
                            self.c.needs_reconnect = False
                            await websocket.close()
                            break

                        data = json.loads(message)
                        if "payload" in data:
                            p = data["payload"]
                            e_name = p.get("event_name")
                            payload_world = str(p.get("world_id", "0"))

                            # DUPLIKAT FILTER
                            uid = f"{e_name}_{p.get('timestamp')}_{p.get('character_id')}_{p.get('attacker_character_id')}"
                            if uid in self.event_cache: continue
                            self.event_cache.add(uid)
                            self.event_history.append(uid)
                            if len(self.event_history) > 500: self.event_cache.discard(self.event_history.pop(0))

                            # -------------------------------------------------
                            # 1. LOGIN / LOGOUT
                            # -------------------------------------------------
                            if e_name == "PlayerLogin":
                                c_id = p.get("character_id")

                                # Check if it's one of our tracked chars
                                for name, saved_id in self.c.char_data.items():
                                    if saved_id == c_id:
                                        self.c.current_character_id = c_id
                                        self.c.current_selected_char_name = name

                                        # UI Update (Thread-Safe via Invoke)
                                        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                                        if hasattr(self.c, 'ovl_config_win'):
                                            QMetaObject.invokeMethod(self.c.ovl_config_win.char_combo, "setCurrentText",
                                                                     Qt.ConnectionType.QueuedConnection,
                                                                     Q_ARG(str, name))

                                        # Server Switch
                                        if payload_world != "0" and payload_world != str(self.c.current_world_id):
                                            s_name = self.c.get_server_name_by_id(payload_world)
                                            self.c.switch_server(s_name, payload_world)

                                        # --- RESTORED FEATURE: LOGIN EVENT TRIGGER ---
                                        def trigger_login_event(cid_val):
                                            try:
                                                u = f"https://census.daybreakgames.com/{self.s_id}/get/ps2:v2/character/?character_id={cid_val}&c:show=faction_id"
                                                r = requests.get(u, timeout=3).json()
                                                f_id = "0"
                                                if r.get("returned", 0) > 0:
                                                    f_id = r["character_list"][0].get("faction_id", "0")

                                                f_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(f_id), "NSO")

                                                self.c.trigger_overlay_event(f"Login {f_tag}")
                                                self.c.add_log(f"AUTO-TRACK: {name} eingeloggt ({f_tag}).")
                                            except:
                                                pass

                                        threading.Thread(target=trigger_login_event, args=(c_id,), daemon=True).start()
                                        break

                            elif e_name == "PlayerLogout":
                                if p.get("character_id") == self.c.current_character_id:
                                    self.c.current_character_id = ""
                                    self.c.add_log("AUTO-TRACK: Ausgeloggt.")

                            # -------------------------------------------------
                            # SERVER FILTER
                            # -------------------------------------------------
                            track_id = p.get("character_id") or p.get("attacker_character_id")
                            if track_id and track_id != "0":
                                tid = p.get("team_id") or p.get("attacker_team_id")
                                f_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                                w_id = str(p.get("world_id", "0"))
                                self.c.active_players[track_id] = (time.time(), f_name, w_id)
                                if track_id not in self.c.name_cache:
                                    self.c.id_queue.put(track_id)

                            # -------------------------------------------------
                            # EVENT PROCESSING
                            # -------------------------------------------------
                            if e_name == "Death":
                                self._handle_death(p, get_stat_obj)
                            elif e_name == "GainExperience":
                                self._handle_experience(p, get_stat_obj)
                            elif e_name == "MetagameEvent":
                                self._handle_metagame(p)

            except Exception as e:
                self.c.add_log(f"Websocket Reconnect: {e}")
                await asyncio.sleep(5)

    def _handle_death(self, p, get_stat_obj):
        killer_id = p.get("attacker_character_id")
        victim_id = p.get("character_id")
        my_id = self.c.current_character_id
        is_hs = (p.get("is_headshot") == "1")
        weapon_id = p.get("attacker_weapon_id")

        # Global Stats
        if p.get("attacker_team_id") != p.get("team_id"):
            if killer_id and killer_id != "0" and killer_id != victim_id:
                w_info = self.c.item_db.get(weapon_id, {})
                cat = w_info.get("type", "Unknown")
                k_obj = get_stat_obj(killer_id, p.get("attacker_team_id"))
                k_obj["k"] += 1
                k_obj["last_kill_time"] = time.time()
                if cat in HSR_WEAPON_CATEGORY:
                    k_obj["hsrkill"] += 1
                    if is_hs: k_obj["hs"] += 1

            if victim_id and victim_id != "0":
                v_obj = get_stat_obj(victim_id, p.get("team_id"))
                v_obj["d"] += 1

        # MY EVENTS
        if my_id:
            icon_html = ""
            if is_hs:
                hs_icon = self.c.config.get("killfeed", {}).get("hs_icon", "headshot.png")

                # --- FIX: Nutze zentrales get_asset_path für EXE Support ---
                hs_path = get_asset_path(hs_icon).replace("\\", "/")

                if os.path.exists(hs_path):
                    icon_html = f'<img src="{hs_path}" width="19" height="19" style="vertical-align: middle;">&nbsp;'

            w_info = self.c.item_db.get(weapon_id, {})
            category = w_info.get("type", "Unknown")

            # A) KILLER
            if killer_id == my_id and victim_id != my_id:
                curr_time = time.time()
                if getattr(self.c, "last_victim_id", None) == victim_id and (
                        curr_time - getattr(self.c, "last_victim_time", 0)) < 0.5:
                    return
                self.c.last_victim_id = victim_id
                self.c.last_victim_time = curr_time

                if p.get("attacker_team_id") == p.get("team_id"):
                    self.c.trigger_auto_voice("tk")
                    self.c.trigger_overlay_event("Team Kill")
                else:
                    # Streak Logic
                    if self.c.config.get("streak", {}).get("active", True):
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

                    # -------------------------------------------------
                    # EVENT ERMITTLUNG (QUEUE LOGIC START)
                    # -------------------------------------------------

                    # 1. Basis-Events sammeln
                    base_events = []
                    weapon_name = w_info.get("name", "Unknown")

                    # Special IDs / Kategorien / Namen
                    if weapon_id in PS2_DETECTION["SPECIAL_IDS"]:
                        base_events.append(PS2_DETECTION["SPECIAL_IDS"][weapon_id])
                    elif category in PS2_DETECTION["CATEGORIES"]:
                        base_events.append(PS2_DETECTION["CATEGORIES"][category])
                    elif weapon_name in PS2_DETECTION["NAMES"]:
                        base_events.append(PS2_DETECTION["NAMES"][weapon_name])

                    if is_hs and "Headshot" not in base_events:
                        base_events.append("Headshot")

                    # 2. Streak Events
                    streak_event = None
                    streak_map = {
                        12: "Squad Wiper", 24: "Double Squad Wipe",
                        36: "Squad Lead's Nightmare", 48: "One Man Platoon"
                    }
                    if self.c.killstreak_count in streak_map:
                        streak_event = streak_map[self.c.killstreak_count]

                    # 3. Multi Events
                    multi_event = None
                    if self.c.kill_counter > 1:
                        multi_map = {
                            2: "Double Kill", 3: "Multi Kill", 4: "Mega Kill",
                            5: "Ultra Kill", 6: "Monster Kill", 7: "Ludicrous Kill",
                            9: "Holy Shit"
                        }
                        if self.c.kill_counter in multi_map:
                            multi_event = multi_map[self.c.kill_counter]

                    # -------------------------------------------------
                    # ENTSCHEIDUNG: QUEUE AN ODER AUS?
                    # -------------------------------------------------
                    is_queue_active = self.c.config.get("event_queue_active", True)

                    if is_queue_active:
                        # ALLES senden (Basis -> Multi -> Streak)
                        for evt in base_events: self.c.trigger_overlay_event(evt)
                        if multi_event: self.c.trigger_overlay_event(multi_event)
                        if streak_event: self.c.trigger_overlay_event(streak_event)
                    else:
                        # NUR PRIORITÄT senden (Streak > Multi > Base)
                        final_event = None
                        if streak_event:
                            final_event = streak_event
                        elif multi_event:
                            final_event = multi_event
                        elif base_events:
                            final_event = base_events[0]  # Nimm das erste (meist speziellste)

                        if final_event: self.c.trigger_overlay_event(final_event)

                    # -------------------------------------------------
                    self.c.trigger_overlay_event("Hitmarker")
                    base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

                    # Killfeed Message bauen
                    v_name = self.c.name_cache.get(victim_id, "Unknown")
                    raw_tag = getattr(self.c, "outfit_cache", {}).get(victim_id, "")
                    v_tag = f"[{raw_tag}] " if raw_tag else ""

                    s_vic = self.c.session_stats.get(victim_id, {})
                    try:
                        kd_str = f"{(s_vic.get('k', 0) / max(1, s_vic.get('d', 1))):.1f}"
                    except:
                        kd_str = "0.0"

                    msg = f"""<div style="{base_style}">
                                                {icon_html}<span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span> 
                                                <span style="color: #aaaaaa; font-size: 16px;"> ({kd_str})</span></div>"""

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

                    # Voice
                    v_load = p.get("character_loadout_id")
                    kd_val = float(kd_str)
                    if v_load in LOADOUT_MAP["max"]:
                        self.c.trigger_overlay_event("Max Kill")
                        self.c.trigger_auto_voice("kill_max")
                    if v_load in LOADOUT_MAP["infil"]:
                        self.c.trigger_overlay_event("Infil Kill")
                        self.c.trigger_auto_voice("kill_infil")
                    if kd_val >= 2.0:
                        self.c.trigger_auto_voice("kill_high_kd")
                    elif is_hs:
                        self.c.trigger_auto_voice("kill_hs")

            # B) VICTIM
            elif victim_id == my_id:
                # --- UPDATE: DEAD STATE SETZEN ---
                self.is_dead_state = True


                # --- KILLSTREAK LOGIK (Fix für "Double Death") ---
                if self.c.killstreak_count > 0:
                    self.c.saved_streak = self.c.killstreak_count
                    self.c.saved_factions = getattr(self.c, 'streak_factions', [])
                    self.c.saved_slots = getattr(self.c, 'streak_slot_map', [])
                else:
                    self.c.saved_streak = 0
                    self.c.saved_factions = []
                    self.c.saved_slots = []

                # Reset
                self.c.killstreak_count = 0
                self.c.streak_factions = []
                self.c.streak_slot_map = []
                self.c.is_dead = True
                self.c.update_streak_display()
                self.c.trigger_overlay_event("Death")

                if killer_id and killer_id != "0":
                    k_name = self.c.name_cache.get(killer_id, "Unknown")
                    raw_tag = getattr(self.c, "outfit_cache", {}).get(killer_id, "")
                    k_tag = f"[{raw_tag}] " if raw_tag else ""
                    k_vic = self.c.session_stats.get(killer_id, {})
                    try:
                        k_kd = f"{(k_vic.get('k', 0) / max(1, k_vic.get('d', 1))):.1f}"
                    except:
                        k_kd = "0.0"

                    # Auch hier den gleichen Style nutzen
                    base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

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
        if not self.c.current_character_id and char_id:
            for name, saved_id in self.c.char_data.items():
                if saved_id == char_id:
                    t_id = p.get("team_id", "0")
                    f_tag = {"1": "VS", "2": "NC", "3": "TR"}.get(str(t_id), "NSO")

                    self.c.current_character_id = char_id
                    self.c.current_selected_char_name = name

                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    if hasattr(self.c, 'ovl_config_win'):
                        QMetaObject.invokeMethod(self.c.ovl_config_win.char_combo, "setCurrentText",
                                                 Qt.ConnectionType.QueuedConnection,
                                                 Q_ARG(str, name))

                    self.c.trigger_overlay_event(f"Login {f_tag}")
                    self.c.add_log(f"AUTO-TRACK: {name} aktiv erkannt ({f_tag} - Late Join).")
                    break

        my_id = self.c.current_character_id

        # --- AB HIER: NORMALE XP LOGIK ---
        if exp_id in ["2", "3", "371", "372"]:
            a_obj = get_stat_obj(char_id, p.get("team_id"))
            a_obj["a"] += 1
        if exp_id in ["7", "53"]:
            r_obj = get_stat_obj(other_id, p.get("team_id"))
            # STATT Deaths abzuziehen, zählen wir Revives hoch
            # if r_obj["d"] > 0: r_obj["d"] -= 1
            r_obj["revives_received"] = r_obj.get("revives_received", 0) + 1

        # A) EVENTS DIE MIR PASSIEREN
        if my_id and other_id == my_id:
            if exp_id == "26":
                self.c.trigger_overlay_event("Get Roadkilled")

            if exp_id in ["7", "53"]:
                self.c.was_revived = True
                self.c.is_dead = False
                # Streak wiederherstellen
                self.c.killstreak_count = getattr(self.c, 'saved_streak', 0)
                self.c.streak_factions = getattr(self.c, 'saved_factions', [])
                self.c.streak_slot_map = getattr(self.c, 'saved_slots', [])
                self.c.update_streak_display()

                self.c.trigger_overlay_event("Revive Taken", is_revive_taken=True)
                self.c.trigger_auto_voice("revived")

                if self.c.config.get("killfeed", {}).get("show_revives", True):
                    m_name = self.c.name_cache.get(char_id, "Medic")

                    # Style Update
                    base_style = "font-family: 'Black Ops One', sans-serif; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;"

                    msg = f'<div style="{base_style}"><span style="color: #00ff00;">✚ REVIVED BY </span>{m_name}</div>'

                    if self.c.config.get("killfeed", {}).get("active", True):
                        if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

        # B) EVENTS DIE ICH MACHE
        if my_id and char_id == my_id:
            try:
                self.c.myTeamId = int(p.get("team_id", 0))
                self.c.myWorldID = int(p.get("world_id", 0))
                self.c.currentZone = int(p.get("zone_id", 0))

                payload_world = str(p.get("world_id", "0"))
                if payload_world != "0" and payload_world != str(self.c.current_world_id):
                    s_name = self.c.get_server_name_by_id(payload_world)
                    self.c.switch_server(s_name, payload_world)
            except:
                pass

            # --- NEUE ZÄHL-LOGIK ---
            # Anstatt direkt zu feuern, leiten wir es an _process_stat_event weiter.

            if exp_id in ["7", "53"]:
                # Revive Given zählen & triggern
                self._process_stat_event("Revive Given")
            else:
                # Alle anderen Support-Events (Heal, Resupply, etc.) aus der Liste prüfen
                for event_name, id_list in PS2_EXP_DETECTION.items():
                    if exp_id in id_list:
                        self._process_stat_event(event_name)
                        break

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
        except:
            pass