"""Break every database guard on purpose and prove it refuses (D-020). Also runs positive controls, so a guard
that blocks EVERYTHING would be caught too. Needs the seeded database (data_pipeline/load_db.py).

Everything happens inside ONE transaction that is always rolled back: no test data is ever left behind.
It runs on the LOCAL test database (TEST_DATABASE_URL) only, never Supabase (D-052).
Each case runs in its own savepoint; deferred checks are forced with SET CONSTRAINTS ALL IMMEDIATE.

Run from the project root:
    .venv\\Scripts\\python backend\\db\\test_triggers.py
"""

import sys
import uuid
from pathlib import Path

import psycopg

results = []


def case(conn, label, fn, expect_error=None):
    """expect_error=None → must succeed (control); a string → must fail with a message containing it."""
    try:
        with conn.transaction():                       # savepoint; rolled back if fn raises
            # SET CONSTRAINTS lasts for the whole outer transaction (a savepoint doesn't undo it), so every case
            # starts deferred again, exactly like a fresh order transaction in the app. Only the two total
            # checks are deferrable, so "all" affects nothing else.
            conn.execute("set constraints all deferred")
            fn()
            conn.execute("set constraints all immediate")  # run deferred total checks now
        outcome = "ok"
    except psycopg.Error as e:
        outcome = f"refused: {(e.diag.message_primary or str(e)).strip()}"
    if expect_error is None:
        passed = outcome == "ok"
    else:
        passed = outcome.startswith("refused") and expect_error in outcome
    results.append(passed)
    print(f"  {'PASS' if passed else 'FAIL'}  {label}\n        → {outcome}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.localdb import require_test_dsn               # D-052: the local test database, never Supabase
    with psycopg.connect(require_test_dsn(), connect_timeout=15) as conn:
        before = conn.execute("select (select count(*) from public.carts), (select count(*) from public.orders), "
                              "(select count(*) from public.menu_items)").fetchone()
        with conn.transaction(force_rollback=True):
            a, b = [r[0] for r in conn.execute("select user_id from public.users where is_demo order by display_name limit 2")]
            q = lambda sql, *p: conn.execute(sql, p).fetchone()  # noqa: E731
            p_branch = q("select branch_id from public.branches where restaurant_id = 'r-paradise' order by branch_id limit 1")[0]
            p_branch2 = q("select branch_id from public.branches where restaurant_id = 'r-paradise' order by branch_id desc limit 1")[0]
            biryani_id, biryani_price = q("select item_id, price from public.menu_items where item_id = 'r-paradise__chicken-dum-biryani'")
            raita_id = q("select item_id from public.menu_items where restaurant_id = 'r-paradise' and dish_id = 'raita'")[0]
            k_item = q("select item_id from public.menu_items where restaurant_id = 'r-kfc' limit 1")[0]
            veg_rid = "r-sri-raghavendra-udipi-veg-n6765562773"
            veg_dish_on_veg_menu = q("select dish_id from public.menu_items where restaurant_id = %s order by dish_id limit 1", veg_rid)[0]
            cart = uuid.uuid4()
            total = 2 * biryani_price

            def new_order(user, branch, items_total, fee=40, taxes=None, grand=None, lines=((biryani_id, 2),)):
                taxes = round(items_total * 0.05) if taxes is None else taxes
                grand = items_total + fee + taxes if grand is None else grand
                oid = uuid.uuid4()
                # delivery_* columns: required since 0007 (D-026); a fixed point in Madhapur is enough here
                conn.execute("insert into public.orders (order_id, checkout_id, user_id, cart_id, branch_id, items_total, "
                             "delivery_fee, taxes, grand_total, delivery_area_id, delivery_lat, delivery_lon) "
                             "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'madhapur', 17.44, 78.39)",
                             (oid, uuid.uuid4(), user, cart, branch, items_total, fee, taxes, grand))
                for item, qty in lines:
                    price = q("select price from public.menu_items where item_id = %s", item)[0]
                    conn.execute("insert into public.order_items (order_id, item_id, dish_name, unit_price, qty, is_veg) "
                                 "select %s, m.item_id, d.name, %s, %s, d.is_veg from public.menu_items m "
                                 "join public.dishes d using (dish_id) where m.item_id = %s", (oid, price, qty, item))

            print("Confirmation gate and cart rules")
            case(conn, "control: open a cart and add 2 × Paradise Chicken Dum Biryani", lambda: (
                conn.execute("insert into public.carts (cart_id, user_id) values (%s, %s)", (cart, a)),
                conn.execute("insert into public.cart_items (cart_id, item_id, branch_id, qty) values (%s, %s, %s, 2)",
                             (cart, biryani_id, p_branch))))
            case(conn, "BREAK: place an order from the OPEN (unconfirmed) cart",
                 lambda: new_order(a, p_branch, total), "not confirmed")
            case(conn, "BREAK: add a KFC item at a Paradise branch",
                 lambda: conn.execute("insert into public.cart_items (cart_id, item_id, branch_id, qty) values (%s, %s, %s, 1)",
                                      (cart, k_item, p_branch)), "is not on the menu of branch")
            case(conn, "BREAK: open a second cart for the same user",
                 lambda: conn.execute("insert into public.carts (user_id) values (%s)", (a,)), "carts_one_open_per_user_idx")
            case(conn, "control: user says yes → cart confirmed",
                 # since 0007 (D-026) a confirmation must record the quote and total that were confirmed
                 lambda: conn.execute("update public.carts set status = 'confirmed', confirmed_at = now(), "
                                      "confirmed_total = 0, confirmed_quote = repeat('0', 20) where cart_id = %s", (cart,)))
            case(conn, "BREAK: slip an extra item into the cart AFTER the yes",
                 lambda: conn.execute("insert into public.cart_items (cart_id, item_id, branch_id, qty) values (%s, %s, %s, 1)",
                                      (cart, raita_id, p_branch)), "items can only change while it is open")
            case(conn, "BREAK: another user places an order from this cart",
                 lambda: new_order(b, p_branch, total), "belongs to another user")
            case(conn, "BREAK: order for a branch that has no items in the cart",
                 lambda: new_order(a, p_branch2, total), "has no items from branch")

            print("Totals")
            case(conn, "BREAK: items_total ₹999 but the items add up to less", lambda: new_order(a, p_branch, 999), "items add up to")
            case(conn, "BREAK: grand_total ≠ items + delivery + taxes",
                 lambda: new_order(a, p_branch, total, grand=total + 1), "orders_check")
            case(conn, f"control: correct order from the confirmed cart (₹{total} + ₹40 + 5% tax)",
                 lambda: new_order(a, p_branch, total))

            print("Veg promise and prices")
            case(conn, "BREAK: put Chicken Dum Biryani on a veg-only Udupi menu",
                 lambda: conn.execute("insert into public.menu_items (item_id, restaurant_id, dish_id, price) values (%s, %s, %s, 300)",
                                      (f"{veg_rid}__chicken-dum-biryani", veg_rid, "chicken-dum-biryani")), "veg-only restaurant")
            case(conn, "control: put Veg Dum Biryani on the same veg-only menu",
                 lambda: conn.execute("insert into public.menu_items (item_id, restaurant_id, dish_id, price) values (%s, %s, %s, 250)",
                                      (f"{veg_rid}__veg-dum-biryani", veg_rid, "veg-dum-biryani")))
            case(conn, f"BREAK: mark '{veg_dish_on_veg_menu}' (on a veg-only menu) as non-veg",
                 lambda: conn.execute("update public.dishes set is_veg = false where dish_id = %s", (veg_dish_on_veg_menu,)),
                 "cannot become non-veg")
            case(conn, "BREAK: switch Paradise (has chicken) to veg-only",
                 lambda: conn.execute("update public.restaurants set veg_only = true where restaurant_id = 'r-paradise'"),
                 "cannot become veg-only")
            case(conn, "BREAK: price Paradise's Chicken Dum Biryani at ₹99 (range ₹220–420)",
                 lambda: conn.execute("update public.menu_items set price = 99 where item_id = %s", (biryani_id,)), "outside dish range")
            case(conn, "BREAK: save 'max_spice' = 7 as a preference",
                 lambda: conn.execute("insert into public.user_preferences (user_id, key, value, source) values (%s, 'max_spice', '7', 'settings') "
                                      "on conflict (user_id, key) do update set value = excluded.value", (a,)), "user_preferences_check")
        after = conn.execute("select (select count(*) from public.carts), (select count(*) from public.orders), "
                             "(select count(*) from public.menu_items)").fetchone()

    print(f"\nRolled back. carts/orders/menu_items before {tuple(before)} → after {tuple(after)} "
          f"({'unchanged' if before == after else 'CHANGED!'})")
    ok = all(results) and before == after
    print(f"{sum(results)}/{len(results)} cases behaved as expected. " + ("ALL GUARDS WORK" if ok else "SOMETHING IS WRONG"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
