from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
from flask_socketio import SocketIO
import time
import threading

from agents.week1_agent import Week1Agent
from agents.week2_agent import Week2Agent
from database import get_all_latest_devices

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
week1_agent = Week1Agent(client)
week2_agent = Week2Agent(client)


@app.route("/")
def home():
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

        time.sleep(5)

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