import requests
from bs4 import BeautifulSoup
# pip install beautifulsoup4 requests

HEADERS = {"User-Agent": "veille-courses-perso/1.0"}


def scan_ffa():
    """Calendrier athle.fr, filtré sur la région Hauts-de-France et le département 59 (Nord)."""
    # TODO : ouvrir la page dans le navigateur, onglet Réseau (F12),
    # repérer si les données arrivent en JSON (plus simple à interroger).
    return []


def scan_1000pattes():
    """Guide 1000 pattes : calendrier des courses, filtrer par région."""
    # TODO : identifier la page calendrier et le format des fiches.
    return []


def scan_klikego():
    """Exemple pour une plateforme d'inscription, à adapter aux pages réelles."""
    return []


SOURCES = [scan_ffa, scan_1000pattes, scan_klikego]
