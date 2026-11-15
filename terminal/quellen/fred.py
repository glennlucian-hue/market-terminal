"""FRED (Federal Reserve Bank of St. Louis): Zinsen, Inflation, Liquidität, Arbeitsmarkt.

Mit FRED_API_KEY in .env wird die offizielle API verwendet.
Ohne Schlüssel weicht das Programm auf den öffentlichen CSV-Download von FRED aus.
"""
import io
import os

import pandas as pd
import requests

from ..cache import DatenFehler, hole

NAME = "FRED (St. Louis Fed)"


def _per_api(serie: str, schluessel: str) -> pd.Series:
    r = requests.get("https://api.stlouisfed.org/fred/series/observations", timeout=30, params={
        "series_id": serie, "api_key": schluessel, "file_type": "json", "observation_start": "2015-01-01"})
    if r.status_code == 400:
        raise DatenFehler(f"FRED lehnt die Anfrage ab (Serie '{serie}' unbekannt oder API-Key ungültig)")
    r.raise_for_status()
    beob = r.json()["observations"]
    return pd.Series({pd.Timestamp(o["date"]): o["value"] for o in beob})


def _per_csv(serie: str) -> pd.Series:
    for versuch in range(3):  # FRED antwortet gelegentlich langsam -> bis zu 3 Versuche
        try:
            r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                             params={"id": serie, "cosd": "2015-01-01"}, timeout=30)
            r.raise_for_status()
            break
        except requests.RequestException:
            if versuch == 2:
                raise
    df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
    if df.empty:
        raise DatenFehler(f"FRED-Serie '{serie}' ist leer oder unbekannt")
    return df.iloc[:, 0]


def serie(serie_id: str, cache_stunden: float = 12) -> tuple[pd.Series, dict]:
    def laden():
        schluessel = os.getenv("FRED_API_KEY", "").strip()
        s = _per_api(serie_id, schluessel) if schluessel else _per_csv(serie_id)
        s = pd.to_numeric(s, errors="coerce").dropna().rename(serie_id)
        s.index = pd.DatetimeIndex(s.index)
        if s.empty:
            raise DatenFehler(f"FRED-Serie '{serie_id}' enthält keine Werte")
        return s

    return hole(f"fred_{serie_id}", NAME, cache_stunden, laden, {"waehrung": ""})
