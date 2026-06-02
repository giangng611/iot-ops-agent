from flask import Blueprint, jsonify

from routes.helpers import require_login_json
from services.profile_service import get_full_storage_status


storage_bp = Blueprint("storage", __name__)


@storage_bp.route("/api/storage/status", methods=["GET"])
def api_storage_status():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(get_full_storage_status())
