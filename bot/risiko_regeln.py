"""Risikomanagement: Positionsgrösse, Tages-Verlustgrenze, Verlustserie, Not-Aus.

Grundsätze (fest eingebaut, nicht optional):
  - Jeder Vorschlag hat einen Stop. Ohne Stop keine Position.
  - Risiko je Trade = fester Anteil des Kontos (Standard 1 %), geteilt durch den Stop-Abstand in Geld.
  - Ist die Tages-Verlustgrenze (Standard 3 %) oder die maximale Verlustserie erreicht: heute keine Signale mehr.
  - Liegt die Datei NOTAUS im Projektordner, gibt der Bot gar nichts mehr aus (Not-Aus, z. B. vom Handy aus anlegen).
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

# Punktwert = Geld je 1.0 Kursbewegung und Stück/Kontrakt; tick = kleinste Kursstufe;
# gebuehr = je Stück und Seite (ungefähr IBKR, USD), min_gebuehr = Mindestgebühr je Auftrag
INSTRUMENTE = {
    "NQ": {"punktwert": 20.0, "tick": 0.25, "einheit": "Kontrakt", "gebuehr": 2.25},
    "MNQ": {"punktwert": 2.0, "tick": 0.25, "einheit": "Kontrakt", "gebuehr": 0.62},
    "ES": {"punktwert": 50.0, "tick": 0.25, "einheit": "Kontrakt", "gebuehr": 2.25},
    "MES": {"punktwert": 5.0, "tick": 0.25, "einheit": "Kontrakt", "gebuehr": 0.62},
    "QQQ": {"punktwert": 1.0, "tick": 0.01, "einheit": "Aktie", "gebuehr": 0.005, "min_gebuehr": 1.0},
    "SPY": {"punktwert": 1.0, "tick": 0.01, "einheit": "Aktie", "gebuehr": 0.005, "min_gebuehr": 1.0},
}


@dataclass
class Regeln:
    konto: float = 10_000.0
    risiko_pro_trade: float = 0.01
    max_tagesverlust: float = 0.03
    max_trades_tag: int = 3
    max_verluste_folge: int = 2
    min_rr: float = 2.0
    stop_puffer_ticks: int = 4
    max_kontrakte: int = 2               # harte Obergrenze, egal was die Rechnung ergibt
    notaus_datei: str = "NOTAUS"


@dataclass
class RisikoWaechter:
    regeln: Regeln = field(default_factory=Regeln)
    tag: object = None
    tages_ergebnis: float = 0.0
    trades_heute: int = 0
    verluste_folge: int = 0

    def _neuer_tag(self, tag):
        if tag != self.tag:
            self.tag, self.tages_ergebnis, self.trades_heute, self.verluste_folge = tag, 0.0, 0, 0

    def erlaubt(self, tag) -> tuple[bool, str]:
        self._neuer_tag(tag)
        if Path(self.regeln.notaus_datei).exists():
            return False, "Not-Aus aktiv (Datei NOTAUS vorhanden)"
        if self.tages_ergebnis <= -self.regeln.max_tagesverlust * self.regeln.konto:
            return False, f"Tages-Verlustgrenze erreicht ({self.tages_ergebnis:.0f})"
        if self.trades_heute >= self.regeln.max_trades_tag:
            return False, f"maximal {self.regeln.max_trades_tag} Trades pro Tag"
        if self.verluste_folge >= self.regeln.max_verluste_folge:
            return False, f"{self.verluste_folge} Verluste in Folge: Pause bis morgen"
        return True, ""

    def positionsgroesse(self, einstieg: float, stop: float, instrument: str, faktor: float = 1.0) -> dict:
        spez = INSTRUMENTE[instrument]
        abstand = abs(einstieg - stop)
        if abstand <= 0:
            return {"stueck": 0, "risiko": 0.0, "grund": "Stop-Abstand 0"}
        budget = self.regeln.konto * self.regeln.risiko_pro_trade * max(0.0, min(faktor, 1.0))
        # Tagesverlust: nie mehr riskieren, als bis zur Grenze übrig ist
        rest = self.regeln.max_tagesverlust * self.regeln.konto + self.tages_ergebnis
        budget = min(budget, max(rest, 0.0))
        stueck = math.floor(budget / (abstand * spez["punktwert"]))
        if spez["einheit"] == "Kontrakt":
            stueck = min(stueck, self.regeln.max_kontrakte)
        grund = "" if stueck > 0 else f"Stop zu weit für das Risikobudget ({budget:.0f})"
        return {"stueck": stueck, "risiko": round(stueck * abstand * spez["punktwert"], 2),
                "einheit": spez["einheit"], "grund": grund}

    def buche(self, tag, ergebnis: float):
        self._neuer_tag(tag)
        self.tages_ergebnis += ergebnis
        self.trades_heute += 1
        self.verluste_folge = self.verluste_folge + 1 if ergebnis < 0 else 0
