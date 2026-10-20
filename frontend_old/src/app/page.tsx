import { DawatLogo } from "@/components/brand/DawatLogo";
import { HomeBrowse } from "@/components/browse/HomeBrowse";
import { AskDawatAI } from "@/components/chat/AskDawatAI";

// Home (Phase 7c, D-049; 7f, D-058): the brand, the invitation to just ask Dawat AI (the showcase), then the area
// picker, cuisine shortcuts and chains near you.
export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-10 px-4 py-12">
      <section className="flex flex-col items-center gap-4 text-center">
        <DawatLogo size={88} title="" />
        <h1 className="font-display text-5xl font-semibold text-plum sm:text-6xl">Dawat</h1>
        <p className="text-lg">Every order, a feast. Browse real Hyderabad restaurants near you.</p>
      </section>
      <AskDawatAI />
      <HomeBrowse />
    </div>
  );
}
