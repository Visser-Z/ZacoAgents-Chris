/**
 * One open question, and the three shapes an answer takes.
 *
 * The Jinja page stacks all fourteen cards down the page. That is honest and it is a bad way to
 * spend a Monday: the operator scrolls to find the one they are on, every card's inputs are live
 * at once, and the evidence for the question being answered is competing with thirteen others.
 * Here it is one at a time, with what the question was raised on beside the answer rather than
 * above three screens of other people's questions.
 *
 * The evidence and the tests are not decoration. Section 5 wants a judgement call to carry what
 * it was made on, and the operator is the one making it -- so the checks that passed and the ones
 * that did not are shown, including for the proposal the system is offering.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { QueueItem } from "../api/rounds";

export interface Answer {
  kind: string;
  /** For a product link. */
  accepted?: boolean;
  /** For a short code. */
  short_code?: string;
  /** For a delivery note. */
  dn?: string | null;
  provenance?: string;
  also?: string[];
  reason: string;
}

function Evidence({ item }: { item: QueueItem }) {
  const rows = Object.entries(item.evidence ?? {});
  if (!rows.length) return null;
  return (
    <table className="evidence">
      <tbody>
        {rows.map(([name, value]) => (
          <tr key={name}>
            <th>{name}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Tests({ item }: { item: QueueItem }) {
  const tests = item.tests ?? [];
  if (!tests.length) return null;
  return (
    <div className="tests">
      {tests.map((test) => (
        <div className={test.passed ? "test muted" : "test warning"} key={test.name}>
          {test.passed ? "✓" : "✗"} <strong>{test.name}</strong> — {test.detail}
        </div>
      ))}
    </div>
  );
}

export function Question({
  item,
  index,
  total,
  busy,
  problem,
  onAnswer,
  onMove,
}: {
  item: QueueItem;
  index: number;
  total: number;
  busy: boolean;
  problem: string;
  onAnswer: (answer: Answer) => void;
  onMove: (delta: number) => void;
}) {
  const [code, setCode] = useState("");
  const [dn, setDn] = useState("");
  const [reason, setReason] = useState("");
  const [also, setAlso] = useState<string[]>([]);

  // A fresh question is a fresh answer. Without this the reason typed for the last delivery note
  // is still sitting in the box for the next one, and it would be recorded against it.
  useEffect(() => {
    setCode("");
    setDn(item.proposal ?? "");
    setReason("");
    setAlso([]);
  }, [item.key, item.kind, item.proposal]);

  const listId = useMemo(() => `codes-${index}`, [index]);
  const choices = item.choices ?? [];
  const companions = item.companions ?? [];

  function submit(event: FormEvent, answer: Answer) {
    event.preventDefault();
    onAnswer(answer);
  }

  return (
    <div className="panel question">
      <div className="question-head">
        <span className="tag">{item.kind.replace(/_/g, " ")}</span>
        <strong>{item.title}</strong>
        <span className="muted question-count">
          {index + 1} of {total}
        </span>
      </div>

      <p className="question-ask">{item.question}</p>
      <p className="muted question-why">{item.reasoning}</p>

      {item.counter_evidence ? (
        <div className="warning">
          This reference is provably not a delivery note. {item.counter_evidence}
        </div>
      ) : null}

      <Evidence item={item} />
      <Tests item={item} />

      {problem ? <div className="error">{problem}</div> : null}

      {item.kind === "product_link" ? (
        <form onSubmit={(event) => submit(event, { kind: item.kind, accepted: true, reason })}>
          <label htmlFor={`why-${index}`}>
            Why (optional, but it is what the next person reads)
          </label>
          <input
            id={`why-${index}`}
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. same fruit, the agent's statement uses its own code"
          />
          <div className="row-of-buttons">
            <button type="submit" disabled={busy}>
              Same product
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => onAnswer({ kind: item.kind, accepted: false, reason })}
            >
              Different products
            </button>
          </div>
        </form>
      ) : null}

      {item.kind === "product_code" ? (
        <form
          onSubmit={(event) => submit(event, { kind: item.kind, short_code: code, reason })}
        >
          {choices.length ? (
            <datalist id={listId}>
              {choices.map((choice) => (
                <option value={choice} key={choice} />
              ))}
            </datalist>
          ) : null}
          <label htmlFor={`code-${index}`}>Zaco&rsquo;s short code (workbook column G)</label>
          <input
            id={`code-${index}`}
            type="text"
            value={code}
            list={choices.length ? listId : undefined}
            onChange={(event) => setCode(event.target.value)}
            placeholder="e.g. Imp Cherries 5kg"
            autoFocus
          />
          <button type="submit" disabled={busy || !code.trim()}>
            Record it
          </button>
        </form>
      ) : null}

      {item.kind === "delivery_note" ? (
        <form
          onSubmit={(event) =>
            submit(event, { kind: item.kind, dn, provenance: "operator", also, reason })
          }
        >
          <label htmlFor={`dn-${index}`}>Delivery note number</label>
          <input
            id={`dn-${index}`}
            type="text"
            value={dn}
            onChange={(event) => setDn(event.target.value)}
            placeholder="14xxx"
          />

          {companions.length ? (
            <fieldset>
              <legend>Same agent, same day — one load?</legend>
              <p className="muted" style={{ fontSize: "0.88em", margin: 0 }}>
                Nothing in the documents says these travelled together. Tick any that share this
                delivery note and give the reason; it is recorded against every one of them.
              </p>
              {companions.map((companion) => (
                <label key={companion}>
                  <input
                    type="checkbox"
                    checked={also.includes(companion)}
                    onChange={(event) =>
                      setAlso((current) =>
                        event.target.checked
                          ? [...current, companion]
                          : current.filter((one) => one !== companion),
                      )
                    }
                  />{" "}
                  {companion}
                </label>
              ))}
            </fieldset>
          ) : null}

          <label htmlFor={`why-${index}`}>
            Reason (required to overwrite, or to record no DN)
          </label>
          <input
            id={`why-${index}`}
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. one truck, three consignments"
          />
          <div className="row-of-buttons">
            <button type="submit" disabled={busy}>
              Approve
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() =>
                onAnswer({
                  kind: item.kind,
                  dn: null,
                  provenance: "none_foreign_producer",
                  also: [],
                  reason,
                })
              }
            >
              No DN — carried for another producer
            </button>
          </div>
        </form>
      ) : null}

      <div className="question-move">
        <button type="button" className="link" disabled={index === 0} onClick={() => onMove(-1)}>
          ← Previous
        </button>
        <span className="muted">
          Alt + ← and Alt + → move between questions without leaving the box you are typing in.
        </span>
        <button
          type="button"
          className="link"
          disabled={index >= total - 1}
          onClick={() => onMove(1)}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
