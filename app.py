from flask import Flask, render_template, redirect, url_for, session
from dotenv import load_dotenv
from openai import OpenAI
import os
from flask_socketio import SocketIO, join_room
from simulator import DEVICES, generate_telemetry
from collections import defaultdict, deque

from agents.ioa_v1_agent import IOAV1Agent
from agents.ioa_v2_agent import IOAV2Agent
from agents.ioa_v3_agent import IOAV3LangGraphN8nAgent
from agents.langchain_agent import LangChainAgent
from agents.langgraph_agent import LangGraphAgent
from routes.auth_routes import auth_bp
from routes.chat_routes import create_chat_blueprint
from routes.diagnose_routes import create_diagnose_blueprint
from routes.helpers import login_required
from routes.profile_routes import profile_bp
from routes.prompt_routes import prompt_bp
from routes.storage_routes import storage_bp
from routes.telemetry_routes import (
    get_user_selected_data_source,
    telemetry_bp,
)
from routes.telegram_routes import create_telegram_blueprint
from storage.relational_store import init_db
from storage.telemetry_store import (
    get_all_latest_devices,
    get_telemetry_source
)
from services.time_service import now, parse_timestamp

load_dotenv()

def get_positive_int_env(name, default):
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        return default

    return value if value > 0 else default

app = Flask(__name__)
flask_secret_key = os.getenv("FLASK_SECRET_KEY")
socketio_cors_origins = os.getenv("SOCKETIO_CORS_ORIGINS", "").strip()
MAX_DIAGNOSE_MESSAGE_CHARS = get_positive_int_env(
    "MAX_DIAGNOSE_MESSAGE_CHARS",
    2000
)
DIAGNOSE_RATE_LIMIT_REQUESTS = get_positive_int_env(
    "DIAGNOSE_RATE_LIMIT_REQUESTS",
    10
)
DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS = get_positive_int_env(
    "DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS",
    60
)
TELEMETRY_BROADCAST_INTERVAL_SECONDS = get_positive_int_env(
    "TELEMETRY_BROADCAST_INTERVAL_SECONDS",
    300
)
TELEMETRY_CONNECTED_GRACE_SECONDS = max(
    90,
    TELEMETRY_BROADCAST_INTERVAL_SECONDS * 2
)
ENABLE_EMBEDDED_TELEMETRY = (
    os.getenv("ENABLE_EMBEDDED_TELEMETRY", "true").lower()
    in {"1", "true", "yes", "on"}
)
diagnose_rate_limit_log = defaultdict(deque)
device_broadcast_task = None

if not flask_secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be configured.")

app.secret_key = flask_secret_key
socketio = SocketIO(
    app,
    cors_allowed_origins=(
        [origin.strip() for origin in socketio_cors_origins.split(",")]
        if socketio_cors_origins
        else None
    ),
    async_mode="gevent"
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ioa_v1_agent = IOAV1Agent(client)
ioa_v2_agent = IOAV2Agent(client)
langchain_agent = LangChainAgent()
langgraph_agent = LangGraphAgent()
ioa_v3_agent = IOAV3LangGraphN8nAgent()

app.register_blueprint(auth_bp)
app.register_blueprint(create_chat_blueprint(client))
app.register_blueprint(create_diagnose_blueprint({
    "ioa_v1_agent": ioa_v1_agent,
    "ioa_v2_agent": ioa_v2_agent,
    "langchain_agent": langchain_agent,
    "langgraph_agent": langgraph_agent,
    "ioa_v3_agent": ioa_v3_agent,
    "get_max_message_chars": lambda: MAX_DIAGNOSE_MESSAGE_CHARS,
    "get_rate_limit_requests": lambda: DIAGNOSE_RATE_LIMIT_REQUESTS,
    "get_rate_limit_window_seconds": lambda: DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS,
    "diagnose_rate_limit_log": diagnose_rate_limit_log,
}))
app.register_blueprint(create_telegram_blueprint({
    "langgraph_agent": langgraph_agent,
    "emit_user_event": lambda user_id, event, payload: socketio.emit(
        event,
        payload,
        to=f"user:{user_id}",
    ),
    "get_user_data_source": get_user_selected_data_source,
}))
app.register_blueprint(prompt_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(storage_bp)
app.register_blueprint(telemetry_bp)

init_db()


@socketio.on("connect")
def connect_user_socket():
    user_id = session.get("user_id")

    if user_id is not None:
        join_room(f"user:{user_id}")

if len(get_all_latest_devices()) == 0:
    for device_id in DEVICES:
        generate_telemetry(device_id)

def generate_telemetry_batch():
    for device_id in DEVICES:
        generate_telemetry(device_id)

def build_device_update_payload():
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
        device_timestamp = parse_timestamp(device["timestamp"])

        if latest_timestamp is None or device_timestamp > latest_timestamp:
            latest_timestamp = device_timestamp

    telemetry_age_seconds = None

    if latest_timestamp:
        telemetry_age_seconds = (
                now() - latest_timestamp
        ).total_seconds()

    telemetry_stream_status = (
        "connected"
        if (
            telemetry_age_seconds is not None
            and telemetry_age_seconds < TELEMETRY_CONNECTED_GRACE_SECONDS
        )
        else "disconnected"
    )

    return {
        "source": get_telemetry_source(),
        "devices": devices,
        "alerts": {
            "critical_count": critical_count,
            "warning_count": warning_count,
            "telemetry_stream_status": telemetry_stream_status,
            "telemetry_age_seconds": telemetry_age_seconds
        }
    }

@app.route("/")
def home():
    if not login_required():
        return redirect(url_for("auth.login"))

    devices = get_all_latest_devices()
    return render_template("index.html", devices=devices)

def device_broadcast_loop():
    while True:
        if ENABLE_EMBEDDED_TELEMETRY:
            generate_telemetry_batch()

        socketio.emit("device_update", build_device_update_payload())

        socketio.sleep(TELEMETRY_BROADCAST_INTERVAL_SECONDS)


def start_device_broadcast_loop():
    global device_broadcast_task

    if not ENABLE_EMBEDDED_TELEMETRY:
        return None

    if device_broadcast_task is None:
        device_broadcast_task = socketio.start_background_task(
            device_broadcast_loop
        )

    return device_broadcast_task


start_device_broadcast_loop()


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5001))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
        environ={"SERVER_NAME": os.getenv("SERVER_NAME", "localhost")}
    )
