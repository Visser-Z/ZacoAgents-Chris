/**
 * What each supplier earned, is owed, and handed over that never sold.
 *
 * Everything above the Nett line is what the agents' reports state. Everything below it exists
 * only here: the agents see Zaco as the supplier and know nothing about the farmers behind it.
 *
 * A consignment with no agreed commission produces no settlement at all and is kept in its own
 * section rather than folded into a total (D13). That is what the meter at the top measures --
 * not how much money there is, but how much of the business the money below can speak for.
 */

import { Fragment, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../api/client";
import { Page } from "../components/Page";
import { Loading, NotReported, Problem } from "../components/values";
import { useSession } from "../auth/session";
import { useSettlement } from "../api/queries";
import type { Settlement as SettlementData } from "../api/queries";
import { Meter } from "../charts/BoardCharts";

type Line = SettlementData["settled"][number];

function LineRows({ lines, withMoney }: { lines: Line[]; withMoney: boolean }) {
  return (
    <>
      {lines.map((line) => (
        <Fragment key={line.consignment_id}>
          <tr>
            <td className="mono">{line.consignment_id}</td>
            <td>{line.product}</td>
            <td className="muted">{line.supplier || "—"}</td>
            <td className="num">{line.percent ? `${line.percent}%` : "—"}</td>
            <td className="num mono">{line.nett || "—"}</td>
            {withMoney ? (
              <>
                <td className="num mono">{line.zaco_keeps || "—"}</td>
                <td className="num mono">
                  <strong>{line.owed_to_supplier || "—"}</strong>
                </td>
              </>
            ) : null}
            <td className="num">{line.cartons_sold}</td>
            <td className="num">
              {line.cartons_unsold === null ? <NotReported /> : line.cartons_unsold}
            </td>
          </tr>
          {line.blocked_by ? (
            <tr>
              <td />
              <td colSpan={withMoney ? 8 : 6} className="finding-quiet">
                {line.blocked_by}
              </td>
            </tr>
          ) : null}
        </Fragment>
      ))}
    </>
  );
}

function Section({
  title,
  lines,
  withMoney,
  empty,
}: {
  title: string;
  lines: Line[];
  withMoney: boolean;
  empty: string;
}) {
  if (!lines.length) {
    return (
      <>
        <h2>
          {title} <span className="muted">(none)</span>
        </h2>
        <p className="muted">{empty}</p>
      </>
    );
  }
  return (
    <>
      <h2>
        {title} <span className="muted">({lines.length})</span>
      </h2>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Consignment</th>
                <th>Product</th>
                <th>Supplier</th>
                <th className="num">Terms</th>
                <th className="num">Nett</th>
                {withMoney ? (
                  <>
                    <th className="num">Zaco keeps</th>
                    <th className="num">Owed</th>
                  </>
                ) : null}
                <th className="num">Sold</th>
                <th className="num">Never sold</th>
              </tr>
            </thead>
            <tbody>
              <LineRows lines={lines} withMoney={withMoney} />
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function AddSupplier() {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");

  const add = useMutation({
    mutationFn: () => api.post("/api/suppliers", { name: name.trim(), contact: contact.trim() }),
    onSuccess: async () => {
      setName("");
      setContact("");
      // The register, the sections and the totals are all re-derived from the same record, so the
      // whole board is asked again rather than one part of it being patched to look right.
      await client.invalidateQueries({ queryKey: ["settlement"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate();
  }

  return (
    <form className="panel" onSubmit={submit}>
      {add.isError ? (
        <div className="error">
          {add.error instanceof ApiError ? add.error.message : "Could not add that supplier."}
        </div>
      ) : null}
      <label htmlFor="supplier-name">Add a supplier</label>
      <input
        id="supplier-name"
        type="text"
        placeholder="e.g. Sunnyvale Orchards"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <label htmlFor="supplier-contact">Contact (optional)</label>
      <input
        id="supplier-contact"
        type="text"
        value={contact}
        onChange={(event) => setContact(event.target.value)}
      />
      <button type="submit" disabled={add.isPending || !name.trim()}>
        {add.isPending ? "Adding…" : "Add"}
      </button>
    </form>
  );
}

export function Settlement() {
  const settlement = useSettlement();
  const { can } = useSession();
  const found = settlement.data;

  const settled = found?.settled.length ?? 0;
  const total =
    settled + (found?.awaiting_terms.length ?? 0) + (found?.awaiting_payment.length ?? 0);

  return (
    <Page title="Settlement" width="wide">
      <h1>Settlement</h1>
      <p className="lede">
        Everything above the Nett line the agent&rsquo;s reports state. Everything below it exists
        only here — the agents see Zaco as the supplier and know nothing about the farmers behind
        it. A consignment with no agreed commission produces no settlement at all, and is shown in
        its own section rather than folded into a total.
      </p>

      {settlement.isError ? <Problem error={settlement.error} /> : null}
      {settlement.isPending ? <Loading what="settlement" /> : null}

      {found ? (
        <>
          <div className="panel">
            <Meter
              title="How much of the business can be settled"
              done={settled}
              total={total}
              legend={`${settled} of ${total} consignment(s)`}
              caption={found.coverage}
            />
            <table>
              <tbody>
                <tr>
                  <td>Owed to suppliers</td>
                  <td className="num mono">{found.total_owed}</td>
                </tr>
                <tr>
                  <td>Zaco&rsquo;s share</td>
                  <td className="num mono">{found.total_kept}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {found.by_supplier.length ? (
            <>
              <h2>By supplier</h2>
              <div className="panel">
                <table>
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th className="num">Earned</th>
                      <th className="num">Paid</th>
                      <th className="num">Owed</th>
                      <th className="num">Cartons never sold</th>
                      <th className="num">Lines</th>
                    </tr>
                  </thead>
                  <tbody>
                    {found.by_supplier.map((row) => (
                      <tr key={row.supplier}>
                        <td>{row.supplier}</td>
                        <td className="num mono">{row.earned}</td>
                        <td className="num mono">{row.paid}</td>
                        <td className="num mono">
                          <strong>{row.owed}</strong>
                        </td>
                        <td className="num">
                          {row.cartons_unsold === null ? <NotReported /> : row.cartons_unsold}
                        </td>
                        <td className="num muted">{row.consignments}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted" style={{ fontSize: "0.9em", margin: "0.6rem 0 0" }}>
                  Cartons that never sold cost the supplier, not Zaco — on consignment the supplier
                  is paid on what sold. They are shown because they are worth knowing, not because
                  they are owed for.
                </p>
              </div>
            </>
          ) : null}

          <h2>
            Suppliers <span className="muted">({found.suppliers.length})</span>
          </h2>
          {found.suppliers.length ? (
            <div className="panel">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Contact</th>
                    <th>Added by</th>
                  </tr>
                </thead>
                <tbody>
                  {found.suppliers.map((supplier) => (
                    <tr key={supplier.name}>
                      <td>{supplier.name}</td>
                      <td className="muted">{supplier.contact || "—"}</td>
                      <td className="muted">{supplier.created_by || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">
              None yet. Suppliers appear in no report — the agents see Zaco as the supplier — so
              the register starts empty and is filled by hand.
            </p>
          )}

          {/* Offered only to an account that may record terms. The server refuses it either way;
              a form that always fails is just a slower refusal. */}
          {can("record_terms") ? <AddSupplier /> : null}

          <Section
            title="Settled"
            lines={found.settled}
            withMoney
            empty="Nothing can be settled yet. A consignment needs both agreed terms and a payment that reconciles."
          />
          <Section
            title="Awaiting terms"
            lines={found.awaiting_terms}
            withMoney={false}
            empty="Every consignment with a payment behind it has agreed terms."
          />
          <Section
            title="Awaiting payment"
            lines={found.awaiting_payment}
            withMoney={false}
            empty="Nothing is waiting on a payment run."
          />
        </>
      ) : null}
    </Page>
  );
}
