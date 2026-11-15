"""Yahoo Finance (über das Paket yfinance): Kurse, Bewertungen, Termine von Quartalszahlen."""
import logging
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
