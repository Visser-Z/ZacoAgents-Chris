/**
 * Saying you cannot get in.
 *
 * This page gives nothing away and is written so that it visibly gives nothing away. The answer
 * is the same sentence whether or not the address has an account, and it is rendered from the
 * server's own words rather than from anything this page knows -- so there is no branch here that
 * a reader could suspect of leaking one, and none that a later edit could accidentally add.
 *
 * Nothing is emailed, because there is no mail in this system by design (D3). What the request
 * does is put the person on a list an administrator can see, which is how an invitation already
 * reaches somebody: by hand, from a person who knows who they are.
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { ApiError, api, type Schemas } from "../api/client";
import { Page } from "../components/Page";

export function Forgot() {
  const [email, setEmail] = useState("");
  const [said, setSaid] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem("");
    setBusy(true);
    try {
      const answer = await api.post<Schemas["Message"]>("/api/auth/forgot", { email });
      setSaid(answer.detail);
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : "Could not reach the server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Forgotten password" width="narrow">
      <h1>Forgotten your password</h1>

      {said ? (
        <div className="panel">
          <p className="notice">{said}</p>
          <p>
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      ) : (
        <>
          <p className="lede">
            Tell us the address you sign in with. An administrator will see that you are waiting
            and can give you a one-time link.
          </p>
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
              <button type="submit" disabled={busy}>
                {busy ? "Sending…" : "Tell an administrator"}
              </button>
            </form>
          </div>
          <p className="muted" style={{ fontSize: "0.9em" }}>
            Nothing is emailed. The link is handed to you by somebody, the same way your invitation
            was.
          </p>
        </>
      )}
    </Page>
  );
}
