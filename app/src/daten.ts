// Laden aller Datenpakete. Jeder Wert behält Quelle, Stand und Art – so wie im Python-Kern erzeugt.
import { entschluesseln, type Huelle } from "./krypto";

export interface Kurs {
  ok: boolean;
  quelle: string | null;
  art: string | null;
  abgerufen: string;
  daten: { symbol: string; kurs: number; veraenderung_pct: number | null; vortag: number | null; stand: string | null; waehrung: string | null } | null;
  versuche: { quelle: string; ok: boolean; grund: string }[];
}
export interface Historie { t: string[]; c: number[]; waehrung: string | null; quelle: string; art: string }
export interface WatchGruppe { gruppe: string; werte: { ticker: string; name: string; art: string; quelle: string }[] }
export interface Termin { datum: string; ereignis: string; wichtig: boolean; original?: string }
export interface Earnings { symbol: string; datum: string; zeit: string; eps_schaetzung: number | null; eps_ist: number | null }
export interface Bewegung { symbol: string; kurs: number | null; veraenderung_pct: number | null; volumen: number | null }
export interface Coin { symbol: string; name: string; kurs: number; veraenderung_24h_pct: number | null; veraenderung_7d_pct: number | null; marktwert: number | null; rang: number; stand: string }
export interface Status { quelle: string; ok: boolean; grund: string; abgerufen: string }
export interface Detail {
  ticker: string; name: string; erstellt: string; waehrungshinweis?: string;
  profil: { sektor: string | null; branche: string | null; land: string | null; waehrung: string | null; mitarbeiter: number | null };
  fundamental: { werte: Record<string, number | null>; quelle: string | null; grund?: string };
  kursziel: { mittel?: number; median?: number; hoch?: number; tief?: number; quelle?: string; grund?: string };
  empfehlung: { kaufen?: number; halten?: number; verkaufen?: number; anzahl?: number; tendenz?: string | null; banken?: string[]; quelle?: string; grund?: string };
  einstufungen: { liste: { datum: string; firma: string; von: string | null; zu: string | null; aktion: string | null }[]; quelle?: string; grund?: string };
  schaetzungen: { jahre: { jahr: string; eps: number | null; umsatz?: number | null; analysten?: number | null }[]; quelle?: string | null; grund?: string | null };
  technik: { grund?: string; kurs?: number; sma50?: number | null; sma200?: number | null; abstand200?: number | null; rsi?: number;
    macd_positiv?: boolean; trend?: string; trendpunkte?: number; signale?: string[]; unterstuetzung?: number | null; widerstand?: number | null;
    hoch52?: number; tief52?: number; vom_hoch?: number; pivots?: Record<string, number>; quelle?: string;
    sma50_reihe?: (number | null)[]; sma200_reihe?: (number | null)[]; reihe_daten?: string[] };
}

export interface Daten {
  erstellt: string;
  kurse: Record<string, Kurs>;
  historie: Record<string, Historie>;
  watchlist: WatchGruppe[];
  wirtschaftstermine: Termin[];
  earnings: Earnings[];
  top_bewegungen: { stand: string; gewinner: Bewegung[]; verlierer: Bewegung[]; meistgehandelt: Bewegung[] } | null;
  krypto: { markt: { marktwert_usd: number; veraenderung_24h_pct: number; dominanz_pct: Record<string, number>; stand: string } | null; coins: Coin[]; fehler: string | null } | null;
  status: Status[];
  details: Record<string, Detail>;
  fehlend: string[];               // Pakete, die nicht geladen werden konnten
}

const PAKETE = ["kurse", "historie", "watchlist", "wirtschaftstermine", "earnings", "top_bewegungen", "krypto", "details", "status"] as const;
const BASIS = new URL("../pakete/", window.location.href);

export class FalschesPasswort extends Error {}

export async function ladeDaten(passwort: string): Promise<Daten> {
  const index = await fetch(new URL("index.json", BASIS), { cache: "no-store" });
  if (!index.ok) throw new Error("Datenpakete nicht gefunden – wurde die Website schon mit der neuen Version gebaut?");
  const { erstellt } = (await index.json()) as { erstellt: string };
  const daten: Record<string, unknown> = { erstellt, fehlend: [] as string[] };
  // Zuerst ein Paket entschlüsseln: schlägt es fehl, ist das Passwort falsch
  for (const [i, name] of PAKETE.entries()) {
    try {
      const r = await fetch(new URL(`${name}.json.enc`, BASIS), { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const inhalt = await entschluesseln<{ inhalt: unknown }>((await r.json()) as Huelle, passwort);
      daten[name] = inhalt.inhalt;
    } catch (e) {
      if (i === 0 && e instanceof DOMException) throw new FalschesPasswort("Falsches Passwort");
      (daten.fehlend as string[]).push(name);
      daten[name] = name === "kurse" || name === "historie" || name === "details" ? {} : name === "top_bewegungen" || name === "krypto" ? null : [];
    }
  }
  return daten as unknown as Daten;
}
