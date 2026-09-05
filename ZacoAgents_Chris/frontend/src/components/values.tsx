/**
 * Absent, and the two different things it means.
 *
 * Most of this system's `null`s mean "no document said". Section 6 is emphatic that this is not
 * nought: a consignment whose source cannot express a return has not told us there were none.
 * Rendering both as `0` would be the system saying something no document does.
 *
 * So there are two renderings. A dash for a figure that is merely missing, and a chip reading
 * "not reported" where the absence is itself the finding and a reader should not skim past it.
 * The Jinja pages made the same distinction by hand in eight places; here it is made once.
 */

import type { ReactNode } from "react";

/** A figure that is not there. */
export function dash(value: string | number | null | undefined): ReactNode {
  return value === null || value === undefined || value === "" ? "—" : value;
}

/** An absence worth stopping on: no source could express this at all. */
export function NotReported() {
  return <span className="chip">not reported</span>;
}

/** Either the figure, or the chip that says why there is not one. */
export function Reported({ value }: { value: string | number | null | undefined }): ReactNode {
  return value === null || value === undefined ? <NotReported /> : value;
}

/** A page's quiet wait. Not a skeleton: these reads re-derive the whole record and can take a
 *  moment, and a shape pretending to be the answer is worse than a line saying it is coming. */
export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" role="status" aria-live="polite">
      Working out {what} from the documents…
    </p>
  );
}

/** Anything the API refused that a permission guard has not already handled. */
export function Problem({ error }: { error: unknown }) {
  return (
    <div className="error">{error instanceof Error ? error.message : "Something went wrong."}</div>
  );
}
