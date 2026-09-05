/**
 * Everything about a round that is not an open question.
 *
 * The queue is what an operator works through; this is what they check it against. All of it is
 * carried over unchanged in substance -- the two documents that disagree, the records counted once
 * and said out loud, the numbers still held by a delivery that has gone, the rows as they stand,
 * and what has been done to the round and by whom.
 *
 * Every destructive action still demands a typed reason, and the button stays disabled until
 * there is one. That is not a nicety: taking a document out of a round changes every figure
 * derived from it, and the reason is the only thing that will explain the change to whoever reads
 * the workbook next.
 */

import { Fragment, useState } from "react";

import type { Round, RoundDocument, Suspension } from "../api/rounds";

const when = (value: string) => String(value).slice(0, 16).replace("T", " ");
const size = (bytes: number) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} kB`);

/** A recorded "no delivery note" is an answer (D11). Showing it as waiting would put it back into
 *  the state the recording exists to get it out of. */
function DnCell({ dn, provenance }: { dn: string | null | undefined; provenance?: string | null }) {
  if (dn) return <>{dn}</>;
  if (provenance === "none_foreign_producer") {
    return (
      <span className="chip" title="Recorded, with a reason">
        no DN — recorded
      </span>
    );
  }
  return <span className="tag">waiting</span>;
}

/** A short form that will not submit until a reason has been typed. */
function WithReason({
  label,
  placeholder,
  action,
  busy,
  onSubmit,
  secondary = false,
}: {
  label: string;
  placeholder: string;
  action: string;
  busy: boolean;
  onSubmit: (reason: string) => void;
  secondary?: boolean;
}) {
  const [reason, setReason] = useState("");
  const id = `why-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (reason.trim()) onSubmit(reason.trim());
      }}
    >
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        value={reason}
        placeholder={placeholder}
        onChange={(event) => setReason(event.target.value)}
      />
      <button type="submit" className={secondary ? "secondary" : undefined} disabled={busy || !reason.trim()}>
        {action}
      </button>
    </form>
  );
}

function SuspensionCard({
  suspension,
  busy,
  onDecide,
}: {
  suspension: Suspension;
  busy: boolean;
  onDecide: (source: string, reason: string) => void;
}) {
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");

  if (suspension.is_decided) {
    return (
      <div className="panel">
        <strong className="mono">{suspension.subject_key}</strong>{" "}
        <span className="tag">settled</span>
        <p className="muted" style={{ margin: "0.3rem 0 0" }}>
          {suspension.description}
        </p>
        <p style={{ margin: "0.3rem 0 0" }}>
          Took <strong>{suspension.chosen_source}</strong> — {suspension.reason}{" "}
          <span className="muted">({suspension.decided_by || "?"})</span>
        </p>
      </div>
    );
  }

  return (
    <form
      className="panel"
      onSubmit={(event) => {
        event.preventDefault();
        if (source.trim() && reason.trim()) onDecide(source.trim(), reason.trim());
      }}
    >
      <strong className="mono">{suspension.subject_key}</strong>
      <p style={{ margin: "0.3rem 0 0" }}>{suspension.description}</p>
      <div className="warning" style={{ margin: "0.5rem 0" }}>
        {suspension.differences}
      </div>
      <label htmlFor={`src-${suspension.id}`}>Which document is right?</label>
      <input
        id={`src-${suspension.id}`}
        type="text"
        value={source}
        placeholder="the filename you are taking"
        onChange={(event) => setSource(event.target.value)}
      />
      <label htmlFor={`why-${suspension.id}`}>Why (required)</label>
      <input
        id={`why-${suspension.id}`}
        type="text"
        value={reason}
        placeholder="e.g. the full export, not the narrowed re-run"
        onChange={(event) => setReason(event.target.value)}
      />
      <button type="submit" disabled={busy || !source.trim() || !reason.trim()}>
        Record the decision
      </button>
    </form>
  );
}

function DocumentRow({
  file,
  editable,
  busy,
  onWithdraw,
  onRestore,
}: {
  file: RoundDocument;
  editable: boolean;
  busy: boolean;
  onWithdraw: (reason: string) => void;
  onRestore: () => void;
}) {
  const [asking, setAsking] = useState(false);

  return (
    <>
      <tr>
        <td
          className="mono"
          style={file.state === "withdrawn" ? { textDecoration: "line-through" } : undefined}
        >
          {file.filename}
        </td>
        <td className="muted">{file.kind.replace(/_/g, " ")}</td>
        <td className="num muted">{size(file.byte_count)}</td>
        <td>
          {file.state === "withdrawn" ? (
            <span className="tag">removed</span>
          ) : file.state === "duplicate" ? (
            <span className="tag">already read in round {file.duplicate_of_round_id}</span>
          ) : (
            <span className="muted">counted</span>
          )}
        </td>
        <td>
          {!editable ? null : file.state === "withdrawn" ? (
            <button type="button" className="link" disabled={busy} onClick={onRestore}>
              Put it back
            </button>
          ) : (
            <button type="button" className="link" onClick={() => setAsking((was) => !was)}>
              Remove
            </button>
          )}
        </td>
      </tr>
      {file.state === "withdrawn" ? (
        <tr>
          <td colSpan={5} className="muted">
            Taken out by {file.withdrawn_by || "?"} — {file.withdrawn_reason}
          </td>
        </tr>
      ) : null}
      {asking && editable && file.state !== "withdrawn" ? (
        <tr>
          <td colSpan={5}>
            <WithReason
              label="Why is this document being taken out? (required)"
              placeholder="e.g. this is another producer's export, uploaded by mistake"
              action="Take it out of the round"
              busy={busy}
              onSubmit={(reason) => {
                setAsking(false);
                onWithdraw(reason);
              }}
            />
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function RoundDetail({
  round,
  busy,
  onDecideSuspension,
  onWithdraw,
  onRestore,
  onRelease,
  onReopen,
  onAbandon,
  onClose,
}: {
  round: Round;
  busy: boolean;
  onDecideSuspension: (id: number, source: string, reason: string) => void;
  onWithdraw: (documentId: number, reason: string) => void;
  onRestore: (documentId: number) => void;
  onRelease: (deliveryId: string, reason: string) => void;
  onReopen: (reason: string) => void;
  onAbandon: (reason: string) => void;
  onClose: () => void;
}) {
  const totals = round.totals;
  const editable = round.summary.status === "staged";
  const suspensions = round.suspensions ?? [];
  const alerts = round.alerts ?? [];
  const orphans = round.orphaned_delivery_notes ?? [];
  const notes = round.delivery_notes ?? [];
  const documents = round.documents ?? [];
  const events = round.events ?? [];
  const rows = round.rows ?? [];
  const counted = documents.filter((file) => file.state === "counted").length;

  return (
    <>
      <div className="panel">
        <table>
          <tbody>
            <tr>
              <td>Deliveries / consignments / rows</td>
              <td>
                {totals.deliveries} / {totals.consignments} / <strong>{totals.rows}</strong>
              </td>
            </tr>
            <tr>
              <td>Cartons sent</td>
              <td>
                {totals.cartons_sent} <span className="muted">— once per consignment</span>
              </td>
            </tr>
            <tr>
              <td>Cartons net</td>
              <td>{totals.cartons_net}</td>
            </tr>
            <tr>
              <td>Gross</td>
              <td>{totals.value}</td>
            </tr>
            <tr>
              <td>Still on the floor</td>
              <td>
                {totals.closing_stock}{" "}
                <span className="muted">— carried into the next round</span>
              </td>
            </tr>
            <tr>
              <td>The operator&rsquo;s book</td>
              <td className="muted">{round.book.detail}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {suspensions.length ? (
        <>
          <h2>
            Two documents disagree{" "}
            <span className="muted">
              ({suspensions.filter((one) => !one.is_decided).length} open)
            </span>
          </h2>
          {suspensions.map((suspension) => (
            <SuspensionCard
              key={suspension.id}
              suspension={suspension}
              busy={busy}
              onDecide={(source, reason) => onDecideSuspension(suspension.id, source, reason)}
            />
          ))}
        </>
      ) : null}

      {alerts.length ? (
        <>
          <h2>
            Counted once, and said out loud <span className="muted">({alerts.length})</span>
          </h2>
          <p className="muted">
            These were read and deliberately not counted again. A skip nobody can see is
            indistinguishable from a record that went missing.
          </p>
          {alerts.map((alert, index) => (
            <div className="warning" key={`${alert.subject}-${index}`}>
              <span className="mono">{alert.subject}</span> — {alert.message}
            </div>
          ))}
        </>
      ) : null}

      {orphans.length ? (
        <>
          <h2>
            Numbers still held <span className="muted">({orphans.length})</span>
          </h2>
          <p className="muted">
            Approved for a delivery this round no longer contains. Until it is released, the number
            stays out of the series and cannot be proposed for anything else.
          </p>
          {orphans.map((note) => (
            <div className="panel" key={note.delivery_id}>
              <strong className="mono">{note.dn ?? "no DN recorded"}</strong> — approved for
              delivery <span className="mono">{note.delivery_id}</span> by{" "}
              {note.approved_by || "?"}
              <p className="muted" style={{ margin: "0.3rem 0 0" }}>
                {note.operator_reason || note.reasoning}
              </p>
              <WithReason
                label="Why give the number back? (required)"
                placeholder="e.g. the delivery came from a file that was removed"
                action="Release the number"
                busy={busy}
                onSubmit={(reason) => onRelease(note.delivery_id, reason)}
              />
            </div>
          ))}
        </>
      ) : null}

      {notes.length ? (
        <>
          <h2>
            Delivery notes approved <span className="muted">({notes.length})</span>
          </h2>
          <div className="panel">
            <div className="scroller">
              <table>
                <thead>
                  <tr>
                    <th>Delivery</th>
                    <th>DN</th>
                    <th>How</th>
                    <th>Reason</th>
                    <th>By</th>
                  </tr>
                </thead>
                <tbody>
                  {notes.map((note) => (
                    <tr key={note.delivery_id}>
                      <td className="mono">{note.delivery_id}</td>
                      <td className="mono">
                        {note.dn ?? <span className="tag">none, recorded</span>}
                      </td>
                      <td>{note.provenance.replace(/_/g, " ")}</td>
                      <td className="muted">{note.operator_reason || note.reasoning}</td>
                      <td className="muted">{note.approved_by || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      <h2>Rows as they stand</h2>
      <p className="muted">
        Opening stock runs down the consignment, not the row: the second account sale opens where
        the first one closed, and what is left carries into the next round.
      </p>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>DN</th>
                <th>Date</th>
                <th>STM No</th>
                <th>Description</th>
                <th className="num">Opening</th>
                <th className="num">Sold</th>
                <th className="num">Left</th>
                <th className="num">Gross</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.delivery_id}-${row.account_sale}-${row.product}-${index}`}>
                  <td className="mono">
                    <DnCell dn={row.dn} provenance={row.dn_provenance} />
                  </td>
                  <td>{row.grouping_date || row.earliest_date || "—"}</td>
                  <td className="mono">{row.account_sale_display}</td>
                  <td>
                    {row.short_code ?? (
                      <>
                        <span className="tag">no code</span>{" "}
                        <span className="muted">{row.product}</span>
                      </>
                    )}
                  </td>
                  <td className="num">
                    {row.stock?.opening ?? "—"}
                    {row.stock?.is_carried_forward ? (
                      <span className="tag">carried in</span>
                    ) : null}
                  </td>
                  <td className="num">{row.stock?.sold ?? "—"}</td>
                  <td className="num">{row.stock?.closing ?? "—"}</td>
                  <td className="num">{row.value}</td>
                  <td>
                    {row.is_writable ? null : (
                      <span className="tag">{(row.blocked_by ?? []).join(", ")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {(round.stock_notes ?? []).map((note) => (
        <div className="warning" key={note}>
          {note}
        </div>
      ))}

      <h2>
        Documents in this round{" "}
        <span className="muted">
          ({counted} of {documents.length} counted)
        </span>
      </h2>
      <p className="muted">
        Everything above is derived from these files and nothing else. Taking one out keeps the
        file and the reason, and removes its figures from the round.
      </p>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Read as</th>
                <th className="num">Size</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {documents.map((file) => (
                <DocumentRow
                  key={file.id}
                  file={file}
                  editable={editable}
                  busy={busy}
                  onWithdraw={(reason) => onWithdraw(file.id, reason)}
                  onRestore={() => onRestore(file.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {events.length ? (
        <>
          <h2>What has been done to this round</h2>
          <div className="panel">
            <div className="scroller">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>What</th>
                    <th>Which</th>
                    <th>Why</th>
                    <th>By</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, index) => (
                    <Fragment key={`${event.at}-${event.subject}-${index}`}>
                      <tr>
                        <td className="muted">{when(event.at)}</td>
                        <td>{event.action.replace(/_/g, " ")}</td>
                        <td className="mono">{event.subject}</td>
                        <td className="muted">{event.reason || "—"}</td>
                        <td className="muted">{event.by || "—"}</td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      <div className="panel">
        <button type="button" onClick={onClose} disabled={!round.is_clear || !editable || busy}>
          {editable ? "Close the queue" : "Queue closed"}
        </button>
        <p className="muted" style={{ fontSize: "0.9em", margin: "0.5rem 0 0" }}>
          {editable
            ? "Closing the queue marks this round ready for the workbook. It stays open until every question above is answered."
            : round.summary.status === "resolved"
              ? "This round is resolved. Appending it to the workbook is the next page."
              : "This round was put aside. Its documents count for nothing and can be uploaded again."}
        </p>
      </div>

      {!editable ? (
        <div className="panel">
          <p className="muted" style={{ margin: "0 0 0.5rem" }}>
            A wrong document is usually only noticed after the round is closed. Reopening puts it
            back to staged so it can be taken out. While the round is open, later rounds are
            derived without it.
          </p>
          <WithReason
            label="Why is this round being reopened? (required)"
            placeholder="e.g. the payment file turned out to be another producer's"
            action="Reopen the round"
            busy={busy}
            onSubmit={onReopen}
          />
        </div>
      ) : (
        <div className="panel">
          <p className="muted" style={{ margin: "0 0 0.5rem" }}>
            If every file in this round was the wrong one, put the whole round aside. It is kept,
            and its documents stop blocking a fresh upload of the same files.
          </p>
          <WithReason
            label="Why is the whole round being put aside? (required)"
            placeholder="e.g. uploaded against the wrong producer"
            action="Put the round aside"
            busy={busy}
            secondary
            onSubmit={onAbandon}
          />
        </div>
      )}
    </>
  );
}
