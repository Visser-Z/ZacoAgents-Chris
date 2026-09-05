/**
 * A page that has its route, its permission check and its place in the navigation, but not yet
 * its contents.
 *
 * This is temporary scaffolding for one reason: the guards are the substance of this step, and a
 * guard with nothing behind it is not a guard that has been shown to work. Each of these carries
 * a link to the same page on the interface that does have contents, so a nav item is never a dead
 * end while both exist. They are replaced one at a time, and the last one to go takes this file
 * with it.
 */

import { Page } from "../components/Page";
import type { NavItem } from "../nav";

export function NotYetBuilt({ item }: { item: NavItem }) {
  return (
    <Page title={item.label}>
      <h1>{item.label}</h1>
      <div className="notice">
        This page has not been rebuilt here yet. It works, in full, on the current interface:{" "}
        <a href={item.existing}>{item.existing}</a>. Both interfaces read the same API and the same
        record, so nothing differs between them but the drawing.
      </div>
    </Page>
  );
}
