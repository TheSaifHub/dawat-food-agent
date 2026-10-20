"""D-053: the in-memory reference copy (menus included) must always equal the database, reload only when the
database's version stamp changes, and never be used for money (cart prices) or by the planner's own checker."""

import pytest

from app import config
from app.tools import reference
from app.tools.cart import add_to_cart, view_cart
from app.tools.menu import get_menu


def version(db):
    return db.execute("select version::text as v from public.reference_version where id = 1").fetchone()["v"]


def a_branch_item(db):
    return db.execute("""select b.branch_id, m.item_id, m.restaurant_id, m.price from public.branches b
                         join public.menu_items m using (restaurant_id)
                         where b.open_for_demo and m.is_available and b.area_id = 'madhapur'
                         order by m.item_id limit 1""").fetchone()


@pytest.fixture(autouse=True)
def fresh_cache():
    reference.clear_reference_cache()
    yield
    reference.clear_reference_cache()


def test_every_reference_table_change_stamps_a_new_version(db):
    seen = {version(db)}
    for stmt in ("update public.menu_items set price = price + 1 where item_id = (select min(item_id) from public.menu_items)",
                 "update public.branches set street = street where branch_id = (select min(branch_id) from public.branches)",
                 "update public.dishes set notes = notes where dish_id = (select min(dish_id) from public.dishes)",
                 "update public.areas set name = name where area_id = 'madhapur'"):
        db.execute(stmt)
        v = version(db)
        assert v not in seen, stmt
        seen.add(v)


def test_user_tables_do_not_stamp_a_version(db, demo_users):
    before = version(db)
    db.execute("update public.users set display_name = display_name where user_id = %s", (demo_users[0],))
    assert version(db) == before


def test_the_cached_menus_equal_the_database_row_for_row_in_order(db):
    ref = reference.get_reference(db)
    rows = db.execute("""select m.item_id, m.restaurant_id, m.dish_id, m.price, d.name, d.is_veg, d.spice_level,
                                d.serves, d.category, d.course
                         from public.menu_items m join public.dishes d using (dish_id)
                         where m.is_available order by m.restaurant_id, m.price, m.item_id""").fetchall()
    by_restaurant = {}
    for r in rows:
        by_restaurant.setdefault(r["restaurant_id"], []).append(dict(r))
    cached = {rid: [{k: i[k] for k in rows[0].keys()} for i in ref.available(rid)] for rid in ref.menus}
    cached = {rid: items for rid, items in cached.items() if items}
    assert cached == by_restaurant
    assert sum(len(v) for v in cached.values()) == len(rows) > 20_000


def test_a_menu_change_is_seen_at_once_in_tests_and_undone_after(db):
    it = a_branch_item(db)
    menu = lambda: {i["item_id"]: i["price"] for i in get_menu(db, it["branch_id"])["items"]}   # noqa: E731
    assert menu()[it["item_id"]] == it["price"]
    db.execute("update public.menu_items set price = price + 7 where item_id = %s", (it["item_id"],))
    assert menu()[it["item_id"]] == it["price"] + 7
    db.execute("update public.menu_items set is_available = false where item_id = %s", (it["item_id"],))
    assert it["item_id"] not in menu()


def test_the_version_is_read_at_most_every_check_interval(db, monkeypatch):
    calls = []
    real = reference.current_version
    monkeypatch.setattr(reference, "current_version", lambda c: calls.append(1) or real(c))
    monkeypatch.setattr(config, "REFERENCE_CHECK_S", 60)
    first = reference.get_reference(db)
    n = len(calls)
    for _ in range(5):
        assert reference.get_reference(db) is first
    assert len(calls) == n                                      # within 60 s: no version read at all


def test_an_unchanged_version_never_reloads(db, monkeypatch):
    first = reference.get_reference(db)
    loads = []
    monkeypatch.setattr(reference, "load_reference", lambda c: loads.append(1))
    for _ in range(3):
        assert reference.get_reference(db) is first
    assert loads == []


def test_before_migration_0010_it_falls_back_to_the_hourly_reload(db, monkeypatch):
    monkeypatch.setattr(reference, "current_version", lambda c: None)
    first = reference.get_reference(db)
    assert first.version is None
    db.execute("update public.menu_items set price = price + 1 where item_id = (select min(item_id) from public.menu_items)")
    assert reference.get_reference(db) is first                 # no stamp to read: waits for the hourly reload


def test_cart_prices_are_live_even_when_the_cache_is_stale(db, demo_users, monkeypatch):
    """Money never comes from the copy: with the copy frozen, the cart still bills today's database price."""
    monkeypatch.setattr(config, "REFERENCE_CHECK_S", 3600)
    it = a_branch_item(db)
    reference.get_reference(db)                                 # loaded, then frozen for an hour
    db.execute("update public.menu_items set price = price + 11 where item_id = %s", (it["item_id"],))
    assert {i["item_id"]: i["price"] for i in get_menu(db, it["branch_id"])["items"]}[it["item_id"]] == it["price"]
    user = demo_users[0]
    db.execute("delete from public.cart_items where cart_id in (select cart_id from public.carts where user_id = %s)",
               (user,))
    add_to_cart(db, user, it["item_id"], it["branch_id"])
    cart = view_cart(db, user)
    line = next(i for b in cart["branches"] for i in b["items"] if i["item_id"] == it["item_id"])
    assert line["price"] == it["price"] + 11
