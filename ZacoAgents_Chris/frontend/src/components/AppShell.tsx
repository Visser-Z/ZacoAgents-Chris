/**
 * The frame every signed-in page sits in: a left sidebar and the page beside it.
 *
 * `base.html` put the brand in a top bar and the navigation in a row under it, and marked neither
 * -- every item looked identical on every page, so the interface never said where you were. The
 * sidebar exists to fix that as much as to look modern: one column, the current page marked, and
 * `aria-current="page"` so it is marked for a screen reader too and not only by colour.
 *
 * It is two things either side of 48rem. Wide: a column that collapses to an icon rail, and the
 * choice is remembered. Narrow: a drawer over the page with a scrim, closing on Escape, on the
 * scrim, and on going somewhere -- because on a phone the destination is what you wanted, and a
 * drawer still covering it is just in the way.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";

import { ACCOUNTS, NAV, type NavItem } from "../nav";
import { useSession } from "../auth/session";
import { Icon } from "./Icon";
import { remember, remembered } from "./store";
import { useMediaQuery } from "./useMediaQuery";

/** The same number as `shell.css`'s breakpoint. */
const NARROW = "(max-width: 47.999em)";
const COLLAPSED_KEY = "zaco.sidebar.collapsed";

function NavRow({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  return (
    <NavLink
      to={item.path}
      end={item.path === "/"}
      className="side-link"
      // Only when it is a rail: with the label showing, a tooltip repeating it is noise, and it
      // covers the item below while you read it.
      title={collapsed ? item.label : undefined}
    >
      <Icon name={item.icon} />
      <span className="side-label">{item.label}</span>
    </NavLink>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut, can } = useSession();
  const narrow = useMediaQuery(NARROW);
  const location = useLocation();

  const [collapsed, setCollapsed] = useState(() => remembered(COLLAPSED_KEY, false));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    remember(COLLAPSED_KEY, collapsed);
  }, [collapsed]);

  // Going somewhere closes the drawer. Without this the page you asked for is behind the thing
  // you asked it from.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", escape);
    // The page behind a drawer should not scroll under it. Restored on close rather than set to
    // an empty string blindly, so a stylesheet that ever sets `overflow` on `body` survives.
    const wasOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Focus follows the drawer in, so a keyboard reaches the navigation it just opened rather
    // than carrying on through the page behind it. This is not a focus trap -- tabbing past the
    // last item still leaves the drawer -- and the honest version of that is Escape, which works.
    closeDrawer.current?.focus();
    return () => {
      window.removeEventListener("keydown", escape);
      document.body.style.overflow = wasOverflow;
    };
  }, [drawerOpen]);

  // A rail is a wide-screen idea. Below the breakpoint the sidebar is a drawer and always shows
  // its labels, so the remembered choice is kept but not applied.
  const railed = collapsed && !narrow;
  const items = NAV.filter((item) => item.permission === null || can(item.permission));

  return (
    <div className={`shell${railed ? " railed" : ""}`}>
      <header className="shell-topbar">
        <button
          type="button"
          className="icon-button"
          aria-label="Open the navigation"
          aria-controls="sections"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          <Icon name="menu" />
        </button>
        <Link to="/" className="brand">
          Zaco account sales
        </Link>
      </header>

      {drawerOpen ? (
        <div className="scrim" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
      ) : null}

      <nav
        className={`sidebar${drawerOpen ? " open" : ""}`}
        aria-label="Sections"
        id="sections"
      >
        <div className="sidebar-head">
          <Link to="/" className="brand" title="Zaco account sales">
            <span className="brand-mark" aria-hidden="true">
              Z
            </span>
            <span className="side-label">Zaco account sales</span>
          </Link>
          <button
            type="button"
            ref={closeDrawer}
            className="icon-button drawer-only"
            aria-label="Close the navigation"
            onClick={() => setDrawerOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>

        <div className="side-nav">
          {items.map((item) => (
            <NavRow key={item.path} item={item} collapsed={railed} />
          ))}
        </div>

        <div className="sidebar-foot">
          {can("admin") ? <NavRow item={ACCOUNTS} collapsed={railed} /> : null}
          <div className="whoami" title={user?.email}>
            <span className="side-label">{user?.display_name || user?.email}</span>
          </div>
          <button
            type="button"
            className="side-link sign-out"
            onClick={() => void signOut()}
            title={railed ? "Sign out" : undefined}
          >
            <Icon name="signout" />
            <span className="side-label">Sign out</span>
          </button>
          <button
            type="button"
            className="icon-button rail-toggle"
            aria-label={collapsed ? "Expand the navigation" : "Collapse the navigation"}
            aria-controls="sections"
            onClick={() => setCollapsed((was) => !was)}
          >
            <Icon name={collapsed ? "expand" : "collapse"} />
          </button>
        </div>
      </nav>

      <div className="shell-body">{children}</div>
    </div>
  );
}
