"""IPO-Kalender der Nasdaq: kommende, kürzlich bewertete und neu angemeldete Börsengänge (USA)."""
from datetime import date

import requests

from ..cache import hole

NAME = "Nasdaq IPO-Kalender"


def _monat(jahr: int, monat: int) -> dict:
    def laden():
        r = requests.get("https://api.nasdaq.com/api/ipo/calendar", params={"date": f"{jahr}-{monat:02d}"},
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=30)
        r.raise_for_status()
        d = r.json().get("data") or {}
        def zeilen(teil):
            blk = d.get(teil) or {}
            return blk.get("rows") or (blk.get("upcomingTable") or {}).get("rows") or []
        return {"kommend": zeilen("upcoming"), "bewertet": zeilen("priced"), "angemeldet": zeilen("filed")}

    return hole(f"ipo_{jahr}-{monat:02d}", NAME, 6, laden)[0]


def _zahl(text) -> float | None:
    try:
        return float(str(text).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def kalender() -> dict:
    """Dieser und nächster Monat zusammengefasst."""
    heute = date.today()
    naechster = (heute.year + heute.month // 12, heute.month % 12 + 1)
    roh = [_monat(heute.year, heute.month), _monat(*naechster)]
    erg = {"kommend": [], "bewertet": [], "angemeldet": []}
    for teil in roh:
        for art in erg:
            for z in teil[art]:
                erg[art].append({
                    "firma": z.get("companyName"), "ticker": z.get("proposedTickerSymbol") or "–",
                    "boerse": z.get("proposedExchange") or "", "preis": z.get("proposedSharePrice") or "",
                    "aktien": _zahl(z.get("sharesOffered")), "volumen": _zahl(z.get("dollarValueOfSharesOffered")),
                    "datum": z.get("expectedPriceDate") or z.get("pricedDate") or z.get("filedDate") or "",
                })
    for art in erg:  # Duplikate entfernen, nach Volumen sortieren
        eindeutig = {(x["firma"], x["datum"]): x for x in erg[art]}
        erg[art] = sorted(eindeutig.values(), key=lambda x: -(x["volumen"] or 0))
    return erg
