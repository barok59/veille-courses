import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import requests
from sources import SOURCES

# --- Paramètres ---
CENTRE = (50.5063, 3.0286)   # Gondecourt (Nord), à vérifier sur une carte
RAYON_KM = 20
DISTANCE_MIN_KM = 10
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "veille-courses-perso/1.0"}


# --- État ---
def load_state():
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("courses", {})
    state.setdefault("geo", {})
    state.setdefault("envois", [])
    state.setdefault("prochain_id", 1)
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def numeroter_existantes(state):
    """Donne un numéro aux courses déjà enregistrées qui n'en ont pas."""
    for info in state["courses"].values():
        info.setdefault("suivie", False)
        if "id" not in info:
            info["id"] = state["prochain_id"]
            state["prochain_id"] += 1


# --- Notifications ---
def notifier(message):
    if not WEBHOOK:
        print("[DRY RUN]", message)
        return
    requests.post(WEBHOOK, json={"content": message[:1900]}, timeout=15)


# --- Géographie ---
def distance_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
