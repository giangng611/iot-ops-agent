from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
from flask_socketio import SocketIO
import time
import threading
from flask import session, redirect, url_for
from prompts import CHAT_TITLE_PROMPT
from simulator import DEVICES, generate_telemetry
from datetime import datetime

from agents.ioa_v1_agent import IOAV1Agent
from agents.ioa_v2_agent import IOAV2Agent
from agents.langchain_agent import LangChainAgent
from database import (
    init_db,
    get_all_latest_devices,
    get_device_telemetry_history,
    create_chat,
    get_chats,
    add_message,
    get_messages,
    create_user,
    verify_user,
    delete_chat,
    toggle_pin_chat,
    change_user_password,
    get_prompts,
    create_prompt,
    update_prompt,
    delete_prompt,
    update_username,
    delete_user_account,
    get_user_by_username,
    get_user_usage_stats
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent"
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ioa_v1_agent = IOAV1Agent(client)
ioa_v2_agent = IOAV2Agent(client)
langchain_agent = LangChainAgent()

init_db()

if len(get_all_latest_devices()) == 0:
    for device_id in DEVICES:
        generate_telemetry(device_id)

@app.route("/")
def home():
    if not login_required():
        return redirect(url_for("login"))

    devices = get_all_latest_devices()
    return render_template("index.html", devices=devices)

@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    data = request.get_json()
    user_input = data.get("message", "")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    try:
        mode = data.get("mode", "ioa_v2_custom")

        if mode == "ioa_v1_custom":
            result = ioa_v1_agent.run(user_input)

            return jsonify({
                "response": result,
                "steps": []
            })

        if mode == "ioa_v2_langchain":
            result = langchain_agent.run(user_input)

            return jsonify({
                "response": result["final_answer"],
                "steps": result["steps"]
            })

        result = ioa_v2_agent.run(user_input)

        return jsonify({
            "response": result["final_answer"],
            "steps": result["steps"]
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@app.route("/api/diagnose-stream", methods=["POST"])
def diagnose_stream():
    data = request.get_json()
    user_input = data.get("message", "")
    mode = data.get("mode", "ioa_v2_custom")

    def generate():
        try:
            if mode == "ioa_v2_langchain":
                yield f"data: {json.dumps({
                    'type': 'thought',
                    'iteration': 1,
                    'thought': 'Using LangChain as the orchestration runtime.',
                    'action': 'Initialize LangChain agent execution'
                })}\n\n"

                result = langchain_agent.run(user_input)

                yield f"data: {json.dumps({
                    'type': 'observation',
                    'iteration': 1,
                    'observation': {
                        'output': {
                            'framework': 'LangChain',
                            'agent_style': 'Framework-managed tool-calling agent',
                            'trace_visibility': 'Limited internal reasoning visibility',
                            'note': 'LangChain abstracts most internal Thought/Action/Observation steps unless callbacks are added.'
                        }
                    }
                })}\n\n"

                yield f"data: {json.dumps({
                    'type': 'thought',
                    'iteration': 2,
                    'thought': 'LangChain returned a final operational diagnosis.',
                    'action': 'Format final answer for IoT Ops Agent UI'
                })}\n\n"

                yield f"data: {json.dumps({
                    'type': 'observation',
                    'iteration': 2,
                    'observation': {
                        'output': result['steps'][0]['output']
                    }
                })}\n\n"

                yield f"data: {json.dumps({
                    'type': 'final',
                    'final_answer': result['final_answer']
                })}\n\n"

                return

            for event in ioa_v2_agent.run_stream(user_input):
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/devices", methods=["GET"])
def get_devices():
    devices = get_all_latest_devices()
    return jsonify({
        "devices": devices
    })

def device_broadcast_loop():
    DEVICE_BROADCAST_INTERVAL_SECONDS = 30
    while True:
        devices = get_all_latest_devices()

        critical_count = len([
            device for device in devices
            if device["status"] == "critical"
        ])

        warning_count = len([
            device for device in devices
            if device["status"] == "warning"
        ])

        latest_timestamp = None

        for device in devices:
            device_timestamp = datetime.fromisoformat(device["timestamp"])

            if latest_timestamp is None or device_timestamp > latest_timestamp:
                latest_timestamp = device_timestamp

        telemetry_age_seconds = None

        if latest_timestamp:
            telemetry_age_seconds = (
                    datetime.now() - latest_timestamp
            ).total_seconds()

        telemetry_stream_status = (
            "connected"
            if telemetry_age_seconds is not None and telemetry_age_seconds < 90
            else "disconnected"
        )

        socketio.emit("device_update", {
            "devices": devices,
            "alerts": {
                "critical_count": critical_count,
                "warning_count": warning_count,
                "telemetry_stream_status": telemetry_stream_status,
                "telemetry_age_seconds": telemetry_age_seconds
            }
        })

        time.sleep(DEVICE_BROADCAST_INTERVAL_SECONDS)

@app.route("/api/prompts", methods=["GET"])
def api_get_prompts():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")
    prompts = get_prompts(user_id)

    default_prompts = [
        {
            "id": "default-1",
            "title": "System Health Overview",
            "command": "/overview system health",
            "category": "Fleet",
            "is_default": 1
        },
        {
            "id": "default-2",
            "title": "Check Unhealthy Devices",
            "command": "/check all unhealthy devices",
            "category": "Fleet",
            "is_default": 1
        },
        {
            "id": "default-3",
            "title": "Find Critical Devices",
            "command": "/find critical devices",
            "category": "Alerts",
            "is_default": 1
        },
        {
            "id": "default-4",
            "title": "Diagnose System Issue",
            "command": "/diagnose system issue",
            "category": "Diagnostics",
            "is_default": 1
        },
        {
            "id": "default-5",
            "title": "Check Heartbeat Delays",
            "command": "/check devices with delayed heartbeat",
            "category": "Fleet",
            "is_default": 1
        },
        {
            "id": "default-6",
            "title": "Show Active Alarms",
            "command": "/show devices with alarms",
            "category": "Alerts",
            "is_default": 1
        }
    ]

    return jsonify({
        "prompts": default_prompts + prompts
    })

@app.route("/api/prompts", methods=["POST"])
def api_create_prompt():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    title = data.get("title")
    command = data.get("command")
    category = data.get("category", "Custom")

    if not title or not command:
        return jsonify({"error": "Title and command are required"}), 400

    user_id = session.get("user_id")
    prompt_id = create_prompt(user_id, title, command, category)

    return jsonify({
        "id": prompt_id,
        "title": title,
        "command": command,
        "category": category,
        "is_default": 0
    })

@app.route("/api/prompts/<int:prompt_id>", methods=["PUT"])
def api_update_prompt(prompt_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    title = data.get("title")
    command = data.get("command")
    category = data.get("category", "Custom")

    if not title or not command:
        return jsonify({"error": "Title and command are required"}), 400

    user_id = session.get("user_id")
    success = update_prompt(prompt_id, user_id, title, command, category)

    if not success:
        return jsonify({"error": "Prompt not found or cannot edit default prompt"}), 404

    return jsonify({"status": "updated"})

@app.route("/api/prompts/<int:prompt_id>", methods=["DELETE"])
def api_delete_prompt(prompt_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")
    success = delete_prompt(prompt_id, user_id)

    if not success:
        return jsonify({"error": "Prompt not found or cannot delete default prompt"}), 404

    return jsonify({"status": "deleted"})

@app.route("/api/telemetry/<device_id>", methods=["GET"])
def get_device_history(device_id):

    history = get_device_telemetry_history(device_id)

    return jsonify({
        "device_id": device_id,
        "history": history
    })

@app.route("/api/chats", methods=["GET"])
def api_get_chats():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")
    chats = get_chats(user_id)

    return jsonify({
        "chats": chats
    })


@app.route("/api/chats", methods=["POST"])
def api_create_chat():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    message = data.get("message", "")

    title = generate_chat_title(message)

    user_id = session.get("user_id")
    chat_id = create_chat(user_id, title)

    return jsonify({
        "chat_id": chat_id,
        "title": title
    })

@app.route("/api/chats/<int:chat_id>/messages", methods=["GET"])
def api_get_messages(chat_id):
    messages = get_messages(chat_id)

    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify({
        "chat_id": chat_id,
        "messages": messages
    })


@app.route("/api/chats/<int:chat_id>/messages", methods=["POST"])
def api_add_message(chat_id):
    data = request.get_json()

    role = data.get("role")
    content = data.get("content")
    reasoning_steps = data.get("reasoning_steps")

    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    if not role or not content:
        return jsonify({
            "error": "role and content are required"
        }), 400

    if reasoning_steps is not None:
        reasoning_steps = json.dumps(reasoning_steps)

    add_message(
        chat_id=chat_id,
        role=role,
        content=content,
        reasoning_steps=reasoning_steps
    )

    return jsonify({
        "status": "saved"
    })

def login_required():
    return "user_id" in session

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    user = verify_user(username, password)

    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return jsonify({"status": "logged_in"})


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")
    access_code = data.get("access_code")

    required_code = os.getenv("ACCESS_CODE")

    if not required_code:
        return jsonify({"error": "Invalid access code"}), 500

    if access_code != required_code:
        return jsonify({"error": "Invalid access code"}), 403

    try:
        create_user(username, password)
        return jsonify({"status": "registered"})
    except Exception:
        return jsonify({"error": "Username already exists"}), 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")

    delete_chat(chat_id, user_id)

    return jsonify({
        "status": "deleted"
    })

@app.route("/api/chats/<int:chat_id>/pin", methods=["POST"])
def api_toggle_pin_chat(chat_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")
    is_pinned = toggle_pin_chat(chat_id, user_id)

    if is_pinned is None:
        return jsonify({"error": "Chat not found"}), 404

    return jsonify({
        "is_pinned": is_pinned
    })

@app.route("/api/profile/change-password", methods=["POST"])
def api_change_password():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"error": "Both fields are required"}), 400

    success, message = change_user_password(
        session.get("user_id"),
        current_password,
        new_password
    )

    if not success:
        return jsonify({"error": message}), 400

    return jsonify({"status": message})

def generate_chat_title(user_message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": CHAT_TITLE_PROMPT
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=0.2,
            max_tokens=20
        )

        title = response.choices[0].message.content.strip()

        if not title:
            return "New analysis"

        return title[:60]

    except Exception:
        return "New analysis"

@app.route("/api/profile/change-username", methods=["POST"])
def api_change_username():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    new_username = data.get("new_username", "").strip()

    if not new_username:
        return jsonify({"error": "New username is required"}), 400

    existing_user = get_user_by_username(new_username)

    if existing_user:
        return jsonify({"error": "Username already exists"}), 400

    success = update_username(session.get("user_id"), new_username)

    if not success:
        return jsonify({"error": "Unable to update username"}), 400

    session["username"] = new_username

    return jsonify({
        "status": "Username updated successfully",
        "username": new_username
    })

@app.route("/api/profile/delete-account", methods=["POST"])
def api_delete_account():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    password = data.get("password", "")

    username = session.get("username")
    user = verify_user(username, password)

    if not user:
        return jsonify({"error": "Password is incorrect"}), 400

    user_id = session.get("user_id")
    success = delete_user_account(user_id)

    if not success:
        return jsonify({"error": "Unable to delete account"}), 400

    session.clear()

    return jsonify({
        "status": "Account deleted"
    })

@app.route("/api/profile/usage-stats", methods=["GET"])
def api_usage_stats():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    stats = get_user_usage_stats(session.get("user_id"))

    return jsonify(stats)

if __name__ == "__main__":

    threading.Thread(
        target=device_broadcast_loop,
        daemon=True
    ).start()

    port = int(os.environ.get("PORT", 5001))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )