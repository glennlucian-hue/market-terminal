"""Gamma-Levels für das Terminal: GEXBot (mit Abo) oder Gratis-Ersatz aus Cboe-Optionsdaten.

Gamma einfach erklärt: Options-Händler (Market Maker) sichern sich ab. Über dem "Zero Gamma" dämpfen sie
Bewegungen eher (sie kaufen bei Rückgängen, verkaufen bei Anstiegen), darunter verstärken sie Bewegungen eher.
"Major"-Strikes mit viel positivem bzw. negativem Gamma wirken oft als Widerstand bzw. Unterstützung.
Das ist eine Markt-Mechanik, keine Prognose.
"""
from .datenpunkt import jetzt_utc
from .provider import GexBot


def _einordnung(spot, zero):
    if not spot or not zero:
        return None
    return "über Zero Gamma – Händler dämpfen eher" if spot >= zero else "unter Zero Gamma – Händler verstärken eher"


def sammle_gamma(watchlist_ticker: list[str], max_ersatz: int = 8) -> dict:
    gex = GexBot()
    abgedeckt = GexBot.abgedeckte_ticker()
    # Welche Watchlist-Werte hat GEXBot? (Indizes und Rohstoffe über Stellvertreter-ETFs)
    paare = []
    for t in watchlist_ticker:
        g = GexBot.ZUORDNUNG.get(t, t if t.isalpha() else None)
        if g and (not abgedeckt or g in abgedeckt) and g not in [p[1] for p in paare]:
            paare.append((t, g))
    werte, hinweise = {}, []
    bereit, grund = gex.bereit()
    if bereit:
        for yahoo_t, gex_t in paare:
            e = gex.levels(gex_t)
            if e.ok:
                d = e.daten
                werte[yahoo_t] = {**d, "gex_ticker": gex_t, "einordnung": _einordnung(d["spot"], d["zero_gamma"]),
                                  "quelle": "GEXBot (Classic, alle Verfälle)", "art": "verzoegert"}
            else:
                hinweise.append(f"{gex_t}: {e.grund}")
        quelle = "GEXBot"
    else:
        # Gratis-Ersatz: eigene Berechnung aus verzögerten Cboe-Optionsdaten (nur einzelne US-Aktien)
        from terminal import risiko
        from terminal.quellen import cboe
        quelle = "Cboe (eigene Berechnung)"
        hinweise.append(f"GEXBot nicht verbunden ({grund}) – Gratis-Ersatz für einzelne US-Aktien")
        for yahoo_t, _ in [p for p in paare if p[0] == p[1]][:max_ersatz]:
            try:
                o, s = cboe.optionskette(yahoo_t)
                g = risiko.gamma_exposure(o, s)
            except Exception as e:
                hinweise.append(f"{yahoo_t}: {str(e)[:60]}")
                continue
            if not g:
                continue
            profil = [[float(k), round(float(v) / 1e6, 3)] for k, v in g["je_strike"].items()]
            werte[yahoo_t] = {"ticker": yahoo_t, "spot": s, "zero_gamma": g["flip"], "major_pos": g["call_wand"],
                              "major_neg": g["put_wand"], "summe_oi": g["gesamt_mrd"], "profil": profil,
                              "stand": jetzt_utc().isoformat(), "einordnung": _einordnung(s, g["flip"]),
                              "quelle": "Cboe-Optionsdaten (verzögert), eigene Berechnung", "art": "eigene_berechnung"}
    return {"quelle": quelle, "gexbot_verbunden": bereit, "werte": werte, "hinweise": hinweise,
            "abgedeckt_bei_gexbot": [p[1] for p in paare], "erstellt": jetzt_utc().isoformat()}
