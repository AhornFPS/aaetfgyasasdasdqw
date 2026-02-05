import socket
import threading
import time
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
        print(f"TWITCH: Loading emotes for {channel_name}...")
        try:
            # User ID holen
            user_data = fetch_json(f"https://api.ivr.fi/v2/twitch/user?login={channel_name}")
            if not user_data: return
            user_id = user_data[0]['id']

            # 7TV (Hier gibt es die meisten animierten Emotes)
            self._load_7tv(f"https://7tv.io/v3/users/twitch/{user_id}")
            self._load_7tv("https://7tv.io/v3/emote-sets/global")

            # BetterTTV
            self._load_bttv(f"https://api.betterttv.net/3/cached/users/twitch/{user_id}")
            self._load_bttv("https://api.betterttv.net/3/cached/emotes/global")

            # FFZ
            self._load_ffz(f"https://api.frankerfacez.com/v1/room/id/{user_id}")
            self._load_ffz("https://api.frankerfacez.com/v1/set/global")

            print(f"TWITCH: Found {len(self.emote_urls)} emote URLs.")
        except Exception as e:
            print(f"TWITCH: Error loading emote lists: {e}")

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
                return f'<img src="file:///{abs_path}" height="28">'

        # 2. Check: Falls nicht im Dictionary, schau manuell im Ordner nach (z.B. nach Neustart)
        for ext in ['gif', 'webp', 'png']:
            test_path = os.path.join(CACHE_DIR, f"{safe_code}.{ext}")
            if os.path.exists(test_path):
                self.emote_files[code] = test_path
                abs_path = os.path.abspath(test_path).replace("\\", "/")
                return f'<img src="file:///{abs_path}" height="28">'

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
                return f'<img src="file:///{abs_path}" height="28">'
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

    def __init__(self, channel):
        super().__init__()
        self.channel = channel.lower().strip().replace("#", "")
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

        self.status_changed.emit(f"JOINING #{self.channel}...")
        try:
            self.sock = socket.socket()
            self.sock.settimeout(10.0)
            self.sock.connect(('irc.chat.twitch.tv', 6667))
            self.sock.settimeout(None)

            self.sock.send(f"PASS oauth:kappa\nNICK justinfan12345\nJOIN #{self.channel}\n".encode('utf-8'))
            self.status_changed.emit(f"CONNECTED: #{self.channel}")

            buffer = ""
            while self.running:
                try:
                    data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                    if not data: break

                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if line.startswith('PING'):
                            self.sock.send("PONG\n".encode('utf-8'))
                        elif "PRIVMSG" in line:
                            parts = line.split(":", 2)
                            if len(parts) > 2:
                                user_part = parts[1]
                                user = user_part.split("!", 1)[0]
                                msg = parts[2].strip()

                                # 1. Parsing (Hier werden Emotes ggf. erst runtergeladen)
                                html = self.emote_mgr.parse_message(msg)

                                # 2. Sicherheitscheck: Enthält die Nachricht ein Bild?
                                # Wenn ja, geben wir Windows eine winzige Atempause (10ms),
                                # um den Datei-Handle nach dem Download freizugeben.
                                if "<img" in html:
                                    time.sleep(0.01)

                                # 3. Signal an die GUI senden
                                self.new_message.emit(user, msg, html)
                except socket.error:
                    break
                except Exception as e:
                    print(f"Loop Error: {e}")

        except Exception as e:
            self.status_changed.emit(f"ERROR: {e}")
        finally:
            self.running = False
            self.status_changed.emit("DISCONNECTED")