from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.db import Base
from app.models import Note, NotificationDelivery, User
from app.telegram import handle_update, send_due_reminders, send_test_message


def _register_login(client, username="telegram-user", password="pw123456"):
    client.post("/api/auth/register", json={"username": username, "password": password})
    r = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_telegram_settings_lifecycle(client):
    headers = _register_login(client)

    r = client.get("/api/account/telegram", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["chat_id"] is None
    assert body["notifications_enabled"] is False
    assert body["link_token"]
    assert body["deep_link"] is None
    assert body["bot_username"] is None
    assert body["timezone"] == "UTC"
    assert body["bot_configured"] is False

    r = client.put(
        "/api/account/telegram",
        headers=headers,
        json={"notifications_enabled": True, "timezone": "Europe/Berlin"},
    )
    assert r.status_code == 200
    assert r.json()["notifications_enabled"] is True
    assert r.json()["timezone"] == "Europe/Berlin"

    r = client.put(
        "/api/account/telegram",
        headers=headers,
        json={"notifications_enabled": True, "timezone": "Not/AZone"},
    )
    assert r.status_code == 422


def test_telegram_link_token_can_be_regenerated(client):
    headers = _register_login(client)
    first = client.get("/api/account/telegram", headers=headers).json()["link_token"]

    r = client.post("/api/account/telegram/regenerate-token", headers=headers)
    assert r.status_code == 200
    assert r.json()["link_token"] != first


class FakeTelegramClient:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    def send_message(self, chat_id, text):
        if self.fail:
            raise RuntimeError("telegram is down")
        self.messages.append((chat_id, text))


def test_handle_start_update_links_telegram_chat(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'telegram.db'}", future=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        db = Session()
        user = User(
            username="alice",
            password_hash=hash_password("pw123456"),
            telegram_link_token="token-123",
        )
        db.add(user)
        db.commit()

        handle_update({"message": {"text": "/start token-123", "chat": {"id": 42}}}, db)
        db.refresh(user)

        assert user.telegram_chat_id == "42"
        assert user.telegram_notifications_enabled is True
        assert user.telegram_linked_at is not None
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_due_reminders_are_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reminders.db'}", future=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        db = Session()
        user = User(
            username="alice",
            password_hash=hash_password("pw123456"),
            telegram_chat_id="42",
            telegram_notifications_enabled=True,
            timezone="UTC",
        )
        db.add(user)
        db.flush()
        due = Note(
            user_id=user.id,
            title="Pay rent",
            content="",
            tags=[],
            note_date=date(2026, 7, 15),
        )
        future = Note(
            user_id=user.id,
            title="Future",
            content="",
            tags=[],
            note_date=date(2026, 7, 16),
        )
        db.add_all([due, future])
        db.commit()

        client = FakeTelegramClient()
        now = datetime(2026, 7, 15, 8, tzinfo=UTC)

        assert send_due_reminders(db, client, now) == 1
        assert send_due_reminders(db, client, now) == 0
        assert client.messages == [("42", "Reminder: Pay rent\nDate: 2026-07-15")]
        deliveries = db.query(NotificationDelivery).all()
        assert len(deliveries) == 1
        assert deliveries[0].event == "note_reminder"
        assert deliveries[0].status == "sent"
        assert deliveries[0].note_id == due.id
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_failed_reminder_records_delivery_and_can_retry(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'failed-reminders.db'}", future=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        db = Session()
        user = User(
            username="alice",
            password_hash=hash_password("pw123456"),
            telegram_chat_id="42",
            telegram_notifications_enabled=True,
            timezone="UTC",
        )
        db.add(user)
        db.flush()
        note = Note(
            user_id=user.id,
            title="Retry me",
            content="",
            tags=[],
            note_date=date(2026, 7, 15),
        )
        db.add(note)
        db.commit()

        now = datetime(2026, 7, 15, 8, tzinfo=UTC)
        assert send_due_reminders(db, FakeTelegramClient(fail=True), now) == 0
        db.refresh(note)
        assert note.telegram_reminder_sent_at is None
        assert note.telegram_reminder_attempts == 1

        failed = db.query(NotificationDelivery).one()
        assert failed.status == "failed"
        assert failed.error == "telegram is down"

        ok_client = FakeTelegramClient()
        assert send_due_reminders(db, ok_client, now) == 1
        assert ok_client.messages == [("42", "Reminder: Retry me\nDate: 2026-07-15")]
        assert [
            d.status for d in db.query(NotificationDelivery).order_by(NotificationDelivery.id)
        ] == [
            "failed",
            "sent",
        ]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_telegram_test_message_requires_configuration(client):
    headers = _register_login(client)

    r = client.post("/api/account/telegram/test-message", headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == "Telegram bot token is not configured"


def test_telegram_test_message_requires_linked_chat(client, monkeypatch):
    headers = _register_login(client)

    from app.routers import account

    monkeypatch.setattr(account.settings, "telegram_bot_token", "bot-token")

    r = client.post("/api/account/telegram/test-message", headers=headers)
    assert r.status_code == 400
    assert r.json()["detail"] == "Telegram is not linked"


def test_send_test_message_records_delivery(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test-message.db'}", future=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        db = Session()
        user = User(
            username="alice",
            password_hash=hash_password("pw123456"),
            telegram_chat_id="42",
        )
        db.add(user)
        db.commit()

        client = FakeTelegramClient()
        send_test_message(db, user, client)

        assert client.messages == [
            ("42", "Telegram reminders are linked. Test message from Notes.")
        ]
        delivery = db.query(NotificationDelivery).one()
        assert delivery.event == "test_message"
        assert delivery.status == "sent"
        assert delivery.note_id is None
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
