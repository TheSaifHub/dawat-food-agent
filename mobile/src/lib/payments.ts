// Simulated test payments (D-061, D-062). No real money, no real card.
//
// The rules (money and consent, so tested hard in __tests__/payment.test.tsx):
//  - The app NEVER sends an amount. /payments/start takes the cart id and answers with the amount the server
//    computed; that is the only figure ever shown. /payments/verify takes only the three values the gateway returned.
//  - Only the fixed test values of docs/API_CONTRACT.md can be chosen (INSTRUMENTS below). There is no text field, so a
//    real card number cannot be typed, stored or sent. No expiry, no CVV, nothing about the instrument is kept.
//  - "Pay" asks for a successful test payment, "Simulate failed payment" for a failed one, with the same instrument.
//  - /payments/verify is called only after the simulator said "paid", and with exactly what it returned. A declined
//    payment creates no order and changes nothing: the cart stays confirmed and the user can try again.
//  - The words shown are the app's own, never a tool's message (those are written for Dawat AI).

import type { ApiResult } from './api';

export const TEST_NOTICE = 'Test payment (simulated). No real money.';

export type Method = 'card' | 'upi';
export type Instrument = { id: string; method: Method; label: string; hint: string; value: string; alwaysFails: boolean };

/** The only values the simulated gateway accepts. Anything else is refused by the server and cannot be chosen here. */
export const INSTRUMENTS: readonly Instrument[] = [
  { id: 'visa', method: 'card', label: 'Visa test card', hint: 'ending 1111', value: '4111 1111 1111 1111', alwaysFails: false },
  { id: 'mastercard', method: 'card', label: 'Mastercard test card', hint: 'ending 4444', value: '5555 5555 5555 4444', alwaysFails: false },
  { id: 'declined', method: 'card', label: 'Test card that is always declined', hint: 'ending 0002', value: '4000 0000 0000 0002', alwaysFails: true },
  { id: 'upi-ok', method: 'upi', label: 'Test UPI id', hint: 'success@razorpay', value: 'success@razorpay', alwaysFails: false },
  { id: 'upi-fail', method: 'upi', label: 'Test UPI id that always fails', hint: 'failure@razorpay', value: 'failure@razorpay', alwaysFails: true },
];

export type Request = <T>(path: string, options?: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown }) => Promise<ApiResult<T>>;

export type Start = { razorpay_order_id: string; amount_rupees: number; gateway: string; cart_id: string; quote_id: string };
export type PaidOrder = { order_id: string; order_number: string; restaurant: string; branch_label: string; status: string; total: number };

export type StartResult = { ok: true; start: Start } | { ok: false; kind: 'changed' | 'unavailable' | 'error'; message: string };

type Body = { status?: string; message?: string; amount?: number } & Record<string, unknown>;
const bodyOf = (r: ApiResult<unknown>): Body => ((r.ok || r.kind === 'http' ? r.data : null) ?? {}) as Body;

/** Opens the payment for the confirmed cart. Sends the cart id and nothing else. */
export async function startPayment(request: Request, cartId: string): Promise<StartResult> {
  const r = await request<Start & { status: string }>('/payments/start', { method: 'POST', body: { cart_id: cartId } });
  if (r.ok && r.data.status === 'ok' && r.data.razorpay_order_id && Number.isInteger(r.data.amount_rupees)) return { ok: true, start: r.data };
  if (!r.ok && r.kind !== 'http') return { ok: false, kind: 'error', message: r.message };
  const b = bodyOf(r);
  if (b.status === 'not_confirmed' || b.status === 'quote_changed')
    return { ok: false, kind: 'changed', message: 'Your cart changed. Please check it and confirm again.' };
  if (b.status === 'not_found') return { ok: false, kind: 'changed', message: "We couldn't find that cart. Please check your cart." };
  if (b.status === 'payments_not_configured' || b.status === 'payment_unavailable')
    return { ok: false, kind: 'unavailable', message: 'Payments are not available right now. Nothing was charged. Please try again later.' };
  return { ok: false, kind: 'error', message: r.ok ? "That didn't work. Please try again." : r.message };
}

export type PayResult =
  | { kind: 'paid'; orders: PaidOrder[]; grandTotal: number }
  | { kind: 'declined'; message: string }
  | { kind: 'retry'; message: string }
  | { kind: 'refund'; message: string }
  | { kind: 'error'; message: string };

const DECLINED = "The test payment didn't go through. Nothing was charged and no order was placed. You can try again.";

/** The simulate body: exactly these fields. Card: the card number only. UPI: the UPI id only. Never an amount. */
export function simulateBody(start: Start, instrument: Instrument, outcome: 'success' | 'failure') {
  return {
    razorpay_order_id: start.razorpay_order_id,
    outcome,
    method: instrument.method,
    ...(instrument.method === 'card' ? { card_number: instrument.value } : { upi_id: instrument.value }),
  };
}

/** One tap on Pay (or on Simulate failed payment): simulate, and only if that paid, verify. */
export async function payAndVerify(request: Request, start: Start, instrument: Instrument, outcome: 'success' | 'failure'): Promise<PayResult> {
  const sim = await request<{ status: string; razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }>('/payments/simulate', {
    method: 'POST',
    body: simulateBody(start, instrument, outcome),
  });
  if (!sim.ok) {
    if (sim.kind !== 'http') return { kind: 'error', message: sim.message };
    if (sim.status === 402) return { kind: 'declined', message: DECLINED };
    if (sim.status === 422) return { kind: 'error', message: "That payment couldn't be started. Please go back and try again." };
    return { kind: 'error', message: sim.message };
  }
  const p = sim.data;
  if (p.status !== 'ok' || !p.razorpay_order_id || !p.razorpay_payment_id || !p.razorpay_signature)
    return { kind: 'error', message: "That didn't work. Please try again." };

  const ver = await request<{ status: string; orders?: PaidOrder[]; grand_total?: number }>('/payments/verify', {
    method: 'POST',
    body: { razorpay_order_id: p.razorpay_order_id, razorpay_payment_id: p.razorpay_payment_id, razorpay_signature: p.razorpay_signature },
  });
  if (ver.ok) {
    const d = ver.data;
    if ((d.status === 'ok' || d.status === 'already_paid') && d.orders && d.orders.length > 0 && typeof d.grand_total === 'number')
      return { kind: 'paid', orders: d.orders, grandTotal: d.grand_total };
    return { kind: 'error', message: "That didn't work. Please try again." };
  }
  if (ver.kind !== 'http') return { kind: 'retry', message: `${ver.message} Your test payment may have gone through: tap Pay again to finish.` };
  const b = bodyOf(ver);
  if (ver.status === 409 && b.status === 'needs_refund') {
    const amount = typeof b.amount === 'number' ? ` of ₹${b.amount}` : '';
    return { kind: 'refund', message: `Your cart or a price changed while you were paying, so no order was placed. The test payment${amount} is refunded (simulated). Please check your cart.` };
  }
  if (ver.status === 422 && b.status === 'bad_signature')
    return { kind: 'retry', message: "The payment couldn't be confirmed, so no order was placed. Nothing is owed. You can pay again." };
  if (ver.status === 409 && b.status === 'payment_conflict')
    return { kind: 'error', message: 'A different payment is already recorded for this order. Please check your orders.' };
  if (ver.status === 503) return { kind: 'retry', message: 'Payments are busy right now. Nothing was ordered. Please try again in a moment.' };
  return { kind: 'error', message: ver.message };
}
