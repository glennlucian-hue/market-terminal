"""Ein Datenpunkt = ein Wert mit Herkunft. So bleibt immer nachvollziehbar, woher eine Zahl stammt."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Erlaubte Arten von Daten (werden in der Oberfläche unterschiedlich gekennzeichnet)
ARTEN = {
    "echtzeit": "Echtzeit",
    "verzoegert": "verzögert (~15 Min.)",
    "schluss": "Schlusskurs",
    "historisch": "historisch",
    "schaetzung": "Schätzung",
    "eigene_berechnung": "eigene Berechnung",
    "offiziell": "offizielle Veröffentlichung",
    "termin": "Termin",
}


def jetzt_utc() -> datetime:
    return datetime.now(timezone.utc)


def als_utc(zeit) -> datetime | None:
    """Wandelt Unix-Zeit, ISO-Text oder datetime in eine UTC-Zeit um. None bleibt None."""
    if zeit is None or zeit == "":
        return None
    if isinstance(zeit, (int, float)):
        if zeit > 1e12:          # Millisekunden
            zeit = zeit / 1000
        return datetime.fromtimestamp(zeit, tz=timezone.utc)
    if isinstance(zeit, str):
        text = zeit.strip().replace("Z", "+00:00")
        if len(text) == 10:      # nur Datum
            text += "T00:00:00+00:00"
        zeit = datetime.fromisoformat(text)
    if zeit.tzinfo is None:
        zeit = zeit.replace(tzinfo=timezone.utc)
    return zeit.astimezone(timezone.utc)


@dataclass
class Datenpunkt:
    wert: Any
    quelle: str
    art: str
    stand: datetime | None = None          # Zeitpunkt, zu dem der Wert gilt
    abgerufen: datetime = field(default_factory=jetzt_utc)
    waehrung: str | None = None            # ISO-Code, z. B. "USD"
    einheit: str | None = None             # z. B. "%", "bp", "Index"

    def __post_init__(self):
        if self.art not in ARTEN:
            raise ValueError(f"Unbekannte Datenart '{self.art}'")
        self.stand = als_utc(self.stand)
        self.abgerufen = als_utc(self.abgerufen)

    def als_dict(self) -> dict:
        d = asdict(self)
        for k in ("stand", "abgerufen"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class Ergebnis:
    """Antwort eines Providers: entweder Daten oder ein klar beschriebener Grund, warum es keine gibt."""
    quelle: str
    ok: bool
    daten: Any = None
    grund: str = ""                        # bei ok=False: z. B. "kein Schlüssel", "Limit erreicht", "HTTP 401"
    art: str | None = None
    abgerufen: datetime = field(default_factory=jetzt_utc)

    def als_dict(self) -> dict:
        return {"quelle": self.quelle, "ok": self.ok, "grund": self.grund, "art": self.art,
                "abgerufen": self.abgerufen.isoformat(), "daten": self.daten}
