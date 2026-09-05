/**
 * Who is signed in, asked once for the whole app.
 *
 * The Jinja pages knew this from the server on every render; a single-page app has to ask, and
 * every page asking separately would be eight requests for one answer. So it is fetched once
 * here and read from context.
 *
 * Three states, not two. `checking` is the one that matters: rendering the signed-out shape while
 * the answer is still in flight would flash the login page at somebody who is signed in, on every
 * reload.
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

import { ApiError, api, onSessionExpired, type Schemas } from "../api/client";

export type User = Schemas["UserOut"];
export type Permission = Schemas["Permission"];

export type SessionStatus = "checking" | "signed-in" | "signed-out";

export interface Session {
  status: SessionStatus;
  user: User | null;
  /** Re-ask the API. Called after signing in, and after anything that changes permissions. */
  refresh: () => Promise<void>;
  /** Record locally that the session is gone. Does not call the API -- see `signOut`. */
  forget: () => void;
  signOut: () => Promise<void>;
  can: (permission: Permission) => boolean;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [user, setUser] = useState<User | null>(null);

  const forget = useCallback(() => {
    setUser(null);
    setStatus("signed-out");
  }, []);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.get<User>("/api/auth/me"));
      setStatus("signed-in");
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthenticated) {
        forget();
        return;
      }
      // Anything else -- the API being down, a proxy in the way -- is not evidence that nobody is
      // signed in. Treating it as a sign-out would bounce the viewer to a login page that cannot
      // work either, and lose the address they were on.
      setStatus("signed-out");
      throw error;
    }
  }, [forget]);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  // A session that expires mid-visit is reported by whichever request was in flight. This is the
  // one place that knows what to do about it.
  useEffect(() => onSessionExpired(forget), [forget]);

  const signOut = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } finally {
      // Even if the call fails, this browser is done with the session. Leaving the shell showing
      // a signed-in person after they pressed Sign out is the worse of the two wrong answers.
      forget();
    }
  }, [forget]);

  const value = useMemo<Session>(
    () => ({
      status,
      user,
      refresh,
      forget,
      signOut,
      can: (permission) => user?.permissions.includes(permission) ?? false,
    }),
    [status, user, refresh, forget, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession was called outside <SessionProvider>.");
  return session;
}
