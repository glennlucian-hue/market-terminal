# Vorbereitung Trading-Bot (für einen neuen Chat)

Stand: 21.11.2026 · Diese Notiz fasst zusammen, was das Market Terminal bereits liefert und was für einen
Trading-Bot noch fehlt. Sie ist als Ausgangspunkt für einen eigenen Chat gedacht.

## Entscheidungen des Nutzers
- Ziel: Bot, der Einstiege (Long/Short) mit Risikomanagement vorschlägt und später automatisch ausführt.
- Datenbasis: **GEXBot**, Paket **«Quant»** (noch kein Abo, Kosten auf gexbot.com prüfen – Budget bisher 5 CHF/Monat).
- Start: **zuerst nur Signale** (Vorschlag mit Einstieg, Stop, Ziel, Positionsgrösse), Ausführung von Hand bzw.
  im Papier-Konto. Automatische Ausführung erst nach einer Testphase und mit einem Broker mit API
  (Yuh und Cler haben keine Handels-API; Kandidat: Interactive Brokers mit Papier-Konto).

## Was das Terminal heute schon hat
| Baustein | Ort | Hinweis |
|---|---|---|
| Provider-Schicht mit Limits, Retries, Herkunft | `kern/provider/` | Finnhub, FMP, Alpha Vantage, CoinGecko, FRED, SEC, **GexBot** |
| GEXBot-Anbindung (Classic-Endpunkt) | `kern/provider/anbieter.py` → `GexBot.levels()` | `GET https://api.gex.bot/v2/{ticker}/classic/{gex_full|gex_zero|gex_one}`, Header `Authorization: Bearer <GEXBOT_API_KEY>` |
| Gamma-Levels für die Watchlist | `kern/gamma.py` | ohne Schlüssel: Ersatz aus Cboe (eigene Berechnung) |
| Chart-Technik (SMA, RSI, MACD, Pivots) | `terminal/technik.py` | |
| Risiko (Sharpe, Beta, Drawdown, GEX/Gamma-Flip) | `terminal/risiko.py` | |
| CTA-Modell, Liquiditäts-Check | `terminal/analysen.py` | |
| Verschlüsselte Datenpakete | `website/pakete/*.json.enc` | alle 15 Min. Mo–Fr (GitHub Actions) |

## Was für einen Bot fehlt
1. **Echtzeit-Daten:** Das Terminal läuft auf GitHub nur etwa alle 15 Minuten (teils verspätet). Ein Bot braucht
   einen dauerhaft laufenden Prozess (eigener PC oder kleiner Server) mit dem GEXBot-Quant-WebSocket:
   `POST /negotiate` (Azure Web PubSub, Protobuf + zstd; Python-Beispiele im GEXBot-Repository «quant-python-sockets»).
2. **Historische Daten für Backtests:** `GET /hist/{ticker}/{package}/{category}/{date}` (Quant: 90 Tage, 1-Sekunden-Snapshots).
3. **Strategie-Regeln** mit klaren Ein- und Ausstiegen, Stop-Loss, Positionsgrösse (z. B. max. 1 % Risiko je Trade),
   Tages-Verlustgrenze, Not-Aus.
4. **Backtest und Papier-Handel** vor echtem Geld.
5. **Broker-API** für die Ausführung (später).

## Wichtige Hinweise
- GEXBot-Daten nur für private Nutzung; keine Weitergabe (Bedingungen von GEXBot).
- Der Nutzer arbeitet bei einer Bank: interne Regeln für private Wertpapiergeschäfte vorab klären.
- Automatischer Handel kann schnell Geld kosten (Fehler, Ausfälle, Hebel). Darum: Signale → Papier-Konto → kleine Beträge.

## Umgesetzt (22.11.2026)
Erster Signal-Bot im Ordner `bot/`, Start mit `python bot_signale.py`. Er kombiniert ICT (Turtle Soup + CISD),
Orderflow (CVD, Footprint, Big Trades), TPO, Makro (VIX9D/VIX, NQ-VIX-Korrelation, 2Y, 10Y, DXY, $TICK), GEX
und feste Risikoregeln, mit einem Kerzen-Backtest. Regeln, Datenlage und erste Ergebnisse: siehe `BOT_STRATEGIE.md`.
