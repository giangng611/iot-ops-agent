import threading

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


def get_selected_data_source():
    return session.get("selected_data_source", "simulator")


def remember_user_data_source(user_id, selected_source):
    if user_id is None:
        return

    with _user_data_source_lock:
        _user_data_sources[int(user_id)] = selected_source


def get_user_selected_data_source(user_id):
    if user_id is None:
        return "simulator"

    with _user_data_source_lock:
        return _user_data_sources.get(int(user_id), "simulator")


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

    return jsonify(get_device_history_payload(device_id))


@telemetry_bp.route("/api/mongo/telemetry/health", methods=["GET"])
def get_mongo_telemetry_health():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    try:
        limit = request.args.get("limit", default=5, type=int)
        return jsonify(get_mongo_telemetry_health_payload(limit))
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc),
        }), 503


@telemetry_bp.route("/api/mongo/telemetry/indexes", methods=["GET", "POST"])
def mongo_telemetry_indexes():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    try:
        return jsonify(get_mongo_telemetry_indexes_payload(
            ensure_indexes=request.method == "POST",
        ))
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry index check failed",
            "details": str(exc),
        }), 503


@telemetry_bp.route("/api/mongo/devices", methods=["GET"])
def get_mongo_devices():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    try:
        return jsonify(get_mongo_devices_payload())
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc),
        }), 503


@telemetry_bp.route("/api/mongo/telemetry/<device_id>", methods=["GET"])
def get_mongo_device_history(device_id):
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    try:
        limit = request.args.get("limit", default=30, type=int)
        return jsonify(get_mongo_device_history_payload(device_id, limit))
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc),
        }), 503
