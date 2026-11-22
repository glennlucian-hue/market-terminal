"""Makro-Filter für QQQ/NQ: VIX9D/VIX, VIX-Korrelation, 2- und 10-jährige US-Zinsen, Dollar, NYSE-TICK.

Einfach erklärt:
  VIX9D / VIX     Kurzfrist- gegen 30-Tage-Volatilität. Über 1 (Backwardation) = akuter Stress, eher Abwärtsdruck.
                  Unter ~0.9 = ruhiger Markt, Rücksetzer werden eher gekauft.
  NQ-VIX-Korrelat. Normal stark negativ. Steigen NQ und VIX gleichzeitig, kauft jemand Absicherung in die Rally:
                  Warnzeichen, darum kleinere Positionen.
  10Y / 2Y        Steigende Zinsen (vor allem real/10Y) belasten Tech-Bewertungen. Der 2Y spiegelt die Fed-Erwartung.
  DXY             Starker Dollar = straffere Finanzbedingungen, eher Gegenwind.
  $TICK           Aufwärts- minus Abwärts-Ticks an der NYSE. Dauerhaft > +300 = breiter Kaufdruck, < −300 = Verkaufsdruck.
                  Ausschläge über ±1000 deuten oft auf Erschöpfung hin.
Das Ergebnis ist ein Punktwert (−∞ … +∞, praktisch etwa −5 … +5), eine Richtung und ein Grössenfaktor.
Fehlt eine Reihe, wird sie übersprungen und als Hinweis gemeldet.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DURATION_ZT = 1.9   # modifizierte Duration des 2-jährigen Treasury-Futures (ungefähr)


@dataclass
class MakroLage:
    punkte: float = 0.0
    bias: str = "neutral"              # "long", "short", "neutral"
    groessen_faktor: float = 1.0       # Multiplikator auf die Positionsgrösse
    gruende: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    werte: dict = field(default_factory=dict)


def _bis(s: pd.Series | None, t: pd.Timestamp) -> pd.Series | None:
    if s is None or s.empty:
        return None
    s = s.dropna()
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None and t.tzinfo is not None:
        s = s[s.index <= t]
    return s if len(s) else None


def _tagesaenderung(s: pd.Series) -> tuple[float, float] | None:
    """(Änderung, Referenzwert) seit dem letzten Wert des Vortags bzw. zum vorherigen Wert."""
    if len(s) < 2:
        return None
    if isinstance(s.index, pd.DatetimeIndex):
        heute = s.index[-1].date()
        vorher = s[s.index.date < heute]
        if len(vorher):
            return float(s.iloc[-1] - vorher.iloc[-1]), float(vorher.iloc[-1])
    return float(s.iloc[-1] - s.iloc[-2]), float(s.iloc[-2])


def bewerte(t: pd.Timestamp, reihen: dict[str, pd.Series], schwelle: float = 1.5) -> MakroLage:
    """reihen: 'basis' (NQ/QQQ-Schluss), 'vix', 'vix9d', 'us10y', 'us02y' (in %) oder 'us02y_future' (Kurs ZT),
    'dxy', 'tick'. Alle optional."""
    m = MakroLage()
    r = {k: _bis(v, t) for k, v in reihen.items()}

    vix, vix9 = r.get("vix"), r.get("vix9d")
    if vix is not None and vix9 is not None:
        q = pd.concat([vix9, vix], axis=1, keys=["v9", "v"]).ffill().dropna()
        if len(q):
            ratio = float(q["v9"].iloc[-1] / q["v"].iloc[-1])
            m.werte["vix9d_vix"] = round(ratio, 3)
            if ratio > 1.0:
                m.punkte -= 1.5
                m.gruende.append(f"VIX9D/VIX {ratio:.2f} > 1: Kurzfrist-Stress (Backwardation)")
            elif ratio < 0.90:
                m.punkte += 1
                m.gruende.append(f"VIX9D/VIX {ratio:.2f} < 0.90: ruhiger Markt")
            if len(q) > 12:
                alt = float(q["v9"].iloc[-13] / q["v"].iloc[-13])
                if ratio / alt - 1 > 0.04:
                    m.punkte -= 0.5
                    m.gruende.append("VIX9D/VIX steigt schnell")
    else:
        m.hinweise.append("VIX9D/VIX fehlt")

    if vix is not None:
        a = _tagesaenderung(vix)
        if a:
            proz = a[0] / a[1] * 100
            m.werte["vix_tag_proz"] = round(proz, 1)
            if proz > 5:
                m.punkte -= 1
                m.gruende.append(f"VIX +{proz:.1f} % heute")
            elif proz < -5:
                m.punkte += 1
                m.gruende.append(f"VIX {proz:.1f} % heute")

    basis = r.get("basis")
    if basis is not None and vix is not None:
        q = pd.concat([basis, vix], axis=1, keys=["b", "v"]).ffill().dropna().pct_change().dropna().tail(60)
        if len(q) >= 30:
            with np.errstate(invalid="ignore", divide="ignore"):
                korr = float(q["b"].corr(q["v"]))
            if korr == korr:   # nicht NaN (z. B. VIX ausserhalb der Handelszeit konstant)
                m.werte["korr_basis_vix"] = round(korr, 2)
            if korr > 0:
                m.groessen_faktor *= 0.5
                m.gruende.append(f"NQ und VIX laufen gleich (Korrelation {korr:+.2f}): Absicherung wird gekauft")

    if r.get("us02y") is None and r.get("us02y_future") is not None:
        r["us02y_bp_aus_future"] = r["us02y_future"]
    for name, schl, gewicht in (("10Y", "us10y", 1.0), ("2Y", "us02y", 0.5)):
        s = r.get(schl)
        fut = r.get("us02y_bp_aus_future") if schl == "us02y" and s is None else None
        if s is None and fut is None:
            m.hinweise.append(f"{name}-Zins fehlt")
            continue
        a = _tagesaenderung(s if s is not None else fut)
        if not a:
            continue
        # Rendite in % -> bp; beim Future: Kursänderung / Duration (ZT ≈ 1.9 Jahre), Vorzeichen umgekehrt
        bp = a[0] * 100 if s is not None else -(a[0] / a[1]) / DURATION_ZT * 10_000
        m.werte[f"{schl}_bp"] = round(bp, 1)
        if bp > 5:
            m.punkte -= gewicht
            m.gruende.append(f"{name} +{bp:.0f} bp: Gegenwind für Tech")
        elif bp < -5:
            m.punkte += gewicht
            m.gruende.append(f"{name} {bp:.0f} bp: Rückenwind für Tech")
    if r.get("us10y") is not None and r.get("us02y") is not None:
        m.werte["kurve_10y_2y"] = round(float(r["us10y"].iloc[-1] - r["us02y"].iloc[-1]), 2)

    dxy = r.get("dxy")
    if dxy is not None:
        a = _tagesaenderung(dxy)
        if a:
            proz = a[0] / a[1] * 100
            m.werte["dxy_tag_proz"] = round(proz, 2)
            if proz > 0.3:
                m.punkte -= 0.5
                m.gruende.append(f"Dollar +{proz:.2f} %")
            elif proz < -0.3:
                m.punkte += 0.5
                m.gruende.append(f"Dollar {proz:.2f} %")
    else:
        m.hinweise.append("DXY fehlt")

    tick = r.get("tick")
    if tick is not None and isinstance(tick.index, pd.DatetimeIndex):
        letzte = tick[tick.index > tick.index[-1] - pd.Timedelta(minutes=30)]
        mittel = float(letzte.mean())
        m.werte["tick_30min"] = round(mittel)
        if mittel > 300:
            m.punkte += 1
            m.gruende.append(f"TICK im Schnitt {mittel:+.0f}: breiter Kaufdruck")
        elif mittel < -300:
            m.punkte -= 1
            m.gruende.append(f"TICK im Schnitt {mittel:+.0f}: breiter Verkaufsdruck")
        if abs(float(tick.iloc[-1])) >= 1000:
            m.gruende.append(f"TICK-Extrem {float(tick.iloc[-1]):+.0f}: mögliche Erschöpfung")
    else:
        m.hinweise.append("$TICK fehlt (nicht bei Yahoo; z. B. über IBKR oder TradingView)")

    m.punkte = round(m.punkte, 2)
    m.bias = "long" if m.punkte >= schwelle else "short" if m.punkte <= -schwelle else "neutral"
    return m
