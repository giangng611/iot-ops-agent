import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from storage.relational_store import (
    create_telegram_link_code,
    get_telegram_link_code,
    mark_telegram_link_code_used,
    upsert_telegram_identity,
)


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def utc_now():
    return datetime.now(timezone.utc)


def parse_iso_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def get_link_code_ttl_minutes():
    try:
        ttl = int(os.getenv("TELEGRAM_LINK_CODE_TTL_MINUTES", "15"))
    except (TypeError, ValueError):
        return 15

    return ttl if ttl > 0 else 15


def hash_link_code(code):
    normalized = normalize_link_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_link_code(code):
    return "".join(
        char
        for char in str(code or "").upper()
        if char.isalnum()
    )


def generate_link_code(length=8):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def create_link_code_for_user(user_id):
    code = generate_link_code()
    expires_at = utc_now() + timedelta(minutes=get_link_code_ttl_minutes())

    create_telegram_link_code(
        hash_link_code(code),
        user_id,
        expires_at.isoformat(),
    )

    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "ttl_minutes": get_link_code_ttl_minutes(),
    }


def consume_link_code(
    code,
    telegram_user_id,
    telegram_username=None,
):
    normalized_code = normalize_link_code(code)

    if not normalized_code:
        return False, "invalid_code"

    link_code = get_telegram_link_code(hash_link_code(normalized_code))

    if not link_code:
        return False, "invalid_code"

    if link_code.get("used_at"):
        return False, "code_already_used"

    if parse_iso_datetime(link_code["expires_at"]) <= utc_now():
        return False, "code_expired"

    if not mark_telegram_link_code_used(link_code["code_hash"]):
        return False, "code_already_used"

    upsert_telegram_identity(
        telegram_user_id,
        link_code["user_id"],
        telegram_username=telegram_username,
        role="viewer",
        allowed_data_sources=["simulator"],
        is_active=True,
    )

    return True, "linked"
