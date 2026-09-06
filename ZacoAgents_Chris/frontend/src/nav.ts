/**
 * The navigation, and what each entry needs to be allowed to show.
 *
 * This was the client's copy of `NAV` in `zaco/web/routes.py`, and is now the only one -- that
 * module went with the rest of the Jinja interface.
 *
 * A menu is not a permission check. The server refuses the request whatever this list says, and a
 * page reached some other way still returns 403. What this list decides is only whether an item
 * is *offered*, which is why it can live on the client at all.
 */

import type { IconName } from "./components/Icon";
import type { Permission } from "./auth/session";

export interface NavItem {
  path: string;
  label: string;
  icon: IconName;
  /** `null` means every signed-in account, which is only the overview. */
  permission: Permission | null;
}

export const NAV: readonly NavItem[] = [
  { path: "/", label: "Overview", icon: "overview", permission: null },
  {
    path: "/rounds",
    label: "Read a document",
    icon: "document",
    permission: "ingest",
  },
  {
    path: "/staged",
    label: "Stage a round",
    icon: "stage",
    permission: "ingest",
  },
  {
    path: "/queue",
    label: "Resolution queue",
    icon: "queue",
    permission: "resolve",
  },
  {
    path: "/workbook",
    label: "Workbook",
    icon: "workbook",
    permission: "append",
  },
  {
    path: "/reconciliation",
    label: "Reconciliation",
    icon: "reconciliation",
    permission: "view_reports",
  },
  {
    path: "/settlement",
    label: "Settlement",
    icon: "settlement",
    permission: "view_reports",
  },
  {
    path: "/reports",
    label: "Reports",
    icon: "reports",
    permission: "view_reports",
  },
  {
    path: "/conduct",
    label: "Agent conduct",
    icon: "conduct",
    permission: "view_reports",
  },
];

/** Accounts sits at the foot beside the person's own name rather than in the nav proper: it is
 *  about who may use this system, not about a round. */
export const ACCOUNTS: NavItem = {
  path: "/admin",
  label: "Accounts",
  icon: "accounts",
  permission: "admin",
};
