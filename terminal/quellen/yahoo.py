"""Yahoo Finance (über das Paket yfinance): Kurse, Bewertungen, Termine von Quartalszahlen."""
import logging
import time
from datetime import date, datetime

import pandas as pd
import yfinance as yf

from ..cache import DatenFehler, hole

NAME = "Yahoo Finance"
logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # keine englischen Warnungen in der Konsole


def kurse(ticker: str, cache_stunden: float = 4) -> tuple[pd.Series, dict]:
    """Tägliche Schlusskurse der letzten 5 Jahre. meta enthält u. a. 'waehrung'."""
    zusatz = {}

    def laden():
        t = yf.Ticker(ticker)
        df = t.history(period="5y", interval="1d", auto_adjust=False)
        if df is None or df.empty or "Close" not in df:
            raise DatenFehler(f"Keine Daten für '{ticker}' (Ticker falsch geschrieben?)")
        s = df["Close"].dropna()
        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        s = s[~s.index.duplicated(keep="last")].rename("schluss")
        if s.empty:
            raise DatenFehler(f"Nur leere Kurse für '{ticker}'")
        zusatz["waehrung"] = (t.history_metadata or {}).get("currency") or ""
        return s

    return hole(f"yahoo_{ticker}", NAME, cache_stunden, laden, zusatz)


def firmendaten(ticker: str) -> dict:
    """Bewertung und nächster Termin der Quartalszahlen (24 h im Cache)."""
    def laden():
        t = yf.Ticker(ticker)
        info = t.info or {}
        termin = None
        try:
            kal = t.calendar or {}
            daten = kal.get("Earnings Date") or []
            kuenftig = [d for d in daten if isinstance(d, (date, datetime)) and d >= date.today()]
            termin = min(kuenftig).isoformat() if kuenftig else None
        except Exception:
            pass
        if not info.get("marketCap") and not termin:
            raise DatenFehler(f"Keine Firmendaten für '{ticker}'")
        return {
            "name": info.get("shortName") or ticker,
            "marktwert": info.get("marketCap"),
            "kgv_erwartet": info.get("forwardPE"),
            "kgv": info.get("trailingPE"),
            "kurs_umsatz": info.get("priceToSalesTrailing12Months"),
            "waehrung": info.get("currency"),
            "naechste_zahlen": termin,
        }

    return hole(f"yahoo_info_{ticker}", NAME, 24, laden)[0]


def ohlc(ticker: str, cache_stunden: float = 4) -> pd.DataFrame:
    """Tageskurse mit Eröffnung, Hoch, Tief, Schluss (1 Jahr) – für Pivot-Punkte und Technik."""
    def laden():
        df = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=False)
        if df is None or df.empty:
            raise DatenFehler(f"Keine Tageskurse für '{ticker}'")
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        return df[["Open", "High", "Low", "Close"]].dropna()

    return hole(f"yahoo_ohlc_{ticker}", NAME, cache_stunden, laden)[0]


def fundamentaldaten(ticker: str) -> dict:
    """Kennzahlen aus Yahoo (24 h im Cache). Verhältniszahlen (Margen, Wachstum) sind währungsneutral;
    absolute Beträge können in der Berichtswährung der Firma sein (z. B. KZT bei Kaspi)."""
    def laden():
        i = {}
        for versuch in range(4):  # Yahoo lehnt solche Abfragen zeitweise ab -> mehrere Versuche
            try:
                i = yf.Ticker(ticker).info or {}
            except Exception:
                i = {}
            if len(i) >= 10:
                break
            time.sleep(3 + versuch * 3)
        if len(i) < 10:
            raise DatenFehler(f"Yahoo liefert zurzeit keine Fundamentaldaten für '{ticker}'")
        felder = ["marketCap", "trailingPE", "priceToSalesTrailing12Months", "revenueGrowth", "earningsGrowth",
                  "grossMargins", "operatingMargins", "profitMargins", "returnOnEquity", "debtToEquity",
                  "dividendYield", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currency", "financialCurrency",
                  "longName", "country", "fullTimeEmployees", "forwardPE", "beta", "sector", "industry",
                  "targetMeanPrice", "targetHighPrice", "targetLowPrice", "targetMedianPrice",
                  "numberOfAnalystOpinions", "recommendationKey", "trailingEps", "forwardEps", "pegRatio"]
        return {f: i.get(f) for f in felder}

    return hole(f"yahoo_fund2_{ticker}", NAME, 24, laden)[0]   # "2": erweiterte Felder (Kursziele)
