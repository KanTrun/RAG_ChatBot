import { describe, expect, it, vi } from "vitest";

const signOut = vi.fn();

vi.mock("next-auth/react", () => ({
  signOut: (...args: unknown[]) => signOut(...args),
}));

describe("client api wrapper", () => {
  it("signs out when an API call returns 401", async () => {
    vi.resetModules();
    globalThis.fetch = vi.fn().mockResolvedValue({
      status: 401,
      ok: false,
      json: async () => ({ detail: "Invalid or expired token" }),
    }) as unknown as typeof fetch;

    const { apiJson } = await import("@/lib/client-api");

    await expect(apiJson("/api/v1/documents")).rejects.toThrow(
      "Session expired. Please sign in again.",
    );
    expect(signOut).toHaveBeenCalledWith({ callbackUrl: "/login" });
  });

  it("surfaces backend detail messages for 403 responses", async () => {
    vi.resetModules();
    globalThis.fetch = vi.fn().mockResolvedValue({
      status: 403,
      ok: false,
      json: async () => ({ detail: "Invalid request origin" }),
    }) as unknown as typeof fetch;

    const { apiJson } = await import("@/lib/client-api");

    await expect(apiJson("/api/v1/documents/upload", { method: "POST" })).rejects.toThrow(
      "Invalid request origin",
    );
  });
});
