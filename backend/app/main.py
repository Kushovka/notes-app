import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import account as account_router
from .routers import auth as auth_router
from .routers import notes as notes_router
from .routers import tags as tags_router
from .telegram import TelegramClient, poll_telegram_updates, run_reminder_loop

app = FastAPI(title="Notes API", version="0.1.0")

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.on_event("startup")
async def start_telegram_tasks() -> None:
    if not settings.telegram_bot_token:
        app.state.telegram_tasks = []
        return
    client = TelegramClient(settings.telegram_bot_token)
    app.state.telegram_tasks = [
        asyncio.create_task(poll_telegram_updates(client)),
        asyncio.create_task(run_reminder_loop(client)),
    ]


@app.on_event("shutdown")
async def stop_telegram_tasks() -> None:
    tasks = getattr(app.state, "telegram_tasks", [])
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app.include_router(auth_router.router, prefix="/api")
app.include_router(account_router.router, prefix="/api")
app.include_router(notes_router.router, prefix="/api")
app.include_router(tags_router.router, prefix="/api")
