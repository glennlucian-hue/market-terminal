"""Daten für den Bot (Gratis-Stufe über Yahoo; verzögert, nur zum Entwickeln und Testen).

Grenzen von Yahoo: 1-Minuten-Kerzen nur ca. 7 Tage zurück, 5-Minuten-Kerzen ca. 60 Tage, Futures ~10–15 Min.
verzögert, kein echtes Delta und kein $TICK. Für echten Betrieb braucht es einen Echtzeit-Feed
(z. B. IBKR-API, Rithmic/CQG über ATAS oder Sierra Chart) und für Gamma GEXBot Quant.
"""
import pandas as pd

ZEITZONE = "America/New_York"

MAKRO_SYMBOLE = {
    "vix": "^VIX",
    "vix9d": "^VIX9D",
    "us10y": "^TNX",      # Rendite in %
    "us02y_future": "ZT=F",  # 2-jähriger Treasury-Future (Kurs); Yahoo hat keine 2Y-Rendite intraday
    "dxy": "DX-Y.NYB",
}


def kerzen(symbol: str, intervall: str = "5m", tage: int = 30) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(symbol, period=f"{tage}d", interval=intervall, auto_adjust=False, progress=False,
                     prepost=True, multi_level_index=False)
    if df is None or df.empty:
        raise RuntimeError(f"keine Daten für {symbol} ({intervall}, {tage} Tage)")
    df.index = df.index.tz_convert(ZEITZONE) if df.index.tz else df.index.tz_localize("UTC").tz_convert(ZEITZONE)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def makro_reihen(intervall: str = "5m", tage: int = 30, melde=print) -> dict[str, pd.Series]:
    reihen = {}
    for name, sym in MAKRO_SYMBOLE.items():
        try:
            reihen[name] = kerzen(sym, intervall, tage)["Close"]
        except Exception as e:
            melde(f"  Hinweis: {name} ({sym}) nicht geladen: {str(e)[:80]}")
    return reihen


def gex_levels(gex_ticker: str = "NDX") -> tuple[dict | None, str]:
    """GEXBot-Levels (Classic) über die bestehende Provider-Schicht, falls GEXBOT_API_KEY gesetzt ist."""
    try:
        from kern.provider import GexBot
    except Exception as e:
        return None, f"GEXBot-Provider nicht verfügbar: {e}"
    g = GexBot()
    bereit, grund = g.bereit()
    if not bereit:
        return None, f"GEXBot nicht verbunden ({grund})"
    e = g.levels(gex_ticker)
    return (e.daten, "") if e.ok else (None, e.grund)
