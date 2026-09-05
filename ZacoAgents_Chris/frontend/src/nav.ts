/**
 * The navigation, and what each entry needs to be allowed to show.
 *
 * This is the client's copy of `NAV` in `zaco/web/routes.py`. It is a copy because a menu is not
 * a permission check: the server refuses the request whatever this list says, and a page reached
 * some other way still returns 403. What this list decides is only whether an item is *offered*.
 *
 * The `phase` slot the Jinja list carried is dropped -- every one of its entries was `None`, so
 * it had stopped saying anything.
 */

import type { IconName } from "./components/Icon";
import type { Permission } from "./auth/session";

export interface NavItem {
  path: string;
  label: string;
  icon: IconName;
  /** `null` means every signed-in account, which is only the overview. */
  permission: Permission | null;
  /** The page on the current interface, while both exist. Removed when the Jinja pages go. */
  existing: string;
}

export const NAV: readonly NavItem[] = [
  { path: "/", label: "Overview", icon: "overview", permission: null, existing: "/" },
  {
    path: "/rounds",
    label: "Read a document",
    icon: "document",
    permission: "ingest",
    existing: "/rounds",
  },
  {
    path: "/staged",
    label: "Stage a round",
    icon: "stage",
    permission: "ingest",
    existing: "/staged",
  },
  {
    path: "/queue",
    label: "Resolution queue",
    icon: "queue",
    permission: "resolve",
    existing: "/queue",
  },
  {
    path: "/workbook",
    label: "Workbook",
    icon: "workbook",
    permission: "append",
    existing: "/workbook",
  },
  {
    path: "/reconciliation",
    label: "Reconciliation",
    icon: "reconciliation",
    permission: "view_reports",
    existing: "/reconciliation",
  },
  {
    path: "/settlement",
    label: "Settlement",
    icon: "settlement",
    permission: "view_reports",
    existing: "/settlement",
  },
  {
    path: "/reports",
    label: "Reports",
    icon: "reports",
    permission: "view_reports",
    existing: "/reports",
  },
  {
    path: "/conduct",
    label: "Agent conduct",
    icon: "conduct",
    permission: "view_reports",
    existing: "/conduct",
  },
];

/** Accounts sits with the person's own name rather than in the nav proper, which is where the
 *  current interface puts it: it is about who you are, not about a round. */
export const ACCOUNTS: NavItem = {
  path: "/admin",
  label: "Accounts",
  icon: "accounts",
  permission: "admin",
  existing: "/admin",
};
