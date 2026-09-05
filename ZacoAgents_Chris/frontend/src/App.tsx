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
import { Accept } from "./pages/Accept";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { NotYetBuilt } from "./pages/NotYetBuilt";
import { Overview } from "./pages/Overview";

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
const Reports = lazy(() => import("./pages/Reports").then((m) => ({ default: m.Reports })));
const Settlement = lazy(() =>
  import("./pages/Settlement").then((m) => ({ default: m.Settlement })),
);

import "./styles/shell.css";
import "./styles/charts.css";

/** Vite writes `/app/`; the router wants it without the trailing slash. */
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

/** The sections that have been rebuilt here. Everything else still points at its twin. */
const BUILT: Record<string, ReactElement> = {
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
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/accept/:token" element={<Accept />} />

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
              <Route
                path={ACCOUNTS.path}
                element={
                  <RequirePermission needed="admin">
                    <NotYetBuilt item={ACCOUNTS} />
                  </RequirePermission>
                }
              />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
