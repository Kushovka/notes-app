from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth import hash_password, verify_password
from ..config import settings
from ..deps import get_current_user, get_db
from ..models import User
from ..rate_limit import (
    auth_rate_limit_key,
    check_auth_rate_limit,
    clear_auth_failures,
    record_auth_failure,
)
from ..schemas import (
    ChangePasswordIn,
    DeleteAccountIn,
    OkOut,
    TelegramSettingsIn,
    TelegramSettingsOut,
)
from ..telegram import (
    TelegramClient,
    ensure_link_token,
    new_link_token,
    send_test_message,
    telegram_bot_username,
    telegram_deep_link,
    validate_timezone,
)

router = APIRouter(prefix="/account", tags=["account"])


def _telegram_settings_out(user: User, db: Session) -> TelegramSettingsOut:
    link_token = ensure_link_token(user, db)
    return TelegramSettingsOut(
        chat_id=user.telegram_chat_id,
        notifications_enabled=user.telegram_notifications_enabled,
        link_token=link_token,
        deep_link=telegram_deep_link(link_token),
        bot_username=telegram_bot_username(),
        linked_at=user.telegram_linked_at,
        timezone=user.timezone,
        bot_configured=bool(settings.telegram_bot_token),
    )


@router.get("/telegram", response_model=TelegramSettingsOut)
def get_telegram_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramSettingsOut:
    return _telegram_settings_out(user, db)


@router.put("/telegram", response_model=TelegramSettingsOut)
def update_telegram_settings(
    payload: TelegramSettingsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramSettingsOut:
    try:
        user.timezone = validate_timezone(payload.timezone)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown timezone") from exc
    user.telegram_notifications_enabled = payload.notifications_enabled
    db.commit()
    db.refresh(user)
    return _telegram_settings_out(user, db)


@router.post("/telegram/test-message", response_model=OkOut)
def send_telegram_test_message(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkOut:
    if not settings.telegram_bot_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telegram bot token is not configured")
    if not user.telegram_chat_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Telegram is not linked")
    try:
        send_test_message(db, user, TelegramClient(settings.telegram_bot_token))
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Telegram test message failed") from exc
    return OkOut()


@router.post("/telegram/regenerate-token", response_model=TelegramSettingsOut)
def regenerate_telegram_link_token(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramSettingsOut:
    user.telegram_link_token = new_link_token()
    db.commit()
    db.refresh(user)
    return _telegram_settings_out(user, db)


@router.post("/change-password", response_model=OkOut)
def change_password(
    request: Request,
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkOut:
    rate_limit_key = auth_rate_limit_key(request, "change-password", user.id)
    check_auth_rate_limit(rate_limit_key)
    if not verify_password(payload.current_password, user.password_hash):
        record_auth_failure(rate_limit_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is wrong")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    clear_auth_failures(rate_limit_key)
    return OkOut()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    payload: DeleteAccountIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    rate_limit_key = auth_rate_limit_key(request, "delete-account", user.id)
    check_auth_rate_limit(rate_limit_key)
    if not verify_password(payload.password, user.password_hash):
        record_auth_failure(rate_limit_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password is wrong")
    db.delete(user)
    db.commit()
    clear_auth_failures(rate_limit_key)
