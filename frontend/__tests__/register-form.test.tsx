import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegisterForm } from "@/components/auth/register-form";
import { LoginForm } from "@/components/auth/login-form";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  signIn: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("next-auth/react", () => ({
  signIn: (...args: unknown[]) => mocks.signIn(...args),
  signOut: vi.fn(),
}));

describe("RegisterForm", () => {
  beforeEach(() => {
    mocks.push.mockReset();
    mocks.signIn.mockReset();
    globalThis.fetch = vi.fn() as unknown as typeof fetch;
    delete process.env.NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL;
  });

  it("creates an account and returns to login", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        access_token: "access-token",
        refresh_token: "refresh-token",
        token_type: "bearer",
      }),
    } as Response);
    render(<RegisterForm />);

    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "New User" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "new-user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Password123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/auth/register",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            email: "new-user@example.com",
            password: "Password123!",
            display_name: "New User",
          }),
        }),
      );
    });
    expect(mocks.push).toHaveBeenCalledWith("/login?registered=1");
  });

  it("blocks submission when password confirmation differs", async () => {
    render(<RegisterForm />);

    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "New User" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "new-user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Password123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "Password456!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows a clear duplicate email error", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Email already registered" }),
    } as Response);

    render(<RegisterForm />);

    fireEvent.change(screen.getByLabelText(/display name/i), {
      target: { value: "New User" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "new-user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Password123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is already registered");
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("shows local admin email without exposing the password", () => {
    process.env.NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL = "admin123@gmail.com";

    render(<LoginForm />);

    expect(screen.getByText("Local dev admin")).toBeInTheDocument();
    expect(screen.getByText("admin123@gmail.com")).toBeInTheDocument();
    expect(
      screen.getByText(/Password is configured on the local backend/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("admin123")).not.toBeInTheDocument();
  });

  it("preserves callbackUrl after successful credentials sign-in", async () => {
    mocks.signIn.mockResolvedValue({ error: undefined });

    render(<LoginForm callbackUrl="/admin" />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "viewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() =>
      expect(mocks.signIn).toHaveBeenCalledWith("credentials", {
        email: "viewer@example.com",
        password: "Password123!",
        redirect: false,
        callbackUrl: "/admin",
      }),
    );
    expect(mocks.push).toHaveBeenCalledWith("/admin");
  });

  it("recovers cleanly when credentials sign-in rejects", async () => {
    mocks.signIn.mockRejectedValue(new Error("network down"));

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "viewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("Sign-in is temporarily unavailable. Please try again.");
    expect(screen.getByRole("button", { name: /^sign in$/i })).not.toBeDisabled();
  });
});
