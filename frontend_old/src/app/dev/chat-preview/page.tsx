import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ChatPreview } from "./ChatPreview";

// A development-only page that shows the Dawat AI panel with a fixed conversation (fixture.json: real plan_meal output
// from the local test database), so the panel can be checked for accessibility and layout without signing in or
// spending model calls. A production build answers 404.

export const metadata: Metadata = { title: "Chat preview (dev)", robots: { index: false } };

const VIEWS = ["conversation", "plans", "thinking", "plan-card", "signed-out", "empty"] as const;
export type PreviewView = (typeof VIEWS)[number];

export default async function Page({ searchParams }: PageProps<"/dev/chat-preview">) {
  if (process.env.NODE_ENV === "production") notFound();
  const asked = (await searchParams).view;
  const view = VIEWS.find((v) => v === asked) ?? "conversation";
  return <ChatPreview view={view} />;
}
