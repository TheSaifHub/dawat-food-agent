"""Dawat backend entry point.

Run locally from the backend/ folder:
    ..\\.venv\\Scripts\\python -m uvicorn app.main:app --reload
"""

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cart import router as cart_router
from app.api.catalog import router as catalog_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.plans import router as plans_router
from app.api.chat import router as chat_router
from app.api.payments import router as payments_router
from app.api.preferences import router as preferences_router
from app import config, devauth
from app.config import ALLOWED_ORIGINS
from app.db import close_pool
from app.tools.reference import warm_reference

# D-059 lock 2: decided once, at import. A dev login asked for on a hosting platform, against a remote database, or
# set in the env file raises DevLoginRefused HERE, so that server never starts (and a deploy fails its health check).
DEV_LOGIN = devauth.enabled()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The database pool opens lazily, so /health never waits on it. The reference copy (menus included, D-053) is
    # loaded in a background thread right away, so the first visitor after a cold start doesn't pay for it.
    if config.DATABASE_URL and os.environ.get("DAWAT_TEST_RUN") != "1":
        threading.Thread(target=warm_reference, name="warm-reference", daemon=True).start()
    yield
    close_pool()


app = FastAPI(
    title="Dawat API",
    description="Backend for Dawat, a Hyderabad food ordering demo with the Dawat AI agent.",
    version="0.1.0",
    lifespan=lifespan,
)

# Only the Dawat frontend(s) listed in ALLOWED_ORIGINS may call this API from a browser.
# Auth uses a bearer token in the Authorization header, not cookies, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(preferences_router)
app.include_router(plans_router)
app.include_router(chat_router)
app.include_router(payments_router)

# D-059 lock 3: the dev login's routes exist only in a server started for it (dev_server.py start, local database).
if DEV_LOGIN:
    from app.api.devauth import router as devauth_router
    app.include_router(devauth_router)
