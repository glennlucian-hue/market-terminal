"""Zwischenspeicher und Datenprotokoll.

Jede Datenabfrage läuft über `hole()`:
  1. Liegt eine frische Kopie im Ordner cache/?  -> diese verwenden (schnell).
  2. Sonst neu laden und im Cache ablegen.
  3. Klappt das Laden nicht, aber es gibt eine alte Kopie -> alte Kopie + Hinweis.
  4. Gibt es gar nichts -> Fehler (die Website zeigt dann "Daten nicht verfügbar").

Jeder Abruf wird im PROTOKOLL vermerkt (Seite "Datenstatus").
Den Ordner cache/ kann man jederzeit löschen; die Daten werden dann neu geladen.
"""
import json
import re
import threading
from datetime import datetime, timedelta

import pandas as pd

from .konfiguration import CACHE_ORDNER

PROTOKOLL: list[dict] = []
_sperre = threading.Lock()
NEU_LADEN = False  # wird von main.py bei --neu-laden auf True gesetzt


class DatenFehler(Exception):
    """Daten konnten nicht geladen werden."""


def _pfad(schluessel: str, endung: str):
    return CACHE_ORDNER / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', schluessel)}.{endung}"


def _lesen(schluessel: str):
    meta_pfad = _pfad(schluessel, "meta.json")
    if not meta_pfad.exists():
        return None
    try:
        meta = json.loads(meta_pfad.read_text(encoding="utf-8"))
        if meta["format"] == "reihe":
            wert = pd.read_csv(_pfad(schluessel, "csv"), index_col=0, parse_dates=True).iloc[:, 0]
        elif meta["format"] == "tabelle":
            wert = pd.read_csv(_pfad(schluessel, "csv"), index_col=0, parse_dates=True)
        else:
            wert = json.loads(_pfad(schluessel, "json").read_text(encoding="utf-8"))
        return wert, meta
    except Exception:
        return None  # kaputte Cache-Datei: wie "nicht vorhanden" behandeln


def _schreiben(schluessel: str, wert, zusatz: dict) -> None:
    CACHE_ORDNER.mkdir(exist_ok=True)
    if isinstance(wert, pd.Series):
        fmt = "reihe"
        wert.to_csv(_pfad(schluessel, "csv"))
    elif isinstance(wert, pd.DataFrame):
        fmt = "tabelle"
        wert.to_csv(_pfad(schluessel, "csv"))
    else:
        fmt = "json"
        _pfad(schluessel, "json").write_text(json.dumps(wert, ensure_ascii=False, default=str), encoding="utf-8")
    meta = {"format": fmt, "abgerufen": datetime.now().isoformat(timespec="seconds"), **zusatz}
    _pfad(schluessel, "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def _protokolliere(quelle, schluessel, status, meldung=""):
    with _sperre:
        PROTOKOLL.append({"quelle": quelle, "schluessel": schluessel, "status": status,
                          "meldung": meldung, "zeit": datetime.now().strftime("%H:%M:%S")})


def hole(schluessel: str, quelle: str, max_stunden: float, laden, zusatz=None):
    """Gibt (wert, meta) zurück. `laden` ist eine Funktion ohne Argumente, die die Daten frisch holt.

    meta enthält 'abgerufen' und ggf. 'hinweis' (wenn alte Daten verwendet werden).
    """
    vorhanden = _lesen(schluessel)
    if vorhanden and not NEU_LADEN:
        wert, meta = vorhanden
        if datetime.now() - datetime.fromisoformat(meta["abgerufen"]) < timedelta(hours=max_stunden):
            _protokolliere(quelle, schluessel, "cache")
            return wert, meta
    try:
        wert = laden()
        _schreiben(schluessel, wert, zusatz or {})
        _protokolliere(quelle, schluessel, "ok")
        return wert, {"abgerufen": datetime.now().isoformat(timespec="seconds"), **(zusatz or {})}
    except Exception as fehler:
        if vorhanden:
            wert, meta = vorhanden
            meta = {**meta, "hinweis": f"Neu laden fehlgeschlagen – Daten vom {meta['abgerufen'][:16].replace('T', ' ')}"}
            _protokolliere(quelle, schluessel, "alt", f"{fehler}")
            return wert, meta
        _protokolliere(quelle, schluessel, "fehler", f"{fehler}")
        if isinstance(fehler, DatenFehler):
            raise
        raise DatenFehler(f"{quelle}: {fehler}") from fehler
