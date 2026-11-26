import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

import requests
from sources import SOURCES

# --- Paramètres ---
CENTRE = (50.5063, 3.0286)   # Gondecourt (Nord), à vérifier sur une carte
RAYON_KM = 20
DISTANCE_MIN_KM = 10
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")
STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "veille-courses-perso/1.0"}
DISCORD_API = "https://discord.com/api/v10"


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
    state.setdefault("dernier_message_id", None)
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


# --- Commandes Discord (bot) ---
def lire_commandes(state):
    """Lit les nouveaux messages du salon et met à jour le champ 'suivie'."""
    if not BOT_TOKEN or not CHANNEL_ID:
        return

    headers = {"Authorization": f"Bot {BOT_TOKEN}", "User-Agent": "veille-courses-perso/1.0"}
    params = {"limit": 100}
    dernier = state.get("dernier_message_id")
    if dernier:
        params["after"] = dernier

    r = requests.get(f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
                     headers=headers, params=params, timeout=15)
    r.raise_for_status()
    messages = sorted(r.json(), key=lambda m: int(m["id"]))

    # Premier passage : on se place à la fin du salon sans rejouer l'historique
    if not dernier:
        if messages:
            state["dernier_message_id"] = messages[-1]["id"]
        return

    par_id = {info["id"]: info for info in state["courses"].values()}

    for m in messages:
        state["dernier_message_id"] = m["id"]
        if m.get("author", {}).get("bot"):
            continue

        texte = m.get("content", "").strip().lower()
        # « ne plus suivre » doit être testé avant « suivre »
        if texte.startswith("ne plus suivre"):
            valeur, action = texte[len("ne plus suivre"):], False
        elif texte.startswith("suivre"):
            valeur, action = texte[len("suivre"):], True
        else:
            continue

        for i in (int(x) for x in re.findall(r"\d+", valeur)):
            info = par_id.get(i)
            if info is None:
                notifier(f"❓ Numéro inconnu : {i}")
                continue
            info["suivie"] = action
            if action:
                notifier(f"✅ Suivie : **{info['nom']}** (#{i})")
            else:
                notifier(f"🚫 Plus suivie : **{info['nom']}** (#{i})")


# --- Géographie ---
def distance_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocoder(lieu, state):
    """Pour les sources qui ne donnent pas de coordonnées : Base Adresse Nationale."""
    if lieu in state["geo"]:
        return state["geo"][lieu]
    r = requests.get(
        "https://api-adresse.data.gouv.fr/search/",
        params={"q": lieu, "limit": 1}, headers=HEADERS, timeout=15,
    )
    feats = r.json().get("features", [])
    if not feats:
        return None
    lon, lat = feats[0]["geometry"]["coordinates"]
    state["geo"][lieu] = [lat, lon]
    return state["geo"][lieu]


def dans_zone(course, state):
    if "coords" in course:
        lat, lon = course["coords"]
    else:
        coords = geocoder(course["lieu"], state)
        if not coords:
            return False
        lat, lon = coords
    return distance_km(*CENTRE, lat, lon) <= RAYON_KM


def distance_suffisante(course):
    if not course.get("distances"):
        return True  # distance inconnue : on garde, à vérifier sur la fiche
    return any(d >= DISTANCE_MIN_KM for d in course["distances"])


# --- Principal ---
def main():
    rappels_seuls = len(sys.argv) > 1 and sys.argv[1] == "rappels"
    state = load_state()
    numeroter_existantes(state)
    now = dt.datetime.now()

    # 1. Scan des sources (une fois par heure)
    if not rappels_seuls:
        for scan in SOURCES:
            try:
                courses = scan()
            except Exception as e:
                print(f"Erreur scan {scan.__name__} : {e}")
                continue

            for c in courses:
                if not (dans_zone(c, state) and distance_suffisante(c)):
                    continue

                url = c["url"]
                info = state["courses"].get(url)

                if info is None:
                    # Nouvelle course : enregistrée avec un numéro, sans notification
                    state["courses"][url] = {
                        "id": state["prochain_id"],
                        "nom": c["nom"],
                        "date": c.get("date"),
                        "lieu": c["lieu"],
                        "distances": c.get("distances", []),
                        "ouverture": c.get("ouverture"),
                        "suivie": False,
                    }
                    state["prochain_id"] += 1
                    continue

                # Course déjà connue : mise à jour de la date d'ouverture
                nouvelle_ouv = c.get("ouverture")
                if nouvelle_ouv and nouvelle_ouv != info.get("ouverture"):
                    premiere_fois = not info.get("ouverture")
                    info["ouverture"] = nouvelle_ouv
                    if premiere_fois and info.get("suivie"):
                        notifier(f"📣 Ouverture des inscriptions annoncée : **{info['nom']}** (#{info['id']})\n{url}")

    # 2. Commandes Discord (dans les deux modes, lecture seule du salon)
    try:
        lire_commandes(state)
    except Exception as e:
        print(f"Erreur lecture commandes Discord : {e}")

    # 3. Rappels J-1 / H-1 (sans requête vers les sites)
    for url, info in state["courses"].items():
        if not info.get("suivie"):
            continue
        ouv_iso = info.get("ouverture")
        if not ouv_iso:
            continue
        ouv = dt.datetime.fromisoformat(ouv_iso)
        if ouv <= now:
            continue  # inscriptions déjà ouvertes
        for typ, delta, libelle in [
            ("J-1", dt.timedelta(days=1), "dans 24h"),
            ("H-1", dt.timedelta(hours=1), "dans 1h"),
        ]:
            cle = f"{url}|{typ}|{ouv_iso}"
            if cle in state["envois"]:
                continue
            if now >= ouv - delta:
                notifier(f"⏰ Inscriptions **{info['nom']}** (#{info['id']}) ouvrent {libelle} ({ouv:%d/%m %H:%M})\n{url}")
                state["envois"].append(cle)

    save_state(state)


if __name__ == "__main__":
    main()
