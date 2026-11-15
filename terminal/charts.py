"""Charts im Stil von Bloomberg/FT: hell, aufgeräumt, Titel und Quelle ausserhalb der Grafik.

Jede Funktion gibt fertiges HTML zurück. Plotly.js wird einmal pro Seite geladen.
Aufbau einer Grafik (wie bei Bloomberg):
    Titel (fett)            <- sagt, was man sieht
    Untertitel (grau)       <- Einheit / Zeitraum
    [Zeitraum-Knöpfe]       <- 1M 3M 6M YTD 1J 2J
    Grafik                  <- Achse rechts, letzter Wert als farbiges Kästchen
    Quelle (klein)
"""
import itertools
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from markupsafe import Markup, escape

# Farbpalette (FT/Bloomberg-artig, auf Farbenblind-Tauglichkeit geprüft). Reihenfolge nicht ändern.
FARBEN = ["#0f5499", "#e0703a", "#00897b", "#990f3d", "#9a8a00"]
TINTE = "#1a1817"
GRAU = "#6b6560"
RASTER = "#e9e6e2"
ACHSE = "#8c857e"
SCHRIFT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"

ZEITRAEUME = [("1M", 31), ("3M", 92), ("6M", 183), ("YTD", "ytd"), ("1J", 365), ("2J", 730)]
_zaehler = itertools.count(1)


def _verbinde(reihen) -> pd.Series:
    """Alle Werte mehrerer Reihen in einer Reihe (nur für Min/Max-Berechnungen)."""
    return pd.Series([float(v) for r in reihen for v in r.values])


def _fmt(wert: float, einheit: str) -> str:
    if einheit == "%":
        return f"{wert:.2f}%"
    if einheit == "pct_signed":
        return f"{wert:+.0f}%"
    if einheit == "korr":
        return f"{wert:+.2f}"
    if abs(wert) >= 10000:
        return f"{wert:,.0f}".replace(",", "’")
    if abs(wert) >= 100:
        return f"{wert:,.1f}".replace(",", "’")
    if abs(wert) >= 10:
        return f"{wert:.2f}"
    return f"{wert:.3f}" if abs(wert) >= 1 else f"{wert:.4f}"


def _tickformat(werte: pd.Series, einheit: str) -> str:
    if einheit == "korr":
        return ".1f"
    if einheit in ("%", "pct_signed"):
        return ".1f" if (werte.max() - werte.min()) < 8 else ".0f"
    groesse = werte.abs().max()
    return ",.0f" if groesse >= 1000 else ".2f" if groesse < 10 else ",.1f" if groesse < 100 else ",.0f"


def _layout(fig: go.Figure, hoehe: int, legende: bool, einheit: str, werte: pd.Series, rechts: int = 64):
    fig.update_layout(
        height=hoehe, margin=dict(l=4, r=rechts, t=28 if legende else 8, b=28),
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        font=dict(family=SCHRIFT, size=11, color=GRAU), separators=".’",
        hovermode="x unified", showlegend=legende,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", font=dict(size=11, color=TINTE),
                    bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=ACHSE, font=dict(color=TINTE, family=SCHRIFT)),
        xaxis=dict(showgrid=False, showline=True, linecolor=ACHSE, ticks="outside", tickcolor=ACHSE,
                   ticklen=4, showspikes=True, spikemode="across", spikecolor=ACHSE,
                   spikethickness=1, spikedash="dot"),
        yaxis=dict(side="right", gridcolor=RASTER, zeroline=False, showline=False,
                   tickformat=_tickformat(werte, einheit), ticksuffix="%" if einheit == "%" else ""),
    )


def _html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displayModeBar": False, "responsive": True, "locale": "de-ch"})


def _letzter_wert(fig, wert: float, farbe: str, einheit: str):
    fig.add_annotation(x=1, xref="paper", xanchor="left", y=wert, yref="y", showarrow=False,
                       text=f"<b>{_fmt(wert, einheit)}</b>", font=dict(color="#ffffff", size=11),
                       bgcolor=farbe, borderpad=3, xshift=2)


def figur(titel: str, untertitel: str, quelle: str, inhalt: str, knoepfe: str = "",
          hinweis: str = "", breit: bool = False) -> Markup:
    """Rahmen um eine Grafik oder Tabelle: Titel, Untertitel, Inhalt, Quelle."""
    klasse = "figur breit" if breit else "figur"
    h = f'<p class="figur-hinweis">{escape(hinweis)}</p>' if hinweis else ""
    return Markup(
        f'<figure class="{klasse}"><h4>{escape(titel)}</h4><p class="figur-unter">{escape(untertitel)}</p>'
        f'{knoepfe}{inhalt}<figcaption>Quelle: {escape(quelle)}</figcaption>{h}</figure>')


def fehlt(titel: str, meldung: str, breit: bool = False) -> Markup:
    return figur(titel, "", "–", f'<div class="fehlt">Daten nicht verfügbar<span>{escape(meldung)}</span></div>',
                 breit=breit)


def linien(serien: dict[str, pd.Series], *, titel: str, untertitel: str, quelle: str,
           einheit: str = "", start_tage: int | None = 365, knoepfe: bool = True, hoehe: int = 270,
           nulllinie: bool = False, flaeche: bool = False, hinweis: str = "", breit: bool = False,
           farben: list[str] | None = None, y_bereich: tuple | None = None) -> Markup:
    """Ein oder mehrere Linien auf EINER Achse (nie zwei verschiedene Skalen)."""
    farben = farben or FARBEN
    serien = {k: v.dropna() for k, v in serien.items() if v is not None and not v.dropna().empty}
    if not serien:
        return fehlt(titel, "keine Werte", breit)
    div_id = f"chart{next(_zaehler)}"
    fig = go.Figure()
    alle = _verbinde(serien.values())
    ende = max(s.index[-1] for s in serien.values())
    for (name, s), farbe in zip(serien.items(), farben):
        fig.add_trace(go.Scatter(
            x=s.index.strftime("%Y-%m-%d").tolist(), y=[round(float(v), 4) for v in s.values], name=name,
            mode="lines", line=dict(color=farbe, width=2),
            fill="tozeroy" if flaeche and len(serien) == 1 else None,
            fillcolor="rgba(15,84,153,0.07)",
            hovertemplate=f"%{{y:{_tickformat(alle, einheit)}}}{'%' if einheit == '%' else ''}"
                          f"<extra>{escape(name)}</extra>"))
        _letzter_wert(fig, float(s.iloc[-1]), farbe, einheit)
    sichtbar = alle
    if start_tage:
        start = ende - timedelta(days=start_tage)
        sichtbar = _verbinde(s[s.index >= start] for s in serien.values())
    _layout(fig, hoehe, len(serien) > 1, einheit, sichtbar)
    if start_tage:
        fig.update_xaxes(range=[start.strftime("%Y-%m-%d"), (ende + timedelta(days=2)).strftime("%Y-%m-%d")])
    if nulllinie:
        fig.add_hline(y=0, line=dict(color=ACHSE, width=1))
    unten, oben = float(sichtbar.min()), float(sichtbar.max())
    puffer = (oben - unten) * 0.08 or abs(oben) * 0.02 or 1
    if y_bereich:
        fig.update_yaxes(range=list(y_bereich), tickvals=[-100, -50, 0, 50, 100] if y_bereich == (-100, 100) else None)
    elif not flaeche:
        fig.update_yaxes(range=[unten - puffer, oben + puffer])
    else:
        fig.update_yaxes(range=[min(0, unten - puffer), oben + puffer])

    k = ""
    if knoepfe:
        aktiv = {31: "1M", 92: "3M", 183: "6M", 365: "1J", 730: "2J"}.get(start_tage, "")
        k = '<div class="zeitraum" data-chart="%s">%s</div>' % (div_id, "".join(
            f'<button data-tage="{t}" class="{"aktiv" if n == aktiv else ""}">{n}</button>' for n, t in ZEITRAEUME))
    return figur(titel, untertitel, quelle, _html(fig, div_id), k, hinweis, breit)


def balken_mit_schnitt(taeglich: pd.Series, schnitt: pd.Series, *, titel: str, untertitel: str, quelle: str,
                       name_balken: str, name_schnitt: str, hoehe: int = 280, breit: bool = False,
                       hinweis: str = "") -> Markup:
    """Tageswerte als feine Balken, gleitender Durchschnitt als Linie (z. B. Tanker-Durchfahrten)."""
    div_id = f"chart{next(_zaehler)}"
    fig = go.Figure()
    fig.add_trace(go.Bar(x=taeglich.index.strftime("%Y-%m-%d").tolist(), y=taeglich.tolist(), name=name_balken,
                         marker=dict(color="#b9c9dc", line=dict(width=0)),
                         hovertemplate="%{y:.0f}<extra>" + escape(name_balken) + "</extra>"))
    fig.add_trace(go.Scatter(x=schnitt.index.strftime("%Y-%m-%d").tolist(), y=schnitt.round(1).tolist(),
                             name=name_schnitt, mode="lines", line=dict(color=FARBEN[0], width=2),
                             hovertemplate="%{y:.1f}<extra>" + escape(name_schnitt) + "</extra>"))
    _letzter_wert(fig, float(schnitt.iloc[-1]), FARBEN[0], "")
    _layout(fig, hoehe, True, "", taeglich)
    fig.update_layout(bargap=0.1)
    fig.update_yaxes(rangemode="tozero", tickformat=".0f")
    return figur(titel, untertitel, quelle, _html(fig, div_id), hinweis=hinweis, breit=breit)


def kurve(kurven: dict[str, pd.Series], *, titel: str, untertitel: str, quelle: str,
          hoehe: int = 280, breit: bool = False) -> Markup:
    """Zinskurve: x = Laufzeiten (Kategorien), mehrere Stichtage als Linien mit Punkten."""
    div_id = f"chart{next(_zaehler)}"
    fig = go.Figure()
    for (name, s), farbe in zip(kurven.items(), [FARBEN[0], FARBEN[1], "#a7a29c"]):
        fig.add_trace(go.Scatter(x=list(s.index), y=s.round(2).tolist(), name=name, mode="lines+markers",
                                 line=dict(color=farbe, width=2), marker=dict(size=8, color=farbe,
                                 line=dict(color="#ffffff", width=2)),
                                 hovertemplate="%{y:.2f}%<extra>" + escape(name) + "</extra>"))
    werte = _verbinde(kurven.values())
    _layout(fig, hoehe, True, "%", werte, rechts=12)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(showspikes=False, type="category")
    return figur(titel, untertitel, quelle, _html(fig, div_id), breit=breit)


def mini(s: pd.Series, farbe: str) -> Markup:
    """Kleine Linie ohne Achsen für Tabellen (Sparkline), als SVG – schnell und druckbar."""
    s = s.dropna().iloc[-66:]
    if len(s) < 2:
        return Markup("")
    b, h = 96, 26
    lo, hi = float(s.min()), float(s.max())
    spanne = (hi - lo) or 1
    punkte = " ".join(f"{i / (len(s) - 1) * b:.1f},{h - 2 - (float(v) - lo) / spanne * (h - 4):.1f}"
                      for i, v in enumerate(s.values))
    return Markup(f'<svg class="mini" viewBox="0 0 {b} {h}" width="{b}" height="{h}" aria-hidden="true">'
                  f'<polyline points="{punkte}" fill="none" stroke="{farbe}" stroke-width="1.5"/></svg>')
