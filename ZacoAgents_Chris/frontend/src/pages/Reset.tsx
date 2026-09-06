/**
 * Spending a reset link on a new password.
 *
 * The link arrives from one of two places -- an administrator who issued it, or the recovery
 * command run on the server when no administrator could -- and it is the same page either way,
 * because the difference is in who had the standing to hand it over, not in what happens next.
 *
 * Two things here are not in `Accept`, which this otherwise mirrors. There is a second password
 * field, because a link works once: a typo on an invitation costs you a sign-in you can retry,
 * while a typo here spends the only way back in and leaves you asking for another. And a spent or
 * expired link says so on its own line with the way forward under it, rather than as a form error
 * beside fields that can no longer do anything.
 */

import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError, api } from "../api/client";
import { Page } from "../components/Page";
import { useSession } from "../auth/session";

const MINIMUM = 12;

export function Reset() {
  const { token = "" } = useParams();
  const { refresh } = useSession();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [problem, setProblem] = useState("");
  const [spent, setSpent] = useState(false);
  const [busy, setBusy] = useState(false);

  const matches = again === "" || again === password;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem("");
    if (password !== again) {
      setProblem("Those two do not match.");
      return;
    }
    // The same rule as `MINIMUM_PASSWORD` in `zaco/auth/service.py`, checked here so that it is
    // the only thing this page can be refused for that is worth retyping. `use_reset` checks the
    // link first and spends it last, so a password too short comes back as a refusal with the
    // link still good -- and telling somebody to go and get another one would be wrong.
    if (password.length < MINIMUM) {
      setProblem(`Use at least ${MINIMUM} characters.`);
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/auth/reset", { token, password });
      // The API signs you in with the new password, so there is nowhere sensible to land except
      // inside. Being asked to type it again immediately would read as the reset not having
      // worked.
      await refresh();
      void navigate("/", { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        // With the length checked above, what is left the server can refuse this for is the link
        // being spent or expired, or the account being turned off. Neither is fixable by typing
        // again, so both end the page rather than sitting as an error beside fields that can no
        // longer do anything. Decided by what the form already ruled out, not by reading the
        // server's sentence -- a message that gets reworded should not change what the page does.
        setSpent(true);
        setProblem(error.message);
      } else {
        setProblem("Could not reach the server. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (spent) {
    return (
      // The heading stays general because two different things land here: a link that has been
      // used or has run out, and an account that has been turned off. The server's own sentence
      // says which, and the way forward is the same either way -- a person.
      <Page title="That link did not work" width="narrow">
        <h1>That link did not work</h1>
        <div className="panel">
          <p className="error">{problem}</p>
          <p>
            A link can be used once and lasts four hours. Ask an administrator, or say so from the
            sign-in page and they will see that you are waiting.
          </p>
          <p>
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </Page>
    );
  }

  return (
    <Page title="Set a new password" width="narrow">
      <h1>Set a new password</h1>
      <p className="lede">
        This link works once and then stops. Choosing a password here signs you in with it.
      </p>

      <div className="panel">
        <form onSubmit={submit}>
          {problem ? <div className="error">{problem}</div> : null}
          <label htmlFor="password">New password (at least {MINIMUM} characters)</label>
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
            {busy ? "Setting…" : "Set password and sign in"}
          </button>
        </form>
      </div>
    </Page>
  );
}
