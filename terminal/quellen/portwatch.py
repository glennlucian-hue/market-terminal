"""IMF PortWatch: tägliche Schiffs-Durchfahrten durch wichtige Meerengen (Satelliten-AIS-Daten).

Hinweis: Die Daten erscheinen mit etwa einer Woche Verzögerung.
"""
import pandas as pd
import requests

from ..cache import DatenFehler, hole

NAME = "IMF PortWatch"
_URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "Daily_Chokepoints_Data/FeatureServer/0/query")


def durchfahrten(meerenge: str = "Strait of Hormuz") -> tuple[pd.DataFrame, dict]:
    """Spalten: tanker, total (Anzahl Schiffe pro Tag)."""
    def laden():
        zeilen, start = [], 0
        while True:  # der Server liefert nur eine begrenzte Anzahl Zeilen pro Abfrage -> seitenweise
            r = requests.get(_URL, timeout=60, params={
                "where": f"portname='{meerenge}' AND date >= DATE '2023-01-01'",
                "outFields": "date,n_tanker,n_total", "orderByFields": "date",
                "resultOffset": start, "f": "json"})
            r.raise_for_status()
            daten = r.json()
            if "error" in daten:
                raise DatenFehler(f"PortWatch meldet: {daten['error'].get('message')}")
            teil = [f["attributes"] for f in daten.get("features", [])]
            zeilen += teil
            if not teil or not daten.get("exceededTransferLimit"):
                break
            start += len(teil)
        if not zeilen:
            raise DatenFehler(f"Keine PortWatch-Daten für '{meerenge}'")
        df = pd.DataFrame(zeilen)
        df.index = pd.to_datetime(df.pop("date"))
        return df.rename(columns={"n_tanker": "tanker", "n_total": "total"}).sort_index()

    return hole(f"portwatch_{meerenge}", NAME, 24, laden)
