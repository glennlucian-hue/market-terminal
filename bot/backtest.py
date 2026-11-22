"""Einfacher Kerzen-Backtest der Signal-Logik.

Annahmen (bewusst vorsichtig):
  - Einstieg zum Schlusskurs der CISD-Kerze, plus Schlupf (slippage) in Ticks gegen uns.
  - Berühren Stop und Ziel dieselbe Kerze, zählt der Stop (schlechtester Fall).
  - Spätestens um `flat_um` (New York) wird glattgestellt. Immer nur eine Position gleichzeitig.
  - Gebühren je Stück und Seite (siehe INSTRUMENTE) werden abgezogen.
Ein Kerzen-Backtest überschätzt Orderflow-Strategien oft. Er ist ein Filter ("taugt die Idee?"), kein Beweis.
"""
from dataclasses import dataclass, field
from datetime import time

import pandas as pd

from . import ict, makro, orderflow, signale, tpo
from .risiko_regeln import INSTRUMENTE, Regeln, RisikoWaechter


@dataclass
class Ergebnis:
    trades: list = field(default_factory=list)
    abgelehnt: dict = field(default_factory=dict)

    def kennzahlen(self) -> dict:
        if not self.trades:
            return {"trades": 0}
        r = pd.Series([t["r"] for t in self.trades])
        geld = pd.Series([t["ergebnis"] for t in self.trades])
        kurve = geld.cumsum()
        gewinne, verluste = geld[geld > 0].sum(), -geld[geld < 0].sum()
        return {"trades": len(r), "trefferquote": round(float((r > 0).mean()) * 100, 1),
                "schnitt_r": round(float(r.mean()), 2), "summe_r": round(float(r.sum()), 2),
                "ergebnis": round(float(geld.sum()), 2),
                "profit_faktor": round(float(gewinne / verluste), 2) if verluste > 0 else None,
                "max_drawdown": round(float((kurve - kurve.cummax().clip(lower=0)).min()), 2)}


def lauf(df: pd.DataFrame, instrument: str, regeln: Regeln | None = None, makro_reihen: dict | None = None,
         gex: dict | None = None, flat_um: time = time(15, 55), schlupf_ticks: int = 1,
         mit_makro: bool = True, kill_zones=signale.KILL_ZONES,
         min_punkte: float = 1.0) -> Ergebnis:
    regeln = regeln or Regeln()
    waechter = RisikoWaechter(regeln)
    spez = INSTRUMENTE[instrument]
    cvd_reihe, cvd_art = orderflow.cvd(df)
    erg = Ergebnis()
    h, l, c = df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy()
    frei_ab = 0
    profile: dict = {}

    for s in ict.setups(df):
        if s.idx < frei_ab:
            erg.abgelehnt["Position offen"] = erg.abgelehnt.get("Position offen", 0) + 1
            continue
        tag = s.zeit.date()
        if tag not in profile:
            profile[tag] = tpo.vortages_profil(df, s.zeit, spez["tick"])
        lage = makro.bewerte(s.zeit, {"basis": df["Close"], **(makro_reihen or {})}) if mit_makro else None
        sig, grund = signale.bewerte(s, df, instrument, waechter, lage, profile[tag], gex, cvd_reihe, cvd_art,
                                     kill_zones, min_punkte)
        if sig is None:
            erg.abgelehnt[grund.split(" (")[0]] = erg.abgelehnt.get(grund.split(" (")[0], 0) + 1
            continue

        vz = 1 if sig.richtung == "long" else -1
        einstieg = sig.einstieg + vz * schlupf_ticks * spez["tick"]
        aus, grund_aus, j = None, "", s.idx
        for j in range(s.idx + 1, len(df)):
            t = df.index[j]
            if t.date() != tag or t.time() >= flat_um:
                aus, grund_aus = c[j - 1] if t.date() != tag else c[j], "Zeit"
                break
            stop_hit = l[j] <= sig.stop if vz > 0 else h[j] >= sig.stop
            ziel_hit = h[j] >= sig.ziel if vz > 0 else l[j] <= sig.ziel
            if stop_hit:
                aus, grund_aus = sig.stop - vz * schlupf_ticks * spez["tick"], "Stop"
                break
            if ziel_hit:
                aus, grund_aus = sig.ziel, "Ziel"
                break
        if aus is None:
            aus, grund_aus = c[-1], "Datenende"
        punkte = (aus - einstieg) * vz
        gebuehr = max(spez["gebuehr"] * sig.stueck, spez.get("min_gebuehr", 0.0))
        ergebnis = punkte * spez["punktwert"] * sig.stueck - 2 * gebuehr
        risiko_pkt = abs(sig.einstieg - sig.stop)
        waechter.buche(tag, ergebnis)
        erg.trades.append({"zeit": sig.zeit, "richtung": sig.richtung, "einstieg": einstieg, "stop": sig.stop,
                           "ziel": sig.ziel, "aus": aus, "grund": grund_aus, "stueck": sig.stueck,
                           "r": round(punkte / risiko_pkt, 2), "ergebnis": round(ergebnis, 2),
                           "qualitaet": sig.punkte})
        frei_ab = j + 1
    return erg
