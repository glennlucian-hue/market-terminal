"""Kurse mit Ersatzkette: Yahoo -> Finnhub -> FMP. Die erste Quelle mit gültigen Daten gewinnt.

Jeder Kurs nennt die tatsächlich verwendete Quelle und die Gründe, warum frühere Quellen nicht lieferten.
"""
from datetime import timezone

import pandas as pd

from .datenpunkt import Ergebnis, jetzt_utc
from .provider import FMP, Finnhub

_finnhub, _fmp = Finnhub(), FMP()


def _yahoo(symbol: str) -> Ergebnis:
    try:
        from terminal.quellen import yahoo
        s, meta = yahoo.kurse(symbol, 0.25)          # 15 Minuten Cache
    except Exception as e:
        return Ergebnis("yahoo", False, grund=str(e)[:160])
    stand = pd.Timestamp(s.index[-1]).to_pydatetime().replace(tzinfo=timezone.utc)
    return Ergebnis("yahoo", True, art="verzoegert", daten={
        "symbol": symbol, "kurs": float(s.iloc[-1]),
        "veraenderung_pct": (float(s.iloc[-1]) / float(s.iloc[-2]) - 1) * 100 if len(s) > 1 else None,
        "vortag": float(s.iloc[-2]) if len(s) > 1 else None, "stand": stand.isoformat(),
        "waehrung": meta.get("waehrung")})


def kurs(symbol: str, nur_us: bool | None = None) -> dict:
    """Gibt {"ok", "daten", "quelle", "art", "versuche": [...]} zurück. Finnhub/FMP nur für US-Symbole."""
    if nur_us is None:
        nur_us = not any(z in symbol for z in ".=^-")       # z. B. NESN.SW, CHF=X, ^GSPC, BTC-USD
    ketten = [_yahoo] + ([_finnhub.kurs, _fmp.kurs] if nur_us else [])
    versuche = []
    for quelle in ketten:
        e = quelle(symbol)
        versuche.append({"quelle": e.quelle, "ok": e.ok, "grund": e.grund})
        if e.ok and e.daten and e.daten.get("kurs") is not None:
            return {"ok": True, "daten": e.daten, "quelle": e.quelle, "art": e.art, "versuche": versuche,
                    "abgerufen": jetzt_utc().isoformat()}
    return {"ok": False, "daten": None, "quelle": None, "art": None, "versuche": versuche,
            "abgerufen": jetzt_utc().isoformat()}
