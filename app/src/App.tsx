// Anmeldung mit dem Website-Passwort, danach das Terminal. Daten werden alle 5 Minuten auf Neues geprüft.
import { useCallback, useEffect, useState } from "react";
import { FalschesPasswort, ladeDaten, type Daten } from "./daten";
import { Terminal } from "./Terminal";

const PW_KEY = "mt-passwort";

function gespeichertesPasswort(): string {
  try { return sessionStorage.getItem(PW_KEY) ?? localStorage.getItem(PW_KEY) ?? ""; } catch { return ""; }
}

export function App() {
  const [passwort, setPasswort] = useState(gespeichertesPasswort);
  const [eingabe, setEingabe] = useState("");
  const [merken, setMerken] = useState(false);
  const [daten, setDaten] = useState<Daten | null>(null);
  const [fehler, setFehler] = useState("");
  const [laedt, setLaedt] = useState(false);

  const laden = useCallback(async (pw: string, merke = false) => {
    setLaedt(true); setFehler("");
    try {
      const d = await ladeDaten(pw);
      setDaten(d); setPasswort(pw);
      try { sessionStorage.setItem(PW_KEY, pw); if (merke) localStorage.setItem(PW_KEY, pw); } catch { /* ohne Speichern */ }
    } catch (e) {
      setDaten(null); setPasswort("");
      setFehler(e instanceof FalschesPasswort ? "Falsches Passwort." : `Daten konnten nicht geladen werden: ${(e as Error).message}`);
      try { sessionStorage.removeItem(PW_KEY); localStorage.removeItem(PW_KEY); } catch { /* egal */ }
    } finally { setLaedt(false); }
  }, []);

  useEffect(() => { if (passwort && !daten) void laden(passwort); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Alle 5 Minuten prüfen, ob GitHub neue Daten veröffentlicht hat
  useEffect(() => {
    if (!daten || !passwort) return;
    const id = window.setInterval(async () => {
      try {
        const r = await fetch(new URL("../pakete/index.json", window.location.href), { cache: "no-store" });
        const { erstellt } = await r.json();
        if (erstellt !== daten.erstellt) setDaten(await ladeDaten(passwort));
      } catch { /* nächster Versuch in 5 Min. */ }
    }, 5 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [daten, passwort]);

  const abmelden = () => {
    try { sessionStorage.removeItem(PW_KEY); localStorage.removeItem(PW_KEY); } catch { /* egal */ }
    setDaten(null); setPasswort("");
  };

  if (daten) return <Terminal daten={daten} abmelden={abmelden} neuLaden={() => void laden(passwort)} />;

  return (
    <div className="anmeldung">
      <form onSubmit={(e) => { e.preventDefault(); void laden(eingabe, merken); }}>
        <div className="marke">MARKET TERMINAL 2.0</div>
        <p className="grau">Persönlicher Markt-Research. Die Daten sind verschlüsselt und werden erst auf diesem Gerät mit deinem Passwort geöffnet.</p>
        <input type="password" autoFocus value={eingabe} placeholder="Passwort" onChange={(e) => setEingabe(e.target.value)} />
        <label><input type="checkbox" checked={merken} onChange={(e) => setMerken(e.target.checked)} /> Auf diesem Gerät angemeldet bleiben</label>
        <button type="submit" disabled={laedt || !eingabe}>{laedt ? "Entschlüssle …" : "Öffnen"}</button>
        {fehler && <p className="minus">{fehler}</p>}
        <p className="vermerk"><a href="../index.html">Zur bisherigen Website</a> · Keine Anlageberatung</p>
      </form>
    </div>
  );
}
