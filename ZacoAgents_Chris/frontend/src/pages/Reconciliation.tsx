/**
 * Section 8: what was sold under each account sale against what was paid for it.
 *
 * Accumulated across every closed round rather than one round at a time. A consignment sells
 * across rounds and a payment lands in whichever round it happened to be loaded in, so a
 * per-round view would call the same account sale unpaid in one place and unexplained in another.
 */

import { Fragment } from "react";

import { Page } from "../components/Page";
import { Loading, Problem } from "../components/values";
import { useBoard } from "../api/queries";
import type { Board } from "../api/queries";
import { ReconciliationStates, type StateRow } from "../charts/BoardCharts";

function Group({ board, state }: { board: Board; state: string }) {
  const items = board.grouped[state] ?? [];
  const label = board.labels[state] ?? state;

  if (!items.length) {
    return (
      <>
        <h2>
          {label} <span className="muted">(none)</span>
        </h2>
        <p className="muted">Nothing is in this state.</p>
      </>
    );
  }

  return (
    <>
      <h2>
        {label}{" "}
        <span className="muted">
          ({items.length}, nett {board.totals[state] ?? "R0.00"})
        </span>
      </h2>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Account sale</th>
                <th>Agent</th>
                <th className="num">Sales side</th>
                <th className="num">Payment side</th>
                <th className="num">Difference</th>
                <th className="num">Nett</th>
                <th className="num">Rows</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <Fragment key={row.account_sale}>
                  <tr>
                    <td className="mono">{row.display_number}</td>
                    <td className="muted">{row.agent || "—"}</td>
                    <td className="num">{row.sold || "—"}</td>
                    <td className="num">{row.paid || "—"}</td>
                    {/* Agreement is to the cent (section 8), so a difference is shown in full
                        rather than rounded to something that looks tidy. Nought is left blank:
                        the row above already says both sides agree. */}
                    <td className="num">
                      {row.difference && row.difference !== "R0.00" ? (
                        <strong>{row.difference}</strong>
                      ) : null}
                    </td>
                    <td className="num">{row.nett || "—"}</td>
                    <td className="num muted">{row.row_count || ""}</td>
                  </tr>
                  <tr>
                    <td />
                    <td colSpan={6} className="finding-quiet">
                      {row.note}{" "}
                      {row.can_never_reconcile ? (
                        <span className="chip stops">can never reconcile</span>
                      ) : null}
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export function Reconciliation() {
  const board = useBoard();
  const found = board.data;

  const rows: StateRow[] = found
    ? found.states.map((state) => ({
        state,
        label: found.labels[state] ?? state,
        count: (found.grouped[state] ?? []).length,
        total: found.totals[state] ?? "R0.00",
      }))
    : [];

  return (
    <Page title="Reconciliation" width="wide">
      <h1>Reconciliation</h1>
      <p className="lede">
        What the sales side says was sold under each account sale, against what the payment side
        says was paid for it. Accumulated across every round in the record, not one round at a
        time — a consignment sells across rounds and a payment lands in whichever round it was
        loaded in, so a per-round view would call the same account sale unpaid in one place and
        unexplained in another.
      </p>

      {board.isError ? <Problem error={board.error} /> : null}
      {board.isPending ? <Loading what="the board" /> : null}

      {found && !found.rounds_covered ? (
        <p className="muted">
          No round has been closed yet. An account sale reaches this board once the round carrying
          it has had its queue closed.
        </p>
      ) : null}

      {found && found.rounds_covered ? (
        <>
          <p className="muted">Over {found.rounds_covered} closed round(s).</p>
          <div className="panel">
            <ReconciliationStates rows={rows} />
          </div>
          {found.states.map((state) => (
            <Group key={state} board={found} state={state} />
          ))}
        </>
      ) : null}
    </Page>
  );
}
