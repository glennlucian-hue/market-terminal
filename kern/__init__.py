"""Kern des Market Terminal 2.0: Datenquellen-Schicht, Herkunftsangaben, Verschlüsselung.

Grundregeln (siehe ARCHITEKTUR.md):
  - Keine erfundenen Daten. Fehlt etwas, wird das ausdrücklich gemeldet.
  - Jeder Wert trägt Quelle, Stand (Zeitpunkt des Werts), Abrufzeit und Art (verzögert, Schluss, Schätzung, ...).
  - Zeiten intern in UTC, Währungen als ISO-Code.
  - API-Schlüssel nur aus Umgebungsvariablen (GitHub-Secrets bzw. .env), nie im Code.
"""
