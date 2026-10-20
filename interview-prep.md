# Dawat — Interview Prep (rolling)

Q&A grounded in what was actually built or decided. Updated every session.

---

## Session 1 — Phase 0 (Setup)

### Environment and dependencies
**Q: Why did you pin every dependency, including sub-dependencies?**
A: Reproducibility. An unpinned `fastapi` can install a different version next month and break the app with no code change. We froze exact versions from `pip freeze` (Python) and used a lockfile plus `save-exact` (npm), so local and Render installs match. Updates are deliberate: bump, test, commit.

**Q: Why Python 3.11 when 3.13 was available?**
A: 3.11 has the widest prebuilt-wheel support across our stack (pandas, numpy, rapidfuzz, LiteLLM, the MCP SDK), which matters on Windows where a missing wheel means compiling from source. Render supports pinning 3.11, and we needed no newer language features. The choice is logged in DECISIONS.md with the rejected alternative.

**Q: Why two requirements files?**
A: `requirements.txt` is what production installs; `requirements-dev.txt` adds test tools. A smaller production install is faster to build, has a smaller attack surface, and makes it clear what the app actually needs.

### Backend and CORS
**Q: What is CORS, and why not just allow `*`?**
A: Browsers stop a page from one origin reading responses from another unless the server allows that origin. With `*`, any website could make a visitor's browser call our API. For an app that manages carts and places orders, only our frontend should be able to do that. We read an explicit allow-list from `ALLOWED_ORIGINS`, so adding the Vercel URL is a config change, not a code change.

**Q: Does CORS protect your server?**
A: No, and that's a common misconception. In testing, a request with `Origin: https://evil.example.com` still got HTTP 200; the server just didn't include the allow header, so a *browser* would refuse to hand the response to that page. CORS protects users' browsers from other sites. Our server is protected separately, by authentication (Supabase JWT), server-side validation and server-computed prices.

**Q: What happens if someone misconfigures `ALLOWED_ORIGINS=*` in production?**
A: The backend refuses to start. `parse_allowed_origins` raises on `*` or on an empty list, and I verified it by starting the app with `ALLOWED_ORIGINS=*`. Failing loudly at boot beats running wide open silently. The code also strips trailing slashes, because browsers send `Origin` without one and a pasted `https://x.vercel.app/` would otherwise never match.

**Q: Why `allow_credentials=False`?**
A: We'll authenticate with a bearer token in the `Authorization` header, not cookies, so the browser doesn't need to send cross-site cookies. Leaving credentials off removes a class of cross-site request risks, and it's also what makes a strict origin list simpler to reason about.

**Q: Tell me about a bug you caught in setup.**
A: Copying `.env.example` unchanged into `.env` set `ALLOWED_ORIGINS=` to an empty string. The code only fell back to the default when the variable was *missing*, so the empty value crashed the backend. The frontend had the same problem with `?? default`, since an empty string isn't nullish. I found it by testing the real workflow (copy the example, start the app) rather than trusting the code. The fix was to treat blank as unset, and I added tests for it.

### Frontend and secrets
**Q: How do you keep API keys out of the browser?**
A: Two rules. First, every secret (Supabase secret key, database URL, Gemini/Groq keys, Razorpay key secret) lives only in the backend's env; the frontend env file has no secret slots at all. Second, only `NEXT_PUBLIC_*` variables reach the browser, and Next.js bakes them into the JS bundle at build time, so they're treated as public by definition. The only values there are designed to be public: the API URL, the Supabase publishable key (safe because Row Level Security restricts it) and the Razorpay test key ID (useless without the secret).

**Q: Why does the health check run in the browser rather than on the server?**
A: A server-side fetch from Next.js to FastAPI doesn't go through CORS at all, so it would pass even if CORS were misconfigured. Running it as a client component makes the demo exercise the same path real users' browsers will take.

### Tooling and safety automation
**Q: How did you make sure an AI coding assistant followed your project rules?**
A: Written rules depend on memory, so I enforced the critical ones with Claude Code hooks: a Python guard that runs before every shell or file tool call. It blocks git commands, any write into the read-only raw-data folder, content that looks like a secret (API key formats, JWTs, Postgres URLs with passwords, long literals assigned to SECRET/TOKEN variables), and any read of real `.env` files, so secrets never enter the conversation. Permission deny rules back up the `.env` block as a second layer.

**Q: How did you test the guard, and what are its limits?**
A: 72 test cases in both directions: what must be blocked, and lookalikes that must pass (`.gitignore`, `os.environ`, `.env.example`, reading raw data). The fake keys in the tests are assembled at runtime so the test file itself contains no secrets. I also scanned every existing project file for false positives. The tests caught a real gap: a key embedded mid-line wasn't detected at first. It fails *closed* if it crashes. Its limit is honest: it's pattern matching, so it prevents mistakes, not a determined attacker. The raw-data rule is reinforced by a write-once fetch script and an OS read-only flag.

### Data sourcing (decided, not yet built)
**Q: What data risk did you find before fetching anything?**
A: The spec's Overpass query selects areas named "Hyderabad". That name also matches **Hyderabad, Pakistan**, and the Indian district boundary may exclude major food hubs like Gachibowli, Madhapur and HITEC City, which fall under the wider GHMC boundary. So the first Phase 1 step is a tiny query that lists every matching boundary before the real fetch. Garbage in the raw file would poison every later phase.

### System design (planned; these answers describe the design intent until the code exists)
**Q: Why will totals be computed on the server, never taken from the client or the LLM?**
A: The client can be tampered with, and the LLM can hallucinate numbers. Prices come from the database; items plus delivery fee plus taxes are computed by backend code. The Razorpay order is created with that server amount, and the payment signature is verified before an order exists. *(To be built in Phases 4 and 8.)*

**Q: Why does the LLM extract constraints but code does the maths?**
A: LLMs are good at understanding "₹500, two people, one veg, spicy" in any language, and unreliable at guaranteeing arithmetic and hard rules. So the LLM outputs a strict JSON schema validated by Pydantic, and deterministic code builds and checks the meal combinations, with property-based tests proving no plan breaks a rule. *(Phase 5.)*

---

## Session 2 — Phase 1 (data sourcing)

**Q: How did you define "Hyderabad" for your dataset, and why does it matter?**
A: The spec matched OSM boundaries by name, which is ambiguous: there's also a Hyderabad in Sindh, Pakistan. And the Indian *district* boundary excludes the western IT corridor (HITEC City, Gachibowli, Madhapur, Kondapur), which is one of the city's biggest food hubs. A query listed what the name matched (two Indian boundaries, admin levels 5 and 8). My collaborator inspected the level-8 relation on openstreetmap.org, and I confirmed it in code with point-in-area checks for those landmarks, plus two controls: Charminar must be inside, Hyderabad in Pakistan must be outside. We then pinned the fetch to that relation **by ID** (7868535). The district sits inside it, so it was dropped.

**Q: Why include a point that should be outside the boundary?**
A: To prove the check can fail. If every test point says "inside", you can't tell a correct boundary from a broken check that always says yes. The Pakistan control coming back "outside" is what makes the "inside" results meaningful. It's the same principle the project applies to evals: a perfect score is a red flag until you've shown the test can catch a failure.

**Q: How do you use a free, shared API like Overpass responsibly?**
A:
- Check the status endpoint for a free slot before querying.
- Send one request per job, with a descriptive User-Agent, and never retry in a loop.
- Pause between requests, and scope expensive queries (a worldwide name scan timed out, so I limited it to a regional bounding box).
- Fetch once and cache the result to disk; the app never calls Overpass live.
- When the server returned 504s, stop and try again at a quieter time rather than hammering it.

**Q: How do you make sure the raw data file is trustworthy?**
A:
- **Write-once:** the fetch script refuses to run if a snapshot exists.
- **Complete, not partial:** it rejects responses carrying an Overpass `remark`, because Overpass can return HTTP 200 with a timeout remark and partial data. It also rejects an empty result.
- **Unaltered:** it saves the server's bytes unchanged, writing to a temp file first so a crash can't leave half a file.
- **Recorded:** a sidecar `.meta.json` holds the exact query, endpoint, fetch time, OSM data timestamp, element count and SHA-256 fingerprint.
- **Protected:** both files are marked read-only, and a Claude Code hook blocks tool writes into the raw folder.

Every later cleaning step is code that re-runs from that file.

**Q: An HTTP 200 means success, right?**
A: Not always. Overpass can answer 200 OK but include a `remark` like "runtime error: Query timed out", with only some of the data. If you save that as your dataset, every statistic downstream is silently wrong. The fetch script treats a remark as a failure and saves nothing.

**Q: Your safety hook blocked a harmless action. Is that a problem?**
A: It's the trade-off of a pattern-based guard. It blocked a shell command that appended notes to a log file, because the text mentioned the raw-data folder alongside a file-operation word, and a regex can't tell prose from commands. I chose to fail on the safe side, used a tool that checks the actual target path instead, and logged tightening the rule as a follow-up. I'd rather have an occasional false positive than a guard so loose it misses a real write to raw data.

---

## Session 3 — guard precision and fallback servers

**Q: How did you fix the guard's false positive without opening a hole?**
A: The guard matched words anywhere in a shell command, so notes *about* the raw folder looked like writes *to* it. "Ignore quoted text" would have been wrong, because `python -c "open('data/raw/x','w')"` is a real write inside quotes. Instead I strip text only where it's provably data: heredoc bodies fed to `cat`/`tee`, and quoted `echo`/`printf` arguments. The redirect target is always kept, so `cat > data/raw/x <<EOF` is still blocked. Heredocs piped to `bash` or fed to `python -` count as code, and the secret scan still reads everything. Each new "allowed" case has "still blocked" counterparts in the tests. 86 tests pass, and the new ones caught an extra edge case (a `;` inside quotes) before it shipped.

**Q: How do you choose a fallback for a flaky external service?**
A: Make sure it's actually independent. Our planned fallback, `overpass.kumi.systems`, turned out to be a DNS alias of `overpass.private.coffee`, the same machine that had already failed as our first fallback. Two hostnames, one server, so trying it would just have hit the same overloaded box again. Now I check DNS (address and aliases) before counting something as a separate fallback. I also treat a failed status check as a hard stop: the data request only goes out when the server says it has capacity.

**Q: `curl` printed `HTTP 000`. What does that tell you?**
A: That there was no HTTP response at all. `-sS` showed the reason: error 28, a timeout. Timing (`-w "%{time_connect}"`) showed the TCP connection opened in 0.2 s, so the network and DNS were fine and the server simply never answered. That points to an overloaded server rather than a blocked or unreachable one, which changes the right response: wait, don't debug your network.

---

## Session 4 — Phase 1: profiling, chains, charts, audited insights

**Q: What did profiling tell you that changed your plan?**
A: That OSM has essentially no neighbourhood information for Hyderabad restaurants: `addr:suburb` is on 0 of 1,538 food places. The only area-like tag (2%) holds district or state names. The spec assumed we'd take areas from tags first. Now nearly every branch's area will be derived from its coordinates by snapping to the nearest locality, which makes the locality reference list one of the most important inputs in the project. Profiling before cleaning is what surfaced that.

**Q: How did you detect restaurant chains without merging the wrong places?**
A:
- I normalised names (case, punctuation, "&"), then built a "core name" by ignoring generic words like hotel, restaurant and cafe. A chain is a core name at 2+ places: 113 chains covering 32.4% of named places.
- Crucially, it's **counting only**. A naive "contains 'paradise'" search finds 21 places, including unrelated ones like "Hotel Persis Paradise". The core-name rule finds 15.
- Everything in between (120 ambiguous names, 42 possible misspellings) goes into a review file for a human, because some fuzzy matches are plainly wrong ("Ananya Food Court" vs "Chaitanya Food Court").
- Merges happen in Phase 2 through a reviewed mapping file, never blind fuzzy matching.

**Q: Why not just use OSM's `brand` tag for chains?**
A: It's reliable only for international chains: Domino's 33 of 34, KFC 23 of 23. The local chains in the top 15 (Paradise, Kritunga, Bawarchi, Mehfil) have zero brand tags. Relying on it would miss exactly the Hyderabad brands the demo is about.

**Q: How do you know your branch counts aren't inflated by duplicates?**
A: I don't yet, and the doc says so. 39 same-name pairs sit within 50 m of each other. 12 of them are a map pin plus a building outline, which often means one place drawn twice, but none has been checked by hand. So they're flagged as candidates, and the dedupe rule is a Phase 2 decision with a logged count.

**Q: How did you make sure the numbers in your data insights document were true?**
A:
- **Every number is traceable:** it comes from a field in JSON files that the profiling scripts write, and each script verifies the raw file's SHA-256 before reading it.
- **An independent auditor re-checks it:** a read-only `data-auditor` sub-agent traces every number to its field *and* recomputes the key ones from the raw file with its own code. Checking the doc only against my own pipeline's output would be circular; a pipeline bug would pass.
- **The first audit failed.** All 46 numbers were right, but it flagged 8 overclaims:
  - "54 PIN codes" were really 54 raw strings, only 50 valid PINs
  - "international chains are clean" skipped Pizza Hut's 7 of 11
  - an unverified duplicate interpretation was stated as fact
- **I fixed them, added the new numbers to the JSON first, and re-audited to PASS.** The lesson: correct numbers can still be wrapped in misleading sentences, so audit the claims, not just the arithmetic.

**Q: This mirrors your eval philosophy. How?**
A: Same principle as "a perfect eval score is a red flag". A check has to be able to fail. The boundary check had a Pakistan control that had to come back "outside"; the auditor recomputes from raw instead of trusting the pipeline; and its first verdict was FAIL, which is evidence it's actually checking. I'll apply the same to the agent evals: break something on purpose and confirm the eval catches it.

**Q: How did you choose chart colours?**
A: By job, not taste. The three place types are categorical identities, so each got a fixed colour used identically across every chart. I validated the set with a colour-blind simulation script: worst separation ΔE 9.2 against a target of 8 or more. One colour (café aqua) is below 3:1 contrast on the background, so every chart also names the types in text. Colour never carries meaning alone. And I rendered and looked at every chart, which caught a legend hiding data points.

**Q: Why pin a separate requirements file for the data pipeline?**
A: The pipeline needs pandas and matplotlib; the deployed backend doesn't. Keeping them separate keeps the Render build small and makes it clear what production depends on. One catch: a before/after `pip freeze` diff missed `packaging`, which matplotlib needs but pytest had already installed. I checked each new package's declared requirements to pin those too; otherwise a fresh install would float to whatever version is newest that day.

---

## Sessions 5–6 — Phase 2: cleaning and enrichment

**Q: How did you decide which restaurants are branches of the same chain?**
A:
- A human-reviewed mapping, not fuzzy matching. A script proposes candidates: names containing a chain's core name, or a close spelling. Each gets a suggestion and a reason. Saif decides every row, and 194 rows are recorded with who decided.
- The principle is "when unsure → separate". OSM doesn't record ownership. Wrongly calling an independent "Bawarchi" a branch of another "Bawarchi" misrepresents a real business, and makes the agent ask a misleading "which branch?" question.
- A missed grouping only loses one branch option. So "Bawarchi" (it means "cook") is not a brand, but "Green Bawarchi" at 4 places is.

**Q: You have three different "be careful" rules that point in different directions. Isn't that inconsistent?**
A: No. Each rule picks the less harmful error for its field.
- **Chain grouping:** separate when unsure.
- **Duplicates:** keep both when unsure (Niloufer, 112 m apart).
- **Vegetarian flags:** mark veg-only when unsure, because a synthetic chicken dish on a real vegetarian restaurant breaks the one promise a veg user relies on, while the reverse only narrows a menu.

The principle is the same; the costs differ.

**Q: How do you assign an area when 0% of places have a suburb tag?**
A:
- The fallback is the nearest of 170 well-known area points, which gives a median 582 m.
- Address tags are used first, but only if they name a known area (with typo tolerance) *within 3 km of the pin*. That guard rejected 4 tags, such as "Secunderabad" on places 5.5 km away, where it's being used as a postal city.
- I'm open about the limitation: for 97.8% of branches the area is geometric, not an address. The agent should say "near Madhapur", not claim a precise address.

**Q: How does the pipeline guarantee a vegetarian restaurant never shows meat?**
A:
- **Phase 2 flags it:** a restaurant is veg-only if any branch has `diet:vegetarian=only` or a veg name keyword (Udupi, Pure Veg, Darshini…), unless a branch is tagged non-veg. That gives 36.
- **Phase 3 enforces it:** the menu validator will fail the build if a veg-only restaurant gets a non-veg item.
- **The audit caught a typo:** "Raghavedndra Vegitarian" slipped past an exact keyword. I widened the pattern and noted the limitation: name-based flags are never complete, so the audit step stays.

**Q: How do you know your cleaning is reproducible and your checks actually work?**
A:
- **Reproducible:** the pipeline reruns end to end from the read-only raw snapshot. The log records the sha256 of every input and output, and a rerun reproduced them byte for byte.
- **Checks that can fail:** the post-checks (no undecided rows, reviewed merges applied, keep-both pairs intact, no same-brand pair within 15 m left) were fed deliberately broken inputs. All 4 were caught.

It's the same philosophy as the evals: a check you've never seen fail isn't evidence of anything.

**Q: Why stable ids derived from OSM instead of auto-increment ids?**
A: So the database seed is idempotent. `b-n675646784` always means the same OSM place, so rerunning the pipeline and seed updates rows instead of creating duplicates, and carts or orders referencing a branch don't break after a re-seed. It also keeps attribution traceable to the OSM object.

**Q: What did you deliberately leave out of the output?**
A: Phone numbers, emails and operator names that some OSM records carry. The demo doesn't need them, and republishing real contact details in a simulated ordering app would be irresponsible. We keep only what the product uses: name, location, area, cuisine, street and postcode, plus the OSM id for attribution.

**Q: What's the biggest data limitation going into menu generation?**
A: 35% of restaurants (394) have no cuisine tag and no name clue, so they default to "Multi-cuisine" and will get a generic Hyderabad menu. It's documented rather than hidden. Guessing cuisines from nothing would be fabricating facts about real businesses.

---

## Session 7 — Phase 3: synthetic menus, database, guards

**Q: Why synthetic menus, and how did you keep them realistic without an LLM call?**
A:
- **Why synthetic:** no free, licensable source has real Hyderabad menus, and scraping platforms is off-limits.
- **How realistic:** a reviewed dish catalogue with prices set once in a file, instead of generated at build time.
  - 319 dishes, each with a Hyderabad price range, veg flag, spice level, serves, category and course.
  - Cuisine templates list the core dishes, optional dishes and menu size.
  - A seeded script builds 1,112 menus from those files, and the output is byte-identical on rerun.
- **Coherent pricing:** each restaurant gets one price level. Budget names ("…Tiffins", "…Point") sit low, chains mid-to-upper, "Grand"/"Palace" high. So Chicken Dum Biryani runs ₹250 at budget places, ₹310 standard, ₹350 at chains and ₹390 at premium places.
- **Checked before anyone saw them:** I showed sample menus to a human before generating everything.

**Q: How do you guarantee a vegetarian is never shown meat?**
A: Four layers:
1. **Catalogue:** egg counts as non-veg. The checker fails if a dish marked veg has a meat or egg word in its name.
2. **Generator:** veg-only restaurants only draw veg dishes.
3. **Validator:** independently fails on any non-veg item on any of the 37 veg-only menus.
4. **Database:** triggers refuse a non-veg dish on a veg-only menu, refuse flipping a dish on such a menu to non-veg, and refuse flipping a restaurant with chicken to veg-only.

I proved each one by trying to break it.

**Q: Why store dishes and aliases once instead of on each menu item?**
A:
- Duplicated data drifts apart. If 23,780 menu items each carried their own `is_veg` and alias list, one bad copy could mark a chicken dish as veg on one menu.
- With `menu_items (restaurant, dish, price)` referencing `dishes` and `dish_aliases`, a menu item physically can't disagree with its dish.
- A `unique(alias_norm)` constraint guarantees that an alias like "kodi biryani" resolves to exactly one dish.
- It also cuts the data size: aliases are stored 1,815 times, instead of roughly 135,000 (an estimate: 23,780 items × about 5.7 aliases each).

**Q: How does the confirmation gate work, and why also in the database?**
A:
- **In the tools layer:** `place_order` refuses unless the cart is confirmed. The agent can only confirm after an explicit "yes".
- **In the database:** a trigger refuses any order whose cart isn't `confirmed`, belongs to another user, or has no items from that branch. A second trigger locks cart items once the cart is confirmed, so nothing can be slipped in after the "yes".
- **Why both:** tool code has bugs, and an LLM might find an unexpected path. The database is the last layer that can't be argued with. I tested it: an unconfirmed-cart order and an item added after the yes were both refused, while a correct order went through.

**Q: How do you make sure order totals are right?**
A:
- The backend computes totals from `menu_items` prices at order time, never from the client or the LLM.
- Carts store no prices.
- The database re-checks two things. A CHECK constraint: `grand_total = items_total + delivery_fee + taxes`. A deferred constraint trigger that runs at commit: `items_total` must equal the sum of the order's items. It's deferred because the order and its items are inserted in the same transaction.
- A deliberately wrong total was refused with "items add up to 700, but items_total is 999".

**Q: Supabase has Row Level Security. Why do you still scope queries in the backend?**
A:
- Our FastAPI backend connects directly to Postgres as the table owner, and Postgres exempts owners from RLS.
- The browser gets no table privileges at all (auto-expose off plus explicit revokes), so the only path to data is the backend.
- The backend takes the user id from the verified Supabase JWT, checked against the project's public JWKS keys, never from the LLM or the request body.
- RLS policies ("own rows only") are still on every user table as a second layer, in case something is ever exposed.

**Q: How did you make database changes safe?**
A:
- Plain SQL migrations, run by a small runner with three modes: plan, `--test` and `--apply`.
- `--test` runs everything in one transaction and rolls back. It proves the SQL works on the real database with nothing committed. It caught a real bug: a trigger name clashing with an auto-generated constraint name.
- Applied files are recorded with a hash, and editing one stops the run.
- The seed script upserts in one transaction and never deletes. Stale rows are reported, because deleting data needs a human decision.

**Q: How do you know your tests actually test something?**
A:
- Every checker was broken on purpose: 10 ways for the templates, 14 for the menu validator, 13 for the database guards. The tests had to fail for the *right* reason.
- The guard tests also include positive controls, like placing a correct order. A guard that blocks everything would pass every "must refuse" test.
- That's exactly how I caught a bug in my own harness. The correct order was refused, and the wrong-total case had been refused for the wrong reason. Reading the refusal reason, not just pass/fail, exposed it.

**Q: What would you do differently at real scale?**
A:
- Real menus from restaurant partners, not synthetic ones, with prices in paise and GST rules per item.
- Menu versions, so an order points at the exact price it was bought at.
- A proper migration tool (Alembic or Supabase CLI) with down-migrations in CI.
- A read replica for search.
- Branch-level menus and availability instead of one shared chain menu.

## Session 8 — Phase 4: sign-in, area resolution, restaurant search, menus

**Q: How does your agent know which user it's acting for? Couldn't the LLM just pass a different user id?**
A:
- No. The user id never comes from the LLM, the request body or a query parameter.
- It comes only from the `sub` claim of a Supabase login token the backend has verified: ES256 signature against the project's public JWKS keys, a pinned algorithm, issuer, audience `authenticated`, expiry and role.
- Tools take `user_id` as a parameter the *server* fills in, and in Phase 6 the agent's tool schemas won't even contain it.
- A test sends `?user_id=<someone else>` and an `X-User-Id` header and proves they're ignored.

**Q: Your backend connects to Postgres as the owner, which bypasses RLS. Isn't that dangerous?**
A:
- It means RLS isn't the protection on that path; the code is. So every query on user data filters by the verified user id, and tests will prove one user can't read or change another's cart or orders.
- The browser has no table access at all, and RLS stays on as a second layer.
- The trade-off: one trusted backend path with tested scoping, instead of the LLM-driven backend talking to the database with per-user credentials.

**Q: Which JWT attacks did you defend against, and how do you know the defences work?**
A:
- Covered: unsigned `alg: none` tokens, algorithm confusion (HS256 "signed" with the public key), tampered payloads, tokens from another key or project, the anon/service roles, anonymous sessions, expired tokens, and missing claims.
- Each has a test that signs tokens with a throwaway key, so no network is needed.
- To prove the tests bite, I planted 7 bugs (accept HS256, skip audience, skip role, trust a query param…) and each one failed a test.
- One honest detail: with HS256 allowed, PyJWT itself still blocked the confusion attack, but by crashing with a 500. My allow-list is a second layer that also keeps the response a clean 401.

**Q: How do you test against a real cloud database without polluting it?**
A:
- Each test runs inside one transaction that's always rolled back.
- The fixture also counts rows in all 11 user-owned tables before and after, and fails if anything leaked.
- I chose the real Supabase database over a local Postgres because the triggers and constraints are the real ones, and it needs no install.
- One lesson: the leftovers check was 22 queries per test to Mumbai. Combining it into one query cut the suite from 81 s to 19 s.

**Q: A user types "madhapoor" or "Shamirpet". What does Dawat do, and why?**
A:
- Areas resolve in a fixed order:
  - city words → ask for an area
  - two places verified outside our boundary → "we don't deliver there"
  - exact name or alias → fine
  - edit-distance 88+ with a clear lead → resolve and mention it
  - 80–87 → ask "Did you mean Madhapur?"
  - anything else → "unknown", with suggestions
- The thresholds came from measuring real typos and about 90 real local place names we don't cover.
- The data showed an overlap band: "madhapoor"→Madhapur scores 82, but so does "Shamirpet"→Shaikpet, a different town. My first rule would have shown Shaikpet restaurants to someone in Shamirpet.
- Where the data can't separate the cases, the user decides. That's the "LLM talks, code decides" principle applied to fuzzy matching: the code knows when it doesn't know.

**Q: How do you handle chains with many branches, and different restaurants with the same name?**
A:
- The search returns `needs_choice` + `choices` (branch id, area, street) whenever more than one branch *or* same-named place fits the best match, e.g. 12 Paradise branches, or 6 unrelated "Hot Chips".
- It returns `selected_branch_id` only when exactly one fits.
- The agent rule "ask which area before showing a menu" is therefore backed by a field the code computes, not by the LLM's judgment.

**Q: Why not just use Postgres full-text or trigram search for restaurant names?**
A:
- Trigram similarity on raw names is dominated by common words: "hotel mehfil" scored Hotel Marjaan as high as Mehfil, and "mehfil restaurant" ranked Trupthi Restaurant first.
- I compare only the *distinctive* words (generic and food words stripped from both sides), in a compact form without spaces or apostrophes ("mc donalds" = "McDonald's"), in tiers: exact → contains → typo of the whole name → typo of a word.
- The data is small and static (1,112 restaurants), so it's cached in memory and the rules are unit-testable.

**Q: What does "the tests pass" actually prove here?**
A:
- Assertions go back to the database, not to the tool's own output:
  - returned branches must exist and belong to that restaurant;
  - "near the area" is recomputed in SQL;
  - a random-filter test checks that items obey every filter *and* that the result equals an independent SQL query.
- Mutation testing found 4 weak spots in the first version: no tie case, no boundary price, no unavailable item, no check that generic words are stripped from names. Each got a test, and all 15 planted bugs are now caught.
- One "caught" mutation was really a syntax error in the mutation itself. It was rewritten, and that exposed the Shamirpet bug.

## Session 9 — Phase 4: dish search, fees and the cart

**Q: How does Dawat understand "rendu kodi biryani karam kam under 300 in Madhapur"?**
A:
- Code parses it in a fixed order, and every step came from a measured probe:
  1. Is the whole thing a dish name or alias?
  2. Take out the price ("under 300") and the area ("in Madhapur").
  3. Drop chat words.
  4. Check for a dish name again, then take out quantity ("rendu" = 2) and group size.
  5. Read diet and spice phrases ("karam kam" = not spicy).
  6. Fix clear typos.
  7. Require every remaining word in one dish's name or alias, after translating kodi → chicken.
- The result is structured: dish ids, quantity 2, max_spice 1, max_price 300, area Madhapur. The tool then reads real items and prices from the database.
- In Phase 6 the LLM will pass the user's words and its own filters; code decides what matches.

**Q: Why not just fuzzy-match the whole query against dish names?**
A:
- I measured it on 61 real queries and it was wrong in ways that matter: "keema samosa" (meat) matched the veg Samosa at 90, "karam kam" (less spicy) matched Ghee Karam Idli, and "biryani" matched one dish instead of the category.
- A score measures letters, not meaning. Now every word must be accounted for in a single dish, and typos are corrected one word at a time.

**Q: How do you stop a typo fix from changing the meaning?**
A:
- **Chat words.** I scored 87 ordinary chat words against the food vocabulary. "andar" (inside) scored 89 against "anda" (egg), and "panir" 89 against "pani" (water), as high as real typos. So chat words are removed and never corrected, and common misspellings are added as data.
- **Thresholds, as for areas:** 88+ with no rival of a different meaning is fixed and reported; 80–87, or a tie, asks "did you mean…?".
- **Ties fail safe.** "vegg" is equally close to veg and egg, so it reads as veg: that can only narrow results, never show egg to a vegetarian.

**Q: How do you guarantee a vegetarian request never returns meat?**
A:
- Diet words are never matched against dish names, because "veg thali" is literally inside "non veg thali". They become an `is_veg` filter applied in code.
- An explicit filter and the text's diet are combined so they only get stricter: veg from either side wins.
- Tests send vegetarian requests in 9 forms (Telugu script, a typo, a conflicting `is_veg=false`) and re-read every result's flag from the database.
- A planted "drop the veg filter" bug was caught.

**Q: Why are totals computed on the server, and how?**
A:
- The browser and the LLM can be wrong or manipulated, so prices are never stored in the cart or accepted from a caller. `view_cart` reads them live from the menu.
- One pure function, `app/pricing.py`, computes everything:
  - ₹25 delivery up to 2 km, plus ₹10 per extra km started; free from ₹499 per restaurant;
  - 5% GST on food and 18% on delivery;
  - integer maths, rounded half up per restaurant.
- The agent is told to quote `grand_total` exactly and never add things up itself.
- The meal planner will use the same function, so "₹500 budget" is checked against the real total including fees and tax.

**Q: Why round GST per restaurant and not on the whole cart?**
A:
- Each restaurant becomes its own order with its own `taxes` column, and the database checks that `grand_total = items + delivery + taxes`.
- Rounding per restaurant makes the cart total exactly the sum of the orders. Rounding once on the cart would leave a ₹1 gap somewhere: the two-restaurant example is ₹617, not ₹616.

**Q: What does property-based testing add over normal tests?**
A:
- Hypothesis generates hundreds of random carts and checks rules that must hold for every one: totals add up, fees are never negative, GST is within half a rupee of the exact value, and further never costs less.
- It's the same idea the meal planner will use to prove its hard rules.

**Q: What happens if the user changes the cart after saying "yes"?**
A:
- Any change (an item, or the delivery point, which changes the fee) reopens the cart and returns `confirmation_cleared`, so the agent must show the new total and ask again.
- A database trigger also refuses changing a confirmed cart's delivery point. Even a bug in the tools can't alter what the user agreed to.

**Q: Why a maximum delivery distance?**
A:
- The approved formula had no limit. In our data the median branch-to-area distance is 11 km (about ₹115 delivery) and the longest 42.6 km (₹435).
- Saif chose an 8 km cap: the cart refuses to add from further away, and items that end up too far after a delivery change are flagged and not billed, just like unavailable items.

**Q: How do you know one user can't touch another user's cart?**
A:
- The backend connects as the table owner, so row-level security doesn't protect it. Every cart query is therefore scoped by the user id from the verified token, and no cart tool even accepts a cart id.
- Tests check that two users' carts stay separate, that removing an item never touches another user's cart, and that another user's address id is answered like a missing one.
- Planted bugs that dropped the user filter were caught.

**Q: Your tests passed first time. Did you trust that?**
A:
- No. After each module I planted bugs on purpose (18 in dish search, 18 in the cart, 3 for the range) and checked each one made a test fail.
- The misses were the valuable part:
  - One showed the demo addresses sit exactly on their area centres, so "ignore the address" changed nothing. A new test moves an address 3 km.
  - Another, "a number inside a dish name taken as quantity", led to a test that found two real bugs ("2 pc chicken please" lost its 2; "chicken biryani 2 persons", an alias of the Full plate, became a group size). After the fix, the guard had become dead code, which the same planted bug proved again.


## Session 10 — Phase 4: the confirmation gate, preferences, API routes

**Q: How does the confirmation gate work, end to end?**
A:
- `view_cart` returns a `quote_id`, a fingerprint of everything on the summary: lines, prices, fees, GST, the delivery point and the total.
- The agent shows that summary and needs a clear "yes". Only then does it call `confirm_cart(cart_id, quote_id)`, which confirms *that* quote and refuses if the cart changed (`stale_quote`).
- `place_order` refuses unless the cart is confirmed, then recomputes the fingerprint. If anything differs, it orders nothing, reopens the cart and returns the new total so the user is asked again.
- The database is a second layer: a trigger refuses any order from an unconfirmed cart, and a check makes "confirmed" impossible without the recorded quote.

**Q: Why fingerprint the quote instead of comparing totals?**
A:
- Totals can match while the agreement changed: one item +₹10 and another −₹10, or an address moved 50 m with the same fee.
- My first tests compared totals in effect, and two planted bugs passed for exactly that reason. Both are now tests.

**Q: How do you stop the agent from saving a preference the user never asked for?**
A:
- Every write declares a source: chat_request, chat_confirmed or settings. The database refuses a row without one.
- A chat write must quote the user's words, and code checks they appear as whole words in the user's latest message. The runtime, not the LLM, supplies that message.
- No other code may write preferences: a test scans the codebase, and another runs a full order to check nothing changed.
- **The honest limit:** code proves whose words they are, not what they meant ("I'm vegetarian, show me biryani"). That judgement is the LLM's, so it's an eval case.

**Q: How do you prove one user can't read or change another user's data, when the backend bypasses Row Level Security?**
A:
- The user id comes only from the verified token. Every query filters by it, and "not yours" returns the same 404 as "doesn't exist".
- Tests do it at both layers: the tools, and HTTP (another user's cart, order and preferences; `?user_id=` and `X-User-Id` ignored).
- Planted bugs (an unscoped read or delete, a route trusting `?user_id=`) were all caught.

**Q: What does an API route do in Dawat, and what does it never do?**
A:
- It validates the request's shape, gets the user from the token, calls the same tool the agent uses, and returns the tool's JSON with a status code mapped from the tool's status.
- It never computes a price, and request bodies refuse extra fields, so a client can't even send one.

**Q: What was the FastAPI commit-timing issue?**
A:
- The database commit happens in a `yield` dependency's cleanup. In FastAPI 0.141 that cleanup runs after the response is sent, unless the dependency is function-scoped.
- So a failed commit could have been shown to the user as "order placed". I declared `scope="function"`, and a test makes the commit fail and expects a 500.
- That test fails if the scope is removed.

**Q: Why do some errors return 409 instead of raising an exception?**
A:
- Raising rolls back the transaction. `quote_changed` both reopens the cart and tells the client to ask again; if it raised, the reopen would be lost.
- So business outcomes are returned as responses with a status code, and only real errors raise.

**Q: How will you test that the meal planner never breaks a hard rule?**
A:
- Three layers:
  1. The planner validates every plan before returning it.
  2. Hypothesis property tests generate random budgets and groups, and check each plan with an independent checker in the tests.
  3. A separate read-only `rule-breaker` sub-agent tries to make it break the four rules: over budget, non-veg for a vegetarian, spicy for a non-spicy person, not enough food.
- The rule-breaker recomputes totals with its own SQL and fee maths, so a bug shared by the planner and its checker can't hide.
- A perfect result would be treated as a reason to check the attacks, not as proof.

## Sessions 11–13 — the meal planner, consent in code, the LLM client, agent tools

**Q: Why does the LLM extract constraints but code build the meal plan?**
A:
- The LLM is good at turning "₹500, spicy, 2 of us, one's veg" into `{budget: 500, people: 2, veg_count: 1, spice_preference: spicy}`. It is unreliable at adding up a bill with GST and delivery, or at guaranteeing a vegetarian gets a veg main.
- So a strict Pydantic `MealRequest` validates the extraction ("500" as text is refused), and code builds and checks every plan.
- Live: both Gemini and Groq extracted exactly that request from the demo sentence with no system prompt.

**Q: How does the planner guarantee dietary rules when you don't know which person is the non-spicy one?**
A:
- The checker uses Hall's marriage condition over four eater types (veg+mild, veg, mild, anyone): every possible assignment of people must be feedable.
- The builder uses a greedy count. Hypothesis checks the two always agree, on 3,000 random cases per run.

**Q: Why re-run the planner when the user picks a plan, instead of adding the plan's items?**
A:
- The items would come back from the LLM or the browser, and either could edit them.
- `add_plan_to_cart` takes only a `plan_id`, re-plans deterministically and adds what the planner itself produced. If prices changed, the id isn't found (`plan_changed`).

**Q: How is "the user said yes" enforced, rather than requested in the prompt?**
A:
- `confirm_cart` from chat requires the user's latest message, supplied by the runtime and never by the LLM, to be a clear yes. It's checked by a word-based classifier in code for English, Hinglish and Telugu.
- "No" always wins; a question, an emoji or an extra request is unclear. A thank-you weakens only a weak yes: "ok thanks" is unclear, "haan thanks" is yes.
- Asking the LLM "did the user agree?" was rejected, because that is the exact thing being guarded against.
- Replacing a cart from chat goes through the same gate, because it deletes what the user chose.

**Q: How does Dawat AI handle free-tier rate limits and outages?**
A:
- One request to Gemini; on any failure (429, 503, timeout, connection, bad request, empty reply) one request to Groq; then a friendly "Dawat AI is busy" message.
- No retries anywhere: LiteLLM's are explicitly off, and a fake provider server counts the HTTP requests in tests to prove it.
- A 503 "high demand" from Gemini was seen live while choosing models, so this path is real.

**Q: How do you test failure handling without spending free-tier quota?**
A:
- A local HTTP server impersonates both providers' APIs, with scripted responses (503, 429, slow replies, empty answers, an echoed key). The real LiteLLM client talks to it via `api_base`.
- That tests the actual HTTP behaviour, including timeouts and request counts, which mocking the library call would hide.
- Then a handful of live calls (3 for the client, 2 for the tools) confirm the real providers behave the same.

**Q: How do you stop API keys leaking into logs or the UI?**
A:
- Keys are passed per request and never logged.
- Every provider error is scrubbed before it's stored: the keys in use, the keys in the environment, `?key=` parameters, Bearer tokens, and anything shaped like a Google or Groq key. Attempts become `agent_traces`, which the "thinking" panel shows.
- Tests include a fake provider that echoes the key back.
- A guard hook refuses any command or file containing a key-shaped string, even a fake one.

**Q: What can't the LLM say when it calls a tool?**
A:
- Who the user is, what the user said, and the confirmation source.
- `user_id` comes from the verified token and `user_message` from the conversation, through a `ToolContext` the model never sees.
- `confirm_cart` always runs as `chat`, so the website's button path can't be chosen.
- Schemas are closed: an extra argument like `price` or `user_id` is refused with an explanation, not ignored.

**Q: Why did you shrink the tool schemas, and how did you decide what to cut?**
A:
- All 16 schemas go with every LLM request. Groq's free tier allows 8,000 tokens a minute, and the first version was about 3,760 tokens, so the fallback could make barely one request a minute.
- Cut what the model doesn't need but code still checks: length limits; a 26-value category enum (the tool already accepts "biriyani" and refuses unknowns); the full nested plan request in `add_plan_to_cart` (described in one line, validated in full).
- Result: about 2,780 tokens, with a test cap at 3,000.

**Q: You planted 10 bugs in the LLM client and one wasn't caught. Is that a problem?**
A:
- It was a finding, not a gap to hide. Removing `max_retries=0` changed nothing, because this LiteLLM version doesn't retry these providers even when told to.
- So the setting is insurance against a future upgrade, and it's recorded that way. A test that sets LiteLLM's global retries to 2 and still expects exactly one request per provider will catch a version that starts retrying.

## Session 14 — the agent loop

**Q: Walk me through one Dawat AI turn.**
A:
- The runtime sends the system prompt, the conversation and the user's message, with 16 tool schemas, to Gemini (falling back to Groq).
- If the model asks for tools, each call goes through `run_tool`, which validates the arguments and injects identity, the user's own message and the chat source. Each tool runs in its own transaction.
- A compact copy of each result goes back to the model, and it repeats until the model answers in text.
- Every call is traced: arguments, a result summary, latency, provider, model and prompt version.

**Q: How do you stop the agent looping forever on free-tier quotas?**
A:
- A hard cap of 8 tool calls per turn. Calls beyond it aren't run, but each gets a `not_run` answer so the history stays valid, and the user gets a fixed message asking them to rephrase.
- Each model call is at most two requests (primary, then fallback), with no retries, so a turn has a known worst case.

**Q: The model fails right after the order was placed. What does the user see?**
A:
- A reply written by code, not the model: "Your order is placed: total ₹X…", with X taken from the `place_order` result.
- The order is already committed, because each tool commits on success. The user is never left wondering, and no model can misstate the total.

**Q: Why commit after every tool instead of once per turn?**
A:
- A model call can take up to 20 s. Holding a transaction that long blocks rows.
- Worse, if the model failed at the end, everything the user saw happen ("added to your cart") would silently vanish.
- Per-tool commits match what the user was told. In tests the same code runs as savepoints inside a rolled-back transaction.

**Q: Can the model talk its way into placing an order?**
A:
- No. `confirm_cart` checks the user's *current* message for a clear yes, and the runtime passes that message, not the model.
- The tests script a model that calls confirm and place after "ok thanks", "wait", a question or "nahi", and also try a "yes" from two messages earlier. No order is created in any case.
- A model passing its own `user_message` or `source` is refused before the tool runs. 9 planted bugs here were all caught.

**Q: What broke when you switched providers partway through a conversation?**
A:
- Groq rejected Gemini's assistant message, because LiteLLM had attached Gemini-only fields to it (`images`, `thinking_blocks`, thought signatures).
- The fix trims assistant messages to the standard fields for non-Gemini providers, while Gemini still gets its own messages whole, since it needs the thought signatures.
- Verified live in both directions. A fake server only accepts what you program it to, so this needed a real call to surface.

## Session 15 — system prompt, chat endpoint, evals

**Q: What's in Dawat AI's system prompt, and what deliberately isn't?**
A:
- Rule 1 is language and script mirroring. Rule 2 is "every fact comes from a tool".
- Then how to act on each tool status, the order flow, preferences and style.
- It does *not* carry the hard rules' enforcement: the yes check, prices, totals and identity live in code. The prompt only reduces how often the code has to refuse.
- It's versioned (v1, v2). Every trace records the version, and a version with eval results is never edited.

**Q: How does the chat stream "thinking" steps to the browser?**
A:
- `POST /chat` returns server-sent events: `start`, one `step` per tool call as it finishes, then `reply` and `done`.
- The turn runs in a worker thread on its own autocommit connection, and a queue relays each step to the response stream.
- The request's own connection checks the user's hourly limit and conversation ownership, and is committed before the stream starts.

**Q: How do you protect free-tier quotas on a public demo?**
A:
- Per user: 30 messages an hour, counted from stored messages. Over that is a 429 with no model call.
- Per request: one try per model in a three-model chain, no retries, a capped output allowance, and a token budget test on the prompt plus tools.
- I measured each Groq model's real limits from response headers; that's why Groq is the last resort, not the first fallback.

**Q: How do you know your eval checks actually work?**
A:
- Each check has a test feeding it a crafted bad reply (an invented price, a price in a table cell without ₹, a misspelled restaurant, a Hinglish word in an English reply, a forbidden tool call) and asserting it fails.
- One real lesson: a consent case only checked "no order placed". It passed while the model was wrongly calling `confirm_cart`, because the code gate caught it. The case now checks the tool calls too.

**Q: Your eval scored 16/16. What did you do?**
A:
- Treated it as a warning. I read every reply, wrote harder cases (a fake price, "yes but add a coke", two dishes in one message), and repeated the fragile cases three times because Gemini runs at temperature 1.0.
- The repeats found a recurring restaurant-name misspelling.
- I documented the eval's limits: small, one model, heuristic checks.

**Q: How did a "spicy" request become a guarantee rather than a hope?**
A:
- A stated preference narrows which portions the spice-tolerant eaters can take, inside the same matching logic as the diet rules: Hall's condition in the checker, a greedy count in the builder.
- So all three plans, including "Best value", must satisfy it, and a property test checks the two algorithms always agree.

**Q: What did manual testing find that automated tests missed?**
A:
- A user with a saved vegetarian diet could add mutton biryani and order butter chicken unchallenged: saved preferences weren't applied yet (planned for Phase 9).
- A typo'd Hinglish yes ("order palce kardo") was refused.
- After a "no", the reply said the order was "cancelled" while the cart still held it.
- All three are now fixes planned for the next session. That's why a human trying the product matters even with 1,000+ tests.

## Session 16 — safety under attack: from word lists to confirmation cards

**Q: Your agent must only place an order after the user says yes. How do you know a message is a yes?**
A: Two layers.
- **Rules first.** `consent()` accepts only unambiguous messages: yes phrases ("haan", "avunu", "place it"), harmless filler and an explicit list of typo repairs. Any other word makes it unclear; a "no" or hesitation word, even next to a question mark, makes it no. Trailing off ("ok. . .") is unclear too.
- **Then a small LLM.** For unclear messages it reads only the question and the reply, and must quote the user's exact words; code checks the quote is really there.
- **The LLM can never create a yes for ordering.** It can only make Dawat ask one natural question.

**Q: Why not just let the LLM decide whether the user agreed?**
A: The decision is code's ("the LLM understands, code decides"). An LLM can be talked into a yes, or misread "I didn't confirm". Our early "strong yes" rule, a yes plus an order word with other words allowed, was beaten by "ok confirm the order at my office". The model's job is to understand the request and ask the question; whether a yes counts is a code rule with tests.

**Q: What is a confirmation card and why did you need it?**
A: A rule-breaker run used a model that lies in its own reply. It asked "want a drink?" while the tools held an order, or hid a "this item is non-veg" question. Code can't check prose. So every question needing a yes is now a card built by code from the tool result: order with items, delivery and total; plan; non-veg item; preference; removal; delivery move. Exactly one card is attached to the reply, and the next message's yes can act only on that card: matching cart and quote, plan and request, item and quantity, the exact preference value. In the web app it's a card with buttons.

**Q: How did you test it, and why did the results keep coming back broken?**
A:
- **The process:** an independent adversarial sub-agent attacks with scripted malicious models and real Hinglish and Telugu messages. Every break becomes a test. Then we plant bugs (undo one fix at a time) to prove the tests catch it.
- **What the runs showed:**
  - Runs 1 and 2 showed that word-list patches create new holes;
  - run 3 showed prose can't be trusted;
  - run 4 found the remaining free-text checks;
  - the verification run found two consent wording gaps.
- **Why that's good:** each run narrowed the class of break. Under Saif's acceptance bar, only "Dawat asks again" cases may remain. A perfect first run would have meant the attack was too weak.

**Q: Where are the honest limits?**
A: Decision 4: at the non-veg question a clean, verified LLM yes adds the item directly. A wrong LLM yes on an unclear message could add it, but the order card still shows it before any money moves. Other limits:
- Items the model adds unasked are visible on the order card rather than blocked.
- The turn lock needs the database's session-mode pooler.

**Q: Why is a confirmation only valid for one turn?**
A: A cart confirmed in turn N could otherwise be ordered by a later "ok" meant for something else. Every new message re-opens a confirmed cart, so confirm and place must follow the same yes. Phase 8 has to keep a website checkout's confirmation from being re-opened by a chat message.

## Session 17 — closing the consent design, starting the web app

**Q: You let an LLM help decide whether a user agreed. What exactly is it allowed to do?**
A: Only add a question. The decision is a code table: if the rules say no, it's no. If the rules say yes but the classifier doubts it, Dawat asks once more. If the rules are unclear and the classifier says yes, Dawat still only asks once more, now at every moment including the non-veg question (D-047). A test runs a classifier that always says yes over 600+ real messages at all three moments, and asserts nothing proceeds unless the code rules alone already said yes.

**Q: Why remove the shortcut where a verified LLM yes added a non-veg item directly?**
A: It was the last way an action could happen without a plain yes. The cost is one extra "yes" for "I'm ordering it for my boyfriend". In return, every action in the agent follows one rule, so I can say "Dawat AI never acts on an LLM's reading of consent" without an asterisk. For a food app's credibility, a vegetarian never getting meat by mistake is worth one extra tap.

**Q: How did you decide Phase 6 was done?**
A: Saif set an acceptance rule after four adversarial runs: the only remaining breaks may be cases where Dawat asks again rather than acting without a yes. D-047 closed the last acting case. Then one full run of the suite on the final code had to pass (1,752 tests, 0 failures). A green partial run on code still changing wouldn't count.

**Q: Why does your Next.js frontend fetch data in the browser instead of rendering on the server?**
A: The backend is on Render's free tier and sleeps when idle, taking up to about 50 seconds to wake. A server-rendered page would block on that and could hit Vercel's function timeout. With static shells plus browser fetching, the page loads instantly and shows "Waking up Dawat AI…" after 4 seconds. It also means the browser's real CORS path is always exercised. The trade-off is SEO, which doesn't matter for a demo app.

**Q: How does the frontend handle errors from the API?**
A: The client never throws; it returns `{ok, status, data, message, kind}`. Many "errors" carry something to show: a 409 when a price changed comes with the fresh cart, a 429 says which limit was hit. Network failures, timeouts and caller cancellations are distinguished, so the page can say "can't reach Dawat" vs "taking too long". The client never sends a price; the backend refuses extra fields anyway.

**Q: How do you guarantee accessible colour contrast with a gold-and-plum brand?**
A: Three layers:
- **A script** reads the actual hex values from the stylesheet and checks 24 text and UI pairs against WCAG AA, so a colour tweak can't silently break contrast. Gold on ivory measures 1.94:1, which is why gold is only used for lines and icons on plum or night.
- **Small details are handled in code:** focus rings switch from plum to gold on the plum header, so keyboard focus never disappears.
- **A read-only ui-checker agent** measures contrast on the rendered page with its own maths, plus keyboard use and the 360px layout.

**Q: How will demo visitors try the app without sharing one account?**
A: Each "Try as Priya" click makes a fresh anonymous Supabase account. The backend seeds it with the persona's preferences and 2–3 sample orders, built through the real cart → confirm → order tools so every rule applies. Then their dates are moved back. Visitors never share a cart or a message limit. A global daily cap, an atomic counter in Postgres, protects the free Gemini quota across all visitors.

**Q: You added a UI library with a CLI. What did you check?**
A: I diffed what it changed. It had swapped the brand font, left a broken CSS variable and put a build tool in runtime dependencies. I also verified an unfamiliar package name was published by the library's own maintainer. Then I split the audit: what visitors' browsers receive has 0 known vulnerabilities. The dev-tool findings were denial of service on malicious input, with only downgrade "fixes", so I logged them to re-check at deploy instead of breaking the toolchain.

## Session 18 — a local test database and caching reference data

**Q: Your tests used to run against Supabase inside rolled-back transactions. Why move them to a local database?**
A: Rolled back or not, the tests read and wrote the production database, used its few pooled connections and its free-tier egress, and a bug in a test could still affect live data. The rule now: tests, evals, the adversarial agent and migration rehearsals run only on a local PostgreSQL 17, the same major version as Supabase. Supabase only gets real migrations, after they pass locally.

**Q: How do you make sure nobody, including an AI agent, accidentally runs tests against production?**
A: In code, not in a doc, in two layers:
- **The entry point:** every test entry point reads only `TEST_DATABASE_URL`, and a host check refuses it unless every host is localhost, 127.0.0.1 or ::1. If it's missing, database tests skip; they never fall back to the production URL.
- **The app itself:** inside a test run, the app's own connection pool refuses a non-local database, even if something loaded the production URL first.

I showed it by pointing the tests at a Supabase-shaped host: pytest, the evals and a migration rehearsal all stopped before connecting. Planted bugs (for example "any host local" instead of "all") were each caught by a test.

**Q: What did the local database need that Supabase gives you for free?**
A: Supabase adds the `auth` schema (`auth.users`, `auth.uid()`), roles like `anon` and `authenticated`, and an `extensions` schema. I wrote minimal stand-ins for exactly what our migrations and code use. I also matched Supabase's settings: UTF-8, ICU en-US collation (so ORDER BY agrees), UTC and the same search_path. The seed has a local mode that writes demo users straight into `auth.users`, because there's no sign-in service locally.

**Q: The first local run had two failures. What were they?**
A: Test bugs. Two tests picked "any item in Madhapur" with `limit 1` and no ORDER BY, then added it for a vegetarian demo user. On Supabase, physical row order happened to return a veg item; on the fresh local load it returned Egg Biryani. The agent correctly asked the diet question instead of adding it. The fix was a deterministic veg pick. A fresh database is a good way to find tests that pass by luck.

**Q: How does the backend cache menus without serving stale prices?**
A: At startup it loads all reference data, including all 23,784 menu items (about 1.5 MB), into memory. Triggers on the reference tables stamp a new random uuid in a one-row table whenever anything changes. The server reads that one row at most once a minute and reloads only if it changed. Two important choices:
- **Money never comes from the cache.** Cart prices, quotes and orders are always read live.
- **The planner's independent checker also reads live.** If the builder and the checker shared one cache, a stale copy could fool both. At worst a stale menu makes the planner propose something the checker refuses, which becomes an honest "try again", never a wrong plan.

**Q: Why a random uuid for the version and not a counter?**
A: Tests change menu rows inside transactions that are rolled back. With a counter, two different rolled-back changes could both produce "version 6", and the cache would wrongly think it was current. A random stamp can't collide that way. In tests the check runs on every call, so each test sees its own changes and the next sees them undone.

**Q: How did you verify the cache is correct?**
A: An equivalence test compares the cached menus with a real database query for every restaurant, row for row and in the same order. Other tests cover:
- a price change being seen at once;
- no reload while the version is unchanged;
- the fallback before the migration exists;
- cart prices staying live while the cache is frozen.

Planted bugs (ignoring availability, never reloading, unsorted ties) were each caught. In the dev app, a menu now comes back in about 5 ms instead of a round trip to Mumbai.

## Sessions 19–20 — the web app's sign-in, checkout, chat widget, a safe local dev login, orders and profile

**Q: How does "Try as Priya" give every recruiter their own demo without sharing data?**
A: Each click makes a fresh anonymous account (Supabase anonymous sign-in), and the backend then seeds it once: a name, Priya's preferences, an address and three sample orders built through the real cart and order tools. It only works for an anonymous account, and only once (`demo_persona` is claimed with `where demo_persona is null`). So a real account can never be overwritten, and two visitors never see each other's cart. The token is verified exactly like any other user's.

**Q: How do you stop many demo visitors from burning the free LLM quota?**
A: A global daily cap in the database, taken in one atomic statement: `insert … on conflict do update set count = count + 1 where count < cap returning`. At the cap it returns no row, so the count can never pass it, even with simultaneous requests. A test races 8 connections for the last slot. A refused request spends no slot and creates no empty conversation.

**Q: The chat and the page share one cart. How does the page update while Dawat AI is still replying?**
A: The chat streams server-sent events: each tool step, then the reply. When a step that changes the cart succeeds (add, plan to cart, remove, confirm, place), the page re-reads the cart from the backend, so the header count changes mid-reply. The page never keeps its own copy of prices. It shows the backend's cart, and every write returns the fresh one.

**Q: Why are confirmation cards and plan options drawn from backend data, not the model's text?**
A: A model can say a different total than the one it's asking about. The card is built by code from the tool result: the items, fees, GST and total. A "Yes" button only sends "Yes", and the backend decides what that yes may act on (only the card under the previous reply). Plan cards are rendered from the planner's own output, and a test checks they equal an independent planner run.

**Q: You have a dev login that bypasses Supabase. How can you be sure it's never on in production?**
A: Five independent locks:
1. **Only a launcher script sets the flag.** If it ever appears in the env file, the server refuses to start.
2. **The backend refuses to START** if the flag is set and the database isn't on this machine, or a hosting platform is detected (Render sets `RENDER`), or the flag has any value other than 1. It's checked at import, so uvicorn never serves, and a bad deploy fails its health check.
3. **When it's off, it doesn't exist.** The routes aren't mounted, and the only trusted token issuer is Supabase's, so a dev token gets a 401.
4. **The frontend can't ship it.** Every path to the dev code sits inside a build-time condition that Next folds to false in production, `next.config` refuses the flag outside the dev server, and `npm run build` scans the output and fails if dev-only strings appear.
5. **Tests:** 41 backend tests including real subprocess start-ups, 9/9 planted bugs, and frontend mutations.

**Q: Why not just use `if (DEV_LOGIN)` with a constant?**
A: The bundler only removes code it can prove is dead. A constant imported from another module isn't folded, and my first build scan found the dev sign-in component in the browser bundle (unreachable, but shipped). Writing the condition inline (`process.env.NODE_ENV === "development" && …`) and putting the dynamic import inside it removed it. A planted mutation that guarded with a same-module const did NOT leak, because the bundler folds that. I reported it as harmless rather than pretending the scan caught it.

**Q: Isn't a dev login a weaker test of authentication?**
A: Only the key and issuer differ. Dev tokens are ES256 and go through the same verifier as Supabase's (signature, issuer, audience, expiry, role, subject), so every authorization rule runs exactly as in production. What it doesn't exercise is Supabase's own sign-in screens, so the deploy checklist re-checks those once against Supabase before going live.

**Q: Why choose a dev login over running Supabase locally in Docker?**
A: The local Supabase stack needs no new code, which is safer. But this machine had about 3 GB of RAM free, and a test run had already been killed for low memory. Docker's VM and its containers on top of the app and a browser wouldn't fit. The CLI's local auth also signs with a shared HS256 secret unless keys are configured, and the backend deliberately refuses HS256. I'd pick the Docker stack on a bigger machine or if the sign-in flows were changing often.

**Q: How does the order tracking page avoid inventing anything?**
A: It shows the status timeline exactly as `track_order` returns it, scoped to the signed-in user (another user's order number looks exactly like a missing one). While an order is open it says "No delivery time yet" instead of an ETA, because no tool returns one. Order numbers in Dawat AI's replies become links, but the page asks the backend, so a wrong number just shows "not found".

**Q: How do the profile page's preference changes differ from the chat's?**
A: In chat, a preference change takes two steps: Dawat AI offers, and only the user's clear yes to that exact offer saves it, because the model could misread intent. The settings screen is explicit by nature (the user pressed Save), so it saves straight away with source `settings`, and each preference shows how it was saved.

**Q: What did accessibility checking find that you wouldn't have noticed by eye?**
A: Three examples:
- The default-area form lost keyboard focus: its list is disabled while loading, and a disabled element can't take focus. The fix focuses it once the list arrives.
- At 360 px a shared `inline-flex` class silently beat `hidden`, so all the header links showed and the page scrolled sideways.
- The local sign-in buttons' border measured 1.29:1.

All were found by an automated checker that measures contrast with its own maths and checks focus after every action, and each was fixed and re-checked.


## Session 21 — Payments and the simulated gateway
**Q: Why is an order created only after payment, and how is that enforced?**
A: `place_order` is an internal step called only from the verified-payment path (a source-scan test enforces the callers). `POST /orders` and the chat tool return `payment_required`. The database also refuses a "paid" order without payment ids, and an unpaid order that moves past "placed".

**Q: How do you stop a client from choosing the price it pays?**
A: `/payments/start` takes only a cart id. The amount is the server's confirmed grand total. The attempt stores the quote fingerprint and amount, and `/verify` re-checks both against the cart.

**Q: What does the signature prove, and what attacks did you consider?**
A: HMAC-SHA256 over `order_id|payment_id` proves the payment belongs to our order. It's compared in constant time. Ids are shape-checked first, because a `|` in an id could shift the signed text. A bad signature changes no state, so an attacker can't poison an attempt, and lookups are scoped to the signed-in user.

**Q: What if the user pays and the cart changed meanwhile?**
A: No order is created. The attempt is marked `needs_refund` and the user gets an honest message. The refund is simulated.

**Q: Razorpay required identity onboarding. What did you do?**
A: Built a local simulated gateway behind one config switch. It uses the same routes, the same HMAC check and `pay_TEST_` ids. It accepts only fixed test cards and UPI ids, and never receives CVV or expiry. A failure creates no order and the cart stays confirmed. The honest limit: the same server issues and checks the signature, so it proves the flow, not a bank's approval.

**Q: How do you show live tracking on a free tier with no worker?**
A: Progress is computed when the order is read, and the events are written once, stamped with their due time. The rider position is a straight-line interpolation. It's simulated, with no ETA.

**Q: How do you know the payment tests are strong?**
A: Planted bugs: break one rule at a time and confirm a test fails. The first run missed 5 of 34. Three were real gaps, which I fixed. One was a harness bug, and one is an equivalent mutant (a second check covers it). A perfect first score would have been a red flag.

## Session 22 — Google-only sign-in and the name-confirm step

**Q: Why did a login that worked in one frontend fail in the copy?**
A: The code was identical; the switch that enables local dev login was missing. The flag is set only by a launcher script, so without it the app used Supabase anonymous sign-in, which fails in local mode. I found it by diffing the lib files and launcher scripts before changing anything.

**Q: Why refuse anonymous tokens in code when you can turn them off in Supabase?**
A: Defense in depth. A dashboard toggle can be wrong or forgotten. If the verifier rejects any `is_anonymous` claim, the policy holds regardless, and a test proves it on every kind of route.

**Q: How do you make sure the displayed name can't be spoofed?**
A: "Keep" stores the name from the verified token, never from the request body. A changed name comes from the user, so the server trims and validates it (1–60 characters, no control or invisible characters, no markup) and scopes the update to the token's user id. Extra body fields are rejected, and tests show another user's row is never touched.

**Q: Why doesn't the backend require `name_confirmed`?**
A: It is a UX flag. If orders, cart or chat depended on it, a UI state could block or change safety rules. A source-scan test confirms only the profile code reads it, so the website gates pages while the backend rules stay independent.

**Q: How does the fake Google user avoid reaching production?**
A: The route and token issuing refuse unless the dev login is enabled, which needs the launcher's flag, a local database and no hosting markers. The frontend condition is inlined so the bundler drops it, and the build scans its output for markers and fails if any appear.

**Q: How did you test the tests?**
A: I planted 21 bugs one at a time (anonymous accepted, an update with no WHERE, the body name beating the token, each validation rule removed, and so on) and confirmed a test failed each time. One apparent miss was my mutation not applying, which is why the harness needs checking too.


## Session 23 - The MCP server

**Q: Why can't consent pass through Claude Desktop?**
A: Over MCP the caller is the client's model. Anything it sends, including "the user said yes", is model output, not the user's word. So the server never confirms or places an order; it only does things that add to the cart and are undoable, and hands ordering to the website where the user presses Place order and Pay.

**Q: How is identity handled over MCP?**
A: A token set by whoever starts the server (environment variable) and verified on every call by the same verifier as the website. It is never a tool argument and the tool schemas are closed, so a `user_id` argument is rejected. Any failure gives one identical generic sign-in reply; the reason only goes to the log, so a client can't probe why a token failed.

**Q: Why verify on every call and not once at start?**
A: An expired or revoked token must stop working immediately. A once-at-start check would keep a dead session alive.

**Q: Which limits exist over MCP and why in code?**
A: Max 10 of one item and 30 items per cart, a confirmed cart is never touched, non-veg is refused for a saved vegetarian, plans only go into an empty cart. A model can't be asked politely to stay within limits; code reads the database and enforces them, with the cart row locked so two parallel calls can't both pass.

**Q: What is an equivalent mutant, and what did you see?**
A: A planted bug that changes nothing observable. Replacing a cart is blocked by the schema, the module's own empty-cart check and the planner's check. Removing one leaves behaviour unchanged, so the test can't fail; I removed them together to prove the remaining lock held and that tests catch it when none do.

**Q: What if the client has no elicitation?**
A: Then nothing is confirmed over MCP at all: the server hands off to the website. The design doesn't depend on a feature whose support in Claude Desktop is unconfirmed.


---

## Session 24 - Mobile pivot, design tokens and the dev link

**Q: You switched from a web app to a native app mid-project. How did the architecture allow that?**
A: The backend was client-agnostic from the start: a Bearer token, JSON routes, and SSE for chat. All facts, totals and rules live in the backend and agent, so a new client is only a new view. The pivot changed Phases 7 to 10 and left the backend, planner, agent and tests untouched. I rejected a PWA or WebView wrapper because it would not be native, would carry web-only layout and tools, and would not give native secure token storage.

**Q: Why are there no CORS settings for the mobile app?**
A: CORS is a browser rule that uses the Origin header. A native app does not send one, so `ALLOWED_ORIGINS` plays no part and the `*` ban stays untouched. The real protections are the same as before: verified tokens, server-side totals, closed request schemas.

**Q: `EXPO_PUBLIC_` variables: what is the risk?**
A: They are embedded in the app bundle, so anyone who unpacks the app can read them. They follow the same no-secrets rule as `NEXT_PUBLIC_`. I added a guard rule that blocks writing such a variable whose name contains words like SECRET, SERVICE_ROLE, GEMINI or DATABASE, with any value, and tests that prove it, including a planted-bug test. The honest gap: a long random value under an innocent-looking public name is not caught, because the Supabase publishable key and Google client IDs are long and public by design.

**Q: A brand colour failed accessibility. What did you do?**
A: Coral `#FF5844` with white text is 3.12:1, below the 4.5:1 body-text minimum. I did not change the brand colour. Primary buttons are navy with white text (12.4:1), and coral is used for icons, badges with dark text, active states and large text. Coral is also under 3:1 on the page background (2.83), so it never stands alone there. A Jest test recomputes every ratio in the design table and also checks that the documented failures stay failures. I broke the tokens on purpose three ways and the tests failed each time.

**Q: How do you test a phone app against a local backend without exposing it to the network?**
A: Over USB with `adb reverse`, which forwards the phone's localhost ports through the cable to the PC's loopback. The backend stays on 127.0.0.1. Binding to the LAN would expose the dev login, which hands out a token to anyone who can reach the port, and would let strangers place orders in the dev database and use the LLM free quota. So LAN and tunnels need explicit approval and were rejected.

**Q: Why stream chat with `expo/fetch` and not an EventSource library?**
A: `EventSource` cannot send a POST body or an Authorization header, and `/chat` needs both. The Expo docs show a streaming response body with `getReader()`. I marked this as unverified until a spike on a real device, and I keep a non-streaming fallback in mind.

**Q: How did you check the supply chain when you installed packages?**
A: Read each package's publisher and repository with `npm view`, checked publish dates and stepped three non-Expo packages back from versions younger than 14 days, pinned every version exactly, kept the lockfile, listed packages with install scripts (only a macOS-only `fsevents`), and ran `npm audit` without `--force` (the forced fix would have downgraded Expo to version 44). I also read peer dependencies and found the test library needed `test-renderer`, not the old `react-test-renderer`, and that the newest `test-renderer` needed React 19.3 while Expo uses 19.2.

**Q: What would you say about the OpenStreetMap tiles in the app?**
A: The tile policy allows interactive use with visible attribution, a distinct User-Agent, honoured cache headers, and no prefetching or offline saving, with best-effort access. The risk is that a WebView showing inline HTML has no valid Referer and a browser User-Agent, so tiles may be refused. I planned a spike before relying on it and a static placeholder map as the fallback.

**Q: Why do the card buttons always send exactly "Yes" or "No" through the chat?**
A: Confirmation must reach the same server-side gate the chat uses: only a clear yes in the user's latest message, acting on the card shown under the previous reply, can confirm. A button that called confirm or place-order directly would bypass that check. The label can say "Yes, place this order", but the message sent is "Yes".


## Session 25 - Mobile sign-in, token handling and the dev-login lock

**Q: When should a mobile client sign the user out?**
A: Only when the backend answers a real HTTP 401. A timeout, offline state, 5xx or the backend's 503 (sign-in keys unreachable) says nothing about the token, so the app keeps it and offers "Try again". Tests cover each status, and a planted bug that treats any non-OK as a 401 fails 14 of them.

**Q: How do you stop a slow response from undoing a sign-out?**
A: Every sign-in and sign-out bumps a generation counter; a response only applies if the counter is unchanged. A test releases a held `/me` answer after sign-out and checks the user stays signed out and the token stays deleted.

**Q: Where is the token stored, and how do you prove it is never logged?**
A: In the platform keystore through `expo-secure-store`, plus memory. A test scans `src/` and fails on any `console.*` or AsyncStorage/localStorage use; another spies on the console during a run. Planted bugs (logging the headers, putting the token in the URL) are caught.

**Q: How do you make sure the dev login cannot ship?**
A: One inline build-time condition (`__DEV__` and an env switch) lets Metro remove the branch and the module it requires. `check:release` exports a production bundle with the switch deliberately on and scans for markers. I also removed `__DEV__` on purpose and confirmed the scan fails, so it is not a check that always passes.

**Q: Why does "Continue with Google" not work yet?**
A: Native Google sign-in needs native code, so it needs a development build, not Expo Go. The plan is the Google sign-in library, an ID token passed to Supabase `signInWithIdToken`, with the backend unchanged. Until then the button says it is not set up, rather than pretending.

**Q: What did testing on a real phone find that tests could not?**
A: Metro bound only to IPv6 so `adb reverse` failed; a rounded View rendered square in the tab bar on one phone; the status-bar strip was black. All were found by screenshots from the device. One unexplained relaunch-to-Welcome is recorded as not reproduced, not hidden.


---

## Session 26 additions

**Q: How does a chat turn get cancelled safely when the user taps Stop or leaves?**
A: The app aborts the stream; the server polls for a gone client and sets a stop flag. The agent loop checks it only between steps, so a tool or database write is never interrupted. Tool calls that did not run get a "not run" answer so the saved history stays valid, the turn is marked cancelled with a code-built reply, and any unseen confirmation card is stripped. I proved it on a real phone turn: `get_menu` ran, `add_to_cart` was answered "Cancelled before this ran", and the conversation did not grow afterwards. Limit: a model call already in flight finishes first.

**Q: Why did the cancel need explicit stream closing?**
A: A test showed Starlette leaves the generator suspended until garbage collection after a disconnect, so the turn would not notice. The response wrapper always closes the generator and swallows the disconnect error.

**Q: How do the Yes/No card buttons stay safe?**
A: They send only the text "Yes" or "No" through the chat, never call confirm or place-order. Cards are answerable only under the newest reply and when no turn is running; an old card greys out with "This question has passed". On the phone, a vegetarian user asking for an Egg Puff got the diet card, and "No" left the cart unchanged (checked in the database).

**Q: How does the payment screen avoid trusting the client?**
A: It sends only the cart id to start; the amount shown is the server's `amount_rupees`; the card or UPI value is chosen from five fixed test values (no text field); verify is called only after a successful simulate and with exactly the three values returned. A decline creates no order. 13 planted bugs (amount sent, wrong signature, decline shown as paid, no double-tap guard, and others) were all caught.

**Q: How did you handle OpenStreetMap's tile policy in a mobile app?**
A: Leaflet in a WebView with a `baseUrl` so tiles carry a Referer, a distinct User-Agent, visible attribution, and only coordinates sent in. A spike on the phone showed both the default and custom user agents load tiles; a plain labelled map is the fallback. The contact address in the User-Agent is a placeholder Saif must set before deployment.

**Q: What did a real test find that the unit tests missed?**
A: My dev seed button picked the wrong demo user (a name-prefix match against "Demo Priya (vegetarian)"), which would have made the diet test meaningless; I caught it from the profile screen and the database before drawing conclusions, and it cost two of the four real chat turns.

## Session 27 additions

**Q: How do you stop one user's orders showing for another on a shared phone?**
A: One loader keeps each answer together with the user id and path it was fetched for and returns it only while that user is signed in; a late reply that arrives after a sign-out and a different sign-in is dropped. Tests cover sign-out then sign-in as someone else, a late answer after the switch, and a failed load not falling back to the first user's rows. Planted bugs: 18 of 20 caught; the 2 survivors were each covered by a second independent lock (removing both is caught).

**Q: A test failed once in a while. What did you do?**
A: I did not guess. A first fix (a longer wait) did nothing, so I ran the suite from a cold cache until it failed and read the output: the first test in one file exceeded jest's 5 s limit while its module was being compiled. The fix was the per-test timeout, and the guess is recorded as such in the decision log.

**Q: What stops a customer paying for a cart that has changed?**
A: The payment and review screens re-read the cart from the server when they open, and payment starts only for a cart the server says is confirmed; the app sends the cart id only and shows the server's amount. Eight planted bugs in that gate were tried; two survived at first, so I added tests (a held cart that is open on re-read, and a 200 reply whose status is not "ok"). A later check found the review screen's re-read was untested too, and I closed that.

**Q: Why did your accessibility scan pass at first, and what did you learn?**
A: It scanned zero files because of an escaping slip. A scan that can pass while looking at nothing proves nothing, so it now asserts it found a minimum number of touchables and inputs, and two planted bugs (a removed label, a shrunk tap target) are caught.

**Q: How do you stop map labels overlapping when points are 100 m apart?**
A: A pure function places each label on the first free side of its dot (top, bottom, right, left) against the labels and dots already placed. The WebView map carries a plain-JS copy, and a 300-case test checks both give the same sides. A test also shows the old "all on top" rule does overlap on the same points.

**Q: What does an Android APK build need, and what does it cost?**
A: A package name, versions, an icon and splash, and a signing key. EAS cloud build generates and stores the key and builds an APK on its free plan (limited low-priority builds, no card). Release Android blocks plain http, so the APK needs the deployed https backend; local testing uses a development build. The release profile is guarded by a test so it can never carry the dev-login switch, and a release-bundle scan fails if dev-login code appears.

**Q: What mistake of yours did you catch this session?**
A: A scripted file write failed on the rupee sign and emptied a test file. I noticed it from the zero-test run, recovered the exact original from the test runner's cache source map, re-ran its tests, re-added my change with a tool that handles UTF-8, and scanned the project for other empty files.
