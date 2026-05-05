import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const auth = vi.fn();

vi.mock("@/lib/auth", () => ({
  auth: (...args: unknown[]) => auth(...args),
}));

describe("api v1 proxy route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts loopback uploads when the public forwarded origin differs from the container origin", async () => {
    auth.mockResolvedValue({ accessToken: "access-token" });
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "pending" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    const { POST } = await import("@/app/api/v1/[...path]/route");

    const request = new Request("http://localhost:3000/api/v1/documents/upload", {
      method: "POST",
      headers: {
        origin: "http://127.0.0.1:3001",
        host: "localhost:3000",
        "x-forwarded-host": "127.0.0.1:3001",
        "x-forwarded-proto": "http",
        "content-type": "multipart/form-data; boundary=test-boundary",
      },
      body: "--test-boundary--",
    });

    const response = await POST(request as NextRequest, {
      params: Promise.resolve({ path: ["documents", "upload"] }),
    });

    expect(response.status).toBe(201);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents/upload"),
      expect.objectContaining({ method: "POST" }),
    );

    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe("Bearer access-token");
  });
});
