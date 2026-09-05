/**
 * The frame every chart on this interface sits in.
 *
 * Two rules are enforced by putting them here rather than by remembering them. A chart always
 * carries a caption saying what is being measured, because a bar length with no unit is a shape.
 * And a chart with nothing to draw says so in words instead of rendering empty axes -- an empty
 * plot frame reads as a chart that failed, not as a record with nothing in it yet, and on this
 * system an empty record is the ordinary case before a round is resolved.
 *
 * Every chart here also sits directly above the table of the same figures. That is not decoration:
 * the numbers in a chart are `render.plot` numbers, which exist only to be drawn, and the figure
 * anybody is owed is the string in the table underneath.
 */

import type { ReactElement, ReactNode } from "react";

export function Figure({
  title,
  note,
  height = 260,
  empty,
  children,
}: {
  title: string;
  note?: string;
  height?: number;
  /** Words to show instead of the plot when there is nothing in it. */
  empty?: string | null;
  children: ReactElement;
}) {
  return (
    <figure className="figure">
      <figcaption>
        <span className="figure-title">{title}</span>
        {note ? <span className="figure-note">{note}</span> : null}
      </figcaption>
      {empty ? (
        <p className="figure-empty">{empty}</p>
      ) : (
        <div style={{ height, width: "100%" }}>{children}</div>
      )}
    </figure>
  );
}

/** One row of a tooltip: what it is, and what it measures. */
export interface TipRow {
  label: string;
  value: string;
}

export function Tip({ heading, rows }: { heading: string; rows: TipRow[] }): ReactNode {
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{heading}</div>
      {rows.map((row) => (
        <div className="chart-tip-row" key={row.label}>
          <span>{row.label}</span>
          <span className="mono">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * What Recharts hands a custom tooltip, described here rather than imported.
 *
 * The library's own generic changes shape between versions and carries a dozen fields these
 * charts never touch. Widened to exactly what is read -- and `readonly`, because that is how the
 * library hands it over and a mutable annotation would not accept it.
 *
 * The datum is cast on the way out. There is no type the library could give it: it hands back
 * whatever was in `data`, and only the caller knows what that was.
 */
export interface TipProps {
  active?: boolean;
  payload?: readonly { payload?: unknown }[];
}

export function tipped<T>(render: (datum: T) => ReactNode) {
  return function Rendered({ active, payload }: TipProps): ReactNode {
    const first = payload?.[0]?.payload as T | undefined;
    if (!active || first === undefined) return null;
    return render(first);
  };
}
