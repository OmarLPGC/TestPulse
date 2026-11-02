import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { getGitHubLoginUrl } from "../api";
import { ErrorState, LoadingState, PulseMark } from "../components/ui";
import { useAuth } from "./AuthContext";
import type { ReactNode } from "react";

export function AuthRoutes({ children }: { children: ReactNode }) {
  return (
    <Routes>
      <Route element={<LoginPage />} path="/login" />
      <Route element={<ProtectedRoute>{children}</ProtectedRoute>} path="*" />
    </Routes>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { session, retrySession } = useAuth();
  const location = useLocation();

  if (session.status === "loading") {
    return <LoadingState label="Checking your session" />;
  }
  if (session.status === "anonymous") {
    return <Navigate replace state={{ from: location }} to="/login" />;
  }
  if (session.status === "error") {
    return <ErrorState message={session.message} onRetry={retrySession} />;
  }
  return children;
}

function LoginPage() {
  const { session } = useAuth();
  const location = useLocation();
  const destination = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  if (session.status === "authenticated") {
    return <Navigate replace to={destination || "/"} />;
  }
  if (session.status === "loading") {
    return <LoadingState label="Checking your session" />;
  }
  if (session.status === "error") {
    return <ErrorState message={session.message} onRetry={() => window.location.reload()} />;
  }

  return (
    <main className="login-page">
      <section aria-labelledby="login-heading" className="login-panel">
        <PulseMark />
        <h1 id="login-heading">Sign in to TestPulse</h1>
        <p>Use your GitHub account to open your workspaces and test history.</p>
        {destination && (
          <p className="login-session-notice" role="status">
            Your session expired or this page requires authentication. Sign in again to continue.
          </p>
        )}
        <a className="github-login-button" href={getGitHubLoginUrl()}>
          Continue with GitHub
        </a>
        <p className="login-note">Your GitHub access stays on this TestPulse installation.</p>
      </section>
    </main>
  );
}
