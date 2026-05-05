import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";

export default auth((request) => {
  if (!request.auth || request.auth.error === "RefreshAccessTokenError") {
    const loginUrl = new URL("/login", request.nextUrl.origin);
    loginUrl.searchParams.set("callbackUrl", request.nextUrl.pathname);
    if (request.auth?.error === "RefreshAccessTokenError") {
      loginUrl.searchParams.set("error", "SessionExpired");
    }
    return NextResponse.redirect(loginUrl);
  }
});

export const config = {
  matcher: ["/chat/:path*", "/admin/:path*", "/documents/:path*"],
};
