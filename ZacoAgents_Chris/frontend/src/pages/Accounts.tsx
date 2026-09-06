/**
 * Accounts: who may use this system, and what has been done to their accounts.
 *
 * The order of the page is the order of urgency, not the order the API happens to list things in.
 * People waiting to be let back in come first, because that is somebody currently unable to work
 * and the only thing here that is blocked on an administrator noticing. Invitations next, then the
 * accounts themselves, then the trail.
 *
 * The trail is last and it is the reason the rest can be trusted. An email change rewrites who
 * every past decision appears to have come from; a permission granted quietly is a permission
 * nobody can be asked about later. Rounds have carried a trail since Phase 3, and accounts --
 * which decide the identity behind every entry in it -- carried none of their own until now.
 */

import { useState, type FormEvent } from "react";

import {
  PERMISSIONS,
  useAccountEvents,
  useAccounts,
  useInvitations,
  useInvite,
  usePasswordRequests,
  useReissueInvitation,
  useRevokeInvitation,
  type Permission,
} from "../api/accounts";
import { CopyLink } from "../accounts/CopyLink";
import { Page } from "../components/Page";
import { PersonCard } from "../accounts/PersonCard";
import { useSession } from "../auth/session";
import { useToast } from "../components/Toasts";

function when(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function day(value: string): string {
  return new Date(value).toLocaleDateString();
}

function Waiting() {
  const requests = usePasswordRequests();
  const rows = requests.data ?? [];
  if (rows.length === 0) return null;

  return (
    <>
      <h2>Waiting to be let back in</h2>
      <div className="panel">
        <p className="notice">
          These people said they could not sign in. Nothing was emailed to them — open their
          account below and issue a one-time link, then give it to them the way you would tell them
          anything else.
        </p>
        <table>
          <thead>
            <tr>
              <th>Who</th>
              <th>Email</th>
              <th>Asked</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.user_id}-${row.requested_at ?? ""}`}>
                <td>{row.display_name || "—"}</td>
                <td>{row.email}</td>
                <td>{when(row.requested_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Invitations() {
  const toast = useToast();
  const invitations = useInvitations();
  const invite = useInvite();
  const revoke = useRevokeInvitation();
  const reissue = useReissueInvitation();

  const [email, setEmail] = useState("");
  const [chosen, setChosen] = useState<Set<Permission>>(new Set());

  const all = invitations.data ?? [];
  const open = all.filter((row) => row.accepted_at === null);

  async function send(event: FormEvent) {
    event.preventDefault();
    try {
      await invite.mutateAsync({ email, permissions: [...chosen] });
      toast.say(`Invitation created for ${email}. Copy the link below and pass it on.`);
      setEmail("");
      setChosen(new Set());
    } catch (error) {
      toast.refuse(error);
    }
  }

  function tick(permission: Permission, on: boolean) {
    setChosen((current) => {
      const next = new Set(current);
      if (on) next.add(permission);
      else next.delete(permission);
      return next;
    });
  }

  return (
    <>
      <h2>Invite someone</h2>
      <div className="panel">
        <form onSubmit={send}>
          <label htmlFor="invite-email">Email address</label>
          <input
            id="invite-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <fieldset>
            <legend>What this account may do</legend>
            {PERMISSIONS.map((permission) => (
              <label key={permission.value} style={{ display: "block" }}>
                <input
                  type="checkbox"
                  checked={chosen.has(permission.value)}
                  onChange={(event) => tick(permission.value, event.target.checked)}
                />{" "}
                <span>{permission.what}</span>{" "}
                <span className="muted" style={{ fontSize: "0.85em" }}>
                  {permission.value}
                </span>
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={invite.isPending}>
            Create invitation
          </button>
        </form>
      </div>

      <h2>Open invitations</h2>
      <div className="panel">
        {open.length === 0 ? (
          <p className="muted">Nobody has an invitation outstanding.</p>
        ) : (
          <>
            {open.map((row) => {
              const expired = new Date(row.expires_at).getTime() < Date.now();
              return (
                <div key={row.id} style={{ marginBottom: "1rem" }}>
                  <p style={{ marginBottom: "0.35rem" }}>
                    <strong>{row.email}</strong>{" "}
                    {row.permissions.map((p) => (
                      <span key={p} className="tag">
                        {p}
                      </span>
                    ))}{" "}
                    <span className="muted">
                      {expired ? "ran out" : "expires"} {day(row.expires_at)}
                    </span>
                  </p>
                  {expired ? (
                    <p className="warning">
                      This one has run out. Re-issuing gives the same invitation a fresh link and
                      another week, rather than making a second one to the same address.
                    </p>
                  ) : (
                    <CopyLink url={row.accept_url} />
                  )}
                  <p style={{ marginTop: "0.35rem" }}>
                    <button
                      type="button"
                      className="link"
                      disabled={reissue.isPending}
                      onClick={() => {
                        reissue.mutate(row.id, {
                          onSuccess: () => toast.say(`Fresh link for ${row.email}.`),
                          onError: (error) => toast.refuse(error),
                        });
                      }}
                    >
                      Re-issue
                    </button>{" "}
                    <button
                      type="button"
                      className="link"
                      disabled={revoke.isPending}
                      onClick={() => {
                        if (!window.confirm(`Revoke the invitation for ${row.email}?`)) return;
                        revoke.mutate(row.id, {
                          onSuccess: () => toast.say(`Invitation for ${row.email} revoked.`),
                          onError: (error) => toast.refuse(error),
                        });
                      }}
                    >
                      Revoke
                    </button>
                  </p>
                </div>
              );
            })}
            <p className="muted" style={{ fontSize: "0.9em", marginBottom: 0 }}>
              No mail is sent. Copy the link and pass it on however you normally would.
            </p>
          </>
        )}
      </div>
    </>
  );
}

function Trail() {
  const events = useAccountEvents();
  const rows = events.data ?? [];

  return (
    <>
      <h2>What has been done to accounts</h2>
      <div className="panel">
        {rows.length === 0 ? (
          <p className="muted">Nothing yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Account</th>
                <th>What</th>
                <th>Why</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.at}-${row.user_id}-${index}`}>
                  <td>{when(row.at)}</td>
                  <td>{row.email}</td>
                  <td>
                    {row.action}
                    {row.detail ? (
                      <div className="muted" style={{ fontSize: "0.86em" }}>
                        {row.detail}
                      </div>
                    ) : null}
                  </td>
                  <td>{row.reason || <span className="muted">—</span>}</td>
                  <td>{row.by || <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

export function Accounts() {
  const { user } = useSession();
  const accounts = useAccounts();

  return (
    <Page title="Accounts">
      <h1>Accounts</h1>
      <p className="lede">
        Invitations go to a specific email address, and every person gets their own account. A
        shared account would make the audit trail worthless: &ldquo;chose this export
        because…&rdquo; means nothing if the record says a domain decided.
      </p>

      <Waiting />
      <Invitations />

      <h2>People</h2>
      {accounts.isPending ? (
        <div className="checking" />
      ) : accounts.error ? (
        <div className="error">{(accounts.error as Error).message}</div>
      ) : (
        (accounts.data ?? []).map((person) => (
          <PersonCard key={person.id} person={person} you={person.id === user?.id} />
        ))
      )}

      <Trail />
    </Page>
  );
}
