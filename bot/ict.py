"""ICT-Bausteine: Liquidität, Turtle Soup (Sweep) und CISD (Change in State of Delivery).

Einfach erklärt:
  Liquidität     Über alten Hochs und unter alten Tiefs liegen viele Stopps. Der Markt holt sie sich oft ab.
                 Hier: bestätigte Swing-Hochs/-Tiefs und Vortages-Hoch/-Tief (PDH/PDL).
  Turtle Soup    Der Kurs sticht über ein altes Hoch (bzw. unter ein altes Tief), holt die Stopps ab
  (TS, Sweep)    und kommt wieder zurück. Das ist der "Fehlausbruch".
  CISD           Nach dem Sweep: Der Kurs schliesst über dem Eröffnungskurs der Kerzenserie, die ihn ins Tief
                 geliefert hat (Long) bzw. unter dem Eröffnungskurs der Serie, die ihn ins Hoch geliefert hat (Short).
                 Damit wechselt die "Lieferung" die Richtung: das ist der Einstiegs-Auslöser.

Wichtig: Alles wird Kerze für Kerze nur mit Daten berechnet, die zum Schluss der jeweiligen Kerze bekannt waren
(kein Blick in die Zukunft). Ein Swing gilt erst als bestätigt, wenn `rechts` Kerzen danach geschlossen haben.
"""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Liquiditaet:
    preis: float
    seite: str          # "hoch" (Buy-Side-Liquidität) oder "tief" (Sell-Side-Liquidität)
    art: str            # "swing" oder "vortag"
    idx: int            # Kerze, an der das Niveau entstanden ist


@dataclass
class Setup:
    """Turtle Soup + CISD. `idx` ist die Kerze, deren Schluss den CISD bestätigt (Einstieg zum Schlusskurs)."""
    idx: int
    zeit: pd.Timestamp
    richtung: str       # "long" oder "short"
    einstieg: float
    extrem: float       # Tief (Long) bzw. Hoch (Short) des Sweeps -> Basis für den Stop
    extrem_idx: int
    sweep: Liquiditaet
    cisd_level: float
    gegenseite: list = field(default_factory=list)   # offene Liquidität in Zielrichtung (Preise)


def _cisd_level(o, c, extrem_idx: int, richtung: str) -> float:
    """Eröffnung der ersten Kerze der Serie, die den Kurs ins Extrem geliefert hat."""
    gegen = (lambda j: c[j] < o[j]) if richtung == "long" else (lambda j: c[j] > o[j])
    j = extrem_idx
    if not gegen(j):          # Extrem-Kerze selbst dreht schon (z. B. Hammer): Serie beginnt davor
        j -= 1
    erste = None
    while j >= 0 and gegen(j):
        erste = j
        j -= 1
    if erste is None:         # keine Serie gefunden: Eröffnung der Extrem-Kerze
        return float(o[extrem_idx])
    return float(o[erste])


def setups(df: pd.DataFrame, links: int = 3, rechts: int = 2, max_alter: int = 120,
           max_bis_cisd: int = 12, vortag: bool = True) -> list[Setup]:
    """Findet alle Turtle-Soup-+-CISD-Setups in einem OHLC-DataFrame (Spalten Open/High/Low/Close).

    links/rechts   Kerzen links/rechts eines Swings (rechts = Bestätigungsverzögerung)
    max_alter      Swing-Niveaus älter als so viele Kerzen verfallen
    max_bis_cisd   so viele Kerzen nach dem Sweep darf der CISD höchstens kommen
    vortag         Vortages-Hoch/-Tief als zusätzliche Liquidität (Index muss Zeitstempel haben)
    """
    o, h, l, c = (df[s].to_numpy(dtype=float) for s in ("Open", "High", "Low", "Close"))
    n = len(df)
    offen: list[Liquiditaet] = []
    sweeps: list[dict] = []
    gefunden: list[Setup] = []

    tage = None
    if vortag and isinstance(df.index, pd.DatetimeIndex):
        tage = pd.Series(df.index.date, index=range(n))
    tag_hoch = tag_tief = None

    for t in range(n):
        # 1) Vortages-Niveaus beim ersten Bar eines neuen Tages
        if tage is not None and t > 0 and tage[t] != tage[t - 1]:
            if tag_hoch is not None:
                offen = [q for q in offen if q.art != "vortag"]
                offen += [Liquiditaet(tag_hoch, "hoch", "vortag", t - 1), Liquiditaet(tag_tief, "tief", "vortag", t - 1)]
            tag_hoch, tag_tief = h[t], l[t]
        else:
            tag_hoch = h[t] if tag_hoch is None else max(tag_hoch, h[t])
            tag_tief = l[t] if tag_tief is None else min(tag_tief, l[t])

        # 2) Swing bestätigen, der jetzt `rechts` Kerzen alt ist
        i = t - rechts
        if i >= links:
            fenster = slice(i - links, t + 1)
            if h[i] == h[fenster].max() and (h[fenster] == h[i]).sum() == 1:
                offen.append(Liquiditaet(float(h[i]), "hoch", "swing", i))
            if l[i] == l[fenster].min() and (l[fenster] == l[i]).sum() == 1:
                offen.append(Liquiditaet(float(l[i]), "tief", "swing", i))
        offen = [q for q in offen if q.art == "vortag" or t - q.idx <= max_alter]

        # 3) Laufende Sweeps nachführen (neues Extrem -> CISD-Niveau neu bestimmen)
        for s in sweeps:
            if s["richtung"] == "long" and l[t] < s["extrem"]:
                s.update(extrem=float(l[t]), extrem_idx=t)
            elif s["richtung"] == "short" and h[t] > s["extrem"]:
                s.update(extrem=float(h[t]), extrem_idx=t)

        # 4) Neue Sweeps: Docht durch ein offenes Niveau (das Niveau ist danach "abgeholt")
        bleibt = []
        for q in offen:
            if q.seite == "tief" and l[t] < q.preis and q.idx < t:
                sweeps.append({"richtung": "long", "liq": q, "start": t, "extrem": float(l[t]), "extrem_idx": t})
            elif q.seite == "hoch" and h[t] > q.preis and q.idx < t:
                sweeps.append({"richtung": "short", "liq": q, "start": t, "extrem": float(h[t]), "extrem_idx": t})
            else:
                bleibt.append(q)
        offen = bleibt

        # 5) CISD prüfen; pro Richtung nur das jüngste offene Sweep-Paket auslösen
        rest = []
        for s in sweeps:
            if t - s["start"] > max_bis_cisd:
                continue
            lvl = _cisd_level(o, c, s["extrem_idx"], s["richtung"])
            ok = (c[t] > lvl and c[t] > s["liq"].preis) if s["richtung"] == "long" else \
                 (c[t] < lvl and c[t] < s["liq"].preis)
            if ok:
                ziel_seite = "hoch" if s["richtung"] == "long" else "tief"
                gegen = sorted(q.preis for q in offen if q.seite == ziel_seite)
                if s["richtung"] == "short":
                    gegen = gegen[::-1]
                gefunden.append(Setup(t, df.index[t], s["richtung"], float(c[t]), s["extrem"], s["extrem_idx"],
                                      s["liq"], lvl, gegen))
            else:
                rest.append(s)
        # mehrere gleichzeitig ausgelöste Sweeps derselben Richtung = ein Setup
        sweeps = rest
        if gefunden and gefunden[-1].idx == t:
            letzte = [g for g in gefunden if g.idx == t]
            for r in ("long", "short"):
                gleiche = [g for g in letzte if g.richtung == r]
                for doppelt in gleiche[1:]:
                    gefunden.remove(doppelt)
    return gefunden
