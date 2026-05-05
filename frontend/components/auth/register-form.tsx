"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { ApiError, apiJson, getApiErrorMessage } from "@/lib/client-api";

function getRegisterErrorMessage(error: unknown) {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 409) return "Email is already registered";
  return getApiErrorMessage(error);
}

export function RegisterForm() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);

    try {
      await apiJson("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          display_name: displayName,
        }),
      });
      router.push("/login?registered=1");
    } catch (err) {
      setError(getRegisterErrorMessage(err));
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
        <label htmlFor="displayName" className="block text-sm font-semibold text-content-primary">
          Display name
        </label>
        <input
          id="displayName"
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
          minLength={1}
          maxLength={100}
          autoComplete="name"
          className="auth-input"
          placeholder="Your name"
        />
      </div>

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
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="password" className="block text-sm font-semibold text-content-primary">
            Password
          </label>
          <span className="text-xs text-content-tertiary">Use 8+ characters</span>
        </div>
        <div className="relative">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            className="auth-input pr-12"
            placeholder="Create a strong password"
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
        <p className="text-xs leading-5 text-content-tertiary">
          A stronger password helps protect private document access and admin-sensitive actions.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="confirmPassword" className="block text-sm font-semibold text-content-primary">
          Confirm password
        </label>
        <div className="relative">
          <input
            id="confirmPassword"
            type={showConfirmPassword ? "text" : "password"}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            className="auth-input pr-12"
            placeholder="Repeat your password"
          />
          <button
            type="button"
            onClick={() => setShowConfirmPassword((value) => !value)}
            className="auth-inline-button absolute inset-y-0 right-3 inline-flex items-center rounded-lg px-2 text-content-tertiary transition-colors hover:text-content-primary"
            aria-label={showConfirmPassword ? "Hide confirmed password" : "Show confirmed password"}
          >
            {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="auth-button-primary w-full px-4 py-3 text-sm font-semibold text-white"
      >
        {loading ? "Creating account..." : "Create account"}
      </button>
    </form>
  );
}
