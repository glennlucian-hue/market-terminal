// Weitere Panels: Termine, US-Top-Bewegungen, Krypto, Datenstatus.
import { Fragment, useState } from "react";
import type { Daten } from "../daten";
import { datum, grossbetrag, klasse, prozent, zahl, zeit } from "../format";
import { KeineDaten, Panel } from "../Panel";

export function Termine({ daten }: { daten: Daten }) {
  const heute = new Date().toISOString().slice(0, 10);
  const liste = [
    ...daten.wirtschaftstermine.map((t) => ({ datum: t.datum, art: "Makro", text: t.ereignis, zusatz: "USA", wichtig: t.wichtig })),
    ...daten.earnings.map((e) => ({ datum: e.datum, art: "Zahlen", text: e.symbol, wichtig: ["NVDA", "AAPL", "MSFT", "ANT"].includes(e.symbol),
      zusatz: [e.zeit, e.eps_schaetzung !== null ? `EPS-Schätzung ${zahl(e.eps_schaetzung, 2)}` : ""].filter(Boolean).join(" · ") })),
  ].filter((t) => t.datum >= heute).sort((a, b) => a.datum.localeCompare(b.datum));
  let vorher = "";
  return (
    <Panel titel="Termine (21 Tage)" quelle="FRED (Wirtschaftsdaten), Finnhub (Quartalszahlen)" stand={daten.erstellt} art="termin">
      {liste.length === 0 ? <KeineDaten grund="Keine Termine geladen" /> : (
        <table className="tabelle"><tbody>
          {liste.map((t, i) => {
            const neu = t.datum !== vorher; vorher = t.datum;
            return (<Fragment key={i}>{neu && <tr className="tageszeile"><td colSpan={3}>{datum(t.datum)}</td></tr>}
              <tr className={t.wichtig ? "wichtig" : ""}>
                <td className="links"><span className={`etikett ${t.art === "Makro" ? "makro" : "zahlen"}`}>{t.art}</span></td>
                <td className="links fett">{t.text}</td><td className="links grau">{t.zusatz}</td></tr></Fragment>);
          })}
        </tbody></table>
      )}
    </Panel>
  );
}

export function TopBewegungen({ daten }: { daten: Daten }) {
  const [reiter, setReiter] = useState<"gewinner" | "verlierer" | "meistgehandelt">("gewinner");
  const tb = daten.top_bewegungen;
  return (
    <Panel titel="US-Top-Bewegungen" quelle="Alpha Vantage (ab 5 USD)" stand={null} art="verzoegert" rechts={
      <span className="knopfgruppe">{(["gewinner", "verlierer", "meistgehandelt"] as const).map((r) =>
        <button key={r} className={r === reiter ? "aktiv" : ""} onClick={() => setReiter(r)}>{r === "meistgehandelt" ? "Volumen" : r[0].toUpperCase() + r.slice(1)}</button>)}</span>}>
      {!tb ? <KeineDaten grund="Alpha Vantage nicht verfügbar" /> : (<>
        <div className="mini-info">Stand {tb.stand}</div>
        <table className="tabelle"><thead><tr><th className="links">Symbol</th><th>Kurs</th><th>Veränd.</th><th>Volumen</th></tr></thead>
          <tbody>{tb[reiter].slice(0, 12).map((x) => (
            <tr key={x.symbol}><td className="links fett">{x.symbol}</td><td>{zahl(x.kurs, 2)}</td>
              <td className={klasse(x.veraenderung_pct)}>{prozent(x.veraenderung_pct)}</td>
              <td className="grau">{zahl((x.volumen ?? 0) / 1e6, 1)} Mio.</td></tr>))}
          </tbody></table></>)}
    </Panel>
  );
}

export function Krypto({ daten }: { daten: Daten }) {
  const k = daten.krypto;
  return (
    <Panel titel="Krypto-Markt" quelle="CoinGecko" stand={k?.markt?.stand} art="verzoegert"
           rechts={k?.markt ? <span className={klasse(k.markt.veraenderung_24h_pct)}>Gesamt {grossbetrag(k.markt.marktwert_usd)} USD {prozent(k.markt.veraenderung_24h_pct)}</span> : null}>
      {!k || !k.coins.length ? <KeineDaten grund={k?.fehler ?? "CoinGecko nicht verfügbar"} /> : (
        <table className="tabelle"><thead><tr><th className="links">Coin</th><th>Kurs USD</th><th>24 h</th><th>7 T.</th><th>Marktwert</th></tr></thead>
          <tbody>{k.coins.map((c) => (
            <tr key={c.symbol}><td className="links">{c.name}<span className="tk">{c.symbol}</span></td><td className="fett">{zahl(c.kurs)}</td>
              <td className={klasse(c.veraenderung_24h_pct)}>{prozent(c.veraenderung_24h_pct)}</td>
              <td className={klasse(c.veraenderung_7d_pct)}>{prozent(c.veraenderung_7d_pct)}</td>
              <td className="grau">{grossbetrag(c.marktwert)}</td></tr>))}
          </tbody></table>)}
    </Panel>
  );
}

export function Datenstatus({ daten }: { daten: Daten }) {
  return (
    <Panel titel="Datenstatus" stand={daten.erstellt} rechts={<span className="grau">Daten erzeugt {zeit(daten.erstellt)}</span>}>
      <table className="tabelle"><tbody>
        {daten.status.map((s) => (
          <tr key={s.quelle}><td className="links">{s.quelle}</td>
            <td className={`links ${s.ok ? "plus" : "minus"}`}>{s.ok ? "✔ ok" : "✖ Problem"}</td>
            <td className="links grau">{s.grund || "–"}</td></tr>))}
        {daten.fehlend.map((f) => <tr key={f}><td className="links">Paket {f}</td><td className="links minus">✖ fehlt</td><td /></tr>)}
      </tbody></table>
    </Panel>
  );
}
