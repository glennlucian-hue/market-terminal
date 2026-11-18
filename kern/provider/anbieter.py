"""Die einzelnen Datenquellen. Jede liefert normalisierte Daten mit Quelle, Stand und Art.

Limits (Gratis-Stufen, vorsichtig angesetzt):
  Finnhub        60 / Minute
  FMP            250 / Tag
  Alpha Vantage  25 / Tag, 5 / Minute
  CoinGecko      ~30 / Minute (ohne Schlüssel)
  FRED           120 / Minute
  SEC EDGAR      10 / Sekunde (wir bleiben weit darunter)
"""
import os
from datetime import date, timedelta

from ..datenpunkt import Ergebnis, als_utc
from .basis import Provider


def _zahl(x):
    try:
        return None if x in (None, "", "None", "-") else float(str(x).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
class Finnhub(Provider):
    name, anzeige = "finnhub", "Finnhub"
    schluessel_env = "FINNHUB_API_KEY"
    pro_minute = 55
    BASIS = "https://finnhub.io/api/v1"

    def _auth(self, headers, params):
        headers["X-Finnhub-Token"] = self.schluessel

    def fehler_in_antwort(self, daten):
        return daten.get("error", "") if isinstance(daten, dict) else ""

    def kurs(self, symbol: str) -> Ergebnis:
        e = self.abfrage(f"{self.BASIS}/quote", {"symbol": symbol}, art="verzoegert")
        if e.ok:
            d = e.daten
            if not d or not d.get("t"):
                return Ergebnis(self.name, False, grund=f"keine Kursdaten für {symbol}")
            e.daten = {"symbol": symbol, "kurs": d.get("c"), "veraenderung_pct": d.get("dp"), "vortag": d.get("pc"),
                       "stand": als_utc(d.get("t")).isoformat(), "waehrung": "USD"}
        return e

    def earnings_kalender(self, tage: int = 21) -> Ergebnis:
        von, bis = date.today(), date.today() + timedelta(days=tage)
        e = self.abfrage(f"{self.BASIS}/calendar/earnings", {"from": von.isoformat(), "to": bis.isoformat()},
                         cache_minuten=180, cache_name=f"earnings_{von}", art="termin")
        if e.ok:
            e.daten = [{"symbol": x.get("symbol"), "datum": x.get("date"),
                        "zeit": {"bmo": "vor Börsenbeginn", "amc": "nach Börsenschluss"}.get(x.get("hour"), ""),
                        "eps_schaetzung": x.get("epsEstimate"), "eps_ist": x.get("epsActual"),
                        "umsatz_schaetzung": x.get("revenueEstimate"), "umsatz_ist": x.get("revenueActual")}
                       for x in (e.daten or {}).get("earningsCalendar", [])]
        return e

    def empfehlungen(self, symbol: str) -> Ergebnis:
        e = self.abfrage(f"{self.BASIS}/stock/recommendation", {"symbol": symbol},
                         cache_minuten=24 * 60, cache_name=f"empf_{symbol}", art="schaetzung")
        if e.ok:
            e.daten = [{"periode": x.get("period"), "stark_kaufen": x.get("strongBuy"), "kaufen": x.get("buy"),
                        "halten": x.get("hold"), "verkaufen": x.get("sell"), "stark_verkaufen": x.get("strongSell")}
                       for x in (e.daten or [])]
        return e

    def insider(self, symbol: str) -> Ergebnis:
        von = (date.today() - timedelta(days=180)).isoformat()
        e = self.abfrage(f"{self.BASIS}/stock/insider-transactions", {"symbol": symbol, "from": von},
                         cache_minuten=24 * 60, cache_name=f"insider_{symbol}", art="offiziell")
        if e.ok:
            e.daten = [{"name": x.get("name"), "datum": x.get("transactionDate"), "meldung": x.get("filingDate"),
                        "art": x.get("transactionCode"), "anzahl": x.get("change"), "preis": x.get("transactionPrice")}
                       for x in (e.daten or {}).get("data", [])]
        return e

    def pruefen(self) -> Ergebnis:
        return self.kurs("AAPL")


# ---------------------------------------------------------------------------
class FMP(Provider):
    name, anzeige = "fmp", "Financial Modeling Prep"
    schluessel_env = "FMP_API_KEY"
    pro_tag = 240
    BASIS = "https://financialmodelingprep.com/stable"

    def _auth(self, headers, params):
        params["apikey"] = self.schluessel

    def fehler_in_antwort(self, daten):
        if isinstance(daten, dict) and daten.get("Error Message"):
            return daten["Error Message"][:160]
        return ""

    def kurs(self, symbol: str) -> Ergebnis:
        e = self.abfrage(f"{self.BASIS}/quote", {"symbol": symbol}, art="verzoegert")
        if e.ok:
            d = (e.daten or [None])[0]
            if not d:
                return Ergebnis(self.name, False, grund=f"keine Kursdaten für {symbol}")
            e.daten = {"symbol": symbol, "kurs": d.get("price"), "veraenderung_pct": d.get("changePercentage"),
                       "vortag": d.get("previousClose"), "stand": als_utc(d.get("timestamp")).isoformat()
                       if d.get("timestamp") else None, "waehrung": None}
        return e

    def kennzahlen(self, symbol: str) -> Ergebnis:
        """Bewertung und Profitabilität der letzten 12 Monate (2 Abfragen, 24 h im Cache)."""
        r = self.abfrage(f"{self.BASIS}/ratios-ttm", {"symbol": symbol}, cache_minuten=24 * 60,
                         cache_name=f"ratios_{symbol}", art="offiziell")
        if not r.ok:
            return r
        k = self.abfrage(f"{self.BASIS}/key-metrics-ttm", {"symbol": symbol}, cache_minuten=24 * 60,
                         cache_name=f"metrics_{symbol}", art="offiziell")
        roh = {**((r.daten or [{}])[0] or {}), **(((k.daten or [{}])[0] or {}) if k.ok else {})}
        if not roh:
            return Ergebnis(self.name, False, grund=f"keine Kennzahlen für {symbol}")

        def erstes(*namen):
            for n in namen:
                if roh.get(n) is not None:
                    return roh[n]
            return None
        r.daten = {"symbol": symbol,
                   "kgv": erstes("priceToEarningsRatioTTM", "peRatioTTM"),
                   "kurs_umsatz": erstes("priceToSalesRatioTTM"),
                   "nettomarge": erstes("netProfitMarginTTM"),
                   "operative_marge": erstes("operatingProfitMarginTTM"),
                   "eigenkapitalrendite": erstes("returnOnEquityTTM"),
                   "dividendenrendite": erstes("dividendYieldTTM"),
                   "verschuldung": erstes("debtToEquityRatioTTM", "debtEquityRatioTTM")}
        return r

    def kursziel(self, symbol: str) -> Ergebnis:
        """Konsens-Kursziel der Analysten (tief, Median, Konsens, hoch). Gratis nur für US-Aktien."""
        e = self.abfrage(f"{self.BASIS}/price-target-consensus", {"symbol": symbol}, cache_minuten=24 * 60,
                         cache_name=f"ziel_{symbol}", art="schaetzung")
        if e.ok:
            d = (e.daten or [None])[0]
            if not d:
                return Ergebnis(self.name, False, grund=f"kein Kursziel für {symbol}")
            e.daten = {"mittel": d.get("targetConsensus"), "median": d.get("targetMedian"),
                       "hoch": d.get("targetHigh"), "tief": d.get("targetLow")}
        return e

    def einstufungen(self, symbol: str, anzahl: int = 12) -> Ergebnis:
        """Letzte Einstufungen einzelner Analysehäuser (wer, wann, von -> zu)."""
        e = self.abfrage(f"{self.BASIS}/grades", {"symbol": symbol}, cache_minuten=24 * 60,
                         cache_name=f"grades_{symbol}", art="schaetzung")
        if e.ok:
            e.daten = [{"datum": x.get("date"), "firma": x.get("gradingCompany"), "von": x.get("previousGrade"),
                        "zu": x.get("newGrade"), "aktion": x.get("action")} for x in (e.daten or [])[:anzahl]]
        return e

    def schaetzungen(self, symbol: str) -> Ergebnis:
        """Analystenschätzungen je Geschäftsjahr (Umsatz, Gewinn je Aktie)."""
        e = self.abfrage(f"{self.BASIS}/analyst-estimates", {"symbol": symbol, "period": "annual"},
                         cache_minuten=24 * 60, cache_name=f"est_{symbol}", art="schaetzung")
        if e.ok:
            heute = date.today().isoformat()
            zeilen = sorted((x for x in (e.daten or []) if (x.get("date") or "") >= heute[:4]), key=lambda x: x.get("date", ""))
            e.daten = [{"jahr": (x.get("date") or "")[:4], "eps": x.get("epsAvg"), "umsatz": x.get("revenueAvg"),
                        "analysten": x.get("numAnalystsEps")} for x in zeilen[:3]]
        return e

    def pruefen(self) -> Ergebnis:
        return self.kurs("AAPL")


# ---------------------------------------------------------------------------
class AlphaVantage(Provider):
    name, anzeige = "alphavantage", "Alpha Vantage"
    schluessel_env = "ALPHAVANTAGE_API_KEY"
    pro_tag, pro_minute = 24, 5
    BASIS = "https://www.alphavantage.co/query"

    def _auth(self, headers, params):
        params["apikey"] = self.schluessel

    def fehler_in_antwort(self, daten):
        if isinstance(daten, dict):
            for feld in ("Error Message", "Note", "Information"):
                if daten.get(feld):
                    return f"Alpha Vantage: {daten[feld][:160]}"
        return ""

    def top_bewegungen(self) -> Ergebnis:
        """Grösste Gewinner, Verlierer und meistgehandelte US-Aktien (1 Abfrage, 6 h im Cache)."""
        e = self.abfrage(self.BASIS, {"function": "TOP_GAINERS_LOSERS"}, cache_minuten=6 * 60,
                         cache_name="top", art="verzoegert")
        if e.ok:
            def liste(teil):
                return [{"symbol": x.get("ticker"), "kurs": _zahl(x.get("price")),
                         "veraenderung_pct": _zahl(x.get("change_percentage")), "volumen": _zahl(x.get("volume"))}
                        for x in e.daten.get(teil, [])[:10]]
            e.daten = {"stand": e.daten.get("last_updated"), "gewinner": liste("top_gainers"),
                       "verlierer": liste("top_losers"), "meistgehandelt": liste("most_actively_traded")}
        return e

    def pruefen(self) -> Ergebnis:
        return self.top_bewegungen()


# ---------------------------------------------------------------------------
class CoinGecko(Provider):
    name, anzeige = "coingecko", "CoinGecko"
    pro_minute = 20
    BASIS = "https://api.coingecko.com/api/v3"

    def markt(self) -> Ergebnis:
        e = self.abfrage(f"{self.BASIS}/global", cache_minuten=10, cache_name="global", art="verzoegert")
        if e.ok:
            d = e.daten.get("data", {})
            e.daten = {"marktwert_usd": d.get("total_market_cap", {}).get("usd"),
                       "volumen_usd": d.get("total_volume", {}).get("usd"),
                       "veraenderung_24h_pct": d.get("market_cap_change_percentage_24h_usd"),
                       "dominanz_pct": {k: round(v, 2) for k, v in sorted(d.get("market_cap_percentage", {}).items(),
                                                                          key=lambda x: -x[1])[:5]},
                       "stand": als_utc(d.get("updated_at")).isoformat() if d.get("updated_at") else None}
        return e

    def top_coins(self, anzahl: int = 15) -> Ergebnis:
        e = self.abfrage(f"{self.BASIS}/coins/markets", {"vs_currency": "usd", "per_page": anzahl, "page": 1,
                         "price_change_percentage": "24h,7d"}, cache_minuten=10, cache_name=f"top{anzahl}",
                         art="verzoegert")
        if e.ok:
            e.daten = [{"symbol": (x.get("symbol") or "").upper(), "name": x.get("name"), "kurs": x.get("current_price"),
                        "veraenderung_24h_pct": x.get("price_change_percentage_24h_in_currency"),
                        "veraenderung_7d_pct": x.get("price_change_percentage_7d_in_currency"),
                        "marktwert": x.get("market_cap"), "rang": x.get("market_cap_rank"),
                        "stand": x.get("last_updated"), "waehrung": "USD"} for x in e.daten]
        return e

    def pruefen(self) -> Ergebnis:
        return self.markt()


# ---------------------------------------------------------------------------
class FredKalender(Provider):
    name, anzeige = "fred", "FRED (St. Louis Fed)"
    schluessel_env = "FRED_API_KEY"
    pro_minute = 100
    BASIS = "https://api.stlouisfed.org/fred"
    # Wichtige US-Veröffentlichungen (Name bei FRED -> deutsche Bezeichnung)
    WICHTIG = {
        "Consumer Price Index": "Konsumentenpreise (CPI)",
        "Employment Situation": "Arbeitsmarktbericht (NFP)",
        "Personal Income and Outlays": "Einkommen & Konsum (PCE-Inflation)",
        "Gross Domestic Product": "Bruttoinlandprodukt (BIP)",
        "Producer Price Index": "Produzentenpreise (PPI)",
        "Advance Monthly Sales for Retail and Food Services": "Detailhandelsumsätze",
        "Job Openings and Labor Turnover Survey": "Offene Stellen (JOLTS)",
        "Unemployment Insurance Weekly Claims Report": "Erstanträge Arbeitslosenhilfe",
        "Industrial Production and Capacity Utilization": "Industrieproduktion",
        "University of Michigan: Consumer Sentiment": "Konsumstimmung (Michigan)",
        "New Residential Construction": "Baubeginne",
        "Durable Goods": "Auftragseingänge langlebige Güter",
    }

    def _auth(self, headers, params):
        params["api_key"] = self.schluessel
        params["file_type"] = "json"

    def fehler_in_antwort(self, daten):
        return daten.get("error_message", "") if isinstance(daten, dict) else ""

    def wirtschaftstermine(self, tage: int = 21) -> Ergebnis:
        heute = date.today()
        e = self.abfrage(f"{self.BASIS}/releases/dates", {
            "realtime_start": heute.isoformat(), "realtime_end": (heute + timedelta(days=tage)).isoformat(),
            "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 1000},
            cache_minuten=12 * 60, cache_name=f"termine_{heute}", art="termin")
        if e.ok:
            liste = []
            for x in e.daten.get("release_dates", []):
                name = x.get("release_name", "")
                for schluessel, deutsch in self.WICHTIG.items():
                    if name.startswith(schluessel):
                        liste.append({"datum": x.get("date"), "ereignis": deutsch, "original": name,
                                      "release_id": x.get("release_id")})
                        break
            e.daten = liste
        return e

    def pruefen(self) -> Ergebnis:
        return self.wirtschaftstermine(7)


# ---------------------------------------------------------------------------
class SecEdgar(Provider):
    name, anzeige = "sec", "SEC EDGAR"
    pro_minute = 120

    def _auth(self, headers, params):
        kontakt = (os.getenv("SEC_KONTAKT") or "").strip()
        headers["User-Agent"] = f"MarketTerminal/1.0 (private research{', ' + kontakt if kontakt else ''})"

    def pruefen(self) -> Ergebnis:
        e = self.abfrage("https://data.sec.gov/submissions/CIK0002130357.json", art="offiziell")
        if e.ok:
            e.daten = {"firma": e.daten.get("name"), "letzte_einreichung": e.daten["filings"]["recent"]["filingDate"][0]}
        return e


ALLE = [Finnhub, FMP, AlphaVantage, CoinGecko, FredKalender, SecEdgar]
