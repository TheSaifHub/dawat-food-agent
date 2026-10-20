"""consent(): is the user's latest message a clear yes? (Saif, Session 12.) Pure, no database.

The rule: a clear yes in English, Hinglish or Telugu confirms; anything negative, hesitant, questioning or unclear
does not (Dawat AI just asks again). The cases below are what users actually type, typos and all.
"""

import pytest

from app.tools.consent import MAX_LEN, consent

ENGLISH_YES = ["yes", "Yes!", "YES PLEASE", "yeah", "yep", "yup", "ok", "Okay", "okkk", "k", "sure", "confirm",
               "Confirm it", "place it", "Place the order please", "go ahead", "yes, place my order", "yesss",
               "ok bro go ahead", "sure thing", "Done", "yes confirm", "Alright, place it", "perfect, place it",
               "sounds good", "I confirm"]
HINGLISH_YES = ["haan", "haa", "Haa!", "ha", "Ha!", "HA", "ha.", "ha ji", "ha kar do", "ha bhai",   # S13: "ha" is yes
                "Haan bhai", "haan kar do", "haanji", "haan ji", "theek hai", "thik hai",
                "haan haan, kar do", "Yes!", "ok.", "theek hai।",
                "theek hai, order kar do", "kar do", "order kar do bhai", "ok hai", "chalega", "pakka", "bilkul",
                "haaan", "confirm kar do", "Haan bhai jaldi order karo"]
TELUGU_YES = ["avunu", "Avunu andi", "sare", "sare andi", "alage", "ok andi", "order pettu", "order cheyyi",
              "avunu, order pettandi", "sare anna cheyyi", "confirm cheyyi", "kaanivvu",
              "అవును", "సరే", "సరే అండి", "అవును, ఆర్డర్ పెట్టు", "ఓకే", "అలాగే"]
HINDI_SCRIPT_YES = ["हाँ", "हां", "ठीक है", "हाँ जी", "हाँ, कर दो"]

ENGLISH_NO = ["no", "No.", "nope", "nah", "not now", "wait", "ok wait", "hold on", "stop", "cancel", "yes no",
              "maybe later", "don't order", "dont", "hmm", "nooo", "yes but wait", "never mind", "not sure"]
HINGLISH_NO = ["nahi", "nahin", "nhi", "nai bhai", "mat karo", "ruko", "haan par ruko", "ek minute", "abhi nahi",
               "baad mein", "rehne do", "theek hai lekin ruko"]
TELUGU_NO = ["vaddu", "vaddu andi", "kaadu", "ledu", "aagu", "konchem aagandi", "sare, vaddu", "cheyaku",
             "వద్దు", "కాదు", "లేదు", "ఆగండి", "సరే కానీ ఆగు"]
HINDI_SCRIPT_NO = ["नहीं", "मत करो", "रुको", "हाँ, पर रुको"]

UNCLEAR = [
    "", "   ", None, 42, "👍", "please", "order", "thanks",               # empty, emoji, filler only, not text
    "yes?", "ok?", "haan?", "should I?", "is delivery free? yes",          # a question is never a yes
    "yes but add a coke", "ok and remove the raita", "yes make it 3",      # an extra request: the cart would change
    "kar do na", "sare kaani", "what", "hello", "biryani",        # unknown or ambiguous words
    "y" * (MAX_LEN + 1), "yes " * 60,                                      # too long for a plain yes
    # Session 12 rule-breaker: every one of these was read as yes by the first version
    "yes？", "haan؟", "yes⁇", "yes‽", "yes ¿", "yes﹖", "yes;",              # question marks in other scripts
    "ok 👎", "yes ❌", "ok 🙅", "yes 🛑", "yes :(", "yes :)", "ok 👍",        # emoji and emoticons: unclear
    "ha ha ha", "ha ha", "accha", "fine and", "ok i", "yes so", "sure then", "y\u200bes", "yes\u202e",
    # Session 13 (Saif): a weak "ok"-type yes plus thanks closes a chat rather than answering the summary
    "ok thanks", "Ok thanks!", "okay thank you", "ok thx", "kk thanks", "fine, thanks", "alright thank you",
    "ok andi thanks", "theek hai dhanyavad", "thik hai shukriya", "sare dhanyavadalu", "సరే ధన్యవాదాలు",
    "ठीक है धन्यवाद", "thank you", "thanks a lot",
    # D-046 (third rule-breaker run): acknowledgements with a weak yes, a trailing "…", a real word read as a typo
    "accha theek hai", "ok cool", "ok nice", "ok great", "accha ok", "ok you", "ok…", "ok...", "pace it",
    # D-046 verification run: an ellipsis with spaces, or a trailing comma or dash, still trails off
    "ok. . .", "ok . . .", "haan. . .", "yes . .", "theek hai. . .", "ok,,,", "ok —", "ok-", "haan… kar do",
]


@pytest.mark.parametrize("message", ENGLISH_YES)
def test_english_yes(message):
    assert consent(message)["consent"] == "yes", consent(message)


@pytest.mark.parametrize("message", HINGLISH_YES)
def test_hinglish_yes(message):
    assert consent(message)["consent"] == "yes", consent(message)


@pytest.mark.parametrize("message", TELUGU_YES)
def test_telugu_yes(message):
    assert consent(message)["consent"] == "yes", consent(message)


@pytest.mark.parametrize("message", HINDI_SCRIPT_YES)
def test_hindi_script_yes(message):
    assert consent(message)["consent"] == "yes", consent(message)


@pytest.mark.parametrize("message", ENGLISH_NO + HINGLISH_NO + TELUGU_NO + HINDI_SCRIPT_NO)
def test_negative_or_hesitant_is_no(message):
    assert consent(message)["consent"] == "no", consent(message)


@pytest.mark.parametrize("message", UNCLEAR)
def test_anything_else_is_unclear(message):
    result = consent(message)
    assert result["consent"] == "unclear", result


def test_the_words_behind_the_answer_are_reported():
    r = consent("haan bhai, kar do")
    assert r == {"consent": "yes", "yes_words": ["han", "kar do"], "no_words": [], "other_words": [], "typos": []}
    r = consent("yes but add a coke")
    assert r["consent"] == "unclear" and r["other_words"] == ["but", "ad", "a", "coke"]


@pytest.mark.parametrize("message", ["yeah yeah", "Yeah yeah!", "yes yes", "ok ok", "haan haan", "sare sare"])
def test_a_repeated_yes_is_still_yes(message):
    # Saif, Session 13: "yeah yeah" is yes. ("ha ha" is the exception: laughter.)
    assert consent(message)["consent"] == "yes", consent(message)


# Saif, Session 13: a strong yes plus thanks is still yes; only the weak "ok / fine" family is weakened by it.
STRONG_YES_WITH_THANKS = ["yes thanks", "Yes, thank you!", "haan thanks", "haan shukriya", "avunu thanks",
                          "avunu dhanyavadalu", "అవును ధన్యవాదాలు", "हाँ धन्यवाद", "sure, ty", "confirm, thanks",
                          "ha thanks", "place it thanks", "ok yes thanks", "order pettu thanks", "kar do thanks bhai"]


@pytest.mark.parametrize("message", STRONG_YES_WITH_THANKS)
def test_a_strong_yes_with_thanks_is_yes(message):
    assert consent(message)["consent"] == "yes", consent(message)


def test_weak_yes_with_thanks_reports_the_thanks():
    assert consent("ok thanks") == {"consent": "unclear", "yes_words": ["ok"], "no_words": [],
                                    "other_words": ["thanks"], "typos": []}
    assert consent("yes thanks") == {"consent": "yes", "yes_words": ["yes"], "no_words": [], "other_words": [], "typos": []}
    assert consent("ok")["consent"] == "yes"                         # without thanks, a weak yes is still a yes


def test_a_thank_you_never_hides_a_no():
    for message in ("no thanks", "nahi shukriya", "vaddu dhanyavadalu", "ok thanks, wait"):
        assert consent(message)["consent"] == "no", message


def test_no_always_wins_over_yes():
    for yes in ("yes", "haan", "avunu", "sare", "ok"):
        for no in ("wait", "nahi", "vaddu", "cancel"):
            assert consent(f"{yes} {no}")["consent"] == "no"
            assert consent(f"{no} {yes}")["consent"] == "no"


@pytest.mark.parametrize("message", ["replace it", "haan, replace kar do", "yes replace the cart", "sare replace chey"])
def test_replace_phrases_count_only_where_they_are_asked_for(message):
    from app.tools.consent import REPLACE_YES
    assert consent(message, also_yes=REPLACE_YES)["consent"] == "yes", message
    assert consent(message)["consent"] == "unclear", message          # never a yes to placing an order


def test_replace_phrases_never_beat_a_no():
    from app.tools.consent import REPLACE_YES
    for message in ("replace it, wait", "replace mat karo", "don't replace", "vaddu replace"):
        assert consent(message, also_yes=REPLACE_YES)["consent"] == "no", message


def test_word_lists_do_not_overlap():
    from app.tools.consent import FILLER, NO, REPLACE_YES, THANKS, WEAK_YES, YES
    assert WEAK_YES < YES                                              # every weak yes is a yes; not every yes is weak
    tables = [YES, NO, FILLER, THANKS, REPLACE_YES]
    assert all(not a & b for i, a in enumerate(tables) for b in tables[i + 1:])


def test_diet_answers_count_only_for_the_diet_question():
    from app.tools.consent import DIET_YES
    for message in ("for my friend", "dost ke liye", "haan, friend kosam"):
        assert consent(message, also_yes=DIET_YES)["consent"] == "yes", message
        assert consent(message)["consent"] != "yes", message                  # never a yes to ordering
    assert consent("no, for my friend", also_yes=DIET_YES)["consent"] == "no"    # a no still wins


@pytest.mark.parametrize("message, hesitant", [("hmm", True), ("wait", True), ("ruko", True), ("ok wait", True),
                                               ("no", False), ("nahi", False), ("no wait", False), ("vaddu", False)])
def test_hesitation_is_told_apart_from_refusal(message, hesitant):
    from app.tools.consent import only_hesitation
    said = consent(message)
    assert said["consent"] == "no" and only_hesitation(said) is hesitant, (message, said)


def test_the_new_word_lists_do_not_overlap_the_old_ones():
    from app.tools.consent import DIET_YES, FILLER, HESITATION, NO, THANKS, YES
    assert HESITATION <= NO and not DIET_YES & (YES | NO | FILLER | THANKS)


# ─── only unambiguous messages, and typos (Saif, Session 16: D-040, then D-045) ─────────────────────────
# D-045 dropped the D-040 "strong yes": any word besides yes phrases, filler and repaired typos makes a message
# unclear, a restaurant or dish name included. The LLM intent check (D-043) then asks one natural question.
WITH_OTHER_WORDS = [
    "haan saudi arebian rest wala order palce kardo.",          # Saif's own message: one confirming question now
    "haan saudi wala order place kar do", "yes, place my order from Mehfil", "haan bhai Paradise wala order kar do",
    "avunu, Annapurna order pettu", "ok, Hi-Tech Bawarchi order confirm kar do", "yes please place the ordr from Kritunga",
    "haan Shah Ghouse ka order kardo", "sare, Kritunga order pettandi", "yes confrim the order from Pista House",
    # the D-044 re-run (BR-1 to BR-3): names, areas and "harmless" filler hid a change
    "haan Paneer Biryani order kar do", "ok confirm the order at my office", "yes place the order at kondapur",
    "haan order kar do for one", "yes place it for my friend", "haan biryani wala order kar do",
]
TYPO_YES = ["order palce kardo", "haan order palce kardo", "yes place the ordr please", "ok confrim the order",
            "haan plce kardo", "yes cofirm the order", "haan, order palce kardo bhai"]
STILL_UNCLEAR = [
    "haan order kar do aur ek coke add karo", "yes but place the order", "haan 2 biryani ka order kar do",
    "should I place the order", "haan order kar do kya", "yes place the order tomorrow", "haan Mehfil wala",
    "saudi wala order place kardo", "haan, saudi arebian rest wala",
    "haan order kar do, address change karo", "yes, which order will you place", "ok place the order instead",
    "haan order kar do, extra raita bhi", "haan saudi wala order place kar do?",
]
STILL_NO = ["avunu, order cheykandi", "sare, order cheyakndi",        # one typo from both "do it" and "don't": a no
            "yes place the order or wait", "haan order cancle karo", "haan, order mat karo", "yes place the order, wiat", "haan order kar do, nahii",
            "haan order kar do, vadu", "yes place the order later", "haan Mehfil wala order kar do, ruko"]


@pytest.mark.parametrize("message", WITH_OTHER_WORDS)
def test_any_other_word_makes_a_yes_unclear(message):
    r = consent(message)
    assert r["consent"] == "unclear" and r["other_words"] and "strong" not in r, r


@pytest.mark.parametrize("message", TYPO_YES)
def test_typos_in_order_words_are_repaired(message):
    r = consent(message)
    assert r["consent"] == "yes" and r["typos"], r


@pytest.mark.parametrize("message", STILL_UNCLEAR)
def test_a_change_a_question_or_a_number_keeps_it_unclear(message):
    assert consent(message)["consent"] in ("unclear", "no"), consent(message)   # never yes


@pytest.mark.parametrize("message", STILL_NO)
def test_no_still_wins_even_misspelled(message):
    assert consent(message)["consent"] == "no", consent(message)


def test_one_unknown_word_next_to_any_yes_phrase_is_never_yes():
    """D-045, the rule itself: every yes phrase plus one word from outside the word lists → never yes."""
    from app.tools.consent import YES
    extra = ["mehfil", "office", "kondapur", "paneer", "two", "for", "one", "friend", "wala", "tonight", "x"]
    tried = 0
    for phrase in YES:
        for word in extra:
            for message in (f"{' '.join(phrase)} {word}", f"{word} {' '.join(phrase)}"):
                tried += 1
                assert consent(message)["consent"] != "yes", (message, consent(message))
    assert tried > 1000


def _typo_variants(word: str) -> set[str]:
    out = set()
    if len(word) >= 2:
        out.add(word[1] + word[0] + word[2:])                            # first two letters swapped
    out.add(word[:-1])                                                   # last letter dropped
    out.add(word + word[-1] + "x")                                       # a stray letter added at the end
    return {v for v in out if v != word}


def test_no_misspelled_no_word_ever_makes_a_yes():
    """Every NO word, misspelled three ways, dropped into an order yes: never a yes."""
    from app.tools.consent import _NO_WORDS
    tried = 0
    for word in _NO_WORDS:
        for variant in _typo_variants(word):
            for message in (f"haan {variant} order place kar do", f"yes place the order {variant}"):
                tried += 1
                assert consent(message)["consent"] != "yes", (word, variant, consent(message))
    assert tried > 100


def test_question_specific_answers_are_never_an_order_yes():
    assert consent("haan dost ke liye")["consent"] == "unclear"         # a diet answer is not an order yes
    assert consent("haan replace kar do")["consent"] == "unclear"       # nor is a replace answer


@pytest.mark.parametrize("message", ["umm ok", "uh, yes", "हम्म ठीक है", "హ్మ్ సరే", "ఉమ్ సరే", "ek second, haan",
                                     "one second, ok", "erm yes"])
def test_hesitation_sounds_in_any_script_are_hesitation(message):
    from app.tools.consent import only_hesitation
    said = consent(message)
    assert said["consent"] == "no" and only_hesitation(said), (message, said)
