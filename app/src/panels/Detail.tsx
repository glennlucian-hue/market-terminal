// Detailansicht einer Aktie: Chart mit Kurszielen und Trendlinien, Fundamentaldaten, Analysten (wer?), Technik.
// Jeder Block nennt seine Quelle. Fehlende Daten werden mit Grund angezeigt – nie geschätzt oder erfunden.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AreaSeries, ColorType, createChart, LineSeries, LineStyle, type UTCTimestamp } from "lightweight-charts";
import type { Daten, Detail } from "../daten";
import { grossbetrag, klasse, prozent, zahl, zeit } from "../format";

const ZEITRAEUME = [["3M", 92], ["6M", 183], ["1J", 366]] as const;

const pct = (x: number | null | undefined, faktor = 100) =>
  x === null || x === undefined ? "–" : `${(x * faktor).toFixed(1)}%`;

function Block({ titel, quelle, grund, children }: { titel: string; quelle?: string | null; grund?: string | null; children?: ReactNode }) {
  return (
    <div className="d-block">
      <h3>{titel}</h3>
      {grund && <p className="d-grund">Keine Daten: {grund}</p>}
      {children}
      {quelle && <div className="d-quelle">Quelle: {quelle}</div>}
    </div>
  );
}

function DetailChart({ daten, d }: { daten: Daten; d: Detail }) {
  const ref = useRef<HTMLDivElement>(null);
  const [tage, setTage] = useState(366);
  const h = daten.historie[d.ticker];
  useEffect(() => {
    if (!ref.current || !h) return;
    const start = Date.now() - tage * 864e5;
    const zeitpunkt = (t: string) => (Date.parse(`${t}T00:00:00Z`) / 1000) as UTCTimestamp;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#16191d" }, textColor: "#9aa0a6", fontFamily: "IBM Plex Mono, monospace", fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: "#23272d" } },
      rightPriceScale: { borderColor: "#2d3238" }, timeScale: { borderColor: "#2d3238" }, localization: { locale: "de-CH" },
    });
    const kurs = chart.addSeries(AreaSeries, { lineColor: "#ffa31a", topColor: "rgba(255,163,26,0.22)", bottomColor: "rgba(255,163,26,0.02)", lineWidth: 2 });
    kurs.setData(h.t.map((t, i) => ({ time: zeitpunkt(t), value: h.c[i] })).filter((p) => p.time * 1000 >= start));
    const tk = d.technik;
    for (const [reihe, farbe] of [[tk.sma50_reihe, "#2a96d4"], [tk.sma200_reihe, "#8a78ee"]] as const) {
      if (!reihe || !tk.reihe_daten) continue;
      const linie = chart.addSeries(LineSeries, { color: farbe, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      linie.setData(tk.reihe_daten.map((t, i) => ({ time: zeitpunkt(t), value: reihe[i] }))
        .filter((p): p is { time: UTCTimestamp; value: number } => p.value !== null && p.time * 1000 >= start));
    }
    const z = d.kursziel;
    if (z.mittel) kurs.createPriceLine({ price: z.mittel, color: "#3ccf6e", lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "Kursziel Ø" });
    if (z.hoch) kurs.createPriceLine({ price: z.hoch, color: "#3ccf6e", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Ziel hoch" });
    if (z.tief) kurs.createPriceLine({ price: z.tief, color: "#ff5c5c", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Ziel tief" });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [h, d, tage]);
  if (!h) return <p className="d-grund">Kein Kursverlauf vorhanden.</p>;
  return (
    <div className="d-chart-rahmen">
      <div className="d-chart-kopf">
        <span className="legende"><i style={{ background: "#ffa31a" }} />Kurs <i style={{ background: "#2a96d4" }} />50-Tage <i style={{ background: "#8a78ee" }} />200-Tage <i style={{ background: "#3ccf6e" }} />Kursziel</span>
        <span className="knopfgruppe">{ZEITRAEUME.map(([n, t]) => <button key={n} className={t === tage ? "aktiv" : ""} onClick={() => setTage(t)}>{n}</button>)}</span>
      </div>
      <div className="d-chart" ref={ref} />
      <div className="d-quelle">Quelle: Kurse {h.quelle} (Schlusskurse), Trendlinien eigene Berechnung, Kursziel {d.kursziel.quelle ?? "–"}</div>
    </div>
  );
}

export function DetailAnsicht({ daten, ticker, schliessen }: { daten: Daten; ticker: string; schliessen: () => void }) {
  const d = daten.details[ticker];
  const k = daten.kurse[ticker];
  const preis = k?.daten?.kurs ?? d?.technik.kurs ?? null;
  const waehrung = k?.daten?.waehrung ?? d?.profil.waehrung ?? "";
  const potenzial = d?.kursziel.mittel && preis ? (d.kursziel.mittel / preis - 1) * 100 : null;
  const f = d?.fundamental.werte ?? {};
  const empf = d?.empfehlung;
  const summeEmpf = (empf?.kaufen ?? 0) + (empf?.halten ?? 0) + (empf?.verkaufen ?? 0);

  useEffect(() => {
    const taste = (e: KeyboardEvent) => { if (e.key === "Escape") schliessen(); };
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  }, [schliessen]);

  if (!d) return null;
  return (
    <div className="detail-hintergrund" onClick={schliessen}>
      <div className="detail" onClick={(e) => e.stopPropagation()}>
        <header className="detail-kopf">
          <div>
            <div className="d-name">{d.name} <span className="tk">{ticker}</span></div>
            <div className="grau">{[d.profil.sektor, d.profil.branche, d.profil.land].filter(Boolean).join(" · ") || "–"}</div>
          </div>
          <div className="d-kurs">
            <b>{zahl(preis)}</b> <span className="grau">{waehrung}</span>
            <span className={klasse(k?.daten?.veraenderung_pct)}> {prozent(k?.daten?.veraenderung_pct)}</span>
            <div className="grau klein">Stand {zeit(k?.daten?.stand)} · {k?.quelle ?? "–"} · verzögert</div>
          </div>
          <button className="d-zu" onClick={schliessen} title="Schliessen (Esc)">✕</button>
        </header>

        <div className="detail-raster">
          <div className="d-links">
            <DetailChart daten={daten} d={d} />
            <div className="d-zwei">
              <Block titel="Analysten-Kursziel (12 Monate)" quelle={d.kursziel.quelle} grund={d.kursziel.grund}>
                {d.kursziel.mittel ? (<>
                  <div className="d-ziel"><b>{zahl(d.kursziel.mittel, 2)}</b> {waehrung}
                    {potenzial !== null && <span className={klasse(potenzial)}> {potenzial > 0 ? "+" : ""}{potenzial.toFixed(1)}% Potenzial</span>}</div>
                  <table className="tabelle"><tbody>
                    <tr><td className="links">Höchstes Ziel</td><td>{zahl(d.kursziel.hoch, 2)}</td></tr>
                    <tr><td className="links">Tiefstes Ziel</td><td>{zahl(d.kursziel.tief, 2)}</td></tr>
                    {d.kursziel.median && <tr><td className="links">Median</td><td>{zahl(d.kursziel.median, 2)}</td></tr>}
                  </tbody></table></>) : undefined}
              </Block>
              <Block titel="Empfehlungen" quelle={empf?.quelle} grund={empf?.grund}>
                {empf && !empf.grund ? (<>
                  {summeEmpf > 0 ? (<>
                    <div className="d-balken">
                      <span className="b-kauf" style={{ flex: empf.kaufen }}>{empf.kaufen} Kaufen</span>
                      <span className="b-halt" style={{ flex: empf.halten }}>{empf.halten} Halten</span>
                      {(empf.verkaufen ?? 0) > 0 && <span className="b-verk" style={{ flex: empf.verkaufen }}>{empf.verkaufen}</span>}
                    </div>
                    <p className="klein grau">{summeEmpf} Analysten · Tendenz: <b>{empf.tendenz ?? "–"}</b> · Verkaufen: {empf.verkaufen ?? 0}</p>
                  </>) : <p>{empf.anzahl} Analysten · Tendenz: <b>{empf.tendenz ?? "–"}</b></p>}
                </>) : undefined}
              </Block>
            </div>
            <Block titel="Wer bewertet die Aktie? – letzte Einstufungen" quelle={d.einstufungen.quelle} grund={d.einstufungen.liste.length ? null : d.einstufungen.grund}>
              {d.einstufungen.liste.length ? (
                <table className="tabelle"><thead><tr><th className="links">Datum</th><th className="links">Analysehaus</th><th className="links">Aktion</th><th className="links">Einstufung</th></tr></thead>
                  <tbody>{d.einstufungen.liste.map((e, i) => (
                    <tr key={i}><td className="links grau">{e.datum?.slice(0, 10)}</td><td className="links fett">{e.firma}</td>
                      <td className={`links ${e.aktion === "upgrade" ? "plus" : e.aktion === "downgrade" ? "minus" : "grau"}`}>{({ upgrade: "Hochstufung", downgrade: "Herabstufung", maintain: "bestätigt", hold: "bestätigt", init: "Erstbewertung" } as Record<string, string>)[e.aktion ?? ""] ?? e.aktion ?? "–"}</td>
                      <td className="links">{e.von && e.von !== e.zu ? `${e.von} → ` : ""}<b>{e.zu}</b></td></tr>))}
                  </tbody></table>) : undefined}
              {empf?.banken && empf.banken.length > 0 && (
                <p className="klein grau d-banken"><b>Abdeckende Häuser ({empf.banken.length}):</b> {empf.banken.join(" · ")}</p>)}
            </Block>
          </div>

          <div className="d-rechts">
            <Block titel="Fundamentaldaten" quelle={d.fundamental.quelle} grund={d.fundamental.grund}>
              {Object.keys(f).length ? (
                <table className="tabelle"><tbody>
                  <tr><td className="links">Börsenwert</td><td>{grossbetrag(f.boersenwert)}</td></tr>
                  <tr><td className="links">KGV (12 Mt.)</td><td>{zahl(f.kgv, 1)}</td></tr>
                  <tr><td className="links">KGV erwartet</td><td>{zahl(f.kgv_erwartet, 1)}</td></tr>
                  <tr><td className="links">Kurs / Umsatz</td><td>{zahl(f.kurs_umsatz, 1)}</td></tr>
                  <tr><td className="links">Umsatzwachstum</td><td className={klasse(f.umsatzwachstum)}>{pct(f.umsatzwachstum)}</td></tr>
                  <tr><td className="links">Gewinnwachstum</td><td className={klasse(f.gewinnwachstum)}>{pct(f.gewinnwachstum)}</td></tr>
                  <tr><td className="links">Operative Marge</td><td>{pct(f.operative_marge)}</td></tr>
                  <tr><td className="links">Nettomarge</td><td>{pct(f.nettomarge)}</td></tr>
                  <tr><td className="links">Eigenkapitalrendite</td><td>{pct(f.eigenkapitalrendite)}</td></tr>
                  <tr><td className="links">Dividendenrendite</td><td>{f.dividendenrendite === null || f.dividendenrendite === undefined ? "–" : f.dividendenrendite > 1 ? `${f.dividendenrendite.toFixed(2)}%` : pct(f.dividendenrendite)}</td></tr>
                  <tr><td className="links">Beta</td><td>{zahl(f.beta, 2)}</td></tr>
                </tbody></table>) : undefined}
              {d.waehrungshinweis && <p className="klein grau">{d.waehrungshinweis} – Bewertungskennzahlen ausgeblendet.</p>}
            </Block>
            <Block titel="Gewinnschätzungen" quelle={d.schaetzungen.quelle} grund={d.schaetzungen.jahre.length ? null : d.schaetzungen.grund}>
              {d.schaetzungen.jahre.length ? (
                <table className="tabelle"><thead><tr><th className="links">Jahr</th><th>Gewinn/Aktie</th><th>Umsatz</th><th>KGV</th></tr></thead>
                  <tbody>{d.schaetzungen.jahre.map((j) => (
                    <tr key={j.jahr}><td className="links">{j.jahr}</td><td>{zahl(j.eps, 2)}</td><td>{grossbetrag(j.umsatz)}</td>
                      <td>{j.eps && preis ? zahl(preis / j.eps, 1) : "–"}</td></tr>))}
                  </tbody></table>) : undefined}
            </Block>
            <Block titel="Chart-Technik" quelle={d.technik.quelle} grund={d.technik.grund}>
              {!d.technik.grund ? (<>
                <table className="tabelle"><tbody>
                  <tr><td className="links">Trend</td><td className="fett">{d.technik.trend} ({d.technik.trendpunkte}/4)</td></tr>
                  <tr><td className="links">RSI (14)</td><td className={(d.technik.rsi ?? 50) > 70 ? "minus" : (d.technik.rsi ?? 50) < 30 ? "plus" : ""}>{zahl(d.technik.rsi, 0)}</td></tr>
                  <tr><td className="links">50- / 200-Tage-Linie</td><td>{zahl(d.technik.sma50, 2)} / {zahl(d.technik.sma200, 2)}</td></tr>
                  <tr><td className="links">Abstand 200-Tage</td><td className={klasse(d.technik.abstand200)}>{prozent(d.technik.abstand200)}</td></tr>
                  <tr><td className="links">52 Wochen tief / hoch</td><td>{zahl(d.technik.tief52, 2)} / {zahl(d.technik.hoch52, 2)}</td></tr>
                  <tr><td className="links">Unterstützung / Widerstand</td><td>{zahl(d.technik.unterstuetzung, 2)} / {zahl(d.technik.widerstand, 2)}</td></tr>
                </tbody></table>
                <ul className="d-signale">{d.technik.signale?.map((s) => <li key={s}>{s}</li>)}</ul></>) : undefined}
            </Block>
          </div>
        </div>
        <p className="d-hinweis">Fakten (Kurse, Fundamentaldaten) und Schätzungen (Kursziele, Empfehlungen, Gewinnschätzungen) stammen aus den genannten Quellen. Technik ist eine eigene, regelbasierte Berechnung. Keine Anlageberatung.</p>
      </div>
    </div>
  );
}
