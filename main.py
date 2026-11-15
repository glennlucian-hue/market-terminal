"""
Market Terminal – Startprogramm.

Benutzung (in der Eingabeaufforderung, im Projektordner):
    python main.py                 -> Website aktualisieren und im Browser öffnen
    python main.py --neu-laden     -> Zwischenspeicher ignorieren, alles frisch laden
    python main.py --nicht-oeffnen -> nur aktualisieren, Browser nicht öffnen (für den automatischen Start)
"""
import argparse
import sys
import time
import webbrowser

from terminal import cache
from terminal.konfiguration import KonfigFehler, lade_env, lade_themen, lade_watchlist
from terminal.website import baue_website


def main() -> int:
    # Windows-Konsole: Umlaute und Sonderzeichen korrekt anzeigen
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Aktualisiert die Market-Terminal-Website.")
    parser.add_argument("--neu-laden", action="store_true", help="Zwischenspeicher ignorieren und alles neu laden")
    parser.add_argument("--nicht-oeffnen", action="store_true", help="Website nicht automatisch im Browser öffnen")
    args = parser.parse_args()

    lade_env()
    cache.NEU_LADEN = args.neu_laden
    try:
        watchlist, themen = lade_watchlist(), lade_themen()
    except KonfigFehler as e:
        print(f"\nPROBLEM MIT EINER KONFIGURATIONSDATEI:\n  {e}\n")
        return 1

    start = time.time()
    print("Market Terminal wird aktualisiert ...")
    startseite = baue_website(watchlist, themen, melde=lambda *a, **k: print(*a, **k, flush=True))
    fehler = sum(1 for p in cache.PROTOKOLL if p["status"] == "fehler")
    print(f"\nFertig in {time.time() - start:.0f} Sekunden.", f"({fehler} Datenquelle(n) mit Fehler – siehe Seite 'Datenstatus')" if fehler else "")
    print(f"Website: {startseite}\n")
    if not args.nicht_oeffnen:
        webbrowser.open(startseite.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
