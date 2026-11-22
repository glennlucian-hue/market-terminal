"""Break & Retest an Gamma-Wänden (Fortsetzung im negativen Gamma-Regime).

Short: Schluss unter einer Wand (Bruch), später berührt ein Hoch die Wand von unten (Retest) und die Kerze
schliesst wieder darunter, CVD fällt. Long spiegelbildlich. Nur unter Zero Gamma (Händler verstärken Bewegungen).
"""
from .ict import Liquiditaet, Setup


def setups(df, levels: list[float], zero_gamma: float | None, cvd, toleranz: float, max_warten: int = 24,
           cvd_kerzen: int = 12) -> list[Setup]:
    o, h, l, c = (df[s].to_numpy(dtype=float) for s in ("Open", "High", "Low", "Close"))
    gefunden, gebrochen = [], {}   # level -> (richtung, idx)
    for t in range(1, len(df)):
        if zero_gamma and c[t] >= zero_gamma:
            continue
        for lv in levels:
            if c[t - 1] >= lv > c[t]:
                gebrochen[lv] = ("short", t)
            elif c[t - 1] <= lv < c[t]:
                gebrochen[lv] = ("long", t)
            elif lv in gebrochen and 0 < t - gebrochen[lv][1] <= max_warten:
                r = gebrochen[lv][0]
                d = cvd.iloc[t] - cvd.iloc[max(0, t - cvd_kerzen)]
                if r == "short" and h[t] >= lv - toleranz and c[t] < lv and c[t] < o[t] and d < 0:
                    ziele = sorted([x for x in levels if x < c[t]], reverse=True)
                    gefunden.append(Setup(t, df.index[t], r, float(c[t]), float(h[t]), t,
                                          Liquiditaet(lv, "tief", "Gamma-Wand", t), lv, ziele))
                    del gebrochen[lv]
                elif r == "long" and l[t] <= lv + toleranz and c[t] > lv and c[t] > o[t] and d > 0:
                    ziele = sorted(x for x in levels if x > c[t])
                    gefunden.append(Setup(t, df.index[t], r, float(c[t]), float(l[t]), t,
                                          Liquiditaet(lv, "hoch", "Gamma-Wand", t), lv, ziele))
                    del gebrochen[lv]
    return gefunden
