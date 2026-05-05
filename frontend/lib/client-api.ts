"use client";

import { signOut } from "next-auth/react";

const SESSION_EXPIRED_MESSAGE = "Session expired. Please sign in again.";

let authRedirectStarted = false;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // Response is not JSON; use status-specific fallback.
  }

  if (response.status === 403) return "You do not have permission for this action.";
  if (response.status === 413) return "File is too large.";
  if (response.status === 400) return "Unsupported file or invalid request.";
  return "Request failed.";
}

async function handleUnauthorized() {
  if (authRedirectStarted) return;
  authRedirectStarted = true;
  await signOut({ callbackUrl: "/login" });
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
  });

  if (response.status === 401) {
    await handleUnauthorized();
    throw new ApiError(401, SESSION_EXPIRED_MESSAGE);
  }

  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  return apiJson<T>(path, {
    method: "POST",
    body: formData,
  });
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}
