from flask import Blueprint, jsonify, request, session

from routes.helpers import current_user_id, require_login_json
from services.prompt_service import (
    create_user_prompt,
    delete_user_prompt,
    list_prompts,
    update_user_prompt,
)


prompt_bp = Blueprint("prompt", __name__)


@prompt_bp.route("/api/prompts", methods=["GET"])
def api_get_prompts():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    return jsonify({
        "prompts": list_prompts(
            current_user_id(),
            session.get("selected_data_source"),
        )
    })


@prompt_bp.route("/api/prompts", methods=["POST"])
def api_create_prompt():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    data = request.get_json()

    title = data.get("title")
    command = data.get("command")
    category = data.get("category", "Custom")

    if not title or not command:
        return jsonify({"error": "Title and command are required"}), 400

    return jsonify(create_user_prompt(
        current_user_id(),
        title,
        command,
        category,
    ))


@prompt_bp.route("/api/prompts/<int:prompt_id>", methods=["PUT"])
def api_update_prompt(prompt_id):
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    data = request.get_json()

    title = data.get("title")
    command = data.get("command")
    category = data.get("category", "Custom")

    if not title or not command:
        return jsonify({"error": "Title and command are required"}), 400

    success = update_user_prompt(
        prompt_id,
        current_user_id(),
        title,
        command,
        category,
    )

    if not success:
        return jsonify({"error": "Prompt not found or cannot edit default prompt"}), 404

    return jsonify({"status": "updated"})


@prompt_bp.route("/api/prompts/<int:prompt_id>", methods=["DELETE"])
def api_delete_prompt(prompt_id):
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    success = delete_user_prompt(prompt_id, current_user_id())

    if not success:
        return jsonify({"error": "Prompt not found or cannot delete default prompt"}), 404

    return jsonify({"status": "deleted"})
