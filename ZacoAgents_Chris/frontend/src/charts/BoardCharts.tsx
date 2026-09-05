/**
 * Reconciliation and settlement.
 *
 * The reconciliation chart is **not** the diverging bar this was planned as, and the reason is
 * worth writing down. A diverging bar needs disagreements spread either side of nought; this
 * record has none. An account sale either agrees exactly -- `difference` is 0.00 on every
 * reconciled line -- or one side of it is simply missing, where `difference` is `null` and
 * drawing it at nought would say the two sides agreed. So the signed axis would have been twelve
 * bars of zero length and six absences: a chart with the shape of information and none in it.
 *
 * What is actually informative is how many account sales sit in each state, so that is what is
 * drawn. The money is on the bar as a direct label rather than as a second axis -- an annotation
 * beside a bar is not an encoding, and two measures on two scales in one frame is the mistake
 * this whole set of charts is written to avoid.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_TICK, GRID, MARK, QUIET } from "./theme";
import { Figure, Tip, tipped } from "./Figure";

export interface StateRow {
  state: string;
  label: string;
  count: number;
  total: string;
}

export function ReconciliationStates({ rows }: { rows: StateRow[] }) {
  const anything = rows.some((row) => row.count > 0);

  return (
    <Figure
      title="Account sales by state"
      note="How many sit in each state, with what they come to beside them. States with nothing in them are kept, so that reads as none of these rather than as a state nobody thought of."
      height={Math.max(180, rows.length * 34 + 40)}
      empty={anything ? null : "No account sale has been read yet."}
    >
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 96, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis
            type="number"
            allowDecimals={false}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={230}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.035)" }}
            content={tipped<StateRow>((datum) => (
              <Tip
                heading={datum.label}
                rows={[
                  { label: "Account sales", value: String(datum.count) },
                  { label: "Nett", value: datum.total },
                ]}
              />
            ))}
          />
          <Bar dataKey="count" fill={MARK} barSize={16} isAnimationActive={false}>
            <LabelList
              dataKey="total"
              position="right"
              fill={QUIET}
              fontSize={11}
              // A zero-count state has no bar to label, and a rand figure floating at the axis
              // beside nothing reads as a bar that failed to draw.
              formatter={(value: unknown) => (value === "R0.00" ? "" : String(value))}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/**
 * One ratio against a total, drawn as a bar rather than a dial.
 *
 * Hand-written SVG. A meter is two rectangles, and reaching for a charting library to draw two
 * rectangles adds a layout engine, an animation loop and a resize observer to a shape that has
 * none of those problems.
 */
export function Meter({
  title,
  done,
  total,
  legend,
  caption,
}: {
  title: string;
  done: number;
  total: number;
  legend: string;
  caption?: string;
}) {
  const share = total > 0 ? done / total : 0;

  return (
    <figure className="figure meter">
      <figcaption>
        <span className="figure-title">{title}</span>
        <span className="figure-note">{legend}</span>
      </figcaption>
      <div
        className="meter-track"
        role="img"
        aria-label={`${done} of ${total}. ${legend}`}
        title={legend}
      >
        <div className="meter-fill" style={{ width: `${Math.round(share * 100)}%` }} />
      </div>
      {caption ? <p className="figure-note meter-caption">{caption}</p> : null}
    </figure>
  );
}
