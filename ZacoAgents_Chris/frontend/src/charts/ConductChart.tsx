/**
 * Section 10's one chart, and the only one on this interface that exists to make a comparison
 * rather than a total.
 *
 * The whole job of section 10 is to make one account sale visible against what is normal for this
 * business. Read down eighteen rows of a table and you get there slowly; drawn as eighteen dots
 * against a line at the normal, you get there at once. So the form is emphasis: the flagged one
 * in amber, every other one in a gray with almost no chroma in it, which is the absence of a
 * claim rather than a colour.
 *
 * Amber and never red. `app.css` says why in as many words -- "a red row is an accusation" -- and
 * section 10 is explicit that none of this is one. What is being said is that a deduction was
 * unlike the others, not that anybody took anything.
 *
 * The normal and the threshold are both drawn from the response. Hardcoding 1.5 here would be the
 * exact duplication section 10 exists to avoid: the panel would go on saying "half again as much
 * as normal" while the chart quietly drew something else.
 */

import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { Schemas } from "../api/client";
import { AXIS_TICK, FLAGGED, GRID, QUIET, RULE, percent, rand } from "./theme";
import { Figure, Tip, tipped } from "./Figure";

type KeptPoint = Schemas["KeptPointOut"];
type Thresholds = Schemas["ThresholdsOut"];

export function KeptShareChart({
  points,
  normal,
  thresholds,
}: {
  points: KeptPoint[];
  normal: number | null | undefined;
  thresholds: Thresholds;
}) {
  // Reversed for drawing. The API sends these ordered by how far from normal they sit, and a
  // category axis lays the first one out at the bottom -- so the one the panel exists to show
  // would end up furthest from the heading that introduces it.
  const data = [...points].reverse();
  const flag = normal == null ? null : normal * thresholds.materially_above;
  const furthest = Math.max(...data.map((point) => point.share), flag ?? 0, 0);
  // Headroom, so the dot that matters is not drawn half off the edge of its own chart.
  const widest = Math.ceil(furthest * 1.08 * 10) / 10;

  return (
    <Figure
      title="What each account sale kept"
      note={
        normal == null
          ? "Nothing has been judged: there are too few finished account sales to say what is normal."
          : `Share of gross deducted, against this business's own normal of ${percent(normal, 0)}.`
      }
      height={Math.max(220, data.length * 26 + 56)}
      empty={
        data.length
          ? null
          : "No account sale in the record carries both a gross and a nett, so there is nothing to compare."
      }
    >
      <ResponsiveContainer>
        {/* Room at the top for the two reference-line labels, which are drawn above the plot. */}
        <ScatterChart margin={{ top: 26, right: 28, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis
            type="number"
            dataKey="share"
            domain={[0, widest]}
            tickFormatter={(value: number) => percent(value, 0)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={132}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          {/* A marker under 8px is a speck. */}
          <ZAxis range={[80, 80]} />
          {normal == null ? null : (
            <ReferenceLine
              x={normal}
              stroke={RULE}
              label={{ value: `normal ${percent(normal, 0)}`, position: "top", fill: RULE, fontSize: 11 }}
            />
          )}
          {flag == null ? null : (
            <ReferenceLine
              x={flag}
              stroke={FLAGGED}
              strokeDasharray="4 4"
              label={{
                value: `${thresholds.materially_above}× normal`,
                position: "top",
                fill: FLAGGED,
                fontSize: 11,
              }}
            />
          )}
          <Tooltip
            cursor={{ stroke: GRID }}
            content={tipped<(typeof data)[number]>((datum) => (
              <Tip
                heading={datum.label}
                rows={[
                  { label: "Kept", value: percent(datum.share) },
                  { label: "Gross", value: rand(datum.gross) },
                  {
                    label: "Over normal",
                    value: datum.excess == null ? "—" : rand(datum.excess),
                  },
                ]}
              />
            ))}
          />
          <Scatter data={data} isAnimationActive={false}>
            {data.map((datum) => (
              <Cell key={datum.label} fill={datum.is_flagged ? FLAGGED : QUIET} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </Figure>
  );
}
