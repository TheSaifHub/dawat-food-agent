"""Phase 2, module 2b: write the dedupe review file for Saif (D-010). Removes nothing.

Takes the pairs that D-010 (Option 2) does NOT auto-merge, i.e. 15–50 m apart or a generic
name, from results/cleaning/dedupe_candidates.csv, and adds Claude's pre-filled suggestion
and a one-line reason. Saif fills `saif_decision` with merge / keep_both for every row.

Output: data/reference/dedupe_review.csv
Refuses to overwrite the file once any saif_decision has been filled in.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\make_dedupe_review.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "results" / "cleaning" / "dedupe_candidates.csv"
OUT = ROOT / "data" / "reference" / "dedupe_review.csv"

# (name_a, name_b, distance_m) → (suggestion, reason). Reasons come from the tags of both records.
SUGGESTIONS = {
    ("Fast Food", "Fast Food", "3.1"): ("keep_both", "Generic name; same survey day but different payment/Wi-Fi tags → likely two stalls side by side"),
    ("Kabab restaurant", "Kabab", "3.7"): ("merge", "Only 3.7 m apart and neither record has any other detail; generic name but almost certainly one place"),
    ("Vistara", "Vistara", "15.3"): ("merge", "Same name 15 m apart; one record has a full Kukatpally address, the other only a check date → one place mapped twice"),
    ("Kahani Cafe", "Kahani Cafe", "15.9"): ("merge", "Pin + building outline with the identical address (Plot 13, Nagarjuna Nagar Colony, Mansoorabad)"),
    ("Cafe Coffee Day", "Cafe Coffee Day", "16.0"): ("merge", "Two brand-tagged CCD records 16 m apart; two real outlets that close is implausible"),
    ("Paradise", "Paradise", "16.3"): ("merge", "Two bare 'Paradise' pins 16 m apart with no other tags; nothing suggests two outlets"),
    ("Domino's", "Domino's", "17.7"): ("merge", "Two brand-tagged Domino's 18 m apart; two real outlets that close is implausible"),
    ("Paradise Cafe", "Paradise Hotel", "19.1"): ("merge", "Same Paradise site (hotel has wikidata Q7134282): cafe counter + main restaurant → one ordering branch. YOUR CALL: one branch or separate counters"),
    ("Nilofer Cafe", "New Nilofer", "22.3"): ("keep_both", "'New' usually marks a different business; no other tags to prove they're the same"),
    ("The Study Sip", "THE STUDY SIP", "23.5"): ("merge", "Both very detailed (41/46 tags), same postcode 500085 and JNTU location → one café mapped by two people"),
    ("Bawarchi", "Bawarchi", "23.9"): ("keep_both", "The phone-numbered Bawarchi vs a bare 'cuisine=indian' record; 'Bawarchi' is used by unrelated places → not enough to merge"),
    ("Paradise Takeaway", "Paradise Hotel", "24.7"): ("merge", "Takeaway-only counter of the same Paradise site → one ordering branch. YOUR CALL (same as the cafe row)"),
    ("Eat street", "Eat Street", "25.9"): ("merge", "Pin + building outline of the same name; neither has other details"),
    ("Paradise Takeaway", "Paradise Cafe", "25.9"): ("merge", "Completes the Paradise site trio (takeaway + cafe); decide together with the two rows above"),
    ("Fast Food", "Fast Food", "31.1"): ("keep_both", "Generic name; different Wi-Fi/payment tags → separate stalls"),
    ("Fast Food", "Fast Food", "32.8"): ("keep_both", "Generic name; different Wi-Fi tags → separate stalls"),
    ("Coronation Cafe", "Coronation Cafe", "39.8"): ("keep_both", "40 m apart and neither record has any detail to confirm they're the same"),
    ("laya", "laya restaurant", "43.2"): ("keep_both", "Two separate building outlines 43 m apart; no evidence they're one restaurant"),
    ("Bawarchi", "Bawarchi", "45.6"): ("keep_both", "Same situation as the 23.9 m row: bare 'cuisine=indian' record vs the phone-numbered one"),
    ("Bawarchi", "Bawarchi", "45.9"): ("merge", "Identical phone (+91 40 27634490), cuisine list and opening hours → one restaurant mapped twice"),
    ("Sai Darshini", "Sai Darshini", "48.2"): ("keep_both", "Near the 50 m limit and a common name; details differ but don't prove it's one place"),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if OUT.exists():
        with OUT.open(encoding="utf-8-sig", newline="") as f:
            if any(r.get("saif_decision", "").strip() for r in csv.DictReader(f)):
                print(f"Refusing to overwrite {OUT.relative_to(ROOT)}: Saif has started filling saif_decision.")
                return 1

    with CANDIDATES.open(encoding="utf-8-sig", newline="") as f:
        review = [r for r in csv.DictReader(f) if r["option_2_close_means_same"] == "keep"]

    rows, missing = [], []
    for i, r in enumerate(review, 1):
        s = SUGGESTIONS.get((r["name_a"], r["name_b"], r["distance_m"]))
        if s is None:
            missing.append((r["name_a"], r["name_b"], r["distance_m"]))
            continue
        kind = "generic" if r["chain_core_name"] in ("fast food", "kabab") else ("exact" if r["same_exact_name"] == "True" else "core")
        rows.append({"pair": i, "name_a": r["name_a"], "name_b": r["name_b"], "distance_m": r["distance_m"],
                     "match": kind, "types": r["types"], "tags_a": r["tags_a"], "tags_b": r["tags_b"],
                     "suggestion": s[0], "reason": s[1], "saif_decision": "", "osm_a": r["a"], "osm_b": r["b"]})
    if missing or len(rows) != len(SUGGESTIONS):
        print(f"Suggestions don't match the review pairs. Missing: {missing}")
        return 1

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(rows)} pairs "
          f"({sum(r['suggestion'] == 'merge' for r in rows)} merge, {sum(r['suggestion'] == 'keep_both' for r in rows)} keep_both suggested). Nothing removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
