import json
import math
import os
import datetime as dt
from pathlib import Path

import requests
from sources import SOURCES

# --- Paramètres ---
CENTRE = (50.5063, 3.0286)  # Gondecourt (Nord), à vérifier sur une carte
RAYON_KM = 20
DISTANCE_MIN_KM = 10
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "veille-courses-perso/1.0"}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"courses": {}, "geo": {}, "envois": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def notifier(message):
    if not WEBHOOK:
        print("[DRY RUN]", message)
        return
    requests.post(WEBHOOK, json={"content": message[:1900]}, timeout=15)


def distance_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau (formule de Haversine)."""
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocoder(lieu, state):
    """Convertit un lieu en coordonnées via la Base Adresse Nationale (gratuite, sans clé)."""
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
    state["geo"][lieu] = (lat, lon)
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
    if not course["distances"]:
        return True  # distance inconnue : on garde, à vérifier sur la fiche
    return any(d >= DISTANCE_MIN_KM for d in course["distances"])


def main():
    state = load_state()
    now = dt.datetime.now()  # heure locale du serveur : configurée en Europe/Paris dans le workflow

    # 1. Scanner les sources
    for scan in SOURCES:
        try:
            courses = scan()
        except Exception as e:
            notifier(f"⚠️ Erreur de scan {scan.__name__} : {e}")
            continue

        for c in courses:
            if not (dans_zone(c, state) and distance_suffisante(c)):
                continue

            url = c["url"]
            connue = state["courses"].get(url)

            if connue is None:
                notifier(
                    f"🆕 Nouvelle course : **{c['nom']}** le {c['date']} "
                    f"({c['lieu']}, distances : {', '.join(str(d) + ' km' for d in c['distances'])})\n{url}"
                )
                state["courses"][url] = {"nom": c["nom"], "ouverture": c.get("ouverture")}
            elif not connue.get("ouverture") and c.get("ouverture"):
                notifier(f"📣 Ouverture des inscriptions annoncée : **{c['nom']}**\n{url}")
                connue["ouverture"] = c["ouverture"]

            # Mettre à jour la date d'ouverture connue
            state["courses"][url]["ouverture"] = c.get("ouverture")
    print(len(courses))
    
    # 2. Envoyer les rappels J-1 et H-1
    for url, info in state["courses"].items():
        ouv_iso = info.get("ouverture")
        if not ouv_iso:
            continue
        ouv = dt.datetime.fromisoformat(ouv_iso)
        if ouv <= now:
            continue  # inscriptions déjà ouvertes : rien à rappeler
        for typ, delta, libelle in [
            ("J-1", dt.timedelta(days=1), "dans 24h"),
            ("H-1", dt.timedelta(hours=1), "dans 1h"),
        ]:
            cle = f"{url}|{typ}|{ouv_iso}"
            if cle in state["envois"]:
                continue
            if now >= ouv - delta:
                notifier(f"⏰ Inscriptions **{info['nom']}** ouvrent {libelle} ({ouv:%d/%m %H:%M})\n{url}")
                state["envois"].append(cle)

    save_state(state)

print("TEST", len(__import__("sources").scan_milesrepublic()), len(__import__("sources").scan_finishers()))

if __name__ == "__main__":
    main()
