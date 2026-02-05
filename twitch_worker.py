import socket
import threading
import time
import random # Für zufällige justinfan Nummer
import requests
import os
from PyQt6.QtCore import QObject, pyqtSignal

# Cache Ordner erstellen
CACHE_DIR = os.path.join(os.getcwd(), "_emote_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


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
        # Wir mappen den Emote-Code (z.B. "KEKW") auf den lokalen Dateipfad
        self.emote_files = {}
        self.emote_urls = {}

    def load_all_emotes(self, channel_name):
        print(f"TWITCH: Loading community emotes for {channel_name}...")
        try:
            # 1. User ID für den Kanal holen (wird für BTTV/FFZ/7TV benötigt)
            user_data = fetch_json(f"https://api.ivr.fi/v2/twitch/user?login={channel_name}")
            if not user_data:
                print("TWITCH: Could not fetch User ID. Skipping channel emotes.")
                user_id = None
            else:
                user_id = user_data[0]['id']

            # --- 2. 7TV (Die wichtigste Quelle) ---
            if user_id:
                self._load_7tv(f"https://7tv.io/v3/users/twitch/{user_id}")
            self._load_7tv("https://7tv.io/v3/emote-sets/global")

            # --- 3. BetterTTV (BTTV) ---
            if user_id:
                self._load_bttv(f"https://api.betterttv.net/3/cached/users/twitch/{user_id}")
            self._load_bttv("https://api.betterttv.net/3/cached/emotes/global")

            # --- 4. FrankerFacez (FFZ) ---
            # FFZ enthält oft die klassischen Twitch-Emotes (Kappa, LUL) in ihrem Global-Set!
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

                # WICHTIG: Wir bevorzugen GIF für Animationen, da Qt das besser kann als WebP
                # Wir suchen von hinten (höchste Qualität) nach vorne
                for f in reversed(files):
                    if f['format'] == 'GIF':
                        target_file = f['name']
                        break

                # Wenn kein GIF, dann WebP (aber nicht AVIF!)
                if not target_file:
                    for f in reversed(files):
                        if f['format'] == 'WEBP':
                            target_file = f['name']
                            break

                # Fallback: Irgendein Format, das nicht AVIF ist
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
            # BTTV liefert GIFs (id/2x oder id/3x)
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
        """Lädt Bild herunter, speichert es auf Disk und gibt <img> Tag zurück."""
        if code not in self.emote_urls:
            return None

        # Dateiname säubern
        safe_code = "".join([c for c in code if c.isalnum() or c in ('_', '-')])

        # 1. Check: Ist der Pfad bereits in unserem Laufzeit-Dictionary?
        if code in self.emote_files:
            filepath = self.emote_files[code]
            if os.path.exists(filepath):
                # FIX: IMMER Absoluter Pfad + Forward Slashes
                abs_path = os.path.abspath(filepath).replace("\\", "/")
                # Wir nutzen ein Custom-Prefix 'emote://', um Qt zu zwingen, NICHT auf der Festplatte zu suchen
                return f'<img src="emote://{abs_path}" height="28">'

        # 2. Check: Falls nicht im Dictionary, schau manuell im Ordner nach (z.B. nach Neustart)
        for ext in ['gif', 'webp', 'png']:
            test_path = os.path.join(CACHE_DIR, f"{safe_code}.{ext}")
            if os.path.exists(test_path):
                self.emote_files[code] = test_path
                abs_path = os.path.abspath(test_path).replace("\\", "/")
                return f'<img src="emote://{abs_path}" height="28">'

        # 3. Download: Falls gar nicht vorhanden
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

                # FIX: Auch beim ersten Download absoluten Pfad erzwingen
                abs_path = os.path.abspath(filepath).replace("\\", "/")
                return f'<img src="emote://{abs_path}" height="28">'
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

    def __init__(self, channel, ignore_list=None):
        super().__init__()
        self.channel = channel.lower().strip().replace("#", "")
        self.ignore_list = [n.lower() for n in ignore_list] if ignore_list else []
        self.running = False
        self.sock = None
        self.emote_mgr = EmoteManager()

    def run(self):
        self.running = True
        self.status_changed.emit("LOADING EMOTES...")

        try:
            self.emote_mgr.load_all_emotes(self.channel)
        except Exception as e:
            print(f"Emote Setup Error: {e}")

        self.status_changed.emit(f"JOINING #{self.channel}...")
        try:
            self.sock = socket.socket()
            self.sock.settimeout(10.0)
            self.sock.connect(('irc.chat.twitch.tv', 6667))
            self.sock.settimeout(None)

            # Zufällige justinfan ID um Kollisionen zu vermeiden
            nick = f"justinfan{random.randint(10000, 99999)}"

            # WICHTIG: Jede Zeile MUSS mit \r\n enden!
            self.sock.send(f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n".encode('utf-8'))
            self.sock.send(f"PASS oauth:kappa\r\n".encode('utf-8'))
            self.sock.send(f"NICK {nick}\r\n".encode('utf-8'))
            self.sock.send(f"JOIN #{self.channel}\r\n".encode('utf-8'))

            self.status_changed.emit(f"CONNECTED: #{self.channel}")

            buffer = ""
            while self.running:
                try:
                    data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                    if not data: break

                    buffer += data
                    while '\r\n' in buffer:  # IRC nutzt \r\n als Trenner
                        line, buffer = buffer.split('\r\n', 1)
                        if not line: continue

                        if line.startswith('PING'):
                            # Twitch will ein PONG mit dem gleichen Token zurück
                            self.sock.send(f"PONG {line.split()[1]}\r\n".encode('utf-8'))
                            continue

                        if "PRIVMSG" in line:
                            # --- TAG PARSING ---
                            tags = {}
                            if line.startswith("@"):
                                tag_part, line = line[1:].split(" ", 1)
                                tags = dict(item.split("=") for item in tag_part.split(";") if "=" in item)

                            # Extraktion von User und Nachricht
                            parts = line.split(":", 2)
                            if len(parts) > 2:
                                # Der Login-Name (kleingeschrieben)
                                raw_user = parts[1].split("!")[0].lower()
                                raw_msg = parts[2].strip()

                                # Display Name (mit Groß/Kleinschreibung aus den Tags)
                                display_name = tags.get("display-name", raw_user)
                                user_color = tags.get("color", "#00f2ff")
                                if not user_color: user_color = "#00f2ff"

                                # --- IGNORE CHECK (Login-Name prüfen ist sicherer) ---
                                if raw_user in self.ignore_list:
                                    continue

                                # 1. Nachricht in HTML umwandeln
                                html = self.emote_mgr.parse_message(raw_msg)

                                # 2. Signal an die GUI
                                self.new_message.emit(display_name, html, user_color)

                except socket.error:
                    break
                except Exception as e:
                    print(f"Loop Error: {e}")

        except Exception as e:
            self.status_changed.emit(f"ERROR: {e}")
        finally:
            self.running = False
            self.status_changed.emit("DISCONNECTED")