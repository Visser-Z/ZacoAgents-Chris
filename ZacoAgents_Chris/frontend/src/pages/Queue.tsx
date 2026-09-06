/**
 * The resolution queue: the facts the reports do not carry.
 *
 * This is the page an operator actually spends time in -- roughly fourteen questions a round --
 * and the two changes that matter are both about that. The round being worked on is in the
 * address bar, so it survives a reload and can be sent to somebody. And the questions come one at
 * a time with their evidence beside them, rather than fourteen cards stacked down a page with
 * every input live at once.
 *
 * Answering does not move you on by itself. A question answered usually disappears -- agreeing
 * that two names are one product removes the code question underneath -- so the list shortens
 * under the same index and the next one is already there. Being moved somewhere you did not ask
 * to go, in a form that records decisions against your name, is worse than one keystroke.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import {
  useAbandonRound,
  useAnswerCode,
  useAnswerDeliveryNote,
  useAnswerLink,
  useCloseQueue,
  useDecideSuspension,
  useReleaseNumber,
  useReopenRound,
  useRestoreDocument,
  useRound,
  useRounds,
  useStartRound,
  useWithdrawDocument,
} from "../api/rounds";
import { DropZone } from "../components/DropZone";
import { Page } from "../components/Page";
import { Loading, Problem } from "../components/values";
import { useToast } from "../components/Toasts";
import { Question, type Answer } from "../queue/Question";
import { RoundDetail } from "../queue/RoundDetail";

function RoundList({
  onOpen,
  onHide,
  openId,
}: {
  onOpen: (id: number) => void;
  onHide: () => void;
  openId: number | null;
}) {
  const rounds = useRounds();

  if (rounds.isPending) return <Loading what="the rounds" />;
  if (rounds.isError) return <Problem error={rounds.error} />;
  if (!rounds.data?.length) return <p className="muted">No rounds saved yet.</p>;

  return (
    <div className="scroller">
      <table>
        <thead>
          <tr>
            <th>Round</th>
            <th>Saved</th>
            <th>By</th>
            <th className="num">Documents</th>
            <th className="num">Open</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rounds.data.map((round) => (
            <tr key={round.id} className={round.id === openId ? "chosen-round" : undefined}>
              <td className="mono">#{round.id}</td>
              <td>{round.created_at.slice(0, 16).replace("T", " ")}</td>
              <td>{round.created_by || "—"}</td>
              <td className="num">
                {round.document_count}
                {round.duplicate_count ? (
                  <span className="tag">{round.duplicate_count} already read</span>
                ) : null}
                {round.withdrawn_count ? (
                  <span className="tag">{round.withdrawn_count} removed</span>
                ) : null}
              </td>
              <td className="num">{round.open_questions || ""}</td>
              <td>{round.status}</td>
              <td>
                {/* The same control both ways round. A row that is already showing offering
                    "Open" is a button that does nothing, and it leaves the only way out of a
                    round being to pick a different one. */}
                {round.id === openId ? (
                  <button type="button" className="link" onClick={onHide}>
                    Hide
                  </button>
                ) : (
                  <button type="button" className="link" onClick={() => onOpen(round.id)}>
                    Open
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Queue() {
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get("round"));
  const openId = Number.isInteger(asked) && asked > 0 ? asked : null;

  const [files, setFiles] = useState<File[]>([]);
  const [at, setAt] = useState(0);
  const [answerProblem, setAnswerProblem] = useState("");
  const toast = useToast();

  const round = useRound(openId);
  const start = useStartRound();

  const id = round.data?.summary.id ?? 0;
  const link = useAnswerLink(id);
  const code = useAnswerCode(id);
  const note = useAnswerDeliveryNote(id);
  const suspension = useDecideSuspension(id);
  const withdraw = useWithdrawDocument(id);
  const restore = useRestoreDocument(id);
  const release = useReleaseNumber(id);
  const reopen = useReopenRound(id);
  const abandon = useAbandonRound(id);
  const close = useCloseQueue(id);

  const queue = round.data?.queue ?? [];
  const total = queue.length;

  // The list shortens as questions are answered, so the index has to be pulled back rather than
  // left pointing past the end -- otherwise answering the last one shows nothing at all.
  useEffect(() => {
    setAt((current) => (total === 0 ? 0 : Math.min(current, total - 1)));
  }, [total]);

  useEffect(() => setAt(0), [openId]);

  // Alt is what makes this safe. A bare arrow key would fight every text box on the page, and
  // this page is almost entirely text boxes.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!event.altKey || total < 2) return;
      if (event.key === "ArrowLeft") setAt((current) => Math.max(0, current - 1));
      if (event.key === "ArrowRight") setAt((current) => Math.min(total - 1, current + 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [total]);

  function open(next: number) {
    const merged = new URLSearchParams(params);
    merged.set("round", String(next));
    setParams(merged, { replace: false });
  }

  /**
   * Stop showing the round. Deliberately not called `close`: `RoundDetail` already has a "Close
   * the queue" button, which is a decision recorded against the round and cannot be undone by
   * looking away. This one only changes what is on the screen.
   *
   * It goes through the address bar like `open` does, so the back button steps out of a round the
   * same way it steps into one.
   */
  function hide() {
    const merged = new URLSearchParams(params);
    merged.delete("round");
    setParams(merged, { replace: false });
  }

  async function startRound() {
    try {
      const created = await start.mutateAsync(files);
      setFiles([]);
      open(created.summary.id);
      toast.say(`Round #${created.summary.id} saved.`);
    } catch (error) {
      toast.refuse(error);
    }
  }

  const item = queue[at];

  async function answer(given: Answer) {
    if (!item) return;
    setAnswerProblem("");
    try {
      if (given.kind === "product_link") {
        const [left = "", right = ""] = item.key.split("||");
        await link.mutateAsync({
          left,
          right,
          accepted: given.accepted ?? false,
          reason: given.reason,
        });
      } else if (given.kind === "product_code") {
        await code.mutateAsync({ product_key: item.key, short_code: given.short_code ?? "" });
      } else {
        await note.mutateAsync({
          delivery_id: item.key,
          also: given.also ?? [],
          dn: given.dn ?? null,
          provenance: given.provenance ?? "operator",
          reason: given.reason,
        });
      }
    } catch (error) {
      // Inline, not a toast. The message is about the box the operator is looking at, and half of
      // these are "a reason is required to overwrite" -- which is an instruction, not an alarm.
      setAnswerProblem(
        error instanceof ApiError ? error.message : "That answer was not recorded.",
      );
    }
  }

  const answering = link.isPending || code.isPending || note.isPending;
  const acting =
    suspension.isPending ||
    withdraw.isPending ||
    restore.isPending ||
    release.isPending ||
    reopen.isPending ||
    abandon.isPending ||
    close.isPending;

  /** Every round-level action reports the same way, so they share one wrapper. */
  const doing =
    <TVariables,>(run: (variables: TVariables) => Promise<unknown>, said: string) =>
    (variables: TVariables) => {
      run(variables)
        .then(() => toast.say(said))
        .catch((error: unknown) => toast.refuse(error));
    };

  return (
    <Page title="Resolution queue" width="wide">
      <h1>Resolution queue</h1>
      <p className="lede">
        The facts the reports do not carry. Every card shows what it was raised on and what the
        system would propose; nothing is applied until you say so, and no round reaches the
        workbook while anything here is unanswered.
      </p>

      <div className="panel">
        <DropZone
          id="files"
          label="Start a round"
          hint="Saved and kept. A file already read in an earlier round is stored again but counts nothing."
          multiple
          files={files}
          onFiles={setFiles}
          disabled={start.isPending}
        />
        <button
          type="button"
          onClick={() => void startRound()}
          disabled={start.isPending || !files.length}
        >
          {start.isPending ? "Saving…" : "Save the round"}
        </button>
        <div style={{ marginTop: "1rem" }}>
          <RoundList onOpen={open} onHide={hide} openId={openId} />
        </div>
      </div>

      {openId === null ? null : round.isPending ? (
        <Loading what="the round" />
      ) : round.isError ? (
        <Problem error={round.error} />
      ) : round.data ? (
        <>
          <h2 className="round-heading">
            <span>
              Round #{round.data.summary.id}{" "}
              <span className="muted">({round.data.summary.status})</span>
            </span>
            {/* Beside the heading as well as in the list, because by the time somebody wants to
                put this away they have scrolled past the list to read it. */}
            <button type="button" className="link" onClick={hide}>
              Hide this round
            </button>
          </h2>
          <div className={round.data.is_clear ? "notice" : "warning"}>
            {round.data.is_clear
              ? `Nothing is outstanding. ${round.data.totals.rows} row(s) are ready for the workbook.`
              : round.data.blocking_reason}
          </div>

          {total ? (
            <>
              <h2>
                Open questions <span className="muted">({total})</span>
              </h2>
              <p className="muted">
                Links first: agreeing that two names are one product can answer a code question
                below it.
              </p>
              {item ? (
                <Question
                  key={`${item.kind}:${item.key}`}
                  item={item}
                  index={at}
                  total={total}
                  busy={answering}
                  problem={answerProblem}
                  onAnswer={(given) => void answer(given)}
                  onMove={(delta) =>
                    setAt((current) => Math.min(total - 1, Math.max(0, current + delta)))
                  }
                />
              ) : null}
            </>
          ) : null}

          <RoundDetail
            round={round.data}
            busy={acting}
            onDecideSuspension={(suspensionId, chosen_source, reason) =>
              doing(
                suspension.mutateAsync,
                "Decision recorded.",
              )({ suspension_id: suspensionId, chosen_source, reason })
            }
            onWithdraw={(document_id, reason) =>
              doing(withdraw.mutateAsync, "Document taken out of the round.")({
                document_id,
                reason,
              })
            }
            onRestore={(document_id) =>
              doing(restore.mutateAsync, "Document put back.")(document_id)
            }
            onRelease={(delivery_id, reason) =>
              doing(release.mutateAsync, "Number released back to the series.")({
                delivery_id,
                reason,
              })
            }
            onReopen={doing(reopen.mutateAsync, "Round reopened.")}
            onAbandon={doing(abandon.mutateAsync, "Round put aside.")}
            onClose={() => doing(close.mutateAsync, "Queue closed.")(undefined)}
          />
        </>
      ) : null}
    </Page>
  );
}
