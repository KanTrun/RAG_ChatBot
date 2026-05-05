"use client";

import { LogOut } from "lucide-react";
import { signOut, useSession } from "next-auth/react";

export function AuthenticatedUserFooter() {
  const { data: session } = useSession();
  const email = session?.user?.email ?? "Signed in";
  const roles = session?.roles ?? session?.user?.roles ?? [];
  const isAdmin = roles.includes("admin");

  return (
    <div className="space-y-3">
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-content-primary">{email}</p>
        <span className="mt-1 inline-flex rounded-full border border-border-primary px-2 py-0.5 text-[11px] font-medium text-content-tertiary">
          {isAdmin ? "Admin" : "User"}
        </span>
      </div>
      <button
        type="button"
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-border-primary px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
      >
        <LogOut className="h-3.5 w-3.5" />
        Logout
      </button>
    </div>
  );
}
