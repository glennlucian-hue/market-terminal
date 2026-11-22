"""Orderflow: Delta, CVD, Footprint (Bid × Ask), Big Trades, Stacked Imbalances.

Zwei Stufen, ehrlich gekennzeichnet:
  echt      Aus Einzel-Trades mit Aggressor-Seite (Export aus ATAS, Sierra Chart, Bookmap, Databento, Rithmic …).
            Spalten: zeit, preis, menge, seite ("ask" = Käufer greift an, "bid" = Verkäufer greift an).
  Schätzung Ohne Trades: Delta je Kerze aus der Lage des Schlusskurses in der Spanne (Close Location Value).
            Das ist nur eine grobe Annäherung, keine echte Orderflow-Information.
Heatmap (ruhende Limit-Orders im Orderbuch) braucht Markttiefe (Level 2) und ist hier nicht abgebildet.
"""
import numpy as np
import pandas as pd


def delta_je_kerze(df: pd.DataFrame) -> tuple[pd.Series, str]:
    """Delta je Kerze. Hat der DataFrame eine Spalte 'Delta' (z. B. aus einem Footprint-Export), wird sie genutzt."""
    if "Delta" in df.columns and df["Delta"].notna().any():
        return df["Delta"].fillna(0.0).astype(float), "echt"
    spanne = (df["High"] - df["Low"]).replace(0, np.nan)
    clv = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / spanne
    return (clv.fillna(0.0) * df["Volume"].fillna(0.0)).astype(float), "schaetzung"


def cvd(df: pd.DataFrame, reset_taeglich: bool = False) -> tuple[pd.Series, str]:
    """Kumuliertes Delta (Cumulative Volume Delta)."""
    d, art = delta_je_kerze(df)
    if reset_taeglich and isinstance(df.index, pd.DatetimeIndex):
        return d.groupby(df.index.date).cumsum(), art
    return d.cumsum(), art


def cvd_divergenz(cvd_reihe: pd.Series, preis_alt_idx: int, preis_neu_idx: int, richtung: str) -> bool:
    """Absorption beim Sweep: Preis macht ein tieferes Tief (Long), CVD aber ein höheres Tief – Verkäufer drücken,
    kommen aber nicht weiter. Für Short spiegelbildlich (höheres Hoch, tieferes CVD)."""
    alt, neu = float(cvd_reihe.iloc[preis_alt_idx]), float(cvd_reihe.iloc[preis_neu_idx])
    return neu > alt if richtung == "long" else neu < alt


# ---- echte Orderflow-Daten aus Einzel-Trades --------------------------------------------------------------

def lade_trades_csv(pfad: str, zeitzone: str = "America/New_York") -> pd.DataFrame:
    """Liest einen Trade-Export (zeit, preis, menge, seite). 'seite' darf ask/bid, buy/sell oder B/S sein."""
    t = pd.read_csv(pfad)
    t.columns = [s.strip().lower() for s in t.columns]
    t["zeit"] = pd.to_datetime(t["zeit"], utc=True).dt.tz_convert(zeitzone)
    t["seite"] = t["seite"].astype(str).str.lower().map(
        {"ask": "ask", "buy": "ask", "b": "ask", "a": "ask", "bid": "bid", "sell": "bid", "s": "bid"})
    return t.dropna(subset=["seite"]).sort_values("zeit").reset_index(drop=True)


def kerzen_aus_trades(trades: pd.DataFrame, intervall: str = "5min") -> pd.DataFrame:
    """OHLCV + echtes Delta je Kerze."""
    t = trades.set_index("zeit")
    vorz = np.where(t["seite"] == "ask", 1.0, -1.0)
    k = t["preis"].resample(intervall).ohlc().rename(columns=str.title)
    k["Volume"] = t["menge"].resample(intervall).sum()
    k["Delta"] = pd.Series(vorz * t["menge"].to_numpy(), index=t.index).resample(intervall).sum()
    return k.dropna(subset=["Open"])


def footprint(trades: pd.DataFrame, tick: float, intervall: str = "5min") -> pd.DataFrame:
    """Footprint Bid × Ask: je Kerze und Preisstufe das Volumen der Verkäufer (bid) und Käufer (ask)."""
    t = trades.copy()
    t["kerze"] = t["zeit"].dt.floor(intervall)
    t["stufe"] = (t["preis"] / tick).round() * tick
    fp = t.pivot_table(index=["kerze", "stufe"], columns="seite", values="menge", aggfunc="sum", fill_value=0)
    for s in ("bid", "ask"):
        if s not in fp:
            fp[s] = 0
    fp = fp[["bid", "ask"]].astype(float)
    fp["delta"] = fp["ask"] - fp["bid"]
    return fp


def stacked_imbalances(fp: pd.DataFrame, verhaeltnis: float = 3.0, min_stapel: int = 3) -> list[dict]:
    """Diagonale Imbalances (Ask auf Stufe p gegen Bid auf Stufe p-1). Ab `min_stapel` übereinander = Zone."""
    zonen = []
    for kerze, g in fp.groupby(level=0):
        g = g.droplevel(0).sort_index()
        bid_darunter = g["bid"].shift(1)
        ask_darueber = g["ask"].shift(-1)
        kauf = (g["ask"] >= verhaeltnis * bid_darunter.clip(lower=1)) & (g["ask"] > 0)
        verkauf = (g["bid"] >= verhaeltnis * ask_darueber.clip(lower=1)) & (g["bid"] > 0)
        for maske, seite in ((kauf, "kauf"), (verkauf, "verkauf")):
            folge, start = 0, None
            stufen = list(g.index)
            for p, ja in zip(stufen, maske.to_numpy()):
                if ja:
                    folge, start = folge + 1, start if folge else p
                else:
                    if folge >= min_stapel:
                        zonen.append({"kerze": kerze, "seite": seite, "von": start, "bis": vorher, "stufen": folge})
                    folge = 0
                vorher = p
            if folge >= min_stapel:
                zonen.append({"kerze": kerze, "seite": seite, "von": start, "bis": vorher, "stufen": folge})
    return zonen


def grosse_trades(trades: pd.DataFrame, min_menge: float | None = None, quantil: float = 0.995) -> pd.DataFrame:
    """Big Trades: einzelne Abschlüsse ab `min_menge` (sonst ab dem 99.5-%-Quantil)."""
    grenze = min_menge if min_menge is not None else float(trades["menge"].quantile(quantil))
    return trades[trades["menge"] >= grenze]


def cluster_profil(trades: pd.DataFrame, tick: float) -> pd.DataFrame:
    """Cluster-/Volumenprofil über alle Trades: Volumen, Bid, Ask und Delta je Preisstufe."""
    t = trades.assign(stufe=(trades["preis"] / tick).round() * tick)
    p = t.pivot_table(index="stufe", columns="seite", values="menge", aggfunc="sum", fill_value=0)
    for s in ("bid", "ask"):
        if s not in p:
            p[s] = 0
    p["volumen"] = p["bid"] + p["ask"]
    p["delta"] = p["ask"] - p["bid"]
    return p.sort_index()
