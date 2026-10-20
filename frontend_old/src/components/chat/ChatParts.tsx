"use client";

// What a chat message is made of (Phase 7f, D-058): the reply text, the steps Dawat AI took (the "thinking" panel),
// a confirmation card and plan options. Cards and plans are built by the BACKEND's code from tool results, never from
// the model's words, so every price on them is the server's (D-046). Their buttons just send the visitor's answer
// ("Yes", "No", or the plan they picked) as a chat message: the backend decides what that yes can act on.

import Link from "next/link";
import { Fragment } from "react";

import { DietMark, SPICE_NAMES } from "@/components/restaurant/RestaurantView";
import { stepLine, stepOutcome, type Card, type CardLine, type PlanOption, type Step } from "@/lib/chat";
import { orderHref } from "@/lib/orders";

// ─── reply text: paragraphs, "- " lists and **bold**, as plain React text (never inserted as HTML) ─────

function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) => p.startsWith("**") && p.endsWith("**") && p.length > 4
        ? <strong key={i}><OrderLinks text={p.slice(2, -2)} /></strong>
        : <OrderLinks key={i} text={p.replace(/(^|\s)\*(\S[^*]*\S|\S)\*(?=\s|$|[.,!?])/g, "$1$2")} />)}
    </>
  );
}

/** Phase 7g: order numbers ("#DW1042", "DW1042") become links to their tracking page. Only that exact shape is
 *  linked, and the page asks the backend, which answers only for the signed-in user's own orders. */
function OrderLinks({ text }: { text: string }) {
  const parts = text.split(/(#?\bDW\d{4,7}\b)/g);
  return (
    <>
      {parts.map((p, i) => i % 2
        ? <Link key={i} href={orderHref(p)} className="font-semibold text-plum underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">{p}</Link>
        : <Fragment key={i}>{p}</Fragment>)}
    </>
  );
}

export function RichText({ text }: { text: string }) {
  const blocks: { list: boolean; ordered: boolean; lines: string[] }[] = [];
  for (const raw of text.replace(/\r/g, "").split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const item = bullet?.[1] ?? numbered?.[1];
    const last = blocks[blocks.length - 1];
    if (item !== undefined) {
      if (last?.list && last.ordered === !!numbered) last.lines.push(item);
      else blocks.push({ list: true, ordered: !!numbered, lines: [item] });
    } else if (!line.trim()) {
      blocks.push({ list: false, ordered: false, lines: [] });
    } else if (last && !last.list && last.lines.length) {
      last.lines.push(line);
    } else {
      blocks.push({ list: false, ordered: false, lines: [line] });
    }
  }
  return (
    <div className="flex flex-col gap-2">
      {blocks.filter((b) => b.lines.length).map((b, i) => b.list ? (
        b.ordered
          ? <ol key={i} className="ml-5 list-decimal space-y-1">{b.lines.map((l, j) => <li key={j}><Inline text={l} /></li>)}</ol>
          : <ul key={i} className="ml-5 list-disc space-y-1">{b.lines.map((l, j) => <li key={j}><Inline text={l} /></li>)}</ul>
      ) : (
        <p key={i}>{b.lines.map((l, j) => <Fragment key={j}>{j ? <br /> : null}<Inline text={l} /></Fragment>)}</p>
      ))}
    </div>
  );
}

// ─── the thinking panel ─────────────────────────────────────────────────────────────────────────────

function StepList({ steps }: { steps: Step[] }) {
  return (
    <ol className="flex flex-col gap-1.5 text-sm">
      {steps.map((s) => {
        const out = stepOutcome(s);
        return (
          <li key={s.step} className="flex gap-2">
            <span aria-hidden="true" className={out.good ? "text-veg" : "text-destructive"}>{out.good ? "✓" : "✕"}</span>
            <span>
              {stepLine(s)} <span className="text-muted-foreground">· {out.text} · {(s.latency_ms / 1000).toFixed(1)} s</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** While a turn runs: each tool call as it finishes. */
export function LiveSteps({ steps }: { steps: Step[] }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/60 p-3">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <span aria-hidden="true" className="inline-block size-2 animate-pulse rounded-full bg-plum motion-reduce:animate-none" />
        Dawat AI is thinking…
      </p>
      {steps.length ? <StepList steps={steps} /> : <p className="text-sm text-muted-foreground">Reading your message</p>}
    </div>
  );
}

/** After the reply: the same steps, folded away. */
export function DoneSteps({ steps }: { steps: Step[] }) {
  if (!steps.length) return null;
  return (
    <details className="group rounded-lg border border-border px-3 py-2 text-sm">
      <summary className="cursor-pointer rounded-sm py-1 font-medium text-plum focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        How Dawat AI got this · {steps.length} {steps.length === 1 ? "step" : "steps"}
      </summary>
      <div className="pt-2"><StepList steps={steps} /></div>
    </details>
  );
}

// ─── confirmation cards ─────────────────────────────────────────────────────────────────────────────

const money = (n: number | null | undefined) => (typeof n === "number" ? `₹${n.toLocaleString("en-IN")}` : "");

function Lines({ lines }: { lines: CardLine[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {lines.map((l, i) => (
        <li key={i} className="flex items-start justify-between gap-3">
          <span className="flex items-start gap-2">
            {l.is_veg === null ? null : <DietMark isVeg={l.is_veg} />}
            <span>{l.qty} × {l.name}{l.restaurant ? <span className="text-muted-foreground">, {l.restaurant}</span> : null}</span>
          </span>
          <span className="shrink-0">{money(l.line_total)}</span>
        </li>
      ))}
    </ul>
  );
}

const yesButton = "inline-flex min-h-11 items-center justify-center rounded-lg bg-plum px-4 font-semibold text-ivory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const noButton = "inline-flex min-h-11 items-center justify-center rounded-lg border border-plum bg-card px-4 font-semibold text-plum hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

function cardWords(card: Card): { title: string; yes: string; no: string } {
  switch (card.kind) {
    case "order": return { title: "Place this order?", yes: `Yes, place order · ${money(card.grand_total)}`, no: "Not yet" };
    case "plan": return { title: `Add the “${card.label ?? "chosen"}” plan to your cart?`, yes: "Yes, add it", no: "No" };
    case "diet": return { title: "This is non-veg. Is it for someone else?", yes: "Yes, add it", no: "No" };
    case "preference": return card.offer?.action === "delete"
      ? { title: `Forget ${card.label}?`, yes: "Yes, forget it", no: "No" }
      : { title: `Save to your preferences: ${card.label}?`, yes: "Yes, save it", no: "No" };
    case "remove": return { title: "Remove from your cart?", yes: "Yes, remove", no: "No, keep it" };
    case "delivery": return { title: `Deliver to ${card.area} instead?`, yes: "Yes, change it", no: "No" };
  }
}

export function ConfirmCard({ card, active, onAnswer }: { card: Card; active: boolean; onAnswer: (text: string) => void }) {
  const words = cardWords(card);
  const headingId = `card-${card.card_id}`;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3 rounded-xl border-2 border-plum bg-card p-4">
      <h3 id={headingId} className="font-sans text-base font-semibold">{words.title}</h3>
      {card.kind === "order" || card.kind === "plan" ? <Lines lines={card.lines} /> : null}
      {card.kind === "diet" ? (
        <p>{card.items.map((it) => `${it.qty} × ${it.name}`).join(", ")}. Your saved diet is {card.saved_diet}.</p>
      ) : null}
      {card.kind === "remove" ? (
        <p>{card.items.map((it) => (it.qty ? `${it.qty} × ${it.name}` : `${it.name} (all of it)`)).join(", ")}</p>
      ) : null}
      {card.kind === "delivery" ? <p>Prices, fees and what&apos;s available may change.</p> : null}
      {card.kind === "order" || card.kind === "plan" ? (
        <div className="flex flex-col gap-1 border-t border-border pt-2 text-sm">
          {card.deliver_to ? <p>Deliver to {card.deliver_to}</p> : null}
          {card.kind === "plan" && card.replace ? <p className="font-medium text-destructive">This replaces everything in your cart.</p> : null}
          {card.kind === "plan" && card.nonveg.length ? (
            <p>Non-veg: {card.nonveg.join(", ")} (your saved diet is {card.saved_diet}).</p>
          ) : null}
          <p className="text-base font-semibold">Total {money(card.grand_total)} <span className="text-sm font-normal text-muted-foreground">with delivery and GST</span></p>
        </div>
      ) : null}
      {active ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={yesButton} onClick={() => onAnswer("Yes")}>{words.yes}</button>
          <button type="button" className={noButton} onClick={() => onAnswer("No")}>{words.no}</button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">This question has passed. Ask again in the chat if you still want it.</p>
      )}
    </section>
  );
}

// ─── plan options ───────────────────────────────────────────────────────────────────────────────────

export function PlanCards({ plans, active, onPick }: { plans: PlanOption[]; active: boolean; onPick: (text: string) => void }) {
  return (
    <ul className="flex flex-col gap-3" aria-label="Meal plans">
      {plans.map((p) => (
        <li key={p.plan_id}>
          <article aria-labelledby={`plan-${p.plan_id}`} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
            <h3 id={`plan-${p.plan_id}`} className="flex items-baseline justify-between gap-3 font-sans text-base font-semibold">
              <span>{p.label}</span><span>{money(p.grand_total)}</span>
            </h3>
            {p.restaurants.map((r) => (
              <div key={r.branch_id} className="flex flex-col gap-1">
                <p className="text-sm font-medium">{r.restaurant} <span className="font-normal text-muted-foreground">· {r.branch_label}, {r.distance_km} km</span></p>
                <ul className="flex flex-col gap-1 text-sm">
                  {r.items.map((it, i) => (
                    <li key={i} className="flex items-start justify-between gap-3">
                      <span className="flex items-start gap-2">
                        <DietMark isVeg={it.is_veg} />
                        <span>{it.qty} × {it.name} <span className="text-muted-foreground">· {SPICE_NAMES[it.spice_level] ?? `spice ${it.spice_level}`}</span></span>
                      </span>
                      <span className="shrink-0">{money(it.line_total)}</span>
                    </li>
                  ))}
                </ul>
                <p className="text-sm text-muted-foreground">
                  Delivery {r.free_delivery ? "free" : money(r.delivery_fee)} · GST {money(r.taxes)}
                </p>
              </div>
            ))}
            {p.diet_note ? <p className="text-sm">{p.diet_note}</p> : null}
            <p className="text-sm">
              <strong>Total {money(p.grand_total)}</strong> with delivery and GST
              {typeof p.budget_left === "number" && p.budget_left > 0 ? <>, {money(p.budget_left)} under your budget</> : null}
            </p>
            {active ? (
              <button type="button" className={yesButton} onClick={() => onPick(`I'll take the “${p.label}” plan (${money(p.grand_total)}).`)}>
                Choose {p.label} · {money(p.grand_total)}
              </button>
            ) : null}
          </article>
        </li>
      ))}
    </ul>
  );
}
