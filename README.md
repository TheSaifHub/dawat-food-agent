# Dawat

*Every order, a feast.*

A Hyderabad food ordering **native mobile app (iOS and Android)** with an agentic ordering assistant, **Dawat AI**. Portfolio project, work in progress.

> Demo project. Menus, prices and orders are simulated. Not affiliated with any restaurant.

## What it is
Tell Dawat AI what you want ("₹500, 2 people, one veg, something spicy") or browse real Hyderabad restaurants. Dawat AI plans, fills your cart, and only places the order after you explicitly say yes. Payment is a simulated test payment: no real money.

## Layout
- `backend/` FastAPI, tools layer, meal planner, Dawat AI agent, tests (complete through Phase 8 backend work)
- `mobile/` Expo React Native app (planned; see `docs/MOBILE_PLAN.md`)
- `data_pipeline/`, `data/`, `evals/`, `docs/`, `results/`
- `frontend/`, `frontend_old/` legacy web reference (read-only, not part of the product)

Design reference: `docs/design/mobile_flow_v2.png`. Client rules: `docs/MOBILE_RULES.md`. API: `docs/API_CONTRACT.md`.

## Status
Backend and data are built and tested. The native app is being planned (pivot from web on 2026-10-15, see `DECISIONS.md` D-068). Install and run instructions will be added when the app exists.

Restaurant names and locations © OpenStreetMap contributors (ODbL). Everything else (menus, prices, users, orders, payments, tracking) is simulated.
