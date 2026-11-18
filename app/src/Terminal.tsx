// Hauptfenster: Statuszeile, Befehlszeile, Panel-Raster (verschieb- und vergrösserbar), Tastenkürzel.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import ReactGridLayout, { useContainerWidth } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import type { Daten } from "./daten";
import { klasse, prozent, zahl, zeit } from "./format";
import { KurseTabelle } from "./panels/KurseTabelle";
import { KursChart } from "./panels/KursChart";
import { Datenstatus, Krypto, Termine, TopBewegungen } from "./panels/Weitere";
import { DetailAnsicht } from "./panels/Detail";

type Layout = { i: string; x: number; y: number; w: number; h: number; minW?: number; minH?: number }[];

const STANDARD_LAYOUT: Layout = [
  { i: "kurse", x: 0, y: 0, w: 5, h: 17, minW: 3, minH: 6 },
  { i: "chart", x: 5, y: 0, w: 7, h: 11, minW: 3, minH: 6 },
  { i: "termine", x: 5, y: 11, w: 4, h: 12, minW: 3, minH: 5 },
  { i: "top", x: 9, y: 11, w: 3, h: 12, minW: 3, minH: 5 },
  { i: "krypto", x: 0, y: 17, w: 5, h: 11, minW: 3, minH: 5 },
  { i: "status", x: 5, y: 23, w: 7, h: 5, minW: 3, minH: 3 },
];
const LAYOUT_KEY = "mt-layout-v1";
const LISTEN_KEY = "mt-watchlists-v1";

function lies<T>(key: string, ersatz: T): T {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : ersatz; } catch { return ersatz; }
}
function schreib(key: string, wert: unknown) {
  try { localStorage.setItem(key, JSON.stringify(wert)); } catch { /* privater Modus: ohne Speichern weiter */ }
}

interface Listen { aktiv: string; listen: Record<string, string[]> }

export function Terminal({ daten, abmelden, neuLaden }: { daten: Daten; abmelden: () => void; neuLaden: () => void }) {
  const alleTicker = useMemo(() => daten.watchlist.flatMap((g) => g.werte.map((w) => w.ticker)), [daten.watchlist]);
  const [listen, setListen] = useState<Listen>(() => lies(LISTEN_KEY, { aktiv: "Standard", listen: { Standard: [] } }));
  const aktiveTicker = listen.aktiv === "Standard" && !(listen.listen.Standard?.length) ? alleTicker : listen.listen[listen.aktiv] ?? [];
  const [auswahl, setAuswahl] = useState<string>("^GSPC");
  const [layout, setLayout] = useState<Layout>(() => lies(LAYOUT_KEY, STANDARD_LAYOUT));
  const [befehl, setBefehl] = useState("");
  const [meldung, setMeldung] = useState("Befehl eingeben – z. B. NVDA ⏎ · ? für Hilfe");
  const [hilfe, setHilfe] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const oeffne = useCallback((t: string) => { setAuswahl(t); if (daten.details?.[t]) setDetail(t); }, [daten.details]);
  const eingabe = useRef<HTMLInputElement>(null);
  const { width, containerRef, mounted } = useContainerWidth();

  useEffect(() => schreib(LISTEN_KEY, listen), [listen]);

  // Tastenkürzel: "/" Befehlszeile, "?" Hilfe, Esc schliesst
  useEffect(() => {
    const taste = (e: KeyboardEvent) => {
      const tippt = document.activeElement === eingabe.current;
      if (e.key === "Escape") { setHilfe(false); eingabe.current?.blur(); }
      else if (!tippt && (e.key === "/" || e.key === ":")) { e.preventDefault(); eingabe.current?.focus(); }
      else if (!tippt && e.key === "?") setHilfe((h) => !h);
    };
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  }, []);

  const ausfuehren = useCallback((roh: string) => {
    const b = roh.trim();
    if (!b) return;
    const gross = b.toUpperCase();
    const finde = (t: string) => alleTicker.find((x) => x.toUpperCase() === t || x.replace("^", "").toUpperCase() === t)
      ?? daten.watchlist.flatMap((g) => g.werte).find((w) => w.name.toUpperCase() === t)?.ticker;
    if (gross === "?" || gross === "HILFE") { setHilfe(true); return setMeldung("Hilfe geöffnet (Esc schliesst)"); }
    if (gross === "RESET") { setLayout(STANDARD_LAYOUT); schreib(LAYOUT_KEY, STANDARD_LAYOUT); return setMeldung("Layout zurückgesetzt"); }
    if (gross === "NEU") { neuLaden(); return setMeldung("Daten werden neu geladen …"); }
    if (gross === "ALT") { window.location.href = "../index.html"; return; }
    if (gross.startsWith("LISTE ")) {
      const name = b.slice(6).trim();
      setListen((l) => ({ aktiv: name, listen: { ...l.listen, [name]: l.listen[name] ?? [] } }));
      return setMeldung(`Watchlist «${name}» aktiv`);
    }
    if (gross.startsWith("+") || gross.startsWith("-")) {
      const t = finde(gross.slice(1).trim()) ?? gross.slice(1).trim();
      setListen((l) => {
        const basis = l.aktiv === "Standard" && !(l.listen.Standard?.length) ? alleTicker : l.listen[l.aktiv] ?? [];
        const neu = gross.startsWith("+") ? [...new Set([...basis, t])] : basis.filter((x) => x !== t);
        return { ...l, listen: { ...l.listen, [l.aktiv]: neu } };
      });
      return setMeldung(`${t} ${gross.startsWith("+") ? "hinzugefügt zu" : "entfernt aus"} «${listen.aktiv}»`
        + (daten.kurse[t] ? "" : " – Hinweis: für diesen Ticker gibt es noch keine Daten (in watchlist.yaml ergänzen)"));
    }
    const t = finde(gross);
    if (t) { oeffne(t); return setMeldung(daten.details?.[t] ? `Detailansicht: ${t} (Esc schliesst)` : `Chart: ${t}`); }
    setMeldung(`«${b}» nicht gefunden. Nur Werte aus watchlist.yaml haben Daten. ? für Hilfe`);
  }, [alleTicker, daten, listen.aktiv, neuLaden, oeffne]);

  const band = ["^GSPC", "^NDX", "^SSMI", "^STOXX50E", "^VIX", "DGS10", "CHF=X", "EURCHF=X", "GC=F", "BZ=F", "BTC-USD"]
    .map((t) => ({ t, k: daten.kurse[t] })).filter((x) => x.k?.ok);
  const name = (t: string) => daten.watchlist.flatMap((g) => g.werte).find((w) => w.ticker === t)?.name ?? t;
  const schmal = width > 0 && width < 760;

  const panels: Record<string, ReactElement> = {
    kurse: <KurseTabelle daten={daten} ticker={aktiveTicker} listenName={listen.aktiv} ausgewaehlt={auswahl} waehle={oeffne} />,
    chart: <KursChart daten={daten} ticker={auswahl} />,
    termine: <Termine daten={daten} />,
    top: <TopBewegungen daten={daten} />,
    krypto: <Krypto daten={daten} />,
    status: <Datenstatus daten={daten} />,
  };

  return (
    <div className="terminal">
      <div className="statuszeile">
        <span className="marke">MARKET TERMINAL 2.0</span>
        <span>Daten: {zeit(daten.erstellt)} Uhr · Zürich · Kurse ~15 Min. verzögert</span>
        <span className="statuszeile-rechts">
          <a href="../index.html">Bisherige Website</a>
          <button onClick={neuLaden}>Neu laden</button>
          <button onClick={abmelden}>Abmelden</button>
        </span>
      </div>
      <div className="befehlszeile">
        <span className="prompt">›</span>
        <input ref={eingabe} value={befehl} placeholder="Ticker oder Befehl (z. B. NVDA, +MELI, LISTE Tech, RESET) – Taste / zum Fokussieren"
               onChange={(e) => setBefehl(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") { ausfuehren(befehl); setBefehl(""); } }} />
        <span className="meldung">{meldung}</span>
      </div>
      <div className="laufband">
        {band.map(({ t, k }) => (
          <span key={t} onClick={() => setAuswahl(t)}>
            <b>{name(t)}</b> {zahl(k!.daten!.kurs, t === "DGS10" ? 2 : undefined)}
            {t !== "DGS10" && <i className={klasse(k!.daten!.veraenderung_pct)}> {prozent(k!.daten!.veraenderung_pct)}</i>}
          </span>))}
      </div>
      <div ref={containerRef} className="arbeitsflaeche">
        {mounted && (schmal ? (
          <div className="stapel">{Object.entries(panels).map(([k, p]) => <div key={k} className={`stapel-${k}`}>{p}</div>)}</div>
        ) : (
          <ReactGridLayout layout={layout} width={width} gridConfig={{ cols: 12, rowHeight: 26, margin: [6, 6] }}
                           dragConfig={{ handle: ".panel-kopf" }}
                           onLayoutChange={(l) => { const neu = l as unknown as Layout; setLayout(neu); schreib(LAYOUT_KEY, neu); }}>
            {Object.entries(panels).map(([k, p]) => <div key={k}>{p}</div>)}
          </ReactGridLayout>
        ))}
      </div>
      {detail && <DetailAnsicht daten={daten} ticker={detail} schliessen={() => setDetail(null)} />}
      {hilfe && (
        <div className="hilfe" onClick={() => setHilfe(false)}>
          <div className="hilfe-fenster" onClick={(e) => e.stopPropagation()}>
            <h2>Bedienung</h2>
            <table className="tabelle"><tbody>
              <tr><td className="links fett">/</td><td className="links">Befehlszeile fokussieren</td></tr>
              <tr><td className="links fett">NVDA ⏎</td><td className="links">Aktie: Detailansicht (Chart, Kursziel, Analysten, Fundamentaldaten) · andere Werte: Chart. Auch Klick auf eine Zeile.</td></tr>
              <tr><td className="links fett">+MELI / -MELI</td><td className="links">Wert zur aktiven Watchlist hinzufügen / entfernen</td></tr>
              <tr><td className="links fett">LISTE Tech</td><td className="links">eigene Watchlist «Tech» anlegen bzw. wechseln («LISTE Standard» = alle Werte)</td></tr>
              <tr><td className="links fett">RESET</td><td className="links">Panel-Anordnung zurücksetzen</td></tr>
              <tr><td className="links fett">NEU</td><td className="links">Daten neu laden</td></tr>
              <tr><td className="links fett">ALT</td><td className="links">zur bisherigen Website</td></tr>
              <tr><td className="links fett">? / Esc</td><td className="links">Hilfe öffnen / schliessen</td></tr>
            </tbody></table>
            <p className="grau">Panels an der Titelleiste verschieben, an der unteren rechten Ecke vergrössern. Anordnung und eigene Watchlists
              werden in diesem Browser gespeichert. Klick auf eine Zeile oder einen Wert im Laufband öffnet den Chart.</p>
          </div>
        </div>
      )}
    </div>
  );
}
