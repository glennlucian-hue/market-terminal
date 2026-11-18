"""Sammel-Job: holt alle Daten der neuen Provider-Schicht und schreibt verschlüsselte Datenpakete.

Läuft auf GitHub alle 15 Minuten (siehe .github/workflows/website.yml) und wird auch von der heutigen
Website verwendet (Wirtschaftskalender, Quartalszahlen, Krypto, US-Top-Bewegungen, Datenquellen-Status).

Datenpakete: website/pakete/<name>.json.enc – NUR verschlüsselt (Passwort aus SITE_PASSWORT).
Ohne Passwort (z. B. lokal) werden keine Pakete geschrieben, die Daten stehen trotzdem der Website zur Verfügung.
"""
import json
import os
from pathlib import Path

from .datenpunkt import jetzt_utc
from .kurse import kurs
from .provider import AlphaVantage, CoinGecko, Finnhub, FredKalender
from .verschluesselung import verschluesseln

# Grosse US-Firmen, deren Quartalszahlen marktbewegend sind (zusätzlich zur Watchlist)
GROSSE_US_FIRMEN = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "AVGO", "TSLA", "BRK.B", "JPM", "V", "MA", "WMT",
    "LLY", "UNH", "XOM", "ORCL", "COST", "HD", "PG", "NFLX", "JNJ", "BAC", "CRM", "AMD", "ADBE", "KO", "PEP",
    "CSCO", "TMO", "NOW", "PLTR", "SNOW", "CRWV", "TSM", "ASML", "MU", "INTC", "QCOM", "GS", "MS", "DIS", "NKE",
    "SBUX", "BA", "CAT", "TGT", "LOW", "PANW", "SHOP", "UBER", "ABNB", "COIN", "MELI", "SE", "KSPI", "ANT",
}
# Wirtschaftsdaten mit grösster Marktwirkung (für die Markierung "wichtig")
WICHTIGE_MAKRO = {"Konsumentenpreise (CPI)", "Arbeitsmarktbericht (NFP)", "Einkommen & Konsum (PCE-Inflation)",
                  "Bruttoinlandprodukt (BIP)"}


def _status(name, ergebnis) -> dict:
    return {"quelle": name, "ok": ergebnis.ok, "grund": ergebnis.grund, "abgerufen": ergebnis.abgerufen.isoformat()}


def _min_preis(liste, minimum=5.0):
    """Penny Stocks und Optionsscheine (Kurs unter 5 USD) aus Ranglisten entfernen."""
    return [x for x in liste if (x.get("kurs") or 0) >= minimum]


def _historie(symbole: list[str], tage: int = 400) -> dict:
    """Tagesschlusskurse für Charts (aus dem Yahoo-Cache, ~1 Jahr). Format: {symbol: {"t": [...], "c": [...]}}."""
    from terminal.quellen import yahoo
    erg = {}
    for symbol in symbole:
        try:
            s, meta = yahoo.kurse(symbol, 0.25)
        except Exception:
            continue
        s = s.dropna().iloc[-tage:]
        erg[symbol] = {"t": [d.strftime("%Y-%m-%d") for d in s.index], "c": [round(float(v), 6) for v in s.values],
                       "waehrung": meta.get("waehrung"), "quelle": "yahoo", "art": "schluss"}
    return erg


def sammle(watchlist_ticker: list[str] | None = None, relevante_aktien: set[str] | None = None,
           watchlist_struktur: list[dict] | None = None) -> dict:
    relevante = GROSSE_US_FIRMEN | set(relevante_aktien or [])
    status = []
    ergebnis = {"erstellt": jetzt_utc().isoformat()}

    # Krypto (CoinGecko)
    cg = CoinGecko()
    m, t = cg.markt(), cg.top_coins(15)
    status += [_status("CoinGecko (Markt)", m), _status("CoinGecko (Top-Coins)", t)]
    ergebnis["krypto"] = {"markt": m.daten if m.ok else None, "coins": t.daten if t.ok else [],
                          "fehler": None if (m.ok and t.ok) else (m.grund or t.grund)}

    # Wirtschaftskalender (FRED)
    w = FredKalender().wirtschaftstermine(21)
    status.append(_status("FRED (Wirtschaftskalender)", w))
    ergebnis["wirtschaftstermine"] = [{**x, "wichtig": x["ereignis"] in WICHTIGE_MAKRO} for x in (w.daten or [])] if w.ok else []

    # Quartalszahlen-Kalender (Finnhub), gefiltert auf relevante Firmen
    e = Finnhub().earnings_kalender(21)
    status.append(_status("Finnhub (Quartalszahlen)", e))
    ergebnis["earnings"] = [x for x in (e.daten or []) if x["symbol"] in relevante] if e.ok else []

    # US-Top-Bewegungen (Alpha Vantage, 1 Abfrage alle 6 Stunden)
    a = AlphaVantage().top_bewegungen()
    status.append(_status("Alpha Vantage (Top-Bewegungen)", a))
    if a.ok:
        ergebnis["top_bewegungen"] = {"stand": a.daten["stand"], "gewinner": _min_preis(a.daten["gewinner"]),
                                      "verlierer": _min_preis(a.daten["verlierer"]),
                                      "meistgehandelt": a.daten["meistgehandelt"]}
    else:
        ergebnis["top_bewegungen"] = None

    # Kurse der Watchlist mit Ersatzkette (Yahoo -> Finnhub -> FMP)
    kurse = {}
    for symbol in watchlist_ticker or []:
        if symbol.isupper() and len(symbol) <= 12:
            kurse[symbol] = kurs(symbol)
    ergebnis["kurse"] = kurse
    ergebnis["historie"] = _historie(list(kurse))
    ergebnis["watchlist"] = watchlist_struktur or []
    ersatz = [s for s, k in kurse.items() if k["ok"] and k["quelle"] != "yahoo"]
    fehlt = [s for s, k in kurse.items() if not k["ok"]]
    status.append({"quelle": "Kurs-Ersatzkette", "ok": not fehlt,
                   "grund": (f"Ersatzquelle für {', '.join(ersatz)}. " if ersatz else "") +
                            (f"Keine Kurse für {', '.join(fehlt)}." if fehlt else ""),
                   "abgerufen": jetzt_utc().isoformat()})
    ergebnis["status"] = status
    return ergebnis


def schreibe_pakete(daten: dict, ordner: Path) -> list[str]:
    """Schreibt je Bereich ein verschlüsseltes Paket. Ohne Passwort: nichts schreiben (nie unverschlüsselt)."""
    passwort = os.getenv("SITE_PASSWORT", "")
    if not passwort:
        return []
    ordner.mkdir(parents=True, exist_ok=True)
    geschrieben = []
    for name in ("krypto", "wirtschaftstermine", "earnings", "top_bewegungen", "kurse", "historie", "watchlist", "status"):
        huelle = verschluesseln({"erstellt": daten["erstellt"], "inhalt": daten.get(name)}, passwort)
        (ordner / f"{name}.json.enc").write_text(json.dumps(huelle), encoding="utf-8")
        geschrieben.append(name)
    (ordner / "index.json").write_text(json.dumps({"erstellt": daten["erstellt"], "pakete": geschrieben,
                                                   "format": "mt-aesgcm-1"}), encoding="utf-8")
    return geschrieben
