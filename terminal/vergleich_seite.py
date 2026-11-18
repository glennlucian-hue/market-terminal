"""Temporäre Seite "Aktienvergleich" (Einstellungen in vergleich.yaml).

Die Punktebewertung ist bewusst einfach und offen gelegt: Für jede Kennzahl bekommt die beste Aktie
3 Punkte, die zweitbeste 2, die schwächste 1. Je Kategorie wird der Durchschnitt gebildet,
alle Kategorien zählen gleich viel. Das ist ein Vergleichswerkzeug, keine Anlageempfehlung.
"""
import math
from datetime import date

import pandas as pd
import yaml

from . import charts, risiko, technik
from .konfiguration import PROJEKT
from .quellen import cboe, nasdaq, news, yahoo

Q_Y, Q_N = "Yahoo Finance", "Nasdaq (Analysten-Konsens)"
FARBEN = charts.FARBEN[:3]


def konfig() -> dict | None:
    pfad = PROJEKT / "vergleich.yaml"
    if not pfad.exists():
        return None
    cfg = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    return cfg if date.today() <= date.fromisoformat(str(cfg.get("anzeigen_bis", "2000-01-01"))) else None


def _rang_punkte(werte: list, hoeher_besser: bool) -> list:
    """3 / 2 / 1 Punkte nach Rang; fehlende Werte bekommen keine Punkte (None)."""
    gueltig = [(i, w) for i, w in enumerate(werte) if w is not None and not (isinstance(w, float) and math.isnan(w))]
    punkte = [None] * len(werte)
    sortiert = sorted(gueltig, key=lambda x: x[1], reverse=hoeher_besser)
    n = len(werte)
    for rang, (i, w) in enumerate(sortiert):
        gleich = [r for r, (_, w2) in enumerate(sortiert) if w2 == w]   # Gleichstand: Punkte teilen
        punkte[i] = sum(n - r for r in gleich) / len(gleich)
    return punkte


def baue(d) -> dict:
    cfg = konfig()
    if not cfg:
        return {}
    zins = float(d.fred["DGS3MO"].iloc[-1]) / 100 if "DGS3MO" in d.fred else 0.04
    markt = d.reihe(cfg["markt"])
    try:
        eem, _ = yahoo.kurse(cfg["schwellenlaender_etf"])
    except Exception:
        eem = None
    usdchf = d.reihe("CHF=X")
    usdchf = float(usdchf.iloc[-1]) if usdchf is not None else None

    firmen = []
    for w in cfg["werte"]:
        t = w["ticker"]
        f = {**w, "ok": False}
        try:
            kurs, meta = yahoo.kurse(t)
            ohlc = yahoo.ohlc(t)
        except Exception as e:
            d.fehler[f"vergleich_{t}"] = str(e)
            firmen.append(f)
            continue
        f.update(ok=True, kurs=kurs, preis=float(kurs.iloc[-1]), waehrung=meta.get("waehrung", "USD"))
        f["technik"] = technik.auswertung(ohlc)
        f["risiko"] = risiko.kennzahlen(kurs, markt, zins)
        f["risiko_em"] = risiko.kennzahlen(kurs, eem, zins) if eem is not None else None
        # Veränderungen
        def seit(tage):
            alt = kurs[kurs.index <= kurs.index[-1] - pd.Timedelta(days=tage)]
            return (f["preis"] / float(alt.iloc[-1]) - 1) * 100 if len(alt) else None
        ytd = kurs[kurs.index < pd.Timestamp(year=kurs.index[-1].year, month=1, day=1)]
        f.update(m1=seit(30), m3=seit(91), j1=seit(365), j3=seit(365 * 3),
                 ytd=(f["preis"] / float(ytd.iloc[-1]) - 1) * 100 if len(ytd) else None)
        # Fundamentaldaten und Analysten
        try:
            f["fund"] = yahoo.fundamentaldaten(t)
        except Exception as e:
            f["fund"], d.fehler[f"fund_{t}"] = {}, str(e)
        try:
            a = nasdaq.analysten(t)
        except Exception as e:
            a, d.fehler[f"analysten_{t}"] = {"jahre": []}, str(e)
        f["analysten"] = a
        j = a.get("jahre", [])
        f["kgv"] = [{"jahr": x["jahr"], "kgv": f["preis"] / x["eps"] if x["eps"] else None, "eps": x["eps"],
                     "anzahl": x["anzahl"]} for x in j]
        f["eps_wachstum"] = ((j[1]["eps"] / j[0]["eps"] - 1) * 100) if len(j) > 1 and j[0]["eps"] else None
        f["eps_wachstum2"] = ((j[2]["eps"] / j[1]["eps"] - 1) * 100) if len(j) > 2 and j[1]["eps"] else None
        kgv2 = f["kgv"][1]["kgv"] if len(f["kgv"]) > 1 else None
        f["peg"] = kgv2 / f["eps_wachstum"] if kgv2 and f["eps_wachstum"] and f["eps_wachstum"] > 0 else None
        f["kursziel"] = a.get("kursziel")
        f["potenzial"] = (a["kursziel"] / f["preis"] - 1) * 100 if a.get("kursziel") else None
        f["dividende"] = a.get("dividendenrendite") or 0.0
        f["boersenwert"] = a.get("boersenwert") or f["fund"].get("marketCap")
        om = f["fund"].get("operatingMargins")
        f["fund"]["operatingMargins"] = om if om not in (0, 0.0) else None   # 0.0 = fehlende Angabe (z. B. Bank-Bilanz)
        # Gamma
        try:
            o, s = cboe.optionskette(t)
            f["gamma"] = risiko.gamma_exposure(o, s)
        except Exception as e:
            f["gamma"], d.fehler[f"gamma_{t}"] = {}, str(e)
        # Stückzahl für den geplanten Betrag
        if usdchf and f["waehrung"] == "USD":
            preis_chf = f["preis"] * usdchf
            f["preis_chf"] = preis_chf
            f["stueck"] = [int(b // preis_chf) for b in cfg["betrag_chf"]]
        firmen.append(f)

    ok = [f for f in firmen if f["ok"]]
    for f, farbe in zip(ok, FARBEN):
        f["farbe"] = farbe
    ctx = {"cfg": cfg, "firmen": firmen, "zins": zins * 100, "usdchf": usdchf}
    if not ok:
        return ctx

    # --- Charts ------------------------------------------------------------------------
    def indexiert(tage):
        serien = {}
        for f in ok:
            k = f["kurs"][f["kurs"].index >= f["kurs"].index[-1] - pd.Timedelta(days=tage)]
            serien[f["name"]] = k / k.iloc[0] * 100
        return serien
    ctx["chart_3m"] = charts.linien(indexiert(92), titel="Kursentwicklung 3 Monate", untertitel="indexiert, Start = 100",
                                   quelle=Q_Y, start_tage=None, knoepfe=False, nulllinie=False, hoehe=290)
    ctx["chart_1j"] = charts.linien(indexiert(365), titel="Kursentwicklung 1 Jahr", untertitel="indexiert, Start = 100",
                                   quelle=Q_Y, start_tage=None, knoepfe=False, hoehe=290)
    ctx["chart_3j"] = charts.linien(indexiert(365 * 3), titel="Kursentwicklung 3 Jahre", untertitel="indexiert, Start = 100",
                                   quelle=Q_Y, start_tage=None, knoepfe=False, hoehe=290, breit=True)
    for f, farbe in zip(ok, FARBEN):
        tk = f["technik"]
        jahr = f["kurs"][f["kurs"].index >= f["kurs"].index[-1] - pd.Timedelta(days=740)]
        p = tk["pivots"]
        f["chart_technik"] = charts.linien(
            {f"{f['name']}": jahr, "50-Tage-Linie": tk["sma50_reihe"], "200-Tage-Linie": tk["sma200_reihe"]},
            titel=f"{f['name']} ({f['ticker']}): Kurs, Trendlinien und Pivot-Punkte",
            untertitel=f"in {f['waehrung']} · Pivot-Punkte aus dem Vormonat ({p['basis']:%m/%Y})",
            quelle=f"{Q_Y}; eigene Berechnung", start_tage=183, hoehe=320,
            farben=[farbe, "#9a9a9a", "#5a5a5a"],
            marken=[(p["R2"], "R2"), (p["R1"], "R1"), (p["P"], "Pivot"), (p["S1"], "S1"), (p["S2"], "S2")])
    namen = [f["name"] for f in ok]
    ctx["chart_kgv"] = charts.balken(
        namen, [f["kgv"][1]["kgv"] if len(f["kgv"]) > 1 else None for f in ok],
        titel="Erwartetes KGV (Kurs / Gewinn je Aktie 2027)", untertitel="tiefer = günstiger bewertet",
        quelle=f"{Q_N}; {Q_Y}; eigene Berechnung", farben=FARBEN,
        beschriftung=[f"{f['kgv'][1]['kgv']:.1f}x" if len(f["kgv"]) > 1 and f["kgv"][1]["kgv"] else "–" for f in ok])
    ctx["chart_wachstum"] = charts.balken(
        namen, [f["eps_wachstum"] for f in ok], titel="Erwartetes Gewinnwachstum je Aktie 2026 → 2027",
        untertitel="in %, Analysten-Konsens", quelle=Q_N, farben=FARBEN,
        beschriftung=[f"{f['eps_wachstum']:+.0f}%" if f["eps_wachstum"] is not None else "–" for f in ok])

    # --- Punktebewertung ----------------------------------------------------------------
    def wert(f, pfad):
        x = f
        for teil in pfad:
            x = x.get(teil) if isinstance(x, dict) else None
            if x is None:
                return None
        return x
    kriterien = {
        "Bewertung": [("Erwartetes KGV 2027", lambda f: f["kgv"][1]["kgv"] if len(f["kgv"]) > 1 else None, False, "x"),
                      ("PEG (KGV / Gewinnwachstum)", lambda f: f["peg"], False, "x"),
                      ("Dividendenrendite", lambda f: f["dividende"], True, "pct")],
        "Wachstum": [("Gewinnwachstum 2026→27 (erwartet)", lambda f: f["eps_wachstum"], True, "pct+"),
                     ("Umsatzwachstum (letztes Quartal, J/J)", lambda f: wert(f, ["fund", "revenueGrowth"]), True, "anteil")],
        "Qualität": [("Eigenkapitalrendite (ROE)", lambda f: wert(f, ["fund", "returnOnEquity"]), True, "anteil"),
                     ("Nettomarge", lambda f: wert(f, ["fund", "profitMargins"]), True, "anteil")],
        "Risiko": [("Sharpe Ratio (1 J.)", lambda f: wert(f, ["risiko", "sharpe"]), True, "x"),
                   ("Volatilität (tiefer = besser)", lambda f: wert(f, ["risiko", "vola"]), False, "pct"),
                   ("Max Drawdown (1 J.)", lambda f: wert(f, ["risiko", "max_dd"]), True, "pct")],
        "Chart-Technik": [("Trendpunkte (0–4)", lambda f: f["technik"]["trendpunkte"], True, "ganz"),
                          ("Abstand zur 200-Tage-Linie", lambda f: f["technik"]["abstand200"], True, "pct+")],
        "Analysten": [("Potenzial bis Kursziel", lambda f: f["potenzial"], True, "pct+")],
    }
    tabelle, summe = [], [0.0] * len(ok)
    for kat, liste in kriterien.items():
        kat_punkte = [[] for _ in ok]
        zeilen = []
        for name, fn, hoeher, fmt in liste:
            werte = [fn(f) for f in ok]
            pkt = _rang_punkte(werte, hoeher)
            for i, p in enumerate(pkt):
                if p is not None:
                    kat_punkte[i].append(p)
            text = [("–" if w is None else f"{w:.2f}" if fmt == "x" else f"{w:.1f}%" if fmt == "pct"
                     else f"{w:+.1f}%" if fmt == "pct+" else f"{w * 100:.1f}%" if fmt == "anteil" else f"{w:.0f}")
                    for w in werte]
            zeilen.append({"name": name, "werte": werte, "text": text, "punkte": pkt})
        mittel = [sum(p) / len(p) if p else 0 for p in kat_punkte]
        summe = [a + b for a, b in zip(summe, mittel)]
        tabelle.append({"kategorie": kat, "zeilen": zeilen, "mittel": mittel})
    ctx["punkte"] = tabelle
    rangliste = sorted(zip(ok, summe), key=lambda x: -x[1])
    ctx["rangliste"] = [{"firma": f, "punkte": p} for f, p in rangliste]
    ctx["max_punkte"] = 3 * len(kriterien)
    for f, gesamt in zip(ok, summe):
        f["gesamt"] = gesamt
        staerken = [t["kategorie"] for t in tabelle if t["mittel"][ok.index(f)] >= 2.5]
        schwaechen = [t["kategorie"] for t in tabelle if t["mittel"][ok.index(f)] <= 1.5]
        f["staerken"], f["schwaechen"] = staerken, schwaechen
        g = f.get("gamma") or {}
        if g.get("flip"):
            f["gamma_text"] = ("unter dem Gamma-Flip – Options-Händler verstärken eher Bewegungen"
                               if f["preis"] < g["flip"] else "über dem Gamma-Flip – Options-Händler dämpfen eher Bewegungen")

    # --- News ----------------------------------------------------------------------------
    from .website import _sortiere_news
    for f in ok:
        try:
            f["news"] = _sortiere_news(news.google_news(f["suchbegriff"], 7), 6)
        except Exception:
            f["news"] = []
    return ctx
