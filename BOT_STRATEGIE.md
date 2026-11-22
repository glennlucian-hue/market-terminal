# Signal-Bot QQQ/NQ – Regeln und Stand

Stand: 22.11.2026 · Status: **Signale + Backtest, keine Ausführung**

Der Bot verbindet, was sich in der Praxis bewährt hat: **ICT (CISD + Turtle Soup)** als Auslöser,
**Orderflow** als Bestätigung, **TPO** und **GEX** für Ziele und Kontext, und **Makro** als Filter.

```
Makro-Filter ──► darf ich in diese Richtung?          (VIX9D/VIX, NQ-VIX-Korrelation, 10Y, 2Y, DXY, $TICK)
     │
ICT-Auslöser ──► Turtle Soup (Sweep) + CISD           (Swing-Hoch/-Tief, Vortages-Hoch/-Tief)
     │
Bestätigung  ──► CVD-Divergenz, Sweep an VAL/VAH, Gamma-Regime, EMA 21/50 (Trend + Abpraller) -> Qualitätspunkte
     │
Break & Retest ─► unter Zero Gamma: Bruch einer Gamma-Wand, Retest, CVD in Trendrichtung (`--wände` oder GEXBot)
Ziel/Stop    ──► Stop hinter Sweep-Extrem; Ziel = nächste Gegen-Liquidität / POC / VAH / VAL / GEX-Wand, CRV ≥ 2
     │
Risiko       ──► 1 % je Trade, 3 % Tagesgrenze, max. 3 Trades, Pause nach 2 Verlusten, Not-Aus
```

## Benutzung
```
python bot_signale.py                                  # Lage und Signale von heute (MNQ, Daten NQ=F, 5 Min.)
python bot_signale.py --backtest --tage 55             # Backtest (Yahoo: 5 Min. max. ~60 Tage)
python bot_signale.py --symbol QQQ --instrument QQQ --konto 5000 --risiko 0.005
python -m pytest tests                                 # Tests der Regeln
```
Not-Aus: Datei `NOTAUS` im Projektordner anlegen → keine Signale mehr.

## Regeln im Detail
| Schritt | Regel | Code |
|---|---|---|
| Liquidität | bestätigte Swings (3 links / 2 rechts, max. 120 Kerzen alt), Vortages-Hoch/-Tief | `bot/ict.py` |
| Turtle Soup | Docht durch ein offenes Niveau; das Niveau gilt danach als abgeholt | `bot/ict.py` |
| CISD | Schluss über (Long) der Eröffnung der Abwärtsserie, die ins Tief geliefert hat, und zurück über dem Niveau; max. 12 Kerzen nach dem Sweep | `bot/ict.py` |
| Zeit | Kill Zones 09:30–11:30 und 13:30–15:30 New York; glattstellen 15:55 | `bot/signale.py` |
| Makro | Punkte ≥ +1.5 = nur Long, ≤ −1.5 = nur Short, dazwischen halbe Grösse; NQ-VIX-Korrelation > 0 halbiert | `bot/makro.py` |
| Stop | Sweep-Extrem ± 4 Ticks | `bot/signale.py` |
| Ziel | nächstes Gegen-Niveau mit CRV ≥ 2, sonst kein Trade | `bot/signale.py` |
| Grösse | (Konto × 1 % × Faktor) / (Stop-Abstand × Punktwert), max. 2 Kontrakte | `bot/risiko_regeln.py` |

Makro-Punkte: VIX9D/VIX > 1 −1.5 · < 0.90 +1 · schnell steigend −0.5 · VIX ±5 % ∓1 · 10Y ±5 bp ∓1 ·
2Y ±5 bp ∓0.5 · DXY ±0.3 % ∓0.5 · $TICK-Schnitt 30 Min. > +300 +1 / < −300 −1.

## Was echt ist und was geschätzt
| Baustein | Heute (gratis) | Für echten Betrieb |
|---|---|---|
| Kerzen NQ/QQQ | Yahoo, ~10–15 Min. verzögert | Echtzeit über Broker (IBKR) oder Rithmic/CQG |
| CVD / Delta | **Schätzung** aus Kerzen (Lage des Schlusses) | echte Trades mit Aggressor-Seite; `orderflow.lade_trades_csv()` liest Exporte (zeit, preis, menge, seite) |
| Footprint Bid×Ask, Stacked Imbalances, Big Trades, Cluster-Profil | Code fertig, braucht Trade-Daten | ATAS / Sierra Chart / Bookmap-Export oder Databento |
| Heatmap (Orderbuch) | **nicht abgebildet** | Markttiefe (Level 2), z. B. Bookmap; schwer zu automatisieren |
| TPO | eigene Berechnung aus 5-Min.-Kerzen (30-Min.-Perioden) | gleich, genauer mit 1-Min.-Daten |
| VIX, VIX9D, 10Y, DXY | Yahoo | gleich |
| 2Y | aus dem 2Y-Future ZT=F über die Duration umgerechnet (Näherung) | Rendite direkt (IBKR, TradingView) |
| $TICK | **fehlt** (nicht bei Yahoo) | IBKR (`TICK-NYSE`) oder TradingView |
| GEX | GEXBot Classic, wenn `GEXBOT_API_KEY` gesetzt | GEXBot Quant (WebSocket) |

## Erster Backtest (22.11.2026, Yahoo 5 Min., 55 Tage, vorsichtige Annahmen)
| Lauf | Trades | Treffer | Summe R | Ergebnis | Profit-Faktor |
|---|---|---|---|---|---|
| MNQ, mit Makro | 2 | 0 % | −2.0 | −93 | 0 |
| MNQ, ohne Makro | 22 | 27 % | −2.8 | −390 | 0.71 |
| QQQ, mit Makro | 69 | 39 % | +4.0 | +168 | 1.08 |

**Einordnung:** viel zu wenige Trades für eine Aussage. Bei MNQ fallen die meisten Setups weg, weil der Stop
für 1 % von 10 000 zu weit ist (5-Min.-Sweeps im NQ sind oft > 50 Punkte) – das ist die Risikoregel, die wirkt.
Der Kerzen-Backtest kennt weder echtes Delta noch die Reihenfolge innerhalb einer Kerze. Nächster sinnvoller
Schritt ist ein Backtest auf **1-Sekunden- oder Trade-Daten** (GEXBot-Historie, Databento) mit echtem CVD.

## Nächste Schritte
1. $TICK und echtes Delta anbinden (IBKR-Papier-Konto liefert beides; `ib_async` als Python-Bibliothek).
2. Backtest mit Trade-Daten und Orderflow-Bestätigung als Pflicht statt Bonus vergleichen.
3. Papier-Handel: `python bot_signale.py --live 5` (fertig). Neue Signale gehen nach `signale_journal.csv` und, mit TELEGRAM_TOKEN + TELEGRAM_CHAT in `.env`, aufs Handy. Ausführung von Hand.
4. Erst nach mehreren Wochen stabiler Papier-Ergebnisse: Ausführung über IBKR-API, mit Not-Aus und Tagesgrenze im Broker.

> Nur Vorschläge, keine Anlageberatung. Vor privatem Handel die internen Regeln der Bank klären.
> GEXBot-Daten nur privat nutzen, nicht weitergeben.
