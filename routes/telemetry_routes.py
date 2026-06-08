from flask import Blueprint, jsonify, request, session

from routes.helpers import require_login_json
from services.telemetry_service import (
    get_device_history_payload,
    get_devices_payload,
    get_mongo_device_history_payload,
    get_mongo_devices_payload,
    get_mongo_telemetry_health_payload,
    get_mongo_telemetry_indexes_payload,
)


telemetry_bp = Blueprint("telemetry", __name__)


def get_selected_data_source():
    return session.get("selected_data_source", "simulator")


@telemetry_bp.route("/api/devices", methods=["GET"])
def get_devices():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(get_devices_payload(get_selected_data_source()))


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

    return jsonify({
        "selected_source": get_selected_data_source(),
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
