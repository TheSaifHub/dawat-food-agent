-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════
-- 0014 · Razorpay test payments: one attempt row per payment, and a paid-before-progress guard   (Phase 8, D-061)
--
-- A confirmed cart is paid for BEFORE its orders exist (Saif, Session 21): POST /payments/start records an attempt
-- (the server's confirmed total and quote, plus the Razorpay order it created), and POST /payments/verify creates the
-- Dawat orders only after the Razorpay signature checks out and the quote is unchanged. The orders already carry
-- razorpay_order_id / razorpay_payment_id / payment_status (0002); this adds the attempt ledger and two second-layer
-- checks so the rules hold even if a code path forgets them.
-- Additive only: one new table and two CHECK constraints that every existing row already satisfies
-- (all existing orders are 'pending' or sample orders).
-- ════════════════════════════════════════════════════════════════════════════════════════════════════════════

create table if not exists public.payment_attempts (
  attempt_id          uuid primary key default gen_random_uuid(),
  user_id             uuid not null references public.users (user_id) on delete restrict,
  cart_id             uuid not null references public.carts (cart_id) on delete restrict,
  quote_id            text not null,                          -- the confirmed quote this payment is for
  amount              integer not null check (amount > 0),    -- whole rupees: the confirmed grand_total, set by the server
  razorpay_order_id   text not null unique,
  razorpay_payment_id text,
  status              text not null default 'created' check (status in ('created', 'paid', 'expired', 'needs_refund')),
  checkout_id         uuid,                                   -- the orders created by a paid attempt
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  check ((status = 'paid') = (checkout_id is not null)),
  check (status not in ('paid', 'needs_refund') or razorpay_payment_id is not null)
);
-- one payment can complete one attempt, ever
create unique index if not exists payment_attempts_payment_idx on public.payment_attempts (razorpay_payment_id)
  where razorpay_payment_id is not null;
create index if not exists payment_attempts_cart_idx on public.payment_attempts (cart_id, status);

create or replace trigger payment_attempts_touch
  before update on public.payment_attempts for each row execute function public.touch_updated_at();

-- Backend only (it connects as the table owner); the browser roles get nothing.
alter table public.payment_attempts enable row level security;
revoke all on public.payment_attempts from anon, authenticated;

-- Second layer 1: an order marked paid carries its Razorpay order and payment ids.
alter table public.orders add constraint orders_paid_has_payment
  check (payment_status <> 'paid' or (razorpay_order_id is not null and razorpay_payment_id is not null));

-- Second layer 2: an order moves past 'placed' only if it is paid (or is a sample order for the demo accounts).
alter table public.orders add constraint orders_progress_needs_payment
  check (status in ('placed', 'cancelled') or payment_status = 'paid' or is_sample);
