"""Nachrichten: Google News (Suchanfragen je Thema) und offizielle Feeds der US-Notenbank.

Es werden nur Schlagzeile, Quelle, Zeit und Link übernommen – die Artikel selbst
liest du beim Anbieter (manche, z. B. FT oder Bloomberg, sind kostenpflichtig).
"""
import html
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

from ..cache import DatenFehler, hole

_KOPF = {"User-Agent": "Mozilla/5.0"}


def _rss(url: str) -> list[dict]:
    r = requests.get(url, headers=_KOPF, timeout=30)
    r.raise_for_status()
    wurzel = ET.fromstring(r.content)
    artikel = []
    for item in wurzel.iter("item"):
        titel = html.unescape((item.findtext("title") or "").strip())
        quelle = (item.findtext("source") or "").strip()
        quelle = quelle.removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
        if " - " in titel:
            titel = titel.rsplit(" - ", 1)[0]  # Google hängt " - Quelle" an den Titel
        titel = titel.strip().rstrip("-–| ").strip()
        try:
            zeit = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:
            zeit = None
        artikel.append({"titel": titel, "quelle": quelle, "link": (item.findtext("link") or "").strip(), "zeit": zeit})
    return artikel


def google_news(suchbegriff: str, tage: int = 7) -> list[dict]:
    url = (f"https://news.google.com/rss/search?q={quote_plus(suchbegriff + f' when:{tage}d')}"
           "&hl=en-US&gl=US&ceid=US:en")

    def laden():
        return _rss(url)  # keine Treffer = leere Liste, kein Fehler

    return hole(f"news_{suchbegriff[:60]}", "Google News", 1, laden)[0]


def fed_reden() -> list[dict]:
    def laden():
        a = _rss("https://www.federalreserve.gov/feeds/speeches.xml")
        for x in a:
            x["quelle"] = "Federal Reserve"
        return a

    return hole("news_fed_reden", "Federal Reserve (Reden)", 6, laden)[0]


def fed_kalender() -> list[dict]:
    """Kommende Termine der Fed (Reden, FOMC-Sitzungen, Anhörungen)."""
    def laden():
        r = requests.get("https://www.federalreserve.gov/json/calendar.json", headers=_KOPF, timeout=30)
        r.raise_for_status()
        roh = json.loads(r.content.decode("utf-8-sig"))
        termine = []
        for e in roh.get("events", []):
            try:
                tag = int(str(e.get("days", "")).split(",")[0].split("-")[0].strip())
                datum = datetime.strptime(f"{e['month']}-{tag:02d}", "%Y-%m-%d").date().isoformat()
            except Exception:
                continue
            termine.append({
                "datum": datum, "zeit_et": e.get("time", ""), "art": e.get("type", ""),
                "titel": html.unescape(e.get("title", "")), "thema": html.unescape(e.get("description", "")),
                "ort": html.unescape(e.get("location", "")),
            })
        if not termine:
            raise DatenFehler("Fed-Kalender ist leer")
        return sorted(termine, key=lambda t: t["datum"])

    return hole("fed_kalender", "Federal Reserve (Kalender)", 12, laden)[0]
