"""Schlüssel-Test: probiert jede Datenquelle mit einer kleinen Abfrage aus.

Aufruf:  python -m kern.pruefung
Ausgabe: Tabelle in der Konsole, Datei cache/kern/pruefung.json und – auf GitHub – Hinweise ("Annotations"),
         die man ohne Anmeldung sehen kann. Schlüssel werden NIE ausgegeben, nur ok/Fehler.
"""
import json
import os
import sys

from .datenpunkt import jetzt_utc
from .kurse import kurs
from .provider import ALLE
from .provider.basis import CACHE_ORDNER


def _kurz(daten) -> str:
    if isinstance(daten, dict):
        teile = [f"{k}={v}" for k, v in daten.items() if not isinstance(v, (dict, list))][:3]
        return ", ".join(teile)
    if isinstance(daten, list):
        return f"{len(daten)} Einträge"
    return ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    auf_github = os.getenv("GITHUB_ACTIONS") == "true"
    ergebnisse = []
    for klasse in ALLE:
        p = klasse()
        e = p.pruefen()
        zeile = {"quelle": p.anzeige, "schluessel_noetig": bool(p.schluessel_env),
                 "schluessel_vorhanden": bool(p.schluessel) if p.schluessel_env else None,
                 "ok": e.ok, "grund": e.grund, "probe": _kurz(e.daten) if e.ok else ""}
        ergebnisse.append(zeile)
        symbol = "OK " if e.ok else "XX "
        print(f"{symbol} {p.anzeige:<26} {('Probe: ' + zeile['probe']) if e.ok else e.grund}")
        if auf_github:
            art = "notice" if e.ok else "warning"
            text = ("funktioniert – " + zeile["probe"]) if e.ok else e.grund
            print(f"::{art} title=Datenquelle {p.anzeige}::{text}")

    # Ersatzkette testen: ein US-Wert und ein Schweizer Wert
    for symbol in ("NVDA", "NESN.SW"):
        k = kurs(symbol)
        weg = " -> ".join(f"{v['quelle']}:{'ok' if v['ok'] else 'nein'}" for v in k["versuche"])
        print(f"{'OK ' if k['ok'] else 'XX '} Kurs {symbol:<9} via {k['quelle']} ({weg})")
        if auf_github:
            print(f"::notice title=Kurs {symbol}::Quelle {k['quelle']} · Kette {weg}")

    # Probe: welche FMP-Endpunkte liefert der Gratis-Plan? (nur Status + Anzahl, keine Schlüssel)
    from .provider import FMP
    fmp = FMP()
    zusammen = []
    for pfad, symbol in (("price-target-consensus", "NVDA"), ("price-target-summary", "NVDA"), ("grades", "NVDA"),
                         ("price-target-news", "NVDA"), ("ratios-ttm", "NESN.SW"), ("ratios-ttm", "MC.PA"),
                         ("profile", "NESN.SW"), ("analyst-estimates", "NVDA")):
        params = {"symbol": symbol}
        if pfad == "analyst-estimates":
            params["period"] = "annual"
        e = fmp.abfrage(f"{fmp.BASIS}/{pfad}", params, art="schaetzung")
        n = len(e.daten) if e.ok and isinstance(e.daten, list) else (1 if e.ok and e.daten else 0)
        felder = ",".join(list(e.daten[0])[:8]) if e.ok and isinstance(e.daten, list) and e.daten else ""
        text = f"{pfad} {symbol}: " + (f"ok, {n} Einträge, Felder {felder}" if e.ok and n else (e.grund or "leer"))
        print(text)
        zusammen.append(f"{pfad}/{symbol}=" + (f"ok({n})" if e.ok and n else (e.grund or "leer")[:40]))
    if auf_github:   # GitHub zeigt max. 10 Hinweise pro Schritt -> alles in einem Hinweis
        print(f"::warning title=FMP-Probe::{' | '.join(zusammen)}")

    CACHE_ORDNER.mkdir(parents=True, exist_ok=True)
    (CACHE_ORDNER / "pruefung.json").write_text(json.dumps(
        {"zeit": jetzt_utc().isoformat(), "ergebnisse": ergebnisse}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
