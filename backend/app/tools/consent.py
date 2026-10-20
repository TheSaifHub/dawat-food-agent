"""Is the user's latest message a clear yes? (Saif, Session 12.) The second lock on confirm_cart from chat.

The first lock is the quote (D-026): confirm_cart confirms exactly the summary the user was shown. This one checks
the user actually said yes to it. The agent runtime (Phase 6) passes the user's latest message, taken from the
conversation, never from the LLM; the LLM can't talk its way past this by deciding the user "meant" yes.

    consent(message) → {"consent": "yes" | "no" | "unclear", "yes_words", "no_words", "other_words"}

Rules, in order (anything not clearly yes is refused; a refusal only means Dawat AI asks again):
  · empty, over 200 characters, a question (a question mark in any script: ? ？ ؟ ¿ ‽ ⁇), or any emoji or
    symbol beyond plain punctuation ("ok 👎", "yes :(", "yes ❌": the words say yes, the rest may not)  → unclear
  · any negative or hesitation word or phrase, in any language ("ok wait", "haan par ruko", "sare, vaddu")  → no
  · at least one yes phrase, and every other word is harmless filler ("please", "bro", "andi", "ji")   → yes
  · anything else: an extra request ("yes but add a coke"), an unknown word ("kar do na"), only filler,
    laughter ("ha ha"), a message cut off mid-sentence ("ok i", "fine and"), or a thank-you whose only yes
    is a weak "ok"-type word ("ok thanks", "theek hai dhanyavad")                                    → unclear
(Session 12 rule-breaker: full-width and Urdu question marks, "no" emoji, "ha ha ha", "accha" and "ok i" were all
read as yes by the first version.)
Typos are repaired first. A word one letter away from a NO word becomes that NO word ("cancle" → cancel). Towards
an order word only an explicit list of common misspellings is used (TYPOS: "palce" → place, "ordr" → order,
"confrim" → confirm), never fuzzy matching: fuzzy repair turned "pettakandi" (don't place it) into "place it".
Saif, Session 16 (D-045): the rules accept ONLY unambiguous messages: yes phrases, harmless filler and repaired
typos ("haan, order palce kardo bhai"). Any other word, a restaurant name included, makes the message unclear, and
the LLM intent check (D-043) asks one natural question instead. The D-040 "strong yes" (a yes word plus an order
command with other words between) was dropped: two rule-breaker runs showed every allow-list of "harmless" other
words hides a change ("haan Paneer Biryani order kar do", "ok confirm the order at my office").
Saif, Session 13: "yeah yeah" is yes (a repeated yes is still a yes). A plain "ha" (and "Ha!") is yes: it's the
most common Hinglish yes; only "ha ha" is laughter. "ok thanks" is unclear: an "ok"-type word plus thanks usually
closes a conversation ("ok, thanks for the info") rather than answering the summary. A strong yes plus thanks is
still yes ("yes thanks", "haan thanks", "avunu thanks").
English, Hinglish and Telugu (Latin letters and Telugu script), plus Hindi in Devanagari. Words are compared after
squeezing repeated letters, so "yesss", "okkk" and "haaan" count, and "nooo" is still no.
"""

import re
import unicodedata

from rapidfuzz.distance import DamerauLevenshtein

from app.text import tokens

MAX_LEN = 200
# Punctuation a plain yes may carry ("Yes!", "ok.", "haan, kar do", "theek hai।"). Anything else that isn't a
# letter, digit, combining mark, space or a zero-width (non-)joiner makes the message unclear.
PLAIN_PUNCTUATION = set(".,!'’‘-–—…।")
JOINERS = {"\u200c", "\u200d"}


def _plain(message: str) -> bool:
    for c in message:
        if c.isalnum() or c.isspace() or c in PLAIN_PUNCTUATION or c in JOINERS:
            continue
        if unicodedata.category(c).startswith("M"):
            continue
        return False
    return True


# A message that trails off is never a yes (D-046): an ellipsis anywhere, written as "…" or as dots with or without
# spaces ("ok..", "ok. . ."), or a trailing comma or dash ("ok,,,", "ok —"). The verification run found "ok. . ."
# read as a plain yes by the earlier two-pattern check.
TRAILING_OFF = re.compile(r"…|\.\s*\.|[,\-–—]\s*$")


def _question(message: str) -> bool:
    return any("QUESTION" in (name := unicodedata.name(c, "")) or "INTERROBANG" in name for c in message)


def _squeeze(word: str) -> str:
    out = []
    for c in word:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def _phrases(*texts: str) -> set[tuple[str, ...]]:
    return {tuple(_squeeze(w) for w in tokens(t)) for t in texts}


YES = _phrases(
    # English
    "yes", "yeah", "yea", "yep", "yup", "ya", "yah", "ok", "okay", "okey", "okie", "k", "kk", "sure", "alright",
    "confirm", "confirmed", "i confirm", "proceed", "go ahead", "do it", "place it", "place order", "place the order",
    "place my order", "order it", "book it", "done", "fine", "lets go", "let's do it", "sounds good", "looks good",
    "go for it", "sure thing",
    # Hinglish
    "haan", "haa", "ha", "han", "hanji", "haanji", "haan ji", "ji haan", "theek hai", "thik hai", "theek h", "thik h",
    "ok hai", "chalega", "chalo", "kar do", "kardo", "kar dijiye", "karo", "order kar do", "order karo",
    "confirm kar do", "confirm karo", "pakka", "bilkul",
    "order kardo", "order kar dijiye", "order place kar do", "order place kardo", "order place karo", "place kar do",
    "place kardo", "place karo", "confirm kardo", "confirm it", "confirm order", "confirm the order", "confirm my order",
    "book order", "book the order",
    # Telugu (Latin letters)
    "avunu", "avnu", "aunu", "sare", "sari", "alage", "alaage", "ok andi", "cheyyi", "cheyandi", "chey",
    "order chey", "order cheyyi", "order cheyandi", "order pettu", "order pettandi", "pettu", "pettandi",
    "confirm chey", "confirm cheyyi", "confirm cheyandi", "kaanivvu", "kanivvu",
    # Telugu script
    "అవును", "సరే", "ఓకే", "అలాగే", "చేయి", "చేయండి", "ఆర్డర్ చేయి", "ఆర్డర్ చేయండి", "ఆర్డర్ పెట్టు",
    "పెట్టు", "కానివ్వు",
    # Hindi (Devanagari)
    "हाँ", "हां", "हा", "जी हाँ", "हाँ जी", "ठीक है", "कर दो", "कर दीजिए", "ओके", "पक्का", "बिल्कुल",
)

NO = _phrases(
    # English
    "no", "nope", "nah", "not", "dont", "do not", "never", "wait", "hold", "hold on", "stop", "cancel", "later",
    "nevermind", "never mind", "negative", "maybe", "hmm", "hm", "unsure", "not sure", "dont order", "rethink",
    "didnt", "cant", "cannot", "wont", "wouldnt", "shouldnt", "refuse", "forget", "forget it", "scratch that",
    "skip", "abort", "kidding", "just kidding", "jk", "joking", "nay", "holdon", "hang on", "one sec", "brb",
    "on second thought", "wrong chat",
    # Hinglish (Session 16 rule-breaker)
    "na karo", "na kar", "ni karo", "ni krna", "ni karna", "nhi karna", "mt", "mt karo", "mazak", "mazaak",
    "galti", "chodo", "jaane do", "jane do", "ek sec", "ni ni",
    # Telugu, Latin letters (Session 16 rule-breaker)
    "oddu", "vaddule", "akkarledu", "apu", "aapu", "aapandi", "pettakandi", "pettakunda", "cheyakunda",
    "oka nimisham",
    # hesitation sounds and pauses (D-046 verification run: "umm ok", "हम्म ठीक है", "హ్మ్ సరే", "ek second, haan")
    "um", "uh", "erm", "uhm", "hmmm", "हम्म", "हं", "హ్మ్", "ఉమ్", "ek second", "ek sec", "one second", "one minute",
    "just a sec", "a sec", "sec", "1 sec", "1 min",
    # Hinglish
    "nahi", "nahin", "nai", "nhi", "mat", "mat karo", "ruko", "ruk", "rukiye", "ruko zara", "ek minute", "ek min",
    "baad mein", "baad me", "abhi nahi", "cancel karo", "rehne do", "rahne do",
    # Telugu (Latin letters)
    "vaddu", "vadhu", "voddu", "vaddhu", "kaadu", "kadu", "ledu", "aagu", "agu", "aagandi", "agandi", "aagi",
    "konchem aagu", "taruvatha", "tarvata", "cheyaku", "cheyakandi", "pettaku",
    # Telugu script
    "వద్దు", "కాదు", "లేదు", "ఆగు", "ఆగండి", "ఆగి", "చేయకు", "చేయకండి", "తర్వాత",
    "ఒద్దు", "వద్దులే", "అక్కర్లేదు", "ఆపు", "ఆపండి", "చెప్పలేదు", "పెట్టకండి",
    # Hindi (Devanagari)
    "नहीं", "नही", "ना", "मत", "रुको", "रुकिए", "बाद में",
)

FILLER = _phrases(
    "please", "pls", "plz", "plss", "kindly", "bro", "bhai", "boss", "sir", "madam", "dude", "man", "yaar", "ji",
    "andi", "anna", "akka", "ra", "babu", "the", "it", "this", "that", "my", "order", "now",
    "abhi", "jaldi", "ippudu",
    "జీ", "అండి", "ప్లీజ్", "जी", "प्लीज़", "भाई",
)

# Thank-you words: harmless next to a strong yes ("yes thanks"), but with only a weak yes they make the message
# unclear ("ok thanks" closes a chat; it doesn't answer the summary). Saif, Session 13.
THANKS = _phrases(
    "thanks", "thank you", "thank", "thx", "thnx", "thanx", "tq", "ty", "tysm", "dhanyavad", "dhanyavaad",
    "shukriya", "dhanyavadalu", "dhanyavaadalu", "ధన్యవాదాలు", "धन्यवाद", "शुक्रिया",
)

# Acknowledgements (D-046, third rule-breaker run): like a thank-you, harmless next to a strong yes ("perfect, place
# it") but with only a weak yes they acknowledge rather than answer ("ok cool", "accha theek hai").
ACK = _phrases("cool", "great", "perfect", "nice", "good", "awesome", "super", "all set", "accha", "acha", "achha")

# The weak yeses: the "ok / fine" family in each language, which also just acknowledges. Every other yes is strong.
WEAK_YES = _phrases(
    "ok", "okay", "okey", "okie", "k", "kk", "fine", "alright", "ok hai", "ok andi", "theek hai", "thik hai",
    "theek h", "thik h", "chalega", "sare", "sari", "alage", "alaage", "సరే", "ఓకే", "అలాగే", "ठीक है", "ओके",
)

# Extra yes phrases that only count as an answer to "replace your cart with this plan?" (add_plan_to_cart). Never
# a yes to placing an order: "replace it" in reply to an order summary would mean something else entirely.
REPLACE_YES = _phrases(
    "replace", "replace it", "replace the cart", "replace my cart", "replace cart", "go with the plan",
    "replace kar do", "replace karo", "replace kardo", "replace chey", "replace cheyyi", "replace cheyandi",
)

# Extra yes phrases that only count as an answer to "You've saved vegetarian, is this for someone else?" (D-039).
# Negation-shaped phrases ("not for me", "mere liye nahi") were removed after the Phase 6 rule-breaker: "not for me,
# thanks" is a polite decline (D-044).
DIET_YES = _phrases(
    "for someone else", "its for someone else", "for a friend", "for my friend", "for my friends", "its for my friend",
    "its for a friend", "for my brother", "for my sister", "for my wife", "for my husband", "for my family",
    "for my mom", "for my dad", "for my son", "for my daughter", "for my kids", "for my colleague",
    "dost ke liye", "friend ke liye", "bhai ke liye", "ghar walon ke liye",
    "kisi aur ke liye", "friend kosam", "naa friend kosam", "vere vallaki",
)

# Extra yes phrases that only count as an answer to a remove card ("Remove Raita ×2 from your cart?", D-046).
REMOVE_YES = _phrases(
    "remove", "remove it", "remove them", "yes remove", "hatao", "hata do", "nikalo", "nikal do", "teeseyi",
    "teeseyandi", "తీసేయి", "తీసేయండి", "हटाओ", "हटा दो",
)

# Hesitation, not refusal: "hmm", "wait", "ruko". For ordering these are a no (don't place it); for a question like
# the diet one they only mean "not yet", so the question is asked again (Saif, Session 16).
HESITATION = _phrases(
    "um", "uh", "erm", "uhm", "hmmm", "हम्म", "हं", "హ్మ్", "ఉమ్", "ek second", "ek sec", "one second", "one minute",
    "just a sec", "a sec", "sec", "1 sec", "1 min",
    "wait", "hold", "hold on", "hmm", "hm", "maybe", "later", "unsure", "not sure", "rethink", "ruko", "ruk", "rukiye",
    "ruko zara", "ek minute", "ek min", "baad mein", "baad me", "aagu", "agu", "aagandi", "agandi", "aagi",
    "konchem aagu", "taruvatha", "tarvata", "ఆగు", "ఆగండి", "ఆగి", "తర్వాత", "रुको", "रुकिए", "बाद में",
)
assert HESITATION <= NO


def only_hesitation(said: dict) -> bool:
    """True when a "no" from consent() is only hesitation words (no real refusal like "no", "nahi", "vaddu")."""
    return said["consent"] == "no" and all(tuple(w.split()) in HESITATION for w in said["no_words"])


_KNOWN = {w for table in (YES, NO, FILLER, THANKS, ACK, REPLACE_YES, DIET_YES, REMOVE_YES) for phrase in table
          for w in phrase}
# Common misspellings of order words, repaired exactly (never fuzzy: see the module docstring).
TYPOS = {_squeeze(k): _squeeze(v) for k, v in {
    "palce": "place", "plce": "place", "plac": "place", "pleace": "place", "plase": "place",
    "ordr": "order", "oder": "order", "odrer": "order", "ordre": "order", "oredr": "order", "orderr": "order",
    "confrim": "confirm", "confirn": "confirm", "cofirm": "confirm", "comfirm": "confirm", "confim": "confirm",
    "cnfirm": "confirm", "confrm": "confirm", "krdo": "kardo", "kro": "karo"}.items()}
# Only single-word NO phrases: the other words of a NO phrase ("abhi" in "abhi nahi", "sure" in "not sure", "order"
# in "dont order") aren't negative on their own (the property test in test_consent.py found this).
_NO_WORDS = sorted({phrase[0] for phrase in NO if len(phrase) == 1 and len(phrase[0]) >= 4 and phrase[0].isascii()})


def _near(word: str, target: str) -> bool:
    return DamerauLevenshtein.distance(word, target) <= (1 if len(target) <= 6 else 2)


# Real words that are one or two letters from a NO word but mean nothing negative ("should" ~ "shouldnt"): never
# repaired. (D-046: questions are now scanned for NO words too, so "should I?" would have become a no.)
NOT_TYPOS = {"should", "could", "would"}


def _repair(word: str) -> str:
    """A known misspelling of an order word is fixed exactly (TYPOS). Otherwise an unknown word one typo away from a
    NO word becomes that NO word (a doubt is never lost). Nothing else is changed."""
    if word in TYPOS:
        return TYPOS[word]
    if word in _KNOWN or word in NOT_TYPOS or len(word) < 4 or not word.isascii():
        return word
    for target in _NO_WORDS:
        if _near(word, target):
            return target
    return word


_LONGEST = max(len(p) for p in YES | NO | FILLER | THANKS | ACK | REPLACE_YES | DIET_YES | REMOVE_YES)
assert WEAK_YES <= YES


def consent(message, also_yes: frozenset | set = frozenset()) -> dict:
    """`also_yes`: extra yes phrases for one specific question (REPLACE_YES, DIET_YES); NO still wins over them."""
    yes = YES | also_yes if also_yes else YES
    out = {"consent": "unclear", "yes_words": [], "no_words": [], "other_words": [], "typos": []}
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_LEN:
        return out
    # A question, an emoji, or a trailing "…" is never a yes, but its NO words still count (D-046: "for someone
    # else? no, it's for me" hid the "no" from the rules, so a wrong classifier yes could add meat).
    doubtful = _question(message) or not _plain(message) or bool(TRAILING_OFF.search(message))
    words = []
    for w in (_squeeze(t) for t in tokens(message)):
        fixed = _repair(w)
        if fixed != w:
            out["typos"].append([w, fixed])
        words.append(fixed)
    thanks = []
    i = 0
    while i < len(words):
        for size in range(min(_LONGEST, len(words) - i), 0, -1):      # longest phrase first; NO before YES
            chunk = tuple(words[i:i + size])
            hit = next((name for name, table in (("no_words", NO), ("yes_words", yes), ("thanks", THANKS | ACK),
                                                 (None, FILLER)) if chunk in table), False)
            if hit is not False:
                if hit == "thanks":
                    thanks.append(" ".join(chunk))
                elif hit:
                    out[hit].append(" ".join(chunk))
                i += size
                break
        else:
            out["other_words"].append(words[i])
            i += 1
    if out["no_words"]:
        out["consent"] = "no"
    elif doubtful:
        pass
    elif out["yes_words"].count("ha") > 1:                              # "ha ha": laughter, not a yes
        pass
    elif out["yes_words"] and not out["other_words"]:
        if thanks and all(tuple(w.split()) in WEAK_YES for w in out["yes_words"]):
            out["other_words"] = thanks                                  # "ok thanks": an acknowledgement
        else:
            out["consent"] = "yes"
    return out
