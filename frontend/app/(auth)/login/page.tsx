import { ShieldCheck } from "lucide-react";
import { AuthPageShell } from "@/components/auth/auth-page-shell";
import { LoginForm } from "@/components/auth/login-form";
import { OAuthButtons } from "@/components/auth/oauth-buttons";

interface LoginPageProps {
  searchParams?: Promise<{ registered?: string; error?: string; callbackUrl?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const registered = params?.registered === "1";
  const sessionExpired = params?.error === "SessionExpired";
  const callbackUrl = params?.callbackUrl || "/chat";

  return (
    <AuthPageShell
      eyebrow="Secure document workspace"
      title="Sign in to a sharper, grounded RAG workflow."
      description="A refined workspace for teams who need fast retrieval, explicit citations, and a calm interface that feels trustworthy from the first screen."
      footerText="Need a new workspace?"
      footerHref="/register"
      footerLinkLabel="Create an account"
    >
      <div className="space-y-6">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent-primary/20 bg-accent-primary/8 px-3 py-1 text-xs font-medium text-accent-primary">
            <ShieldCheck className="h-3.5 w-3.5" />
            Authenticated access
          </div>

          <div>
            <h2 className="font-heading text-2xl font-semibold text-content-primary">
              Welcome back
            </h2>
            <p className="mt-2 text-sm leading-6 text-content-secondary">
              Continue where you left off and return to your indexed documents, active chat scope,
              and grounded answers.
            </p>
          </div>
        </div>

        {registered && (
          <div
            role="status"
            className="rounded-2xl border border-accent-success/30 bg-accent-success/10 px-4 py-3 text-sm text-accent-success"
          >
            Account created. Please sign in.
          </div>
        )}
        {sessionExpired && (
          <div
            role="alert"
            className="rounded-2xl border border-accent-error/30 bg-accent-error/10 px-4 py-3 text-sm text-accent-error"
          >
            Session expired. Please sign in again.
          </div>
        )}

        <OAuthButtons callbackUrl={callbackUrl} />

        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-content-tertiary">
            Or use email
          </span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <LoginForm callbackUrl={callbackUrl} />

        <p className="text-xs leading-6 text-content-tertiary">
          Protected access keeps your conversation scope, document ownership, and admin controls
          separated correctly.
        </p>
      </div>
    </AuthPageShell>
  );
}
