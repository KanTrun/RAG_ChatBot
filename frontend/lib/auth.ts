import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import type { JWT } from "next-auth/jwt";

const API_URL = process.env.BACKEND_URL || "http://localhost:8000";
const REFRESH_BUFFER_MS = 60_000;
const DEFAULT_ACCESS_TOKEN_TTL_MS = 15 * 60 * 1000;

interface BackendTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface AccessTokenPayload {
  sub?: string;
  email?: string;
  roles?: string[];
  exp?: number;
}

function decodeAccessToken(token?: string): AccessTokenPayload {
  if (!token) return {};
  try {
    const payload = token.split(".")[1];
    if (!payload) return {};
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const json = decodeURIComponent(
      Array.from(atob(padded), (char) =>
        `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`,
      ).join(""),
    );
    return JSON.parse(json);
  } catch {
    return {};
  }
}

function tokenExpiresAt(accessToken?: string): number {
  const payload = decodeAccessToken(accessToken);
  return payload.exp ? payload.exp * 1000 : Date.now() + DEFAULT_ACCESS_TOKEN_TTL_MS;
}

function buildToken(
  token: JWT,
  data: BackendTokenResponse,
  fallbackEmail?: string | null,
): JWT {
  const payload = decodeAccessToken(data.access_token);
  return {
    ...token,
    sub: payload.sub ?? token.sub,
    email: payload.email ?? fallbackEmail ?? token.email,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    accessTokenExpires: tokenExpiresAt(data.access_token),
    roles: payload.roles ?? [],
    error: undefined,
  };
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
  if (!token.refreshToken) {
    return { ...token, error: "RefreshAccessTokenError" };
  }

  try {
    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token.refreshToken }),
    });

    if (!response.ok) {
      throw new Error("Refresh failed");
    }

    const data = (await response.json()) as BackendTokenResponse;
    return buildToken(token, data);
  } catch {
    return { ...token, error: "RefreshAccessTokenError" };
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        const response = await fetch(`${API_URL}/api/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });

        if (!response.ok) return null;

        const data = (await response.json()) as BackendTokenResponse;
        const payload = decodeAccessToken(data.access_token);
        return {
          id: payload.sub ?? String(credentials.email),
          email: payload.email ?? String(credentials.email),
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
        };
      },
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GitHub({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),
  ],
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user?.accessToken) {
        return buildToken(token, {
          access_token: user.accessToken,
          refresh_token: user.refreshToken ?? "",
          token_type: "bearer",
        }, user.email);
      }

      if (!token.accessTokenExpires || !token.refreshToken) {
        return token;
      }

      if (Date.now() < token.accessTokenExpires - REFRESH_BUFFER_MS) {
        return token;
      }

      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.accessTokenExpires = token.accessTokenExpires;
      session.roles = token.roles ?? [];
      session.error = token.error;
      if (session.user) {
        if (token.sub) {
          session.user.id = token.sub;
        }
        session.user.email = token.email ?? session.user.email;
        session.user.roles = token.roles ?? [];
      }
      return session;
    },
  },
});
