import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


def get_app_timezone():
    timezone_name = os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE)

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def now():
    return datetime.now(get_app_timezone())


def now_iso():
    return now().isoformat(timespec="seconds")


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=get_app_timezone())

    return parsed.astimezone(get_app_timezone())
