import { useCallback, useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Screen } from '@/components/Screen';
import { AppText } from '@/components/AppText';
import { Chip } from '@/components/Chip';
import { Bubble, CardView, Notice, PaymentNote, PlanOptions, StepsSummary, ThinkingPanel } from '@/components/ChatParts';
import { useChat } from '@/lib/chat-context';
import { useCart } from '@/lib/cart';
import { MAX_MESSAGE_CHARS } from '@/lib/chat';
import { MIN_TARGET, colors, radii } from '@/theme/tokens';

const TRY = ['Biryani for 2, less spicy', '₹500, spicy, veg for 2', 'What is in my cart?'];

export default function ChatScreen() {
  const { messages, sending, slow, liveSteps, send, stop, actionableId } = useChat();
  const { refresh } = useCart();
  const router = useRouter();
  const [draft, setDraft] = useState('');
  const scroller = useRef<ScrollView>(null);

  // Leaving the screen stops the stream (the backend may still finish the turn; the chat provider re-reads the cart).
  // Coming back reads the cart again too. The callback is stable on purpose: if it changed while a turn was running,
  // React would run its cleanup and stop that turn.
  const latest = useRef({ stop, refresh });
  useEffect(() => {
    latest.current = { stop, refresh };
  });
  useFocusEffect(
    useCallback(() => {
      void latest.current.refresh();
      return () => latest.current.stop();
    }, []),
  );

  const submit = (text: string) => {
    if (sending || !text.trim()) return;
    setDraft('');
    void send(text);
  };
  const empty = messages.length === 0 && !sending;

  return (
    <Screen scroll={false}>
      <AppText variant="display" weight={800} accessibilityRole="header">
        Dawat AI
      </AppText>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scroller}
          style={{ flex: 1 }}
          contentContainerStyle={{ gap: 10, paddingVertical: 8 }}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: true })}
        >
          {empty ? (
            <View style={{ gap: 10 }}>
              <AppText color={colors.muted}>Tell Dawat AI what you are craving. Nothing is ordered until you say yes.</AppText>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {TRY.map((t) => (
                  <Chip key={t} label={t} selected={false} onPress={() => submit(t)} />
                ))}
              </View>
            </View>
          ) : null}

          {messages.map((m) => {
            if (m.role === 'notice') return <Notice key={m.id} text={m.text} tone={m.tone} />;
            if (m.role === 'user') return <Bubble key={m.id} m={m} />;
            const active = m.id === actionableId;
            return (
              <View key={m.id} style={{ gap: 8 }}>
                <Bubble m={m} />
                {m.card ? <CardView card={m.card} cardText={m.cardText} active={active} onAnswer={submit} /> : null}
                {m.plans && m.plans.length > 0 ? <PlanOptions plans={m.plans} active={active} onPick={(label) => submit(`Go with ${label}`)} /> : null}
                {m.payment ? <PaymentNote total={m.payment.grand_total} onPay={() => router.push('/payment')} /> : null}
                <StepsSummary steps={m.steps} />
              </View>
            );
          })}
          {sending ? <ThinkingPanel steps={liveSteps} slow={slow} /> : null}
        </ScrollView>

        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, paddingBottom: 8 }}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Message Dawat AI"
            placeholderTextColor={colors.muted}
            accessibilityLabel="Message Dawat AI"
            multiline
            maxLength={MAX_MESSAGE_CHARS}
            editable={!sending}
            style={{
              flex: 1,
              minHeight: MIN_TARGET,
              maxHeight: 120,
              borderRadius: radii.md,
              backgroundColor: colors.card,
              paddingHorizontal: 16,
              paddingVertical: 10,
              color: colors.ink,
              fontSize: 15,
              borderWidth: 1.5,
              borderColor: colors.navy,
            }}
          />
          {sending ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Stop"
              onPress={stop}
              style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, borderRadius: radii.pill, backgroundColor: colors.card, borderWidth: 1.5, borderColor: colors.navy, alignItems: 'center', justifyContent: 'center' }}
            >
              <Ionicons name="stop" size={20} color={colors.navy} />
            </Pressable>
          ) : (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Send"
              accessibilityState={{ disabled: !draft.trim() }}
              disabled={!draft.trim()}
              onPress={() => submit(draft)}
              style={{ minHeight: MIN_TARGET, minWidth: MIN_TARGET, borderRadius: radii.pill, backgroundColor: colors.navy, alignItems: 'center', justifyContent: 'center', opacity: draft.trim() ? 1 : 0.55 }}
            >
              <Ionicons name="arrow-up" size={22} color={colors.white} />
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
