"""CFTC Commitments of Traders: Wie sind grosse Marktteilnehmer in Futures positioniert?

Erscheint wöchentlich (Freitag), Stichtag ist jeweils der Dienstag davor.
- Finanz-Futures (S&P 500): "Leveraged Funds" (Hedgefonds/CTAs) und "Asset Manager"
- Rohstoffe (Gold, WTI): "Managed Money" (Hedgefonds/CTAs)
"""
import pandas as pd
import requests

from ..cache import DatenFehler, hole

NAME = "CFTC Commitments of Traders"
_URL = "https://publicreporting.cftc.gov/resource/{ds}.json"

MAERKTE = {
    "sp500": {"name": "S&P 500 E-Mini", "code": "13874A", "datensatz": "gpe5-46if",
              "gruppen": {"Hedgefonds (Leveraged Funds)": "lev_money_positions",
                          "Vermögensverwalter (Asset Manager)": "asset_mgr_positions"}},
    "gold": {"name": "Gold (COMEX)", "code": "088691", "datensatz": "72hh-3qpy",
             "gruppen": {"Hedgefonds (Managed Money)": "m_money_positions"}},
    "wti": {"name": "WTI-Rohöl (NYMEX)", "code": "067651", "datensatz": "72hh-3qpy",
            "gruppen": {"Hedgefonds (Managed Money)": "m_money_positions"}},
}


def netto_positionen(markt: str) -> tuple[pd.DataFrame, dict]:
    """Netto-Kontrakte (Long minus Short) je Händlergruppe, Wochenwerte seit 2020."""
    m = MAERKTE[markt]

    def laden():
        r = requests.get(_URL.format(ds=m["datensatz"]), timeout=60, params={
            "$where": f"cftc_contract_market_code='{m['code']}' AND report_date_as_yyyy_mm_dd >= '2020-01-01'",
            "$order": "report_date_as_yyyy_mm_dd", "$limit": 2000})
        r.raise_for_status()
        zeilen = r.json()
        if not zeilen:
            raise DatenFehler(f"Keine CFTC-Daten für {m['name']}")
        df = pd.DataFrame(zeilen)
        df.index = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.normalize()
        ergebnis = pd.DataFrame(index=df.index)
        for anzeige, feld in m["gruppen"].items():
            lang = f"{feld}_long_all" if f"{feld}_long_all" in df else f"{feld}_long"
            kurz = f"{feld}_short_all" if f"{feld}_short_all" in df else f"{feld}_short"
            ergebnis[anzeige] = pd.to_numeric(df[lang]) - pd.to_numeric(df[kurz])
        ergebnis["Open Interest"] = pd.to_numeric(df["open_interest_all"])
        return ergebnis[~ergebnis.index.duplicated(keep="last")]

    return hole(f"cftc_{markt}", NAME, 24, laden)
