// Rahmen für jedes Panel: Titelleiste (zum Verschieben), Inhalt, Fusszeile mit Quelle · Stand · Art.
import type { ReactNode } from "react";
import { ARTEN, zeit } from "./format";

interface Props {
  titel: string;
  quelle?: string;
  stand?: string | null;
  art?: string | null;
  rechts?: ReactNode;
  children: ReactNode;
}

export function Panel({ titel, quelle, stand, art, rechts, children }: Props) {
  return (
    <section className="panel">
      <header className="panel-kopf" title="Zum Verschieben ziehen">
        <span className="panel-titel">{titel}</span>
        <span className="panel-rechts" onMouseDown={(e) => e.stopPropagation()}>{rechts}</span>
      </header>
      <div className="panel-inhalt">{children}</div>
      {(quelle || stand || art) && (
        <footer className="panel-fuss">
          {quelle && <span>Quelle: {quelle}</span>}
          {stand && <span>Stand: {zeit(stand)}</span>}
          {art && <span className="art">{ARTEN[art] ?? art}</span>}
        </footer>
      )}
    </section>
  );
}

export function KeineDaten({ grund }: { grund: string }) {
  return <div className="keine-daten">Keine Daten<span>{grund}</span></div>;
}
