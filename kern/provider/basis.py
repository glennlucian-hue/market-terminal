"""Gemeinsame Grundlage aller Datenquellen: Schlüssel, Ratenbegrenzung, Wiederholungen, Cache.

Jeder Provider erbt von `Provider` und definiert nur noch seine Endpunkte.
"""
import json
import os
import random
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from ..datenpunkt import Ergebnis

CACHE_ORDNER = Path(__file__).resolve().parents[2] / "cache" / "kern"


class Ratenbegrenzer:
    """Begrenzt Abfragen pro Minute (gleitend) und pro Tag (Zähler in einer Datei, überlebt Neustarts via Cache)."""

    def __init__(self, name: str, pro_minute: int | None, pro_tag: int | None):
        self.name, self.pro_minute, self.pro_tag = name, pro_minute, pro_tag
        self._zeiten: list[float] = []
        self._sperre = threading.Lock()
        self._datei = CACHE_ORDNER / f"limit_{name}.json"

    def _tageszaehler(self) -> dict:
        try:
            d = json.loads(self._datei.read_text())
            return d if d.get("tag") == date.today().isoformat() else {"tag": date.today().isoformat(), "anzahl": 0}
        except Exception:
            return {"tag": date.today().isoformat(), "anzahl": 0}

    def tag_rest(self) -> int | None:
        return None if self.pro_tag is None else self.pro_tag - self._tageszaehler()["anzahl"]

    def anfordern(self) -> bool:
        """True = Abfrage erlaubt (und gezählt). False = Tageslimit erreicht. Wartet ggf. für das Minutenlimit."""
        with self._sperre:
            if self.pro_tag is not None:
                z = self._tageszaehler()
                if z["anzahl"] >= self.pro_tag:
                    return False
            if self.pro_minute:
                while True:
                    jetzt = time.monotonic()
                    self._zeiten = [t for t in self._zeiten if jetzt - t < 60]
                    if len(self._zeiten) < self.pro_minute:
                        break
                    time.sleep(max(0.05, 60 - (jetzt - self._zeiten[0])))
                self._zeiten.append(time.monotonic())
            if self.pro_tag is not None:
                z["anzahl"] += 1
                CACHE_ORDNER.mkdir(parents=True, exist_ok=True)
                self._datei.write_text(json.dumps(z))
            return True


class Provider:
    name = "basis"
    anzeige = "Basis"
    schluessel_env: str | None = None      # Name der Umgebungsvariable, None = kein Schlüssel nötig
    pro_minute: int | None = None
    pro_tag: int | None = None

    def __init__(self):
        self.begrenzer = Ratenbegrenzer(self.name, self.pro_minute, self.pro_tag)

    # --- Schlüssel --------------------------------------------------------------
    @property
    def schluessel(self) -> str | None:
        if not self.schluessel_env:
            return None
        return (os.getenv(self.schluessel_env) or "").strip() or None

    def bereit(self) -> tuple[bool, str]:
        if self.schluessel_env and not self.schluessel:
            return False, f"kein Schlüssel ({self.schluessel_env} fehlt)"
        return True, ""

    # Unterklassen können Schlüssel als Header oder Parameter anhängen
    def _auth(self, headers: dict, params: dict) -> None:
        pass

    # --- Abfrage mit Cache, Limit und Wiederholungen -----------------------------
    def abfrage(self, url: str, params: dict | None = None, *, cache_minuten: float = 0, art: str | None = None,
                cache_name: str | None = None) -> Ergebnis:
        params = dict(params or {})
        ok, grund = self.bereit()
        if not ok:
            return Ergebnis(self.name, False, grund=grund)

        cache_datei = None
        if cache_minuten and cache_name:
            cache_datei = CACHE_ORDNER / f"{self.name}_{cache_name}.json"
            try:
                roh = json.loads(cache_datei.read_text())
                alter = datetime.now() - datetime.fromisoformat(roh["gespeichert"])
                if alter < timedelta(minutes=cache_minuten):
                    return Ergebnis(self.name, True, daten=roh["daten"], art=art, grund="aus Cache")
            except Exception:
                pass

        if not self.begrenzer.anfordern():
            return Ergebnis(self.name, False, grund=f"Tageslimit von {self.pro_tag} Abfragen erreicht")

        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        self._auth(headers, params)
        letzter_fehler = ""
        for versuch in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
            except requests.RequestException as e:
                letzter_fehler = f"Verbindung fehlgeschlagen ({type(e).__name__})"
            else:
                if r.status_code == 429:              # Limit beim Anbieter: warten und erneut versuchen
                    letzter_fehler = "HTTP 429 (Limit beim Anbieter)"
                    time.sleep(float(r.headers.get("Retry-After", 2 + versuch * 3)) + random.random())
                    continue
                if r.status_code in (401, 403):
                    return Ergebnis(self.name, False, grund=f"HTTP {r.status_code} – Schlüssel ungültig oder Endpunkt nicht im Gratis-Plan")
                if r.status_code >= 500:
                    letzter_fehler = f"HTTP {r.status_code} (Störung beim Anbieter)"
                    time.sleep(1 + versuch * 2)
                    continue
                if r.status_code >= 400:
                    return Ergebnis(self.name, False, grund=f"HTTP {r.status_code}: {r.text[:120]}")
                try:
                    daten = r.json()
                except ValueError:
                    return Ergebnis(self.name, False, grund="Antwort ist kein JSON")
                fehler = self.fehler_in_antwort(daten)
                if fehler:
                    return Ergebnis(self.name, False, grund=fehler)
                if cache_datei:
                    CACHE_ORDNER.mkdir(parents=True, exist_ok=True)
                    cache_datei.write_text(json.dumps({"gespeichert": datetime.now().isoformat(), "daten": daten}))
                return Ergebnis(self.name, True, daten=daten, art=art)
            time.sleep(1 + versuch)
        return Ergebnis(self.name, False, grund=letzter_fehler or "unbekannter Fehler")

    def fehler_in_antwort(self, daten) -> str:
        """Manche Anbieter melden Fehler mit HTTP 200 im Text. Unterklassen prüfen das hier."""
        return ""

    def pruefen(self) -> Ergebnis:
        """Kleine Test-Abfrage für den Schlüssel-Test. Muss von Unterklassen überschrieben werden."""
        raise NotImplementedError
