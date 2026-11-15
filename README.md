# Market Terminal – Anleitung

Deine persönliche Markt-Website: Kurse, Charts, Makro, Positionierung, Themen, Termine und News –
auf Knopfdruck aktualisiert und im Browser geöffnet. Läuft komplett auf deinem PC, nur mit Gratis-Daten.

---

## 1. Einmalig einrichten (ca. 10 Minuten)

### a) Python installieren
1. Gehe auf **python.org/downloads** und klicke auf den gelben Knopf **«Download Python 3.x»**.
2. Öffne die heruntergeladene Datei.
3. **Ganz wichtig:** Im ersten Fenster unten das Kästchen **«Add python.exe to PATH»** ankreuzen.
4. Auf **«Install Now»** klicken und warten, bis «Setup was successful» erscheint.

> Schon installiert, aber ohne das Kästchen? Installer nochmals öffnen → «Modify» → weiter →
> «Add Python to environment variables» ankreuzen → Install.

### b) Projekt entpacken
1. Die ZIP-Datei `market-terminal.zip` mit der rechten Maustaste anklicken → **«Alle extrahieren…»**.
2. Als Ziel z. B. `Dokumente` wählen. Es entsteht der Ordner `Dokumente\market-terminal`.

### c) Pakete installieren
1. Im Ordner `market-terminal` auf **`1_einrichten.bat`** doppelklicken.
2. Falls Windows warnt («Der Computer wurde durch Windows geschützt»): **«Weitere Informationen»** → **«Trotzdem ausführen»**.
   (Die Warnung erscheint bei allen selbst erstellten Startdateien.)
3. Warten, bis **«FERTIG!»** erscheint, dann eine Taste drücken.

### d) (Optional) FRED-Schlüssel eintragen
Das Terminal funktioniert auch ohne Schlüssel. Mit Schlüssel werden FRED-Daten über die offizielle Schnittstelle geladen.
1. Im Ordner die Datei **`.env`** mit der rechten Maustaste anklicken → **«Öffnen mit»** → **«Editor»**.
2. Hinter `FRED_API_KEY=` deinen Schlüssel einfügen (aus `Dokumente\fred-schluessel.txt`), ohne Leerzeichen:
   `FRED_API_KEY=abcd1234...`
3. Speichern (**Ctrl + S**) und schliessen. **Diese Datei nie weitergeben.**

---

## 2. Starten

Doppelklick auf **`2_terminal_starten.bat`**. Nach einigen Sekunden öffnet sich die Website im Browser.

- Beim ersten Start dauert es etwa 30–60 Sekunden, danach meist nur wenige Sekunden
  (geladene Daten werden zwischengespeichert: Kurse 4 Stunden, Makro 12 Stunden, News 1 Stunde).
- Die Website liegt im Ordner `website\`. Du kannst `website\index.html` auch direkt öffnen (zeigt den letzten Stand).
- **Als PDF speichern:** Im Browser **Ctrl + P** → Ziel «Als PDF speichern» → unter «Weitere Einstellungen»
  **«Hintergrundgrafiken»** ankreuzen → Speichern.

**Für Fortgeschrittene** (Eingabeaufforderung im Projektordner):
```
.venv\Scripts\python main.py --neu-laden       (alles frisch laden, Zwischenspeicher ignorieren)
.venv\Scripts\python main.py --nicht-oeffnen   (nur aktualisieren, Browser nicht öffnen)
```

---

## 3. Online-Version (Handy, Tablet, unterwegs)

Die Website wird zusätzlich jeden Morgen automatisch auf einem Gratis-Server von GitHub erstellt
und passwortgeschützt veröffentlicht – dein PC muss dafür nicht laufen.

- **Adresse:** `https://glennlucian-hue.github.io/market-terminal/`
- **Zeitpunkt:** täglich ca. 6:00 Uhr (Sommerzeit 7:00 Uhr), GitHub startet teils etwas verspätet.
- **Sofort aktualisieren:** auf github.com im Repository → Reiter **Actions** → links **«Website aktualisieren»**
  → rechts **«Run workflow»** → grüner Knopf **«Run workflow»**. Nach ca. 2–3 Minuten ist die Seite neu.
- **Passwort ändern:** Repository → **Settings** → **Secrets and variables** → **Actions** →
  `SITE_PASSWORT` → Stift-Symbol → neues Passwort → **Update secret**. Danach einmal «Run workflow».
- **Aufs Handy-Startbildschirm:** Adresse im Handy-Browser öffnen →
  iPhone: Teilen-Symbol → «Zum Home-Bildschirm» · Android: Menü ⋮ → «Zum Startbildschirm hinzufügen».
- **Watchlist online ändern:** im Repository auf `watchlist.yaml` klicken → Stift-Symbol (Edit) →
  ändern → **«Commit changes»**. Die Website wird dann automatisch neu gebaut.
- Fehlgeschlagene Läufe meldet GitHub per E-Mail. Details im Reiter **Actions** (rotes ✖ anklicken).

Der Programmcode ist öffentlich einsehbar (Gratis-Bedingung von GitHub Pages), enthält aber keine Schlüssel.
Die Website-Inhalte selbst sind mit deinem Passwort verschlüsselt (StatiCrypt, AES-256).

## 4. Die Seiten

| Seite | Inhalt |
|---|---|
| **Übersicht** | Automatische Zusammenfassung, Top-News, grösste Bewegungen, Schlüsselmärkte, Termine der Woche |
| **Märkte** | Ganze Watchlist mit 1T/1W/1M/YTD/1J und Charts (Knöpfe 1M bis 2J) |
| **Makro & Zinsen** | US-Zinskurve, Renditen, Leitzins, Inflation, Arbeitsmarkt, Kreditrisiko, Liquidität |
| **Positionierung** | CTA-Modell (eigene Schätzung) mit Auslöser-Niveaus, CFTC-Daten zu S&P 500, Gold, Öl |
| **Themen** | Fed, Gold/Bitcoin/Liquidität, Nvidia & KI, Strait of Hormuz, CTA, Schweiz – mit Daten und Schlagzeilen |
| **Termine** | Fed-Reden, FOMC, Quartalszahlen der nächsten 3 Wochen (Schweizer Zeit) |
| **News** | Alle Schlagzeilen, filterbar nach Thema |
| **Datenstatus** | Welche Daten geladen wurden und was fehlgeschlagen ist |

---

## 5. Watchlist ändern (`watchlist.yaml`)

1. `watchlist.yaml` mit der rechten Maustaste → «Öffnen mit» → «Editor».
2. Kürzel auf **finance.yahoo.com** suchen (steht in Klammern, z. B. «Novartis AG (NOVN.SW)»).
3. Einen bestehenden Eintrag kopieren und anpassen, z. B. unter `Aktien`:
   ```yaml
         - name: Novartis
           ticker: "NOVN.SW"
   ```
4. Speichern und Terminal neu starten.

**Regeln:** Einrückung mit Leerzeichen (nie Tabulator), genau wie die Zeilen darüber.
Ticker immer in `"Anführungszeichen"`. Mit `band: true` erscheint ein Wert zusätzlich im Kursband oben.

## 6. Themen ändern (`themen.yaml`)

Jedes Thema bekommt automatisch einen eigenen Newsfeed. Neues Thema: einen Block kopieren und anpassen:
```yaml
  - id: china
    titel: China & Konjunktur
    beschreibung: Stimulus, Immobilien und Exporte.
    suchbegriffe:
      - 'China stimulus economy'
      - '"PBOC" OR "People''s Bank of China"'
```
Suchbegriffe in einfache Anführungszeichen `'...'` setzen. Auf Englisch gibt es mehr Treffer.

---

## 7. Probleme lösen

| Problem | Lösung |
|---|---|
| «Python wurde nicht gefunden» | Python installieren und **«Add python.exe to PATH»** ankreuzen (Abschnitt 1a). Danach PC neu starten. |
| Fenster geht sofort zu | Eingabeaufforderung öffnen (Windows-Taste, `cmd`), in den Ordner wechseln (`cd Dokumente\market-terminal`) und `2_terminal_starten.bat` eintippen – dann bleibt die Meldung sichtbar. |
| «PROBLEM MIT EINER KONFIGURATIONSDATEI … Zeile 42» | In der genannten Datei die Zeile prüfen: Einrückung, Tabulator statt Leerzeichen, fehlende Anführungszeichen. |
| Ein Wert zeigt «Daten nicht verfügbar» | Seite **Datenstatus** ansehen. «Ticker falsch geschrieben?» → Kürzel auf finance.yahoo.com prüfen. Sonst später nochmals versuchen. |
| Charts erscheinen nicht | Die Website braucht Internet, um die Chart-Bibliothek zu laden. Verbindung prüfen. |
| Alte Zahlen | `--neu-laden` verwenden (siehe Abschnitt 2) oder den Ordner `cache` löschen. |
| Online-Seite zeigt alten Stand | Reiter **Actions** auf github.com prüfen: rotes ✖ = Fehler (anklicken für Details). Im Handy-Browser neu laden. |
| Alles kaputt? | Ordner `.venv` löschen und `1_einrichten.bat` nochmals ausführen. |

---

## 8. Datenquellen

| Quelle | Daten | Hinweis |
|---|---|---|
| Yahoo Finance (via yfinance) | Kurse, Bewertungen, Termine Quartalszahlen | inoffizielle Schnittstelle, teils verzögert |
| FRED (St. Louis Fed) | Zinsen, Inflation, Arbeitsmarkt, Liquidität | mit oder ohne API-Key |
| CFTC Commitments of Traders | Positionierung in Futures | wöchentlich, Stichtag Dienstag |
| IMF PortWatch | Schiffsdurchfahrten Strait of Hormuz | ca. 1 Woche Verzögerung |
| Federal Reserve | Reden, Termin-Kalender | offiziell |
| Google News | Schlagzeilen zu den Themen | nur Titel + Link; Artikel teils kostenpflichtig |

Die Modelle (CTA, Net Liquidity, Liquiditäts-Check) sind vereinfachte, eigene Schätzungen.
Persönlicher Research, keine Anlageberatung.

## 9. Ordnerstruktur

```
market-terminal\
  1_einrichten.bat          einmalig: Pakete installieren
  2_terminal_starten.bat    Website aktualisieren und öffnen
  watchlist.yaml            deine Werte
  themen.yaml               deine Themen
  .env                      deine Schlüssel (geheim)
  main.py                   Startprogramm
  terminal\                 Programmcode (Datenquellen, Analysen, Charts, Website)
  vorlagen\                 Layout der Seiten (HTML/CSS)
  website\                  die erzeugte Website (wird jedes Mal neu gebaut)
  cache\                    Zwischenspeicher (darf gelöscht werden)
```
