"""Simulated order progress and the rider's position (Phase 8, D-061). There is no kitchen and no rider: this is a
clock. A PAID order moves through Confirmed → Preparing → Picked up → On the way → Delivered about six minutes after
it was placed, and the "rider" moves in a straight line from the restaurant to the delivery point.

Why computed on read: the free Render tier sleeps and has no background worker. Whenever the user opens an order or
their history, the events that are already due get written (idempotent, one row per status, stamped with the moment
they were due, not "now"), so the timeline is the same whenever and however often it is read.

What is never simulated: unpaid orders and the demo accounts' sample orders do not move; the clock never starts before
payment is verified. Nothing here invents an ETA: the API says there is none and that the progress is simulated.
"""

import math
import uuid

from psycopg import Connection

# (status, seconds after the order was placed). Steps are 45 to 90 s apart, six minutes in all (Saif, Session 21).
SCHEDULE = (("confirmed", 60), ("preparing", 135), ("picked_up", 225), ("on_the_way", 270), ("delivered", 360))
FINAL = ("delivered", "cancelled")
PICKED_UP_S, ON_THE_WAY_S, DELIVERED_S = 225, 270, 360


def due_statuses(age_s: float) -> list[tuple[str, int]]:
    """The scheduled steps whose time has come after `age_s` seconds."""
    return [(s, off) for s, off in SCHEDULE if off <= age_s]


def next_update_in(age_s: float) -> int | None:
    """Whole seconds until the next step, or None once delivered."""
    for _s, off in SCHEDULE:
        if off > age_s:
            return math.ceil(off - age_s)
    return None


def rider_position(age_s: float, start: tuple[float, float], end: tuple[float, float]) -> dict | None:
    """Where the simulated rider is: None before pickup; at the restaurant while picked up; moving in a straight line
    while on the way; at the delivery point once delivered."""
    if age_s < PICKED_UP_S:
        return None
    if age_s < ON_THE_WAY_S:
        return {"lat": start[0], "lon": start[1], "stage": "picked_up"}
    if age_s >= DELIVERED_S:
        return {"lat": end[0], "lon": end[1], "stage": "delivered"}
    t = (age_s - ON_THE_WAY_S) / (DELIVERED_S - ON_THE_WAY_S)
    return {"lat": round(start[0] + (end[0] - start[0]) * t, 6), "lon": round(start[1] + (end[1] - start[1]) * t, 6),
            "stage": "on_the_way"}


def advance(conn: Connection, user_id: uuid.UUID, order_id: uuid.UUID | None = None) -> int:
    """Write the progress events that are due for the user's paid, non-sample, unfinished orders (one order, or all of
    them). Returns how many events were written. Only this user's orders can be touched."""
    where = "and o.order_id = %s" if order_id else ""
    params = (user_id, order_id) if order_id else (user_id,)
    rows = conn.execute(f"""
        select o.order_id, extract(epoch from now() - o.created_at)::float as age, o.delivery_lat, o.delivery_lon,
               b.lat as b_lat, b.lon as b_lon
        from public.orders o join public.branches b using (branch_id)
        where o.user_id = %s and o.payment_status = 'paid' and not o.is_sample and o.status not in ('delivered', 'cancelled')
              {where}
        order by o.created_at for update of o""", params).fetchall()
    written = 0
    for r in rows:
        have = {e["status"] for e in conn.execute("select status from public.order_status_events where order_id = %s",
                                                  (r["order_id"],)).fetchall()}
        due = [(s, off) for s, off in due_statuses(r["age"]) if s not in have]
        for status, off in due:
            lat, lon = ((r["b_lat"], r["b_lon"]) if status in ("picked_up", "on_the_way") else
                        (r["delivery_lat"], r["delivery_lon"]) if status == "delivered" else (None, None))
            conn.execute("""insert into public.order_status_events (order_id, status, rider_lat, rider_lon, created_at)
                            select %s, %s, %s, %s, o.created_at + make_interval(secs => %s)
                            from public.orders o where o.order_id = %s""",
                         (r["order_id"], status, lat, lon, off, r["order_id"]))
            written += 1
        if due:
            conn.execute("update public.orders set status = %s where order_id = %s", (due[-1][0], r["order_id"]))
    return written
