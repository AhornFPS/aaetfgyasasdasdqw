import sqlite3

from dior_utils import DB_PATH


class DatabaseHandler:
    def __init__(self, db_name=None):
        self.db_name = db_name or DB_PATH
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # Cache Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS player_cache 
                          (character_id TEXT PRIMARY KEY, name TEXT, name_lower TEXT, 
                           faction_id INTEGER, world_id INTEGER, outfit_tag TEXT, 
                           battle_rank INTEGER, created_date TEXT, last_login TEXT, 
                           kills INTEGER, deaths INTEGER, score INTEGER, playtime INTEGER,
                           m30_kills INTEGER, m30_deaths INTEGER, m30_score INTEGER, m30_time INTEGER)''')
        # My Characters Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS my_chars 
                          (character_id TEXT PRIMARY KEY, name TEXT)''')
        conn.commit()
        conn.close()

    def load_my_chars(self):
        """Lädt eigene Charaktere für das Dropdown."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT name, character_id FROM my_chars")
        data = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return data

    def load_player_cache(self):
        """Lädt den Namens-Cache für den Killfeed."""
        try:
            conn = sqlite3.connect(self.db_name)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT character_id, name, outfit_tag FROM player_cache")
            rows = cursor.fetchall()
            conn.close()

            # Gibt zwei Dictionaries zurück: Names und Outfits
            names = {row['character_id']: row['name'] for row in rows}
            outfits = {row['character_id']: row['outfit_tag'] for row in rows}
            return names, outfits
        except Exception as e:
            print(f"DB Error: {e}")
            return {}, {}

    def save_char_to_db(self, cid, name, world_id, faction_id=0, rank=0, tag=""):
        """Speichert einen Charakter (Thread-Safe, da neue Connection)."""
        conn = sqlite3.connect(self.db_name)
        conn.execute(
            "INSERT OR REPLACE INTO player_cache (character_id, name, faction_id, battle_rank, outfit_tag, world_id) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, name, faction_id, rank, tag, world_id))
        # Auch in "My Chars" speichern (fürs Tracking)
        conn.execute("INSERT OR REPLACE INTO my_chars (name, character_id) VALUES (?, ?)", (name, cid))
        conn.commit()
        conn.close()

    def remove_my_char(self, name):
        conn = sqlite3.connect(self.db_name)
        conn.execute("DELETE FROM my_chars WHERE name=?", (name,))
        conn.commit()
        conn.close()
