"""
Signal-Bot – Startprogramm (nur Vorschläge, keine Ausführung).

Benutzung:
    python bot_signale.py                           -> aktuelle Lage und Signale von heute (MNQ auf NQ=F, 5 Min.)
    python bot_signale.py --backtest --tage 55      -> Backtest über die letzten 55 Tage
    python bot_signale.py --symbol QQQ --instrument QQQ --konto 5000
    python bot_signale.py --ohne-makro              -> Makro-Filter aus (zum Vergleich im Backtest)
    python bot_signale.py --live 5                  -> Papier-Betrieb: alle 5 Min., Journal + Telegram
Not-Aus: Datei NOTAUS im Projektordner anlegen.
"""
import argparse
import sys
import time

import pandas as pd

from bot import backtest, daten, journal, retest, ict, makro, orderflow, signale, tpo
from bot.risiko_regeln import INSTRUMENTE, Regeln, RisikoWaechter


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="ICT + Orderflow + Makro Signal-Bot (nur Vorschläge)")
    p.add_argument("--symbol", default="NQ=F")
    p.add_argument("--instrument", default="MNQ", choices=sorted(INSTRUMENTE))
    p.add_argument("--intervall", default="5m")
    p.add_argument("--tage", type=int, default=10)
    p.add_argument("--konto", type=float, default=10_000)
    p.add_argument("--risiko", type=float, default=0.01, help="Risiko je Trade als Anteil (0.01 = 1 %%)")
    p.add_argument("--min-rr", type=float, default=2.0)
    p.add_argument("--wände", default="", help="eigene Gamma-Wände im Kurs des Symbols, z. B. 26173,25967,25761")
    p.add_argument("--gex", default="NDX", help="GEXBot-Ticker (nur mit GEXBOT_API_KEY)")
    p.add_argument("--backtest", action="store_true")
    p.add_argument("--ohne-makro", action="store_true")
    p.add_argument("--live", type=int, default=0, metavar="MIN", help="alle MIN Minuten neu prüfen, neue Signale ins Journal")
    a = p.parse_args()

    try:
        from terminal.konfiguration import lade_env
        lade_env()
    except Exception:
        pass

    regeln = Regeln(konto=a.konto, risiko_pro_trade=a.risiko, min_rr=a.min_rr)
    gesehen = set()
    while True:
        print(f"Lade {a.symbol} ({a.intervall}, {a.tage} Tage) ...")
        try:
            df = daten.kerzen(a.symbol, a.intervall, a.tage)
        except Exception as e:
            if not a.live:
                raise
            print(f"  Daten fehlen ({e}), neuer Versuch später")
            time.sleep(a.live * 60)
            continue
        reihen = {} if a.ohne_makro else daten.makro_reihen(a.intervall, a.tage)
        gex, gex_hinweis = daten.gex_levels(a.gex)
        if gex_hinweis:
            print(f"  Hinweis: {gex_hinweis}")

        if a.backtest:
            e = backtest.lauf(df, a.instrument, regeln, reihen, None, mit_makro=not a.ohne_makro)
            print("\nBACKTEST (Kerzen, vorsichtige Annahmen – kein Beweis):")
            for k, v in e.kennzahlen().items():
                print(f"  {k:15} {v}")
            print("  abgelehnte Setups:", dict(sorted(e.abgelehnt.items(), key=lambda x: -x[1])))
            if e.trades:
                print("\n" + pd.DataFrame(e.trades).tail(15).to_string(index=False))
            return 0

        jetzt = df.index[-1]
        lage = None if a.ohne_makro else makro.bewerte(jetzt, {"basis": df["Close"], **reihen})
        if lage:
            print(f"\nMAKRO {lage.bias.upper()} ({lage.punkte:+.1f}), Grössenfaktor {lage.groessen_faktor}")
            for g in lage.gruende:
                print(f"  · {g}")
            for h in lage.hinweise:
                print(f"  ? {h}")
            print(f"  Werte: {lage.werte}")
        profil = tpo.vortages_profil(df, jetzt, INSTRUMENTE[a.instrument]["tick"])
        if profil:
            print(f"\nTPO Vortag: POC {profil['poc']:.2f} · VAH {profil['vah']:.2f} · VAL {profil['val']:.2f}"
                  f"{' · Poor High' if profil['poor_high'] else ''}{' · Poor Low' if profil['poor_low'] else ''}")
        if gex:
            print(f"GEX {a.gex}: Zero Gamma {gex.get('zero_gamma')} · Call-Wand {gex.get('major_pos')} · "
                  f"Put-Wand {gex.get('major_neg')}")

        cvd_reihe, cvd_art = orderflow.cvd(df)
        waechter = RisikoWaechter(regeln)
        # Gamma-Wände: eigene Liste oder GEXBot; GEX-Kurse (z. B. QQQ/NDX) aufs Symbol umrechnen
        faktor = float(df["Close"].iloc[-1]) / gex["spot"] if gex and gex.get("spot") else 1.0
        waende = [float(x) for x in a.wände.split(",") if x] or \
                 [gex[k] * faktor for k in ("major_pos", "major_neg") if gex and gex.get(k)]
        zg = gex["zero_gamma"] * faktor if gex and gex.get("zero_gamma") else None
        if gex and faktor != 1.0:
            gex = {**gex, **{k: gex[k] * faktor for k in ("spot", "zero_gamma", "major_pos", "major_neg") if gex.get(k)}}
        tol = 4 * INSTRUMENTE[a.instrument]["tick"] * (10 if a.instrument in ("NQ", "MNQ") else 1)
        alle = ict.setups(df) + (retest.setups(df, waende, zg, cvd_reihe, tol) if waende else [])
        heute = sorted((s for s in alle if s.zeit.date() == jetzt.date()), key=lambda s: s.idx)
        print(f"\nSETUPS HEUTE ({jetzt:%d.%m.%Y}, CVD: {cvd_art}): {len(heute)}")
        for s in heute:
            sig, grund = signale.bewerte(s, df, a.instrument, waechter, lage, profil, gex, cvd_reihe, cvd_art)
            if sig:
                print("\n" + sig.text(a.instrument))
                if a.live and sig.zeit not in gesehen:
                    gesehen.add(sig.zeit)
                    journal.melde(sig, a.instrument)
            else:
                print(f"  {s.zeit:%H:%M} {s.richtung:5} verworfen: {grund}")
        print("\nNur Vorschläge, keine Anlageberatung. Daten verzögert. Erst im Papier-Konto prüfen.")
        if not a.live:
            return 0
        time.sleep(a.live * 60)


if __name__ == "__main__":
    sys.exit(main())
