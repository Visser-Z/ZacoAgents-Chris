/**
 * The two ways a page can be refused, kept deliberately different.
 *
 * **Not signed in** is a redirect to the login page, remembering where you were headed so signing
 * in finishes the journey rather than dumping you at the overview.
 *
 * **Signed in without the permission** is not. It renders inside the ordinary shell, navigation
 * and all, and says which permission is missing -- because bouncing somebody to a login page they
 * have already been through tells them their password was wrong, which is a lie. This is what
 * `forbidden.html` does today, and it is worth keeping.
 */

import { Navigate, useLocation } from "react-router";
import type { ReactNode } from "react";

import { DESCRIPTIONS } from "../permissions";
import { Page } from "../components/Page";
import { useSession, type Permission } from "./session";

/** Shown for the moment between asking who is signed in and being told.
 *
 * Deliberately almost nothing. A skeleton of a page that may turn out to be a redirect is a
 * flash of somewhere you were never going. */
function Checking() {
  return <div className="checking" role="status" aria-live="polite" aria-label="Loading" />;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  if (status === "checking") return <Checking />;
  if (status === "signed-out") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

export function NotPermitted({ needed }: { needed: Permission }) {
  return (
    <Page title="Not permitted">
      <h1>Not permitted</h1>
      <div className="warning">
        Your account does not have the <code>{needed}</code> permission
        {DESCRIPTIONS[needed] ? ` (${DESCRIPTIONS[needed].toLowerCase()})` : ""}, so this page is
        not available to you. An administrator can grant it.
      </div>
    </Page>
  );
}

export function RequirePermission({
  needed,
  children,
}: {
  needed: Permission;
  children: ReactNode;
}) {
  const { can } = useSession();
  if (!can(needed)) return <NotPermitted needed={needed} />;
  return <>{children}</>;
}
