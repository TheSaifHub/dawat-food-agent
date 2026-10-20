"""The website routes (D-027): thin wrappers over the tools layer.

Without a database: every private route refuses a missing token before opening a connection (the list of routes
comes from the app itself, so a new route is covered automatically), every status a tool can return has an HTTP
code, and a commit that fails is reported as an error, never as success.
With the database (rolled back): browsing is public; the whole order flow works over HTTP with the same gate as
the chat; bodies can't carry a price, a user id or a preference source; and one user can't see or change another
user's cart, orders or preferences through any route."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.auth import get_verifier
from app.db import get_conn
from app.main import app
from tests.test_orders import item

client = TestClient(app)
PUBLIC = {("get", "/health"), ("get", "/areas"), ("get", "/restaurants"), ("get", "/dishes"),
          ("get", "/branches/{branch_id}/menu"), ("post", "/plans"),
          ("get", "/areas/{area_id}/home"), ("get", "/areas/{area_id}/restaurants"),
          ("get", "/branches/{branch_id}")}
DUMMY_BODIES = {"/cart/items": {"item_id": "x", "branch_id": "y"}, "/cart/delivery": {"area": "Madhapur"},
                "/cart/confirm": {"cart_id": "x", "quote_id": "y"}, "/orders": {"cart_id": "x"},
                "/me/preferences/{key}": {"value": "veg"}, "/cart/plan": {"request": {}, "plan_id": "x"},
                "/chat": {"message": "hi"},
                "/payments/start": {"cart_id": "x"},
                "/payments/simulate": {"razorpay_order_id": "order_x", "outcome": "success", "method": "upi", "upi_id": "success@razorpay"},
                "/payments/verify": {"razorpay_order_id": "order_x", "razorpay_payment_id": "pay_x", "razorpay_signature": "a" * 64}}


def operations():
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            yield method, path


def concrete(path: str) -> str:
    return re.sub(r"\{[a-z_]+\}", "x1", path)


def use(verifier, conn=None):
    app.dependency_overrides[get_verifier] = lambda: verifier
    if conn is None:
        def no_db():
            raise AssertionError("a rejected request must not open a database connection")
            yield  # noqa: unreachable; makes this a generator dependency like get_conn
        app.dependency_overrides[get_conn] = no_db
    else:
        def test_db():
            yield conn
        app.dependency_overrides[get_conn] = test_db


def call(method, path, token=None, headers=None, **kw):
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method.upper(), path, headers={**(headers or {}), **auth}, **kw)


# ── without a database ───────────────────────────────────────────────────
def test_the_public_routes_are_exactly_the_browsing_ones():
    ops = set(operations())
    assert PUBLIC <= ops
    assert len(ops - PUBLIC) == 19                    # the private routes: /demo/start is gone (D-064), /me/name is new
    assert {p for _, p in ops - PUBLIC} == {"/me", "/cart", "/cart/items", "/cart/items/{item_id}", "/cart/delivery",
                                           "/cart/confirm", "/cart/plan", "/orders", "/orders/{order_id}",
                                           "/me/preferences", "/me/preferences/{key}", "/chat",
                                           "/me/addresses", "/me/name", "/payments/start", "/payments/verify", "/payments/simulate"}


@pytest.mark.parametrize("method, path", sorted(set(operations()) - PUBLIC))
def test_every_private_route_needs_a_token_and_opens_no_connection(verifier, method, path):
    use(verifier)
    r = call(method, concrete(path), json=DUMMY_BODIES.get(path))
    assert r.status_code == 401, (method, path, r.text)
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method, path", sorted(set(operations()) - PUBLIC))
def test_a_forged_token_is_refused_everywhere(verifier, make_token, attacker_key, method, path):
    use(verifier)
    r = call(method, concrete(path), make_token(key=attacker_key), json=DUMMY_BODIES.get(path))
    assert r.status_code == 401


def test_every_status_a_tool_can_return_has_an_http_code():
    app_dir = Path(__file__).resolve().parent.parent / "app"
    found = set()
    for p in [*app_dir.glob("tools/*.py"), *app_dir.glob("planner/*.py")]:
        found |= set(re.findall(r'"status": "([a-z_]+)"', p.read_text(encoding="utf-8")))
    found |= deps.AREA_ANSWERS | {"ok"}               # resolve_area's statuses, passed through by several tools
    assert len(found) > 30
    assert found <= set(deps.STATUS_CODES), sorted(found - set(deps.STATUS_CODES))


def test_an_unmapped_status_is_a_generic_500():
    r = deps.respond({"status": "something_new", "secret": "internal detail"})
    assert r.status_code == 500 and b"internal detail" not in r.body


def test_an_unresolved_area_means_a_write_did_not_happen():
    for s in deps.AREA_ANSWERS:
        assert deps.respond({"status": s}).status_code == 200
        assert deps.respond({"status": s}, write=True).status_code == 422


# ── with the database ────────────────────────────────────────────────────
@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "family": family, "priya": priya}


@pytest.fixture
def as_user(db, users, verifier, make_token):
    use(verifier, db)
    return {name: make_token(uid) for name, uid in users.items()}


def test_a_failed_commit_is_reported_as_an_error_not_success(db, users, verifier, make_token):
    """get_conn commits when the route finishes. If that commit fails, the user must get an error. With FastAPI's
    default dependency scope the response would already have been sent as a success."""
    app.dependency_overrides[get_verifier] = lambda: verifier

    def failing_commit():
        yield db
        raise RuntimeError("commit failed")
    app.dependency_overrides[get_conn] = failing_commit
    r = TestClient(app, raise_server_exceptions=False).get("/cart", headers={"Authorization": f"Bearer {make_token(users['priya'])}"})
    assert r.status_code == 500


def test_one_connection_per_request(db, users, verifier, make_token):
    """The user check and the route share ONE connection (one transaction), so the profile created on a first
    request is visible to the cart tool in the same request."""
    app.dependency_overrides[get_verifier] = lambda: verifier
    opened = []

    def counting():
        opened.append(1)
        yield db
    app.dependency_overrides[get_conn] = counting
    assert call("get", "/cart", make_token(users["priya"])).status_code == 200
    assert len(opened) == 1


def test_browsing_needs_no_sign_in(db, verifier):
    use(verifier, db)
    areas = call("get", "/areas").json()["areas"]
    assert {"area_id": "madhapur", "name": "Madhapur"}.items() <= next(a for a in areas if a["area_id"] == "madhapur").items()
    r = call("get", "/dishes", params={"q": "chicken biryani", "area": "Madhapur", "max_price": 400})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert all(x["price"] <= 400 for x in r.json()["results"])
    branch = r.json()["results"][0]["branch"]["branch_id"]
    menu = call("get", f"/branches/{branch}/menu", params={"is_veg": True})
    assert menu.status_code == 200 and menu.json()["status"] == "ok"
    r = call("get", "/restaurants", params={"q": "paradise"})
    assert r.status_code == 200 and r.json()["status"] != "invalid_input"


@pytest.mark.parametrize("path, params, code", [
    ("/dishes", {"q": "biryani"}, 200),                              # needs_area: an answer, not an error
    ("/dishes", {"q": "biryani", "area": "Madhapur", "max_spice": 5}, 422),
    ("/dishes", {"q": "", "area": "Madhapur"}, 422),
    ("/dishes", {"q": "x" * 201, "area": "Madhapur"}, 422),
    ("/branches/not-a-branch/menu", {}, 422),
    ("/branches/b-n1/menu", {"is_veg": "maybe"}, 422),
    ("/restaurants", {}, 422),
])
def test_browsing_input_is_validated(db, verifier, path, params, code):
    use(verifier, db)
    assert call("get", path, params=params).status_code == code


@pytest.fixture
def pay_for(monkeypatch):
    """Test-mode payment for a confirmed cart over HTTP, with Razorpay replaced by a stub (no network). D-061."""
    import hashlib
    from app import config
    from app.payments import razorpay
    secret = hashlib.sha256(b"dawat-routes-test").hexdigest()[:32]
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "rzp_" + "test_ROUTES123456")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", secret)
    made = []

    def post(url, body, kid, key):
        made.append(body["amount"])
        return {"id": f"order_Routes{len(made):03d}", "amount": body["amount"], "currency": "INR"}
    monkeypatch.setattr(razorpay, "_post", post)

    def pay(user_token, cart):
        s = call("post", "/payments/start", user_token, json={"cart_id": cart["cart_id"]}).json()
        sig = razorpay.sign(s["razorpay_order_id"], "pay_Routes1", secret)
        return call("post", "/payments/verify", user_token, json={
            "razorpay_order_id": s["razorpay_order_id"], "razorpay_payment_id": "pay_Routes1", "razorpay_signature": sig})
    return pay



def test_the_whole_order_flow_over_http(db, as_user, pay_for):
    priya = as_user["priya"]
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    r = call("post", "/cart/items", priya, json={"item_id": item_id, "branch_id": branch_id, "qty": 2})
    assert r.status_code == 200 and r.json()["cart"]["branches"][0]["items"][0]["qty"] == 2
    cart = call("get", "/cart", priya).json()
    assert call("post", "/orders", priya, json={"cart_id": cart["cart_id"]}).status_code == 409        # not confirmed
    r = call("post", "/cart/confirm", priya, json={"cart_id": cart["cart_id"], "quote_id": cart["quote_id"]})
    assert r.status_code == 200
    r = call("post", "/orders", priya, json={"cart_id": cart["cart_id"]})
    assert r.status_code == 409 and r.json()["status"] == "payment_required" and r.json()["grand_total"] == cart["grand_total"]
    assert call("get", "/orders", priya).json()["status"] == "empty"                # nothing ordered until it is paid (D-061)
    r = pay_for(priya, cart)
    assert r.status_code == 200 and r.json()["grand_total"] == cart["grand_total"]
    order_id = r.json()["orders"][0]["order_id"]
    again = call("post", "/orders", priya, json={"cart_id": cart["cart_id"]})
    assert again.status_code == 200 and again.json()["status"] == "already_placed"
    history = call("get", "/orders", priya).json()
    assert history["checkouts"][0]["checkout_id"] == r.json()["checkout_id"]
    track = call("get", f"/orders/{order_id}", priya)
    assert track.status_code == 200 and track.json()["total"] == cart["grand_total"]


def test_the_gate_over_http(db, as_user):
    priya = as_user["priya"]
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    call("post", "/cart/items", priya, json={"item_id": item_id, "branch_id": branch_id})
    cart = call("get", "/cart", priya).json()
    r = call("post", "/cart/confirm", priya, json={"cart_id": cart["cart_id"], "quote_id": "0" * 20})
    assert r.status_code == 409 and r.json()["status"] == "stale_quote"
    call("post", "/cart/confirm", priya, json={"cart_id": cart["cart_id"], "quote_id": cart["quote_id"]})
    db.execute("update public.menu_items set price = price + 10 where item_id = %s", (item_id,))
    r = call("post", "/orders", priya, json={"cart_id": cart["cart_id"]})
    assert r.status_code == 409 and r.json()["status"] == "quote_changed"
    assert r.json()["new_total"] > r.json()["confirmed_total"]
    assert db.execute("select status from public.carts where cart_id = %s", (cart["cart_id"],)).fetchone()["status"] == "open"
    assert db.execute("select count(*) as n from public.orders where cart_id = %s", (cart["cart_id"],)).fetchone()["n"] == 0


@pytest.mark.parametrize("extra", [{"price": 1}, {"unit_price": 1}, {"total": 1}, {"user_id": "someone"}, {"qty": "2"},
                                   {"qty": 0}, {"qty": 21}, {"qty": True}])
def test_a_cart_body_cannot_carry_a_price_or_a_user(db, as_user, users, extra):
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    r = call("post", "/cart/items", as_user["priya"], json={"item_id": item_id, "branch_id": branch_id, **extra})
    assert r.status_code == 422
    assert db.execute("select count(*) as n from public.cart_items ci join public.carts c using (cart_id) "
                      "where c.user_id = %s", (users["priya"],)).fetchone()["n"] == 0


def test_cart_answers_map_to_http_codes(db, as_user):
    priya = as_user["priya"]
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    assert call("post", "/cart/items", priya, json={"item_id": "r-nope__nope", "branch_id": branch_id}).status_code == 404
    assert call("post", "/cart/items", priya, json={"item_id": "bad id", "branch_id": branch_id}).status_code == 422
    assert call("delete", f"/cart/items/{item_id}", priya).status_code == 404                 # not in the cart
    call("post", "/cart/items", priya, json={"item_id": item_id, "branch_id": branch_id})
    assert call("delete", f"/cart/items/{item_id}", priya).status_code == 200
    r = call("put", "/cart/delivery", priya, json={"area": "Manikonda"})
    assert r.status_code == 422 and r.json()["status"] == "outside_coverage"
    assert call("put", "/cart/delivery", priya, json={"area": "Kondapur"}).json()["cart"]["delivery"]["area"] == "Kondapur"
    assert call("put", "/cart/delivery", priya, json={"area": "Kondapur", "address_id": "x"}).status_code == 422


def test_one_user_cannot_reach_another_users_cart_or_orders(db, as_user, users, pay_for):
    priya, arjun = as_user["priya"], as_user["arjun"]
    item_id, branch_id = item(db, "Hi-Tech Bawarchi", "Chicken Dum Biryani", "madhapur")
    call("post", "/cart/items", priya, json={"item_id": item_id, "branch_id": branch_id})
    cart = call("get", "/cart", priya).json()
    stolen = {"cart_id": cart["cart_id"], "quote_id": cart["quote_id"]}
    assert call("post", "/cart/confirm", arjun, json=stolen).status_code == 404
    call("post", "/cart/confirm", priya, json=stolen)
    assert call("post", "/orders", arjun, json={"cart_id": cart["cart_id"]}).status_code == 404
    assert call("post", "/payments/start", arjun, json={"cart_id": cart["cart_id"]}).status_code == 404
    placed = pay_for(priya, cart).json()
    order_id = placed["orders"][0]["order_id"]
    assert call("get", f"/orders/{order_id}", arjun).status_code == 404
    assert call("get", f"/orders/{order_id}?user_id={users['priya']}", arjun).status_code == 404
    assert placed["checkout_id"] not in {c["checkout_id"] for c in call("get", "/orders", arjun).json()["checkouts"]}
    assert call("get", "/cart", arjun).json().get("cart_id") != cart["cart_id"]


# ── preferences over HTTP ────────────────────────────────────────────────
def test_view_set_and_forget_preferences(db, as_user):
    arjun = as_user["arjun"]
    prefs = call("get", "/me/preferences", arjun).json()["preferences"]
    assert prefs["diet"]["value"] == "non_vegetarian"
    r = call("put", "/me/preferences/diet", arjun, json={"value": "veg"})
    assert r.status_code == 200 and r.json()["preferences"]["diet"] == {**r.json()["preferences"]["diet"],
                                                                         "value": "vegetarian", "source": "settings"}
    assert call("put", "/me/preferences/max_spice", arjun, json={"value": 1}).json()["value"] == 1
    assert call("delete", "/me/preferences/diet", arjun).json()["deleted"] == ["diet"]
    assert call("delete", "/me/preferences/diet", arjun).json()["status"] == "not_saved"
    assert call("delete", "/me/preferences/all", arjun).status_code == 200
    assert call("get", "/me/preferences", arjun).json()["preferences"] == {}


@pytest.mark.parametrize("key, body", [
    ("max_spice", {"value": True}), ("max_spice", {"value": 4}), ("max_spice", {"value": 1.5}),
    ("language", {"value": "hindi"}), ("default_area", {"value": "madhapoor"}), ("default_area", {"value": "Manikonda"}),
    ("email", {"value": "x"}), ("diet", {}), ("diet", {"value": None}),
    ("diet", {"value": "veg", "source": "chat_request"}), ("diet", {"value": "veg", "user_id": "someone"}),
])
def test_bad_preference_writes_are_refused_and_change_nothing(db, as_user, users, key, body):
    before = call("get", "/me/preferences", as_user["arjun"]).json()["preferences"]
    assert call("put", f"/me/preferences/{key}", as_user["arjun"], json=body).status_code == 422
    assert call("get", "/me/preferences", as_user["arjun"]).json()["preferences"] == before


def test_one_user_cannot_see_or_change_another_users_preferences(db, as_user, users):
    priya_before = call("get", "/me/preferences", as_user["priya"]).json()["preferences"]
    arjun = as_user["arjun"]
    mine = call("get", f"/me/preferences?user_id={users['priya']}", arjun).json()["preferences"]
    assert mine["diet"]["value"] == "non_vegetarian" != priya_before["diet"]["value"]       # still Arjun's own
    call("put", f"/me/preferences/language?user_id={users['priya']}", arjun, json={"value": "te"})
    call("delete", "/me/preferences/all", arjun, headers={"X-User-Id": str(users["priya"])})
    assert call("get", "/me/preferences", as_user["priya"]).json()["preferences"] == priya_before


# ── the meal planner over HTTP (5f) ───────────────────────────────────────
PLAN_REQUEST = {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "meal_type": "dinner",
                "area": "Madhapur"}


def test_plans_are_public_and_a_bad_token_is_still_refused(db, verifier, make_token, attacker_key):
    use(verifier, db)
    r = call("post", "/plans", json=PLAN_REQUEST)
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["delivery"]["address_id"] is None
    assert call("post", "/plans", make_token(key=attacker_key), json=PLAN_REQUEST).status_code == 401
    assert call("post", "/plans", headers={"Authorization": "Basic abc"}, json=PLAN_REQUEST).status_code == 401


@pytest.mark.parametrize("body, code, status", [
    ({**PLAN_REQUEST, "budget": "1000"}, 422, "invalid_input"),
    ({**PLAN_REQUEST, "price": 1}, 422, "invalid_input"),
    ({**PLAN_REQUEST, "area": None}, 200, "needs_info"),
    ({**PLAN_REQUEST, "area": "Manikonda"}, 200, "outside_coverage"),
    ({**PLAN_REQUEST, "budget": 150}, 200, "over_budget"),
])
def test_plan_answers_map_to_http_codes(db, verifier, body, code, status):
    use(verifier, db)
    r = call("post", "/plans", json=body)
    assert (r.status_code, r.json()["status"]) == (code, status)


def test_a_signed_in_plan_goes_into_the_cart_and_still_needs_the_yes(db, as_user, users):
    priya = as_user["priya"]
    plans = call("post", "/plans", priya, json=PLAN_REQUEST).json()
    assert plans["delivery"]["address_id"] is not None                 # Priya's Madhapur home
    pid = plans["plans"][1]["plan_id"]
    r = call("post", "/cart/plan", priya, json={"request": PLAN_REQUEST, "plan_id": pid})
    assert r.status_code == 200 and r.json()["cart"]["grand_total"] == plans["plans"][1]["grand_total"]
    assert r.json()["cart"]["cart_status"] == "open"
    again = call("post", "/cart/plan", priya, json={"request": PLAN_REQUEST, "plan_id": pid})
    assert again.status_code == 409 and again.json()["status"] == "cart_not_empty"
    cart = call("get", "/cart", priya).json()
    assert call("post", "/orders", priya, json={"cart_id": cart["cart_id"]}).status_code == 409   # not confirmed
    # The website's "Replace cart" click is the yes: the route replaces without a chat message (source="website").
    other = plans["plans"][0]
    swapped = call("post", "/cart/plan", priya, json={"request": PLAN_REQUEST, "plan_id": other["plan_id"],
                                                      "replace": True})
    assert swapped.status_code == 200 and swapped.json()["cart"]["grand_total"] == other["grand_total"]


@pytest.mark.parametrize("body", [
    {"request": PLAN_REQUEST, "plan_id": "x", "price": 1},
    {"request": PLAN_REQUEST, "plan_id": "x", "items": [{"item_id": "a", "qty": 1}]},
    {"request": PLAN_REQUEST, "plan_id": "x", "replace": "true"},
    {"request": PLAN_REQUEST, "plan_id": "x", "user_id": "someone"},
    {"request": PLAN_REQUEST, "plan_id": "x", "source": "chat"},          # the browser can't pick the source
    {"request": PLAN_REQUEST, "plan_id": "x", "user_message": "yes"},     # nor write the user's "yes"
])
def test_a_plan_body_cannot_carry_items_prices_or_a_user(db, as_user, users, body):
    assert call("post", "/cart/plan", as_user["priya"], json=body).status_code == 422
    assert db.execute("select count(*) as n from public.carts where user_id = %s", (users["priya"],)).fetchone()["n"] == 0


def test_add_plan_answers_map_to_http_codes(db, as_user):
    priya = as_user["priya"]
    r = call("post", "/cart/plan", priya, json={"request": PLAN_REQUEST, "plan_id": "0" * 20})
    assert r.status_code == 409 and r.json()["status"] == "plan_changed"
    r = call("post", "/cart/plan", priya, json={"request": {**PLAN_REQUEST, "area": None}, "plan_id": "0" * 20})
    assert r.status_code == 422 and r.json()["status"] == "needs_info"                 # nothing was added
    r = call("post", "/cart/plan", priya, json={"request": {**PLAN_REQUEST, "area": "madhapoor"}, "plan_id": "0" * 20})
    assert r.status_code == 422 and r.json()["status"] == "confirm_area"
