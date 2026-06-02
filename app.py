from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
import requests
from flask_socketio import SocketIO
import time
import threading
from flask import session, redirect, url_for
from prompts import CHAT_TITLE_PROMPT, DIAGNOSIS_OUTPUT_FORMAT
from simulator import DEVICES, generate_telemetry
from datetime import datetime
import time
from collections import defaultdict, deque

from agents.ioa_v1_agent import IOAV1Agent
from agents.ioa_v2_agent import IOAV2Agent
from agents.langchain_agent import LangChainAgent
from agents.langgraph_agent import LangGraphAgent
from database import (
    init_db,
    create_chat,
    get_chats,
    chat_belongs_to_user,
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
from telemetry_store import (
    get_all_latest_devices,
    get_device_telemetry_history,
    get_latest_status,
    get_telemetry_source
)
from tools import check_system_overview, check_system_alarms
from benchmark_logger import log_benchmark_result
from mongo_store import (
    ensure_telemetry_indexes,
    get_all_latest_devices_from_mongo,
    get_device_telemetry_history_from_mongo,
    get_telemetry_indexes,
    get_telemetry_health,
)

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
    30
)
ENABLE_EMBEDDED_TELEMETRY = (
    os.getenv("ENABLE_EMBEDDED_TELEMETRY", "true").lower()
    in {"1", "true", "yes", "on"}
)
diagnose_rate_limit_log = defaultdict(deque)

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

init_db()

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

def get_rate_limit_key():
    user_id = session.get("user_id")

    if user_id:
        return f"user:{user_id}"

    return f"ip:{request.remote_addr or 'unknown'}"

def check_diagnose_rate_limit():
    now = time.time()
    key = get_rate_limit_key()
    request_times = diagnose_rate_limit_log[key]
    window_start = now - DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS

    while request_times and request_times[0] <= window_start:
        request_times.popleft()

    if len(request_times) >= DIAGNOSE_RATE_LIMIT_REQUESTS:
        retry_after = max(
            1,
            int(DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS - (now - request_times[0]))
        )
        return False, retry_after

    request_times.append(now)
    return True, None

def validate_diagnose_request():
    allowed, retry_after = check_diagnose_rate_limit()

    if not allowed:
        response = jsonify({
            "error": (
                "Rate limit exceeded. Please wait before sending another "
                "diagnosis request."
            )
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return None, response

    data = request.get_json(silent=True) or {}
    user_input = data.get("message", "").strip()

    if not user_input:
        return None, (jsonify({"error": "No message provided"}), 400)

    if len(user_input) > MAX_DIAGNOSE_MESSAGE_CHARS:
        return None, (
            jsonify({
                "error": (
                    "Message is too long. Please keep diagnosis requests "
                    f"under {MAX_DIAGNOSE_MESSAGE_CHARS} characters."
                )
            }),
            413
        )

    data["message"] = user_input
    return data, None

def extract_device_id_from_text(text):
    known_devices = [
        device["device_id"]
        for device in get_all_latest_devices()
    ]

    normalized_text = text.replace(",", " ").replace(".", " ")

    for token in normalized_text.split():
        cleaned_token = token.strip()

        if cleaned_token in known_devices:
            return cleaned_token

    return None

def build_n8n_payload(user_input):
    target_device = extract_device_id_from_text(user_input)

    operational_context = {
        "telemetry_source": get_telemetry_source(),
        "latest_devices": get_all_latest_devices(),
        "system_overview": check_system_overview(),
        "system_alarms": check_system_alarms(),
        "target_device": target_device,
        "target_device_status": None,
        "target_device_history": []
    }

    if target_device:
        operational_context["target_device_status"] = get_latest_status(
            target_device
        )
        operational_context["target_device_history"] = (
            get_device_telemetry_history(target_device)
        )

    system_prompt = (
        "You are an IoT operations assistant. Use only the telemetry "
        "and operational context provided in this payload. Do not invent "
        "device IDs, telemetry values, alarms, or logs. Heartbeat delay "
        "values are measured in seconds. For gateway heartbeat-delay "
        "investigations, use 300 seconds as the default threshold unless "
        "the user provides a different threshold in seconds. If a user says "
        "ms or milliseconds, state that the available telemetry is stored "
        "in seconds and evaluate the stored second-based values."
    )

    llm_prompt = f"""
{system_prompt}

User request:
{user_input}

Required final answer format:
{DIAGNOSIS_OUTPUT_FORMAT}

Operational context JSON:
{json.dumps(operational_context, indent=2)}

Return a valid JSON object only:
{{
  "response": "final answer using the required format",
  "steps": [
    {{
      "thought": "what information you inspected",
      "action": "which n8n node or context field you used",
      "output": "short evidence from the operational context"
    }}
  ]
}}
""".strip()

    return {
        "message": user_input,
        "prompt": user_input,
        "source": "iot-ops-agent-ui",
        "runtime": "n8n",
        "system_prompt": system_prompt,
        "n8n_llm_prompt": llm_prompt,
        "diagnosis_output_format": DIAGNOSIS_OUTPUT_FORMAT,
        "operational_context": operational_context,
        "response_contract": {
            "response": "Final answer formatted exactly with DIAGNOSIS_OUTPUT_FORMAT.",
            "steps": [
                {
                    "thought": "Short operational reasoning step.",
                    "action": "Workflow node, tool, or data source used.",
                    "output": "Useful evidence or result from that step."
                }
            ]
        }
    }

def call_n8n_agent(user_input):
    webhook_url = (
        os.getenv("N8N_WEBHOOK_URL")
        or os.getenv("EVAL_N8N_WEBHOOK_URL")
    )

    if not webhook_url:
        raise RuntimeError(
            "N8N_WEBHOOK_URL is not configured. "
            "Set it to your local n8n webhook URL."
        )

    response = requests.post(
        webhook_url,
        json=build_n8n_payload(user_input),
        timeout=90
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")

    if "application/json" not in content_type:
        return {
            "final_answer": response.text.strip(),
            "steps": []
        }

    response_body = response.text.strip()

    if not response_body:
        raise RuntimeError(
            "n8n returned an empty response body. Check that the Webhook "
            "node uses 'Respond to Webhook' and the Respond node returns JSON."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "n8n returned invalid JSON. Raw response: "
            f"{response_body[:500]}"
        ) from exc

    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        return {
            "final_answer": json.dumps(data, indent=2),
            "steps": []
        }

    final_answer = (
        data.get("response")
        or data.get("answer")
        or data.get("text")
        or data.get("output")
        or data.get("message")
        or json.dumps(data, indent=2)
    )

    return {
        "final_answer": final_answer,
        "steps": data.get("steps", [])
    }

def build_dify_payload(user_input):
    n8n_payload = build_n8n_payload(user_input)
    operational_context = n8n_payload["operational_context"]

    return {
        "inputs": {
            "system_prompt": n8n_payload["system_prompt"],
            "diagnosis_output_format": DIAGNOSIS_OUTPUT_FORMAT,
            "operational_context": json.dumps(
                operational_context,
                indent=2
            )
        },
        "query": n8n_payload["n8n_llm_prompt"],
        "response_mode": "blocking",
        "user": os.getenv("DIFY_USER", "iot-ops-agent-ui")
    }

def call_dify_agent(user_input):
    api_url = (
        os.getenv("DIFY_API_URL")
        or os.getenv("EVAL_DIFY_API_URL")
        or "http://localhost/v1/chat-messages"
    )
    api_key = (
        os.getenv("DIFY_API_KEY")
        or os.getenv("EVAL_DIFY_API_KEY")
    )

    if not api_key:
        raise RuntimeError(
            "DIFY_API_KEY is not configured. Set it to your Dify app API key."
        )

    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json=build_dify_payload(user_input),
        timeout=120
    )
    response.raise_for_status()

    data = response.json()
    answer = (
        data.get("answer")
        or data.get("response")
        or data.get("text")
        or json.dumps(data, indent=2)
    )
    returned_steps = []

    if isinstance(answer, str):
        try:
            parsed_answer = json.loads(answer)
            if isinstance(parsed_answer, dict):
                returned_steps = parsed_answer.get("steps", [])
                answer = (
                    parsed_answer.get("response")
                    or parsed_answer.get("answer")
                    or parsed_answer.get("text")
                    or answer
                )
        except ValueError:
            pass

    metadata = data.get("metadata", {})

    return {
        "final_answer": answer,
        "steps": returned_steps,
        "metadata": metadata,
        "conversation_id": data.get("conversation_id"),
        "message_id": data.get("message_id")
    }

def normalize_n8n_steps(result):
    raw_steps = result.get("steps", [])

    steps = [
        {
            "iteration": 1,
            "thought": "The request should be delegated to n8n for workflow-based orchestration.",
            "action": "call_n8n_webhook",
            "output": {
                "framework": "n8n",
                "runtime_type": "external workflow runtime",
                "response_received": True
            }
        }
    ]

    if isinstance(raw_steps, list):
        for index, step in enumerate(raw_steps, start=2):
            if isinstance(step, dict):
                steps.append({
                    "iteration": index,
                    "thought": (
                        step.get("thought")
                        or step.get("description")
                        or step.get("node")
                        or "n8n returned a workflow execution step."
                    ),
                    "action": (
                        step.get("action")
                        or step.get("tool")
                        or step.get("node")
                        or "n8n_workflow_step"
                    ),
                    "output": (
                        step.get("output")
                        if "output" in step
                        else step
                    )
                })
            else:
                steps.append({
                    "iteration": index,
                    "thought": "n8n returned a workflow execution step.",
                    "action": "n8n_workflow_step",
                    "output": step
                })

    if len(steps) == 1:
        steps.append({
            "iteration": 2,
            "thought": "n8n completed execution and returned a final response.",
            "action": "format_n8n_response",
            "output": {
                "answer_preview": result.get("final_answer", "")[:300]
            }
        })

    return steps

def normalize_dify_steps(result):
    metadata = result.get("metadata") or {}
    returned_steps = result.get("steps") or []

    steps = [
        {
            "iteration": 1,
            "thought": "The request should be delegated to Dify for app-based agent orchestration.",
            "action": "call_dify_chat_messages_api",
            "output": {
                "framework": "Dify",
                "runtime_type": "external app API runtime",
                "response_received": True,
                "conversation_id": result.get("conversation_id"),
                "message_id": result.get("message_id")
            }
        }
    ]

    if isinstance(returned_steps, list):
        for index, step in enumerate(returned_steps, start=2):
            if isinstance(step, dict):
                steps.append({
                    "iteration": index,
                    "thought": (
                        step.get("thought")
                        or step.get("description")
                        or step.get("node")
                        or "Dify returned an app execution step."
                    ),
                    "action": (
                        step.get("action")
                        or step.get("tool")
                        or step.get("node")
                        or "dify_app_step"
                    ),
                    "output": (
                        step.get("output")
                        if "output" in step
                        else step
                    )
                })

    workflow_run_id = metadata.get("workflow_run_id")

    if workflow_run_id:
        steps.append({
            "iteration": len(steps) + 1,
            "thought": "Dify returned workflow metadata that can be used to inspect the run in Dify logs.",
            "action": "inspect_dify_workflow_run",
            "output": {
                "workflow_run_id": workflow_run_id
            }
        })

    if len(steps) == 1:
        steps.append({
            "iteration": 2,
            "thought": "Dify completed execution and returned a final response.",
            "action": "format_dify_response",
            "output": {
                "answer_preview": result.get("final_answer", "")[:300]
            }
        })

    return steps

def log_n8n_benchmark(user_input, latency_seconds, status, step_count, error=None):
    notes = (
        f"Automatic benchmark capture from UI execution through n8n webhook. "
        f"status={status}; step_count={step_count}"
    )

    if error:
        notes = f"{notes}; error={error[:300]}"

    log_benchmark_result(
        mode="IOA v2 · n8n",
        prompt=user_input,
        latency_seconds=latency_seconds,
        accuracy_score=0,
        tool_usage_score=0,
        reasoning_clarity_score=0,
        observability_score=0,
        development_complexity_score=4,
        integration_speed_score=5,
        ecosystem_score=4,
        maintainability_score=4,
        notes=notes
    )

def log_dify_benchmark(user_input, latency_seconds, status, step_count, error=None):
    notes = (
        f"Automatic provisional benchmark capture from UI execution through Dify API. "
        f"status={status}; step_count={step_count}"
    )

    if error:
        notes = f"{notes}; error={error[:300]}"

    if status == "success":
        accuracy_score = 3
        tool_usage_score = 3
        reasoning_clarity_score = 3
        observability_score = 3
    else:
        accuracy_score = 0
        tool_usage_score = 0
        reasoning_clarity_score = 0
        observability_score = 0

    log_benchmark_result(
        mode="IOA v2 · Dify",
        prompt=user_input,
        latency_seconds=latency_seconds,
        accuracy_score=accuracy_score,
        tool_usage_score=tool_usage_score,
        reasoning_clarity_score=reasoning_clarity_score,
        observability_score=observability_score,
        development_complexity_score=4,
        integration_speed_score=4,
        ecosystem_score=4,
        maintainability_score=4,
        notes=notes
    )

@app.route("/")
def home():
    if not login_required():
        return redirect(url_for("login"))

    devices = get_all_latest_devices()
    return render_template("index.html", devices=devices)

@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data, error_response = validate_diagnose_request()

    if error_response:
        return error_response

    user_input = data["message"]

    try:
        mode = data.get("mode", "ioa_v2_custom")
        start_time = time.time()

        if mode == "ioa_v1_custom":
            result = ioa_v1_agent.run(user_input)

            latency_seconds = round(
                time.time() - start_time,
                2
            )

            log_benchmark_result(
                mode="IOA v1 · Custom Python",
                prompt=user_input,
                latency_seconds=latency_seconds,
                accuracy_score=0,
                tool_usage_score=0,
                reasoning_clarity_score=0,
                observability_score=0,
                development_complexity_score=2,
                integration_speed_score=3,
                ecosystem_score=2,
                maintainability_score=3,
                notes="Automatic benchmark capture from UI execution."
            )

            return jsonify({
                "response": result,
                "steps": []
            })

        if mode == "ioa_v2_langgraph":
            result = langgraph_agent.run(user_input)

            latency_seconds = round(
                time.time() - start_time,
                2
            )

            log_benchmark_result(
                mode="IOA v2 · LangGraph",
                prompt=user_input,
                latency_seconds=latency_seconds,
                accuracy_score=0,
                tool_usage_score=0,
                reasoning_clarity_score=0,
                observability_score=0,
                development_complexity_score=4,
                integration_speed_score=4,
                ecosystem_score=4,
                maintainability_score=4,
                notes="Automatic benchmark capture from UI execution."
            )

            return jsonify({
                "response": result["final_answer"],
                "steps": result["steps"]
            })

        if mode == "ioa_v2_langchain":
            result = langchain_agent.run(user_input)

            latency_seconds = round(
                time.time() - start_time,
                2
            )

            log_benchmark_result(
                mode="IOA v2 · LangChain",
                prompt=user_input,
                latency_seconds=latency_seconds,
                accuracy_score=0,
                tool_usage_score=0,
                reasoning_clarity_score=0,
                observability_score=0,
                development_complexity_score=5,
                integration_speed_score=5,
                ecosystem_score=5,
                maintainability_score=4,
                notes="Automatic benchmark capture from UI execution."
            )

            return jsonify({
                "response": result["final_answer"],
                "steps": result["steps"]
            })

        if mode == "ioa_v2_n8n":
            try:
                result = call_n8n_agent(user_input)
                steps = normalize_n8n_steps(result)
                latency_seconds = round(
                    time.time() - start_time,
                    2
                )
                log_n8n_benchmark(
                    user_input=user_input,
                    latency_seconds=latency_seconds,
                    status="success",
                    step_count=len(steps)
                )
            except Exception as e:
                latency_seconds = round(
                    time.time() - start_time,
                    2
                )
                log_n8n_benchmark(
                    user_input=user_input,
                    latency_seconds=latency_seconds,
                    status="error",
                    step_count=0,
                    error=str(e)
                )
                raise

            return jsonify({
                "response": result["final_answer"],
                "steps": steps
            })

        if mode == "ioa_v2_dify":
            try:
                result = call_dify_agent(user_input)
                steps = normalize_dify_steps(result)
                latency_seconds = round(
                    time.time() - start_time,
                    2
                )
                log_dify_benchmark(
                    user_input=user_input,
                    latency_seconds=latency_seconds,
                    status="success",
                    step_count=len(steps)
                )
            except Exception as e:
                latency_seconds = round(
                    time.time() - start_time,
                    2
                )
                log_dify_benchmark(
                    user_input=user_input,
                    latency_seconds=latency_seconds,
                    status="error",
                    step_count=0,
                    error=str(e)
                )
                raise

            return jsonify({
                "response": result["final_answer"],
                "steps": steps
            })

        result = ioa_v2_agent.run(user_input)

        latency_seconds = round(
            time.time() - start_time,
            2
        )

        log_benchmark_result(
            mode="IOA v2 · Custom Python",
            prompt=user_input,
            latency_seconds=latency_seconds,
            accuracy_score=0,
            tool_usage_score=0,
            reasoning_clarity_score=0,
            observability_score=0,
            development_complexity_score=1,
            integration_speed_score=2,
            ecosystem_score=2,
            maintainability_score=3,
            notes="Automatic benchmark capture from UI execution."
        )

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
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data, error_response = validate_diagnose_request()

    if error_response:
        return error_response

    user_input = data["message"]
    mode = data.get("mode", "ioa_v2_custom")
    start_time = time.time()

    def generate():
        try:
            if mode == "ioa_v2_langgraph":
                for event in langgraph_agent.run_stream(user_input):
                    yield f"data: {json.dumps(event)}\n\n"

                latency_seconds = round(time.time() - start_time, 2)

                log_benchmark_result(
                    mode="IOA v2 · LangGraph",
                    prompt=user_input,
                    latency_seconds=latency_seconds,
                    accuracy_score=0,
                    tool_usage_score=0,
                    reasoning_clarity_score=0,
                    observability_score=0,
                    development_complexity_score=4,
                    integration_speed_score=4,
                    ecosystem_score=4,
                    maintainability_score=4,
                    notes="Automatic benchmark capture from streamed UI execution."
                )

                return

            if mode == "ioa_v2_langchain":
                yield f"data: {json.dumps({
                    'type': 'thought',
                    'iteration': 1,
                    'thought': 'Using LangChain as the orchestration runtime.',
                    'action': 'Initialize LangChain agent execution'
                })}\n\n"

                result = langchain_agent.run(user_input)

                latency_seconds = round(time.time() - start_time, 2)

                log_benchmark_result(
                    mode="IOA v2 · LangChain",
                    prompt=user_input,
                    latency_seconds=latency_seconds,
                    accuracy_score=0,
                    tool_usage_score=0,
                    reasoning_clarity_score=0,
                    observability_score=0,
                    development_complexity_score=5,
                    integration_speed_score=5,
                    ecosystem_score=5,
                    maintainability_score=4,
                    notes="Automatic benchmark capture from streamed UI execution."
                )

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

            if mode == "ioa_v2_n8n":
                try:
                    yield f"data: {json.dumps({
                        'type': 'thought',
                        'iteration': 1,
                        'thought': 'The request should be delegated to n8n for workflow-based orchestration.',
                        'action': 'call_n8n_webhook'
                    })}\n\n"

                    result = call_n8n_agent(user_input)
                    steps = normalize_n8n_steps(result)

                    latency_seconds = round(time.time() - start_time, 2)

                    log_n8n_benchmark(
                        user_input=user_input,
                        latency_seconds=latency_seconds,
                        status="success",
                        step_count=len(steps)
                    )

                    first_step = steps[0]

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': first_step['iteration'],
                        'observation': {
                            'output': first_step['output']
                        }
                    })}\n\n"

                    for step in steps[1:]:
                        yield f"data: {json.dumps({
                            'type': 'thought',
                            'iteration': step['iteration'],
                            'thought': step['thought'],
                            'action': step['action']
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'observation',
                            'iteration': step['iteration'],
                            'observation': {
                                'output': step['output']
                            }
                        })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'final',
                        'final_answer': result['final_answer']
                    })}\n\n"
                except Exception as e:
                    latency_seconds = round(time.time() - start_time, 2)

                    log_n8n_benchmark(
                        user_input=user_input,
                        latency_seconds=latency_seconds,
                        status="error",
                        step_count=0,
                        error=str(e)
                    )

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': 1,
                        'observation': {
                            'output': {
                                'framework': 'n8n',
                                'status': 'error',
                                'error': str(e)
                            }
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'error',
                        'error': str(e)
                    })}\n\n"

                return

            if mode == "ioa_v2_dify":
                try:
                    yield f"data: {json.dumps({
                        'type': 'thought',
                        'iteration': 1,
                        'thought': 'The request should be delegated to Dify for app-based agent orchestration.',
                        'action': 'call_dify_chat_messages_api'
                    })}\n\n"

                    result = call_dify_agent(user_input)
                    steps = normalize_dify_steps(result)

                    latency_seconds = round(time.time() - start_time, 2)

                    log_dify_benchmark(
                        user_input=user_input,
                        latency_seconds=latency_seconds,
                        status="success",
                        step_count=len(steps)
                    )

                    first_step = steps[0]

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': first_step['iteration'],
                        'observation': {
                            'output': first_step['output']
                        }
                    })}\n\n"

                    for step in steps[1:]:
                        yield f"data: {json.dumps({
                            'type': 'thought',
                            'iteration': step['iteration'],
                            'thought': step['thought'],
                            'action': step['action']
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'observation',
                            'iteration': step['iteration'],
                            'observation': {
                                'output': step['output']
                            }
                        })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'final',
                        'final_answer': result['final_answer']
                    })}\n\n"
                except Exception as e:
                    latency_seconds = round(time.time() - start_time, 2)

                    log_dify_benchmark(
                        user_input=user_input,
                        latency_seconds=latency_seconds,
                        status="error",
                        step_count=0,
                        error=str(e)
                    )

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': 1,
                        'observation': {
                            'output': {
                                'framework': 'Dify',
                                'status': 'error',
                                'error': str(e)
                            }
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'error',
                        'error': str(e)
                    })}\n\n"

                return

            for event in ioa_v2_agent.run_stream(user_input):
                yield f"data: {json.dumps(event)}\n\n"

            latency_seconds = round(time.time() - start_time, 2)

            log_benchmark_result(
                mode="IOA v2 · Custom Python",
                prompt=user_input,
                latency_seconds=latency_seconds,
                accuracy_score=0,
                tool_usage_score=0,
                reasoning_clarity_score=0,
                observability_score=0,
                development_complexity_score=1,
                integration_speed_score=2,
                ecosystem_score=2,
                maintainability_score=3,
                notes="Automatic benchmark capture from streamed UI execution."
            )

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/devices", methods=["GET"])
def get_devices():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    devices = get_all_latest_devices()
    return jsonify({
        "source": get_telemetry_source(),
        "devices": devices
    })

def device_broadcast_loop():
    while True:
        if ENABLE_EMBEDDED_TELEMETRY:
            generate_telemetry_batch()

        socketio.emit("device_update", build_device_update_payload())

        time.sleep(TELEMETRY_BROADCAST_INTERVAL_SECONDS)

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
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    history = get_device_telemetry_history(device_id)

    return jsonify({
        "source": get_telemetry_source(),
        "device_id": device_id,
        "history": history
    })

@app.route("/api/mongo/telemetry/health", methods=["GET"])
def get_mongo_telemetry_health():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        limit = request.args.get("limit", default=5, type=int)
        return jsonify(get_telemetry_health(limit=limit))
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc)
        }), 503

@app.route("/api/mongo/telemetry/indexes", methods=["GET", "POST"])
def mongo_telemetry_indexes():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if request.method == "POST":
            ensure_telemetry_indexes()

        return jsonify(get_telemetry_indexes())
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry index check failed",
            "details": str(exc)
        }), 503

@app.route("/api/mongo/devices", methods=["GET"])
def get_mongo_devices():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        devices = get_all_latest_devices_from_mongo()
        return jsonify({
            "source": "mongodb",
            "devices": devices
        })
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc)
        }), 503

@app.route("/api/mongo/telemetry/<device_id>", methods=["GET"])
def get_mongo_device_history(device_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        limit = request.args.get("limit", default=30, type=int)
        history = get_device_telemetry_history_from_mongo(device_id, limit=limit)
        return jsonify({
            "source": "mongodb",
            "device_id": device_id,
            "history": history
        })
    except Exception as exc:
        return jsonify({
            "error": "MongoDB telemetry read failed",
            "details": str(exc)
        }), 503

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
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    if not chat_belongs_to_user(chat_id, session.get("user_id")):
        return jsonify({"error": "Chat not found"}), 404

    messages = get_messages(chat_id)

    return jsonify({
        "chat_id": chat_id,
        "messages": messages
    })


@app.route("/api/chats/<int:chat_id>/messages", methods=["POST"])
def api_add_message(chat_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    if not chat_belongs_to_user(chat_id, session.get("user_id")):
        return jsonify({"error": "Chat not found"}), 404

    data = request.get_json()

    role = data.get("role")
    content = data.get("content")
    reasoning_steps = data.get("reasoning_steps")

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

    success = delete_chat(chat_id, user_id)

    if not success:
        return jsonify({"error": "Chat not found"}), 404

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
