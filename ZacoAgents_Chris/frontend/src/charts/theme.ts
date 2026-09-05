/**
 * The colours and the defaults every chart here uses.
 *
 * The project's own palette is kept for chrome -- the sidebar, buttons, chips, panel edges -- and
 * is deliberately **not** used for data marks. Checked rather than assumed: the accent #17564a
 * has a chroma of 0.066, which reads as gray when it is a bar rather than a border, and the warn
 * edge #e0b56a sits at 1.91:1 against white. Both fail as marks and neither is wrong as chrome.
 *
 * What is here passed the validator against #ffffff, and these exact strings were what was run:
 *
 *   #2a78d6 with #eb6834   -- all checks pass  (the two directions of a difference)
 *   #2a78d6 with #c77d18   -- all checks pass  (ordinary against flagged, section 10)
 *
 * `FLAGGED` is amber and never red. `app.css` says it outright -- "a red row is an accusation" --
 * and section 10 is explicit that nothing in it is one.
 */

/** One measure, one colour. Most charts here are a single series and need nothing more. */
export const MARK = "#2a78d6";

/** Section 10's emphasis form: the one that is unlike the others, against everything else held
 *  back. The gray is a deliberate near-zero chroma -- it is the absence of a claim. */
export const FLAGGED = "#c77d18";
export const QUIET = "#8d9497";

/** The other direction of a signed figure, where one exists. */
export const AGAINST = "#eb6834";

/** Chrome inside the plot: grid, axes, reference lines. Recessive on purpose -- the marks are
 *  what is being read, and a grid dark enough to notice is a grid competing with them. */
export const GRID = "#e6e9ea";
export const AXIS = "#5d6467";
export const RULE = "#9aa1a4";

export const AXIS_TICK = { fill: AXIS, fontSize: 11 } as const;

/** Charts are drawn from `plot()` numbers, which exist only to be drawn. The figure anybody is
 *  owed is the string beside it in the same response, and it is the table that carries that. So
 *  these formatters are for axes and tooltips, and nothing is settled against them. */
export function rand(value: number): string {
  return `R${Math.round(value).toLocaleString("en-ZA")}`;
}

export function percent(value: number, places = 1): string {
  return `${(value * 100).toFixed(places)}%`;
}

/** Long product names do not fit an axis. Cut on a word so what is left is still a name. */
export function shorten(label: string, limit = 24): string {
  if (label.length <= limit) return label;
  const cut = label.slice(0, limit);
  const space = cut.lastIndexOf(" ");
  return `${(space > limit * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}
