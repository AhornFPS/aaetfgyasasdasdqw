import os
import sys
import time
import traceback

# Ermittelt den Ordner, in dem die EXE oder das Skript liegt
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_asset_path(filename):
    if not filename: return ""
    return os.path.join(BASE_DIR, "assets", filename)

def clean_path(text):
    """Entfernt 'No file selected' und Pfade, gibt nur Dateinamen zurück."""
    if not text or "No file selected" in text:
        return ""
    return os.path.basename(text.strip())

# --- ERROR LOGGER ---
def log_exception(exc_type, exc_value, exc_traceback):
    with open("error_log.txt", "a") as f:
        f.write(f"\n--- CRASH LOG {time.ctime()} ---\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

# --- KONSTANTEN ---
CHEAT_OPTIONS = [
    "Aimbot", "Magic Bullet", "Hitbox Mod", "Triggerbot",
    "Wallhack (ESP)", "Radar Hack", "Speedhack", "Flying",
    "Teleport", "No Recoil/Spread", "Fire Rate Mod", "Unlimited Heat",
    "Instant Hit", "No Collision", "Invincibility", "Stat Padding"
]

CHEAT_DESCRIPTIONS = {
    "Aimbot": "Automated target acquisition that unnaturally snaps the crosshair to critical hit zones.",
    "Magic Bullet": "Manipulation of projectile vectors, allowing shots to hit targets even when not directly aimed at them.",
    "Hitbox Mod": "Artificial enlargement of player hitboxes, resulting in an unnaturally high hit-rate.",
    "Triggerbot": "Automated firing system that triggers the weapon instantly when a target enters the reticle.",
    "Wallhack (ESP)": "Tactical overlay showing player positions, health, and distances through solid terrain.",
    "Radar Hack": "External real-time position tracking of all units far beyond the range of in-game detection tools.",
    "Speedhack": "Illegal modification of movement speed (client-speed) exceeding normal gameplay mechanics.",
    "Flying": "Suspension of gravity constants, allowing the character to move freely through the air without a jetpack.",
    "Teleport": "Instantaneous movement between coordinates or snapping to a target's position.",
    "No Recoil/Spread": "Complete elimination of weapon kick and bullet spread for perfect accuracy at any range.",
    "Fire Rate Mod": "Technical increase of the weapon's rate of fire beyond the server-defined maximum.",
    "Unlimited Heat": "Manipulation of the heat mechanic to allow continuous firing without cooldown or ammo depletion.",
    "Instant Hit": "Removal of projectile travel time (bullet velocity), making shots hit the target instantaneously.",
    "No Collision": "Modification allowing the player to walk through walls and solid objects (NoClip).",
    "Invincibility": "Exploiting game memory to prevent taking damage from any source (God Mode).",
    "Stat Padding": "Coordinated actions to artificially inflate character statistics outside of normal competitive play."
}