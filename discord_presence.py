import time


class DiscordPresenceManager:
    CLIENT_ID = "363412528308682752"

    def __init__(self, log_func=None):
        self._log = log_func
        self._Presence = None
        self._rpc = None
        self._enabled = False
        self._connected = False
        self._start_ts = int(time.time())
        self._last_payload = None
        self._last_update_ts = 0.0
        self._last_connect_try_ts = 0.0
        self._min_update_interval_sec = 5.0
        self._reconnect_backoff_sec = 10.0

    def _add_log(self, msg):
        if callable(self._log):
            try:
                self._log(msg)
            except Exception:
                pass

    def start(self):
        self._enabled = True
        if self._Presence is None:
            try:
                from pypresence import Presence
                self._Presence = Presence
            except Exception:
                self._enabled = False
                self._add_log("DISCORD: pypresence missing. Install with: pip install pypresence")
                return
        if self._connected:
            return
        self._connect()

    def _connect(self):
        if not self._enabled or self._Presence is None:
            return False
        now = time.time()
        if now - self._last_connect_try_ts < self._reconnect_backoff_sec:
            return False
        self._last_connect_try_ts = now
        try:
            self._rpc = self._Presence(self.CLIENT_ID)
            self._rpc.connect()
            self._connected = True
            self._add_log("DISCORD: RPC connected.")
            return True
        except Exception:
            self._rpc = None
            self._connected = False
            return False

    @staticmethod
    def _trim(value, max_len):
        value = str(value or "").strip()
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

    def update_presence(self, character_name, server_name, base_name):
        if not self._enabled:
            return
        if not self._connected and not self._connect():
            return

        safe_character = self._trim(character_name or "Unknown", 48)
        safe_server = self._trim(server_name or "Unknown Server", 40)
        safe_base = self._trim(base_name or "", 48)

        state = f"Playing {safe_character} on {safe_server}."
        if safe_base:
            state = f"Playing {safe_character} on {safe_server} around {safe_base}"
        state = self._trim(state, 128)

        payload = {
            "name": "Better Planetside",
            "details": "PlanetSide 2",
            "state": state,
            "buttons": [{"label": "Join", "url": "steam://rungameid/218230"}],
            "instance": False,
            "start": self._start_ts,
            "activity_type": 0,
        }

        now = time.time()
        if payload == self._last_payload and (now - self._last_update_ts) < self._min_update_interval_sec:
            return

        try:
            self._rpc.update(**payload)
            self._last_payload = payload
            self._last_update_ts = now
        except Exception:
            self._connected = False
            self._rpc = None

    def clear_presence(self):
        self._last_payload = None
        self._last_update_ts = 0.0
        if not self._enabled:
            return
        rpc = self._rpc
        if rpc is None:
            self._connected = False
            return
        try:
            rpc.clear()
            # Give Discord IPC a brief moment to flush the clear command.
            time.sleep(0.12)
        except Exception:
            pass
        try:
            rpc.close()
        except Exception:
            pass
        self._connected = False
        self._rpc = None

    def close(self):
        self.clear_presence()
        self._enabled = False
