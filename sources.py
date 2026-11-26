import re
import requests
import math
import datetime as dt

from bs4 import BeautifulSoup

MILES_URL = "https://fr.milesrepublic.com/_search/multi-search"
MILES_TOKEN_URL = "https://fr.milesrepublic.com/search-token"
MILES_SEARCH_URL = "https://fr.milesrepublic.com/_search/multi-search"

FINISHERS_URL = "https://vn2qtcjsbg0ea481p.a1.typesense.net/multi_search?x-typesense-api-key=G1BPjGr3KDU7n6yylcfOREpRVGUBpKYW"
RAYON_RECHERCHE = 30  # km, marge large autour de Gondecourt, le filtre fin est dans veille.py


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

KLIKEGO_URL = "https://www.klikego.com/v8/evenements/search.jsp?sport=running&geo=02%3B59%3B62%3B60%3B80%3B&date="
MOIS = {"janv": 1, "févr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
        "juil": 7, "août": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12}


def nettoyer_lieu(texte):
    """'Soissons, Aisne (02)' -> 'Soissons, Aisne' (plus facile à géocoder)."""
    return re.sub(r"\s*\(\d+\)\s*$", "", " ".join(texte.split()))


def date_klikego(texte):
    """'29 nov. 2026' ou '1 sept. 2026 – 31 août 2027' -> '2026-11-29'."""
    m = re.match(r"(\d{1,2})\s+([^\s.]+)\.?\s+(\d{4})", texte.strip())
    if not m or m.group(2) not in MOIS:
        return None
    return f"{m.group(3)}-{MOIS[m.group(2)]:02d}-{int(m.group(1)):02d}"


def scan_1000pattes():
    """Guide 1000 Pattes, Nord / Pas-de-Calais."""
    url = "https://nord-pas-de-calais.1000pattes.guide/events/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        courses = []
        for event in soup.find_all("article", class_=["tribe-events-calendar-list__event", "type-tribe_events"]):
            link = event.find(class_="tribe-events-calendar-list__event-title-link") or event.find("a")
            if not link or not link.get("href"):
                continue
            date_tag = event.find(class_="tribe-events-calendar-list__event-date-tag-datetime")
            venue = event.find(class_="tribe-events-calendar-list__event-venue")
            courses.append({
                "url": link["href"],
                "nom": link.get_text(strip=True),
                "date": date_tag["datetime"] if date_tag and date_tag.get("datetime") else None,
                "ouverture": None,
                "lieu": nettoyer_lieu(venue.get_text(" ", strip=True)) if venue else "",
                "distances": [],  # inconnues sur cette page
            })
        return courses
    except Exception as e:
        print(f"Erreur scan 1000 Pattes : {e}")
        return []

def _distance_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def scan_milesrepublic():
    """Miles Republic : token de session, puis recherche géographique (comme le site)."""
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.headers.update({
            "Origin": "https://fr.milesrepublic.com",
            "Referer": "https://fr.milesrepublic.com/search?geoSearch=51.0894%2C4.2301%2C49.9707%2C2.0677&geoLocation=Nord",
        })

        tok = s.post(MILES_TOKEN_URL, timeout=15)
        tok.raise_for_status()
        token = tok.json()["token"]

        body = {"queries": [{
            "indexUid": "fra_events",
            "q": "",
            "hitsPerPage": 500,
            "filter": [
                "_geoBoundingBox([51.0894, 4.2301], [49.9707, 2.0677])",
                f"editionLiveEndDateTimestamp > {int(dt.datetime.now().timestamp())} AND eventStatus = \"LIVE\"",
            ],
            "attributesToRetrieve": ["objectID", "eventName", "eventSlug", "eventCity",
                                     "eventCountrySubdivisionNameLevel2", "editionLiveStartDateTimestamp",
                                     "distances", "_geo"],
        }]}
        r = s.post(MILES_SEARCH_URL, json=body,
                   headers={"X-TYPESENSE-API-KEY": token, "Authorization": f"Bearer {token}"},
                   timeout=20)
        r.raise_for_status()
        hits = r.json()["results"][0]["hits"]

        courses = []
        for h in hits:
            geo = h.get("_geo") or {}
            if not geo.get("lat"):
                continue
            ts = h.get("editionLiveStartDateTimestamp")
            courses.append({
                "url": f"https://fr.milesrepublic.com/event/{h['eventSlug']}",
                "nom": h["eventName"],
                "date": dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M") if ts else None,
                "ouverture": None,
                "lieu": f"{h['eventCity']}, {h.get('eventCountrySubdivisionNameLevel2', '')}",
                "distances": h.get("distances") or [],
                "coords": (geo["lat"], geo["lng"]),
            })
        return courses
    except Exception as e:
        print(f"Erreur scan Miles Republic : {e}")
        return []


def scan_finishers():
    """Finishers (Typesense), courses du Nord."""
    body = {"searches": [{
        "collection": "races_2026-11-26_03-12-08",  # nom de collection vu dans la réponse
        "q": "*",
        "per_page": 100,
        "group_by": "eventId",
        "group_limit": 1,
        "filter_by": "level2Id:=7199541a-1480-41c7-850c-7962113897ff",
    }]}
    try:
        r = requests.post(FINISHERS_URL, json=body, headers=HEADERS, timeout=20)
        r.raise_for_status()
        courses = []
        for group in r.json()["results"][0]["grouped_hits"]:
            d = group["hits"][0]["document"]
            geo = d.get("_geoloc") or {}
            if not geo.get("lat"):
                continue
            courses.append({
                "url": d.get("eventRegistrationUrl") or f"https://www.finishers.com/{d.get('eventSlug', '')}",
                "nom": d["eventName"],
                "date": dt.datetime.fromtimestamp(d["raceDate"]).strftime("%Y-%m-%dT%H:%M"),
                "ouverture": None,
                "lieu": f"{d['city']}, Nord",
                "distances": [x / 1000 for x in d.get("raceDistanceVariants", [])
                              if d.get("raceDistanceUnit") == "meters"],
                "coords": (geo["lat"], geo["lng"]),
            })
        return courses
    except Exception as e:
        print(f"Erreur scan Finishers : {e}")
        return []


SOURCES = [scan_1000pattes, scan_finishers]  # scan_milesrepublic désactivé (429)
