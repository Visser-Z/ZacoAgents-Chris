/**
 * One document, read and reported on. Nothing is stored.
 *
 * The refusal is as much the point as the reading. Section 4 asks for an explanation rather than
 * a failure, so when no reader recognises a file the page shows what each of the five made of it,
 * sorted by confidence -- which is usually enough to see that a Payment Details export was saved
 * over a Daily Sales Detail, or that the file is a spreadsheet somebody renamed.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError, api, type Refusal, type Schemas } from "../api/client";
import { DropZone } from "../components/DropZone";
import { Page } from "../components/Page";
import { Problems } from "../components/Problems";

type Inspection = Schemas["InspectionOut"];

function Scores({ scores, filename }: { scores: Record<string, number>; filename: string }) {
  const ranked = Object.entries(scores).sort((left, right) => right[1] - left[1]);
  return (
    <>
      <p className="muted">
        What each reader made of <span className="mono">{filename}</span>:
      </p>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Reader</th>
              <th className="num">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {ranked.length ? (
              ranked.map(([kind, value]) => (
                <tr key={kind}>
                  <td className="mono">{kind}</td>
                  <td className="num">{(value * 100).toFixed(0)}%</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={2}>Nothing recognised it.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Read({ found }: { found: Inspection }) {
  const counts = Object.entries(found.counts)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${count} ${name}`)
    .join(", ");

  // A narrowed or unstated scope is a warning rather than a note. What the export leaves out is
  // invisible by definition, and the mistake it invites -- reading a one-market file as the whole
  // business -- is the one that would put a wrong figure in front of somebody.
  const narrowed = found.scope.is_narrowed;
  const unstated = found.scope.is_unstated;

  return (
    <>
      <h2>Read as {found.kind_title}</h2>
      <div className="notice">
        <strong>{found.filename}</strong> was identified by its content as a {found.kind_title}{" "}
        (confidence {(found.confidence * 100).toFixed(0)}%), and yielded {counts || "nothing"}.
      </div>
      <div className={narrowed || unstated ? "warning" : "notice"}>
        <strong>Scope:</strong> {found.scope.description}.
        {narrowed
          ? " Anything outside that is absent from this file, not absent from the business."
          : unstated
            ? " It cannot be assumed complete."
            : ""}
      </div>

      <Problems problems={found.problems} withLines />

      <h2>What was read</h2>
      <div className="panel">
        <div className="scroller">
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th>Detail</th>
                <th>Figures</th>
              </tr>
            </thead>
            <tbody>
              {found.preview.map((record, index) => (
                <tr key={`${record.label}-${index}`}>
                  <td className="mono">{record.label}</td>
                  <td>
                    {record.detail}
                    <div style={{ marginTop: "0.35rem" }}>
                      {(record.flags ?? []).map((flag) => (
                        <span className="tag" key={flag}>
                          {flag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ fontSize: "0.9em" }}>
                    {Object.entries(record.figures ?? {}).map(([name, value]) => (
                      <div key={name}>
                        <span className="muted">{name}:</span> {value}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="muted" style={{ fontSize: "0.9em" }}>
        Nothing has been stored. This reads and reports; staging a round into the durable record is
        the next page.
      </p>
    </>
  );
}

export function ReadDocument() {
  const [files, setFiles] = useState<File[]>([]);
  const [expected, setExpected] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<Inspection | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [problem, setProblem] = useState("");

  // The five kinds come from the server rather than being written out here. They are an enum the
  // classifier reads against, and a list in the client that had drifted from it would offer a
  // kind no reader answers to.
  const kinds = useQuery({
    queryKey: ["ingest-kinds"],
    queryFn: () => api.get<Record<string, string>>("/api/ingest/kinds"),
    staleTime: Infinity,
  });

  async function read() {
    const file = files[0];
    if (!file) return;
    setBusy(true);
    setFound(null);
    setRefusal(null);
    setProblem("");
    try {
      const result = await api.inspect<Inspection>(
        "/api/ingest/inspect",
        file,
        expected ? { expected } : {},
      );
      setFound(result);
    } catch (error) {
      if (error instanceof ApiError && error.refusal) {
        setRefusal(error.refusal);
      } else {
        setProblem(error instanceof Error ? error.message : "The file could not be read.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Read a document">
      <h1>Read a document</h1>
      <p className="lede">
        Drop in one agent report. The system works out what it is by reading it, never by its
        filename, and shows you everything it could and could not make sense of.
      </p>

      <div className="panel">
        <DropZone
          id="file"
          label="The file"
          multiple={false}
          files={files}
          onFiles={setFiles}
          disabled={busy}
        />

        <label htmlFor="expected">What you believe it is (optional)</label>
        <select
          id="expected"
          value={expected}
          onChange={(event) => setExpected(event.target.value)}
        >
          <option value="">Let the system work it out</option>
          {Object.entries(kinds.data ?? {}).map(([value, title]) => (
            <option key={value} value={value}>
              {title}
            </option>
          ))}
        </select>
        <p className="muted" style={{ fontSize: "0.88em", margin: "0.4rem 0 0" }}>
          If you name a kind and the file turns out to be something else, it is refused rather than
          read either way. The file is not what you think it is, and that is worth stopping for.
        </p>

        <button type="button" onClick={() => void read()} disabled={busy || !files.length}>
          {busy ? "Reading…" : "Read it"}
        </button>
      </div>

      {problem ? <div className="error">{problem}</div> : null}

      {refusal ? (
        <>
          <h2>Refused</h2>
          {/* The server's message already ends with "Nothing was taken from it", so this does
              not say it again. */}
          <div className="error">{refusal.detail}</div>
          <Scores scores={refusal.scores} filename={refusal.filename} />
        </>
      ) : null}

      {found ? <Read found={found} /> : null}
    </Page>
  );
}
