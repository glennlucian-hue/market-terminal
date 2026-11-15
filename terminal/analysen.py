"""Eigene Analysen auf Basis der geladenen Daten.

Alle Modelle hier sind bewusst einfach und nachvollziehbar. Sie sind Schätzungen,
keine echten Positionsdaten von Banken oder Fonds.
"""
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CTA-Modell (Trendfolger)
# ---------------------------------------------------------------------------
# Idee: CTAs kaufen, wenn der Kurs über dem Kurs von vor X Tagen liegt (Trend positiv),
# und verkaufen, wenn er darunter liegt. Viele CTAs mischen mehrere Zeitfenster und
# verkleinern ihre Positionen, wenn der Markt sehr schwankt (Volatilität).
#
#   Trendsignal je Fenster = tanh( Rendite über das Fenster / erwartete Schwankung )
#                            -> Wert zwischen -1 (klar fallend) und +1 (klar steigend)
#   Volatilitätsbremse     = min(1, 15 % / aktuelle Jahres-Volatilität)
#   Modell-Exposure        = Durchschnitt der Signale x Volatilitätsbremse, in % (-100 bis +100)

CTA_FENSTER = {"1 Monat": 21, "3 Monate": 63, "6 Monate": 126, "12 Monate": 252}
CTA_ZIELVOLA = 0.15


def cta_modell(kurs: pd.Series) -> dict:
    kurs = kurs.dropna()
    rendite = np.log(kurs).diff()
    vola_tag = rendite.rolling(63).std()

    signale = {}
    for name, n in CTA_FENSTER.items():
        trend = np.log(kurs / kurs.shift(n))
        signale[name] = np.tanh(trend / (vola_tag * np.sqrt(n)))
    signale = pd.DataFrame(signale).dropna()

    vola_jahr = rendite.rolling(21).std() * np.sqrt(252)
    bremse = (CTA_ZIELVOLA / vola_jahr).clip(upper=1).reindex(signale.index)
    exposure = (signale.mean(axis=1) * bremse * 100).dropna()

    jetzt = float(kurs.iloc[-1])
    ausloeser = []
    for name, n in CTA_FENSTER.items():
        # Der Kurs, mit dem der heutige Kurs verglichen wird. Fällt der Kurs darunter, kippt das Signal.
        referenz = float(kurs.iloc[-n - 1])
        ausloeser.append({
            "fenster": name, "tage": n, "signal": float(signale[name].iloc[-1]),
            "referenz": referenz, "abstand": (jetzt / referenz - 1) * 100,
        })
    return {
        "exposure": exposure,
        "aktuell": float(exposure.iloc[-1]),
        "vor_woche": float(exposure.iloc[-6]) if len(exposure) > 6 else None,
        "vola": float(vola_jahr.iloc[-1]) * 100,
        "ausloeser": ausloeser,
    }


# ---------------------------------------------------------------------------
# US-Liquidität ("Net Liquidity")
# ---------------------------------------------------------------------------
# Fed-Bilanzsumme minus Guthaben des US-Finanzministeriums bei der Fed (TGA)
# minus Reverse-Repo-Geschäfte. Steigt sie, ist tendenziell mehr Geld im System.

def netto_liquiditaet(walcl: pd.Series, tga: pd.Series, rrp: pd.Series) -> pd.Series:
    """Alle Eingaben wie von FRED geliefert: WALCL (Mio. USD), WTREGEN (Mio. USD), RRPONTSYD (Mrd. USD).
    Ergebnis in Billionen USD (Wochenwerte, Mittwoch)."""
    df = pd.concat({"bilanz": walcl / 1000, "tga": tga / 1000, "rrp": rrp}, axis=1).sort_index().ffill()
    netto = (df["bilanz"] - df["tga"] - df["rrp"]).dropna() / 1000
    return netto.resample("W-WED").last().dropna()


# ---------------------------------------------------------------------------
# Korrelation und Liquiditäts-Selloff
# ---------------------------------------------------------------------------

def rollierende_korrelation(a: pd.Series, b: pd.Series, fenster: int = 30) -> pd.Series:
    """Korrelation der täglichen Renditen über die letzten `fenster` gemeinsamen Handelstage."""
    df = pd.concat([a, b], axis=1, join="inner").dropna()
    r = df.pct_change().dropna()
    return r.iloc[:, 0].rolling(fenster).corr(r.iloc[:, 1]).dropna()


def selloff_check(reihen: dict[str, pd.Series], tage: int = 5) -> dict:
    """Prüft das typische Muster eines Liquiditäts-Selloffs über die letzten `tage` Handelstage:
    Gold, Bitcoin und Aktien fallen gleichzeitig, VIX und Dollar steigen."""
    erwartet = {"Gold": "fällt", "Bitcoin": "fällt", "Nasdaq 100": "fällt", "VIX": "steigt", "Dollar-Index": "steigt"}
    zeilen, treffer = [], 0
    for name, richtung in erwartet.items():
        s = reihen.get(name)
        if s is None or len(s) <= tage:
            zeilen.append({"name": name, "erwartet": richtung, "veraenderung": None, "passt": None})
            continue
        v = (float(s.iloc[-1]) / float(s.iloc[-tage - 1]) - 1) * 100
        passt = v < 0 if richtung == "fällt" else v > 0
        treffer += passt
        zeilen.append({"name": name, "erwartet": richtung, "veraenderung": v, "passt": passt})
    gueltig = sum(z["passt"] is not None for z in zeilen)
    if gueltig and treffer >= 4:
        urteil, stufe = "Muster eines Liquiditäts-Selloffs erkennbar", "hoch"
    elif gueltig and treffer == 3:
        urteil, stufe = "Teilweise Anzeichen von Liquiditätsstress", "mittel"
    else:
        urteil, stufe = "Kein Liquiditäts-Selloff-Muster", "tief"
    return {"zeilen": zeilen, "treffer": treffer, "von": gueltig, "urteil": urteil, "stufe": stufe, "tage": tage}


def perzentil(s: pd.Series, jahre: int = 3) -> float | None:
    """Wo liegt der letzte Wert im Vergleich zu den letzten `jahre` Jahren? (0 = Tiefst, 100 = Höchst)"""
    s = s.dropna()
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=jahre)]
    if len(s) < 10:
        return None
    return float((s < s.iloc[-1]).mean() * 100)


def jahresveraenderung(s: pd.Series) -> pd.Series:
    """Für Monatsdaten wie den Konsumentenpreisindex: Veränderung gegenüber Vorjahr in %."""
    return (s.pct_change(12) * 100).dropna()
