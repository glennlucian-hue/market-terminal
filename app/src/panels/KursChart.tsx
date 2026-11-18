// Kurs-Chart mit TradingView Lightweight Charts (Open Source): Achse rechts, Zeitraum-Knöpfe.
import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, ColorType, createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { Daten } from "../daten";
import { klasse, prozent, zahl } from "../format";
import { KeineDaten, Panel } from "../Panel";

const ZEITRAEUME = [["1M", 31], ["3M", 92], ["6M", 183], ["1J", 366]] as const;

export function KursChart({ daten, ticker }: { daten: Daten; ticker: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [tage, setTage] = useState<number>(183);
  const h = daten.historie[ticker];
  const name = useMemo(() => daten.watchlist.flatMap((g) => g.werte).find((w) => w.ticker === ticker)?.name ?? ticker, [daten, ticker]);

  const punkte = useMemo(() => {
    if (!h) return [];
    const start = Date.now() - tage * 864e5;
    return h.t.map((t, i) => ({ time: (Date.parse(`${t}T00:00:00Z`) / 1000) as UTCTimestamp, value: h.c[i] }))
              .filter((p) => p.time * 1000 >= start);
  }, [h, tage]);
  const veraenderung = punkte.length > 1 ? (punkte[punkte.length - 1].value / punkte[0].value - 1) * 100 : null;

  useEffect(() => {
    if (!ref.current || punkte.length === 0) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#16191d" }, textColor: "#9aa0a6",
                fontFamily: "IBM Plex Mono, Consolas, monospace", fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: "#23272d" } },
      rightPriceScale: { borderColor: "#2d3238" },
      timeScale: { borderColor: "#2d3238" },
      crosshair: { horzLine: { labelBackgroundColor: "#cc8000" }, vertLine: { labelBackgroundColor: "#cc8000" } },
      localization: { locale: "de-CH" },
    });
    const serie = chart.addSeries(AreaSeries, {
      lineColor: "#ffa31a", topColor: "rgba(255,163,26,0.25)", bottomColor: "rgba(255,163,26,0.02)", lineWidth: 2,
      priceLineColor: "#ffa31a",
    });
    serie.setData(punkte);
    chart.timeScale().fitContent();
    chartRef.current = chart;
    return () => { chart.remove(); chartRef.current = null; };
  }, [punkte]);

  return (
    <Panel titel={`Chart · ${name}`} quelle={h ? `${h.quelle} (${ticker})` : undefined} stand={h ? `${h.t[h.t.length - 1]}T22:00:00Z` : null}
           art={h?.art} rechts={
      <span className="knopfgruppe">
        {veraenderung !== null && <span className={`chart-ver ${klasse(veraenderung)}`}>{prozent(veraenderung)}</span>}
        {ZEITRAEUME.map(([n, t]) => <button key={n} className={t === tage ? "aktiv" : ""} onClick={() => setTage(t)}>{n}</button>)}
      </span>}>
      {!h ? <KeineDaten grund={`Kein Kursverlauf für ${ticker}. Nur Werte aus watchlist.yaml haben einen Verlauf.`} /> : (
        <>
          <div className="chart-kopf"><b>{zahl(h.c[h.c.length - 1])}</b> <span className="grau">{h.waehrung ?? ""}</span></div>
          <div className="chart" ref={ref} />
        </>
      )}
    </Panel>
  );
}
