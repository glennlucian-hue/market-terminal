"""Nasdaq: Analysten-Konsens (Gewinnschätzungen je Aktie, Kursziel) – kostenlos, ohne Schlüssel."""
import requests

from ..cache import DatenFehler, hole

NAME = "Nasdaq (Analystenschätzungen)"
_KOPF = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _zahl(text):
    try:
        return float(str(text).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def analysten(ticker: str) -> dict:
    """Gewinnschätzungen je Aktie (USD) für die nächsten Geschäftsjahre und das 1-Jahres-Kursziel."""
    def laden():
        r = requests.get(f"https://api.nasdaq.com/api/analyst/{ticker}/earnings-forecast", headers=_KOPF, timeout=30)
        r.raise_for_status()
        jahre = ((r.json().get("data") or {}).get("yearlyForecast") or {}).get("rows") or []
        s = requests.get(f"https://api.nasdaq.com/api/quote/{ticker}/summary", params={"assetclass": "stocks"},
                         headers=_KOPF, timeout=30)
        s.raise_for_status()
        zusammen = (s.json().get("data") or {}).get("summaryData") or {}
        if not jahre:
            raise DatenFehler(f"Keine Analystenschätzungen für {ticker}")
        return {
            "jahre": [{"jahr": z.get("fiscalEnd"), "eps": _zahl(z.get("consensusEPSForecast")),
                       "hoch": _zahl(z.get("highEPSForecast")), "tief": _zahl(z.get("lowEPSForecast")),
                       "anzahl": int(_zahl(z.get("noOfEstimates")) or 0)} for z in jahre[:3]],
            "kursziel": _zahl((zusammen.get("OneYrTarget") or {}).get("value")),
            "boersenwert": _zahl((zusammen.get("MarketCap") or {}).get("value")),
            "dividendenrendite": _zahl(((zusammen.get("Yield") or {}).get("value") or "").replace("%", "")),
            "sektor": (zusammen.get("Sector") or {}).get("value"),
        }

    return hole(f"nasdaq_analysten_{ticker}", NAME, 24, laden)[0]
