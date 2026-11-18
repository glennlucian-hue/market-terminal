# Market Terminal 2.0 – Architekturvorschlag (angepasst)

Stand: 18.11.2026 · Status: **Vorschlag, noch nicht umgesetzt**

## 0. Entscheidungen des Nutzers (18.11.2026)

| Frage | Entscheidung | Folge für die Architektur |
|---|---|---|
| Wo läuft die Anwendung? | **GitHub** | Kein eigener Server. GitHub Actions übernimmt die Rolle des Backends, GitHub Pages liefert die Oberfläche aus. |
| KI-Analysten | **Keine Kosten** | Keine kostenpflichtige KI-API. Stattdessen **regelbasierte Analysten** mit derselben Struktur (Fakten / Schätzungen / Interpretation). KI kann später ergänzt werden. |
| Aktualität der Kurse | **15 Min. Verzögerung reicht** | Aktualisierung alle 15 Minuten während der Handelszeiten, kein WebSocket nötig. |
| Budget | **5 CHF/Monat** | Nur Gratis-Dienste. Ziel: 0 CHF. |

---

## 1. Grundidee: "GitHub als Backend"

```
 GitHub Actions (geplant alle 15 Min. Mo–Fr 08:00–22:30 Zürich, plus nächtlicher Volllauf)
   │  1. Daten holen (Provider-Schicht, Fallbacks, Rate-Limits, Cache)
   │  2. Normalisieren (UTC, ISO-Währungen, Herkunft je Wert)
   │  3. Analysen rechnen (Technik, Risiko, CTA, Liquidität, Screener, regelbasierte Analysten)
   │  4. Datenpakete schreiben (JSON, je Modul) und mit deinem Passwort VERSCHLÜSSELN
   │  5. Oberfläche (React-App) bauen und zusammen mit den verschlüsselten Daten veröffentlichen
   ▼
 GitHub Pages (öffentliche Adresse, Inhalte nur mit Passwort lesbar)
   ▼
 Browser / Handy: React-App lädt Datenpakete, entschlüsselt sie lokal mit deinem Passwort,
                  zeigt Panels, Charts, Tabellen, Filter, Watchlists – alles interaktiv im Browser
```

- **Schlüssel bleiben sicher:** API-Schlüssel liegen nur in den GitHub-Secrets und werden nur im Actions-Lauf verwendet. Der Browser sieht nie einen Schlüssel.
- **Daten bleiben privat:** Datenpakete werden vor der Veröffentlichung mit AES-256 verschlüsselt (Schlüssel aus deinem Passwort abgeleitet, PBKDF2). Die heutige StatiCrypt-Lösung verschlüsselt nur HTML. Die neue App braucht dieselbe Verschlüsselung auch für ihre Datendateien.
- **Kosten:** GitHub Actions ist für öffentliche Repositories unbegrenzt gratis, GitHub Pages ebenfalls. Alle Datenquellen in ihren Gratis-Stufen.
- **Grenzen, offen gesagt:**
  - GitHub startet geplante Läufe teils 5 bis 30 Minuten verspätet. "15 Minuten" ist also ein Richtwert.
  - Bei öffentlichen Repositories ohne Aktivität stoppt GitHub geplante Läufe nach 60 Tagen. Das Terminal schreibt deshalb regelmässig eine Statusdatei.
  - Eingaben im Browser (z. B. eine neue Watchlist) werden im Browser gespeichert (pro Gerät) und können als Datei exportiert werden. Dauerhaft und geräteübergreifend gelten weiterhin die YAML-Dateien im Repository.
  - **Portfolio-Daten dürfen nicht ins öffentliche Repository.** Lösungen siehe Phase 4.

---

## 2. Technologie

| Teil | Wahl |
|---|---|
| Daten-Jobs ("Backend") | Python 3.12, bestehender Code aus `terminal/` als Provider-Schicht, in GitHub Actions |
| Datenhaltung | Verlauf und Cache in **Parquet/JSON-Dateien**, über GitHub-Actions-Cache von Lauf zu Lauf behalten. Logisches Schema wie unten, physisch als Dateien |
| Oberfläche | **React + TypeScript + Vite**, als statische App auf GitHub Pages |
| Panels | react-grid-layout (verschieb- und skalierbar, Layout im Browser gespeichert) |
| Charts | TradingView Lightweight Charts (Open Source) für Kurse und Indikatoren, ECharts für alles andere |
| Tabellen | TanStack Table (sortieren, filtern, Spalten wählen, CSV-Export) |
| Tastatur | Befehlszeile (Ticker eingeben ⏎), Funktionstasten pro Modul, `?` für die Hilfe |
| Verschlüsselung | WebCrypto (AES-GCM, PBKDF2) im Browser, `cryptography` in Python beim Bauen |
| Design | dunkles Anthrazit (#121417), Panels #1a1d21, Bernstein für Titel und Fokus, Monospace für Zahlen |

---

## 3. Datenquellen und Zuständigkeiten

Jede Quelle ist ein Adapter mit gleicher Schnittstelle. Wichtige Daten haben Ersatzquellen (Fallback-Kette).
Jeder Wert trägt `quelle`, `stand`, `abgerufen` und `art` ∈ {verzögert, schluss, historisch, schätzung, eigene_berechnung}.

| Datentyp | 1. Wahl | Ersatz | Abruf-Rhythmus (wegen Gratis-Limits) |
|---|---|---|---|
| Kurse (alle Märkte, ~15 Min. verzögert) | Yahoo | Finnhub (US), FMP | alle 15 Min. |
| Tageshistorie | Yahoo | FMP, Alpha Vantage | nächtlich |
| Fundamentaldaten | FMP | SEC EDGAR, Yahoo | nächtlich, verteilt (FMP ~250/Tag) |
| Schätzungen, Kursziele | Nasdaq, FMP | Finnhub | nächtlich |
| Earnings-Termine und Überraschungen | Finnhub | FMP, Nasdaq | 2× täglich |
| Insider | Finnhub | SEC Form 4 | täglich |
| 13F | SEC EDGAR | – | wöchentlich |
| ETF-Flows | **keine Gratis-Quelle**, nur gekennzeichnete Schätzung aus Anteilsänderungen | – | täglich |
| US-Makro und Kalender | FRED | BLS | täglich |
| EZB / SNB | EZB- und SNB-Datenportal | FRED | täglich |
| Krypto | CoinGecko | Yahoo | alle 15 Min. |
| Optionen / Gamma | Cboe (verzögert) | – | stündlich |
| News | Finnhub, Google News | Alpha Vantage (mit Sentiment, 25/Tag) | alle 15 Min. (AV 1–2× täglich) |
| US-Top-Bewegungen | Alpha Vantage | eigene Watchlist | 1× täglich |
| Positionierung, Hormuz | CFTC, IMF PortWatch | – | täglich |

---

## 4. Logisches Datenschema (als Dateien)

Wie im ersten Vorschlag, aber als Dateien statt Datenbanktabellen:

```
daten/stamm/instrumente.json         Instrumente + Symbol je Quelle (z. B. Roche: ROP.SW)
daten/kurse/tag/<ticker>.parquet     Tageskurse mit Quelle
daten/kurse/aktuell.json             letzte Kurse aller Werte (alle 15 Min.)
daten/fundamental/<ticker>.json      Kennzahlen je Periode, Währung, Quelle
daten/schaetzungen/<ticker>.json     EPS/Umsatz-Schätzungen, Kursziele, Anzahl Analysten
daten/termine/earnings.json, wirtschaft.json
daten/makro/<serie>.parquet          mit Veröffentlichungsdatum
daten/smart_money/insider.json, 13f.json, etf_fluesse.json
daten/news/news.json                 Schlagzeile, Link, Quelle, Zeit, Sentiment (falls vorhanden)
daten/analysten/<modul>.json         regelbasierte Berichte: fakten / schaetzungen / interpretation / quellen
daten/status/abrufe.json             jeder Abruf: Quelle, Zeit, Status, Dauer (Datenstatus-Panel)
```

Veröffentlicht werden nur verschlüsselte Pakete `pakete/<modul>.enc` plus die App.

---

## 5. Module

| Modul | Umsetzung | Machbarkeit (gratis) |
|---|---|---|
| Market Overview | S&P 500, Nasdaq, DAX, SMI, VIX, DXY, Cockpit | ✅ |
| Global Markets | Aktien, Anleihen, FX, Rohstoffe, Krypto | ✅ |
| Macro Dashboard | CPI, PCE, NFP, Fed, EZB, SNB, Wirtschaftskalender | ✅ |
| Stock Screener | Value, Growth, Momentum, Dividende, Filter im Browser | ⚠️ Universum begrenzt (S&P 500 + SMI + Watchlist), nachts aktualisiert |
| Smart Money | 13F, Insider, ETF-Flows | ✅ / ⚠️ ETF-Flows nur Schätzung |
| News Terminal | Schlagzeilen, Sentiment (Alpha Vantage), regelbasierte Zusammenfassung | ✅ (keine KI-Texte) |
| Earnings Calendar | Termine, Schätzungen, Überraschungen | ✅ |
| Portfolio | Performance, Exposure, Risiko | ✅ mit privater Datenhaltung (Phase 4) |
| Technical Analysis | RSI, MACD, gleitende Durchschnitte, Pivots; VWAP nur Tages-VWAP-Annäherung | ✅ / ⚠️ |
| Research | regelbasierte Analysten (siehe 6) | ✅ |

---

## 6. Analysten ohne Kosten (regelbasiert)

Sechs Analysten mit fester Logik statt KI, damit nichts erfunden wird und nichts kostet:

| Analyst | Fakten | Schätzungen | Interpretation (regelbasiert, gekennzeichnet) |
|---|---|---|---|
| Equity Research | Bewertung, Wachstum, Margen, Bilanz | Konsens, Kursziel | Punkte-Scoring (wie im Aktienvergleich), Stärken/Schwächen, Bear-Case-Liste aus Risikoindikatoren |
| Macro Research | Inflation, Arbeitsmarkt, Zinsen, Liquidität | Markterwartung über 2J-Rendite | Regime-Einordnung (z. B. "Inflation steigt, Arbeitsmarkt kühlt ab") |
| Technical Analysis | Kurse, Indikatoren | – | Trendpunkte, Signale, Unterstützungen/Widerstände |
| Earnings Analysis | Ist-Zahlen, Termine | Schätzungen, implizite Bewegung aus Optionen | Überraschungs-Historie, Erwartung vs. Ergebnis |
| News & Sentiment | Schlagzeilen | Sentiment-Werte (Alpha Vantage) | Themen-Häufung, Stimmungsverlauf |
| Portfolio Risk | Positionen, Kurse | – | Klumpenrisiken, Beta, Korrelation, Währungsanteile |

Jeder Bericht trennt die drei Teile sichtbar und nennt Quelle und Stand jeder Zahl.
**Später optional:** Wenn ein Budget vorhanden ist, kann eine KI (z. B. Claude) die Interpretation ergänzen. Die Schnittstelle wird dafür vorbereitet.

---

## 7. Fahrplan

| Phase | Ergebnis | Von dir benötigt |
|---|---|---|
| **1. Fundament** | Provider-Schicht (Fallbacks, Rate-Limits, Normalisierung, Herkunft), Dateispeicher, Verschlüsselung der Datenpakete, 15-Minuten-Lauf, Tests | Gratis-Schlüssel für Finnhub, FMP und Alpha Vantage als GitHub-Secrets |
| **2. Oberfläche** | React-Terminal: Panels, Befehlszeile, Tastenkürzel, Watchlists, Market Overview, Global Markets, Datenstatus | – |
| **3. Daten-Module** | Macro Dashboard, Earnings Calendar, Technical Analysis, News Terminal, Krypto | – |
| **4. Fortgeschritten** | Screener, Smart Money, Portfolio | Entscheidung zur privaten Portfolio-Ablage |
| **5. Analysten** | 6 regelbasierte Analysten | – |
| **6. Umstieg** | Alte Seiten (Anthropic, Vergleich, Themen, Positionierung) als Module übernommen, alte Website abgeschaltet | – |

Bis Phase 6 läuft die heutige Website unverändert weiter.

### Portfolio privat halten (Entscheidung in Phase 4)
- **a) Nur im Browser:** Eingabe bzw. CSV-Import (z. B. Export aus Parqet) direkt in der App, gespeichert auf dem jeweiligen Gerät. Gratis, aber pro Gerät.
- **b) Als GitHub-Secret:** CSV-Inhalt als verschlüsseltes Secret, wird im Actions-Lauf verarbeitet. Gratis, Änderungen etwas umständlich.
- **c) GitHub Pro (4 USD/Monat):** privates Repository mit veröffentlichter Seite. Liegt innerhalb von 5 CHF, ist aber nicht nötig.
