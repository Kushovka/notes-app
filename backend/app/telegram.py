import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from urllib import parse, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, joinedload

from .config import settings
from .db import SessionLocal
from .models import Note, NotificationDelivery, User

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_link_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_link_token(user: User, db: Session) -> str:
    if user.telegram_link_token:
        return user.telegram_link_token
    user.telegram_link_token = new_link_token()
    db.commit()
    db.refresh(user)
    return user.telegram_link_token


def telegram_bot_username() -> str | None:
    if not settings.telegram_bot_username:
        return None
    username = settings.telegram_bot_username.strip().lstrip("@")
    return username or None


def telegram_deep_link(link_token: str) -> str | None:
    username = telegram_bot_username()
    if not username:
        return None
    return f"https://t.me/{username}?start={parse.quote(link_token)}"


def validate_timezone(value: str) -> str:
    timezone = value.strip()
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown timezone") from exc
    return timezone


def today_for_user(user: User, now: datetime | None = None):
    base = now or now_utc()
    return base.astimezone(ZoneInfo(user.timezone or "UTC")).date()


class TelegramApiError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, payload: dict | None = None) -> dict:
        data = parse.urlencode(payload or {}).encode()
        req = request.Request(f"{self.base_url}/{method}", data=data, method="POST")
        with request.urlopen(req, timeout=15) as response:
            body = json.loads(response.read().decode())
        if not body.get("ok"):
            raise TelegramApiError(str(body.get("description") or body))
        return body

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        payload: dict[str, int] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        body = self.call("getUpdates", payload)
        return body.get("result", [])

    def send_message(self, chat_id: str, text: str) -> None:
        self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": 1,
            },
        )


def reminder_text(note: Note) -> str:
    date_text = note.note_date.isoformat() if note.note_date else "today"
    return f"Reminder: {note.title}\nDate: {date_text}"


def test_message_text() -> str:
    return "Telegram reminders are linked. Test message from Notes."


def record_delivery(
    db: Session,
    *,
    user_id: int,
    note_id: int | None,
    event: str,
    status: str,
    message: str,
    error: str | None = None,
) -> None:
    db.add(
        NotificationDelivery(
            user_id=user_id,
            note_id=note_id,
            channel="telegram",
            event=event,
            status=status,
            message=message,
            error=error[:1000] if error else None,
        )
    )


def link_telegram_chat(token: str, chat_id: str, db: Session) -> bool:
    user = db.query(User).filter(User.telegram_link_token == token).one_or_none()
    if user is None:
        return False
    user.telegram_chat_id = str(chat_id)
    user.telegram_notifications_enabled = True
    user.telegram_linked_at = now_utc()
    db.commit()
    return True


def handle_update(update: dict, db: Session) -> None:
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id or not text.startswith("/start"):
        return

    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return
    link_telegram_chat(parts[1].strip(), str(chat_id), db)


def send_due_reminders(db: Session, client: TelegramClient, now: datetime | None = None) -> int:
    notes = (
        db.query(Note)
        .options(joinedload(Note.owner))
        .join(User)
        .filter(
            Note.note_date.is_not(None),
            Note.archived_at.is_(None),
            Note.telegram_reminder_sent_at.is_(None),
            User.telegram_notifications_enabled.is_(True),
            User.telegram_chat_id.is_not(None),
        )
        .all()
    )

    sent = 0
    for note in notes:
        if note.note_date is None or note.note_date > today_for_user(note.owner, now):
            continue
        message = reminder_text(note)
        try:
            client.send_message(note.owner.telegram_chat_id or "", message)
        except Exception as exc:
            error = str(exc)
            note.telegram_reminder_attempts += 1
            note.telegram_reminder_last_error = error[:1000]
            record_delivery(
                db,
                user_id=note.user_id,
                note_id=note.id,
                event="note_reminder",
                status="failed",
                message=message,
                error=error,
            )
            db.commit()
            continue

        note.telegram_reminder_sent_at = now_utc()
        note.telegram_reminder_last_error = None
        record_delivery(
            db,
            user_id=note.user_id,
            note_id=note.id,
            event="note_reminder",
            status="sent",
            message=message,
        )
        db.commit()
        sent += 1
    return sent


def send_test_message(db: Session, user: User, client: TelegramClient) -> None:
    message = test_message_text()
    try:
        client.send_message(user.telegram_chat_id or "", message)
    except Exception as exc:
        record_delivery(
            db,
            user_id=user.id,
            note_id=None,
            event="test_message",
            status="failed",
            message=message,
            error=str(exc),
        )
        db.commit()
        raise

    record_delivery(
        db,
        user_id=user.id,
        note_id=None,
        event="test_message",
        status="sent",
        message=message,
    )
    db.commit()


async def poll_telegram_updates(client: TelegramClient) -> None:
    offset: int | None = None
    while True:
        try:
            updates = await asyncio.to_thread(client.get_updates, offset, 25)
            with SessionLocal() as db:
                for update in updates:
                    offset = int(update["update_id"]) + 1
                    handle_update(update, db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram polling failed")
            await asyncio.sleep(settings.telegram_poll_interval_seconds)


async def run_reminder_loop(client: TelegramClient) -> None:
    while True:
        try:
            await asyncio.to_thread(send_due_reminders_once, client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram reminder loop failed")
        await asyncio.sleep(settings.telegram_reminder_interval_seconds)


def send_due_reminders_once(client: TelegramClient) -> int:
    with SessionLocal() as db:
        return send_due_reminders(db, client)
