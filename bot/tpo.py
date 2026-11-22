"""TPO-Profil (Market Profile): POC, Value Area, Initial Balance, Single Prints, Poor High/Low.

Einfach erklärt:
  TPO          Jede 30-Minuten-Periode bekommt einen Buchstaben auf jeder Preisstufe, die sie berührt hat.
  POC          Preis mit den meisten TPOs = "fairster" Preis der Sitzung.
  Value Area   Bereich um den POC mit 70 % aller TPOs (VAH = oberer, VAL = unterer Rand).
  IB           Initial Balance = Spanne der ersten Stunde.
  Single Print Stufe, die nur eine Periode berührt hat: schnelle, einseitige Bewegung; wird oft wieder getestet.
  Poor High/Low Hoch/Tief mit mehreren TPOs = "unfertige" Auktion; wird oft später noch abgeholt (Liquidität).
"""
import math

import pandas as pd


def tpo_profil(df: pd.DataFrame, tick: float, periode: str = "30min", value_area: float = 0.70) -> dict | None:
    if df.empty:
        return None
    perioden = df.resample(periode).agg({"High": "max", "Low": "min"}).dropna()
    zaehler: dict[float, int] = {}
    for _, p in perioden.iterrows():
        a, b = math.floor(p["Low"] / tick + 1e-9), math.floor(p["High"] / tick + 1e-9)
        for k in range(a, b + 1):
            zaehler[k] = zaehler.get(k, 0) + 1
    if not zaehler:
        return None
    stufen = sorted(zaehler)
    mitte = (stufen[0] + stufen[-1]) / 2
    top = max(zaehler.values())
    poc = min((k for k in stufen if zaehler[k] == top), key=lambda k: abs(k - mitte))
    # Value Area: vom POC aus jeweils die Seite mit mehr TPOs dazunehmen (je zwei Stufen, wie üblich)
    ziel, summe = value_area * sum(zaehler.values()), zaehler[poc]
    unten = oben = poc
    while summe < ziel and (unten > stufen[0] or oben < stufen[-1]):
        hoch2 = sum(zaehler.get(oben + i, 0) for i in (1, 2))
        tief2 = sum(zaehler.get(unten - i, 0) for i in (1, 2))
        if hoch2 >= tief2 and oben < stufen[-1]:
            oben, summe = oben + 2, summe + hoch2
        elif unten > stufen[0]:
            unten, summe = unten - 2, summe + tief2
        else:
            oben, summe = oben + 2, summe + hoch2
    oben, unten = min(oben, stufen[-1]), max(unten, stufen[0])
    ib = perioden.iloc[:2]
    singles = [k * tick for k in stufen[1:-1] if zaehler[k] == 1]
    return {
        "poc": poc * tick, "vah": oben * tick, "val": unten * tick,
        "hoch": stufen[-1] * tick, "tief": stufen[0] * tick,
        "ib_hoch": float(ib["High"].max()), "ib_tief": float(ib["Low"].min()),
        "single_prints": singles,
        "poor_high": zaehler[stufen[-1]] >= 2, "poor_low": zaehler[stufen[0]] >= 2,
        "tpo": {k * tick: v for k, v in zaehler.items()},
    }


def rth(df: pd.DataFrame, start: str = "09:30", ende: str = "16:00") -> pd.DataFrame:
    """Nur reguläre US-Handelszeit (Index in New Yorker Zeit)."""
    return df.between_time(start, ende, inclusive="left")


def vortages_profil(df: pd.DataFrame, bis: pd.Timestamp, tick: float) -> dict | None:
    """Profil der letzten abgeschlossenen RTH-Sitzung vor dem Zeitpunkt `bis`."""
    r = rth(df[df.index < bis.normalize()])
    if r.empty:
        return None
    letzter_tag = r.index[-1].date()
    return tpo_profil(r[r.index.date == letzter_tag], tick)
