"""Build the dev chat preview's fixture (frontend/src/app/dev/chat-preview/fixture.json, Phase 7f, D-058) from REAL
tool output on the LOCAL test database (D-052), inside a rolled-back transaction. Run from backend/:

    ..\.venv\Scripts\python chat_preview_fixture.py


The plan options and both cards come from plan_meal / cards.* exactly as the chat would send them; only the reply
texts and the step timings are written by hand (they are the model's part)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import psycopg
from psycopg.rows import dict_row

from app.localdb import is_local, test_dsn
from app.agent import cards
from app.planner.plan import plan_meal

dsn = test_dsn()
assert dsn and is_local(dsn), "local test database only"
REQUEST = {"budget": 900, "people": 2, "veg_count": 1, "spice_preference": "spicy", "area": "Madhapur"}

with psycopg.connect(dsn, row_factory=dict_row, prepare_threshold=None) as conn:
    with conn.transaction(force_rollback=True):
        result = plan_meal(conn, REQUEST, None)
assert result["status"] == "ok", result["status"]
plans = cards.plan_options(result)
first = result["plans"][0]
plan_card = cards.plan_card(first, REQUEST, False, [], None, result["delivery"])
order_card = cards.order_card({"status": "ok", "can_confirm": True, "cart_id": "preview-cart", "quote_id": "preview-quote",
                               "grand_total": first["grand_total"], "delivery": {"area": result["delivery"].get("area") or "Madhapur"},
                               "branches": first["restaurants"]})

steps_plan = [
    {"step": 1, "tool": "plan_meal", "arguments": REQUEST, "status": "ok", "ok": True, "latency_ms": 1840,
     "counts": {"plans_count": len(result["plans"])}},
]
steps_order = [
    {"step": 1, "tool": "add_plan_to_cart", "arguments": {"plan_id": first["plan_id"]}, "status": "ok", "ok": True,
     "latency_ms": 420, "counts": {}},
    {"step": 2, "tool": "view_cart", "arguments": {}, "status": "ok", "ok": True, "latency_ms": 95, "counts": {"branches_count": len(first["restaurants"])}},
]
live = [{"step": 1, "tool": "search_dishes", "arguments": {"query": "paneer tikka", "area": "Madhapur"}, "status": "ok",
         "ok": True, "latency_ms": 310, "counts": {"results_count": 9}}]

fixture = {
    "_note": "Dev preview only. Plans and cards: real plan_meal output from the local test DB; reply texts: hand-written.",
    "messages": [
        {"id": 1, "role": "user", "text": "₹900 for 2 people, one is vegetarian, something spicy, Madhapur"},
        {"id": 2, "role": "assistant", "status": "ok", "steps": steps_plan, "card": None, "plans": plans,
         "text": "Here are **three plans** for 2 in Madhapur, all within ₹900:\n\n- Best value keeps the most budget left\n"
                 "- Best match fits the spice best\n- Variety mixes it up\n\nWhich one would you like?"},
        {"id": 3, "role": "user", "text": f"I'll take the “{first['label']}” plan (₹{first['grand_total']})."},
        {"id": 4, "role": "assistant", "status": "ok", "steps": steps_order, "card": order_card, "plans": None,
         "text": f"Added the {first['label']} plan to your cart. Shall I place the order?"},
    ],
    "plan_card": plan_card,
    "live_steps": live,
}
out = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "dev" / "chat-preview" / "fixture.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(fixture, ensure_ascii=False, indent=1, default=str), encoding="utf-8", newline="\n")
print("plans", [(p["label"], p["grand_total"]) for p in plans], "->", out)
