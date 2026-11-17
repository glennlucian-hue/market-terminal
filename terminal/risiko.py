"""Risiko-Kennzahlen und Optionsanalyse.

Begriffe (einfach erklärt):
  Volatilität   Wie stark schwankt der Kurs? (annualisiert, in %)
  Sharpe Ratio  Rendite über dem risikolosen Zins pro Einheit Schwankung. > 1 gilt als gut.
  Sortino Ratio Wie Sharpe, zählt aber nur die Abwärtsschwankungen.
  Beta          Wie stark bewegt sich die Aktie, wenn der S&P 500 um 1 % steigt/fällt? 1.5 = 1.5 %.
  Max Drawdown  Grösster Verlust vom Höchststand bis zum Tiefpunkt.
  Gamma (GEX)   Wie viele Aktien müssen Options-Händler (Market Maker) kaufen/verkaufen,
                wenn sich der Kurs bewegt? Positives Gamma bremst Bewegungen, negatives verstärkt sie.
"""
import math
from datetime import date

import numpy as np
import pandas as pd


def kennzahlen(kurs: pd.Series, markt: pd.Series | None, zins_jahr: float = 0.0, tage: int = 365) -> dict | None:
    """Risiko-Kennzahlen über die letzten `tage` Kalendertage (oder seit Handelsbeginn, falls kürzer)."""
    kurs = kurs.dropna()
    kurs = kurs[kurs.index >= kurs.index[-1] - pd.Timedelta(days=tage)]
    if len(kurs) < 15:
        return None
    r = kurs.pct_change().dropna()
    jahre = len(r) / 252
    rendite = (kurs.iloc[-1] / kurs.iloc[0]) ** (1 / jahre) - 1 if jahre >= 0.25 else kurs.iloc[-1] / kurs.iloc[0] - 1
    vola = r.std() * math.sqrt(252)
    abwaerts = r[r < 0].std() * math.sqrt(252)
    ueber = r.mean() * 252 - zins_jahr
    beta = korrelation = None
    if markt is not None:
        df = pd.concat([r, markt.pct_change()], axis=1, join="inner").dropna()
        if len(df) >= 15:
            beta = float(df.iloc[:, 0].cov(df.iloc[:, 1]) / df.iloc[:, 1].var())
            korrelation = float(df.iloc[:, 0].corr(df.iloc[:, 1]))
    hoch = kurs.cummax()
    return {
        "rendite": rendite * 100, "annualisiert": jahre >= 0.25, "vola": vola * 100,
        "sharpe": ueber / vola if vola else None, "sortino": ueber / abwaerts if abwaerts else None,
        "beta": beta, "korrelation": korrelation, "max_dd": float((kurs / hoch - 1).min() * 100),
        "handelstage": len(kurs), "seit": kurs.index[0],
    }


def ipo_verlauf(kurs: pd.Series, tage: int = 120) -> pd.Series:
    """Kursentwicklung ab dem 1. Handelstag (Schlusskurs Tag 1 = 100), x = Handelstag."""
    k = kurs.dropna().iloc[:tage + 1]
    return pd.Series((k / k.iloc[0] * 100).values, index=range(len(k)))


# ---------------------------------------------------------------------------
# Gamma-Exposure (GEX) der Options-Händler
# ---------------------------------------------------------------------------
# Annahme (Branchenstandard): Händler sind bei Calls "long" (Kunden verkaufen Calls) und bei
# Puts "short" (Kunden kaufen Puts zur Absicherung). GEX je Strike in USD pro 1 % Kursbewegung:
#     Gamma x Open Interest x 100 Aktien x Kurs² x 0.01   (Calls +, Puts −)

def _bs_gamma(s: float, k: float, t: float, iv: float) -> float:
    if t <= 0 or iv <= 0 or s <= 0:
        return 0.0
    d1 = (math.log(s / k) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
    return math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * iv * math.sqrt(t))


def gamma_exposure(optionen: pd.DataFrame, kurs: float, max_tage: int = 60) -> dict:
    heute = date.today()
    o = optionen.copy()
    o["tage"] = [(date.fromisoformat(v) - heute).days for v in o["verfall"]]
    o = o[(o["tage"] >= 0) & (o["tage"] <= max_tage) & (o["oi"] > 0)]
    if o.empty:
        return {}
    vorzeichen = np.where(o["typ"] == "C", 1, -1)
    o["gex"] = o["gamma"].clip(lower=0) * o["oi"] * 100 * kurs ** 2 * 0.01 * vorzeichen
    je_strike = o.groupby("strike")["gex"].sum()
    naehe = je_strike[(je_strike.index > kurs * 0.75) & (je_strike.index < kurs * 1.25)]

    # Gamma-Flip: bei welchem Kurs kippt das Gesamt-Gamma von positiv zu negativ?
    o["t"] = (o["tage"].clip(lower=1)) / 365
    raster = np.linspace(kurs * 0.8, kurs * 1.2, 81)
    profil = []
    for s in raster:
        g = sum(_bs_gamma(s, k, t, iv) * oi * 100 * s * s * 0.01 * (1 if typ == "C" else -1)
                for k, t, iv, oi, typ in zip(o["strike"], o["t"], o["iv"], o["oi"], o["typ"]))
        profil.append(g)
    profil = np.array(profil)
    flip = None
    for i in range(1, len(raster)):
        if profil[i - 1] < 0 <= profil[i] or profil[i - 1] >= 0 > profil[i]:
            flip = float(raster[i - 1] + (raster[i] - raster[i - 1]) * (-profil[i - 1]) / (profil[i] - profil[i - 1]))
            break
    calls, puts = je_strike[je_strike > 0], je_strike[je_strike < 0]
    return {
        "gesamt_mrd": float(je_strike.sum()) / 1e9, "je_strike": naehe, "flip": flip, "kurs": kurs,
        "call_wand": float(calls.idxmax()) if not calls.empty else None,
        "put_wand": float(puts.idxmin()) if not puts.empty else None,
        "verfaelle": sorted(o["verfall"].unique())[:6], "max_tage": max_tage,
    }
