"""Baut die komplette Website (mehrere HTML-Seiten) im Ordner website/.

Ablauf:  1. Daten sammeln (jede Quelle einzeln abgesichert)
         2. Analysen rechnen
         3. Seiten mit den Vorlagen aus vorlagen/ erzeugen
Fällt eine Quelle aus, erscheint an ihrer Stelle "Daten nicht verfügbar" – der Rest wird trotzdem gebaut.
"""
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.offline
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import analysen, anthropic_seite, cache, charts, kennzahlen, vergleich_seite
from .konfiguration import VORLAGEN_ORDNER, WEBSITE_ORDNER
from .quellen import cftc, fred, news, portwatch, yahoo

ZUERICH = ZoneInfo("Europe/Zurich")
NEW_YORK = ZoneInfo("America/New_York")
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

SEITEN = [("index", "Übersicht"), ("maerkte", "Märkte"), ("makro", "Makro & Zinsen"),
          ("positionierung", "Positionierung"), ("themen", "Themen"), ("anthropic", "Anthropic & IPOs"),
          ("termine", "Termine"),
          ("news", "News"), ("status", "Datenstatus")]

# Zusätzliche Kurse für Analysen (falls nicht schon in der Watchlist)
EXTRA_TICKER = {"^SOX": "Halbleiter-Index (SOX)", "AVGO": "Broadcom", "TSM": "TSMC"}
KI_KORB = ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "TSM"]

FRED_SERIEN = {
    "DGS1MO": "1M", "DGS3MO": "3M", "DGS6MO": "6M", "DGS1": "1J", "DGS2": "2J", "DGS3": "3J",
    "DGS5": "5J", "DGS7": "7J", "DGS10": "10J", "DGS20": "20J", "DGS30": "30J",
    "T10Y2Y": None, "DFF": None, "DFEDTARU": None, "CPIAUCSL": None, "PCEPILFE": None, "UNRATE": None,
    "ICSA": None, "DFII10": None, "T10YIE": None, "BAMLH0A0HYM2": None,
    "WALCL": None, "WTREGEN": None, "RRPONTSYD": None,
}
Q_YAHOO, Q_FRED, Q_CFTC = "Yahoo Finance", "FRED, Federal Reserve Bank of St. Louis", "CFTC Commitments of Traders"


# ===========================================================================
# Formatierung
# ===========================================================================
def fmt_zahl(x, stellen=None) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    if stellen is None:
        stellen = 4 if abs(x) < 10 else 2 if abs(x) < 10000 else 0
    return f"{x:,.{stellen}f}".replace(",", "’")


def fmt_veraenderung(x, einheit="%") -> str:
    if x is None or pd.isna(x):
        return "–"
    pfeil = "▲" if x > 0 else "▼" if x < 0 else "■"
    return f"{pfeil} {x:+.0f} bp" if einheit == "bp" else f"{pfeil} {x:+.2f}%"


def fmt_kurs(z: dict) -> str:
    """Kurs eines Watchlist-Werts: Renditen immer mit 2 Nachkommastellen."""
    return fmt_zahl(z.get("kurs"), 2 if z.get("einheit") == "bp" else None)


def css_klasse(x) -> str:
    if x is None or pd.isna(x) or abs(x) < 1e-9:
        return "neutral"
    return "plus" if x > 0 else "minus"


def fmt_mrd(x) -> str:
    if not x:
        return "–"
    return f"{x / 1e12:,.2f} Bio.".replace(",", "’") if x >= 1e12 else f"{x / 1e9:,.0f} Mrd.".replace(",", "’")


def vor_wann(iso: str | None) -> str:
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    diff = datetime.now(timezone.utc) - t
    if diff < timedelta(hours=1):
        return f"vor {max(1, int(diff.total_seconds() // 60))} Min."
    if diff < timedelta(hours=24):
        return f"vor {int(diff.total_seconds() // 3600)} Std."
    return t.astimezone(ZUERICH).strftime("%d.%m.%Y")


def anker(text: str) -> str:
    """Macht aus einem Ticker oder Namen eine gültige Sprungmarke für Links (#...)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def datum_lang(d) -> str:
    return f"{WOCHENTAGE[d.weekday()]}, {d.day}. {MONATE[d.month - 1]} {d.year}"


def datum_kurz(d) -> str:
    return f"{WOCHENTAGE[d.weekday()][:2]}, {d.day:02d}.{d.month:02d}."


# ===========================================================================
# Datensammlung
# ===========================================================================
class Sammlung:
    """Hält alle geladenen Daten. Jeder Zugriff liefert None, wenn die Quelle ausgefallen ist."""

    def __init__(self, watchlist: dict, themen: list[dict], melde=print):
        self.watchlist, self.themen, self.melde = watchlist, themen, melde
        self.cache_stunden = watchlist["einstellungen"]["cache_stunden"]
        self.kurse: dict[str, pd.Series] = {}
        self.meta: dict[str, dict] = {}
        self.fehler: dict[str, str] = {}
        self.fred: dict[str, pd.Series] = {}

    # --- Hilfen -----------------------------------------------------------
    def _versuche(self, schluessel, funktion, *args):
        try:
            return funktion(*args)
        except Exception as e:
            self.fehler[schluessel] = str(e)
            return None

    def reihe(self, ticker: str) -> pd.Series | None:
        return self.kurse.get(ticker)

    # --- Laden ------------------------------------------------------------
    def lade_alles(self):
        werte = [w for g in self.watchlist["gruppen"] for w in g["werte"]]
        yahoo_ticker = {w["ticker"] for w in werte if w["quelle"] == "yahoo"} | set(EXTRA_TICKER) | set(KI_KORB)
        fred_ids = set(FRED_SERIEN) | {w["ticker"] for w in werte if w["quelle"] == "fred"}

        self.melde(f"  Kurse von Yahoo Finance ({len(yahoo_ticker)} Werte) ...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            for t, erg in zip(yahoo_ticker, pool.map(
                    lambda t: self._versuche(t, yahoo.kurse, t, self.cache_stunden), yahoo_ticker)):
                if erg is not None:
                    self.kurse[t], self.meta[t] = erg

        self.melde(f"  Makrodaten von FRED ({len(fred_ids)} Serien) ...")
        with ThreadPoolExecutor(max_workers=6) as pool:
            for sid, erg in zip(fred_ids, pool.map(lambda s: self._versuche(s, fred.serie, s), fred_ids)):
                if erg is not None:
                    self.fred[sid] = erg[0]
                    self.kurse[sid], self.meta[sid] = erg

        self.melde("  Positionierung (CFTC), Hormuz (IMF PortWatch), Fed-Kalender ...")
        self.cftc = {m: (r[0] if (r := self._versuche(f"cftc_{m}", cftc.netto_positionen, m)) else None)
                     for m in cftc.MAERKTE}
        pw = self._versuche("portwatch", portwatch.durchfahrten)
        self.hormuz = pw[0] if pw else None
        self.fed_kalender = self._versuche("fed_kalender", news.fed_kalender) or []
        self.fed_reden = self._versuche("fed_reden", news.fed_reden) or []

        self.melde("  Firmendaten und Termine der Quartalszahlen ...")
        aktien = KI_KORB + [w["ticker"] for g in self.watchlist["gruppen"] if g["name"] == "Aktien"
                            for w in g["werte"]]
        aktien = list(dict.fromkeys(aktien))
        with ThreadPoolExecutor(max_workers=6) as pool:
            self.firmen = dict(zip(aktien, pool.map(lambda t: self._versuche(f"info_{t}", yahoo.firmendaten, t),
                                                    aktien)))

        self.melde("  News zu den Themen (Google News) ...")
        self.news = {}
        for thema in self.themen:
            artikel = []
            for begriff in thema["suchbegriffe"]:
                artikel += self._versuche(f"news_{begriff}", news.google_news, begriff) or []
            self.news[thema["id"]] = _sortiere_news(artikel)

        self.melde("  Neue Datenquellen (Finnhub, FRED-Kalender, CoinGecko, Alpha Vantage) ...")
        relevante = set(KI_KORB) | {w["ticker"] for g in self.watchlist["gruppen"] for w in g["werte"]}
        try:
            from kern.sammeln import sammle
            struktur = [{"gruppe": g["name"], "werte": [{"ticker": w["ticker"], "name": w["name"], "art": w["art"],
                                                       "quelle": w["quelle"]} for w in g["werte"]]}
                        for g in self.watchlist["gruppen"]]
            self.kern = sammle(sorted(t for t in yahoo_ticker if t.isupper()), relevante, struktur)
            # FRED-Serien der Watchlist (z. B. US-Renditen) als Kurse und Verlauf ergänzen
            for w in (w for g in self.watchlist["gruppen"] for w in g["werte"] if w["quelle"] == "fred"):
                reihe = self.fred.get(w["ticker"])
                if reihe is None or len(reihe) < 2:
                    continue
                self.kern["kurse"][w["ticker"]] = {
                    "ok": True, "quelle": "fred", "art": "offiziell", "abgerufen": self.kern["erstellt"], "versuche": [],
                    "daten": {"symbol": w["ticker"], "kurs": float(reihe.iloc[-1]), "vortag": float(reihe.iloc[-2]),
                              "veraenderung_pct": None, "stand": reihe.index[-1].strftime("%Y-%m-%dT00:00:00+00:00"),
                              "waehrung": "%"}}
                teil = reihe.iloc[-400:]
                self.kern["historie"][w["ticker"]] = {"t": [x.strftime("%Y-%m-%d") for x in teil.index],
                                                      "c": [round(float(v), 4) for v in teil.values],
                                                      "waehrung": "%", "quelle": "fred", "art": "offiziell"}
            if os.getenv("GITHUB_ACTIONS") == "true":   # Status als öffentlicher Hinweis (nie Schlüssel)
                for q in self.kern.get("status", []):
                    print(f"::{'notice' if q['ok'] else 'warning'} title={q['quelle']}::"
                          f"{'in Ordnung' if q['ok'] else 'Problem'} {q['grund'][:150]}", flush=True)
        except Exception as e:
            self.kern = {}
            self.fehler["kern_sammeln"] = f"{type(e).__name__}: {e}"


def _sortiere_news(artikel: list[dict], anzahl: int = 12) -> list[dict]:
    gesehen, ergebnis = set(), []
    for a in sorted(artikel, key=lambda a: a.get("zeit") or "", reverse=True):
        schluessel = a["titel"].lower()[:70]
        if schluessel in gesehen or len(a["titel"].strip(" -–")) < 20:  # leere/zu kurze Titel überspringen
            continue
        gesehen.add(schluessel)
        ergebnis.append({**a, "vor": vor_wann(a.get("zeit"))})
    return ergebnis[:anzahl]


# ===========================================================================
# Seiteninhalte
# ===========================================================================
def _alle_werte(d: Sammlung) -> list[dict]:
    """Alle Watchlist-Werte mit Kennzahlen (oder Fehler)."""
    zeilen = []
    for g in d.watchlist["gruppen"]:
        for w in g["werte"]:
            s = d.reihe(w["ticker"])
            z = {**w, "gruppe": g["name"], "ok": s is not None}
            if s is not None:
                meta = d.meta.get(w["ticker"], {})
                z.update(kennzahlen.berechne(s, w["art"]), serie=s, hinweis=meta.get("hinweis", ""),
                         waehrung="%" if w["art"] == "rendite" else meta.get("waehrung", ""),
                         veraltet=(datetime.now() - s.index[-1].to_pydatetime()).days > 4,
                         quelle_name=Q_FRED if w["quelle"] == "fred" else Q_YAHOO)
            else:
                z["fehler"] = d.fehler.get(w["ticker"], "unbekannter Fehler")
            zeilen.append(z)
    return zeilen


def _kurs_chart(z: dict, hoehe=250, start_tage=365, knoepfe=True) -> Markup:
    if not z["ok"]:
        return charts.fehlt(z["name"], z["fehler"])
    unter = "Rendite in %" if z["art"] == "rendite" else f"Schlusskurs in {z['waehrung']}" if z["waehrung"] else "Schlusskurs"
    zwei_jahre = z["serie"][z["serie"].index >= z["serie"].index[-1] - timedelta(days=740)]  # Knöpfe zeigen max. 2 J.
    return charts.linien({z["name"]: zwei_jahre}, titel=z["name"], untertitel=unter,
                         quelle=f"{z['quelle_name']} ({z['ticker']})", einheit="%" if z["art"] == "rendite" else "",
                         start_tage=start_tage, knoepfe=knoepfe, hoehe=hoehe, hinweis=z.get("hinweis", ""))


def _indexiert(serien: dict[str, pd.Series], tage: int = 365) -> dict[str, pd.Series]:
    """Mehrere Kurse auf 100 setzen (gleicher Start), damit sie auf EINER Achse vergleichbar sind."""
    erg = {}
    for name, s in serien.items():
        if s is None:
            continue
        teil = s[s.index >= s.index[-1] - timedelta(days=tage)]
        erg[name] = teil / teil.iloc[0] * 100
    return erg


def seite_maerkte(d: Sammlung, werte: list[dict]) -> dict:
    gruppen = []
    for g in d.watchlist["gruppen"]:
        zeilen = [z for z in werte if z["gruppe"] == g["name"]]
        for z in zeilen:
            if z["ok"]:
                z["mini"] = charts.mini(z["serie"], charts.FARBEN[0])
        gruppen.append({"name": g["name"], "id": anker(g["name"]), "zeilen": zeilen,
                        "charts": [_kurs_chart(z, hoehe=215) for z in zeilen]})
    return {"gruppen": gruppen, "krypto": (getattr(d, "kern", {}) or {}).get("krypto")}


def seite_makro(d: Sammlung) -> dict:
    f = d.fred
    bloecke = []

    # Zinskurve
    laufzeiten = {k: v for k, v in FRED_SERIEN.items() if v}
    if all(k in f for k in laufzeiten):
        df = pd.concat({v: f[k] for k, v in laufzeiten.items()}, axis=1).ffill().dropna()
        letzt = df.index[-1]
        kurven = {f"Aktuell ({letzt:%d.%m.%Y})": df.iloc[-1],
                  "Vor 1 Monat": df[df.index <= letzt - timedelta(days=30)].iloc[-1],
                  "Vor 1 Jahr": df[df.index <= letzt - timedelta(days=365)].iloc[-1]}
        bloecke.append(charts.kurve(kurven, titel="US-Zinskurve", quelle=Q_FRED, breit=True,
                       untertitel="Rendite von US-Staatsanleihen nach Laufzeit, in %"))
    else:
        bloecke.append(charts.fehlt("US-Zinskurve", "Nicht alle Laufzeiten verfügbar", breit=True))

    def linie(ids_namen, titel, unter, einheit="%", start=730, erkl="", null=False, umrechnen=None):
        serien = {}
        for sid, name in ids_namen.items():
            if sid not in f:
                return charts.fehlt(titel, d.fehler.get(sid, f"{sid} fehlt"))
            reihe = umrechnen(f[sid]) if umrechnen else f[sid]
            serien[name] = reihe[reihe.index >= reihe.index[-1] - timedelta(days=max(start, 730) + 31)]
        return charts.linien(serien, titel=titel, untertitel=unter, quelle=f"{Q_FRED} ({', '.join(ids_namen)})",
                             einheit=einheit, start_tage=start, hinweis=erkl, nulllinie=null)

    bloecke += [
        linie({"DGS2": "2 Jahre", "DGS10": "10 Jahre"}, "US-Staatsanleihen: Renditen", "in %", start=365,
              erkl="Die 2-jährige Rendite reagiert stark auf erwartete Leitzinsen, die 10-jährige auf Wachstum und Inflation."),
        linie({"T10Y2Y": "10 J. minus 2 J."}, "Steilheit der Zinskurve", "Differenz in Prozentpunkten", start=730,
              null=True, erkl="Unter null (\"inverse Kurve\") galt historisch als Rezessionssignal."),
        linie({"DFEDTARU": "Leitzins (Obergrenze)", "DFF": "Effektiver Tagesgeldsatz"}, "US-Leitzins",
              "in %", start=730),
        linie({"CPIAUCSL": "Konsumentenpreise (CPI)", "PCEPILFE": "Kern-PCE (Fed-Zielgrösse)"}, "US-Inflation",
              "Veränderung gegenüber Vorjahr in %", start=1825, umrechnen=analysen.jahresveraenderung,
              erkl="Die Fed strebt 2 % Kern-PCE-Inflation an."),
        linie({"UNRATE": "Arbeitslosenquote"}, "US-Arbeitsmarkt", "Arbeitslosenquote in %", start=1825),
        linie({"ICSA": "Erstanträge"}, "Erstanträge auf Arbeitslosenhilfe", "pro Woche, Anzahl", einheit="",
              start=730, erkl="Steigende Erstanträge sind ein frühes Signal für einen schwächeren Arbeitsmarkt."),
        linie({"DFII10": "Realrendite 10 J.", "T10YIE": "Inflationserwartung 10 J."},
              "Realrendite und Inflationserwartung", "in %", start=730,
              erkl="Hohe Realrenditen belasten typischerweise Gold und Wachstumsaktien."),
        linie({"BAMLH0A0HYM2": "Risikoaufschlag High Yield"}, "Kreditrisiko: Hochzinsanleihen",
              "Aufschlag gegenüber Staatsanleihen in %", start=730,
              erkl="Ein steigender Aufschlag zeigt Stress am Kreditmarkt."),
    ]
    return {"bloecke": bloecke, "liquiditaet": _liquiditaet_chart(d), "kennzahlen": _makro_kennzahlen(d)}


def _makro_kennzahlen(d: Sammlung) -> list[dict]:
    """Die wichtigsten US-Makrowerte auf einen Blick, mit Veränderung gegenüber dem Vormonat."""
    f = d.fred
    defs = [("DFEDTARU", "Leitzins (Obergrenze)", None), ("DGS2", "Rendite 2 J.", None),
            ("DGS10", "Rendite 10 J.", None), ("T10Y2Y", "Steilheit 10J–2J", None),
            ("CPIAUCSL", "Inflation (CPI, J/J)", analysen.jahresveraenderung),
            ("PCEPILFE", "Kern-PCE (J/J)", analysen.jahresveraenderung),
            ("UNRATE", "Arbeitslosenquote", None), ("BAMLH0A0HYM2", "High-Yield-Aufschlag", None)]
    ergebnis = []
    for sid, name, umrechnen in defs:
        if sid not in f:
            ergebnis.append({"name": name, "wert": None})
            continue
        s = umrechnen(f[sid]) if umrechnen else f[sid]
        vormonat = kennzahlen.kurs_am_oder_vor(s, s.index[-1] - timedelta(days=31))
        diff = (float(s.iloc[-1]) - vormonat) * 100 if vormonat is not None else None
        ergebnis.append({"name": name, "wert": float(s.iloc[-1]), "diff_bp": diff, "stand": s.index[-1]})
    return ergebnis


def _liquiditaet_chart(d: Sammlung, breit=True) -> Markup:
    f = d.fred
    if not all(k in f for k in ("WALCL", "WTREGEN", "RRPONTSYD")):
        return charts.fehlt("US-Liquidität (Net Liquidity)", "FRED-Daten fehlen", breit)
    netto = analysen.netto_liquiditaet(f["WALCL"], f["WTREGEN"], f["RRPONTSYD"])
    return charts.linien({"Net Liquidity": netto}, titel="US-Liquidität (Net Liquidity)",
                         untertitel="Fed-Bilanz minus Treasury-Konto (TGA) minus Reverse Repo, in Bio. USD",
                         quelle=f"{Q_FRED} (WALCL, WTREGEN, RRPONTSYD); eigene Berechnung", start_tage=730,
                         breit=breit, hinweis="Steigt die Linie, fliesst tendenziell Liquidität ins Finanzsystem.")


def _cta(d: Sammlung) -> dict | None:
    s = d.reihe("^GSPC")
    if s is None or len(s) < 300:
        return None
    return analysen.cta_modell(s)


def seite_positionierung(d: Sammlung) -> dict:
    ctx = {}
    cta = _cta(d)
    if cta:
        ctx["cta"] = cta
        ctx["cta_chart"] = charts.linien(
            {"Modell-Exposure": cta["exposure"]}, titel="CTA-Modell: geschätzte Positionierung im S&P 500",
            untertitel="in % der maximalen Position (−100 = voll short, +100 = voll long)", einheit="pct_signed",
            quelle=f"Eigene Berechnung auf Basis {Q_YAHOO} (^GSPC)", start_tage=730, nulllinie=True, breit=True,
            y_bereich=(-100, 100),
            hinweis="Modellschätzung, keine echten Positionsdaten. Methode: Trendsignale über 1, 3, 6 und 12 Monate, "
                    "verkleinert bei hoher Volatilität.")
    sp = d.cftc.get("sp500")
    if sp is not None:
        ctx["cftc_sp"] = charts.linien(
            {k: sp[k] for k in sp.columns if k != "Open Interest"}, titel="S&P 500 Futures: Netto-Positionen",
            untertitel="Long minus Short, Anzahl Kontrakte (E-Mini)", quelle=Q_CFTC, start_tage=1095, nulllinie=True)
    else:
        ctx["cftc_sp"] = charts.fehlt("S&P 500 Futures: Netto-Positionen", d.fehler.get("cftc_sp500", ""))
    for m, titel in (("gold", "Gold"), ("wti", "WTI-Rohöl")):
        df = d.cftc.get(m)
        ctx[f"cftc_{m}"] = charts.linien(
            {df.columns[0]: df.iloc[:, 0]}, titel=f"{titel}: Netto-Positionen der Hedgefonds",
            untertitel="Managed Money, Long minus Short, Anzahl Kontrakte", quelle=Q_CFTC, start_tage=1095,
            nulllinie=True) if df is not None else charts.fehlt(titel, d.fehler.get(f"cftc_{m}", ""))

    tabelle = []
    for m, info in cftc.MAERKTE.items():
        df = d.cftc.get(m)
        if df is None:
            continue
        for gruppe in info["gruppen"]:
            s = df[gruppe]
            tabelle.append({"markt": info["name"], "gruppe": gruppe, "netto": float(s.iloc[-1]),
                            "woche": float(s.iloc[-1] - s.iloc[-2]), "perzentil": analysen.perzentil(s),
                            "stand": s.index[-1]})
    ctx["cftc_tabelle"] = tabelle
    return ctx


def _termine(d: Sammlung, tage: int = 21) -> list[dict]:
    heute = date.today()
    bis = heute + timedelta(days=tage)
    liste = []
    for t in d.fed_kalender:
        tag = date.fromisoformat(t["datum"])
        if not heute <= tag <= bis:
            continue
        zeit_ch = ""
        try:
            roh = t["zeit_et"].replace(".", "").upper()
            et = datetime.strptime(f"{t['datum']} {roh}", "%Y-%m-%d %I:%M %p").replace(tzinfo=NEW_YORK)
            zeit_ch = et.astimezone(ZUERICH).strftime("%H:%M")
        except Exception:
            pass
        art = {"Speeches": "Fed-Rede", "FOMC": "FOMC", "Testimony": "Anhörung", "Stat": "Statistik",
               "Beige": "Beige Book", "Other": "Sonstiges"}.get(t["art"], t["art"] or "Fed")
        liste.append({"datum": tag, "zeit": zeit_ch, "art": art,
                      "titel": t["titel"].replace("Speech - ", "").replace("Discussion - ", "Diskussion: "),
                      "detail": re.sub(r"<[^>]+>", "", t["thema"]).strip(),
                      "wichtig": "Chair" in t["titel"] or "FOMC" in t["art"]})
    for ticker, info in d.firmen.items():
        if info and info.get("naechste_zahlen"):
            tag = date.fromisoformat(info["naechste_zahlen"])
            if heute <= tag <= bis:
                liste.append({"datum": tag, "zeit": "", "art": "Quartalszahlen", "titel": info["name"],
                              "detail": ticker, "wichtig": ticker == "NVDA"})
    try:
        liste += [t for t in anthropic_seite.termine() if heute <= t["datum"] <= bis]
    except Exception:
        pass
    kern = getattr(d, "kern", {}) or {}
    for t in kern.get("wirtschaftstermine", []):
        tag = date.fromisoformat(t["datum"])
        if heute <= tag <= bis:
            liste.append({"datum": tag, "zeit": "", "art": "Wirtschaftsdaten", "titel": t["ereignis"],
                          "detail": "USA · Quelle FRED", "wichtig": t["wichtig"]})
    schon = {(x["detail"], x["datum"]) for x in liste if x["art"] == "Quartalszahlen"}
    for t in kern.get("earnings", []):
        tag = date.fromisoformat(t["datum"])
        if heute <= tag <= bis and (t["symbol"], tag) not in schon:
            eps = f" · erwarteter Gewinn/Aktie {t['eps_schaetzung']:.2f} USD" if t.get("eps_schaetzung") else ""
            liste.append({"datum": tag, "zeit": t["zeit"], "art": "Quartalszahlen", "titel": t["symbol"],
                          "detail": f"Quelle Finnhub{eps}", "wichtig": t["symbol"] in ("NVDA", "AAPL", "MSFT", "ANT")})
    for x in liste:  # Sortierschlüssel: Zeiten wie "vor Börsenbeginn" vor leeren Zeiten
        x.setdefault("zeit", "")
    liste.sort(key=lambda x: (x["datum"], x["zeit"] if x["zeit"][:1].isdigit() else "99"))
    vorher = None
    for x in liste:
        x["tag_text"] = datum_kurz(x["datum"])
        x["tag_lang"] = ("Heute · " if x["datum"] == heute else "Morgen · " if x["datum"] == heute + timedelta(days=1)
                         else "") + datum_lang(x["datum"])
        x["neuer_tag"] = x["datum"] != vorher
        vorher = x["datum"]
    return liste


def seite_themen(d: Sammlung, werte: list[dict]) -> list[dict]:
    ergebnis = []
    for t in d.themen:
        block = {**t, "news": d.news.get(t["id"], []), "charts": [], "tabellen": {}}
        a = t.get("analyse")
        if a == "fed":
            block["termine"] = [x for x in _termine(d, 14) if x["art"] != "Quartalszahlen"]
            for i, x in enumerate(block["termine"]):
                x["neuer_tag"] = i == 0 or x["datum"] != block["termine"][i - 1]["datum"]
            block["reden"] = [{**r, "vor": vor_wann(r.get("zeit"))} for r in d.fed_reden[:6]]
            if "DGS2" in d.fred and "DFEDTARU" in d.fred:
                block["charts"].append(charts.linien(
                    {"Rendite 2 J.": d.fred["DGS2"], "Leitzins (Obergrenze)": d.fred["DFEDTARU"]},
                    titel="Was der Markt von der Fed erwartet", untertitel="in %", quelle=f"{Q_FRED} (DGS2, DFEDTARU)",
                    einheit="%", start_tage=365,
                    hinweis="Liegt die 2-jährige Rendite deutlich unter dem Leitzins, erwartet der Markt Zinssenkungen."))
        elif a == "gold_btc":
            gold, btc, ndx = d.reihe("GC=F"), d.reihe("BTC-USD"), d.reihe("^NDX")
            if gold is not None and btc is not None:
                block["charts"].append(charts.linien(
                    _indexiert({"Gold": gold, "Bitcoin": btc, "Nasdaq 100": ndx}), titel="Gold, Bitcoin und Nasdaq im Vergleich",
                    untertitel="indexiert, Start vor einem Jahr = 100", quelle=f"{Q_YAHOO}; eigene Berechnung",
                    start_tage=None, knoepfe=False))
                korr = {"Gold ↔ Bitcoin": analysen.rollierende_korrelation(gold, btc)}
                if ndx is not None:
                    korr["Bitcoin ↔ Nasdaq 100"] = analysen.rollierende_korrelation(btc, ndx)
                block["charts"].append(charts.linien(
                    korr, titel="Laufen sie gemeinsam?", untertitel="Korrelation der Tagesrenditen, 30 Handelstage (−1 bis +1)",
                    quelle=f"{Q_YAHOO}; eigene Berechnung", start_tage=365, nulllinie=True, einheit="korr",
                    hinweis="Werte nahe +1: bewegen sich gleich. In Liquiditätskrisen steigt die Korrelation oft."))
            else:
                block["charts"].append(charts.fehlt("Gold und Bitcoin", "Kurse fehlen"))
            block["selloff"] = analysen.selloff_check({"Gold": gold, "Bitcoin": btc, "Nasdaq 100": ndx,
                                                       "VIX": d.reihe("^VIX"), "Dollar-Index": d.reihe("DX-Y.NYB")})
            block["charts"].append(_liquiditaet_chart(d, breit=False))
        elif a == "ki":
            block["charts"].append(charts.linien(
                _indexiert({"Nvidia": d.reihe("NVDA"), "Halbleiter (SOX)": d.reihe("^SOX"),
                            "Nasdaq 100": d.reihe("^NDX")}),
                titel="Nvidia gegen Halbleiter und Nasdaq", untertitel="indexiert, Start vor einem Jahr = 100",
                quelle=f"{Q_YAHOO}; eigene Berechnung", start_tage=None, knoepfe=False))
            nvda = next((z for z in werte if z["ticker"] == "NVDA"), None)
            if nvda:
                block["charts"].append(_kurs_chart(nvda))
            block["tabellen"]["bewertung"] = [{"ticker": t_, **info} for t_, info in d.firmen.items()
                                              if info and t_ in KI_KORB]
        elif a == "hormuz":
            h = d.hormuz
            if h is not None:
                h = h[h.index >= "2024-01-01"]
                schnitt = h["tanker"].rolling(7).mean().dropna()
                block["charts"].append(charts.balken_mit_schnitt(
                    h["tanker"], schnitt, titel="Tanker-Durchfahrten durch die Strasse von Hormuz",
                    untertitel="Anzahl Tanker pro Tag", quelle="IMF PortWatch (Satelliten-AIS-Daten)",
                    name_balken="pro Tag", name_schnitt="7-Tage-Schnitt", breit=True,
                    hinweis=f"Daten mit rund einer Woche Verzögerung, letzter Stand {h.index[-1]:%d.%m.%Y}."))
                v2025 = d.hormuz.loc["2025", "tanker"].mean() if "2025" in d.hormuz.index.year.astype(str) else None
                block["kpi"] = {"aktuell": float(schnitt.iloc[-1]), "vorjahr": float(v2025) if v2025 else None,
                                "stand": h.index[-1]}
            else:
                block["charts"].append(charts.fehlt("Hormuz-Durchfahrten", d.fehler.get("portwatch", ""), breit=True))
            brent = next((z for z in werte if z["ticker"] == "BZ=F"), None)
            if brent:
                block["charts"].append(_kurs_chart(brent))
        elif a == "cta":
            block["cta"] = _cta(d)
        ergebnis.append(block)
    return ergebnis


def _kommentar(d: Sammlung, werte: list[dict], themen: list[dict]) -> list[Markup]:
    """Automatisch erzeugte Sätze aus den Daten – kein Ersatz für eigene Einschätzung."""
    w = {z["ticker"]: z for z in werte if z["ok"]}
    saetze = []
    if "^GSPC" in w:
        z = w["^GSPC"]
        saetze.append(f"Der <b>S&P 500</b> {'stieg' if z['tag'] > 0 else 'fiel'} zuletzt um {z['tag']:+.2f}% auf "
                      f"{fmt_zahl(z['kurs'])} Punkte; seit Jahresbeginn {z['ytd']:+.1f}%.")
    if "^SSMI" in w:
        z = w["^SSMI"]
        saetze.append(f"Der <b>SMI</b> steht bei {fmt_zahl(z['kurs'])} ({z['tag']:+.2f}% am Tag, {z['ytd']:+.1f}% YTD).")
    preise = [z for z in werte if z["ok"] and z["art"] == "preis" and z["tag"] is not None and not z["veraltet"]
              and z["ticker"] != "^VIX"]
    if len(preise) > 3:
        top, flop = max(preise, key=lambda z: z["tag"]), min(preise, key=lambda z: z["tag"])
        saetze.append(f"Stärkster Wert der Watchlist: <b>{top['name']}</b> ({top['tag']:+.2f}%), "
                      f"schwächster: <b>{flop['name']}</b> ({flop['tag']:+.2f}%).")
    if "DGS10" in w:
        z = w["DGS10"]
        saetze.append(f"Die <b>10-jährige US-Rendite</b> liegt bei {z['kurs']:.2f}% "
                      f"({z['woche']:+.0f} bp in einer Woche).")
    if "^VIX" in w:
        v = w["^VIX"]["kurs"]
        stufe = "ruhig" if v < 15 else "normal" if v < 20 else "erhöht" if v < 30 else "Stress"
        saetze.append(f"Der <b>VIX</b> (Angstbarometer) steht bei {v:.1f} – Einordnung: {stufe}.")
    cta = _cta(d)
    if cta:
        richtung = "long" if cta["aktuell"] > 0 else "short"
        trend = ""
        if cta["vor_woche"] is not None:
            trend = " (Tendenz steigend)" if cta["aktuell"] > cta["vor_woche"] + 5 else \
                " (Tendenz fallend)" if cta["aktuell"] < cta["vor_woche"] - 5 else " (stabil)"
        saetze.append(f"Unser <b>CTA-Modell</b> schätzt Trendfolger im S&P 500 bei {cta['aktuell']:+.0f}% ({richtung}){trend}.")
    for t in themen:
        if t.get("selloff"):
            saetze.append(f"<b>Liquiditäts-Check</b> (5 Tage): {t['selloff']['urteil']} "
                          f"({t['selloff']['treffer']} von {t['selloff']['von']} Kriterien).")
        if t.get("kpi"):
            k = t["kpi"]
            vj = f" – im Jahr 2025 waren es im Schnitt {k['vorjahr']:.0f}" if k["vorjahr"] else ""
            saetze.append(f"<b>Hormuz:</b> im Schnitt {k['aktuell']:.1f} Tanker pro Tag (7 Tage bis {k['stand']:%d.%m.}){vj}.")
    return [Markup(s) for s in saetze]


# ===========================================================================
# Website schreiben
# ===========================================================================
def baue_website(watchlist: dict, themen: list[dict], melde=print):
    d = Sammlung(watchlist, themen, melde)
    d.lade_alles()
    melde("  Rechne Analysen und baue Seiten ...")

    werte = _alle_werte(d)
    themen_bloecke = seite_themen(d, werte)
    jetzt = datetime.now()
    alle_news = [{**a, "thema": t["titel"], "thema_id": t["id"]} for t in themen_bloecke for a in t["news"]]
    alle_news += [{**r, "vor": vor_wann(r.get("zeit")), "thema": "Fed-Reden", "thema_id": "fedreden"}
                  for r in d.fed_reden[:10]]
    alle_news.sort(key=lambda a: a.get("zeit") or "", reverse=True)

    melde("  Anthropic & IPOs (Prospekt, Vergleichsfirmen, Optionen, IPO-Kalender) ...")
    vix = d.reihe("^VIX")
    cta = _cta(d)
    marktlage = {"selloff": next((t["selloff"]["stufe"] for t in themen_bloecke if t.get("selloff")), None),
                 "vix": float(vix.iloc[-1]) if vix is not None else None, "cta": cta["aktuell"] if cta else None}
    try:
        anthropic_ctx = anthropic_seite.baue(d, marktlage)
    except Exception as e:
        anthropic_ctx = {"fehler_seite": f"{type(e).__name__}: {e}"}
        d.fehler["anthropic_seite"] = anthropic_ctx["fehler_seite"]
    alle_news += [{**a, "thema": "Anthropic", "thema_id": "anthropic"} for a in anthropic_ctx.get("news", [])[:15]]
    alle_news.sort(key=lambda a: a.get("zeit") or "", reverse=True)

    preise = [z for z in werte if z["ok"] and z["art"] == "preis" and z["tag"] is not None and not z["veraltet"]
              and z["ticker"] != "^VIX"]  # VIX ist ein Risikobarometer, kein Anlagewert
    beweger = sorted(preise, key=lambda z: z["tag"])
    status = cache.PROTOKOLL

    seiten = list(SEITEN)
    vergleich_ctx = {}
    if vergleich_seite.konfig():
        melde("  Aktienvergleich (vergleich.yaml) ...")
        try:
            vergleich_ctx = vergleich_seite.baue(d)
        except Exception as e:
            d.fehler["vergleich_seite"] = f"{type(e).__name__}: {e}"
        if vergleich_ctx.get("rangliste"):
            seiten.insert([s_[0] for s_ in seiten].index("anthropic") + 1, ("vergleich", "Aktienvergleich"))
    elif (WEBSITE_ORDNER / "vergleich.html").exists():
        (WEBSITE_ORDNER / "vergleich.html").unlink()  # abgelaufene Vergleichsseite entfernen

    gemeinsam = {
        "seiten": seiten, "datum_lang": datum_lang(jetzt), "erstellt": jetzt.strftime("%d.%m.%Y, %H:%M"),
        "band": [z for z in werte if z.get("band")],
        "plotly_version": plotly.offline.get_plotlyjs_version(),
        "anzahl_fehler": sum(1 for p in status if p["status"] == "fehler"),
    }
    inhalte = {
        "index": {"kommentar": _kommentar(d, werte, themen_bloecke),
                  "gewinner": beweger[::-1][:5], "verlierer": beweger[:5],
                  "cockpit": [{**z, "mini_gross": charts.mini(z["serie"], charts.FARBEN[0], b=150, h=40),
                               "anker": anker(z["ticker"]), "gruppe_id": anker(z["gruppe"])}
                              for z in werte if z.get("band") and z["ok"]],
                  "news": alle_news[:12], "termine": _termine(d, 7),
                  "top_bewegungen": (getattr(d, "kern", {}) or {}).get("top_bewegungen")},
        "maerkte": seite_maerkte(d, werte),
        "makro": seite_makro(d),
        "positionierung": seite_positionierung(d),
        "themen": {"themen": themen_bloecke},
        "anthropic": anthropic_ctx,
        "vergleich": vergleich_ctx,
        "termine": {"termine": _termine(d, 21), "fred_key": bool(os.getenv("FRED_API_KEY"))},
        "news": {"news": alle_news, "themen_liste": [(t["id"], t["titel"]) for t in themen_bloecke]
                 + [("anthropic", "Anthropic"), ("fedreden", "Fed-Reden")]},
        "status": {"protokoll": status, "fehler": d.fehler, "quellen": (getattr(d, "kern", {}) or {}).get("status", []),
                   "zaehler": {s: sum(1 for p in status if p["status"] == s) for s in ("ok", "cache", "alt", "fehler")}},
    }

    umgebung = Environment(loader=FileSystemLoader(VORLAGEN_ORDNER), autoescape=select_autoescape(["html"]))
    umgebung.filters.update(anker=anker, kurs=fmt_kurs, zahl=fmt_zahl, veraenderung=fmt_veraenderung, klasse=css_klasse, mrd=fmt_mrd,
                            datum=lambda x: x.strftime("%d.%m.%Y") if x else "–")
    WEBSITE_ORDNER.mkdir(exist_ok=True)
    if getattr(d, "kern", None):
        from kern.sammeln import schreibe_pakete
        pakete = schreibe_pakete(d.kern, WEBSITE_ORDNER / "pakete")
        melde(f"  Verschlüsselte Datenpakete: {len(pakete)}" if pakete else
              "  Datenpakete übersprungen (kein SITE_PASSWORT – wird nie unverschlüsselt veröffentlicht)")
    (WEBSITE_ORDNER / "assets").mkdir(exist_ok=True)
    for datei in ("stil.css", "app.js"):
        shutil.copy(VORLAGEN_ORDNER / datei, WEBSITE_ORDNER / "assets" / datei)
    for seite, titel in seiten:
        html = umgebung.get_template(f"{seite}.html").render(aktiv=seite, titel=titel, **gemeinsam, **inhalte[seite])
        (WEBSITE_ORDNER / f"{seite}.html").write_text(html, encoding="utf-8")

    return WEBSITE_ORDNER / "index.html"
