/**
 * The three charts on the reports page.
 *
 * All three are one measure against one set of names, which is why none of them has two axes.
 * Where a second measure would have been useful -- sell-through beside value, say -- it is in the
 * table underneath instead: two measures on one frame is the mistake that makes a chart look
 * authoritative while saying nothing checkable.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Schemas } from "../api/client";
import { AXIS_TICK, GRID, MARK, percent, rand, shorten } from "./theme";
import { Figure, Tip, tipped } from "./Figure";

type ProductPoint = Schemas["ProductPointOut"];
type TakeOnPoint = Schemas["TakeOnPointOut"];
type Docket = Schemas["DocketOut"];

/**
 * The value bands, darkest first.
 *
 * A single hue with lightness stepping down as the band matters more -- the form a ranked
 * classification takes, and the same language the band chips in the table already use: the vital
 * few darkest, the long tail palest. Checked rather than eyeballed: OKLab lightness 0.48, 0.62,
 * 0.76 at one hue throughout, so the order survives colour blindness and a monochrome print.
 * The palest step is under 3:1 on white, which is what the light end of any ramp is; it is
 * legible because the table of the same figures sits directly beneath the chart.
 */
const BAND: Record<string, string> = {
  A: "#1c5cab",
  B: "#3987e5",
  C: "#86b6ef",
  unbanded: "#8d9497",
};

const bandColour = (band: string) => BAND[band] ?? BAND.unbanded!;

export function ProductValueChart({
  points,
  bands,
}: {
  points: ProductPoint[];
  bands: Record<string, string>;
}) {
  const data = points.map((point) => ({ ...point, short: shorten(point.label) }));

  return (
    <Figure
      title="Takings by product"
      note="Rand over the period, biggest first. Colour is the value band."
      height={Math.max(200, data.length * 30 + 44)}
      empty={data.length ? null : "Nothing sold in this period, so there is nothing to draw."}
    >
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis
            type="number"
            tickFormatter={rand}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="short"
            width={230}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.035)" }}
            content={tipped<(typeof data)[number]>((datum) => (
              <Tip
                heading={datum.label}
                rows={[
                  { label: "Takings", value: rand(datum.value) },
                  {
                    label: "Share",
                    value: datum.share_of_value == null ? "—" : percent(datum.share_of_value),
                  },
                  { label: "Band", value: `${datum.band} — ${bands[datum.band] ?? ""}` },
                ]}
              />
            ))}
          />
          <Bar dataKey="value" barSize={16} isAnimationActive={false}>
            {data.map((datum) => (
              <Cell key={datum.label} fill={bandColour(datum.band)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/** The band key. Colour that nobody is told the meaning of is decoration. */
export function BandKey({ shown, bands }: { shown: string[]; bands: Record<string, string> }) {
  if (shown.length < 2) return null;
  return (
    <p className="chart-key">
      {shown.map((band) => (
        <span key={band} className="chart-key-item">
          <span className="chart-key-swatch" style={{ background: bandColour(band) }} />
          <strong>{band}</strong> — {bands[band] ?? ""}
        </span>
      ))}
    </p>
  );
}

export function TakeOnChart({ points }: { points: TakeOnPoint[] }) {
  // A line that cannot be ranked is kept, kept last, and drawn with no bar at all. Putting it at
  // nought would say it returned nothing for every carton committed to it, which is a far
  // stronger claim than "no document says what was sent".
  const rankable = points.filter((point) => point.per_carton_sent != null);
  const unrankable = points.filter((point) => point.per_carton_sent == null);
  const data = [...rankable, ...unrankable].map((point) => ({
    ...point,
    short: shorten(point.label),
  }));

  return (
    <Figure
      title="What each carton sent came back with"
      note="Rand per carton committed, best first. Not per carton sold: what is scarce is the market slot."
      height={Math.max(200, data.length * 30 + 44)}
      empty={data.length ? null : "Nothing here can be ranked yet."}
    >
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis
            type="number"
            tickFormatter={(value: number) => `R${value.toFixed(0)}`}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="short"
            width={230}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.035)" }}
            content={tipped<(typeof data)[number]>((datum) => (
              <Tip
                heading={datum.label}
                rows={[
                  {
                    label: "Per carton sent",
                    value:
                      datum.per_carton_sent == null
                        ? "not ranked"
                        : `R${datum.per_carton_sent.toFixed(2)}`,
                  },
                  {
                    label: "Sell-through",
                    value: datum.sell_through == null ? "—" : percent(datum.sell_through),
                  },
                  {
                    label: "Came back",
                    value: datum.return_rate == null ? "—" : percent(datum.return_rate),
                  },
                ]}
              />
            ))}
          />
          <Bar dataKey="per_carton_sent" fill={MARK} barSize={16} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  );
}

/** Whole days between two ISO dates. */
function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000);
}

/** The Monday of the week a date falls in, as an ISO date. */
function weekStart(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday);
  return date.toISOString().slice(0, 10);
}

export interface Bucketed {
  bucket: string;
  value: number;
  dockets: number;
}

export interface Buckets {
  rows: Bucketed[];
  grain: "day" | "week";
  /** Sales the window left out, dated ones outside it and undated ones alike. Counted so the
   *  line can say what it is not showing rather than quietly being short. */
  left_out: number;
}

/**
 * Sales gathered into days, or into weeks when there are too many days to read.
 *
 * The grain is chosen from the span rather than offered as a control. A second picker beside the
 * one that already scopes the page is mostly a way for two filters to disagree with each other.
 */
export function bucket(dockets: Docket[], from: string | null, to: string | null): Buckets {
  const inRange = dockets.filter((docket) => {
    if (!docket.date_sold) return false;
    if (from && docket.date_sold < from) return false;
    if (to && docket.date_sold > to) return false;
    return true;
  });

  const dates = inRange.map((docket) => docket.date_sold!).sort();
  const span = dates.length ? daysBetween(dates[0]!, dates[dates.length - 1]!) : 0;
  const grain: "day" | "week" = span > 70 ? "week" : "day";

  const totals = new Map<string, Bucketed>();
  for (const docket of inRange) {
    const key = grain === "week" ? weekStart(docket.date_sold!) : docket.date_sold!;
    const row = totals.get(key) ?? { bucket: key, value: 0, dockets: 0 };
    row.value += docket.value ?? 0;
    row.dockets += 1;
    totals.set(key, row);
  }

  return {
    rows: [...totals.values()].sort((left, right) => left.bucket.localeCompare(right.bucket)),
    grain,
    left_out: dockets.length - inRange.length,
  };
}

export function TakingsOverTime({ buckets, scope }: { buckets: Buckets; scope: string }) {
  const { rows, grain } = buckets;
  return (
    <Figure
      title={`Takings by ${grain}`}
      note={`Every sale off the floor, gathered by ${grain}. ${scope}`}
      height={240}
      empty={
        rows.length > 1
          ? null
          : rows.length === 1
            ? "Everything in this period sold on one day, so there is no line to draw."
            : "No dated sale falls in this period."
      }
    >
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis
            dataKey="bucket"
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value: string) => value.slice(5)}
          />
          <YAxis
            tickFormatter={rand}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          <Tooltip
            content={tipped<Bucketed>((datum) => (
              <Tip
                heading={grain === "week" ? `Week of ${datum.bucket}` : datum.bucket}
                rows={[
                  { label: "Takings", value: rand(datum.value) },
                  { label: "Sales", value: String(datum.dockets) },
                ]}
              />
            ))}
          />
          {/* Straight between the points, never smoothed. A curve through daily totals draws a
              value for every moment between two days, and dips below both of them on the way --
              takings that were never taken, on a chart of what was. */}
          <Line
            type="linear"
            dataKey="value"
            stroke={MARK}
            strokeWidth={2}
            dot={{ r: 3, fill: MARK, strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Figure>
  );
}
