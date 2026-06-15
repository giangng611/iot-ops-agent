import os
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request, session

from routes.helpers import current_user_id, require_login_json
from services.telemetry_service import (
    get_device_history_payload,
    get_devices_payload,
    get_mongo_device_history_payload,
    get_mongo_devices_payload,
    get_mongo_telemetry_health_payload,
    get_mongo_telemetry_indexes_payload,
)


telemetry_bp = Blueprint("telemetry", __name__)
_user_data_source_lock = threading.Lock()
_user_data_sources = {}
_mongo_read_rate_limit_lock = threading.Lock()
_mongo_read_rate_limit_log = defaultdict(deque)


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def check_mongo_read_rate_limit():
    requests = _positive_int_env(
        "MONGO_READ_RATE_LIMIT_REQUESTS",
        60,
    )
    window_seconds = _positive_int_env(
        "MONGO_READ_RATE_LIMIT_WINDOW_SECONDS",
        60,
    )
    key = f"user:{current_user_id()}"
    now = time.monotonic()
    window_start = now - window_seconds

    with _mongo_read_rate_limit_lock:
        request_times = _mongo_read_rate_limit_log[key]

        while request_times and request_times[0] <= window_start:
            request_times.popleft()

        if len(request_times) >= requests:
            retry_after = max(
                1,
                int(window_seconds - (now - request_times[0])),
            )
            response = jsonify({
                "error": "MongoDB read rate limit exceeded.",
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        request_times.append(now)

    return None


def get_selected_data_source():
    return session.get("selected_data_source", "simulator")


def remember_user_data_source(user_id, selected_source):
    if user_id is None:
        return

    with _user_data_source_lock:
        _user_data_sources[int(user_id)] = selected_source


def get_user_selected_data_source(user_id):
    default_source = os.getenv(
        "TELEGRAM_DEFAULT_DATA_SOURCE",
        "simulator",
    ).strip().lower()

    if default_source not in {"simulator", "company"}:
        default_source = "simulator"

    if user_id is None:
        return default_source

    with _user_data_source_lock:
        return _user_data_sources.get(int(user_id), default_source)


@telemetry_bp.route("/api/devices", methods=["GET"])
def get_devices():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    selected_source = get_selected_data_source()
    remember_user_data_source(current_user_id(), selected_source)

    return jsonify(get_devices_payload(selected_source))


@telemetry_bp.route("/api/data-source", methods=["GET", "POST"])
def data_source():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        selected_source = data.get("selected_source", "simulator")

        if selected_source not in {"simulator", "company"}:
            return jsonify({"error": "Invalid data source"}), 400

        session["selected_data_source"] = selected_source

    selected_source = get_selected_data_source()
    remember_user_data_source(current_user_id(), selected_source)

    return jsonify({
        "selected_source": selected_source,
    })


@telemetry_bp.route("/api/telemetry/<device_id>", methods=["GET"])
def get_device_history(device_id):
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(get_device_history_payload(
        device_id,
        get_selected_data_source(),
    ))


@telemetry_bp.route("/api/mongo/telemetry/health", methods=["GET"])
def get_mongo_telemetry_health():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    rate_limited = check_mongo_read_rate_limit()
    if rate_limited:
        return rate_limited

    try:
        limit = request.args.get("limit", default=5, type=int)
        return jsonify(get_mongo_telemetry_health_payload(limit))
    except Exception:
        return jsonify({
            "error": "MongoDB telemetry read failed",
        }), 503


@telemetry_bp.route("/api/mongo/telemetry/indexes", methods=["GET"])
def mongo_telemetry_indexes():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    rate_limited = check_mongo_read_rate_limit()
    if rate_limited:
        return rate_limited

    try:
        return jsonify(get_mongo_telemetry_indexes_payload())
    except Exception:
        return jsonify({
            "error": "MongoDB telemetry index check failed",
        }), 503


@telemetry_bp.route("/api/mongo/devices", methods=["GET"])
def get_mongo_devices():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    rate_limited = check_mongo_read_rate_limit()
    if rate_limited:
        return rate_limited

    try:
        return jsonify(get_mongo_devices_payload())
    except Exception:
        return jsonify({
            "error": "MongoDB telemetry read failed",
        }), 503


@telemetry_bp.route("/api/mongo/telemetry/<device_id>", methods=["GET"])
def get_mongo_device_history(device_id):
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    rate_limited = check_mongo_read_rate_limit()
    if rate_limited:
        return rate_limited

    try:
        limit = request.args.get("limit", default=30, type=int)
        return jsonify(get_mongo_device_history_payload(device_id, limit))
    except Exception:
        return jsonify({
            "error": "MongoDB telemetry read failed",
        }), 503
