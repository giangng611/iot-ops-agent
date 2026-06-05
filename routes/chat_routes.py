from flask import Blueprint, jsonify, request

from routes.helpers import current_user_id, require_login_json
from services.chat_service import (
    create_user_chat,
    get_chat_messages,
    list_chats,
    remove_chat,
    save_chat_message,
    toggle_chat_pin,
)


def create_chat_blueprint(openai_client):
    chat_bp = Blueprint("chat", __name__)

    @chat_bp.route("/api/chats", methods=["GET"])
    def api_get_chats():
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        return jsonify({"chats": list_chats(current_user_id())})

    @chat_bp.route("/api/chats", methods=["POST"])
    def api_create_chat():
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        data = request.get_json()
        message = data.get("message", "")
        chat_id, title = create_user_chat(
            current_user_id(),
            message,
            openai_client,
        )

        return jsonify({
            "chat_id": chat_id,
            "title": title,
        })

    @chat_bp.route("/api/chats/<int:chat_id>/messages", methods=["GET"])
    def api_get_messages(chat_id):
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        messages = get_chat_messages(chat_id, current_user_id())

        if messages is None:
            return jsonify({"error": "Chat not found"}), 404

        return jsonify({
            "chat_id": chat_id,
            "messages": messages,
        })

    @chat_bp.route("/api/chats/<int:chat_id>/messages", methods=["POST"])
    def api_add_message(chat_id):
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        data = request.get_json()
        success, message, status_code = save_chat_message(
            chat_id=chat_id,
            user_id=current_user_id(),
            role=data.get("role"),
            content=data.get("content"),
            reasoning_steps=data.get("reasoning_steps"),
            token_usage=data.get("token_usage"),
        )

        if not success:
            return jsonify({"error": message}), status_code

        return jsonify({"status": message})

    @chat_bp.route("/api/chats/<int:chat_id>", methods=["DELETE"])
    def api_delete_chat(chat_id):
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        if not remove_chat(chat_id, current_user_id()):
            return jsonify({"error": "Chat not found"}), 404

        return jsonify({"status": "deleted"})

    @chat_bp.route("/api/chats/<int:chat_id>/pin", methods=["POST"])
    def api_toggle_pin_chat(chat_id):
        unauthorized = require_login_json()

        if unauthorized:
            return unauthorized

        is_pinned = toggle_chat_pin(chat_id, current_user_id())

        if is_pinned is None:
            return jsonify({"error": "Chat not found"}), 404

        return jsonify({"is_pinned": is_pinned})

    return chat_bp
