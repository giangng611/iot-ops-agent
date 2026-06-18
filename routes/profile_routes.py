from flask import Blueprint, jsonify

from routes.helpers import current_user_id, require_login_json
from services.profile_service import get_profile_usage_stats
from services.telegram_link_service import create_link_code_for_user


profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/api/profile/usage-stats", methods=["GET"])
def api_usage_stats():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(get_profile_usage_stats(current_user_id()))


@profile_bp.route("/api/profile/telegram-link-code", methods=["POST"])
def api_create_telegram_link_code():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify(create_link_code_for_user(current_user_id()))
