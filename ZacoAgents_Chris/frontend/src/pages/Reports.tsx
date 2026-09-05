/**
 * Section 9, over the whole record or one month or one week.
 *
 * The period lives in the address bar rather than in a variable. A report is the thing somebody
 * pastes into a message -- "look at the week of the first" -- and a page that always opens on all
 * time cannot be sent to anybody. It is also what makes the back button mean what it looks like
 * it means.
 *
 * Charts sit above the tables they summarise, never instead of them. The numbers a chart is drawn
 * from are `render.plot` numbers, which exist only to be drawn; the figure anybody is owed is the
 * string in the table underneath, and it is always there.
 */

import { useSearchParams } from "react-router";

import { Page } from "../components/Page";
import { Loading, Problem, Reported, dash } from "../components/values";
import { useDockets, useReport, type Period } from "../api/queries";
import type { Report } from "../api/queries";
import {
  BandKey,
  ProductValueChart,
  TakeOnChart,
  TakingsOverTime,
  bucket,
} from "../charts/ReportCharts";

const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "month", label: "A month" },
  { value: "week", label: "A week" },
];

function isPeriod(value: string | null): value is Period {
  return value === "all" || value === "month" || value === "week";
}

function Caveats({ caveats }: { caveats: string[] }) {
  if (!caveats.length) return null;
  // A caveat is not a footnote. Section 10's rule -- a conclusion travels with the figures --
  // applies here too, so these sit above the numbers they qualify rather than under them.
  return (
    <div className="warning">
      <strong>What these figures do not say</strong>
      <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
        {caveats.map((caveat) => (
          <li key={caveat}>{caveat}</li>
        ))}
      </ul>
    </div>
  );
}

function Headline({ report }: { report: Report }) {
  const headline = report.headline;
  return (
    <>
      <h2>Headline</h2>
      <div className="panel">
        <table>
          <tbody>
            <tr>
              <td>Cartons sold</td>
              <td className="num mono">{dash(headline.cartons_sold)}</td>
            </tr>
            <tr>
              <td>Came back</td>
              <td className="num mono">
                <Reported value={headline.cartons_returned} />
              </td>
            </tr>
            <tr>
              <td>Net</td>
              <td className="num mono">
                <strong>{dash(headline.cartons_net)}</strong>
              </td>
            </tr>
            <tr>
              <td>Takings</td>
              <td className="num mono">
                <strong>{dash(headline.takings)}</strong>
              </td>
            </tr>
            <tr>
              <td>A carton fetched</td>
              <td className="num mono">{dash(headline.price_per_carton)}</td>
            </tr>
            <tr>
              <td>Return rate</td>
              <td className="num mono">{dash(headline.return_rate)}</td>
            </tr>
          </tbody>
        </table>
        <p className="muted" style={{ margin: "0.6rem 0 0" }}>
          {headline.return_rate_basis}
        </p>
        {headline.not_yet_paid && headline.not_yet_paid !== "R0.00" ? (
          <p className="muted" style={{ margin: "0.35rem 0 0" }}>
            Of the takings, {headline.not_yet_paid} is not yet in any payment run — it sold, and it
            has not arrived.
          </p>
        ) : null}
      </div>
    </>
  );
}

function Products({ report }: { report: Report }) {
  if (!report.products.length) {
    return (
      <>
        <h2>Products</h2>
        <p className="muted">Nothing sold in this period.</p>
      </>
    );
  }
  const shown = [...new Set(report.products.map((line) => line.band))];

  return (
    <>
      <h2>
        Products <span className="muted">({report.products.length}, by value)</span>
      </h2>
      <div className="panel">
        <ProductValueChart points={report.chart.products} bands={report.bands} />
        <BandKey shown={shown} bands={report.bands} />
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Band</th>
                <th>Product</th>
                <th>Code</th>
                <th className="num">Share</th>
                <th className="num">Value</th>
                <th className="num">A carton</th>
                <th className="num">Net</th>
                <th className="num">Sent</th>
                <th className="num">Sell-through</th>
                <th className="num">Days</th>
              </tr>
            </thead>
            <tbody>
              {report.products.map((line) => (
                <tr key={`${line.product}-${line.short_code ?? ""}`}>
                  <td>
                    <span className={`chip band-${line.band}`}>{line.band}</span>
                  </td>
                  <td>{line.product}</td>
                  <td className="mono muted">{dash(line.short_code)}</td>
                  <td className="num">{dash(line.share_of_value)}</td>
                  <td className="num mono">{dash(line.value)}</td>
                  <td className="num mono">{dash(line.price_per_carton)}</td>
                  <td className="num">{dash(line.cartons_net)}</td>
                  <td className="num">
                    <Reported value={line.cartons_sent} />
                  </td>
                  <td className="num">{dash(line.sell_through)}</td>
                  <td className="num">{dash(line.days_on_market)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: "0.9em", margin: "0.6rem 0 0" }}>
          Sent, sell-through and days on market belong to the delivery, so they cover each
          consignment&rsquo;s whole life and are counted once per consignment — never per row.
        </p>
      </div>
    </>
  );
}

function Totals({
  title,
  what,
  rows,
}: {
  title: string;
  what: string;
  rows: Report["agents"];
}) {
  if (!rows.length) return null;
  return (
    <>
      <h2>By {title}</h2>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>{what}</th>
              <th className="num">Value</th>
              <th className="num">Net cartons</th>
              <th className="num">Consignments</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="num mono">{row.value}</td>
                <td className="num">{row.cartons_net}</td>
                <td className="num muted">{row.consignments}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function TakeOn({ report }: { report: Report }) {
  if (!report.take_on.length) return null;
  return (
    <>
      <h2>What to take on again</h2>
      <div className="panel">
        <p className="muted" style={{ margin: "0 0 0.6rem" }}>
          <strong>Ranked on:</strong> {report.take_on_basis}. The denominator is what was{" "}
          <em>sent</em>, not what sold — nothing is bought here, and what is scarce is the market
          slot and the handling spent on produce that then fails to move.
          {report.commission_coverage ? (
            <>
              <br />
              <strong>Coverage:</strong> {report.commission_coverage}
            </>
          ) : null}
        </p>
        <TakeOnChart points={report.chart.take_on} />
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th className="num">Per carton sent</th>
                <th className="num">Sent</th>
                <th className="num">Sell-through</th>
                <th className="num">Came back</th>
                <th className="num">Value</th>
                <th className="num">Zaco earned</th>
              </tr>
            </thead>
            <tbody>
              {report.take_on.map((line) => (
                <tr key={line.product}>
                  <td>{line.product}</td>
                  <td className="num mono">
                    <strong>{dash(line.per_carton_sent)}</strong>
                  </td>
                  <td className="num">{dash(line.cartons_sent)}</td>
                  <td className="num">{dash(line.sell_through)}</td>
                  <td className="num">{dash(line.return_rate)}</td>
                  <td className="num mono">{dash(line.value)}</td>
                  <td className="num mono">{dash(line.earned)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {report.take_on.some((line) => line.note) ? (
          <ul className="muted" style={{ fontSize: "0.9em", margin: "0.6rem 0 0" }}>
            {report.take_on
              .filter((line) => line.note)
              .map((line) => (
                <li key={line.product}>
                  <strong>{line.product}</strong> — {line.note}
                </li>
              ))}
          </ul>
        ) : null}
      </div>
    </>
  );
}

export function Reports() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("period");
  const period: Period = isPeriod(raw) ? raw : "all";
  const on = params.get("on") ?? "";

  const report = useReport(period, on);
  const dockets = useDockets();

  function change(next: Partial<{ period: Period; on: string }>) {
    const merged = new URLSearchParams(params);
    if (next.period !== undefined) merged.set("period", next.period);
    if (next.on !== undefined) merged.set("on", next.on);
    if ((next.period ?? period) === "all") merged.delete("on");
    setParams(merged, { replace: true });
  }

  const found = report.data;
  const buckets = bucket(dockets.data?.dockets ?? [], found?.start ?? null, found?.end ?? null);

  return (
    <Page title="Reports" width="wide">
      <h1>Reports</h1>
      <p className="lede">
        Over the whole recorded history, or a month, or a week. Every figure is worked out from the
        documents on read, so the same history gives the same answer, and everything a score rests
        on is shown beside it.
      </p>

      <div className="panel picker">
        <label htmlFor="period">Period</label>
        <select
          id="period"
          value={period}
          onChange={(event) => change({ period: event.target.value as Period })}
        >
          {PERIODS.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
        {period === "all" ? null : (
          <>
            <label htmlFor="on">The day it sits around</label>
            <input
              id="on"
              type="date"
              value={on}
              onChange={(event) => change({ on: event.target.value })}
            />
          </>
        )}
      </div>

      {report.isError ? <Problem error={report.error} /> : null}
      {!found && report.isPending ? <Loading what="the report" /> : null}

      {found ? (
        // Held at reduced opacity while the next period is worked out, rather than replaced by a
        // skeleton. The figures on screen are still true; they are just not the ones asked for yet.
        <div className={report.isFetching ? "settling" : undefined}>
          <h2 style={{ marginTop: "1.5rem" }}>
            {found.period}{" "}
            <span className="muted">— {found.headline.docket_count} sale(s)</span>
          </h2>

          <Caveats caveats={found.caveats} />
          <Headline report={found} />

          <h2>Over time</h2>
          <div className="panel">
            {dockets.isError ? (
              <Problem error={dockets.error} />
            ) : (
              <TakingsOverTime
                buckets={buckets}
                scope={
                  found.is_all_time
                    ? "The whole record."
                    : `Within ${found.start ?? "?"} to ${found.end ?? "?"}.`
                }
              />
            )}
          </div>

          <Products report={found} />
          <Totals title="agent" what="Agent" rows={found.agents} />
          <Totals title="market" what="Market" rows={found.markets} />
          <TakeOn report={found} />
        </div>
      ) : null}
    </Page>
  );
}
