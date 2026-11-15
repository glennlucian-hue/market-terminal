"""Veränderungen einer Kursreihe über verschiedene Zeiträume."""
from datetime import timedelta

import pandas as pd


def kurs_am_oder_vor(s: pd.Series, datum) -> float | None:
    vorher = s[s.index <= datum]
    return float(vorher.iloc[-1]) if not vorher.empty else None


def veraenderung(jetzt: float, vorher: float | None, art: str = "preis") -> float | None:
    if vorher is None or vorher == 0:
        return None
    if art == "rendite":
        return (jetzt - vorher) * 100      # Prozentpunkte -> Basispunkte
    return (jetzt / vorher - 1) * 100      # Prozent


def berechne(s: pd.Series, art: str = "preis") -> dict:
    """
    tag   = gegenüber dem vorherigen Handelstag
    woche = gegenüber dem letzten Kurs vor 7 Kalendertagen
    monat = vor 30 Tagen,  jahr = vor 365 Tagen
    ytd   = gegenüber dem letzten Kurs des Vorjahres
    """
    d = s.index[-1]
    jetzt = float(s.iloc[-1])
    vergleich = {
        "tag": float(s.iloc[-2]) if len(s) > 1 else None,
        "woche": kurs_am_oder_vor(s, d - timedelta(days=7)),
        "monat": kurs_am_oder_vor(s, d - timedelta(days=30)),
        "jahr": kurs_am_oder_vor(s, d - timedelta(days=365)),
        "ytd": kurs_am_oder_vor(s, pd.Timestamp(year=d.year, month=1, day=1) - timedelta(days=1)),
    }
    ergebnis = {k: veraenderung(jetzt, v, art) for k, v in vergleich.items()}
    return {"kurs": jetzt, "stand": d, "einheit": "bp" if art == "rendite" else "%", **ergebnis}
