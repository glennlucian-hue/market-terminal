// Entschlüsselung der Datenpakete im Browser (Gegenstück zu kern/verschluesselung.py).
// Verfahren: PBKDF2-SHA256 (Passwort + Salz) -> AES-256-GCM. Alles läuft lokal, nichts verlässt das Gerät.

export interface Huelle {
  format: string;
  durchgaenge: number;
  salz: string;
  iv: string;
  daten: string;
}

const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

export async function entschluesseln<T>(huelle: Huelle, passwort: string): Promise<T> {
  if (huelle.format !== "mt-aesgcm-1") throw new Error(`Unbekanntes Paketformat ${huelle.format}`);
  const basis = await crypto.subtle.importKey("raw", new TextEncoder().encode(passwort), "PBKDF2", false, ["deriveKey"]);
  const schluessel = await crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: b64(huelle.salz), iterations: huelle.durchgaenge },
    basis, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
  // Wirft einen Fehler, wenn das Passwort falsch ist (Prüfsumme stimmt nicht)
  const klar = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(huelle.iv) }, schluessel, b64(huelle.daten));
  return JSON.parse(new TextDecoder().decode(klar)) as T;
}
