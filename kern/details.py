"""Detail-Daten je Aktie für die Detailansicht der Terminal-App.

Je Block wird die Quelle mitgeliefert. Reihenfolge der Quellen:
  Fundamentaldaten   FMP (nur US) -> Yahoo
  Kursziel           FMP (nur US) -> Nasdaq (nur US) -> Yahoo
  Empfehlungen       Nasdaq (Kaufen/Halten/Verkaufen, abdeckende Banken) -> Yahoo (Anzahl, Tendenz)
  Einstufungen       FMP "grades" (wer, wann, von -> zu; nur US)
  Schätzungen        FMP (nur US)
  Technik            eigene Berechnung aus Yahoo-Tageskursen
Fehlt etwas, steht im Block ein Grund statt erfundener Werte.
"""
import requests

from .datenpunkt import jetzt_utc
from .provider import FMP


def _ist_us(ticker: str) -> bool:
    return not any(z in ticker for z in ".=^-")


def _nasdaq(ticker: str) -> dict | None:
    """Konsens und abdeckende Banken von der Nasdaq (12 h im Cache des Terminal-Caches)."""
    from terminal.cache import hole

    def laden():
        kopf = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        z = requests.get(f"https://api.nasdaq.com/api/analyst/{ticker}/targetprice", headers=kopf, timeout=30).json()
        r = requests.get(f"https://api.nasdaq.com/api/analyst/{ticker}/ratings", headers=kopf, timeout=30).json()
        k = ((z.get("data") or {}).get("consensusOverview") or {})
        rd = r.get("data") or {}
        return {"mittel": k.get("priceTarget"), "hoch": k.get("highPriceTarget"), "tief": k.get("lowPriceTarget"),
                "kaufen": k.get("buy"), "halten": k.get("hold"), "verkaufen": k.get("sell"),
                "tendenz": rd.get("meanRatingType"), "banken": rd.get("brokerNames") or [],
                "aenderungen": [{"datum": x.get("date"), "firma": x.get("brokerName") or x.get("firm"),
                                 "aktion": x.get("action"), "zu": x.get("rating"), "von": None}
                                for x in (rd.get("upgradesDowngrades") or [])[:10]]}
    try:
        return hole(f"nasdaq_analyse_{ticker}", "Nasdaq (Analysten)", 12, laden)[0]
    except Exception:
        return None


def details(ticker: str, name: str) -> dict:
    from terminal import technik
    from terminal.quellen import yahoo

    fmp = FMP()
    us = _ist_us(ticker)
    d = {"ticker": ticker, "name": name, "erstellt": jetzt_utc().isoformat()}

    # --- Yahoo-Grunddaten (für alle Märkte) ---
    try:
        y = yahoo.fundamentaldaten(ticker)
    except Exception as e:
        y, d["yahoo_fehler"] = {}, str(e)[:120]

    # --- Fundamentaldaten ---
    fund, quelle = {}, None
    if us:
        k = fmp.kennzahlen(ticker)
        if k.ok:
            fund, quelle = {key: v for key, v in k.daten.items() if key != "symbol"}, "FMP"
    if y:
        ergaenzung = {"kgv": y.get("trailingPE"), "kgv_erwartet": y.get("forwardPE"), "kurs_umsatz": y.get("priceToSalesTrailing12Months"),
                      "nettomarge": y.get("profitMargins"), "operative_marge": y.get("operatingMargins") or None,
                      "eigenkapitalrendite": y.get("returnOnEquity"), "umsatzwachstum": y.get("revenueGrowth"),
                      "gewinnwachstum": y.get("earningsGrowth"), "dividendenrendite": y.get("dividendYield"),
                      "verschuldung": y.get("debtToEquity"), "beta": y.get("beta"), "boersenwert": y.get("marketCap")}
        for key, v in ergaenzung.items():
            if fund.get(key) is None and v is not None:
                fund[key] = v
        quelle = f"{quelle} + Yahoo" if quelle else "Yahoo"
    if y.get("financialCurrency") and y.get("currency") and y["financialCurrency"] != y["currency"]:
        # Bewertungskennzahlen aus gemischten Währungen (z. B. Bericht in DKK, Kurs in USD) sind unzuverlässig
        for key in ("kgv", "kgv_erwartet", "kurs_umsatz"):
            fund.pop(key, None)
        d["waehrungshinweis"] = f"Berichtswährung {y['financialCurrency']}, Kurs in {y['currency']}"
    d["fundamental"] = {"werte": fund, "quelle": quelle, "art": "offiziell"} if fund else \
        {"werte": {}, "quelle": None, "grund": "keine Fundamentaldaten verfügbar (z. B. bei ETFs)"}
    d["profil"] = {"sektor": y.get("sector"), "branche": y.get("industry"), "land": y.get("country"),
                   "waehrung": y.get("currency"), "mitarbeiter": y.get("fullTimeEmployees")}

    # --- Kursziel und Empfehlungen ---
    ziel, ziel_quelle = None, None
    if us:
        z = fmp.kursziel(ticker)
        if z.ok:
            ziel, ziel_quelle = z.daten, "FMP"
    nas = _nasdaq(ticker) if us else None
    if not ziel and nas and nas.get("mittel"):
        ziel, ziel_quelle = {k: nas[k] for k in ("mittel", "hoch", "tief")}, "Nasdaq"
    if not ziel and y.get("targetMeanPrice"):
        ziel, ziel_quelle = {"mittel": y.get("targetMeanPrice"), "median": y.get("targetMedianPrice"),
                             "hoch": y.get("targetHighPrice"), "tief": y.get("targetLowPrice")}, "Yahoo"
    d["kursziel"] = {**ziel, "quelle": ziel_quelle, "art": "schaetzung"} if ziel else {"grund": "kein Analysten-Kursziel verfügbar"}

    if nas and (nas.get("kaufen") is not None):
        d["empfehlung"] = {"kaufen": nas["kaufen"], "halten": nas["halten"], "verkaufen": nas["verkaufen"],
                           "tendenz": nas.get("tendenz"), "banken": nas["banken"], "quelle": "Nasdaq", "art": "schaetzung"}
    elif y.get("numberOfAnalystOpinions"):
        d["empfehlung"] = {"anzahl": y["numberOfAnalystOpinions"], "tendenz": y.get("recommendationKey"), "banken": [],
                           "quelle": "Yahoo", "art": "schaetzung"}
    else:
        d["empfehlung"] = {"grund": "keine Analysten-Empfehlungen verfügbar"}

    # --- Einstufungen einzelner Häuser (wer?) ---
    einst = fmp.einstufungen(ticker) if us else None
    if einst is not None and einst.ok and einst.daten:
        d["einstufungen"] = {"liste": einst.daten, "quelle": "FMP", "art": "schaetzung"}
    elif nas and nas.get("aenderungen"):
        d["einstufungen"] = {"liste": nas["aenderungen"], "quelle": "Nasdaq", "art": "schaetzung"}
    else:
        d["einstufungen"] = {"liste": [], "grund": "Einstufungen einzelner Banken gratis nur für US-Aktien verfügbar"
                             if not us else "keine Einstufungen gefunden"}

    # --- Schätzungen ---
    if us:
        s = fmp.schaetzungen(ticker)
        d["schaetzungen"] = {"jahre": s.daten, "quelle": "FMP", "art": "schaetzung"} if s.ok and s.daten else {"jahre": [], "grund": s.grund or "keine"}
    else:
        eps = y.get("forwardEps")
        d["schaetzungen"] = {"jahre": [{"jahr": "nächste 12 Mt.", "eps": eps}] if eps else [], "quelle": "Yahoo" if eps else None,
                             "art": "schaetzung", "grund": None if eps else "keine Schätzungen verfügbar"}

    # --- Chart-Technik ---
    try:
        t = technik.auswertung(yahoo.ohlc(ticker))
        d["technik"] = {k: t[k] for k in ("kurs", "sma50", "sma200", "abstand200", "rsi", "macd_positiv", "trend",
                                          "trendpunkte", "signale", "unterstuetzung", "widerstand", "hoch52", "tief52", "vom_hoch")}
        d["technik"]["pivots"] = {k: v for k, v in t["pivots"].items() if k != "basis"}
        d["technik"]["quelle"], d["technik"]["art"] = "eigene Berechnung aus Yahoo-Tageskursen", "eigene_berechnung"
        d["technik"]["sma50_reihe"] = [round(float(v), 4) if v == v else None for v in t["sma50_reihe"].iloc[-400:].values]
        d["technik"]["sma200_reihe"] = [round(float(v), 4) if v == v else None for v in t["sma200_reihe"].iloc[-400:].values]
        d["technik"]["reihe_daten"] = [x.strftime("%Y-%m-%d") for x in t["sma50_reihe"].iloc[-400:].index]
    except Exception as e:
        d["technik"] = {"grund": f"Technik nicht berechenbar: {str(e)[:100]}"}
    return d
