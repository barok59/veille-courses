import re
import requests
from bs4 import BeautifulSoup

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


def scan_ffa():
    """Mis de côté pour l'instant."""
    return []


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


def scan_klikego():
    """Cartes de courses de la recherche Klikego (HTML)."""
    try:
        r = requests.get(KLIKEGO_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        courses = []
        for card in soup.find_all("div", class_=lambda c: c and "md:max-w-64" in c.split()):
            link = card.find("a", href=True)
            titre = card.select_one("div.text-text-base-bolder")
            lieu = card.select_one("div.text-text-base-medium")
            date = card.select_one("span.flex-1")
            if not (link and titre):
                continue
            distances = []
            for badge in card.select("span.badge"):
                m = re.search(r"([\d,]+)\s*km", badge.get_text())
                if m:
                    distances.append(float(m.group(1).replace(",", ".")))
            courses.append({
                "url": link["href"],
                "nom": titre.get_text(strip=True),
                "date": date_klikego(date.get_text()) if date else None,
                "ouverture": None,  # absente de la liste, à récupérer sur la fiche
                "lieu": nettoyer_lieu(lieu.get_text()) if lieu else "",
                "distances": distances,
            })
        return courses
    except Exception as e:
        print(f"Erreur scan Klikego : {e}")
        return []


SOURCES = [scan_1000pattes, scan_klikego]
