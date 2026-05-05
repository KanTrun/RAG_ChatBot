import { BadgeCheck } from "lucide-react";
import { AuthPageShell } from "@/components/auth/auth-page-shell";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { RegisterForm } from "@/components/auth/register-form";

export default function RegisterPage() {
  return (
    <AuthPageShell
      eyebrow="Professional onboarding"
      title="Create a workspace built for cited, document-first answers."
      description="Set up your account once, then move smoothly from upload to retrieval to grounded chat in a cleaner, more confident environment."
      footerText="Already have an account?"
      footerHref="/login"
      footerLinkLabel="Sign in"
    >
      <div className="space-y-6">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent-secondary/20 bg-accent-secondary/8 px-3 py-1 text-xs font-medium text-accent-secondary">
            <BadgeCheck className="h-3.5 w-3.5" />
            Refined onboarding
          </div>

          <div>
            <h2 className="font-heading text-2xl font-semibold text-content-primary">
              Create your account
            </h2>
            <p className="mt-2 text-sm leading-6 text-content-secondary">
              Start with a secure account, index your private documents, and ask better questions
              inside a workspace designed for evidence-first AI assistance.
            </p>
          </div>
        </div>

        <OAuthButtons />

        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-content-tertiary">
            Or register with email
          </span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <RegisterForm />

        <p className="text-xs leading-6 text-content-tertiary">
          Use a work email if this workspace will manage shared reports, admin review, or document
          operations across a team.
        </p>
      </div>
    </AuthPageShell>
  );
}
