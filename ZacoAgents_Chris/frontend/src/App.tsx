/**
 * Step 2 is the toolchain, not the interface. This page exists to prove the chain end to end --
 * the build, the mount under /app, the session cookie reaching the API, and the generated types
 * describing what comes back. The shell replaces it in step 3.
 */

import { useEffect, useState } from "react";

import { ApiError, api, type Schemas } from "./api/client";

type User = Schemas["UserOut"];

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<User>("/api/auth/me")
      .then(setUser)
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.isUnauthenticated) {
          setProblem("Not signed in. Sign in on the current interface, then reload this page.");
          return;
        }
        setProblem(error instanceof Error ? error.message : String(error));
      });
  }, []);

  return (
    <main className="narrow">
      <h1>Zaco</h1>
      <p className="lede">
        The React interface, being built alongside the one at <a href="/">/</a>. Nothing here
        replaces that yet.
      </p>

      {problem ? <div className="error">{problem}</div> : null}

      {user ? (
        <div className="panel">
          <p>
            Signed in as <strong>{user.display_name ?? user.email}</strong>.
          </p>
          <p className="muted" style={{ marginBottom: 0 }}>
            {user.permissions.length} permission(s): {user.permissions.join(", ")}
          </p>
        </div>
      ) : null}
    </main>
  );
}
