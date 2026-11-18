"""Chart-Technik: gleitende Durchschnitte, RSI, MACD und Pivot-Punkte.

Einfach erklärt:
  50-/200-Tage-Linie  Durchschnittskurs der letzten 50 bzw. 200 Handelstage. Liegt der Kurs darüber,
                      gilt der Trend als positiv. Kreuzt die 50er die 200er von unten = "Golden Cross".
  RSI (14 Tage)       0–100. Über 70 = "überkauft" (stark gestiegen), unter 30 = "überverkauft".
  MACD                Differenz zweier Durchschnitte. Liegt der MACD über seiner Signallinie = Aufwärtsimpuls.
  Pivot-Punkte        Aus Hoch, Tief und Schluss des Vormonats berechnete Zonen. Händler achten darauf:
                      R1/R2 = mögliche Widerstände (oben), S1/S2 = mögliche Unterstützungen (unten).
"""
import pandas as pd


def rsi(kurs: pd.Series, tage: int = 14) -> pd.Series:
    diff = kurs.diff()
    auf = diff.clip(lower=0).ewm(alpha=1 / tage, adjust=False).mean()
    ab = (-diff.clip(upper=0)).ewm(alpha=1 / tage, adjust=False).mean()
    return 100 - 100 / (1 + auf / ab)


def macd(kurs: pd.Series) -> tuple[pd.Series, pd.Series]:
    linie = kurs.ewm(span=12, adjust=False).mean() - kurs.ewm(span=26, adjust=False).mean()
    return linie, linie.ewm(span=9, adjust=False).mean()


def pivots(ohlc: pd.DataFrame, periode: str = "M") -> dict:
    """Klassische Pivot-Punkte aus der letzten abgeschlossenen Periode (M = Monat, W = Woche)."""
    regel = "ME" if periode == "M" else "W-FRI"
    p = ohlc.resample(regel).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    letzte_ganze = p.iloc[-2] if len(p) >= 2 else p.iloc[-1]   # die laufende Periode ist noch nicht fertig
    h, l, c = float(letzte_ganze["High"]), float(letzte_ganze["Low"]), float(letzte_ganze["Close"])
    pp = (h + l + c) / 3
    return {"P": pp, "R1": 2 * pp - l, "S1": 2 * pp - h, "R2": pp + (h - l), "S2": pp - (h - l),
            "basis": p.index[-2] if len(p) >= 2 else p.index[-1]}


def auswertung(ohlc: pd.DataFrame) -> dict:
    k = ohlc["Close"]
    sma50, sma200 = k.rolling(50).mean(), k.rolling(200).mean()
    r = rsi(k)
    m, sig = macd(k)
    jetzt = float(k.iloc[-1])
    piv = pivots(ohlc, "M")
    punkte = 0
    signale = []
    if pd.notna(sma50.iloc[-1]):
        if jetzt > sma50.iloc[-1]:
            punkte += 1; signale.append("Kurs über der 50-Tage-Linie")
        else:
            signale.append("Kurs unter der 50-Tage-Linie")
    if pd.notna(sma200.iloc[-1]):
        if jetzt > sma200.iloc[-1]:
            punkte += 1; signale.append("Kurs über der 200-Tage-Linie (langfristiger Aufwärtstrend)")
        else:
            signale.append("Kurs unter der 200-Tage-Linie (langfristiger Abwärtstrend)")
        if pd.notna(sma50.iloc[-1]) and sma50.iloc[-1] > sma200.iloc[-1]:
            punkte += 1; signale.append("50er über 200er Linie")
    if m.iloc[-1] > sig.iloc[-1]:
        punkte += 1; signale.append("MACD über Signallinie (Aufwärtsimpuls)")
    else:
        signale.append("MACD unter Signallinie (Abwärtsimpuls)")
    rsi_jetzt = float(r.iloc[-1])
    if rsi_jetzt > 70:
        signale.append(f"RSI {rsi_jetzt:.0f}: überkauft – Rücksetzer möglich")
    elif rsi_jetzt < 30:
        signale.append(f"RSI {rsi_jetzt:.0f}: überverkauft – Erholung möglich")
    naechste_unterstuetzung = max([v for n, v in piv.items() if n != "basis" and v < jetzt], default=None)
    naechster_widerstand = min([v for n, v in piv.items() if n != "basis" and v > jetzt], default=None)
    hoch52, tief52 = float(k.max()), float(k.min())
    return {
        "kurs": jetzt, "sma50": float(sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None,
        "sma200": float(sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None,
        "abstand200": (jetzt / sma200.iloc[-1] - 1) * 100 if pd.notna(sma200.iloc[-1]) else None,
        "rsi": rsi_jetzt, "macd_positiv": bool(m.iloc[-1] > sig.iloc[-1]), "trendpunkte": punkte,
        "trend": ["Abwärtstrend", "eher schwach", "neutral", "eher positiv", "Aufwärtstrend"][punkte],
        "signale": signale, "pivots": piv, "unterstuetzung": naechste_unterstuetzung, "widerstand": naechster_widerstand,
        "hoch52": hoch52, "tief52": tief52, "vom_hoch": (jetzt / hoch52 - 1) * 100,
        "sma50_reihe": sma50, "sma200_reihe": sma200,
    }
