/**
 * The book, and the round landing beneath it, in one grid.
 *
 * One grid rather than two, because the question the screen has to answer is "where does this go
 * in the file I know". The book is drawn first and always; a round being looked at is drawn into
 * the same columns below a line, dashed so it can never pass for a row that has been written.
 *
 * ## What is load-bearing here
 *
 * **Column order comes from the spreadsheet letter, never from array position.** The brief prints
 * 21 columns A to U; the real book has 23, so `Baby Stock` is at L and not K, and the operator's
 * own columns sit *between* the ones this system writes. Sorted length-first so Z comes before
 * AA -- a plain string sort puts AA between A and B.
 *
 * **Alignment is decided per column, not per cell.** A column is right-aligned because it holds
 * figures, taken from the list the server sends, so the same column is aligned the same way above
 * and below the line. Deciding from the value would align one row's DN and not the next one's,
 * which reads worse than aligning nothing.
 *
 * The styling is the existing `app.css` grid, used rather than copied: `border-collapse:
 * separate` for the sticky cells, a three-level z-index stack for the header, the gutter and the
 * corner, and a per-`<tr>` cascade of cell colours so banding, hover and the blocked tint reach
 * the formula and never-written cells instead of stopping at the plain ones.
 */

import type { Book, BookRow, Preview, PreviewRow } from "../api/workbook";

export interface Column {
  kind: "ours" | "theirs";
  /** The letter the column actually resolved to in the operator's file. */
  letter: string;
  header: string;
  /** The field name this system knows it by, where it knows it at all. */
  name?: string;
}

/** 1 -> A, 26 -> Z, 27 -> AA. The book's own columns are known only by their index. */
export function letterOf(index: number): string {
  let out = "";
  let left = index;
  while (left > 0) {
    out = String.fromCharCode(64 + (((left - 1) % 26) + 1)) + out;
    left = Math.floor((left - 1) / 26);
  }
  return out;
}

export function columnsOf(book: Book): Column[] {
  const all: Column[] = book.order.map((name) => ({
    kind: "ours",
    name,
    letter: book.letters[name] ?? "",
    header: book.headers[name] ?? name,
  }));
  for (const [header, index] of Object.entries(book.unknown_headers)) {
    all.push({ kind: "theirs", letter: letterOf(index), header });
  }
  // Length first: sorted as plain strings, AA lands between A and B.
  all.sort((left, right) => left.letter.length - right.letter.length || left.letter.localeCompare(right.letter));
  return all;
}

/** Columns the append never touches: the ones this system does not know, plus the ones it knows
 *  and deliberately leaves alone -- NOTES among them. In the book they hold the operator's own
 *  writing, so they are tinted rather than hatched: the content is the point. */
export function ownedLetters(book: Book): Set<string> {
  const owned = new Set(Object.values(book.unknown_headers).map(letterOf));
  for (const name of book.never_written) {
    const letter = book.letters[name];
    if (letter) owned.add(letter);
  }
  return owned;
}

export function numericLetters(book: Book): Set<string> {
  return new Set(
    book.numeric_columns.map((name) => book.letters[name]).filter((letter): letter is string => !!letter),
  );
}

function HeaderRow({ columns, numeric }: { columns: Column[]; numeric: Set<string> }) {
  return (
    <thead>
      <tr>
        <th className="rownum">#</th>
        {columns.map((column) => (
          <th key={column.letter} className={numeric.has(column.letter) ? "num" : undefined}>
            <span className="letter">{column.letter}</span>
            <span className="header">{column.header}</span>
          </th>
        ))}
      </tr>
    </thead>
  );
}

/**
 * A cell of the book.
 *
 * Excel stores a formula and the result it last cached; openpyxl does not calculate, so a row
 * nobody has opened in Excel has the formula and no cached result. Showing the formula is truer
 * than showing an empty cell.
 */
function BookCell({
  row,
  column,
  owned,
  numeric,
}: {
  row: BookRow;
  column: Column;
  owned: Set<string>;
  numeric: Set<string>;
}) {
  const classes: string[] = [];
  if (numeric.has(column.letter)) classes.push("num");
  if ((row.formulas ?? {})[column.letter]) classes.push("formula");
  if (owned.has(column.letter)) classes.push("owned");
  return <td className={classes.join(" ") || undefined}>{(row.cells ?? {})[column.letter] ?? ""}</td>;
}

/**
 * A cell of the round about to land.
 *
 * A blank that was a decision says so where the value would have been. A blank nobody explained
 * is indistinguishable from one nobody got to, which is the whole reason the reason is carried.
 */
function LandingCell({
  preview,
  row,
  name,
}: {
  preview: Preview;
  row: PreviewRow;
  name: string;
}) {
  const classes: string[] = [];
  if (preview.numeric_columns.includes(name)) classes.push("num");
  if (preview.formula_columns.includes(name)) classes.push("formula");
  if (preview.never_written.includes(name)) classes.push("theirs");

  const value = (row.cells ?? {})[name] ?? "";
  const blank = (row.blanks ?? {})[name];
  const stops = (row.blocked_by ?? []).length > 0 && ["dn", "description", "date"].includes(name);

  return (
    <td className={classes.join(" ") || undefined}>
      {value ? value : blank ? <span className={stops ? "chip stops" : "chip"}>{blank}</span> : ""}
    </td>
  );
}

function Legend({ landing }: { landing: boolean }) {
  return (
    <div className="legend">
      <span>
        <span className="swatch written" /> plain — a value in the cell
      </span>
      <span>
        <span className="swatch formula" /> blue monospace — a formula; Excel computes it when the
        file is opened
      </span>
      <span>
        <span className="swatch owned" /> the operator&rsquo;s own column — read back and written
        back unchanged
      </span>
      {landing ? (
        <>
          <span>
            <span className="swatch landing" /> not in the file yet — where this round would go
          </span>
          <span>
            <span className="swatch blocked" /> amber edge — a row the append will not write yet
          </span>
          <span>
            <span className="chip">reason</span> a blank that was decided, not missed
          </span>
          <span>
            <span className="chip stops">reason</span> a blank that stops the append
          </span>
        </>
      ) : null}
    </div>
  );
}

export function Grid({ book, preview }: { book: Book; preview: Preview | null }) {
  if (!book.is_readable) return null;

  const columns = columnsOf(book);
  const owned = ownedLetters(book);
  const numeric = numericLetters(book);

  // A round that has not been appended is drawn beneath the line. One that has is drawn *in* the
  // book, at the rows it wrote, so the two claims can be compared rather than described.
  const landing = preview && !preview.appended_at && preview.rows.length ? preview : null;
  const already =
    preview && preview.appended_at
      ? new Set(preview.rows.map((row) => Number(row.row_number)))
      : new Set<number>();

  return (
    <>
      <h2>
        {book.filename}{" "}
        <span className="muted">
          — {book.sheet_name}, {book.row_count} row(s)
        </span>
      </h2>
      <div className="grid-wrap">
        <table className="grid">
          <HeaderRow columns={columns} numeric={numeric} />
          <tbody>
            {book.rows.map((row) => (
              <tr key={row.row_number} className={already.has(row.row_number) ? "highlit" : undefined}>
                <td className="rownum">{row.row_number}</td>
                {columns.map((column) => (
                  <BookCell
                    key={column.letter}
                    row={row}
                    column={column}
                    owned={owned}
                    numeric={numeric}
                  />
                ))}
              </tr>
            ))}

            {landing ? (
              <>
                <tr className="landing-note">
                  <td className="rownum" />
                  <td colSpan={columns.length}>
                    Round #{landing.round_id} would be written here — {landing.rows.length} row(s)
                    from row {landing.first_row}. Nothing below this line is in the file.
                  </td>
                </tr>
                {landing.rows.map((row) => (
                  <tr
                    key={row.row_number}
                    className={`landing${row.is_writable ? "" : " blocked"}`}
                  >
                    <td className="rownum">{row.row_number}</td>
                    {columns.map((column) =>
                      column.kind === "theirs" || !column.name ? (
                        <td className="theirs" key={column.letter} />
                      ) : (
                        <LandingCell
                          key={column.letter}
                          preview={landing}
                          row={row}
                          name={column.name}
                        />
                      ),
                    )}
                  </tr>
                ))}
              </>
            ) : null}
          </tbody>
        </table>
      </div>
      <Legend landing={landing !== null} />
      {book.rows_from > (book.header_row ?? 0) + 1 ? (
        <p className="muted" style={{ margin: "0.4rem 0 0" }}>
          Showing the last {book.rows.length} of {book.row_count} rows, from row {book.rows_from}.
          An append lands at the bottom.
        </p>
      ) : null}
    </>
  );
}
