"""Seite "Anthropic & IPOs": Börsengang, Fundamentaldaten, Bewertung, Szenarien, Risiko, Gamma, IPO-Kalender.

Grundlage der Fundamentaldaten: anthropic.yaml (aus dem SEC-Prospekt).
Die Szenarien sind ein einfaches, offen gelegtes Modell – keine Prognose und keine Anlageberatung:
    Kursziel in 12 Monaten = Run-Rate-Umsatz heute x (1 + Wachstum je Quartal)^4 x Umsatz-Multiplikator / Aktien
"""
from datetime import date, timedelta
from statistics import median

import numpy as np
import pandas as pd
import yaml
from markupsafe import Markup

from . import analysen, charts, risiko
from .konfiguration import PROJEKT
from .quellen import cboe, ipo, news, sec, yahoo

Q_PROSPEKT = "Anthropic, Form S-1/A vom 17.11.2026 (SEC)"
FARBE_SZENARIO = {"bull": charts.FARBEN[4], "neutral": charts.FARBEN[0], "bear": charts.FARBEN[2]}  # grün / bernstein / magenta


def lade_konfig() -> dict:
    return yaml.safe_load((PROJEKT / "anthropic.yaml").read_text(encoding="utf-8"))


def _mrd(x: float) -> str:
    return f"{x:,.1f}".replace(",", "’")


def _status(cfg: dict, kal: dict | None) -> dict:
    """Wo steht der Börsengang? Nasdaq-Kalender hat Vorrang vor der Datei, wenn aktueller."""
    i = cfg["ipo"]
    st = {"spanne": list(i["preisspanne"]), "preis": i.get("ausgabepreis"), "datum": i["preisfestsetzung"],
          "phase": "angekündigt"}
    if kal:
        for z in kal["bewertet"]:
            if z["ticker"] == cfg["firma"]["ticker"]:
                st.update(phase="Preis festgesetzt", preis=st["preis"] or float(z["preis"]))
        for z in kal["kommend"]:
            if z["ticker"] == cfg["firma"]["ticker"] and "-" in z["preis"]:
                tief, hoch = (float(v) for v in z["preis"].split("-"))
                st.update(spanne=[tief, hoch], phase="Zeichnungsfrist")
    return st


def _vergleichsfirmen(cfg: dict, d) -> list[dict]:
    zeilen = []
    for ticker, cik in cfg["vergleich_bewertung"].items():
        try:
            f = sec.umsatz_und_aktien(ticker, cik)
        except Exception as e:
            d.fehler[f"sec_{ticker}"] = str(e)
            continue
        kurs = d.reihe(ticker)
        if kurs is None:
            try:
                kurs, _ = yahoo.kurse(ticker)
            except Exception:
                continue
        mcap = float(kurs.iloc[-1]) * f["aktien"]
        zeilen.append({"ticker": ticker, "firma": f["firma"], "boersenwert": mcap, "umsatz": f["umsatz_ttm"],
                       "ps": mcap / f["umsatz_ttm"], "wachstum": f["wachstum"], "kurs": kurs})
    return sorted(zeilen, key=lambda z: -z["ps"])


def _wahrscheinlichkeiten(cfg: dict, marktlage: dict) -> tuple[dict, list[str]]:
    """Grundgewichte aus anthropic.yaml, angepasst an die aktuelle Marktlage (feste Regeln)."""
    p = dict(cfg["szenarien"]["wahrscheinlichkeiten"])
    regeln = []
    if marktlage.get("selloff") == "hoch":
        p["bull"] -= 10; p["bear"] += 10
        regeln.append("Liquiditäts-Check zeigt Selloff-Muster → Bull −10, Bear +10 Prozentpunkte")
    elif marktlage.get("selloff") == "mittel":
        p["bull"] -= 5; p["bear"] += 5
        regeln.append("Anzeichen von Liquiditätsstress → Bull −5, Bear +5")
    vix = marktlage.get("vix")
    if vix is not None and vix > 25:
        p["bull"] -= 5; p["bear"] += 5
        regeln.append(f"VIX {vix:.1f} über 25 → Bull −5, Bear +5")
    elif vix is not None and vix < 15:
        p["bull"] += 5; p["bear"] -= 5
        regeln.append(f"VIX {vix:.1f} unter 15 → Bull +5, Bear −5")
    cta = marktlage.get("cta")
    if cta is not None and cta < -25:
        p["neutral"] -= 5; p["bear"] += 5
        regeln.append(f"CTA-Modell {cta:+.0f}% (Trendfolger short) → Neutral −5, Bear +5")
    elif cta is not None and cta > 50:
        p["neutral"] -= 5; p["bull"] += 5
        regeln.append(f"CTA-Modell {cta:+.0f}% (Trendfolger stark long) → Neutral −5, Bull +5")
    p = {k: max(5, v) for k, v in p.items()}
    summe = sum(p.values())
    p = {k: v * 100 / summe for k, v in p.items()}
    if not regeln:
        regeln.append("Marktlage neutral → Grundgewichte unverändert")
    return p, regeln


def baue(d, marktlage: dict) -> dict:
    cfg = lade_konfig()
    ctx = {"cfg": cfg}
    aktien = cfg["ipo"]["aktien_nach_ipo"]
    k = cfg["kennzahlen"]

    # --- IPO-Kalender und Status -------------------------------------------------
    try:
        kal = ipo.kalender()
    except Exception as e:
        kal, d.fehler["ipo_kalender"] = None, str(e)
    ctx["kalender"] = kal
    st = _status(cfg, kal)
    ctx["status"] = st

    # --- Kurs, falls schon gehandelt ---------------------------------------------
    ant = None
    if date.today() >= date.fromisoformat(cfg["ipo"]["erster_handelstag"]):
        try:
            ant, _ = yahoo.kurse(cfg["firma"]["ticker"], 1)
        except Exception as e:
            d.fehler["ANT"] = f"Noch keine Kurse für ANT: {e}"
    ctx["ant_kurs"] = float(ant.iloc[-1]) if ant is not None else None
    mitte = sum(st["spanne"]) / 2
    basis = ctx["ant_kurs"] or st["preis"] or mitte
    ctx["basis"] = basis
    ctx["basis_text"] = ("aktueller Börsenkurs" if ctx["ant_kurs"] else "Ausgabepreis" if st["preis"]
                         else "Mitte der Preisspanne")

    # --- Fundamentaldaten ----------------------------------------------------------
    q = cfg["quartale"]
    umsatz_ttm = sum(x["umsatz"] for x in q[-4:]) / 1000
    ctx["fund"] = {
        "umsatz_ttm": umsatz_ttm, "q_letzt": q[-1]["umsatz"] / 1000,
        "q_qoq": (q[-1]["umsatz"] / q[-2]["umsatz"] - 1) * 100, "q_yoy": (q[-1]["umsatz"] / q[-5]["umsatz"] - 1) * 100,
        "be_letzt": q[-1]["betriebsergebnis"] / 1000, "run_rate": k["run_rate_mrd"],
        "rr_monat": (k["run_rate_mrd"] / k["run_rate_vormonat_mrd"] - 1) * 100,
        "anteil_amazon_google": (k["aktien_amazon"] + k["aktien_google"]) / aktien * 100,
    }
    namen = [x["quartal"] for x in q]
    ctx["chart_umsatz"] = charts.balken(
        namen, [x["umsatz"] / 1000 for x in q], titel="Umsatz pro Quartal", untertitel="in Mrd. USD",
        quelle=Q_PROSPEKT, beschriftung=[f"{x['umsatz'] / 1000:.1f}" for x in q],
        hinweis=f"Letztes Quartal +{ctx['fund']['q_qoq']:.0f}% zum Vorquartal, +{ctx['fund']['q_yoy']:,.0f}% zum Vorjahr.".replace(",", "’"))
    ctx["chart_ergebnis"] = charts.balken(
        namen, [x["betriebsergebnis"] / 1000 for x in q], titel="Betriebsergebnis pro Quartal",
        untertitel="in Mrd. USD (negativ = Verlust)", quelle=Q_PROSPEKT,
        farben=[charts.FARBEN[4] if x["betriebsergebnis"] >= 0 else charts.FARBEN[2] for x in q],
        beschriftung=[f"{x['betriebsergebnis'] / 1000:+.1f}" for x in q],
        hinweis="Q2 2026 erstmals operativ in der Gewinnzone, Q3 wieder knapp negativ.")
    ctx["chart_kosten"] = charts.balken(
        namen, [x["rechenzentren"] / x["umsatz"] * 100 for x in q], titel="Rechenzentrumskosten im Verhältnis zum Umsatz",
        untertitel="Kosten für Rechenleistung und Infrastruktur in % des Umsatzes", quelle=Q_PROSPEKT,
        beschriftung=[f"{x['rechenzentren'] / x['umsatz'] * 100:.0f}%" for x in q],
        hinweis="Sinkt der Wert, wird jeder Umsatzdollar mit weniger Rechenkosten erzielt (Skaleneffekte).")

    # --- Bewertung -----------------------------------------------------------------
    ctx["bewertung"] = [{"preis": p, "text": t, "boersenwert": p * aktien / 1e9,
                         "ps_ttm": p * aktien / 1e9 / umsatz_ttm, "ps_rr": p * aktien / 1e9 / k["run_rate_mrd"]}
                        for p, t in ((st["spanne"][0], "unteres Ende"), (mitte, "Mitte"), (st["spanne"][1], "oberes Ende"))]
    if st["preis"]:
        ctx["bewertung"].append({"preis": st["preis"], "text": "Ausgabepreis", "boersenwert": st["preis"] * aktien / 1e9,
                                 "ps_ttm": st["preis"] * aktien / 1e9 / umsatz_ttm,
                                 "ps_rr": st["preis"] * aktien / 1e9 / k["run_rate_mrd"]})
    if ctx["ant_kurs"]:
        ctx["bewertung"].append({"preis": ctx["ant_kurs"], "text": "Börsenkurs heute",
                                 "boersenwert": ctx["ant_kurs"] * aktien / 1e9,
                                 "ps_ttm": ctx["ant_kurs"] * aktien / 1e9 / umsatz_ttm,
                                 "ps_rr": ctx["ant_kurs"] * aktien / 1e9 / k["run_rate_mrd"]})

    peers = _vergleichsfirmen(cfg, d)
    ctx["peers"] = peers
    ps_werte = [p["ps"] for p in peers]
    ant_ps = basis * aktien / 1e9 / k["run_rate_mrd"]
    if peers:
        kat = [p["ticker"] for p in peers] + ["ANT (Run-Rate)"]
        werte = [p["ps"] for p in peers] + [ant_ps]
        ctx["chart_peers"] = charts.balken(
            kat, werte, horizontal=True, titel="Bewertung im Vergleich: Börsenwert / Umsatz",
            untertitel=f"Vergleichsfirmen: Umsatz der letzten 12 Monate · Anthropic: Run-Rate, Preis {basis:.2f} USD ({ctx['basis_text']})",
            quelle="SEC-Finanzberichte (Umsatz, Aktien), Yahoo Finance (Kurse); eigene Berechnung",
            farben=[charts.FARBEN[1]] * len(peers) + [charts.FARBEN[0]],
            beschriftung=[f"{w:.1f}x" for w in werte], hoehe=320)

    # --- Szenarien -----------------------------------------------------------------
    sz = cfg["szenarien"]
    p, regeln = _wahrscheinlichkeiten(cfg, marktlage)
    szenarien = []
    for name in ("bear", "neutral", "bull"):
        s = sz[name]
        if s["multiplikator"] == "auto" and len(ps_werte) >= 4:
            mult, mult_text = float(np.percentile(ps_werte, s["perzentil"])), f"{s['perzentil']}. Perzentil der Vergleichsfirmen"
        elif isinstance(s["multiplikator"], (int, float)):
            mult, mult_text = float(s["multiplikator"]), "fest in anthropic.yaml"
        else:
            mult, mult_text = float(s["ersatz_multiplikator"]), "Ersatzwert (Vergleichsdaten fehlen)"
        rr12 = k["run_rate_mrd"] * (1 + s["wachstum_pro_quartal"]) ** 4
        wert = rr12 * mult
        ziel = wert * 1e9 / aktien
        szenarien.append({"id": name, "titel": s["titel"], "wachstum_q": s["wachstum_pro_quartal"] * 100,
                          "run_rate_12m": rr12, "multiplikator": mult, "mult_text": mult_text, "wert_mrd": wert,
                          "ziel": ziel, "potenzial": (ziel / basis - 1) * 100, "p": p[name],
                          "begruendung": s["begruendung"], "farbe": FARBE_SZENARIO[name]})
    erwartung = sum(s["ziel"] * s["p"] / 100 for s in szenarien)
    ctx["szenarien"], ctx["regeln"] = szenarien, regeln
    ctx["erwartung"] = {"ziel": erwartung, "potenzial": (erwartung / basis - 1) * 100}

    start = max(date.today(), date.fromisoformat(cfg["ipo"]["erster_handelstag"]))
    ende = start + timedelta(days=365)
    pfade = {f"{s['titel']} ({s['p']:.0f}%)": ([start.isoformat(), ende.isoformat()], [basis, s["ziel"]])
             for s in reversed(szenarien)}
    farben = [s["farbe"] for s in reversed(szenarien)]
    if ant is not None and len(ant) > 1:
        pfade["Kurs ANT"] = (ant.index.strftime("%Y-%m-%d").tolist(), ant.values.tolist())
        farben.append(charts.FARBEN[1])
    ctx["chart_szenarien"] = charts.linien_xy(
        pfade, titel="Anthropic: Szenarien für die nächsten 12 Monate",
        untertitel=f"Kursziel je Aktie in USD · Start: {basis:.2f} USD ({ctx['basis_text']})",
        quelle=f"Eigenes Modell auf Basis {Q_PROSPEKT} und Vergleichsfirmen (SEC, Yahoo)", einheit="",
        farben=farben, gestrichelt={k for k in pfade if k != "Kurs ANT"}, band=tuple(st["spanne"]),
        band_text=f"IPO-Preisspanne {st['spanne'][0]:.0f}–{st['spanne'][1]:.0f} USD", breit=True, hoehe=360,
        hinweis="Gestrichelt: Modellpfade (gerade Linie vom Start zum Kursziel). Echte Kurse schwanken deutlich stärker.")

    # --- Risiko-Kennzahlen -----------------------------------------------------------
    markt = d.reihe("^GSPC")
    zins = float(d.fred["DGS3MO"].iloc[-1]) / 100 if "DGS3MO" in d.fred else 0.04
    ctx["zins"] = zins * 100
    zeilen = []
    if ant is not None:
        zeilen.append({"name": "Anthropic", "ticker": "ANT", "gruppe": "Anthropic", "k": risiko.kennzahlen(ant, markt, zins)})
    for pz in peers:
        zeilen.append({"name": pz["firma"].title()[:26], "ticker": pz["ticker"], "gruppe": "KI-Vergleich",
                       "k": risiko.kennzahlen(pz["kurs"], markt, zins)})
    ipo_reihen = {}
    for ticker, name in cfg["vergleich_ipos"].items():
        try:
            s, _ = yahoo.kurse(ticker)
        except Exception as e:
            d.fehler[f"ipo_{ticker}"] = str(e)
            continue
        ipo_reihen[name] = s
        zeilen.append({"name": name, "ticker": ticker, "gruppe": "Frühere IPOs", "k": risiko.kennzahlen(s, markt, zins)})
    if markt is not None:
        zeilen.append({"name": "S&P 500", "ticker": "^GSPC", "gruppe": "Markt", "k": risiko.kennzahlen(markt, markt, zins)})
    ctx["risiko"] = [z for z in zeilen if z["k"]]
    betas = [z["k"]["beta"] for z in ctx["risiko"] if z["gruppe"] in ("KI-Vergleich", "Frühere IPOs") and z["k"]["beta"]]
    vols = [z["k"]["vola"] for z in ctx["risiko"] if z["gruppe"] in ("KI-Vergleich", "Frühere IPOs")]
    ctx["proxy"] = {"beta": median(betas) if betas else None, "vola": median(vols) if vols else None}

    # --- Gamma (Optionen) -------------------------------------------------------------
    # Optionen auf ANT gibt es frühestens ab dem ersten Handelstag – vorher Nvidia als Beispiel
    gamma_ticker = cfg["firma"]["ticker"] if ant is not None else "NVDA"
    try:
        o, s = cboe.optionskette(gamma_ticker)
    except Exception:
        gamma_ticker = "NVDA"
        try:
            o, s = cboe.optionskette(gamma_ticker)
        except Exception as e:
            o, d.fehler["cboe"] = None, str(e)
    ctx["gamma_ticker"] = gamma_ticker
    if o is not None:
        g = risiko.gamma_exposure(o, s)
        ctx["gamma"] = g
        if g:
            js = g["je_strike"]
            ctx["chart_gamma"] = charts.balken(
                [f"{x:g}" for x in js.index], [v / 1e6 for v in js.values],
                titel=f"{gamma_ticker}: Gamma-Exposure der Options-Händler nach Ausübungspreis",
                untertitel=f"Mio. USD je 1 % Kursbewegung · Optionen mit Verfall in ≤ {g['max_tage']} Tagen · Kurs {s:.2f} USD",
                quelle="Cboe (verzögerte Optionsdaten); eigene Berechnung", breit=True, hoehe=320,
                farben=[charts.FARBEN[1] if v >= 0 else charts.FARBEN[2] for v in js.values],
                beschriftung=["" for _ in js.values],
                linie_bei=list(js.index).index(min(js.index, key=lambda x: abs(x - s))),  # Position des nächsten Strikes
                linie_text=f"Kurs {s:.2f}",
                hinweis="Blau: Händler bremsen Bewegungen (kaufen bei Rückgang, verkaufen bei Anstieg). "
                        "Magenta: Händler verstärken Bewegungen.")

    # --- IPO-Vergleich -----------------------------------------------------------------
    verlauf = {name: risiko.ipo_verlauf(s) for name, s in ipo_reihen.items()}
    if verlauf:
        tabelle = []
        for name, v in verlauf.items():
            def nach(n): return (float(v.iloc[n]) - 100) if len(v) > n else None
            tabelle.append({"name": name, "t5": nach(5), "t20": nach(20), "t60": nach(60), "t120": nach(120),
                            "tief": float(v.min() - 100), "heute": (float(ipo_reihen[name].iloc[-1]) /
                                                                     float(ipo_reihen[name].iloc[0]) - 1) * 100})
        ctx["ipo_tabelle"] = tabelle
        df = pd.DataFrame(verlauf)
        mitte_pfad = df.median(axis=1).dropna()
        serien = {n: (list(v.index), list(v.values)) for n, v in verlauf.items()}
        serien["Median der IPOs"] = (list(mitte_pfad.index), list(mitte_pfad.values))
        grau = [charts.KONTEXT] * len(verlauf)
        farben_ipo = grau + [charts.FARBEN[0]]
        if ant is not None and len(ant) > 1:
            av = risiko.ipo_verlauf(ant)
            serien["Anthropic"] = (list(av.index), list(av.values))
            farben_ipo.append(charts.FARBEN[2])
        ctx["chart_ipos"] = charts.linien_xy(
            serien, titel="Wie liefen grosse Tech-Börsengänge nach dem ersten Handelstag?",
            untertitel="Schlusskurs Tag 1 = 100, x-Achse: Handelstage seit Börsengang",
            quelle="Yahoo Finance; eigene Berechnung", farben=farben_ipo, breit=True, hoehe=340,
            x_titel="Handelstage seit Börsengang", referenz=100,
            hinweis="Grau: einzelne Börsengänge, Bernstein: Median. Der Ausgabepreis selbst ist nicht enthalten (nur Börsenkurse).")

    # --- News & Unterlagen ---------------------------------------------------------------
    artikel = []
    for begriff in cfg.get("suchbegriffe", []):
        try:
            artikel += news.google_news(begriff, 7)
        except Exception as e:
            d.fehler[f"news_{begriff}"] = str(e)
    from .website import _sortiere_news  # vermeidet Zirkel-Import beim Laden
    ctx["news"] = _sortiere_news(artikel, 30)
    ctx["bloomberg"] = [a for a in ctx["news"] if "bloomberg" in a["quelle"].lower()][:10]
    try:
        ctx["unterlagen"] = sec.einreichungen(cfg["firma"]["sec_cik"], 12)
    except Exception as e:
        ctx["unterlagen"], d.fehler["sec_unterlagen"] = [], str(e)
    return ctx


def termine(cfg: dict | None = None) -> list[dict]:
    """IPO-Termine für die Seite "Termine"."""
    cfg = cfg or lade_konfig()
    i = cfg["ipo"]
    return [{"datum": date.fromisoformat(i["preisfestsetzung"]), "zeit": "", "art": "IPO",
             "titel": f"Anthropic: Festsetzung des Ausgabepreises", "detail": "ANT", "wichtig": True},
            {"datum": date.fromisoformat(i["erster_handelstag"]), "zeit": "15:30", "art": "IPO",
             "titel": "Anthropic: erster Handelstag an der Nasdaq (erwartet)", "detail": "ANT", "wichtig": True}]
