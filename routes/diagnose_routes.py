import json
import time
from collections import defaultdict, deque

from flask import Blueprint, Response, current_app, jsonify, request, session

from benchmark_logger import log_benchmark_result
from routes.helpers import login_required
from services.diagnose_service import (
    call_dify_agent,
    call_n8n_agent,
    log_dify_benchmark,
    log_n8n_benchmark,
    normalize_dify_steps,
    normalize_n8n_steps,
    resolve_agent_operational_context,
)


def create_diagnose_blueprint(runtime):
    diagnose_bp = Blueprint("diagnose", __name__)
    ioa_v1_agent = runtime["ioa_v1_agent"]
    ioa_v2_agent = runtime["ioa_v2_agent"]
    ioa_v3_agent = runtime.get("ioa_v3_agent")
    langchain_agent = runtime["langchain_agent"]
    langgraph_agent = runtime["langgraph_agent"]
    get_max_message_chars = runtime.get(
        "get_max_message_chars",
        lambda: runtime["max_message_chars"],
    )
    get_rate_limit_requests = runtime.get(
        "get_rate_limit_requests",
        lambda: runtime["rate_limit_requests"],
    )
    get_rate_limit_window_seconds = runtime.get(
        "get_rate_limit_window_seconds",
        lambda: runtime["rate_limit_window_seconds"],
    )
    diagnose_rate_limit_log = runtime.get("diagnose_rate_limit_log") or defaultdict(deque)
    public_runtime_error = (
        "The requested runtime failed. Please try again later."
    )

    runtime_metadata = {
        "ioa_v1_custom": {
            "runtime_label": "IOA v1 · Custom Python",
            "model_name": "gpt-4.1-mini",
        },
        "ioa_v2_custom": {
            "runtime_label": "IOA v2 · Custom Python",
            "model_name": "gpt-4.1-mini",
        },
        "ioa_v2_langchain": {
            "runtime_label": "IOA v2 · LangChain",
            "model_name": "gpt-4o-mini",
        },
        "ioa_v2_langgraph": {
            "runtime_label": "IOA v2 · LangGraph",
            "model_name": "gpt-4o-mini",
        },
        "ioa_v2_n8n": {
            "runtime_label": "IOA v2 · n8n",
            "model_name": "n8n workflow model",
        },
        "ioa_v2_dify": {
            "runtime_label": "IOA v2 · Dify",
            "model_name": "Dify app model",
        },
        "ioa_v3_langgraph_n8n": {
            "runtime_label": "IOA v3 · Ops Graph",
            "model_name": "gpt-4o-mini + operational workflow",
        },
    }

    def add_runtime_metadata(token_usage, mode):
        metadata = runtime_metadata.get(mode, runtime_metadata["ioa_v2_custom"])
        usage = dict(token_usage or {})

        usage["runtime_label"] = metadata["runtime_label"]
        usage["model_name"] = metadata["model_name"]

        return usage

    def get_rate_limit_key():
        user_id = session.get("user_id")

        if user_id:
            return f"user:{user_id}"

        return f"ip:{request.remote_addr or 'unknown'}"

    def check_diagnose_rate_limit():
        now = time.time()
        key = get_rate_limit_key()
        request_times = diagnose_rate_limit_log[key]
        rate_limit_requests = get_rate_limit_requests()
        rate_limit_window_seconds = get_rate_limit_window_seconds()
        window_start = now - rate_limit_window_seconds

        while request_times and request_times[0] <= window_start:
            request_times.popleft()

        if len(request_times) >= rate_limit_requests:
            retry_after = max(
                1,
                int(rate_limit_window_seconds - (now - request_times[0]))
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
        max_message_chars = get_max_message_chars()

        if not user_input:
            return None, (jsonify({"error": "No message provided"}), 400)

        if len(user_input) > max_message_chars:
            return None, (
                jsonify({
                    "error": (
                        "Message is too long. Please keep diagnosis requests "
                        f"under {max_message_chars} characters."
                    )
                }),
                413
            )

        data["message"] = user_input
        return data, None

    @diagnose_bp.route("/api/diagnose", methods=["POST"])
    def diagnose():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 401

        data, error_response = validate_diagnose_request()

        if error_response:
            return error_response

        user_input = data["message"]

        try:
            mode = data.get("mode", "ioa_v2_custom")
            data_source = data.get("data_source", session.get(
                "selected_data_source",
                "simulator",
            ))
            source_resolution = resolve_agent_operational_context(data_source)
            company_context = source_resolution.get("operational_context")
            effective_data_source = (
                "company"
                if source_resolution.get("active_source") == "company_mongodb"
                else "simulator"
            )
            start_time = time.time()

            if mode == "ioa_v1_custom":
                result = (
                    ioa_v1_agent.run_with_operational_context(
                        user_input,
                        company_context,
                    )
                    if company_context is not None
                    else ioa_v1_agent.run(user_input)
                )

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
                    "response": result["final_answer"],
                    "steps": [],
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            if mode == "ioa_v2_langgraph":
                result = langgraph_agent.run(
                    user_input,
                    data_source=effective_data_source,
                )

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
                    "steps": result["steps"],
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            if mode == "ioa_v2_langchain":
                result = langchain_agent.run(
                    user_input,
                    operational_context=company_context,
                )

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
                    "steps": result["steps"],
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            if mode == "ioa_v2_n8n":
                try:
                    result = call_n8n_agent(
                        user_input,
                        source_resolution=source_resolution,
                    )
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
                    "steps": steps,
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            if mode == "ioa_v2_dify":
                try:
                    result = call_dify_agent(
                        user_input,
                        source_resolution=source_resolution,
                    )
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
                    "steps": steps,
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            if mode == "ioa_v3_langgraph_n8n":
                if ioa_v3_agent is None:
                    raise RuntimeError("IOA v3 runtime is not configured.")

                result = ioa_v3_agent.run(
                    user_input,
                    selected_source=data_source,
                    source_resolution=source_resolution,
                    user_id=session.get("user_id"),
                )

                latency_seconds = round(
                    time.time() - start_time,
                    2
                )

                log_benchmark_result(
                    mode="IOA v3 · Ops Graph",
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
                    notes="Automatic benchmark capture from IOA v3 operational workflow."
                )

                return jsonify({
                    "response": result["final_answer"],
                    "steps": result["steps"],
                    "token_usage": add_runtime_metadata(
                        result.get("token_usage"),
                        mode
                    )
                })

            result = (
                ioa_v2_agent.run_with_operational_context(
                    user_input,
                    company_context,
                )
                if company_context is not None
                else ioa_v2_agent.run(user_input)
            )

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
                "steps": result["steps"],
                "token_usage": add_runtime_metadata(
                    result.get("token_usage"),
                    mode
                )
            })

        except Exception as exc:
            current_app.logger.exception(
                "Diagnose runtime failed: %s",
                exc,
            )
            return jsonify({
                "error": public_runtime_error,
            }), 500

    @diagnose_bp.route("/api/diagnose-stream", methods=["POST"])
    def diagnose_stream():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 401

        data, error_response = validate_diagnose_request()

        if error_response:
            return error_response

        user_input = data["message"]
        mode = data.get("mode", "ioa_v2_custom")
        data_source = data.get("data_source", session.get(
            "selected_data_source",
            "simulator",
        ))
        source_resolution = resolve_agent_operational_context(data_source)
        company_context = source_resolution.get("operational_context")
        effective_data_source = (
            "company"
            if source_resolution.get("active_source") == "company_mongodb"
            else "simulator"
        )
        start_time = time.time()
        app_logger = current_app.logger
        session_user_id = session.get("user_id")

        def generate():
            try:
                if mode == "ioa_v2_langgraph":
                    for event in langgraph_agent.run_stream(
                        user_input,
                        data_source=effective_data_source,
                    ):
                        if event.get("type") == "final":
                            event["token_usage"] = add_runtime_metadata(
                                event.get("token_usage"),
                                mode
                            )
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
                        'action': 'Initialize LangChain agent execution',
                        'workflow': {
                            'framework': 'LangChain',
                            'node_id': 'create_agent',
                            'node_label': 'Create agent'
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': 1,
                        'observation': {
                            'output': {
                                'framework': 'LangChain',
                                'agent_style': 'Framework-managed tool-calling agent',
                                'trace_visibility': 'Limited internal reasoning visibility',
                                'note': 'LangChain create_agent is initialized with IoT telemetry tools.'
                            }
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'thought',
                        'iteration': 2,
                        'thought': 'LangChain is running its framework-managed tool-calling loop.',
                        'action': 'Run LangChain agent loop',
                        'workflow': {
                            'framework': 'LangChain',
                            'node_id': 'agent_loop',
                            'node_label': 'Agent loop'
                        }
                    })}\n\n"

                    result = langchain_agent.run(
                        user_input,
                        operational_context=company_context,
                    )

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
                        'iteration': 2,
                        'observation': {
                            'output': result['steps'][0]['output']
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'thought',
                        'iteration': 3,
                        'thought': 'LangChain returned a final operational diagnosis.',
                        'action': 'Format final answer for IoT Ops Agent UI',
                        'workflow': {
                            'framework': 'LangChain',
                            'node_id': 'final_answer',
                            'node_label': 'Final answer'
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'observation',
                        'iteration': 3,
                        'observation': {
                            'output': {
                                'framework': 'LangChain',
                                'status': 'final_answer_ready'
                            }
                        }
                    })}\n\n"

                    yield f"data: {json.dumps({
                        'type': 'final',
                        'final_answer': result['final_answer'],
                        'token_usage': add_runtime_metadata(
                            result.get('token_usage'),
                            mode
                        )
                    })}\n\n"

                    return

                if mode == "ioa_v2_n8n":
                    try:
                        yield f"data: {json.dumps({
                            'type': 'thought',
                            'iteration': 1,
                            'thought': 'The request should be delegated to n8n for workflow-based orchestration.',
                            'action': 'call_n8n_webhook',
                            'workflow': {
                                'framework': 'n8n',
                                'node_id': 'webhook',
                                'node_label': 'Webhook'
                            }
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'observation',
                            'iteration': 1,
                            'observation': {
                                'output': {
                                    'framework': 'n8n',
                                    'status': 'request_dispatched',
                                    'webhook_url_configured': True
                                }
                            }
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'thought',
                            'iteration': 2,
                            'thought': 'n8n should now execute the configured workflow and LLM chain.',
                            'action': 'run_n8n_workflow',
                            'workflow': {
                                'framework': 'n8n',
                                'node_id': 'workflow',
                                'node_label': 'Basic LLM Chain'
                            }
                        })}\n\n"

                        result = call_n8n_agent(
                            user_input,
                            source_resolution=source_resolution,
                        )
                        normalized_steps = normalize_n8n_steps(result)

                        latency_seconds = round(time.time() - start_time, 2)

                        log_n8n_benchmark(
                            user_input=user_input,
                            latency_seconds=latency_seconds,
                            status="success",
                            step_count=len(normalized_steps)
                        )

                        yield f"data: {json.dumps({
                            'type': 'observation',
                            'iteration': 2,
                            'observation': {
                                'output': {
                                    'framework': 'n8n',
                                    'status': 'workflow_response_received',
                                    'latency_seconds': latency_seconds,
                                    'returned_step_count': max(
                                        len(normalized_steps) - 1,
                                        0
                                    ),
                                    'answer_preview': result['final_answer'][:300]
                                }
                            }
                        })}\n\n"

                        for iteration, step in enumerate(
                            normalized_steps[1:],
                            start=3
                        ):
                            yield f"data: {json.dumps({
                                'type': 'thought',
                                'iteration': iteration,
                                'thought': step['thought'],
                                'action': step['action'],
                                'workflow': {
                                    'framework': 'n8n',
                                    'node_id': 'code',
                                    'node_label': 'Code in JavaScript'
                                }
                            })}\n\n"

                            yield f"data: {json.dumps({
                                'type': 'observation',
                                'iteration': iteration,
                                'observation': {
                                    'output': step['output']
                                }
                            })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'final',
                            'final_answer': result['final_answer'],
                            'token_usage': add_runtime_metadata(
                                result.get('token_usage'),
                                mode
                            )
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
                                    'error': public_runtime_error,
                                }
                            }
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'error',
                            'error': public_runtime_error,
                        })}\n\n"

                    return

                if mode == "ioa_v3_langgraph_n8n":
                    if ioa_v3_agent is None:
                        raise RuntimeError("IOA v3 runtime is not configured.")

                    try:
                        for event in ioa_v3_agent.run_stream(
                            user_input,
                            selected_source=data_source,
                            source_resolution=source_resolution,
                            user_id=session_user_id,
                        ):
                            if event.get("type") == "final":
                                event["token_usage"] = add_runtime_metadata(
                                    event.get("token_usage"),
                                    mode
                                )
                            yield f"data: {json.dumps(event)}\n\n"

                        latency_seconds = round(time.time() - start_time, 2)

                        log_benchmark_result(
                            mode="IOA v3 · Ops Graph",
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
                            notes="Automatic benchmark capture from streamed IOA v3 operational workflow."
                        )
                    except Exception as exc:
                        app_logger.exception(
                            "IOA v3 stream runtime failed: %s",
                            exc,
                        )
                        yield f"data: {json.dumps({
                            'type': 'observation',
                            'iteration': 1,
                            'observation': {
                                'output': {
                                    'framework': 'LangGraph+n8n',
                                    'status': 'error',
                                    'error': public_runtime_error,
                                }
                            }
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'error',
                            'error': public_runtime_error,
                        })}\n\n"

                    return

                if mode == "ioa_v2_dify":
                    try:
                        yield f"data: {json.dumps({
                            'type': 'thought',
                            'iteration': 1,
                            'thought': 'The request should be delegated to Dify for app-based agent orchestration.',
                            'action': 'call_dify_chat_messages_api',
                            'workflow': {
                                'framework': 'Dify',
                                'node_id': 'chat_api',
                                'node_label': 'Chat API'
                            }
                        })}\n\n"

                        result = call_dify_agent(
                            user_input,
                            source_resolution=source_resolution,
                        )
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
                            'final_answer': result['final_answer'],
                            'token_usage': add_runtime_metadata(
                                result.get('token_usage'),
                                mode
                            )
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
                                    'error': public_runtime_error,
                                }
                            }
                        })}\n\n"

                        yield f"data: {json.dumps({
                            'type': 'error',
                            'error': public_runtime_error,
                        })}\n\n"

                    return

                if mode == "ioa_v1_custom":
                    result = (
                        ioa_v1_agent.run_with_operational_context(
                            user_input,
                            company_context,
                        )
                        if company_context is not None
                        else ioa_v1_agent.run(user_input)
                    )
                    yield f"data: {json.dumps({
                        'type': 'final',
                        'final_answer': result['final_answer'],
                        'token_usage': add_runtime_metadata(
                            result.get('token_usage'),
                            mode
                        )
                    })}\n\n"
                    return

                stream = (
                    ioa_v2_agent.run_stream_with_operational_context(
                        user_input,
                        company_context,
                    )
                    if company_context is not None
                    else ioa_v2_agent.run_stream(user_input)
                )

                for event in stream:
                    if event.get("type") == "final":
                        event["token_usage"] = add_runtime_metadata(
                            event.get("token_usage"),
                            mode
                        )
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

            except Exception as exc:
                app_logger.exception(
                    "Diagnose stream runtime failed: %s",
                    exc,
                )
                yield f"data: {json.dumps({
                    'type': 'error',
                    'error': public_runtime_error,
                })}\n\n"

        return Response(generate(), mimetype="text/event-stream")

    def device_broadcast_loop():
        while True:
            if ENABLE_EMBEDDED_TELEMETRY:
                generate_telemetry_batch()

    return diagnose_bp
