"use client";

// The header's account control: "Sign in", or Orders, the user's name (their profile) and "Sign out" (Phase 7g).
// It sits on plum, so focus rings are gold (5.8:1 on plum) and text is ivory.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useSession } from "@/lib/session";

// No display class here: each control sets its own (inline-flex, or hidden on phones / wider screens). A shared
// inline-flex would override `hidden`, since both set display.
const base = "h-10 items-center rounded-md px-2 sm:px-3 text-ivory underline-offset-4 hover:underline focus-visible:outline-gold";
const control = `inline-flex ${base}`;

export function AccountNav() {
  const { session, signOut } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  if (session.state === "loading") return <span className="h-10 w-20" aria-hidden="true" />;
  if (session.state !== "signed_in") {
    return (
      <Link href="/login" className={control} aria-current={pathname === "/login" ? "page" : undefined}>
        Sign in
      </Link>
    );
  }
  const current = (href: string) => (pathname === href || pathname.startsWith(href + "/") ? "page" : undefined);
  return (
    <div className="flex items-center gap-1">
      {/* Phase 7g: Orders, and the name opens the profile. Phones show only a short "Profile" link (the profile page
          has Your orders and Sign out): with the cart count, more would push the header past a 360px screen. */}
      <Link href="/orders" className={`${base} hidden sm:inline-flex`} aria-current={current("/orders")}>Orders</Link>
      <Link href="/profile" className={`${base} hidden max-w-[12rem] text-sm sm:inline-flex`} aria-current={current("/profile")}>
        <span className="sr-only">Profile, signed in as </span><span className="truncate">{session.me.display_name}</span>
      </Link>
      <Link href="/profile" className={`${base} inline-flex sm:hidden`} aria-current={current("/profile")}>Profile</Link>
      <button type="button" className={`${base} hidden sm:inline-flex`} onClick={async () => { await signOut(); router.push("/"); }}>
        Sign out
      </button>
    </div>
  );
}
