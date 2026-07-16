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
from storage.relational_store import get_user_data_source_policy


telemetry_bp = Blueprint("telemetry", __name__)
_user_data_source_lock = threading.Lock()
_user_data_sources = {}
_user_data_source_explicit = {}
_mongo_read_rate_limit_lock = threading.Lock()
_mongo_read_rate_limit_log = defaultdict(deque)
ALLOWED_ALERT_POLICIES = {"official", "fallback"}


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


def get_allowed_data_sources(user_id):
    return set(
        get_user_data_source_policy(user_id).get(
            "allowed_data_sources",
            ["simulator"],
        )
    )


def get_default_data_source(user_id):
    policy = get_user_data_source_policy(user_id)
    default_source = policy.get("default_data_source", "simulator")
    allowed_sources = set(policy.get("allowed_data_sources") or ["simulator"])

    if default_source not in allowed_sources:
        return "simulator"

    return default_source


def get_selected_data_source():
    user_id = current_user_id()
    selected_source = session.get("selected_data_source")
    selected_source_explicit = bool(session.get("selected_data_source_explicit"))

    if selected_source_explicit and selected_source in get_allowed_data_sources(user_id):
        return selected_source

    selected_source = get_default_data_source(user_id)
    session["selected_data_source"] = selected_source
    session["selected_data_source_explicit"] = False
    return selected_source


def get_selected_alert_policy():
    selected_policy = session.get("selected_alert_policy", "fallback")

    if selected_policy not in ALLOWED_ALERT_POLICIES:
        selected_policy = "fallback"
        session["selected_alert_policy"] = selected_policy

    return selected_policy


def remember_user_data_source(user_id, selected_source, explicit=False):
    if user_id is None:
        return

    with _user_data_source_lock:
        _user_data_sources[int(user_id)] = selected_source
        _user_data_source_explicit[int(user_id)] = bool(explicit)


def get_user_selected_data_source(user_id):
    if user_id is None:
        return "simulator"

    allowed_sources = get_allowed_data_sources(user_id)
    default_source = get_default_data_source(user_id)

    with _user_data_source_lock:
        selected_source = _user_data_sources.get(int(user_id), default_source)
        selected_source_explicit = _user_data_source_explicit.get(
            int(user_id),
            False,
        )

    if not selected_source_explicit:
        return default_source

    if selected_source not in allowed_sources:
        return default_source

    return selected_source


@telemetry_bp.route("/api/devices", methods=["GET"])
def get_devices():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    selected_source = get_selected_data_source()
    remember_user_data_source(
        current_user_id(),
        selected_source,
        explicit=bool(session.get("selected_data_source_explicit")),
    )

    payload = get_devices_payload(selected_source)
    payload["selected_source"] = selected_source
    payload["default_source"] = get_default_data_source(current_user_id())
    payload["allowed_data_sources"] = sorted(
        get_allowed_data_sources(current_user_id())
    )
    payload["selected_alert_policy"] = get_selected_alert_policy()
    return jsonify(payload)


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

        if selected_source not in get_allowed_data_sources(current_user_id()):
            return jsonify({
                "error": "You are not allowed to use this data source.",
                "selected_source": get_selected_data_source(),
                "allowed_data_sources": sorted(
                    get_allowed_data_sources(current_user_id())
                ),
            }), 403

        session["selected_data_source"] = selected_source
        session["selected_data_source_explicit"] = True

    selected_source = get_selected_data_source()
    remember_user_data_source(
        current_user_id(),
        selected_source,
        explicit=bool(session.get("selected_data_source_explicit")),
    )

    return jsonify({
        "selected_source": selected_source,
        "default_source": get_default_data_source(current_user_id()),
        "allowed_data_sources": sorted(get_allowed_data_sources(current_user_id())),
        "selected_alert_policy": get_selected_alert_policy(),
    })


@telemetry_bp.route("/api/alert-policy", methods=["GET", "POST"])
def alert_policy():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        selected_policy = data.get("selected_alert_policy", "fallback")

        if selected_policy not in ALLOWED_ALERT_POLICIES:
            return jsonify({"error": "Invalid alert policy"}), 400

        session["selected_alert_policy"] = selected_policy

    return jsonify({
        "selected_alert_policy": get_selected_alert_policy(),
        "available_alert_policies": sorted(ALLOWED_ALERT_POLICIES),
        "official_alert_status": "integrated",
        "official_alert_source": "company_kpi_grafana_n8n",
        "fallback_alert_status": "available",
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
