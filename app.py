from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
from flask_socketio import SocketIO
import time
import threading
from flask import session, redirect, url_for

from agents.week1_agent import Week1Agent
from agents.week2_agent import Week2Agent
from database import (
    get_all_latest_devices,
    get_device_telemetry_history,
    create_chat,
    get_chats,
    add_message,
    get_messages,
    create_user,
    verify_user
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
socketio = SocketIO(app, cors_allowed_origins="*")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
week1_agent = Week1Agent(client)
week2_agent = Week2Agent(client)


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
        mode = data.get("mode", "week2")

        if mode == "week1":
            result = week1_agent.run(user_input)

            return jsonify({
                "response": result,
                "steps": []
            })

        else:
            result = week2_agent.run(user_input)

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

    def generate():
        try:
            for event in week2_agent.run_stream(user_input):
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

        socketio.emit("device_update", {
            "devices": devices,
            "alerts": {
                "critical_count": critical_count,
                "warning_count": warning_count
            }
        })

        time.sleep(DEVICE_BROADCAST_INTERVAL_SECONDS)


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
    title = data.get("title", "New Chat")

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

    try:
        create_user(username, password)
        return jsonify({"status": "registered"})
    except Exception:
        return jsonify({"error": "Username already exists"}), 400


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":

    threading.Thread(
        target=device_broadcast_loop,
        daemon=True
    ).start()

    socketio.run(
        app,
        debug=True,
        port=5001
    )