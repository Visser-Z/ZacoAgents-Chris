/** Turning an invitation into an account. */

import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import { ApiError, api } from "../api/client";
import { Page } from "../components/Page";
import { useSession } from "../auth/session";

const MINIMUM = 12;

export function Accept() {
  const { token = "" } = useParams();
  const { refresh } = useSession();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem("");
    setBusy(true);
    try {
      await api.post("/api/auth/accept", {
        token,
        password,
        display_name: displayName,
      });
      await refresh();
      void navigate("/", { replace: true });
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : "Could not reach the server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Set up your account" width="narrow">
      <h1>Set up your account</h1>
      <p className="lede">
        This invitation belongs to one email address. Your own account is what stamps every queue
        answer, DN approval and append you make, so it is not shared.
      </p>

      <div className="panel">
        <form onSubmit={submit}>
          {problem ? <div className="error">{problem}</div> : null}
          <label htmlFor="display_name">Your name</label>
          <input
            id="display_name"
            type="text"
            autoComplete="name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
          <label htmlFor="password">Choose a password (at least {MINIMUM} characters)</label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MINIMUM}
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
      </div>
    </Page>
  );
}
