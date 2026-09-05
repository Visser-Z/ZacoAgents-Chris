/**
 * What a document said that the reader could not simply take at face value.
 *
 * Grouped by severity and kept in that order, because the three are different questions. An error
 * is something the reader could not do. A warning is something it did that a person should check.
 * A note is something worth knowing about the document itself. Flattening them into one list
 * makes the second and third look like the first, and a page of red on a document that read
 * perfectly well teaches an operator to stop reading them.
 */

import type { Schemas } from "../api/client";

type Problem = Schemas["ProblemOut"];

const LEVELS: { severity: string; title: string; className: string }[] = [
  { severity: "error", title: "Errors", className: "error" },
  { severity: "warning", title: "Warnings", className: "warning" },
  { severity: "note", title: "Notes", className: "notice" },
];

export function Problems({ problems, withLines = false }: { problems: Problem[]; withLines?: boolean }) {
  return (
    <>
      {LEVELS.map(({ severity, title, className }) => {
        const items = problems.filter((problem) =>
          severity === "note"
            ? problem.severity !== "error" && problem.severity !== "warning"
            : problem.severity === severity,
        );
        if (!items.length) return null;
        return (
          <section key={severity}>
            <h2>
              {title} <span className="muted">({items.length})</span>
            </h2>
            {items.map((problem, index) => (
              <div className={className} key={`${problem.message}-${index}`}>
                {problem.message}
                {withLines && problem.line_number ? (
                  <div className="muted" style={{ marginTop: "0.3rem" }}>
                    line {problem.line_number}
                    {problem.line ? (
                      <>
                        : <span className="mono">{problem.line}</span>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ))}
          </section>
        );
      })}
    </>
  );
}
