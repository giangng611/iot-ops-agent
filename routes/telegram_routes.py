import os

from flask import Blueprint, jsonify, request

from services.telegram_service import (
    handle_telegram_update,
    get_telegram_secret_token,
    telegram_enabled,
    telegram_secret_is_valid,
)


def create_telegram_blueprint(runtime):
    telegram_bp = Blueprint("telegram", __name__)
    langgraph_agent = runtime["langgraph_agent"]

    @telegram_bp.route("/api/telegram/webhook", methods=["POST"])
    def telegram_webhook():
        if not telegram_enabled():
            return jsonify({"error": "Telegram bot is not configured."}), 503

        request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

        if not telegram_secret_is_valid(request_secret):
            return jsonify({"error": "Invalid Telegram webhook secret."}), 403

        update = request.get_json(silent=True) or {}
        result = handle_telegram_update(update, langgraph_agent)

        return jsonify(result)

    @telegram_bp.route("/api/telegram/webhook-info", methods=["GET"])
    def telegram_webhook_info():
        public_base_url = (
            os.getenv("PUBLIC_BASE_URL")
            or os.getenv("RENDER_EXTERNAL_URL")
            or request.host_url
        )
        webhook_url = f"{public_base_url.rstrip('/')}/api/telegram/webhook"

        return jsonify({
            "configured": telegram_enabled(),
            "webhook_url": webhook_url,
            "secret_configured": bool(get_telegram_secret_token()),
            "history_user_id_configured": bool(os.getenv("TELEGRAM_HISTORY_USER_ID")),
            "allowed_user_ids_configured": bool(os.getenv("TELEGRAM_ALLOWED_USER_IDS")),
        })

    return telegram_bp
