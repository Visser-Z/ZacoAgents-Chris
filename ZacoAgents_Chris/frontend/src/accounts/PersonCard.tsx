/**
 * One account, and the five things an administrator may do to it.
 *
 * Closed, it says who somebody is and what they may do. Open, it is five separate forms rather
 * than one big one with a single Save. That is deliberate: these are five different acts with
 * five different consequences, and one of them -- changing the address an account signs in with --
 * rewrites who every past decision appears to have come from. Bundling it into a Save button
 * beside a name typo would make the serious change look like the trivial one.
 *
 * `<details>` rather than a piece of state, because the browser already knows how to do this and
 * gets the keyboard and the screen-reader announcement right for free.
 */

import { useState, type FormEvent } from "react";

import {
  PERMISSIONS,
  useIssueReset,
  useSetActive,
  useSetEmail,
  useSetPermissions,
  useSetProfile,
  type Account,
  type Permission,
  type ResetLink,
} from "../api/accounts";
import { useToast } from "../components/Toasts";
import { CopyLink } from "./CopyLink";

function when(value: string | null | undefined): string {
  if (!value) return "never";
  return new Date(value).toLocaleString();
}

export function PersonCard({ person, you }: { person: Account; you: boolean }) {
  const toast = useToast();
  const setProfile = useSetProfile();
  const setEmail = useSetEmail();
  const setPermissions = useSetPermissions();
  const setActive = useSetActive();
  const issueReset = useIssueReset();

  const [name, setName] = useState(person.display_name);
  const [email, setEmailValue] = useState(person.email);
  const [emailReason, setEmailReason] = useState("");
  const [resetReason, setResetReason] = useState("");
  const [link, setLink] = useState<ResetLink | null>(null);

  const held = new Set<Permission>(person.permissions);

  async function saveName(event: FormEvent) {
    event.preventDefault();
    try {
      await setProfile.mutateAsync({ id: person.id, displayName: name });
      toast.say(`Now shown as ${name}.`);
    } catch (error) {
      toast.refuse(error);
    }
  }

  async function saveEmail(event: FormEvent) {
    event.preventDefault();
    try {
      await setEmail.mutateAsync({ id: person.id, email, reason: emailReason });
      toast.say(`Signs in as ${email} from now on.`);
      setEmailReason("");
    } catch (error) {
      toast.refuse(error);
    }
  }

  async function toggle(permission: Permission, on: boolean) {
    const next = new Set(held);
    if (on) next.add(permission);
    else next.delete(permission);
    try {
      await setPermissions.mutateAsync({ id: person.id, permissions: [...next] });
    } catch (error) {
      toast.refuse(error);
    }
  }

  async function setOnOff() {
    try {
      await setActive.mutateAsync({ id: person.id, isActive: !person.is_active });
      toast.say(person.is_active ? `${person.email} turned off.` : `${person.email} turned on.`);
    } catch (error) {
      toast.refuse(error);
    }
  }

  async function makeLink(event: FormEvent) {
    event.preventDefault();
    try {
      setLink(await issueReset.mutateAsync({ id: person.id, reason: resetReason }));
      setResetReason("");
    } catch (error) {
      toast.refuse(error);
    }
  }

  return (
    <details className="panel">
      <summary style={{ cursor: "pointer" }}>
        <strong>{person.display_name || person.email}</strong>{" "}
        <span className="muted">{person.email}</span>{" "}
        {person.is_active ? null : <span className="tag">turned off</span>}
        {you ? <span className="tag">you</span> : null}
        <div className="muted" style={{ fontSize: "0.86em", marginTop: "0.2rem" }}>
          {person.permissions.length === 0 ? "no permissions" : person.permissions.join(", ")} · last
          signed in {when(person.last_login_at)}
        </div>
      </summary>

      <h3>What this account may do</h3>
      <fieldset disabled={setPermissions.isPending}>
        <legend className="muted">Saved as you tick them.</legend>
        {PERMISSIONS.map((permission) => (
          <label key={permission.value} style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={held.has(permission.value)}
              onChange={(event) => void toggle(permission.value, event.target.checked)}
            />{" "}
            <span>{permission.what}</span>{" "}
            <span className="muted" style={{ fontSize: "0.85em" }}>
              {permission.value}
            </span>
          </label>
        ))}
      </fieldset>

      <h3>Name</h3>
      <form onSubmit={saveName}>
        <label htmlFor={`name-${person.id}`}>Shown beside every decision this account makes</label>
        <input
          id={`name-${person.id}`}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button type="submit" className="secondary" disabled={setProfile.isPending}>
          Save name
        </button>
      </form>

      <h3>Email</h3>
      <form onSubmit={saveEmail}>
        <p className="warning">
          This is the account&rsquo;s identity. Every queue answer, DN approval and append it has
          already made is stamped with the old address, so the reason you type here is what
          explains the change to whoever reads the record afterwards.
        </p>
        <label htmlFor={`email-${person.id}`}>Address</label>
        <input
          id={`email-${person.id}`}
          type="email"
          required
          value={email}
          onChange={(event) => setEmailValue(event.target.value)}
        />
        <label htmlFor={`why-${person.id}`}>Why</label>
        <input
          id={`why-${person.id}`}
          type="text"
          required
          placeholder="Married name; the old address was typed wrong; …"
          value={emailReason}
          onChange={(event) => setEmailReason(event.target.value)}
        />
        <button type="submit" className="secondary" disabled={setEmail.isPending}>
          Change address
        </button>
      </form>

      <h3>Password</h3>
      {link ? (
        <>
          <p className="notice">
            Give this to {link.email}. It works once, and expires{" "}
            {new Date(link.expires_at).toLocaleString()}.
          </p>
          <CopyLink url={link.reset_url} />
          <p className="muted" style={{ fontSize: "0.9em" }}>
            It is shown here once and is not stored anywhere you can read it again. If it is lost,
            issue another.
          </p>
          <button type="button" className="link" onClick={() => setLink(null)}>
            Done with it
          </button>
        </>
      ) : (
        <form onSubmit={makeLink}>
          <label htmlFor={`reset-${person.id}`}>Why (optional, kept with the account)</label>
          <input
            id={`reset-${person.id}`}
            type="text"
            placeholder="Asked in person; said they could not get in; …"
            value={resetReason}
            onChange={(event) => setResetReason(event.target.value)}
          />
          <button type="submit" className="secondary" disabled={issueReset.isPending}>
            Issue a one-time link
          </button>
        </form>
      )}

      <h3>Access</h3>
      <p className="muted">
        A turned-off account cannot sign in, and a link issued before it was turned off is refused
        too. Nothing it has already done is removed — the record keeps its name.
      </p>
      <button type="button" className="secondary" onClick={() => void setOnOff()} disabled={you}>
        {person.is_active ? "Turn this account off" : "Turn this account back on"}
      </button>
      {you ? (
        <p className="muted" style={{ fontSize: "0.9em" }}>
          You cannot turn off your own account, or take away your own administrator permission.
        </p>
      ) : null}
    </details>
  );
}
