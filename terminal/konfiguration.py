"""Liest die Watchlist (watchlist.yaml), die Themen (themen.yaml) und die Schlüssel (.env)."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJEKT = Path(__file__).resolve().parent.parent
WATCHLIST_DATEI = PROJEKT / "watchlist.yaml"
THEMEN_DATEI = PROJEKT / "themen.yaml"
CACHE_ORDNER = PROJEKT / "cache"
WEBSITE_ORDNER = PROJEKT / "website"
VORLAGEN_ORDNER = PROJEKT / "vorlagen"


class KonfigFehler(Exception):
    """Eine Konfigurationsdatei ist fehlerhaft. Die Meldung erklärt, was zu tun ist."""


def lade_env() -> None:
    """Lädt die Schlüssel aus .env in die Umgebung (falls die Datei existiert)."""
    load_dotenv(PROJEKT / ".env")


def _lies_yaml(pfad: Path) -> dict:
    if not pfad.exists():
        raise KonfigFehler(f"Die Datei {pfad.name} wurde nicht gefunden (erwartet in {pfad.parent}).")
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        zeile = getattr(getattr(e, "problem_mark", None), "line", None)
        wo = f" in Zeile {zeile + 1}" if zeile is not None else ""
        raise KonfigFehler(
            f"{pfad.name} ist nicht lesbar{wo}. Meist ist die Einrückung falsch "
            f"oder ein Tabulator statt Leerzeichen verwendet. Details: {e}"
        ) from e
    if not isinstance(daten, dict):
        raise KonfigFehler(f"{pfad.name} ist leer oder hat ein unerwartetes Format.")
    return daten


def _portfolio_gruppen() -> list:
    """Private Portfolio-Gruppen: aus dem GitHub-Secret WATCHLIST_PORTFOLIO oder der lokalen Datei
    watchlist_portfolio.yaml (wird nie hochgeladen). Fehlt beides, gibt es keine Portfolio-Gruppe."""
    text = os.getenv("WATCHLIST_PORTFOLIO", "").strip()
    pfad = PROJEKT / "watchlist_portfolio.yaml"
    if not text and pfad.exists():
        text = pfad.read_text(encoding="utf-8")
    if not text:
        return []
    try:
        daten = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise KonfigFehler(f"Portfolio-Watchlist (watchlist_portfolio.yaml bzw. Secret) ist nicht lesbar: {e}") from e
    return daten.get("gruppen", []) if isinstance(daten, dict) else []


def lade_watchlist(pfad: Path = WATCHLIST_DATEI) -> dict:
    daten = _lies_yaml(pfad)
    if not isinstance(daten.get("gruppen"), list):
        raise KonfigFehler("watchlist.yaml braucht einen Abschnitt 'gruppen:' mit einer Liste von Gruppen.")
    privat = _portfolio_gruppen()
    if privat:
        stelle = next((i for i, g in enumerate(daten["gruppen"]) if g.get("name") == "Favoriten"), len(daten["gruppen"]))
        daten["gruppen"][stelle:stelle] = privat
    for g in daten["gruppen"]:
        if not g.get("name") or not isinstance(g.get("werte"), list):
            raise KonfigFehler(f"Jede Gruppe braucht 'name:' und 'werte:'. Problem bei: {g}")
        for w in g["werte"]:
            if not w.get("name") or not w.get("ticker"):
                raise KonfigFehler(f"Jeder Wert braucht 'name:' und 'ticker:'. Problem bei: {w}")
            w["ticker"] = str(w["ticker"]).strip()
            w.setdefault("art", "preis")
            w.setdefault("quelle", "yahoo")
            w.setdefault("band", False)
            if w["quelle"] not in ("yahoo", "fred"):
                raise KonfigFehler(f"'quelle:' muss yahoo oder fred sein. Problem bei: {w['name']}")
        g.setdefault("aktien", False)
    daten.setdefault("einstellungen", {})
    daten["einstellungen"].setdefault("cache_stunden", 4)
    return daten


def lade_themen(pfad: Path = THEMEN_DATEI) -> list[dict]:
    daten = _lies_yaml(pfad)
    themen = daten.get("themen")
    if not isinstance(themen, list):
        raise KonfigFehler("themen.yaml braucht einen Abschnitt 'themen:' mit einer Liste.")
    for t in themen:
        if not t.get("id") or not t.get("titel"):
            raise KonfigFehler(f"Jedes Thema braucht 'id:' und 'titel:'. Problem bei: {t}")
        t.setdefault("beschreibung", "")
        t.setdefault("suchbegriffe", [])
        t.setdefault("analyse", None)
    return themen
