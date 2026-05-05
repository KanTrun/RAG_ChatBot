"use client";

import Link from "next/link";
import { ArrowRight, FileText, LockKeyhole, Sparkles } from "lucide-react";
import { ThemeToggle } from "@/components/shared/theme-toggle";

interface AuthPageShellProps {
  eyebrow: string;
  title: string;
  description: string;
  footerText: string;
  footerHref: string;
  footerLinkLabel: string;
  children: React.ReactNode;
}

const AUTH_POINTS = [
  {
    icon: FileText,
    title: "Grounded answers",
    description: "Responses stay attached to your indexed documents and cited evidence.",
  },
  {
    icon: LockKeyhole,
    title: "Private by default",
    description: "Your workspace stays scoped and controlled across chat and document management.",
  },
  {
    icon: Sparkles,
    title: "Professional workflow",
    description: "Upload, index, compare, and summarize with a calm, enterprise-grade interface.",
  },
];

export function AuthPageShell({
  eyebrow,
  title,
  description,
  footerText,
  footerHref,
  footerLinkLabel,
  children,
}: AuthPageShellProps) {
  return (
    <div className="auth-screen min-h-dvh px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-6xl flex-col">
        <div className="flex justify-end">
          <ThemeToggle />
        </div>

        <main className="flex flex-1 items-center justify-center py-4">
          <div className="auth-shell grid w-full overflow-hidden rounded-[28px] lg:grid-cols-[1.08fr_0.92fr]">
            <section className="auth-hero-panel flex flex-col justify-between gap-10 px-6 py-8 sm:px-8 sm:py-10 lg:px-10 lg:py-12">
              <div className="space-y-6">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-content-secondary">
                  <span className="h-2 w-2 rounded-full bg-accent-citation" />
                  {eyebrow}
                </div>

                <div className="max-w-xl space-y-4">
                  <h1 className="max-w-lg font-heading text-3xl font-semibold leading-[1.05] text-content-primary sm:text-4xl lg:text-[2.85rem]">
                    {title}
                  </h1>
                  <p className="max-w-lg text-base leading-7 text-content-secondary sm:text-[1.05rem]">
                    {description}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="auth-stat-chip rounded-2xl px-4 py-3">
                    <p className="text-2xl font-semibold text-content-primary">Strict</p>
                    <p className="mt-1 text-sm text-content-secondary">Grounded document mode</p>
                  </div>
                  <div className="auth-stat-chip rounded-2xl px-4 py-3">
                    <p className="text-2xl font-semibold text-content-primary">Fast</p>
                    <p className="mt-1 text-sm text-content-secondary">Index to chat workflow</p>
                  </div>
                  <div className="auth-stat-chip rounded-2xl px-4 py-3">
                    <p className="text-2xl font-semibold text-content-primary">Clear</p>
                    <p className="mt-1 text-sm text-content-secondary">Evidence-first answers</p>
                  </div>
                </div>
              </div>

              <div className="grid gap-3">
                {AUTH_POINTS.map(({ icon: Icon, title: pointTitle, description: pointDescription }) => (
                  <div
                    key={pointTitle}
                    className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4 backdrop-blur-sm"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 rounded-xl border border-white/10 bg-white/8 p-2 text-accent-primary">
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-content-primary">{pointTitle}</p>
                        <p className="mt-1 text-sm leading-6 text-content-secondary">
                          {pointDescription}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="flex items-center justify-center px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
              <div className="auth-card w-full max-w-lg rounded-[28px] p-5 sm:p-6">
                {children}

                <div className="mt-8 border-t border-border/80 pt-5 text-sm text-content-secondary">
                  {footerText}{" "}
                  <Link
                    href={footerHref}
                    className="auth-text-link inline-flex items-center gap-1 font-semibold text-accent-primary transition-colors hover:text-accent-primary-hover"
                  >
                    {footerLinkLabel}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
