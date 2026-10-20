import type { Metadata } from "next";

import { LoginPanel } from "@/components/auth/LoginPanel";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-12">
      <h1 className="font-display text-5xl font-semibold text-plum">Sign in</h1>
      <LoginPanel />
    </section>
  );
}
