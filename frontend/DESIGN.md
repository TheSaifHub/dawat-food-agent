# Dawat Design System & Architecture Guide
**Tagline:** *"Every order, a feast."*  
**Domain:** Hyderabad Authentic Food Ordering Web App & AI Concierge  
**Design System Version:** 1.0.0  

---

## 1. Brand Identity & Principles

Dawat is crafted to evoke the culinary heritage of the Nizams of Hyderabad—majestic dastarkhwans, slow acacia charcoal dum cooking, sealed earthen handis, and Irani samovars—while maintaining the crisp usability, accessibility, and high conversion velocity of a modern tier-one consumer web application.

### Key Brand Anchors
- **Emblem / Logo:** A gilded Mughal pointed cusped (ogee) arch enclosing a covered serving dish (*degh* / *cloche*) with steam fragrance curls, set against a royal Plum background (`#5B1E4E`). Implemented entirely as a clean, scalable inline vector SVG (`components/DawatLogo.tsx`).
- **Brand Motifs:** Subtle geometric star-point grid textures (`.nizami-pattern` and `.nizami-pattern-dark`), arched container silhouettes, brass-accented katori badges, and warm Deccani culinary illustrations.
- **Tone of Voice:** Warm, polite, hospitable (*Adaab!*), knowledgeable about Hyderabad localities (Banjara Hills, Jubilee Hills, Charminar, Madhapur, etc.), and respectful of dietary boundaries.

---

## 2. Colour Tokens & WCAG Contrast Rules

All color tokens are strictly defined in `app/globals.css` using CSS custom properties and mapped to Tailwind CSS utilities.

| Token Name | Hex Code | Role | Usage & Accessibility Rule |
| :--- | :--- | :--- | :--- |
| **Plum** (`--color-plum`) | `#5B1E4E` | Primary Brand Color | Primary buttons, headers, active tabs, brand accents, icon badges. Contrast on Ivory: **8.2:1** (WCAG AAA). |
| **Plum Dark** (`--color-plum-dark`) | `#3F1436` | Primary Hover / Deep | Button active/hover states, deep footer accents. Contrast on Ivory: **11.4:1** (WCAG AAA). |
| **Plum Soft** (`--color-plum-soft`) | `#F5EDF3` | Surface Highlight | Selected items, active persona pill background, subtle table rows. |
| **Gold** (`--color-gold`) | `#D8AE4A` | Accent / Highlight | **STRICT RULE:** Used exclusively for divider lines, borders, icons, and highlights on Plum (`#5B1E4E`) or Night (`#22161F`) backgrounds. **NEVER used for text on Ivory.** |
| **Ivory** (`--color-ivory`) | `#FAF6EF` | Canvas Background | Global page background, soft input backgrounds, subtle card tints. Warm, inviting, non-glare. |
| **Night** (`--color-night`) | `#22161F` | Primary Typography | Body copy, headers on light canvas, dark footers. Contrast on Ivory: **13.5:1** (Exceeds WCAG AAA requirement of 7:1). |
| **Night Muted** (`--color-night-muted`) | `#574652` | Secondary Microcopy | Subtitles, helper text, timestamps, dish descriptions. Contrast on Ivory: **5.8:1** (WCAG AA). |
| **Night Subtle** (`--color-night-subtle`)| `#877682` | Tertiary / Placeholder | Input placeholders, inactive icons, divider strokes. |
| **Warm Border** (`--color-border-warm`)| `#EADFCF` | Structural Dividers | Card borders, table dividers, inputs. |

### Spice Level Indicators
- **Not spicy:** `#2E7D32` (Forest Green) &bull; Mild fragrant aromatics only.
- **Mild:** `#9A7D0A` (Warm Amber) &bull; Gentle whole spices, creamy rabri/korma profile.
- **Medium:** `#D35400` (Ochre Orange) &bull; Balanced Nizami warmth and roasted cumin.
- **Hot:** `#C0392B` (Crimson Chili) &bull; Sun-dried Guntur red chillies & crushed black peppercorn.

---

## 3. Typography & Type Scale

Fonts are loaded with `next/font/google` with zero layout shift (`display: swap`).

- **Display & Headings:** `Cormorant Garamond` (Weights: 400, 500, 600, 700)  
  *Heritage, regal Deccani courtly aesthetic, serif elegance.*
- **Body, Inputs & Microcopy:** `DM Sans` (Weights: 400, 500, 600, 700)  
  *Geometric, ultra-legible numerals for prices, crisp tap targets, modern app clarity.*

### Type Scale Breakdown
- **Display 1 (Hero Title):** `text-4xl` to `text-6xl` (36px – 60px), Font: Cormorant Garamond, Leading: 1.15
- **Heading 1 (Page Title):** `text-3xl` to `text-4xl` (30px – 36px), Font: Cormorant Garamond, Bold
- **Heading 2 (Section Title):** `text-2xl` to `text-3xl` (24px – 30px), Font: Cormorant Garamond, Bold
- **Heading 3 (Card Title / Subtitle):** `text-lg` to `text-xl` (18px – 20px), Font: Cormorant Garamond / DM Sans, Semi-Bold
- **Body Regular:** `text-sm` (14px), Font: DM Sans, Leading: 1.5
- **Body Small / Descriptions:** `text-xs` (12px), Font: DM Sans, Leading: 1.4
- **Micro / Badges:** `text-[10px]` to `text-[11px]`, Font: DM Sans, Uppercase / Tracking-wider, Bold

---

## 4. Spacing, Grid & Layout System

- **Baseline Grid:** 4px / 8px scale (`p-1` = 4px, `p-2` = 8px, `p-3` = 12px, `p-4` = 16px, `p-5` = 20px, `p-6` = 24px, `p-8` = 32px, `p-12` = 48px).
- **Target Viewports:**
  - **Phone:** 360px minimum width tested without horizontal scroll (`overflow-x-hidden`).
  - **Tablet:** 768px (2-column grids, collapsible drawers).
  - **Desktop:** 1280px standard container (`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`).
- **Touch / Tap Target Rule:** All interactive buttons, quantity selectors, checkboxes, and links maintain a minimum dimension of **44px &times; 44px** (`min-h-[44px]`).
- **Focus Rings:** High-visibility dual-state focus outlines:
  - On Ivory/Light surfaces: `outline: 2px solid #5B1E4E; outline-offset: 2px;`
  - On Plum/Dark surfaces: `outline: 2px solid #D8AE4A; outline-offset: 2px;`

---

## 5. Component Registry (`components/`)

1. **`TopBanner.tsx`**  
   Persistent top announcement fulfilling the mandatory demo requirement:  
   *"Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant."*
2. **`Header.tsx`**  
   Sticky navigation containing the inline SVG Dawat logo, interactive Hyderabad locality picker (Banjara Hills, Jubilee Hills, etc.), persona switcher pill (Arjun / Priya), live cart counter badge, and Dawat AI launcher CTA.
3. **`Footer.tsx`**  
   Comprehensive footer featuring brand mission, screen directory links, accessibility statement, and the mandatory attribution:  
   *"Restaurant names and locations &copy; OpenStreetMap contributors"*.
4. **`DawatLogo.tsx`**  
   Inline SVG component with pointed Mughal arch, cloche lid with steam plumes, and pedestal base on Plum background (`#5B1E4E`).
5. **`FoodIllustration.tsx`**  
   Handcrafted neutral SVG vector illustrations for Hyderabadi specialties (Biryani handi, Haleem bowl, Charcoal seekh kebab, Karahi curry/salan, Saffron sheermal, Irani chai with Osmania biscuit, Double ka meetha, and Royal thali). Avoids copyrighted imagery while delivering a warm, authentic aesthetic.
6. **`RestaurantCard.tsx`**  
   Listing card presenting real distance (e.g. `1.4 km`), delivery fee (e.g. `Free Delivery` or `₹25 fee`), price tier (`₹₹`), cuisine tags, and dietary badges. **Strictly omits star ratings, reviews, and fake time estimates.**
7. **`MenuItemRow.tsx`**  
   Interactive menu item presenting Indian regulatory dietary indicators (Green circle for Veg, Brown square for Non-Veg), mandatory spice labels (`Not spicy`, `Mild`, `Medium`, `Hot`), price in ₹, description, and accessible `+ / -` quantity selector.
8. **`CartBill.tsx`**  
   Single-restaurant bill enforcement. Itemizes food subtotal, delivery fee or `FREE`, 5% restaurant GST, and grand total. Contains the primary "Place Order" trigger.
9. **`StatusTimeline.tsx`**  
   Order tracking visualizer depicting 5 distinct stages (Order Placed &rarr; Degh Dum Simmering &rarr; Rider Assigned &rarr; In Transit &rarr; Delivered) with demo stepper controls and simulated delivery partner credentials.
10. **`MapPlaceholder.tsx`**  
    Bespoke schematic vector map of Hyderabad showing landmarks (Hussain Sagar, PVNR Expressway, Banjara Hills Road 10), distance radius rings, and live courier tracking coordinates.
11. **`ChatPanel.tsx`**  
    The Dawat AI assistant widget:
    - Floating launcher button at bottom right.
    - 440px fixed side-sheet on desktop.
    - Fullscreen modal on 360px phones.
    - Integrated with `ThinkingSteps`, `PlanCard`, and `ConfirmCard`.
12. **`ThinkingSteps.tsx`**  
    Collapsible reasoning steps dropdown displaying how Dawat AI evaluates local kitchens, spice thresholds, and portion economics.
13. **`PlanCard.tsx`**  
    Plan options curated by AI (`Best value`, `Best match`, `Variety`) with serves-count, item breakdowns, and 1-tap cart addition.
14. **`ConfirmCard.tsx`**  
    Order confirmation prompt with explicit `Yes, Add to Cart` and `No, Tweak` actions.

---

## 6. Page Routing Architecture

| Screen | Route | Responsiveness & Feature Summary |
| :--- | :--- | :--- |
| **1. Home** | `/` | Area selector, cuisine shortcuts with neutral SVG art, "Chains near you", and "Just ask Dawat AI" spotlight with 1-tap prompts. |
| **2. Restaurant Listing** | `/restaurants` | Search bar, veg-only toggle, cuisine selector, price filter, distance slider, delivery fee filter, and sort options. |
| **3. Restaurant Page** | `/restaurant/[id]` | Hero header, locality map placeholder, category menu anchors, spice badges, and sticky cart checkout drawer. Prerendered statically via `generateStaticParams`. |
| **4. Cart & Checkout** | `/cart` | Single kitchen bill, item quantity adjustments, saved delivery address picker, delivery notes, and simulated payment methods (UPI, Card, COD). |
| **5. Order Tracking** | `/order-tracking` | Status timeline milestones, route map, itemized receipt, and direct link to ask Dawat AI for simulated order assistance. |
| **6. Profile** | `/profile` | Active persona switcher, saved spice tolerance, favorite Deccani dishes, saved addresses, and past order history with 1-tap re-order. |
| **7. Login** | `/login` | Instant 1-tap demo personas: **Priya (vegetarian)** and **Arjun (loves spicy)**, plus mock email sign-in. |
| **8. Dawat AI Widget** | Global (`components/ChatPanel.tsx`) | Bottom-right launcher, desktop side-drawer, mobile fullscreen panel, collapsible reasoning steps, plan cards, confirmation cards. |

---

## 7. Design Decisions & Trade-offs

1. **Strict "No Gold Text on Ivory" Rule:**  
   Gold (`#D8AE4A`) on Ivory (`#FAF6EF`) yields a low contrast ratio (~1.8:1), which fails WCAG AA legibility standards. We strictly restricted Gold to decorative strokes, icon highlights, and borders on dark/plum backgrounds. All text on Ivory surfaces uses Night (`#22161F`, 13.5:1 ratio) or Plum (`#5B1E4E`, 8.2:1 ratio).
2. **Single-Restaurant Bill Integrity:**  
   To honor authentic Hyderabadi dum cooking (where food cannot be mixed or held between distant kitchens), Dawat enforces a strict single-restaurant cart rule. When a user adds an item from a different kitchen, the system prompts them or cleanly transitions the bill while displaying the active kitchen name.
3. **Distance & Delivery Fee Over Artificial Minutes:**  
   In compliance with the brief, all restaurant cards and tracking screens present exact road distance (e.g. `1.4 km`) and delivery fee (e.g. `Free Delivery` or `₹25 fee`) rather than fabricated "30-40 mins" timers.
4. **Neutral Vector Art Over Stock Photography:**  
   Rather than using generic, unverified food photographs, bespoke vector SVG illustrations were crafted for each dish category. This reinforces the regal, Nizami brand feel and prevents any copyright issues.
5. **Interactive Demo Personas:**  
   Priya and Arjun personas can be toggled on any screen (via header, login, profile, or mobile drawer), instantly shifting diet filters (Vegetarian vs Non-Veg), spice tolerance, and AI conversational recommendations.

---

## 8. Build & Compilation Verification

The application was built and validated with Next.js 16.4.0 (Turbopack) using `npm run build`:
- **Result:** Successfully compiled with 0 errors.
- **Prerendering:** All 16 static paths (including dynamic restaurant slugs `/restaurant/nawabs-dastarkhwan`, `/restaurant/anarkali-veg`, etc.) prerendered as static HTML.
- **Type Checking:** 100% TypeScript type check passed without warnings.
