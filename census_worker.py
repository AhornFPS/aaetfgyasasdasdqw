import asyncio
import json
import time
import threading
import sqlite3
import os
import requests
import websockets

# --- KONSTANTEN & MAPPINGS ---
S_ID = "s:1799912354"

PS2_DETECTION = {
    "CATEGORIES": {"Knife": "Knife Kill", "Grenade": "Nade Kill", "MAX": "Max Kill"},
    "NAMES": {"SpitFire Turret": "Spitfire Kill", "Spitfire Auto-Turret": "Spitfire Kill"},
    "SPECIAL_IDS": {
        "802512": "Spitfire Kill", "802514": "Spitfire Kill", "802515": "Spitfire Kill",
        "802516": "Spitfire Kill", "802517": "Spitfire Kill", "802518": "Spitfire Kill",
        "6005426": "Spitfire Kill", "6005427": "Spitfire Kill", "6009294": "Spitfire Kill",
        "650": "Tankmine Kill", "6005961": "Tankmine Kill", "6005962": "Tankmine Kill",
        "1045": "AP-Mine Kill", "1044": "AP-Mine Kill", "6005422": "AP-Mine Kill"
        # (Liste gekürzt für Übersicht, du kannst deine volle Liste hier einfügen)
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
    "Road Kill": ["26"],
    "Domination": ["10"],
    "Revenge": ["11"],
    "Killstreak Stop": ["8"],
    "Gunner Assist": ["373", "314", "146", "148", "149", "150", "154", "155", "515", "681"]
}


# Hilfsfunktion für Pfade (Da wir keinen Zugriff auf BASE_DIR vom Main haben)
def get_asset_path_local(filename):
    if not filename: return ""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", filename)


class CensusWorker:
    def __init__(self, controller):
        """
        :param controller: Referenz auf die DiorClientGUI Instanz (für Zugriff auf Stats, Config, etc.)
        """
        self.c = controller  # 'c' als Abkürzung für controller
        self.loop = None
        self.websocket = None
        self.event_cache = set()
        self.event_history = []

    def start(self):
        """Startet den Async-Loop im Hintergrund-Thread."""

        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(self.listener())

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    async def listener(self):
        uri = f"wss://push.planetside2.com/streaming?environment=ps2&service-id={S_ID}"

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

                    # Helper für Stats
                    def get_stat_obj(cid, tid):
                        if cid not in self.c.session_stats:
                            faction_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                            self.c.session_stats[cid] = {
                                "id": cid,
                                "name": self.c.name_cache.get(cid, "Searching..."),
                                "faction": faction_name,
                                "k": 0, "d": 0, "a": 0, "hs": 0, "hsrkill": 0,
                                "start": time.time(),
                                "last_kill_time": time.time()
                            }
                        return self.c.session_stats[cid]

                    async for message in websocket:
                        # Reconnect Logik vom Controller
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

                                        # GUI Update (Thread-Safe via Signal/Timer im Main Code oder direkten Methodenaufruf wenn sicher)
                                        # Wir rufen hier update_active_char auf, das loggt und switched
                                        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                                        if hasattr(self.c, 'ovl_config_win'):
                                            QMetaObject.invokeMethod(self.c.ovl_config_win.char_combo, "setCurrentText",
                                                                     Qt.ConnectionType.QueuedConnection,
                                                                     Q_ARG(str, name))

                                        self.c.add_log(f"AUTO-TRACK: {name} eingeloggt.")

                                        # Server Switch
                                        if payload_world != "0" and payload_world != str(self.c.current_world_id):
                                            s_name = self.c.get_server_name_by_id(payload_world)
                                            # Da switch_server GUI elemente anfasst, besser via Timer/Signal
                                            # Aber für einfaches Switching ist direkter Aufruf hier ok, da Logik-Variablen
                                            self.c.switch_server(s_name, payload_world)
                                        break

                            elif e_name == "PlayerLogout":
                                if p.get("character_id") == self.c.current_character_id:
                                    self.c.current_character_id = ""
                                    self.c.add_log("AUTO-TRACK: Ausgeloggt.")

                            # -------------------------------------------------
                            # SERVER FILTER & TRACKING
                            # -------------------------------------------------
                            if payload_world != "0" and payload_world != str(self.c.current_world_id):
                                continue

                            track_id = p.get("character_id") or p.get("attacker_character_id")
                            if track_id and track_id != "0":
                                tid = p.get("team_id") or p.get("attacker_team_id")
                                f_name = {"1": "VS", "2": "NC", "3": "TR"}.get(str(tid), "NSO")
                                self.c.active_players[track_id] = (time.time(), f_name)
                                if track_id not in self.c.name_cache:
                                    self.c.id_queue.put(track_id)

                            # -------------------------------------------------
                            # EVENT: DEATH
                            # -------------------------------------------------
                            if e_name == "Death":
                                self._handle_death(p, get_stat_obj)

                            # -------------------------------------------------
                            # EVENT: EXPERIENCE
                            # -------------------------------------------------
                            elif e_name == "GainExperience":
                                self._handle_experience(p, get_stat_obj)

                            # -------------------------------------------------
                            # EVENT: METAGAME
                            # -------------------------------------------------
                            elif e_name == "MetagameEvent":
                                self._handle_metagame(p)

            except Exception as e:
                self.c.add_log(f"Websocket Reconnect: {e}")
                await asyncio.sleep(5)

    def _handle_death(self, p, get_stat_obj):
        """Ausgelagerte Kill-Logik"""
        killer_id = p.get("attacker_character_id")
        victim_id = p.get("character_id")
        my_id = self.c.current_character_id
        is_hs = (p.get("is_headshot") == "1")
        weapon_id = p.get("attacker_weapon_id")

        # Globale Stats
        if p.get("attacker_team_id") != p.get("team_id"):
            if killer_id and killer_id != "0" and killer_id != victim_id:
                # Waffe holen
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

        # --- MEINE EVENTS ---
        if my_id:
            icon_html = ""
            if is_hs:
                hs_icon = self.c.config.get("killfeed", {}).get("hs_icon", "headshot.png")
                hs_path = get_asset_path_local(hs_icon).replace("\\", "/")
                if os.path.exists(hs_path):
                    icon_html = f'<img src="{hs_path}" width="40" height="40" style="vertical-align: middle;">&nbsp;'

            w_info = self.c.item_db.get(weapon_id, {})
            category = w_info.get("type", "Unknown")

            # A) KILLER
            if killer_id == my_id and victim_id != my_id:
                curr_time = time.time()
                # Dubletten
                if getattr(self.c, "last_victim_id", None) == victim_id and (
                        curr_time - getattr(self.c, "last_victim_time", 0)) < 0.5:
                    return
                self.c.last_victim_id = victim_id
                self.c.last_victim_time = curr_time

                # Team Kill
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

                    # Multi Kill
                    if curr_time - getattr(self.c, "last_kill_time", 0) <= self.c.streak_timeout:
                        self.c.kill_counter += 1
                    else:
                        self.c.kill_counter = 1
                    self.c.last_kill_time = curr_time

                    # Event Detection
                    weapon_name = w_info.get("name", "Unknown")
                    evt = None

                    # Hier muss auf self.c.item_db zugegriffen werden, aber PS2_DETECTION ist lokal in dieser Datei
                    if weapon_id in PS2_DETECTION["SPECIAL_IDS"]:
                        evt = PS2_DETECTION["SPECIAL_IDS"][weapon_id]
                    elif category in PS2_DETECTION["CATEGORIES"]:
                        evt = PS2_DETECTION["CATEGORIES"][category]
                    elif weapon_name in PS2_DETECTION["NAMES"]:
                        evt = PS2_DETECTION["NAMES"][weapon_name]

                    if is_hs and not evt: evt = "Headshot"

                    if evt: self.c.trigger_overlay_event(evt)
                    self.c.trigger_overlay_event("Hitmarker")

                    # Killfeed
                    v_name = self.c.name_cache.get(victim_id, "Unknown")
                    raw_tag = getattr(self.c, "outfit_cache", {}).get(victim_id, "")
                    if raw_tag is None: raw_tag = ""
                    v_tag = f"[{raw_tag}] " if raw_tag else ""

                    s_vic = self.c.session_stats.get(victim_id, {})
                    try:
                        kd_val = s_vic.get('k', 0) / max(1, s_vic.get('d', 1))
                        kd_str = f"{kd_val:.1f}"
                    except:
                        kd_str = "0.0"

                    msg = f"""<div style="font-family: 'Black Ops One'; font-size: 19px; color: white; text-align: right; margin-bottom: 2px;">
                            {icon_html}<span style="color: #888;">{v_tag}</span><span style="color: #ffffff;">{v_name}</span> 
                            <span style="color: #aaaaaa; font-size: 16px;"> ({kd_str})</span></div>"""

                    if self.c.overlay_win:
                        self.c.overlay_win.signals.killfeed_entry.emit(msg)

                    # Auto Voice
                    v_load = p.get("character_loadout_id")
                    if kd_val >= 2.0:
                        self.c.trigger_auto_voice("kill_high_kd")
                    elif v_load in LOADOUT_MAP["max"]:
                        self.c.trigger_auto_voice("kill_max")
                    elif v_load in LOADOUT_MAP["infil"]:
                        self.c.trigger_auto_voice("kill_infil")
                    elif is_hs:
                        self.c.trigger_auto_voice("kill_hs")

            # B) VICTIM
            elif victim_id == my_id:
                if self.c.killstreak_count > 0:
                    self.c.saved_streak = self.c.killstreak_count
                    self.c.saved_factions = getattr(self.c, 'streak_factions', [])
                    self.c.saved_slots = getattr(self.c, 'streak_slot_map', [])

                self.c.killstreak_count = 0
                self.c.streak_factions = []
                self.c.streak_slot_map = []
                self.c.is_dead = True
                self.c.update_streak_display()
                self.c.trigger_overlay_event("Death")

                if killer_id and killer_id != "0":
                    k_name = self.c.name_cache.get(killer_id, "Unknown")
                    raw_tag = getattr(self.c, "outfit_cache", {}).get(killer_id, "")
                    if raw_tag is None: raw_tag = ""
                    k_tag = f"[{raw_tag}] " if raw_tag else ""

                    k_vic = self.c.session_stats.get(killer_id, {})
                    try:
                        k_kd = f"{(k_vic.get('k', 0) / max(1, k_vic.get('d', 1))):.1f}"
                    except:
                        k_kd = "0.0"

                    msg = f"""<div style="font-family: 'Black Ops One'; font-size: 19px; text-shadow: 1px 1px 2px #000; margin-bottom: 2px; text-align: right;">
                            {icon_html}<span style="color: #888;">{k_tag}</span><span style="color: #ff4444;">{k_name}</span>
                            <span style="color: #aaa; font-size: 19px;"> ({k_kd})</span></div>"""

                    if self.c.overlay_win:
                        self.c.overlay_win.signals.killfeed_entry.emit(msg)

    def _handle_experience(self, p, get_stat_obj):
        """Ausgelagerte Exp-Logik"""
        exp_id = str(p.get("experience_id", "0"))
        other_id = p.get("other_id")
        char_id = p.get("character_id")
        my_id = self.c.current_character_id

        # Stats
        if exp_id in ["2", "3", "371", "372"]:
            a_obj = get_stat_obj(char_id, p.get("team_id"))
            a_obj["a"] += 1
        if exp_id in ["7", "53"]:
            r_obj = get_stat_obj(other_id, p.get("team_id"))
            if r_obj["d"] > 0: r_obj["d"] -= 1

        # Logic
        if my_id and other_id == my_id:
            if exp_id in ["7", "53"]:  # Revived
                self.c.was_revived = True
                self.c.is_dead = False

                # Restore Streak
                self.c.killstreak_count = getattr(self.c, 'saved_streak', 0)
                self.c.streak_factions = getattr(self.c, 'saved_factions', [])
                self.c.streak_slot_map = getattr(self.c, 'saved_slots', [])

                self.c.update_streak_display()
                self.c.trigger_overlay_event("Revive Taken")
                self.c.trigger_auto_voice("revived")

                if self.c.config.get("killfeed", {}).get("show_revives", True):
                    m_name = self.c.name_cache.get(char_id, "Medic")
                    msg = f'<div style="font-family: \'Black Ops One\'; font-size: 19px; color: white; text-align: right;"><span style="color: #00ff00;">✚ REVIVED BY </span>{m_name}</div>'
                    if self.c.overlay_win: self.c.overlay_win.signals.killfeed_entry.emit(msg)

        if my_id and char_id == my_id:
            try:
                self.c.myTeamId = int(p.get("team_id", 0))
                self.c.myWorldID = int(p.get("world_id", 0))
                self.c.currentZone = int(p.get("zone_id", 0))
            except:
                pass

            if exp_id in ["7", "53"]:
                self.c.trigger_overlay_event("Revive Given")
            else:
                for event_name, id_list in PS2_EXP_DETECTION.items():
                    if exp_id in id_list:
                        self.c.trigger_overlay_event(event_name)
                        break

    def _handle_metagame(self, p):
        state = p.get("metagame_event_state_name")
        if state != "ended": return

        try:
            world = int(p.get("world_id", 0))
            zone = int(p.get("zone_id", 0))
            if world != getattr(self.c, 'myWorldID', 0) or zone != getattr(self.c, 'currentZone', 0):
                return

            VS = float(p.get("faction_vs", 0))
            TR = float(p.get("faction_tr", 0))
            NC = float(p.get("faction_nc", 0))

            my_team = self.c.myTeamId
            won = False
            if my_team == 1 and VS > TR and VS > NC:
                won = True
            elif my_team == 2 and NC > TR and NC > VS:
                won = True
            elif my_team == 3 and TR > VS and TR > NC:
                won = True

            if won:
                self.c.trigger_overlay_event("Alert Win")
                self.c.add_log("EVENT: Alert Win!")
            else:
                self.c.trigger_overlay_event("Alert End")
        except:
            pass