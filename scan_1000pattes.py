import re

def scan_1000pattes():
    """Guide 1000 pattes : retourne les courses au format attendu par veille.py."""
    url = "https://nord-pas-de-calais.1000pattes.guide/events/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        courses = []

        for event in soup.find_all("article", class_=["tribe-events-calendar-list__event", "type-tribe_events"]):
            link_tag = event.find(class_="tribe-events-calendar-list__event-title-link") or event.find("a")
            if not link_tag or not link_tag.get("href"):
                continue

            date_tag = event.find(class_="tribe-events-calendar-list__event-date-tag-datetime")
            date_iso = date_tag["datetime"] if date_tag and date_tag.get("datetime") else None

            venue = event.find(class_="tribe-events-calendar-list__event-venue")
            lieu = " ".join(venue.get_text(" ", strip=True).split()) if venue else ""

            courses.append({
                "url": link_tag["href"],
                "nom": link_tag.get_text(strip=True),
                "date": date_iso,
                "ouverture": None,   # non disponible sur cette page
                "lieu": lieu,
                "distances": [],     # à compléter depuis la fiche de l'événement
            })
        return courses
    except Exception as e:
        print(f"Erreur scan 1000 Pattes : {e}")
        return []
