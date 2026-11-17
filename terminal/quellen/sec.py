"""SEC EDGAR (US-Börsenaufsicht): offizielle Unterlagen und Finanzzahlen börsenkotierter Firmen.

Die SEC verlangt, dass automatische Abfragen eine Kontaktangabe enthalten.
Trage dafür in .env (bzw. als GitHub-Secret) SEC_KONTAKT=deine@email.ch ein.
Ohne Kontaktangabe kann die SEC Anfragen ablehnen – das Terminal zeigt dann die
Prospektdaten aus anthropic.yaml und markiert fehlende Vergleichsdaten.
"""
import os
from datetime import date, timedelta

import requests

from ..cache import DatenFehler, hole

NAME = "SEC EDGAR"


def _kopf() -> dict:
    kontakt = os.getenv("SEC_KONTAKT", "").strip()
    return {"User-Agent": f"MarketTerminal/1.0 (private research{', ' + kontakt if kontakt else ''})"}


def _hole_json(url: str) -> dict:
    r = requests.get(url, headers=_kopf(), timeout=60)
    if r.status_code == 403:
        raise DatenFehler("SEC lehnt die Anfrage ab – bitte SEC_KONTAKT (E-Mail) in .env bzw. GitHub-Secrets eintragen")
    r.raise_for_status()
    return r.json()


def einreichungen(cik: str, anzahl: int = 12) -> list[dict]:
    """Neueste Unterlagen einer Firma (Prospekte, Nachträge, Mitteilungen) mit Link."""
    def laden():
        d = _hole_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")["filings"]["recent"]
        liste = []
        for i in range(min(anzahl, len(d["form"]))):
            nr = d["accessionNumber"][i].replace("-", "")
            liste.append({"datum": d["filingDate"][i], "formular": d["form"][i],
                          "link": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nr}/{d['primaryDocument'][i]}"})
        return liste

    return hole(f"sec_einreichungen_{cik}", NAME, 6, laden)[0]


def _cik_tabelle() -> dict:
    return hole("sec_tickers", NAME, 24 * 7, lambda: {
        v["ticker"]: v["cik_str"] for v in _hole_json("https://www.sec.gov/files/company_tickers.json").values()})[0]


def umsatz_und_aktien(ticker: str, cik: int | None = None) -> dict:
    """Umsatz der letzten 12 Monate (Summe der 4 letzten Quartale), Wachstum zum Vorjahr
    und verwässerte Aktienanzahl – aus den XBRL-Finanzdaten der Quartals- und Jahresberichte."""
    def laden():
        nummer = cik or _cik_tabelle().get(ticker)
        if not nummer:
            raise DatenFehler(f"{ticker} nicht im SEC-Verzeichnis")
        roh = _hole_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(nummer):010d}.json")
        fakten = roh["facts"]["us-gaap"]
        quartale = {}
        for feld in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"):
            for x in fakten.get(feld, {}).get("units", {}).get("USD", []):
                if not x.get("start"):
                    continue
                tage = (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days
                if 80 <= tage <= 100:  # nur echte 3-Monats-Werte
                    quartale[x["end"]] = max(quartale.get(x["end"], 0), x["val"])
        enden = sorted(quartale)
        if len(enden) < 8:
            raise DatenFehler(f"Zu wenige Quartalsumsätze für {ticker}")
        ttm = sum(quartale[e] for e in enden[-4:])
        vorjahr = sum(quartale[e] for e in enden[-8:-4])
        aktien = [x for x in fakten.get("WeightedAverageNumberOfDilutedSharesOutstanding", {}).get("units", {}).get("shares", [])
                  if x.get("start") and 80 <= (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days <= 100]
        aktien.sort(key=lambda x: (x["end"], x.get("filed", "")))
        if not aktien:
            raise DatenFehler(f"Keine Aktienanzahl für {ticker}")
        return {"firma": roh.get("entityName"), "umsatz_ttm": ttm, "wachstum": (ttm / vorjahr - 1) * 100 if vorjahr else None,
                "aktien": aktien[-1]["val"], "stand": enden[-1]}

    return hole(f"sec_fakten_{ticker}", NAME, 24, laden)[0]
