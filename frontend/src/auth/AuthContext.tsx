import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, getCurrentUser, logout, type AuthenticatedUser } from "../api";

type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: AuthenticatedUser }
  | { status: "error"; message: string };

interface AuthContextValue {
  session: SessionState;
  signOut: () => Promise<void>;
  retrySession: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionState>({ status: "loading" });
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal)
      .then((user) => setSession({ status: "authenticated", user }))
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) {
          setSession({ status: "anonymous" });
          return;
        }
        setSession({
          status: "error",
          message: error instanceof Error ? error.message : "Could not check your session.",
        });
      });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    const expireSession = () => setSession({ status: "anonymous" });
    window.addEventListener("testpulse:session-expired", expireSession);
    return () => window.removeEventListener("testpulse:session-expired", expireSession);
  }, []);

  async function signOut() {
    await logout();
    setSession({ status: "anonymous" });
  }

  const value = useMemo(
    () => ({ session, signOut, retrySession: () => setRetry((value) => value + 1) }),
    [session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
