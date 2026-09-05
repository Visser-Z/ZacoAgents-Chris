/**
 * One page's `<main>`, at one of the three widths the interface uses.
 *
 * The widths are carried over unchanged from `app.css`: 62rem by default, 26rem for the two
 * pages that are a single form, and unbounded for the five that are a table wider than prose.
 * The title is set here rather than in each page so that a browser tab and a back-button history
 * entry say which page they are, which the current interface only manages because Jinja does it.
 */

import { useEffect, type ReactNode } from "react";

export type Width = "default" | "narrow" | "wide";

export function Page({
  title,
  width = "default",
  children,
}: {
  title: string;
  width?: Width;
  children: ReactNode;
}) {
  useEffect(() => {
    // The overview is already called "Zaco account sales"; suffixing it says the word twice.
    document.title = title.startsWith("Zaco") ? title : `${title} — Zaco`;
  }, [title]);

  return <main className={width === "default" ? undefined : width}>{children}</main>;
}
