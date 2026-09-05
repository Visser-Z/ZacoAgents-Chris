/**
 * What the queue page says when an action succeeds or is refused.
 *
 * Replaces `window.alert`. Eighteen of those was not a style problem: an alert stops the page,
 * has to be dismissed before anything else can be read, and cannot show the row it is about --
 * so a refusal that named a delivery arrived as a sentence with no context and then vanished.
 *
 * Deliberately not used for anything a form can say better. A message about the field you are
 * filling in belongs beside that field; this is for the actions that happen further down the
 * page, where the button you pressed may already have scrolled away.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Tone = "said" | "refused";

interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

interface Toaster {
  say: (message: string) => void;
  refuse: (error: unknown) => void;
}

const ToastContext = createContext<Toaster | null>(null);

/** A refusal stays until it is dismissed; a confirmation goes on its own. Being told something
 *  worked is worth a glance, and being told why something did not is worth reading twice. */
const SAID_FOR = 4000;

let counter = 0;

export function ToastHost({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const drop = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback((tone: Tone, message: string) => {
    counter += 1;
    setToasts((current) => [...current, { id: counter, tone, message }]);
  }, []);

  const value = useMemo<Toaster>(
    () => ({
      say: (message) => push("said", message),
      refuse: (error) =>
        push("refused", error instanceof Error ? error.message : "Something went wrong."),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <Note key={toast.id} toast={toast} onDone={() => drop(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function Note({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  useEffect(() => {
    if (toast.tone === "refused") return;
    const timer = window.setTimeout(onDone, SAID_FOR);
    return () => window.clearTimeout(timer);
  }, [toast.tone, onDone]);

  return (
    <div className={`toast ${toast.tone}`}>
      <span>{toast.message}</span>
      <button type="button" className="link" onClick={onDone} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}

export function useToast(): Toaster {
  const toaster = useContext(ToastContext);
  if (!toaster) throw new Error("useToast was called outside <ToastHost>.");
  return toaster;
}
