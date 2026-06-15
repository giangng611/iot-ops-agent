import os
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from routes.helpers import current_user_id, require_login_json
from services.auth_service import (
    authenticate_user,
    change_password,
    change_username,
    delete_account,
    register_user,
)


auth_bp = Blueprint("auth", __name__)
_login_rate_limit_lock = threading.Lock()
_login_rate_limit_log = defaultdict(deque)


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def check_login_rate_limit(username):
    attempts = _positive_int_env("LOGIN_RATE_LIMIT_ATTEMPTS", 10)
    window_seconds = _positive_int_env(
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        300,
    )
    key = (
        f"{request.remote_addr or 'unknown'}:"
        f"{(username or '').strip().lower()}"
    )
    now = time.monotonic()
    window_start = now - window_seconds

    with _login_rate_limit_lock:
        attempt_times = _login_rate_limit_log[key]

        while attempt_times and attempt_times[0] <= window_start:
            attempt_times.popleft()

        if len(attempt_times) >= attempts:
            retry_after = max(
                1,
                int(window_seconds - (now - attempt_times[0])),
            )
            return False, retry_after

        attempt_times.append(now)

    return True, None


def clear_login_rate_limit(username):
    key = (
        f"{request.remote_addr or 'unknown'}:"
        f"{(username or '').strip().lower()}"
    )

    with _login_rate_limit_lock:
        _login_rate_limit_log.pop(key, None)


@auth_bp.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    password = data.get("password")
    allowed, retry_after = check_login_rate_limit(username)

    if not allowed:
        response = jsonify({
            "error": "Too many login attempts. Please try again later.",
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    user = authenticate_user(username, password)

    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    clear_login_rate_limit(username)
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return jsonify({"status": "logged_in"})


@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()

    success, message, status_code = register_user(
        data.get("username"),
        data.get("password"),
        data.get("access_code"),
    )

    if not success:
        return jsonify({"error": message}), status_code

    return jsonify({"status": message})


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/profile/change-password", methods=["POST"])
def api_change_password():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    data = request.get_json()

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"error": "Both fields are required"}), 400

    success, message = change_password(
        current_user_id(),
        current_password,
        new_password,
    )

    if not success:
        return jsonify({"error": message}), 400

    return jsonify({"status": message})


@auth_bp.route("/api/profile/change-username", methods=["POST"])
def api_change_username():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    data = request.get_json()
    new_username = data.get("new_username", "").strip()

    if not new_username:
        return jsonify({"error": "New username is required"}), 400

    success, message = change_username(current_user_id(), new_username)

    if not success:
        return jsonify({"error": message}), 400

    session["username"] = new_username

    return jsonify({
        "status": message,
        "username": new_username,
    })


@auth_bp.route("/api/profile/delete-account", methods=["POST"])
def api_delete_account():
    unauthorized = require_login_json()

    if unauthorized:
        return unauthorized

    data = request.get_json()
    password = data.get("password", "")

    success, message = delete_account(
        current_user_id(),
        session.get("username"),
        password,
    )

    if not success:
        return jsonify({"error": message}), 400

    session.clear()

    return jsonify({"status": message})
