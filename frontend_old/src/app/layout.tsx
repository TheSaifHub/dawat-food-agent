import type { Metadata, Viewport } from "next";
import { Cormorant_Garamond, DM_Sans } from "next/font/google";
import "./globals.css";

import { AccountNav } from "@/components/auth/AccountNav";
import { CartBar, CartLink } from "@/components/cart/CartWidgets";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { DemoBanner, SiteFooter, SiteHeader, SkipLink } from "@/components/layout/SiteChrome";
import { CartProvider } from "@/lib/cart";
import { ChatProvider } from "@/lib/chat-context";
import { SessionProvider } from "@/lib/session";
import { cn } from "@/lib/utils";

const display = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const body = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Dawat", template: "%s · Dawat" },
  description: "Every order, a feast. A Hyderabad food ordering demo with the Dawat AI assistant.",
};

export const viewport: Viewport = {
  themeColor: "#5B1E4E",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("h-full", "antialiased", display.variable, body.variable, "font-sans")}>
      <body className="flex min-h-full flex-col">
        <SessionProvider>
          <CartProvider>
            <ChatProvider>
              <SkipLink />
              <DemoBanner />
              <SiteHeader>
                <CartLink />
                <AccountNav />
              </SiteHeader>
              {/* tabIndex -1: the skip link moves real focus here in every browser, not just the scroll position. */}
              <main id="main" tabIndex={-1} className="flex flex-1 flex-col focus:outline-none">
                {children}
              </main>
              <CartBar />
              <SiteFooter />
              {/* Last in the page: the launcher is the final Tab stop, after the footer. */}
              <ChatWidget />
            </ChatProvider>
          </CartProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
