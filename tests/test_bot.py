"""Tests der Bot-Bausteine mit konstruierten Daten (kein Netz nötig).  Start: python -m pytest tests"""
import numpy as np
import pandas as pd
import pytest

from bot import backtest, ict, makro, orderflow, signale, tpo
from bot.risiko_regeln import Regeln, RisikoWaechter


def kerzen(reihe, start="2026-11-17 09:30", freq="5min"):
    """reihe: Liste (open, high, low, close)."""
    idx = pd.date_range(start, periods=len(reihe), freq=freq, tz="America/New_York")
    df = pd.DataFrame(reihe, columns=["Open", "High", "Low", "Close"], index=idx)
    df["Volume"] = 1000.0
    return df


def long_setup_reihe():
    return [
        (105, 106, 104, 105),     # 0
        (105, 105.5, 103, 104),   # 1
        (104, 104.5, 100, 101),   # 2  Swing-Tief 100
        (101, 103, 100.5, 102.5), # 3
        (102.5, 104, 102, 103.5), # 4  -> Swing bei 2 bestätigt (rechts=2)
        (103.5, 104, 102, 102.5), # 5  Abwärtsserie beginnt (Open 103.5)
        (102.5, 102.8, 101, 101.2),  # 6
        (101.2, 101.5, 99, 99.5), # 7  Sweep unter 100
        (99.5, 103.8, 99.4, 103.7),  # 8  Schluss über 103.5 = CISD
        (103.7, 104, 103, 103.5), # 9
    ]


def test_turtle_soup_mit_cisd_long():
    df = kerzen(long_setup_reihe())
    s = ict.setups(df, links=2, rechts=2, vortag=False)
    assert len(s) == 1
    s = s[0]
    assert (s.richtung, s.idx, s.extrem, s.cisd_level, s.sweep.preis) == ("long", 8, 99, 103.5, 100)


def test_kein_cisd_ohne_schluss_ueber_serie():
    reihe = long_setup_reihe()[:8] + [(99.5, 103.4, 99.4, 103.3), (103.3, 103.4, 102, 102.2)]
    assert ict.setups(kerzen(reihe), links=2, rechts=2, vortag=False) == []


def test_short_spiegelbildlich():
    gespiegelt = [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in long_setup_reihe()]
    s = ict.setups(kerzen(gespiegelt), links=2, rechts=2, vortag=False)
    assert len(s) == 1 and s[0].richtung == "short" and s[0].extrem == 101 and s[0].cisd_level == 96.5


def test_tpo_poc_und_value_area():
    # vier 30-Min-Perioden; 100–101 wird von allen berührt
    idx = pd.date_range("2026-11-17 09:30", periods=4, freq="30min", tz="America/New_York")
    df = pd.DataFrame({"High": [102, 101, 101, 104], "Low": [99, 100, 98, 100]}, index=idx)
    p = tpo.tpo_profil(df, tick=1.0)
    assert p["poc"] in (100, 101) and p["val"] <= p["poc"] <= p["vah"]
    assert p["hoch"] == 104 and p["tief"] == 98 and p["ib_hoch"] == 102 and p["ib_tief"] == 99
    assert 103 in p["single_prints"]


def test_cvd_schaetzung_und_echt():
    df = kerzen([(100, 101, 99, 101), (101, 101, 99, 99)])
    c, art = orderflow.cvd(df)
    assert art == "schaetzung" and list(c) == [1000, 0]
    df["Delta"] = [50, -20]
    c, art = orderflow.cvd(df)
    assert art == "echt" and list(c) == [50, 30]


def test_footprint_und_stacked_imbalance():
    zeit = pd.Timestamp("2026-11-17 10:00", tz="America/New_York")
    zeilen = []
    for p in (100.0, 100.25, 100.5, 100.75):
        zeilen += [(zeit, p, 30, "ask"), (zeit, p, 2, "bid")]
    t = pd.DataFrame(zeilen, columns=["zeit", "preis", "menge", "seite"])
    fp = orderflow.footprint(t, tick=0.25)
    assert fp["delta"].sum() == 4 * 28
    zonen = orderflow.stacked_imbalances(fp, verhaeltnis=3, min_stapel=3)
    assert zonen and zonen[0]["seite"] == "kauf" and zonen[0]["stufen"] == 3
    assert len(orderflow.grosse_trades(t, min_menge=30)) == 4
    k = orderflow.kerzen_aus_trades(t)
    assert float(k["Delta"].iloc[0]) == 112


def test_positionsgroesse_und_grenzen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    w = RisikoWaechter(Regeln(konto=10_000, risiko_pro_trade=0.01, max_kontrakte=5))
    g = w.positionsgroesse(20_000, 19_990, "MNQ")      # 10 Pkt × 2 USD = 20 USD je Kontrakt, Budget 100
    assert g["stueck"] == 5 and g["risiko"] == 100
    assert w.positionsgroesse(20_000, 19_900, "MNQ")["stueck"] == 0   # 200 USD je Kontrakt > Budget
    tag = pd.Timestamp("2026-11-17").date()
    assert w.erlaubt(tag)[0]
    w.buche(tag, -100)
    w.buche(tag, -100)
    assert not w.erlaubt(tag)[0]                         # zwei Verluste in Folge
    assert w.erlaubt(pd.Timestamp("2026-11-18").date())[0]   # neuer Tag
    (tmp_path / "NOTAUS").write_text("")
    assert w.erlaubt(pd.Timestamp("2026-11-18").date()) == (False, "Not-Aus aktiv (Datei NOTAUS vorhanden)")


def test_makro_bias():
    idx = pd.date_range("2026-11-16 09:30", periods=200, freq="5min", tz="America/New_York")
    t = idx[-1]
    stress = makro.bewerte(t, {"vix": pd.Series(20.0, idx), "vix9d": pd.Series(23.0, idx),
                              "us10y": pd.Series(np.r_[np.full(100, 4.0), np.full(100, 4.1)], idx)})
    assert stress.bias == "short" and stress.punkte <= -1.5
    ruhig = makro.bewerte(t, {"vix": pd.Series(20.0, idx), "vix9d": pd.Series(16.0, idx),
                             "tick": pd.Series(500.0, idx)})
    assert ruhig.bias == "long"


def test_signal_aus_setup():
    reihe = long_setup_reihe() + [(103.5, 104, 103, 103.6)]
    df = kerzen(reihe)
    s = ict.setups(df, links=2, rechts=2, vortag=False)[0]
    s.gegenseite = [106, 120]
    w = RisikoWaechter(Regeln(konto=10_000, stop_puffer_ticks=4))
    sig, grund = signale.bewerte(s, df, "QQQ", w, kill_zones=None)
    assert grund == "" and sig.stop == pytest.approx(98.96) and sig.ziel == 120
    assert sig.stueck == int(100 / (103.7 - 98.96))
    gegen = makro.MakroLage(punkte=-3, bias="short")
    assert signale.bewerte(s, df, "QQQ", w, gegen, kill_zones=None)[0] is None


def test_backtest_laeuft_auf_zufallsdaten():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2026-10-01", "2026-10-20", freq="5min", tz="America/New_York")
    idx = idx[(idx.time >= pd.Timestamp("09:30").time()) & (idx.time < pd.Timestamp("16:00").time())]
    c = 400 + np.cumsum(rng.normal(0, 0.4, len(idx)))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"Open": o, "Close": c, "High": np.maximum(o, c) + rng.random(len(c)) * 0.3,
                       "Low": np.minimum(o, c) - rng.random(len(c)) * 0.3, "Volume": 1e5}, index=idx)
    e = backtest.lauf(df, "QQQ", mit_makro=False)
    k = e.kennzahlen()
    assert k["trades"] == len(e.trades) and all(t["grund"] in ("Stop", "Ziel", "Zeit", "Datenende") for t in e.trades)


def test_break_und_retest_short():
    from bot import retest
    df = kerzen([(102, 102.5, 101, 101.5), (101.5, 101.6, 99, 99.2), (99.2, 99.5, 98.5, 99),
                 (99, 100.1, 98.8, 99.3), (99.3, 99.4, 97, 97.5)])
    cvd = pd.Series([0, -5, -8, -9, -15], index=df.index)
    s = retest.setups(df, [100, 95], zero_gamma=105, cvd=cvd, toleranz=0.2)
    assert len(s) == 1 and s[0].richtung == "short" and s[0].idx == 3 and s[0].gegenseite == [95]
