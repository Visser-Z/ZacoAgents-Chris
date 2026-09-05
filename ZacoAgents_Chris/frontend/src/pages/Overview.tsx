/**
 * The first page after signing in.
 *
 * `home.html` still opens with "Phase 0 is in place ... nothing reports a figure yet", which
 * stopped being true several phases ago -- the record is read, resolved, appended, reconciled,
 * settled and reported on. That notice is not carried over; the Jinja copy of it goes when the
 * Jinja pages do.
 */

import { Page } from "../components/Page";
import { DESCRIPTIONS } from "../permissions";
import { useSession } from "../auth/session";
import type { Permission } from "../auth/session";

const ORDER: readonly Permission[] = [
  "ingest",
  "resolve",
  "append",
  "record_terms",
  "view_reports",
  "admin",
];

export function Overview() {
  const { user } = useSession();
  const held = ORDER.filter((permission) => user?.permissions.includes(permission));

  return (
    <Page title="Zaco account sales">
      <h1>Zaco account sales</h1>
      <p className="lede">
        Reads a round of market agent reports, resolves the facts those reports do not carry, and
        appends the result to the operator&rsquo;s live workbook.
      </p>

      <h2>What your account may do</h2>
      <div className="panel">
        {held.length ? (
          <table>
            <tbody>
              {held.map((permission) => (
                <tr key={permission}>
                  <td className="mono">{permission}</td>
                  <td>{DESCRIPTIONS[permission]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">
            Your account has no permissions yet. An administrator grants them individually.
          </p>
        )}
      </div>

      <h2>Where the decisions are written down</h2>
      <div className="panel">
        <p style={{ marginBottom: 0 }}>
          Every call this system makes where the reports left a choice open is recorded in{" "}
          <code>docs/DECISIONS.md</code>, together with what was rejected and why, and the
          questions that are still open. Those open questions are surfaced in the interface as
          they come up rather than being guessed at.
        </p>
      </div>
    </Page>
  );
}
