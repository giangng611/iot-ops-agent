from flask import jsonify, session


def login_required():
    return "user_id" in session


def require_login_json():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    return None


def current_user_id():
    return session.get("user_id")
