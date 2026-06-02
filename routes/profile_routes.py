from flask import Blueprint, jsonify

from routes.helpers import current_user_id, require_login_json
from services.profile_service import get_profile_usage_stats


profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/api/profile/usage-stats", methods=["GET"])
def api_usage_stats():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(get_profile_usage_stats(current_user_id()))
