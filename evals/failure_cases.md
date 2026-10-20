# Dawat AI: documented failure cases

A required deliverable (CLAUDE.md). Every case here was seen in a recorded run. Phase 10 extends this file.

**Result files:** `evals/results/phase6_*.json`. Each one records the prompt version and the models, plus the model that answered each turn.

## Fixed

### F-1 · An English question got a Hinglish reply
- **Seen:** prompt v1, run `2026-10-04T181019Z`, case `category-only`.
- **What happened:** "Show me only the biryanis at Hi-Tech Bawarchi in Madhapur" got "Hi-Tech Bawarchi ke do branches hain Madhapur mein…". The earlier live checks in 6c/6d showed the same thing (an English question answered in Telugu or Hinglish).
- **Likely cause:** the Indian restaurant and area names pulled the model's language choice.
- **Fix:** prompt v2 adds one line to Rule 1: names never decide the language; only the user's own words do.
- **After:**
  - v2 full run: 12 of 12 English checks passed;
  - `category-only` repeated 3 times: English every time;
  - fragile-case repeats: 9 of 9 English checks passed.

### F-2 · The model tried to confirm the order after "ok thanks"
- **Seen:** prompt v1, run `2026-10-04T181019Z`, case `ok-thanks-is-not-a-yes`.
- **What happened:** after the cart summary, the user said "ok thanks", and the model called `confirm_cart`.
- **No harm done.** The code gate refused it (`no_clear_yes`, D-030 addendum), no order was placed, and the model showed the summary again. This is exactly why consent is checked in code and not only in the prompt.
- **Why the eval first missed it:** the case only checked that no order was placed. It now also expects `confirm_cart` not to be called.
- **Fix:** prompt v2 says a thank-you or acknowledgement is not a yes to ordering; ask "Shall I place the order?" instead.
- **After:** v2 full run, plus 3 repeats: no `confirm_cart` call, reply "Shall I place the order?".

## Fixed in code (Session 16)

### F-3 · A restaurant name is sometimes misspelled ("Annapura" for "Annapurna")
- **Seen:**
  - the 6e live run (Hinglish);
  - run `2026-10-04T181941Z`, case `ok-thanks-is-not-a-yes`, repeat 2 of 3 (English).
- **Model:** Gemini 3.5 Flash-Lite. Prompt v1 and v2 both say "names stay exactly as the tools give them".
- **Impact:** the price shown was right and the cart line was right, since it's added by id. It's still a credibility problem: the name on screen doesn't match the menu.
- **Detected by:** the `names_spelled` check (fuzzy ≥ 85 but not exact).
- **Rate so far:** "Annapurna" appeared in about 8 replies across the runs and was misspelled in 2.
- **Fix (Saif chose option 3, D-041):** before a reply is shown, code replaces near-miss restaurant names with the exact name from the tool results. It never touches numbers, and each fix is logged as a `name_correction` trace. The model still misspells sometimes; the user no longer sees it.

### F-4 · "Order cancelled" after a no, while the cart still had the item (Saif's own test)
- **Seen:** Saif's chat, Session 15: "Order cancel kardiya hai".
- **Fix (D-041):** prompt v3 plus `confirm_cart`'s own answer to a no say the order was NOT placed and the items are still in the cart.
- **After:** evals `no-keeps-the-cart` and `nahi-keeps-the-cart-hinglish`, 2/2.

### F-5 · A saved vegetarian was sold meat without a question; a typo'd Hinglish yes was refused (Saif's own test)
- **Fix:** D-039 (saved diet in plans, plus an ask-once check enforced in code) and D-040 (the strong yes with typo repair).
- **After:** evals `saved-veg-*` and `typo-yes-with-restaurant-name` pass.

### F-6 · The model copied an English example sentence to Telugu-script and Hinglish users (D-043)
- **Seen:** run `065553Z`. The `confirm_intent` guidance contained an English template, and the reply to "సరే, ఆర్డర్ పెట్టండి" came back in English.
- **Fix:** guidance without templates: use the user's language and script, and echo their words. After the fix, the Telugu-script question came back in Telugu script (2/2).
- **Lesson:** text inside tool results steers the model's language as strongly as the prompt does.

### F-7 · After `confirm_intent`, the model called `place_order` anyway (D-043)
- **Seen:** one run of `intent-telugu-script-order`. Code refused it (`not_confirmed`); no order was placed.
- **Fix:** the guidance says not to call `confirm_cart` or `place_order` again that turn. After the fix, 2/2 repeats passed.

## Behaviour by design, worth knowing (not a model failure)

### B-1 · A cheap "Best value" dinner can be tiffin
- **Seen:** `hinglish-group-plan`, ₹1,000 for 4 in Kondapur. Best value was ₹324 for Idli + Medu Vada + Sambar from a tiffin place in Gachibowli.
- **Why:** the planner's D-028 rules count tiffin as a proper meal main, and no spice preference was stated.
- **Where to decide:** that's the planner rules (Saif, Phase 5), not the agent.

## Limits of this eval (why passing it is not proof)
- **Small and mostly short:** 20 conversations, 31 turns, nearly all single-topic. Phase 10 grows it to 50+.
- **One model answered every turn** (Flash-Lite). The 3.8 Flash and Groq fallbacks were tested live once each (D-034 to D-036), not run through these cases.
- **The checks are heuristics:**
  - "English only" is a word list;
  - name spelling is fuzzy matching;
  - number grounding accepts any number that appears in any tool result of the conversation (or the user's own words), so a real number attached to the wrong dish passes.
- **Some behaviour isn't checked yet:** whether "the cheapest one" really was the cheapest; whether every menu item was listed; whether a typo correction was mentioned.
- **Gemini runs at temperature 1.0,** so one pass says little. The fragile cases were repeated 3 times; more repeats need more of the free quota (Saif's AI Studio limits are still to be checked).
