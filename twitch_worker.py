import socket
import threading
import time
import random # For random justinfan number
import requests
import os
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from dior_utils import get_user_data_dir
    BASE_DATA_DIR = get_user_data_dir()
except ImportError:
    # Fallback for standalone testing
    BASE_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Cache folder path (Creation moved to EmoteManager init)
CACHE_DIR = os.path.join(BASE_DATA_DIR, "_emote_cache")


def fetch_json(url):
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

class EmoteManager:
    def __init__(self):
        # Ensure Cache folder exists in a writable location
        if not os.path.exists(CACHE_DIR):
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
            except Exception as e:
                print(f"TWITCH: Could not create cache dir {CACHE_DIR}: {e}")

        # We map the emote code (e.g. "KEKW") to the local file path
        self.emote_files = {}
        self.emote_urls = {}

    def load_all_emotes(self, channel_name):
        print(f"TWITCH: Loading community emotes for {channel_name}...")
        try:
            # 1. Get User ID for the channel (needed for BTTV/FFZ/7TV)
            user_data = fetch_json(f"https://api.ivr.fi/v2/twitch/user?login={channel_name}")
            if not user_data:
                print("TWITCH: Could not fetch User ID. Skipping channel emotes.")
                user_id = None
            else:
                user_id = user_data[0]['id']

            # --- 2. 7TV (The most important source) ---
            if user_id:
                self._load_7tv(f"https://7tv.io/v3/users/twitch/{user_id}")
            self._load_7tv("https://7tv.io/v3/emote-sets/global")

            # --- 3. BetterTTV (BTTV) ---
            if user_id:
                self._load_bttv(f"https://api.betterttv.net/3/cached/users/twitch/{user_id}")
            self._load_bttv("https://api.betterttv.net/3/cached/emotes/global")

            # --- 4. FrankerFacez (FFZ) ---
            # FFZ often contains the classic Twitch emotes (Kappa, LUL) in its Global Set!
            if user_id:
                self._load_ffz(f"https://api.frankerfacez.com/v1/room/id/{user_id}")
            self._load_ffz("https://api.frankerfacez.com/v1/set/global")

            print(f"TWITCH: Done! Total emotes in library: {len(self.emote_urls)}")

        except Exception as e:
            print(f"TWITCH: Error in load_all_emotes: {e}")


    def _load_7tv(self, url):
        data = fetch_json(url)
        if not data: return

        items = []
        if 'emote_set' in data:
            items = data['emote_set']['emotes']
        elif 'emotes' in data:
            items = data['emotes']
        elif isinstance(data, list):
            items = data

        for e in items:
            name = e['name']
            try:
                host = e['data']['host']
                base = f"https:{host['url']}"
                files = host['files']

                target_file = None

                # IMPORTANT: We prefer GIF for animations, as Qt handles it better than WebP
                # We search from back (highest quality) to front
                for f in reversed(files):
                    if f['format'] == 'GIF':
                        target_file = f['name']
                        break

                # If no GIF, then WebP (but not AVIF!)
                if not target_file:
                    for f in reversed(files):
                        if f['format'] == 'WEBP':
                            target_file = f['name']
                            break

                # Fallback: Any format that is not AVIF
                if not target_file:
                    for f in files:
                        if f['format'] not in ['AVIF']:
                            target_file = f['name']
                            break

                if target_file:
                    self.emote_urls[name] = f"{base}/{target_file}"
            except:
                pass

    def _load_bttv(self, url):
        data = fetch_json(url)
        if not data: return
        items = data if isinstance(data, list) else data.get('channelEmotes', []) + data.get('sharedEmotes', [])
        for e in items:
            # BTTV provides GIFs (id/2x or id/3x)
            self.emote_urls[e['code']] = f"https://cdn.betterttv.net/emote/{e['id']}/2x"

    def _load_ffz(self, url):
        data = fetch_json(url)
        if not data: return
        if 'sets' in data:
            for s in data['sets'].values():
                for e in s['emoticons']:
                    urls = e['urls']
                    best = urls.get('4') or urls.get('2') or urls.get('1')
                    if best: self.emote_urls[e['name']] = f"https:{best}"


    def get_emote_html(self, code):
        """Downloads image, saves it to disk and returns <img> tag."""
        if code not in self.emote_urls:
            return None

        # Clean filename
        safe_code = "".join([c for c in code if c.isalnum() or c in ('_', '-')])

        # 1. Check: Is the path already in our runtime dictionary?
        if code in self.emote_files:
            filepath = self.emote_files[code]
            if os.path.exists(filepath):
                # FIX: ALWAYS Absolute Path + Forward Slashes
                abs_path = os.path.abspath(filepath).replace("\\", "/")
                # We use a custom prefix 'emote://' to force Qt NOT to search on the disk
                return f'<img src="emote://{abs_path}">'

        # 2. Check: If not in dictionary, check manually in folder (e.g. after restart)
        for ext in ['gif', 'webp', 'png']:
            test_path = os.path.join(CACHE_DIR, f"{safe_code}.{ext}")
            if os.path.exists(test_path):
                self.emote_files[code] = test_path
                abs_path = os.path.abspath(test_path).replace("\\", "/")
                return f'<img src="emote://{abs_path}">'

        # 3. Download: If not present at all
        url = self.emote_urls[code]
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                ctype = r.headers.get('Content-Type', '').lower()
                ext = "png"
                if "gif" in ctype or url.endswith(".gif"):
                    ext = "gif"
                elif "webp" in ctype or url.endswith(".webp"):
                    ext = "webp"

                filename = f"{safe_code}.{ext}"
                filepath = os.path.join(CACHE_DIR, filename)

                with open(filepath, "wb") as f:
                    f.write(r.content)

                self.emote_files[code] = filepath

                # FIX: Force absolute path even on first download
                abs_path = os.path.abspath(filepath).replace("\\", "/")
                return f'<img src="emote://{abs_path}">'
        except Exception:
            pass

        return None

    def parse_message(self, message):
        words = message.split(' ')
        new_words = []
        for word in words:
            # Check Emote
            img_tag = self.get_emote_html(word)
            if img_tag:
                new_words.append(img_tag)
            else:
                # HTML Escape
                safe = word.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                new_words.append(safe)
        return " ".join(new_words)


class TwitchWorker(QObject):
    new_message = pyqtSignal(str, str, str)
    status_changed = pyqtSignal(str)

    def __init__(self, channel, ignore_list=None, ignore_special=False):
        super().__init__()
        self.channel = channel.lower().strip().replace("#", "")
        self.ignore_list = [n.lower() for n in ignore_list] if ignore_list else []
        self.ignore_special = ignore_special
        self.running = False
        self.sock = None
        self.emote_mgr = EmoteManager()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def run(self):
        self.running = True
        self.status_changed.emit("LOADING EMOTES...")

        try:
            self.emote_mgr.load_all_emotes(self.channel)
        except Exception as e:
            print(f"Emote Setup Error: {e}")

        while self.running:
            self.status_changed.emit(f"JOINING #{self.channel}...")
            try:
                self.sock = socket.socket()
                self.sock.settimeout(10.0)
                self.sock.connect(('irc.chat.twitch.tv', 6667))
                self.sock.settimeout(None)

                # Random justinfan ID to avoid collisions
                nick = f"justinfan{random.randint(10000, 99999)}"

                # IMPORTANT: Every line MUST end with \r\n!
                self.sock.send(f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n".encode('utf-8'))
                self.sock.send(f"PASS oauth:kappa\r\n".encode('utf-8'))
                self.sock.send(f"NICK {nick}\r\n".encode('utf-8'))
                self.sock.send(f"JOIN #{self.channel}\r\n".encode('utf-8'))

                self.status_changed.emit(f"CONNECTED: #{self.channel}")

                buffer = ""
                while self.running:
                    try:
                        data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                        if not data:
                            print("TWITCH: Connection lost (empty data).")
                            break

                        buffer += data
                        while '\r\n' in buffer:  # IRC uses \r\n as separator
                            line, buffer = buffer.split('\r\n', 1)
                            if not line: continue

                            if line.startswith('PING'):
                                # Twitch wants a PONG with the same token back
                                self.sock.send(f"PONG {line.split()[1]}\r\n".encode('utf-8'))
                                continue

                            if "PRIVMSG" in line:
                                # --- TAG PARSING ---
                                tags = {}
                                if line.startswith("@"):
                                    tag_part, line = line[1:].split(" ", 1)
                                    tags = dict(item.split("=") for item in tag_part.split(";") if "=" in item)

                                # Extraction of user and message
                                parts = line.split(":", 2)
                                if len(parts) > 2:
                                    # The Login Name (lowercase)
                                    raw_user = parts[1].split("!")[0].lower()
                                    raw_msg = parts[2].strip()

                                    # Display Name (with case sensitivity from tags)
                                    display_name = tags.get("display-name", raw_user)
                                    user_color = tags.get("color", "#00f2ff")
                                    if not user_color: user_color = "#00f2ff"

                                    # --- IGNORE CHECK (Checking Login Name is safer) ---
                                    if raw_user in self.ignore_list:
                                        continue
                                    
                                    # --- SPECIAL CHAR CHECK ---
                                    if self.ignore_special and raw_msg.startswith("!"):
                                        continue

                                    # 1. Convert message to HTML
                                    html = self.emote_mgr.parse_message(raw_msg)

                                    # 2. Signal to GUI
                                    self.new_message.emit(display_name, html, user_color)

                    except socket.timeout:
                        continue # Normal if no messages
                    except socket.error as e:
                        print(f"TWITCH: Socket error during recv: {e}")
                        break
                    except Exception as e:
                        print(f"TWITCH: Loop Error: {e}")
            
            except (socket.error, Exception) as e:
                if self.running:
                    self.status_changed.emit(f"RECONNECTING (5s)...")
                    print(f"TWITCH: Connection failed: {e}. Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    break
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                self.sock = None

        self.status_changed.emit("DISCONNECTED")
