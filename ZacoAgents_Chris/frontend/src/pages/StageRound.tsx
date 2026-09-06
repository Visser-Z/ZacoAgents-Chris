/**
 * A whole round, read together and shown as what it amounts to. Nothing is stored.
 *
 * The one thing here the page it replaced did not do: every file is classified as it is chosen,
 * before anything is staged. One unreadable document refuses the entire round -- staging the rest
 * would produce a picture that looks complete and is not -- so being told which file that is
 * *before* pressing the button is the difference between fixing one export and re-uploading five.
 *
 * That costs a read of each file. It is the same read staging does, done once per file instead of
 * once for the round, and it is worth it: `InspectionOut` already carries the confidence, so the
 * case where a Payment Details export was saved over a Daily Sales Detail is visible rather than
 * arriving later as a total that is quietly short.
 */

import { Fragment, useState } from "react";

import { ApiError, api, type Schemas } from "../api/client";
import { DropZone } from "../components/DropZone";
import { Page } from "../components/Page";
import { Problems } from "../components/Problems";

type Staged = Schemas["StagedRoundOut"];
type CartonFigures = Schemas["CartonsOut"];
type Inspection = Schemas["InspectionOut"];

/** What one chosen file turned out to be, before any of them are staged. */
interface Classified {
  file: File;
  kind: string | null;
  confidence: number | null;
  refused: string | null;
}

function Cartons({ cartons }: { cartons: CartonFigures }) {
  return (
    <>
      {cartons.sold} sold,{" "}
      {cartons.returns_reportable ? (
        <>{cartons.returned} back</>
      ) : (
        // Absent, not nought. No source for this consignment can express a return at all, and
        // "0 back" would be this system stating something no document does (section 6).
        <span className="muted" title="No source could report returns for this">
          returns not reported
        </span>
      )}
      , <strong>{cartons.net} net</strong>
    </>
  );
}

function Classification({ rows }: { rows: Classified[] }) {
  if (!rows.length) return null;
  const refused = rows.filter((row) => row.refused);
  return (
    <div className="panel">
      <p className="muted" style={{ margin: "0 0 0.5rem" }}>
        What each file turned out to be, read before anything is staged.
      </p>
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Read as</th>
            <th className="num">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.file.name}-${row.file.size}`}>
              <td className="mono">{row.file.name}</td>
              <td>
                {row.refused ? <span className="chip stops">not recognised</span> : row.kind}
              </td>
              <td className="num">
                {row.confidence == null ? "—" : `${(row.confidence * 100).toFixed(0)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {refused.length ? (
        <div className="warning" style={{ margin: "0.8rem 0 0" }}>
          {refused.length} file(s) were not recognised, so the round would be refused as a whole.
          {refused.map((row) => (
            <div key={row.file.name} className="muted" style={{ marginTop: "0.3rem" }}>
              <span className="mono">{row.file.name}</span> — {row.refused}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Round({ staged }: { staged: Staged }) {
  const totals = staged.totals;

  return (
    <>
      <h2>The round</h2>
      <div className="notice">
        <strong>{staged.sources.length} document(s)</strong> → {totals.deliveries} deliveries,{" "}
        {totals.consignments} consignments, <strong>{totals.rows} rows</strong>,{" "}
        {totals.account_sales} account sales.
      </div>

      <div className="panel">
        <table>
          <tbody>
            <tr>
              <td>Cartons</td>
              <td>
                <Cartons cartons={staged.cartons} />
              </td>
            </tr>
            <tr>
              <td>Cartons sent</td>
              <td>
                {totals.cartons_sent}{" "}
                <span className="muted">— counted once per consignment, not once per row</span>
              </td>
            </tr>
            <tr>
              <td>Gross value</td>
              <td>
                {totals.value}{" "}
                <span className="muted">
                  — cartons sold × unit price; the Nett arrives from the payment side
                </span>
              </td>
            </tr>
            <tr>
              <td>Products without a short code</td>
              <td>
                {totals.products_unresolved}{" "}
                <span className="muted">— a row cannot be written until each is captured</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <Problems problems={staged.problems.filter((p) => p.severity !== "note")} />

      <h2>
        Rows <span className="muted">(delivery × product × account sale)</span>
      </h2>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Delivery</th>
                <th>STM No</th>
                <th>Product</th>
                <th>Cartons</th>
                <th className="num">Gross</th>
                <th className="num">Price/crt</th>
                <th>Earliest date</th>
              </tr>
            </thead>
            <tbody>
              {staged.rows.map((row, index) => (
                <tr key={`${row.delivery_id}-${row.account_sale}-${row.product}-${index}`}>
                  <td className="mono">{row.delivery_id || "—"}</td>
                  <td className="mono">{row.account_sale_display}</td>
                  <td>
                    {row.product}
                    {row.short_code ? null : <span className="tag">no short code</span>}
                  </td>
                  <td>
                    <Cartons cartons={row.cartons} />
                  </td>
                  <td className="num">{row.value}</td>
                  <td className="num">{row.price ?? "—"}</td>
                  <td>{row.earliest_date || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2>Deliveries and what is on the floor</h2>
      {staged.deliveries.map((delivery, index) => (
        <div className="panel" key={`${delivery.delivery_id ?? "unidentified"}-${index}`}>
          <div className="delivery-head">
            <strong className="mono">{delivery.delivery_id || "(unidentified delivery)"}</strong>
            <span>
              <span className="muted">DN</span>{" "}
              {delivery.dn ?? <span className="tag">not captured yet</span>}
            </span>
            <span>
              <span className="muted">Supplier Ref</span>{" "}
              <span className="mono">{delivery.supplier_ref || "—"}</span>
            </span>
            <span>
              <span className="muted">Market</span>{" "}
              {delivery.market ?? <span className="tag">not stated</span>}
            </span>
            <span>
              <span className="muted">Agent</span> {delivery.agent || "—"}
            </span>
          </div>
          <div className="scroller">
            <table style={{ marginTop: "0.6rem" }}>
              <thead>
                <tr>
                  <th>Consignment</th>
                  <th>Product</th>
                  <th
                    className="num"
                    title="Belongs to the delivery. Counted once per consignment, never once per row."
                  >
                    Qty sent
                  </th>
                  <th>Cartons</th>
                  <th className="num">Value</th>
                  <th>Account sales</th>
                  <th className="num" title="Belongs to the delivery, not the account sale">
                    On market
                  </th>
                </tr>
              </thead>
              <tbody>
                {(delivery.consignments ?? []).map((consignment, position) => (
                  <tr key={`${consignment.consignment_id ?? "none"}-${position}`}>
                    <td className="mono">
                      {consignment.consignment_id || "(no consignment ID)"}
                      {consignment.consignment_id ? null : (
                        <span className="tag">cannot be tracked</span>
                      )}
                    </td>
                    <td>
                      {consignment.product}{" "}
                      {consignment.short_code ? (
                        <span className="tag">{consignment.short_code}</span>
                      ) : (
                        <span className="tag">no short code yet</span>
                      )}
                    </td>
                    <td className="num">{consignment.qty_sent ?? "—"}</td>
                    <td>
                      <Cartons cartons={consignment.cartons} />
                    </td>
                    <td className="num">{consignment.value}</td>
                    <td>
                      {(consignment.account_sales ?? []).length ? (
                        (consignment.account_sales ?? []).map((sale) => (
                          <span className="tag" key={sale}>
                            {sale}
                          </span>
                        ))
                      ) : (
                        <span className="muted">none yet</span>
                      )}
                    </td>
                    <td className="num">
                      {consignment.days_on_market == null ? "—" : `${consignment.days_on_market}d`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <h2>Account sales</h2>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>STM No</th>
                <th>Agent</th>
                <th>Paid</th>
                <th className="num">Gross</th>
                <th className="num">Nett</th>
                <th className="num">Agent kept</th>
                <th className="num">Rows</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {staged.account_sales.map((sale) => (
                <tr key={sale.number}>
                  <td className="mono">{sale.display_number}</td>
                  <td>{sale.agent || "—"}</td>
                  <td>{sale.date_paid || "—"}</td>
                  <td className="num">{sale.gross ?? "—"}</td>
                  <td className="num">{sale.nett ?? "—"}</td>
                  <td className="num">{sale.deduction_share ?? "—"}</td>
                  <td className="num">{sale.row_count}</td>
                  <td>
                    {sale.has_commodity_breakdown ? null : (
                      <span className="tag">no breakdown — can never reconcile</span>
                    )}
                    {sale.row_count === 0 && sale.has_commodity_breakdown ? (
                      <span className="tag">paid, no sales behind it</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {staged.unpaid_dockets.length ? (
        <>
          <h2>
            Sold, not yet in any payment run{" "}
            <span className="muted">({staged.unpaid_dockets.length})</span>
          </h2>
          <p className="muted">
            A row is delivery × product × account sale. These have no account sale, so no row can
            be written for them yet.
          </p>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Consignment</th>
                  <th>Docket</th>
                  <th>Sold</th>
                  <th className="num">Qty</th>
                  <th className="num">Value</th>
                </tr>
              </thead>
              <tbody>
                {staged.unpaid_dockets.map((docket) => (
                  <tr key={docket.docket_number}>
                    <td className="mono">{docket.consignment_id || "—"}</td>
                    <td className="mono">{docket.docket_number}</td>
                    <td>{docket.date_sold || "—"}</td>
                    <td className="num">{docket.quantity ?? "—"}</td>
                    <td className="num">{docket.value ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {staged.suggestions.length ? (
        <>
          <h2>
            Possible product links <span className="muted">({staged.suggestions.length})</span>
          </h2>
          <p className="muted">
            Not applied. Merging on resemblance would put one product&rsquo;s takings under
            another&rsquo;s name in every ranking.
          </p>
          {staged.suggestions.map((suggestion) => (
            <div className="warning" key={`${suggestion.left}||${suggestion.right}`}>
              {suggestion.reason}
            </div>
          ))}
        </>
      ) : null}

      <h2>Products</h2>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Operator short code</th>
              <th>Also known as</th>
            </tr>
          </thead>
          <tbody>
            {staged.products.map((product) => (
              <tr key={product.key}>
                <td>{product.display_name}</td>
                <td>
                  {product.short_code ?? <span className="tag">must be captured</span>}
                </td>
                <td>
                  {(product.names ?? []).length > 1
                    ? (product.names ?? []).map((name) => (
                        <div className="mono" style={{ fontSize: "0.9em" }} key={name}>
                          {name}
                        </div>
                      ))
                    : null}
                  {(product.merge_reasons ?? []).map((reason) => (
                    <div className="muted" style={{ fontSize: "0.88em" }} key={reason}>
                      merged: {reason}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Problems problems={staged.problems.filter((p) => p.severity === "note")} />

      <p className="muted" style={{ fontSize: "0.9em" }}>
        Nothing has been stored. Capturing the delivery note numbers and the missing short codes
        comes next, and no row can be written until they are answered.
      </p>
    </>
  );
}

export function StageRound() {
  const [files, setFiles] = useState<File[]>([]);
  const [classified, setClassified] = useState<Classified[]>([]);
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [staged, setStaged] = useState<Staged | null>(null);
  const [problem, setProblem] = useState("");

  async function classify(chosen: File[]) {
    setFiles(chosen);
    setStaged(null);
    setProblem("");
    setClassified([]);
    if (!chosen.length) return;

    setReading(true);
    try {
      const rows = await Promise.all(
        chosen.map(async (file): Promise<Classified> => {
          try {
            const found = await api.inspect<Inspection>("/api/ingest/inspect", file);
            return { file, kind: found.kind_title, confidence: found.confidence, refused: null };
          } catch (error) {
            const why =
              error instanceof ApiError ? error.message : "It could not be read at all.";
            return { file, kind: null, confidence: null, refused: why };
          }
        }),
      );
      setClassified(rows);
    } finally {
      setReading(false);
    }
  }

  async function stage() {
    setBusy(true);
    setProblem("");
    setStaged(null);
    try {
      setStaged(await api.upload<Staged>("/api/rounds/stage", files));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The round could not be staged.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Stage a round" width="wide">
      <h1>Stage a round</h1>
      <p className="lede">
        Upload the documents for one round together. This shows what they amount to: the
        deliveries, the consignments on the floor, and the rows those would become. Nothing is
        written anywhere.
      </p>

      <div className="panel">
        <DropZone
          id="files"
          label="The documents"
          hint="Any of the five kinds, in any order."
          multiple
          files={files}
          onFiles={(chosen) => void classify(chosen)}
          disabled={busy || reading}
        />
        <p className="muted" style={{ fontSize: "0.88em", margin: "0.4rem 0 0" }}>
          If one of them cannot be identified, the whole round is refused — staging the rest would
          show a picture that looks complete and is not.
        </p>
        <button type="button" onClick={() => void stage()} disabled={busy || reading || !files.length}>
          {busy ? "Staging…" : "Stage it"}
        </button>
      </div>

      {reading ? <p className="muted">Reading each file…</p> : null}
      <Classification rows={classified} />

      {problem ? (
        <>
          <h2>Refused</h2>
          <div className="error">{problem}</div>
        </>
      ) : null}

      {staged ? (
        <Fragment key={staged.sources.join("|")}>
          <Round staged={staged} />
        </Fragment>
      ) : null}
    </Page>
  );
}
