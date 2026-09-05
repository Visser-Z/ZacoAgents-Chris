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
 * kind of drift that appears when the two lists are maintained separately.
 */

import { BrowserRouter, Outlet, Route, Routes } from "react-router";

import { ACCOUNTS, NAV } from "./nav";
import { AppShell } from "./components/AppShell";
import { RequireAuth, RequirePermission } from "./auth/guards";
import { SessionProvider } from "./auth/session";
import { Accept } from "./pages/Accept";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { NotYetBuilt } from "./pages/NotYetBuilt";
import { Overview } from "./pages/Overview";

import "./styles/shell.css";

/** Vite writes `/app/`; the router wants it without the trailing slash. */
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

const SECTIONS = NAV.filter((item) => item.path !== "/");

function Shell() {
  return (
    <RequireAuth>
      <AppShell>
        <Outlet />
      </AppShell>
    </RequireAuth>
  );
}

export function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/accept/:token" element={<Accept />} />

          <Route element={<Shell />}>
            <Route index element={<Overview />} />
            {SECTIONS.map((item) => (
              <Route
                key={item.path}
                path={item.path}
                element={
                  item.permission ? (
                    <RequirePermission needed={item.permission}>
                      <NotYetBuilt item={item} />
                    </RequirePermission>
                  ) : (
                    <NotYetBuilt item={item} />
                  )
                }
              />
            ))}
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
  );
}
