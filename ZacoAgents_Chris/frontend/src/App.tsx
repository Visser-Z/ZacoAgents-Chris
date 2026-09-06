/**
 * The routes.
 *
 * Mounted under `/app` while the Jinja interface still owns `/`, `/login`, `/queue` and the rest;
 * the two would collide otherwise. The prefix comes from Vite's `base` rather than being written
 * out, so the last step of the port -- moving this app to `/` -- is a change to one build setting
 * and not a search through the source for a string.
 *
 * The eight sections are generated from the same `NAV` the sidebar is drawn from. That is on
 * purpose: a route the navigation does not offer, or an item that leads nowhere, is exactly the
 * kind of drift that appears when the two lists are maintained separately. A path with no entry
 * in `BUILT` gets the placeholder, so adding a page is one line here and nothing anywhere else.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Outlet, Route, Routes } from "react-router";
import { Suspense, lazy, type ReactElement } from "react";

import { ACCOUNTS, NAV } from "./nav";
import { AppShell } from "./components/AppShell";
import { RequireAuth, RequirePermission } from "./auth/guards";
import { SessionProvider } from "./auth/session";
import { ToastHost } from "./components/Toasts";
import { Accept } from "./pages/Accept";
import { Accounts } from "./pages/Accounts";
import { Forgot } from "./pages/Forgot";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { NotYetBuilt } from "./pages/NotYetBuilt";
import { Overview } from "./pages/Overview";
import { ReadDocument } from "./pages/ReadDocument";
import { Reset } from "./pages/Reset";
import { StageRound } from "./pages/StageRound";
import { YourAccount } from "./pages/YourAccount";

/**
 * The four pages that draw charts are fetched when one is opened, not before.
 *
 * Recharts is 500kB of the bundle on its own. Shipping it in the first response means the login
 * page -- which draws nothing -- carries a charting library, on whatever connection the person
 * signing in happens to have. Split out, the shell and the login are a fifth of the size and the
 * charts arrive with the page that needs them.
 */
const Conduct = lazy(() => import("./pages/Conduct").then((m) => ({ default: m.Conduct })));
const Reconciliation = lazy(() =>
  import("./pages/Reconciliation").then((m) => ({ default: m.Reconciliation })),
);
const Queue = lazy(() => import("./pages/Queue").then((m) => ({ default: m.Queue })));
const Reports = lazy(() => import("./pages/Reports").then((m) => ({ default: m.Reports })));
const Workbook = lazy(() => import("./pages/Workbook").then((m) => ({ default: m.Workbook })));
const Settlement = lazy(() =>
  import("./pages/Settlement").then((m) => ({ default: m.Settlement })),
);

import "./styles/shell.css";
import "./styles/charts.css";

/** Vite writes `/app/`; the router wants it without the trailing slash. */
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

/** The sections that have been rebuilt here. Everything else still points at its twin. */
const BUILT: Record<string, ReactElement> = {
  "/rounds": <ReadDocument />,
  "/queue": <Queue />,
  "/workbook": <Workbook />,
  "/staged": <StageRound />,
  "/reconciliation": <Reconciliation />,
  "/settlement": <Settlement />,
  "/reports": <Reports />,
  "/conduct": <Conduct />,
};

/**
 * One client for the whole app.
 *
 * `retry: false` because these endpoints re-derive the record from every document on every call.
 * Retrying a read that failed is asking a slow question again for no new reason, and a refusal --
 * no session, no permission -- gives the same answer three times. `refetchOnWindowFocus` is off
 * for the same reason: coming back to a tab should not silently re-parse the history.
 */
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
});

const SECTIONS = NAV.filter((item) => item.path !== "/");

function Shell() {
  return (
    <RequireAuth>
      <AppShell>
        {/* The fallback is deliberately quiet. A page arriving over the wire is not a page that
            failed, and a skeleton of the wrong shape is worse than nothing for the half-second
            it takes. */}
        <Suspense fallback={<div className="checking" />}>
          <Outlet />
        </Suspense>
      </AppShell>
    </RequireAuth>
  );
}

export function App() {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter basename={BASENAME}>
        <SessionProvider>
          <ToastHost>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/accept/:token" element={<Accept />} />
              {/* The two pages a person reaches when they cannot sign in. Outside the shell for
                  the same reason as the login: guarding them would demand the session they are
                  here to get back. `RESET_PATH` in `zaco/auth/service.py` is the other half of
                  this address -- it is what the recovery command prints. */}
              <Route path="/forgot" element={<Forgot />} />
              <Route path="/reset/:token" element={<Reset />} />

              <Route element={<Shell />}>
                <Route index element={<Overview />} />
                {SECTIONS.map((item) => {
                  const page = BUILT[item.path] ?? <NotYetBuilt item={item} />;
                  return (
                    <Route
                      key={item.path}
                      path={item.path}
                      element={
                        item.permission ? (
                          <RequirePermission needed={item.permission}>{page}</RequirePermission>
                        ) : (
                          page
                        )
                      }
                    />
                  );
                })}
                {/* Your own account needs no permission: it is the one page that is about you
                    rather than about a round, and everybody has one. */}
                <Route path="/account" element={<YourAccount />} />
                <Route
                  path={ACCOUNTS.path}
                  element={
                    <RequirePermission needed="admin">
                      <Accounts />
                    </RequirePermission>
                  }
                />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </ToastHost>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
