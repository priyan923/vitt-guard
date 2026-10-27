import { useState } from "react";
import type { FormEvent } from "react";
import { ShieldCheck } from "lucide-react";
import { ApiError, verifyCredentials } from "../api/client";

interface LoginPageProps {
  onAuthenticated: () => void;
}

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await verifyCredentials(username, password);
      setPassword("");
      onAuthenticated();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError && requestError.status === 401
          ? "The username or password was not accepted."
          : "Authentication could not be verified. Check the service and retry.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <div className="brand auth-brand">
          <div className="brand__mark">
            <ShieldCheck size={21} strokeWidth={2.2} />
          </div>
          <span>
            vitt<span className="brand__light">guard</span>
          </span>
        </div>
        <p className="eyebrow">PROTECTED DEMONSTRATION</p>
        <h1 id="auth-title">Sign in to Vitt Guard</h1>
        <p className="auth-description">
          Use the demo credentials provided by the site owner. Credentials are
          kept in memory only for this browser session.
        </p>
        <form className="auth-form" onSubmit={submit}>
          <label className="field-label" htmlFor="auth-username">
            Username
          </label>
          <input
            autoComplete="username"
            id="auth-username"
            name="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <label className="field-label" htmlFor="auth-password">
            Password
          </label>
          <input
            autoComplete="current-password"
            id="auth-password"
            name="password"
            required
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button button--primary auth-submit"
            disabled={submitting}
            type="submit"
          >
            {submitting ? "Verifying…" : "Sign in"}
          </button>
        </form>
        <p className="auth-footnote">
          All actions remain simulated; no money moves.
        </p>
      </section>
    </main>
  );
}
