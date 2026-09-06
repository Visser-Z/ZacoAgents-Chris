/**
 * Signing in.
 *
 * Two things here are not a straight port. A failed sign-in used to reload the page; here the
 * message appears beside the form with what you typed still in it. And a sign-in that was
 * interrupted by a link into a page you were not signed in for finishes at that page rather than
 * at the overview -- the address is carried in the router's location state by `RequireAuth`.
 */

import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { ApiError, api } from "../api/client";
import { Page } from "../components/Page";
import { useSession } from "../auth/session";

interface CameFrom {
  from?: string;
}

export function Login() {
  const { status, refresh } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const destination = (location.state as CameFrom | null)?.from ?? "/";

  // Already signed in. The current interface redirects here too, rather than offering a form that
  // would replace a working session with the same one.
  if (status === "signed-in") return <Navigate to={destination} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem("");
    setBusy(true);
    try {
      await api.post("/api/auth/login", { email, password });
      await refresh();
      void navigate(destination, { replace: true });
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : "Could not reach the server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Sign in" width="narrow">
      <h1>Zaco account sales</h1>
      <p className="lede">Sign in to ingest a round, resolve the queue, or read the reports.</p>

      <div className="panel">
        <form onSubmit={submit}>
          {problem ? <div className="error">{problem}</div> : null}
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p style={{ marginBottom: 0 }}>
          <Link to="/forgot">Forgotten your password?</Link>
        </p>
      </div>

      <p className="muted" style={{ fontSize: "0.9em" }}>
        Accounts are created by invitation to a specific address. If you need one, ask an
        administrator — there is no self-registration.
      </p>
    </Page>
  );
}
