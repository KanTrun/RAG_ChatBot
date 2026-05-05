"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

interface LoginFormProps {
  callbackUrl?: string;
}

export function LoginForm({ callbackUrl = "/chat" }: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const localAdminEmail = process.env.NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL || "";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl,
      });

      if (result?.error) {
        setError("Invalid email or password");
      } else {
        router.push(callbackUrl);
      }
    } catch {
      setError("Sign-in is temporarily unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {error && (
        <div
          role="alert"
          className="rounded-2xl border border-accent-error/30 bg-accent-error/10 px-4 py-3 text-sm text-accent-error"
        >
          {error}
        </div>
      )}

      <div className="space-y-2">
        <label htmlFor="email" className="block text-sm font-semibold text-content-primary">
          Email
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
          className="auth-input"
          placeholder="you@example.com"
        />
        <p className="text-xs leading-5 text-content-tertiary">
          Sign in with the email attached to your document workspace.
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="password" className="block text-sm font-semibold text-content-primary">
            Password
          </label>
          <span className="text-xs text-content-tertiary">Minimum 8 characters</span>
        </div>

        <div className="relative">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="current-password"
            className="auth-input pr-12"
            placeholder="Enter your password"
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            className="auth-inline-button absolute inset-y-0 right-3 inline-flex items-center rounded-lg px-2 text-content-tertiary transition-colors hover:text-content-primary"
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="auth-button-primary w-full px-4 py-3 text-sm font-semibold text-white"
      >
        {loading ? "Signing in..." : "Sign in"}
      </button>

      {localAdminEmail && (
        <div className="rounded-2xl border border-accent-primary/20 bg-accent-primary/8 px-4 py-3 text-sm">
          <p className="font-medium text-content-primary">Local dev admin</p>
          <p className="mt-1 text-content-secondary">
            Email: <span className="font-mono text-content-primary">{localAdminEmail}</span>
          </p>
          <p className="mt-1 text-content-secondary">
            Password is configured on the local backend and should not be exposed in the browser.
          </p>
        </div>
      )}
    </form>
  );
}
