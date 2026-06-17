import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from storage.relational_store import (
    create_telegram_link_code,
    deactivate_telegram_identity,
    get_telegram_identity,
    get_telegram_link_code,
    mark_telegram_link_code_used,
    update_user_data_source_policy,
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

    existing_identity = get_telegram_identity(telegram_user_id)
    role = "viewer"
    allowed_data_sources = ["simulator"]

    if existing_identity:
        if int(existing_identity["user_id"]) != int(link_code["user_id"]):
            return False, "telegram_already_linked"

        role = existing_identity.get("role") or role
        allowed_data_sources = sorted(set(
            (existing_identity.get("allowed_data_sources") or [])
            + allowed_data_sources
        ))

    upsert_telegram_identity(
        telegram_user_id,
        link_code["user_id"],
        telegram_username=telegram_username,
        role=role,
        allowed_data_sources=allowed_data_sources,
        is_active=True,
    )
    update_user_data_source_policy(
        link_code["user_id"],
        allowed_data_sources=allowed_data_sources,
        default_data_source=(
            "company" if "company" in allowed_data_sources else "simulator"
        ),
    )

    return True, "linked"


def unlink_telegram_identity(telegram_user_id):
    if telegram_user_id is None:
        return False, "missing_telegram_user_id"

    existing_identity = get_telegram_identity(telegram_user_id)

    if not existing_identity:
        return False, "telegram_identity_not_mapped"

    if not existing_identity.get("is_active"):
        return False, "telegram_identity_inactive"

    if not deactivate_telegram_identity(telegram_user_id):
        return False, "telegram_identity_not_mapped"

    return True, "unlinked"
