"""Cboe (Optionsbörse Chicago): verzögerte Optionskurse inkl. Griechen (Delta, Gamma, ...) und Open Interest."""
import re
from datetime import datetime

import pandas as pd
import requests

from ..cache import DatenFehler, hole

NAME = "Cboe (verzögerte Optionsdaten)"
_SYMBOL = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")


def optionskette(ticker: str) -> tuple[pd.DataFrame, float]:
    """Gibt (Optionen, aktueller Kurs) zurück. Spalten: verfall, typ (C/P), strike, oi, gamma, iv."""
    def laden():
        r = requests.get(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=60, allow_redirects=True)
        if r.status_code in (403, 404):
            raise DatenFehler(f"Keine Optionen für {ticker} bei Cboe (noch nicht gehandelt?)")
        r.raise_for_status()
        d = r.json()["data"]
        zeilen = []
        for o in d.get("options", []):
            m = _SYMBOL.match(o["option"])
            if not m:
                continue
            zeilen.append({"verfall": datetime.strptime(m.group(2), "%y%m%d").date().isoformat(), "typ": m.group(3),
                           "strike": int(m.group(4)) / 1000, "oi": o.get("open_interest") or 0,
                           "gamma": o.get("gamma") or 0, "iv": o.get("iv") or 0})
        if not zeilen:
            raise DatenFehler(f"Leere Optionskette für {ticker}")
        return {"kurs": d.get("current_price"), "optionen": zeilen}

    roh = hole(f"cboe_{ticker}", NAME, 2, laden)[0]
    return pd.DataFrame(roh["optionen"]), float(roh["kurs"])
