"""The Dawat MCP server (Phase 9, D-065/D-066): Claude Desktop (or any MCP client) browses, plans and views the cart
through the SAME tools the website and Dawat AI use.

The one rule that shapes everything: the client's model is the caller, so nothing it sends can be trusted as the
user's word.

  · Identity comes only from a token, verified on EVERY call by the same TokenVerifier as the website. The token is
    set by whoever starts the server (environment variable DAWAT_MCP_TOKEN, i.e. the Claude Desktop config); it is
    never a tool argument, and the tool schemas are closed, so a `user_id` or `token` argument is refused.
  · There is no `user_message` argument and the server passes none to the tools. The yes-checks that web chat needs
    can never be satisfied from here. So only tools that need no yes are exposed: the read-only ones, and two that
    only ADD to the cart under app.mcp_cart's limits (M2). Removing, replacing, delivery changes, preferences and
    ordering are the website's (D-065).
  · Reasons for a rejected token go to the log (stderr), never to the client.

stdio carries the protocol on stdout, so nothing in this process may print there: logging goes to stderr.
"""

import json
import logging
import os
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager

import anyio
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, TextContent,
                       Tool, ToolAnnotations)

from app import mcp_cart
from app.agent import cards
from app.agent.loop import to_model
from app.agent.tools import TOOLS, ToolContext, run_tool
from app.auth import AuthError, AuthUnavailable, AuthUser, TokenVerifier
from app.tools.preferences import saved_diet
from app.tools.users import ensure_user

log = logging.getLogger("dawat.mcp")

TOKEN_ENV = "DAWAT_MCP_TOKEN"
# What is exposed: the read-only tools (M1; view_cart may create the user's empty cart, like opening the cart page) and
# the two additive cart tools (M2), which run through app.mcp_cart's own schemas and rules instead of the agent's.
EXPOSED = ("search_restaurants", "get_menu", "search_dishes", "plan_meal", "view_cart", "get_preferences",
           "get_user_history", "track_order", *mcp_cart.CART_TOOLS)
NOT_READ_ONLY = ("view_cart", *mcp_cart.CART_TOOLS)
ORDER_ON_WEBSITE = ("You can't confirm or place an order from here. The user orders on the Dawat website: they open "
                    "their cart there and press Place order, then Pay.")

# Where a tool's description (written for the website's chat) says something that isn't true over MCP.
DESCRIPTIONS = {
    "view_cart": "The user's cart: every line, delivery fee, GST and grand_total (all computed by the server). Show "
                 "the numbers exactly as given; never add them up yourself. " + ORDER_ON_WEBSITE,
    "plan_meal": TOOLS["plan_meal"].description + " To put a plan the user picked in their cart, use add_plan_to_cart "
                 "(only into an empty cart).",
}
INSTRUCTIONS = (
    "Dawat is a demo food-ordering service for Hyderabad. Menus, prices and orders are simulated. Every restaurant, "
    "dish, price and total you state must come from a Dawat tool result; never invent or recompute one. Use "
    "plan_meal for any request with a budget, a group size or mixed diets. If a restaurant has several branches, ask "
    "which area before showing a menu. " + ORDER_ON_WEBSITE)

SIGN_IN = {"status": "sign_in_required", "message": "Dawat couldn't verify who you are. Sign in to the Dawat website and "
           "start this server again with a fresh token."}
UNAVAILABLE = {"status": "unavailable", "message": "Dawat's sign-in check or database isn't available right now. "
               "Please try again in a minute."}
TOOL_ERROR = {"status": "tool_error", "message": "Something went wrong on our side and nothing was changed. Please "
              "try again."}
ERROR_STATUSES = {"sign_in_required", "unavailable", "tool_error", "unknown_tool", "invalid_arguments"}


def _env_token() -> str | None:
    return os.environ.get(TOKEN_ENV)


def _default_verifier() -> TokenVerifier:
    from app.auth import get_verifier
    return get_verifier()


def _default_connect() -> AbstractContextManager:
    from app.db import get_pool
    return get_pool().connection()


def _view_cart_for_mcp(result: dict) -> dict:
    """The cart as the model sees it here: no card, no ids to confirm with, and the website instruction."""
    if not isinstance(result, dict):
        return result
    out = {k: v for k, v in result.items() if k not in (cards.RESULT_KEY, "cart_id", "quote_id", "can_confirm")}
    if result.get("status") == "ok":
        out["message"] = ORDER_ON_WEBSITE
    return out


class Handler:
    """Everything a call needs, injected so tests can supply a token, a verifier and a rolled-back connection."""

    def __init__(self, *, token_source: Callable[[], str | None] = _env_token,
                 verifier: Callable[[], TokenVerifier] = _default_verifier,
                 connect: Callable[[], AbstractContextManager] = _default_connect):
        self.token_source, self.verifier, self.connect = token_source, verifier, connect

    def identify(self) -> AuthUser | dict:
        """The verified user's id, or the reply to give instead. Checked on every call, so an expired token stops
        working at once; the reason for a refusal is logged here and never returned."""
        token = (self.token_source() or "").strip()
        if not token:
            log.info("no token set (%s)", TOKEN_ENV)
            return SIGN_IN
        try:
            return self.verifier().verify(token)
        except AuthError as e:
            log.info("token rejected: %s", e)
            return SIGN_IN
        except Exception as e:           # AuthUnavailable, a missing configuration, anything unexpected: not the user's fault
            log.warning("token check unavailable: %s", type(e).__name__)
            return UNAVAILABLE

    def call(self, name: str, arguments) -> dict:
        """One tool call. Sync (psycopg); the server runs it in a worker thread."""
        if name not in EXPOSED:
            return {"status": "unknown_tool", "message": f"There is no tool called {name!r}. Use one of: "
                                                         f"{', '.join(EXPOSED)}."}
        who = self.identify()
        if isinstance(who, dict):
            return who
        user = who
        try:
            with self.connect() as conn:
                profile = ensure_user(conn, user.user_id, user.display_name)
                if profile is None:
                    log.info("token for an account that no longer exists")
                    return SIGN_IN
                ctx = ToolContext(conn=conn, user_id=user.user_id, user_message=None,
                                  turn_diet=saved_diet(conn, user.user_id))
                with conn.transaction():
                    result = (mcp_cart.run_cart_tool(name, arguments, ctx) if name in mcp_cart.CART_TOOLS
                              else run_tool(name, arguments, ctx))
        except (AuthError, AuthUnavailable):
            return UNAVAILABLE
        except Exception as e:           # the details go to the log only
            log.exception("tool %s failed: %s", name, type(e).__name__)
            return TOOL_ERROR
        return _view_cart_for_mcp(result) if name == "view_cart" else result


def _tool_list() -> list[Tool]:
    out = []
    for name in EXPOSED:
        t = mcp_cart.CART_TOOLS.get(name) or TOOLS[name]
        hints = {"readOnlyHint": True} if name not in NOT_READ_ONLY else {"readOnlyHint": False, "destructiveHint": False}
        out.append(Tool(name=name, description=DESCRIPTIONS.get(name, t.description), input_schema=t.parameters,
                        annotations=ToolAnnotations(openWorldHint=False, **hints)))
    return out


def build_server(handler: Handler | None = None) -> Server:
    handler = handler or Handler()

    async def list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
        return ListToolsResult(tools=_tool_list())

    async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
        result = await anyio.to_thread.run_sync(handler.call, params.name, params.arguments or {})
        text = to_model(result) if isinstance(result, dict) else json.dumps(result, default=str)
        return CallToolResult(content=[TextContent(type="text", text=text)],
                              is_error=isinstance(result, dict) and result.get("status") in ERROR_STATUSES)

    return Server("Dawat", instructions=INSTRUCTIONS, on_list_tools=list_tools, on_call_tool=call_tool)


async def serve() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    anyio.run(serve)
