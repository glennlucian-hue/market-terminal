"""Signal-Logik: ICT-Setup (Turtle Soup + CISD) + Orderflow-Bestätigung + TPO/GEX-Kontext + Makro-Filter.

Ablauf je Setup:
  1. Zeitfenster   nur in den Kill Zones (Standard: 09:30–11:30 und 13:30–15:30 New York)
  2. Makro         Signal gegen den Makro-Bias wird verworfen; bei neutralem Bias halbe Grösse
  3. Stop          hinter dem Sweep-Extrem plus Puffer
  4. Ziel          nächste Gegen-Liquidität (Swing, Vortag, TPO-VAH/VAL/POC, GEX-Levels) mit mindestens min_rr;
                   gibt es keine, wird das Setup verworfen (kein "Hoffnungs-Ziel")
  5. Bestätigung   CVD-Divergenz (Absorption), Sweep an Value-Area-Rand, GEX-Lage -> Punkte
  6. Grösse        aus dem Risikowächter (1 % Risiko, Grenzen, Not-Aus)
Ergebnis ist ein VORSCHLAG. Der Bot handelt nicht selbst.
"""
from dataclasses import dataclass, field
from datetime import time

import pandas as pd

from . import orderflow
from .ict import Setup
from .makro import MakroLage
from .risiko_regeln import INSTRUMENTE, RisikoWaechter

KILL_ZONES = ((time(9, 30), time(11, 30)), (time(13, 30), time(15, 30)))


@dataclass
class Signal:
    zeit: pd.Timestamp
    richtung: str
    einstieg: float
    stop: float
    ziel: float
    rr: float
    stueck: int
    einheit: str
    risiko: float
    punkte: float
    gruende: list = field(default_factory=list)
    warnungen: list = field(default_factory=list)

    def text(self, instrument: str) -> str:
        pfeil = "LONG ▲" if self.richtung == "long" else "SHORT ▼"
        z = [f"{self.zeit:%d.%m.%Y %H:%M} NY  {instrument} {pfeil}",
             f"  Einstieg {self.einstieg:.2f} · Stop {self.stop:.2f} · Ziel {self.ziel:.2f} · CRV {self.rr:.1f}",
             f"  Grösse {self.stueck} {self.einheit} · Risiko {self.risiko:.0f} · Qualität {self.punkte:.1f}"]
        z += [f"  + {g}" for g in self.gruende] + [f"  ! {w}" for w in self.warnungen]
        return "\n".join(z)


def in_kill_zone(t: pd.Timestamp, zonen=KILL_ZONES) -> bool:
    return any(a <= t.time() < b for a, b in zonen)


def _ziele(setup: Setup, profil: dict | None, gex: dict | None) -> list[tuple[float, str]]:
    kand = [(p, "Liquidität") for p in setup.gegenseite]
    if profil:
        kand += [(profil["poc"], "Vortages-POC"), (profil["vah"], "Vortages-VAH"), (profil["val"], "Vortages-VAL")]
    if gex:
        for k, name in (("zero_gamma", "Zero Gamma"), ("major_pos", "GEX Call-Wand"), ("major_neg", "GEX Put-Wand")):
            if gex.get(k):
                kand.append((float(gex[k]), name))
    e = setup.einstieg
    if setup.richtung == "long":
        return sorted([k for k in kand if k[0] > e], key=lambda k: k[0])
    return sorted([k for k in kand if k[0] < e], key=lambda k: -k[0])


def bewerte(setup: Setup, df: pd.DataFrame, instrument: str, waechter: RisikoWaechter,
            makro: MakroLage | None = None, profil: dict | None = None, gex: dict | None = None,
            cvd_reihe: pd.Series | None = None, cvd_art: str = "schaetzung", kill_zones=KILL_ZONES,
            min_punkte: float = 1.0) -> tuple[Signal | None, str]:
    """Gibt (Signal, "") oder (None, Grund für die Ablehnung) zurück."""
    r, regeln, spez = setup.richtung, waechter.regeln, INSTRUMENTE[instrument]
    if kill_zones and not in_kill_zone(setup.zeit, kill_zones):
        return None, "ausserhalb der Kill Zones"
    ok, grund = waechter.erlaubt(setup.zeit.date())
    if not ok:
        return None, grund

    seite, lage = ("Tief", "über") if r == "long" else ("Hoch", "unter")
    gruende = [f"Turtle Soup an {setup.sweep.art}-{seite} {setup.sweep.preis:.2f}, CISD {lage} {setup.cisd_level:.2f}"]
    warn, punkte, faktor = [], 1.0, 1.0

    if makro is not None:
        if makro.bias not in ("neutral", r):
            return None, f"gegen Makro-Bias ({makro.bias}, {makro.punkte:+.1f})"
        if makro.bias == r:
            punkte += 1
            gruende.append(f"Makro stützt ({makro.punkte:+.1f}): " + "; ".join(makro.gruende[:3]))
        else:
            faktor *= 0.5
            warn.append(f"Makro neutral ({makro.punkte:+.1f}): halbe Grösse")
        faktor *= makro.groessen_faktor
        if makro.groessen_faktor < 1:
            warn.append("NQ/VIX-Korrelation positiv: Grösse reduziert")

    puffer = regeln.stop_puffer_ticks * spez["tick"]
    stop = setup.extrem - puffer if r == "long" else setup.extrem + puffer
    risiko_pkt = abs(setup.einstieg - stop)
    ziel, ziel_name = None, ""
    for preis, name in _ziele(setup, profil, gex):
        if abs(preis - setup.einstieg) / risiko_pkt >= regeln.min_rr:
            ziel, ziel_name = preis, name
            break
    if ziel is None:
        return None, f"kein Ziel mit CRV ≥ {regeln.min_rr}"
    rr = abs(ziel - setup.einstieg) / risiko_pkt
    gruende.append(f"Ziel {ziel_name} {ziel:.2f}")

    if cvd_reihe is not None and setup.sweep.art == "swing":
        if orderflow.cvd_divergenz(cvd_reihe, setup.sweep.idx, setup.extrem_idx, r):
            punkte += 1 if cvd_art == "echt" else 0.5
            gruende.append("CVD-Divergenz am Sweep (Absorption)" + ("" if cvd_art == "echt" else " – geschätzt"))

    if profil:
        rand = profil["val"] if r == "long" else profil["vah"]
        if (r == "long" and setup.extrem <= rand) or (r == "short" and setup.extrem >= rand):
            punkte += 0.5
            gruende.append(f"Sweep {'unter VAL' if r == 'long' else 'über VAH'} des Vortags ({rand:.2f})")

    if gex and gex.get("zero_gamma") and gex.get("spot"):
        # GEX-Levels kommen oft vom Index/ETF (NDX/QQQ): nur die Lage über/unter Zero Gamma wird genutzt
        ueber = gex["spot"] >= gex["zero_gamma"]
        if (r == "long") == ueber:
            punkte += 0.5
            gruende.append("über Zero Gamma: Händler dämpfen, Rücksetzer werden eher gekauft" if ueber else
                           "unter Zero Gamma: Händler verstärken Abwärtsbewegungen")
        else:
            warn.append("Trade gegen das Gamma-Regime")

    if punkte < min_punkte:
        return None, f"Qualität {punkte:.1f} < {min_punkte}"
    g = waechter.positionsgroesse(setup.einstieg, stop, instrument, faktor)
    if g["stueck"] <= 0:
        return None, g["grund"]
    return Signal(setup.zeit, r, setup.einstieg, round(stop, 4), round(ziel, 4), round(rr, 2), g["stueck"],
                  g["einheit"], g["risiko"], punkte, gruende, warn), ""
