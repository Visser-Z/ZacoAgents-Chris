/**
 * A link that has to be carried to somebody by hand.
 *
 * Both of the things this shows -- an invitation and a one-time password reset -- reach a person
 * because an administrator passes them on. There is no mail in this system by design (D3), so the
 * link on screen is the whole delivery mechanism and it has to be easy to get out of the browser
 * without retyping.
 *
 * The link is shown as well as copyable, not hidden behind the button. `navigator.clipboard`
 * needs a secure context, so on an http host that is not localhost it is simply absent -- and a
 * copy button that silently does nothing, with no visible link to fall back on, is how somebody
 * ends up telling a colleague a token over the phone.
 */

import { useEffect, useRef, useState } from "react";

const SAID_FOR = 2000;

export function CopyLink({ url, label = "Copy link" }: { url: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), SAID_FOR);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Selecting it is the honest fallback: it says what to do next rather than failing quietly.
      field.current?.select();
    }
  }

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
      <input
        ref={field}
        type="text"
        readOnly
        value={url}
        onFocus={(event) => event.target.select()}
        style={{ flex: 1, fontFamily: "ui-monospace, monospace", fontSize: "0.85em" }}
      />
      <button type="button" className="secondary" onClick={() => void copy()}>
        {copied ? "Copied" : label}
      </button>
    </div>
  );
}
