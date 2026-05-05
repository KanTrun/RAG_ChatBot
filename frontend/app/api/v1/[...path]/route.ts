import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";

const API_BASE = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function isAllowedOrigin(origin: string, requestOrigin: string) {
  if (origin === requestOrigin) return true;

  for (const value of [process.env.NEXTAUTH_URL, process.env.AUTH_URL]) {
    if (!value) continue;
    try {
      if (origin === new URL(value).origin) return true;
    } catch {
      continue;
    }
  }

  try {
    const actual = new URL(origin);
    const expected = new URL(requestOrigin);
    const loopbackHosts = new Set(["localhost", "127.0.0.1"]);
    return (
      actual.protocol === expected.protocol &&
      actual.port === expected.port &&
      loopbackHosts.has(actual.hostname) &&
      loopbackHosts.has(expected.hostname)
    );
  } catch {
    return false;
  }
}

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

function getRequestOrigin(request: NextRequest) {
  const url = new URL(request.url);
  const forwardedHost = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (!forwardedHost) return url.origin;

  const forwardedProto = request.headers.get("x-forwarded-proto");
  const protocol = forwardedProto ?? url.protocol.replace(":", "");
  return `${protocol}://${forwardedHost}`;
}

async function proxyRequest(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const requestOrigin = getRequestOrigin(request);

  if (MUTATING_METHODS.has(request.method)) {
    const origin = request.headers.get("origin");
    if (origin && !isAllowedOrigin(origin, requestOrigin)) {
      return NextResponse.json({ detail: "Invalid request origin" }, { status: 403 });
    }
  }

  const targetUrl = `${API_BASE}/api/v1/${path.join("/")}${url.search}`;
  const session = await auth();
  if (session?.error === "RefreshAccessTokenError") {
    return NextResponse.json(
      { detail: "Session expired. Please sign in again." },
      { status: 401 },
    );
  }

  const token = session?.accessToken;

  const headers = new Headers(request.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = await request.arrayBuffer();
  }

  const response = await fetch(targetUrl, init);
  const responseHeaders = new Headers(response.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    responseHeaders.delete(header);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
