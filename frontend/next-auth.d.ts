import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    accessTokenExpires?: number;
    roles?: string[];
    error?: "RefreshAccessTokenError";
    user?: DefaultSession["user"] & {
      id?: string;
      roles?: string[];
    };
  }

  interface User {
    accessToken?: string;
    refreshToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    accessTokenExpires?: number;
    roles?: string[];
    error?: "RefreshAccessTokenError";
  }
}
