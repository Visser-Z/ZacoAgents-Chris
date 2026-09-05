/** Whether a CSS media query currently matches, kept in sync as the window changes.
 *
 * The sidebar is two different things either side of one breakpoint -- a rail that collapses on
 * wide screens, a drawer that slides over the page on narrow ones -- and which one it is has to be
 * known in JavaScript, not only in CSS: the drawer needs a scrim, an Escape key and focus, and
 * none of those are stylesheet concerns. The breakpoint is stated once, in `shell.css`, and
 * repeated here as the same number; they are checked against each other by eye and nothing else.
 */

import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);

  return matches;
}
