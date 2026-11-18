// Zahlen und Zeiten im Schweizer Format, Zeiten in Zürcher Zeit.

export function zahl(x: number | null | undefined, stellen?: number): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const s = stellen ?? (Math.abs(x) < 10 ? 4 : Math.abs(x) < 10000 ? 2 : 0);
  return x.toLocaleString("de-CH", { minimumFractionDigits: s, maximumFractionDigits: s }).replace(/'/g, "’");
}

export function prozent(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const pfeil = x > 0 ? "▲" : x < 0 ? "▼" : "■";
  return `${pfeil} ${x > 0 ? "+" : ""}${x.toFixed(2)}%`;
}

export function klasse(x: number | null | undefined): string {
  if (x === null || x === undefined || Math.abs(x) < 1e-9) return "neutral";
  return x > 0 ? "plus" : "minus";
}

export function grossbetrag(x: number | null | undefined): string {
  if (!x) return "–";
  if (x >= 1e12) return `${zahl(x / 1e12, 2)} Bio.`;
  if (x >= 1e9) return `${zahl(x / 1e9, 1)} Mrd.`;
  return `${zahl(x / 1e6, 0)} Mio.`;
}

export function zeit(iso: string | null | undefined, mitDatum = true): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Tageswerte (Schlusskurse) haben keine Uhrzeit: nur das Datum zeigen
  if (/T00:00:00(\.000)?(\+00:00|Z)$/.test(iso)) return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
  const opt: Intl.DateTimeFormatOptions = { timeZone: "Europe/Zurich", hour: "2-digit", minute: "2-digit" };
  if (mitDatum) Object.assign(opt, { day: "2-digit", month: "2-digit" });
  return d.toLocaleString("de-CH", opt);
}

export function datum(iso: string): string {
  const [j, m, t] = iso.slice(0, 10).split("-");
  const tag = new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("de-CH", { weekday: "short" });
  return `${tag} ${t}.${m}.${j.slice(2)}`;
}

export const ARTEN: Record<string, string> = {
  echtzeit: "Echtzeit", verzoegert: "verzögert ~15 Min.", schluss: "Schlusskurs", historisch: "historisch",
  schaetzung: "Schätzung", eigene_berechnung: "eigene Berechnung", offiziell: "offiziell", termin: "Termin",
};
