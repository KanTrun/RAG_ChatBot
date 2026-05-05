import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/(auth)/login/page";
import RegisterPage from "@/app/(auth)/register/page";
import { OAuthButtons } from "@/components/auth/oauth-buttons";

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

describe("auth pages", () => {
  beforeEach(() => {
    mocks.push.mockReset();
    mocks.signIn.mockReset();
  });

  it("renders the refined login page with registered status", async () => {
    render(await LoginPage({ searchParams: Promise.resolve({ registered: "1" }) }));

    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.getByText(/Account created\. Please sign in\./i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /create an account/i })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("renders the refined register page shell", () => {
    render(<RegisterPage />);

    expect(screen.getByRole("heading", { name: /create your account/i })).toBeInTheDocument();
    expect(screen.getByText(/Refined onboarding/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("sends oauth sign-in actions to the expected providers", () => {
    render(<OAuthButtons callbackUrl="/documents" />);

    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue with github/i }));

    expect(mocks.signIn).toHaveBeenNthCalledWith(1, "google", { callbackUrl: "/documents" });
    expect(mocks.signIn).toHaveBeenNthCalledWith(2, "github", { callbackUrl: "/documents" });
  });
});
