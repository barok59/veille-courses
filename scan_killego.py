import re
from bs4 import BeautifulSoup

KLIKEGO_URL = "https://www.klikego.com/v8/evenements/search.jsp?sport=running&geo=02%3B59%3B62%3B60%3B80%3B&date="
MOIS = {"janv": 1, "févr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
        "juil": 7, "août": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12}

def date_klikego(texte):
    """'29 nov. 2026' ou '1 sept. 2026 – 31 août 2027' -> '2026-11-29' (première date)."""
    m = re.match(r"(\d{1,2})\s+([^\s.]+)\.?\s+(\d{4})", texte.strip())
    if not m or m.group(2) not in MOIS:
        return None
    return f"{m.group(3)}-{MOIS[m.group(2)]:02d}-{int(m.group(1)):02d}"

def scan_klikego():
    """Cartes de courses renvoyées par search.jsp (HTML, pas JSON)."""
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
                "lieu": lieu.get_text(strip=True) if lieu else "",
                "distances": distances,
            })
        return courses
    except Exception as e:
        print(f"Erreur scan Klikego : {e}")
        return []
