// Watchlist-Tabelle: sortierbar, Klick auf eine Zeile öffnet den Chart. Jede Zeile zeigt ihre Quelle.
import { useMemo, useState } from "react";
import type { Daten } from "../daten";
import { klasse, prozent, zahl, zeit } from "../format";
import { KeineDaten, Panel } from "../Panel";

interface Props {
  daten: Daten;
  ticker: string[];
  listenName: string;
  ausgewaehlt: string;
  waehle: (t: string) => void;
}

type Spalte = "name" | "kurs" | "veraenderung" | "stand";

export function KurseTabelle({ daten, ticker, listenName, ausgewaehlt, waehle }: Props) {
  const [sort, setSort] = useState<{ spalte: Spalte; ab: boolean } | null>(null);
  const namen = useMemo(() => {
    const m: Record<string, { name: string; art: string; gruppe: string }> = {};
    for (const g of daten.watchlist) for (const w of g.werte) m[w.ticker] = { name: w.name, art: w.art, gruppe: g.gruppe };
    return m;
  }, [daten.watchlist]);

  const zeilen = useMemo(() => {
    const z = ticker.map((t) => {
      const k = daten.kurse[t];
      return { t, info: namen[t], k, wert: k?.daten?.kurs ?? null, ver: k?.daten?.veraenderung_pct ?? null, stand: k?.daten?.stand ?? "" };
    });
    if (!sort) return z;
    const fak = sort.ab ? -1 : 1;
    return [...z].sort((a, b) => {
      const va = sort.spalte === "name" ? (a.info?.name ?? a.t) : sort.spalte === "kurs" ? a.wert : sort.spalte === "veraenderung" ? a.ver : a.stand;
      const vb = sort.spalte === "name" ? (b.info?.name ?? b.t) : sort.spalte === "kurs" ? b.wert : sort.spalte === "veraenderung" ? b.ver : b.stand;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * fak;
    });
  }, [ticker, daten.kurse, namen, sort]);

  const kopf = (s: Spalte, text: string, links = false) => (
    <th className={links ? "links" : ""} onClick={() => setSort(sort?.spalte === s ? { spalte: s, ab: !sort.ab } : { spalte: s, ab: s !== "name" })}>
      {text}{sort?.spalte === s ? (sort.ab ? " ▼" : " ▲") : ""}
    </th>
  );
  const quellen = [...new Set(zeilen.map((z) => z.k?.quelle).filter(Boolean))].join(", ");

  return (
    <Panel titel={`Watchlist · ${listenName}`} quelle={quellen || "–"} stand={daten.erstellt} art="verzoegert"
           rechts={<span className="grau">{zeilen.length} Werte</span>}>
      {zeilen.length === 0 ? <KeineDaten grund="Liste ist leer – mit «+TICKER» in der Befehlszeile hinzufügen" /> : (
        <table className="tabelle">
          <thead><tr>{kopf("name", "Wert", true)}{kopf("kurs", "Kurs")}{kopf("veraenderung", "1 Tag")}{kopf("stand", "Stand")}<th>Quelle</th></tr></thead>
          <tbody>
            {zeilen.map((z) => {
              const zins = z.info?.art === "rendite";
              return (
                <tr key={z.t} className={z.t === ausgewaehlt ? "aktiv" : ""} onClick={() => waehle(z.t)}>
                  <td className="links">{z.info?.name ?? z.t}<span className="tk">{z.t}</span></td>
                  {z.k?.ok ? (<>
                    <td className="fett">{zahl(z.wert, zins ? 2 : undefined)}<span className="whg">{zins ? "%" : z.k.daten?.waehrung ?? ""}</span></td>
                    <td className={klasse(z.ver)}>{zins ? "–" : prozent(z.ver)}</td>
                    <td className="grau">{zeit(z.stand)}</td>
                    <td className="grau">{z.k.quelle}</td>
                  </>) : (
                    <td colSpan={4} className="minus links">keine Daten{z.k ? ` (${z.k.versuche.map((v) => v.quelle).join(", ")})` : " (nicht in watchlist.yaml)"}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
