"""Browsing routes (D-027): areas, restaurant search, dish search, a branch's menu; by area (7c, D-056).

Public: browsing needs no sign-in, only the cart and orders do. They read the same reference data and tools as
Dawat AI, so the page and the chat always show the same restaurants, dishes and prices.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import Conn, respond
from app.tools import browse, dishes, restaurants
from app.tools.menu import get_menu
from app.tools.reference import get_reference

router = APIRouter(tags=["catalog"])

Area = Annotated[str | None, Query(max_length=80, description="An area name, e.g. Madhapur")]
IsVeg = Annotated[bool | None, Query()]
MaxSpice = Annotated[int | None, Query(ge=0, le=3)]
MaxPrice = Annotated[int | None, Query(ge=1, le=dishes.MAX_PRICE_LIMIT)]
Category = Annotated[str | None, Query(max_length=40)]


@router.get("/areas")
def list_areas(conn: Conn):
    """Every covered area, for the area picker."""
    ref = get_reference(conn)
    areas = sorted(ref.areas.values(), key=lambda a: a["name"])
    return {"status": "ok", "areas": [{"area_id": a["area_id"], "name": a["name"], "name_te": a["name_te"]} for a in areas]}


@router.get("/restaurants")
def search_restaurants(conn: Conn, q: Annotated[str, Query(min_length=1, max_length=restaurants.MAX_QUERY_LEN)],
                       area: Area = None, limit: Annotated[int, Query(ge=1, le=restaurants.MAX_RESULTS)] = restaurants.MAX_RESULTS):
    return respond(restaurants.search_restaurants(conn, q, area=area, limit=limit))


@router.get("/dishes")
def search_dishes(conn: Conn, q: Annotated[str, Query(min_length=1, max_length=dishes.MAX_QUERY_LEN)], area: Area = None,
                  is_veg: IsVeg = None, max_spice: MaxSpice = None, max_price: MaxPrice = None, category: Category = None,
                  limit: Annotated[int, Query(ge=1, le=dishes.MAX_LIMIT)] = dishes.DEFAULT_LIMIT):
    return respond(dishes.search_dishes(conn, q, area=area, is_veg=is_veg, max_spice=max_spice, max_price=max_price,
                                        category=category, limit=limit))


@router.get("/branches/{branch_id}/menu")
def branch_menu(conn: Conn, branch_id: Annotated[str, Path(max_length=20)], category: Category = None,
                is_veg: IsVeg = None, max_spice: MaxSpice = None, max_price: MaxPrice = None):
    return respond(get_menu(conn, branch_id, category=category, is_veg=is_veg, max_spice=max_spice, max_price=max_price))


AreaId = Annotated[str, Path(min_length=1, max_length=80, description="An area id from GET /areas, e.g. madhapur")]


@router.get("/areas/{area_id}/home")
def area_home(conn: Conn, area_id: AreaId):
    """The home page for an area: cuisine shortcuts and chains near you (D-049)."""
    return respond(browse.area_home(conn, area_id))


@router.get("/areas/{area_id}/restaurants")
def restaurants_near(conn: Conn, area_id: AreaId,
                     cuisine: Annotated[str | None, Query(max_length=40)] = None,
                     veg_only: Annotated[bool | None, Query()] = None,
                     mild: Annotated[bool | None, Query(description="only restaurants with several mild mains")] = None,
                     max_km: Annotated[float | None, Query(gt=0, le=8)] = None,
                     max_price_for_one: Annotated[int | None, Query(ge=1, le=5000)] = None,
                     sort: Annotated[str, Query(pattern="^(distance|price|name)$")] = "distance",
                     offset: Annotated[int, Query(ge=0, le=5000)] = 0,
                     limit: Annotated[int, Query(ge=1, le=browse.MAX_LIMIT)] = browse.DEFAULT_LIMIT):
    """Restaurants that deliver to this area (a branch within 8 km), nearest first, with real fees and prices."""
    return respond(browse.restaurants_near(conn, area_id, cuisine=cuisine, veg_only=veg_only, mild=mild, max_km=max_km,
                                           max_price_for_one=max_price_for_one, sort=sort, offset=offset, limit=limit))


@router.get("/branches/{branch_id}")
def branch_info(conn: Conn, branch_id: Annotated[str, Path(max_length=20)], area: Area = None):
    """A restaurant page's header and map; with ?area=, whether this branch delivers there and the fee."""
    return respond(browse.branch_info(conn, branch_id, area=area))
