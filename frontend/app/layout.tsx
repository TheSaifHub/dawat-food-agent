import type { Metadata } from 'next';
import { Cormorant_Garamond, DM_Sans } from 'next/font/google';
import './globals.css';
import { SessionProvider } from '@/lib/session';
import { DawatProvider } from '@/context/DawatContext';
import { TopBanner } from '@/components/TopBanner';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { ChatPanel } from '@/components/ChatPanel';
import { AuthGate } from '@/components/AuthGate';

const cormorant = Cormorant_Garamond({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-cormorant',
  display: 'swap',
});

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-dm-sans',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Dawat — Every order, a feast | Hyderabad Nizami Dining',
  description:
    'Experience authentic Hyderabad dining with Dawat and your AI dining concierge. From charcoal-dum biryanis to royal samovar chai.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${cormorant.variable} ${dmSans.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#FAF6EF] text-[#22161F]">
        <SessionProvider>
          <DawatProvider>
            {/* Hard Rule Mandated Top Banner */}
            <TopBanner />

            {/* Persistent App Header */}
            <Header />

            {/* Main Content Area */}
            <main className="flex-1 w-full" id="main-content">
              <AuthGate>{children}</AuthGate>
            </main>

            {/* Hard Rule Mandated Global Footer */}
            <Footer />

            {/* Dawat AI Universal Chat Concierge */}
            <ChatPanel />
          </DawatProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
