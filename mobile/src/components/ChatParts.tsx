import { useState } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppText } from './AppText';
import { Button } from './Button';
import { VegMark } from './MenuParts';
import { rupees } from './BillParts';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';
import { stepLine, stepOutcome, type Card, type CardLine, type PlanOption, type Step } from '@/lib/chat';
import type { ChatMessage } from '@/lib/chat-context';

/** The words a card button sends. Exactly these two, whatever the label says. */
export const YES = 'Yes';
export const NO = 'No';

export function Bubble({ m }: { m: Extract<ChatMessage, { role: 'user' | 'assistant' }> }) {
  const mine = m.role === 'user';
  return (
    <View
      accessible
      accessibilityLabel={`${mine ? 'You' : 'Dawat AI'}: ${m.text}`}
      style={{
        alignSelf: mine ? 'flex-end' : 'flex-start',
        maxWidth: '88%',
        backgroundColor: mine ? colors.navy : colors.card,
        borderRadius: radii.md,
        paddingHorizontal: 14,
        paddingVertical: 10,
      }}
    >
      <AppText color={mine ? colors.white : colors.ink} selectable>
        {m.text}
      </AppText>
    </View>
  );
}

export function Notice({ text, tone }: { text: string; tone: 'info' | 'error' }) {
  return (
    <View style={{ alignSelf: 'stretch', backgroundColor: tone === 'error' ? colors.coralTint : colors.butter, borderRadius: radii.sm, padding: 10 }} accessibilityLiveRegion="polite">
      <AppText weight={600}>{text}</AppText>
    </View>
  );
}

function StepRow({ s }: { s: Step }) {
  const o = stepOutcome(s);
  return (
    <View style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }}>
      <Ionicons name={o.good ? 'checkmark-circle' : 'alert-circle'} size={16} color={colors.navy} style={{ marginTop: 2 }} />
      <AppText variant="caption" style={{ flex: 1 }}>
        {stepLine(s)} · {o.text}
      </AppText>
    </View>
  );
}

/** The live "Dawat AI is thinking" panel: one row per tool step, as each one arrives. */
export function ThinkingPanel({ steps, slow }: { steps: Step[]; slow: boolean }) {
  return (
    <View style={{ alignSelf: 'stretch', backgroundColor: colors.sky, borderRadius: radii.md, padding: 12, gap: 8 }} accessibilityLiveRegion="polite">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <ActivityIndicator color={colors.navy} />
        <AppText weight={700}>{slow && steps.length === 0 ? 'Waking up Dawat AI…' : 'Dawat AI is thinking…'}</AppText>
      </View>
      {steps.map((s) => (
        <StepRow key={s.step} s={s} />
      ))}
    </View>
  );
}

/** After the reply the steps fold into one line that opens on tap. */
export function StepsSummary({ steps }: { steps: Step[] }) {
  const [open, setOpen] = useState(false);
  if (steps.length === 0) return null;
  return (
    <View style={{ alignSelf: 'flex-start', gap: 6 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`How Dawat AI got this, ${steps.length} ${steps.length === 1 ? 'step' : 'steps'}`}
        onPress={() => setOpen(!open)}
        style={{ minHeight: MIN_TARGET, flexDirection: 'row', alignItems: 'center', gap: 6 }}
      >
        <Ionicons name={open ? 'chevron-down' : 'chevron-forward'} size={16} color={colors.navy} />
        <AppText variant="caption" weight={600} color={colors.navy}>
          How Dawat AI got this · {steps.length} {steps.length === 1 ? 'step' : 'steps'}
        </AppText>
      </Pressable>
      {open ? (
        <View style={{ backgroundColor: colors.card, borderRadius: radii.sm, padding: 10, gap: 6 }}>
          {steps.map((s) => (
            <StepRow key={s.step} s={s} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function Lines({ lines }: { lines: CardLine[] }) {
  return (
    <View style={{ gap: 4 }}>
      {lines.map((l, i) => (
        <View key={`${l.name}-${i}`} style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          {l.is_veg !== null ? <VegMark isVeg={l.is_veg} withLabel={false} /> : null}
          <AppText style={{ flex: 1 }}>
            {l.qty} × {l.name}
            {l.restaurant ? ` (${l.restaurant})` : ''}
          </AppText>
          {l.line_total !== null ? <AppText weight={600}>{rupees(l.line_total)}</AppText> : null}
        </View>
      ))}
    </View>
  );
}

function cardTitle(c: Card): string {
  switch (c.kind) {
    case 'order':
      return 'Confirm this order?';
    case 'plan':
      return c.label ? `Add “${c.label}” to your cart?` : 'Add this plan to your cart?';
    case 'diet':
      return 'Add this anyway?';
    case 'preference':
      return 'Save this preference?';
    case 'remove':
      return 'Remove from your cart?';
    case 'delivery':
      return 'Change where to deliver?';
  }
}

/**
 * A confirmation card from the backend. Yes and No send those exact words through the chat like any message. They are
 * only usable while this card is the one under the latest reply (`active`).
 */
export function CardView({ card, cardText, active, onAnswer }: { card: Card; cardText: string | null; active: boolean; onAnswer: (word: string) => void }) {
  return (
    <View
      style={{ alignSelf: 'stretch', backgroundColor: colors.butter, borderRadius: radii.md, padding: 14, gap: 10, opacity: active ? 1 : 0.7 }}
      accessibilityLabel={cardText ?? cardTitle(card)}
    >
      <AppText weight={800} variant="title">
        {cardTitle(card)}
      </AppText>
      {card.kind === 'order' || card.kind === 'plan' ? (
        <>
          <Lines lines={card.lines} />
          {card.kind === 'plan' && card.replace ? <AppText weight={700}>This replaces everything now in your cart.</AppText> : null}
          {card.kind === 'plan' && card.nonveg.length > 0 ? (
            <AppText>Includes non-veg: {card.nonveg.join(', ')}{card.saved_diet ? ` (you saved ${card.saved_diet})` : ''}.</AppText>
          ) : null}
          {card.deliver_to ? <AppText>Delivering to {card.deliver_to}</AppText> : null}
          <AppText weight={800}>Total {rupees(card.grand_total)}</AppText>
        </>
      ) : null}
      {card.kind === 'diet' ? (
        <>
          {card.items.map((i, k) => (
            <AppText key={`${i.name}-${k}`}>{i.qty} × {i.name}</AppText>
          ))}
          {card.saved_diet ? <AppText>You saved {card.saved_diet}. Is this for someone else?</AppText> : null}
        </>
      ) : null}
      {card.kind === 'preference' ? <AppText>{card.label}</AppText> : null}
      {card.kind === 'remove'
        ? card.items.map((i, k) => (
            <AppText key={`${i.name}-${k}`}>{i.qty === null ? 'All' : i.qty} × {i.name}</AppText>
          ))
        : null}
      {card.kind === 'delivery' ? <AppText>Deliver to {card.area}</AppText> : null}
      {active ? (
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Button label="Yes" onPress={() => onAnswer(YES)} style={{ flex: 1 }} accessibilityLabel={`Yes. ${cardTitle(card)}`} />
          <Button label="No" variant="secondary" onPress={() => onAnswer(NO)} style={{ flex: 1 }} accessibilityLabel={`No. ${cardTitle(card)}`} />
        </View>
      ) : (
        <AppText variant="caption" color={colors.muted}>
          This question has passed. Ask again if you still want it.
        </AppText>
      )}
    </View>
  );
}

/** Up to three plan options from this turn. Choosing one sends a message naming its label (the contract). */
export function PlanOptions({ plans, active, onPick }: { plans: PlanOption[]; active: boolean; onPick: (label: string) => void }) {
  return (
    <View style={{ alignSelf: 'stretch', gap: 10 }}>
      {plans.map((p) => (
        <View key={p.plan_id} style={{ backgroundColor: colors.card, borderRadius: radii.md, padding: 14, gap: 8, borderWidth: 1.5, borderColor: colors.sky, opacity: active ? 1 : 0.7 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <AppText weight={800} variant="title" style={{ flex: 1 }}>
              {p.label}
            </AppText>
            <AppText weight={800}>{rupees(p.grand_total)}</AppText>
          </View>
          {p.restaurants.map((r) => (
            <View key={r.branch_id} style={{ gap: 4 }}>
              <AppText weight={700}>
                {r.restaurant} · {r.branch_label}
              </AppText>
              {r.items.map((i, k) => (
                <View key={`${i.name}-${k}`} style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                  <VegMark isVeg={i.is_veg} withLabel={false} />
                  <AppText style={{ flex: 1 }}>
                    {i.qty} × {i.name}
                  </AppText>
                  <AppText weight={600}>{rupees(i.line_total)}</AppText>
                </View>
              ))}
              <AppText variant="caption" color={colors.muted}>
                Delivery {r.free_delivery ? 'free' : rupees(r.delivery_fee)} · GST {rupees(r.taxes)}
              </AppText>
            </View>
          ))}
          {p.diet_note ? <AppText variant="caption">{p.diet_note}</AppText> : null}
          {p.budget_left !== null ? (
            <AppText variant="caption" color={colors.muted}>
              {rupees(p.budget_left)} of your budget left
            </AppText>
          ) : null}
          {active ? <Button label={`Choose ${p.label}`} variant="secondary" onPress={() => onPick(p.label)} /> : null}
        </View>
      ))}
    </View>
  );
}

/** The reply said the user's yes needs payment. The button only opens the payment screen: the app pays nothing from here. */
export function PaymentNote({ total, onPay }: { total: number; onPay: () => void }) {
  return (
    <View style={{ alignSelf: 'stretch', backgroundColor: colors.sage, borderRadius: radii.md, padding: 14, gap: 8 }}>
      <AppText weight={800}>Confirmed: {rupees(total)}</AppText>
      <AppText>Next: pay with a test payment. No real money moves, and nothing is ordered until you pay.</AppText>
      <Button label={`Pay ${rupees(total)}`} onPress={onPay} />
    </View>
  );
}
