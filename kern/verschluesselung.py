"""Verschlüsselung der Datenpakete mit dem Website-Passwort.

Verfahren (Standard, im Browser mit WebCrypto entschlüsselbar):
  Schlüssel = PBKDF2-HMAC-SHA256(Passwort, zufälliges Salz, 310'000 Durchgänge) -> 256 Bit
  Daten     = AES-256-GCM(Schlüssel, zufälliger 12-Byte-IV, JSON-Text)
Ergebnis ist eine kleine JSON-Hülle mit Salz, IV, Durchgängen und verschlüsselten Daten (Base64).
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DURCHGAENGE = 310_000


def _schluessel(passwort: str, salz: bytes, durchgaenge: int) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salz, iterations=durchgaenge).derive(passwort.encode("utf-8"))


def verschluesseln(daten, passwort: str) -> dict:
    if not passwort:
        raise ValueError("Kein Passwort – Datenpakete werden nie unverschlüsselt veröffentlicht.")
    salz, iv = os.urandom(16), os.urandom(12)
    klartext = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    geheim = AESGCM(_schluessel(passwort, salz, DURCHGAENGE)).encrypt(iv, klartext, None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return {"format": "mt-aesgcm-1", "kdf": "PBKDF2-SHA256", "durchgaenge": DURCHGAENGE,
            "salz": b64(salz), "iv": b64(iv), "daten": b64(geheim)}


def entschluesseln(huelle: dict, passwort: str):
    b = lambda s: base64.b64decode(s)  # noqa: E731
    klartext = AESGCM(_schluessel(passwort, b(huelle["salz"]), huelle["durchgaenge"])).decrypt(
        b(huelle["iv"]), b(huelle["daten"]), None)
    return json.loads(klartext)
