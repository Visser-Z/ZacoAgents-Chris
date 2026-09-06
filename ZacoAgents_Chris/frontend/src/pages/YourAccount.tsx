/**
 * Your own account: who the record says you are, and changing your password.
 *
 * Everything this page shows about you is read-only, and that is the point rather than an
 * omission. Your name and address are stamped on every queue answer, DN approval and append you
 * have made, so changing either rewrites who those decisions appear to have come from -- which is
 * an administrator's act, recorded with a reason, not something to do to yourself quietly.
 *
 * The password is the exception, because it is the one thing here that is nobody else's business.
 * Changing it demands the current one: a session left open on a shared machine should not be
 * enough to lock its owner out of their own account.
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { ApiError, api, type Schemas } from "../api/client";
import { PERMISSIONS } from "../api/accounts";
import { Page } from "../components/Page";
import { useSession } from "../auth/session";

const MINIMUM = 12;

function when(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function YourAccount() {
  const { user } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [problem, setProblem] = useState("");
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);

  const matches = again === "" || again === next;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem("");
    setSaid("");
    if (next !== again) {
      setProblem("Those two do not match.");
      return;
    }
    setBusy(true);
    try {
      const answer = await api.post<Schemas["Message"]>("/api/auth/password", {
        current_password: current,
        new_password: next,
      });
      setSaid(answer.detail);
      setCurrent("");
      setNext("");
      setAgain("");
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : "Could not reach the server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const held = PERMISSIONS.filter((p) => user?.permissions.includes(p.value));

  return (
    <Page title="Your account">
      <h1>Your account</h1>
      <p className="lede">
        This is the name on every decision you make here. An administrator changes it, and the
        change is recorded with a reason.
      </p>

      <div className="panel">
        <table>
          <tbody>
            <tr>
              <th scope="row">Name</th>
              <td>{user?.display_name || "—"}</td>
            </tr>
            <tr>
              <th scope="row">Email</th>
              <td>{user?.email}</td>
            </tr>
            <tr>
              <th scope="row">Last signed in</th>
              <td>{when(user?.last_login_at)}</td>
            </tr>
            <tr>
              <th scope="row">May</th>
              <td>
                {held.length === 0 ? (
                  <span className="muted">Nothing yet — ask an administrator.</span>
                ) : (
                  held.map((p) => (
                    <span key={p.value} className="tag" title={p.what}>
                      {p.label}
                    </span>
                  ))
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Change your password</h2>
      <div className="panel">
        <form onSubmit={submit}>
          {problem ? <div className="error">{problem}</div> : null}
          {said ? <div className="notice">{said}</div> : null}
          <label htmlFor="current">Current password</label>
          <input
            id="current"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <label htmlFor="next">New password (at least {MINIMUM} characters)</label>
          <input
            id="next"
            type="password"
            autoComplete="new-password"
            required
            minLength={MINIMUM}
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
          <label htmlFor="again">Type it again</label>
          <input
            id="again"
            type="password"
            autoComplete="new-password"
            required
            value={again}
            onChange={(event) => setAgain(event.target.value)}
            aria-invalid={!matches}
          />
          {matches ? null : <p className="warning">Those two do not match yet.</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Changing…" : "Change password"}
          </button>
        </form>
      </div>

      <p className="muted" style={{ fontSize: "0.9em" }}>
        If you cannot remember the current one, sign out and{" "}
        <Link to="/login">say so from the sign-in page</Link>. An administrator can give you a
        one-time link.
      </p>
    </Page>
  );
}
