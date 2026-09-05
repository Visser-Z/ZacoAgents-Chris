/**
 * Section 10: has the agent treated the money normally.
 *
 * The order of this page is load-bearing and is not a layout preference. What the panel cannot
 * see is drawn **first**, inside a panel of its own with the weight of a finding, because section
 * 10 requires that a conclusion travel with the figures. A page that reports only what it can
 * check reads as a clean bill of health on the thing it is blind to, and a reader who stops
 * halfway down has to have met it before the tables.
 *
 * The chart goes after that, not before it.
 */

import { Fragment } from "react";

import { Page } from "../components/Page";
import { Loading, Problem, dash } from "../components/values";
import { useConduct } from "../api/queries";
import type { Conduct as ConductData } from "../api/queries";
import { KeptShareChart } from "../charts/ConductChart";

function BlindSpot({ found }: { found: ConductData }) {
  return (
    <div className="panel blind-spot">
      <h2 style={{ marginTop: 0 }}>What this panel cannot see</h2>
      <p>{found.not_answerable}</p>
      <p className="muted" style={{ marginBottom: 0 }}>
        {found.price_evidence}
      </p>
    </div>
  );
}

function Normals({ found }: { found: ConductData }) {
  if (!found.normal_share_kept) {
    return (
      <div className="panel">
        <p className="muted" style={{ margin: 0 }}>
          Nothing in the record states both a gross and a nett, so this business has no normal and
          nothing below is judged.
        </p>
      </div>
    );
  }
  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>This business&rsquo;s own normal</h2>
      <p className="muted">
        Section 10 asks for the comparison to be against what Zaco itself normally pays, not an
        outside benchmark. Both figures below are the middle of this record — a median, because a
        mean is pulled by the very outlier it is being used to find.
      </p>
      <table>
        <tbody>
          <tr>
            <td>Share of a sale the agent keeps</td>
            <td className="num mono">
              <strong>{found.normal_share_kept}</strong>
            </td>
          </tr>
          <tr>
            <td>Share of what was sent that did not sell</td>
            <td className="num mono">
              <strong>{dash(found.normal_never_sold)}</strong>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Kept({ found }: { found: ConductData }) {
  const kept = found.kept;
  if (!kept.length) return null;
  return (
    <>
      <h2>How much of the sale the agent kept</h2>
      <div className="panel">
        <p className="muted" style={{ margin: "0 0 0.7rem" }}>
          Every account sale is listed, not only the flagged ones — how ordinary the ordinary ones
          are is the whole basis for the comparison. Ordered by the rand difference from normal,
          because the share raises the question and the money decides whether it is worth asking.{" "}
          <strong>None of this is an accusation:</strong> a high deduction has innocent
          explanations, so the figures that raised it are shown beside it.
        </p>

        <KeptShareChart
          points={found.chart.kept}
          normal={found.chart.normal_share_kept}
          thresholds={found.thresholds}
        />

        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Account sale</th>
                <th>Agent</th>
                <th className="num">Gross</th>
                <th className="num">Nett</th>
                <th className="num">Kept</th>
                <th className="num">Share</th>
                <th className="num">Normal would be</th>
                <th className="num">Difference</th>
              </tr>
            </thead>
            <tbody>
              {kept.map((line) => (
                <tr key={line.account_sale} className={line.is_flagged ? "flagged" : undefined}>
                  <td className="mono">
                    {line.account_sale}{" "}
                    {line.is_flagged ? <span className="chip stops">above normal</span> : null}
                    {line.has_commodity_breakdown ? null : (
                      <span className="chip">no lines behind it</span>
                    )}
                  </td>
                  <td>{line.agent ?? <span className="muted">not named</span>}</td>
                  <td className="num mono">{line.gross}</td>
                  <td className="num mono">{line.nett}</td>
                  <td className="num mono">{line.kept}</td>
                  <td className="num mono">
                    <strong>{line.share}</strong>
                  </td>
                  <td className="num mono muted">{dash(line.normal_kept)}</td>
                  <td className="num mono">
                    {dash(line.excess)}
                    {line.times_normal ? (
                      <span className="muted"> ({line.times_normal})</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function NeverSold({ found }: { found: ConductData }) {
  const lines = found.never_sold;
  if (!lines.length) return null;
  return (
    <>
      <h2>How much of what was sent never sold</h2>
      <div className="panel">
        <p className="muted" style={{ margin: "0 0 0.7rem" }}>
          A consignment still selling has not failed to sell. Any whose last sale sits at the end
          of the record is set aside and counted here rather than judged — counting fruit that is
          still on the floor as fruit that did not move would say something false about the agent
          holding it.
        </p>
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th className="num">Sent</th>
                <th className="num">Sold, net</th>
                <th className="num">Not sold</th>
                <th className="num">Share</th>
                <th className="num">Normal</th>
                <th className="num">Consignments</th>
                <th>Still selling</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <Fragment key={line.agent ?? "unnamed"}>
                  <tr className={line.is_flagged ? "flagged" : undefined}>
                    <td>
                      {line.agent ?? <span className="muted">not named</span>}{" "}
                      {line.is_flagged ? <span className="chip stops">above normal</span> : null}
                    </td>
                    <td className="num">{line.cartons_sent}</td>
                    <td className="num">{line.cartons_net}</td>
                    <td className="num">{line.cartons_unsold}</td>
                    <td className="num mono">
                      {line.is_judged ? (
                        <strong>{dash(line.share)}</strong>
                      ) : (
                        <span className="muted">{dash(line.share)}</span>
                      )}
                    </td>
                    <td className="num mono muted">{dash(found.normal_never_sold)}</td>
                    <td className="num">{line.consignments}</td>
                    <td>
                      {line.still_selling ? (
                        <>
                          {line.still_selling}{" "}
                          <span className="muted">({line.still_selling_cartons} cartons)</span>
                        </>
                      ) : (
                        <span className="muted">none</span>
                      )}
                    </td>
                  </tr>
                  {line.why_not_judged ? (
                    <tr>
                      <td />
                      <td colSpan={7} className="finding-quiet">
                        Not judged — {line.why_not_judged}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export function Conduct() {
  const conduct = useConduct();
  const found = conduct.data;

  return (
    <Page title="Agent conduct" width="wide">
      <h1>Has the agent treated the money normally</h1>
      <p className="lede">
        Zaco is not on the floor when the fruit sells, so the only leverage is what the reports
        say. Two questions here can be answered from them and one cannot, and the one that cannot
        is inside the panel rather than beside it.
      </p>

      {conduct.isError ? <Problem error={conduct.error} /> : null}
      {conduct.isPending ? <Loading what="the record" /> : null}

      {found ? (
        <>
          {found.flagged_count ? (
            <p className="lede">
              <strong>{found.flagged_count}</strong> thing(s) sit far enough from this
              business&rsquo;s own normal to be worth asking about.
            </p>
          ) : (
            <p className="lede muted">
              Nothing sits far enough from this business&rsquo;s own normal to be worth asking
              about — on the two questions below, which are not all of them.
            </p>
          )}

          <BlindSpot found={found} />

          {found.caveats.length ? (
            <div className="warning">
              <strong>What would otherwise be read from the absence of a flag</strong>
              <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
                {found.caveats.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <Normals found={found} />
          <Kept found={found} />
          <NeverSold found={found} />
        </>
      ) : null}
    </Page>
  );
}
