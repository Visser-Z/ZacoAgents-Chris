/**
 * The operator's live book: what is in it, what a round would put in it, and how to get back.
 *
 * The round being looked at is in the address bar. This is the one page where being able to send
 * somebody a link that opens on the same rows matters most -- the argument about an append is
 * always about specific rows, and "open the workbook page and click round 4" is how the wrong
 * round gets looked at.
 *
 * Nothing here writes without being asked twice: the append button is disabled until every row of
 * the round can be written, and a rollback will not submit without a typed reason.
 */

import { Fragment, useState } from "react";
import { useSearchParams } from "react-router";

import { Page } from "../components/Page";
import { Loading, Problem } from "../components/values";
import { useToast } from "../components/Toasts";
import { useAppend, useBook, usePreview, useRollBack, type Book, type Preview } from "../api/workbook";
import { Grid } from "../workbook/Grid";

const when = (value: string | null | undefined) =>
  value ? String(value).slice(0, 16).replace("T", " ") : "—";
const size = (bytes: number) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} kB`);

function State({ book }: { book: Book }) {
  if (!book.is_readable) return <div className="warning">{book.problem}</div>;
  const theirs = Object.keys(book.unknown_headers).length;
  return (
    <div className="panel">
      <table>
        <tbody>
          <tr>
            <td>File</td>
            <td className="mono">
              {book.filename} <span className="muted">({size(book.byte_count)})</span>
            </td>
          </tr>
          <tr>
            <td>Data sheet</td>
            <td className="mono">
              {book.sheet_name}{" "}
              <span className="muted">— found by its header row, not by position</span>
            </td>
          </tr>
          <tr>
            <td>Columns</td>
            <td>
              {book.order.length + theirs}, of which {theirs}{" "}
              <span className="muted">belong to the operator and are never touched</span>
            </td>
          </tr>
          <tr>
            <td>Rows already in it</td>
            <td>{book.row_count}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Rounds({ book, onShow }: { book: Book; onShow: (id: number) => void }) {
  // A rollback restores the file and deliberately leaves the round's appended mark alone, so the
  // record can go on claiming rows the book no longer has. Say which, rather than leaving the
  // operator to notice.
  const off = book.appended_rounds.filter((round) => !round.agrees);
  const checked = book.appended_rounds.find((round) => round.checked)?.checked ?? "";

  return (
    <>
      <h2>
        Rounds <span className="muted">({book.ready_rounds.length} ready)</span>
      </h2>
      {book.ready_rounds.length ? (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Round</th>
                <th>Queue closed</th>
                <th>By</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {book.ready_rounds.map((round) => (
                <tr key={round.round_id}>
                  <td className="mono">#{round.round_id}</td>
                  <td className="muted">{when(round.resolved_at)}</td>
                  <td className="muted">{round.resolved_by || "—"}</td>
                  <td>
                    <button type="button" className="link" onClick={() => onShow(round.round_id)}>
                      See what would be written
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">
          No round is waiting. A round reaches here once every question in its queue is answered
          and the queue is closed on the Resolution queue page.
        </p>
      )}

      {book.appended_rounds.length ? (
        <>
          <h2>Already in the book</h2>
          {off.length ? (
            <div className="warning">
              <strong>
                {off.length} of {book.appended_rounds.length} appended round(s) no longer match the
                book.
              </strong>{" "}
              Nothing has been changed on either side — this is only what the two now say.
            </div>
          ) : null}
          <div className="panel">
            <div className="scroller">
              <table>
                <thead>
                  <tr>
                    <th>Round</th>
                    <th>Rows</th>
                    <th>When</th>
                    <th>By</th>
                    <th>Still in the book</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {book.appended_rounds.map((round) => (
                    <Fragment key={round.round_id}>
                      <tr>
                        <td className="mono">#{round.round_id}</td>
                        <td className="mono">
                          {round.first_row}–{round.last_row}
                        </td>
                        <td className="muted">{when(round.appended_at)}</td>
                        <td className="muted">{round.appended_by || "—"}</td>
                        <td>
                          {round.agrees ? (
                            <span className="chip agrees">matches</span>
                          ) : (
                            <span className="chip stops">does not match</span>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="link"
                            onClick={() => onShow(round.round_id)}
                          >
                            See what was written
                          </button>
                        </td>
                      </tr>
                      {round.agrees ? null : (
                        <tr>
                          <td />
                          <td colSpan={5} className="finding">
                            {round.finding || ""}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            {checked ? (
              <p className="muted" style={{ fontSize: "0.9em", margin: "0.75rem 0 0" }}>
                {checked}
              </p>
            ) : null}
          </div>
        </>
      ) : null}
    </>
  );
}

function PreviewDetail({
  preview,
  busy,
  onAppend,
}: {
  preview: Preview;
  busy: boolean;
  onAppend: () => void;
}) {
  const stuck = preview.rows.filter((row) => !row.is_writable);
  const explained = preview.rows.filter((row) => row.why);

  return (
    <>
      <h2>
        Round #{preview.round_id}{" "}
        <span className="muted">
          — {preview.rows.length} row(s)
          {preview.first_row
            ? `, ${preview.appended_at ? "at" : "starting at"} row ${preview.first_row}`
            : ""}
        </span>
      </h2>

      {preview.appended_at ? (
        <div className="notice">
          Appended {when(preview.appended_at)} by {preview.appended_by || "?"}, rows{" "}
          {preview.appended_rows}.
          {preview.saved_as ? (
            <>
              {" "}
              The version before it was saved as <span className="mono">{preview.saved_as}</span>.
            </>
          ) : (
            " The version before it is no longer among the kept copies."
          )}
          <br />
          <span className="muted">
            These rows are worked out from the round&rsquo;s documents again now, and drawn at the
            rows it wrote. <em>Already in the book</em> above says whether the file still holds
            them.
          </span>
        </div>
      ) : preview.is_writable ? (
        <div className="notice">
          Nothing has been written. This is the round cell by cell, as it would go in.
        </div>
      ) : (
        <div className="warning">
          {preview.refusals.map((refusal) => (
            <div key={refusal}>{refusal}</div>
          ))}
        </div>
      )}

      {preview.rows.length ? null : (
        <div className="panel">
          <p style={{ margin: "0 0 0.5rem" }}>
            <strong>This round formed no rows, so there is no grid to draw.</strong>
          </p>
          <p className="muted" style={{ margin: 0 }}>
            A row is one delivery, one product and one account sale together. A round whose
            documents never name an account sale — a consignment report on its own, say, which
            cannot tell one payment run from the next — has nothing to make a row out of. Its
            sales are held as <em>sold, not yet in any payment run</em> until a payment report
            names them. The Resolution queue shows what these documents did carry.
          </p>
        </div>
      )}

      {stuck.length ? (
        <>
          <h3>
            Rows that cannot be written yet{" "}
            <span className="muted">
              ({stuck.length} of {preview.rows.length})
            </span>
          </h3>
          <p className="muted">
            Answered on the Resolution queue. Until every one of them is, the append is refused — a
            book with some of a round in it is worse than one with none.
          </p>
          <div className="panel">
            <div className="scroller">
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Delivery</th>
                    <th>Product</th>
                    <th>What is missing</th>
                  </tr>
                </thead>
                <tbody>
                  {stuck.map((row) => (
                    <tr key={row.row_number}>
                      <td className="mono muted">{row.row_number}</td>
                      <td className="mono">{row.delivery_id}</td>
                      <td>{row.product}</td>
                      <td>
                        {(row.blocked_by ?? []).map((why) => (
                          <div key={why}>{why}</div>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      {explained.length ? (
        <>
          <h3>
            Blanks in full <span className="muted">({explained.length} row(s))</span>
          </h3>
          {explained.map((row) => (
            <div className="panel" key={row.row_number}>
              <strong className="mono">
                row {row.row_number} · {row.delivery_id}
              </strong>{" "}
              <span className="muted">
                {row.product} · {row.account_sale}
              </span>
              <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                {row.why}
              </p>
            </div>
          ))}
        </>
      ) : null}

      {preview.appended_at || !preview.rows.length ? null : (
        <div className="panel">
          <button type="button" onClick={onAppend} disabled={busy || !preview.is_writable}>
            {busy ? "Appending…" : `Append ${preview.rows.length} row(s) to the book`}
          </button>
          <p className="muted" style={{ fontSize: "0.9em", margin: "0.5rem 0 0" }}>
            The book is copied aside first, in the same step. If the write fails, the copy goes
            back and the round stays waiting — there is no half-written state to land in.
          </p>
        </div>
      )}
    </>
  );
}

function Versions({ book }: { book: Book }) {
  const roll = useRollBack();
  const toast = useToast();
  const [asking, setAsking] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  return (
    <>
      <h2>
        Saved versions <span className="muted">({book.versions.length})</span>
      </h2>
      <p className="muted">
        One is taken as a step inside every append, so the book before it is always recoverable.
        Rolling back saves the current version first, which is what makes a rollback itself
        undoable.
      </p>
      <p>
        {/* A plain link, not a fetch: the browser's own download is the one that gets the
            filename and the Content-Disposition right, and this is a file people keep. */}
        <a href="/api/workbook/download">Download the book as it stands</a>
      </p>

      {book.versions.length ? (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Taken</th>
                <th>Why</th>
                <th className="num">Size</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {book.versions.map((version) => (
                <Fragment key={version.name}>
                  <tr>
                    <td className="muted">{when(version.taken_at)}</td>
                    <td>{version.label || "—"}</td>
                    <td className="num muted">{size(version.byte_count)}</td>
                    <td>
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          setReason("");
                          setAsking((current) => (current === version.name ? null : version.name));
                        }}
                      >
                        Roll back to this
                      </button>
                    </td>
                  </tr>
                  {asking === version.name ? (
                    <tr>
                      <td colSpan={4}>
                        <form
                          onSubmit={(event) => {
                            event.preventDefault();
                            if (!reason.trim()) return;
                            roll
                              .mutateAsync({ name: version.name, reason: reason.trim() })
                              .then(() => {
                                setAsking(null);
                                toast.say("The book was put back to that version.");
                              })
                              .catch((error: unknown) => toast.refuse(error));
                          }}
                        >
                          <label htmlFor={`why-${version.name}`}>
                            Why is the book being rolled back? (required)
                          </label>
                          <input
                            id={`why-${version.name}`}
                            type="text"
                            value={reason}
                            placeholder="e.g. round 4 was appended against the wrong producer"
                            onChange={(event) => setReason(event.target.value)}
                          />
                          <button type="submit" disabled={roll.isPending || !reason.trim()}>
                            Put this version back
                          </button>
                        </form>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No versions kept yet. The first append takes one.</p>
      )}
    </>
  );
}

export function Workbook() {
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get("round"));
  const roundId = Number.isInteger(asked) && asked > 0 ? asked : null;

  const book = useBook();
  const preview = usePreview(roundId);
  const append = useAppend();
  const toast = useToast();

  function show(id: number) {
    const merged = new URLSearchParams(params);
    merged.set("round", String(id));
    setParams(merged, { replace: false });
  }

  if (book.isPending) return <Loading what="the book" />;
  if (book.isError)
    return (
      <Page title="The operator's book" width="wide">
        <h1>The operator&rsquo;s book</h1>
        <Problem error={book.error} />
      </Page>
    );

  const found = book.data;

  return (
    <Page title="The operator's book" width="wide">
      <h1>The operator&rsquo;s book</h1>
      <p className="lede">
        Rows are appended beneath what is already there, never rebuilt. Eight columns hold the
        operator&rsquo;s own formulas and a computed value is never written into one. The NOTES
        column is not read, not derived and not written.
      </p>

      {found ? (
        <>
          <State book={found} />
          <Grid book={found} preview={preview.data ?? null} />
          <Rounds book={found} onShow={show} />

          {roundId === null ? null : preview.isPending ? (
            <Loading what="the round" />
          ) : preview.isError ? (
            <Problem error={preview.error} />
          ) : preview.data ? (
            <PreviewDetail
              preview={preview.data}
              busy={append.isPending}
              onAppend={() =>
                append
                  .mutateAsync(preview.data.round_id)
                  .then((written) =>
                    toast.say(`Round #${written.round_id} written, rows ${written.appended_rows}.`),
                  )
                  .catch((error: unknown) => toast.refuse(error))
              }
            />
          ) : null}

          <Versions book={found} />
        </>
      ) : null}
    </Page>
  );
}
