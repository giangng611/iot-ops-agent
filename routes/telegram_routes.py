import os

from flask import Blueprint, jsonify, request

from services.telegram_service import (
    get_telegram_secret_token,
    process_telegram_update_in_background,
    telegram_enabled,
    telegram_secret_is_valid,
)


def create_telegram_blueprint(runtime):
    telegram_bp = Blueprint("telegram", __name__)
    telegram_agent = runtime.get("telegram_agent") or runtime["langgraph_agent"]
    emit_user_event = runtime.get("emit_user_event")
    get_user_data_source = runtime.get("get_user_data_source")
    resolve_source_context = runtime.get("resolve_source_context")

    @telegram_bp.route("/api/telegram/webhook", methods=["POST"])
    def telegram_webhook():
        if not telegram_enabled():
            return jsonify({"error": "Telegram bot is not configured."}), 503

        request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

        if not telegram_secret_is_valid(request_secret):
            return jsonify({"error": "Invalid Telegram webhook secret."}), 403

        update = request.get_json(silent=True) or {}
        process_telegram_update_in_background(
            update,
            telegram_agent,
            emit_user_event=emit_user_event,
            get_user_data_source=get_user_data_source,
            resolve_source_context=resolve_source_context,
        )

        return jsonify({"status": "accepted"})

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
            "identity_mapping_required": True,
            "allowed_user_ids_configured": bool(os.getenv("TELEGRAM_ALLOWED_USER_IDS")),
        })

    return telegram_bp
