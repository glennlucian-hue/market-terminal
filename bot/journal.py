"""Papier-Journal (signale_journal.csv) und optional Telegram (TELEGRAM_TOKEN, TELEGRAM_CHAT in .env)."""
import csv
import os
from pathlib import Path

import requests

DATEI = Path("signale_journal.csv")


def melde(sig, instrument: str):
    neu = not DATEI.exists()
    with DATEI.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neu:
            w.writerow(["zeit", "instrument", "richtung", "einstieg", "stop", "ziel", "crv", "stueck", "risiko",
                        "qualitaet", "gruende"])
        w.writerow([sig.zeit.isoformat(), instrument, sig.richtung, sig.einstieg, sig.stop, sig.ziel, sig.rr,
                    sig.stueck, sig.risiko, sig.punkte, " | ".join(sig.gruende + sig.warnungen)])
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT")
    if token and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": sig.text(instrument)}, timeout=10)
        except Exception as e:
            print(f"  Telegram fehlgeschlagen: {e}")
