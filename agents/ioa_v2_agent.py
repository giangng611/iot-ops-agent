import json
import re

from tools import TOOLS
from prompts import (
    COMPANY_CONTEXT_INSTRUCTION,
    DIAGNOSIS_OUTPUT_FORMAT,
    IOA_V2_AGENT_PROMPT,
)
from storage.telemetry_store import get_all_latest_devices
from services.company_data_service import (
    get_company_device_context,
    get_company_disconnected_context,
    get_company_inventory_context,
    get_company_rule_readiness_context,
    get_company_telemetry_coverage_context,
    scan_company_payload_threshold,
)


SYSTEM_LEVEL_TOOLS = [
    "check_system_overview",
    "check_system_alarms"
]
COMPANY_CONTEXT_TOOLS = {
    "inspect_company_fleet_summary",
    "inspect_company_device_samples",
    "inspect_company_alerts",
    "inspect_company_provenance",
}
COMPANY_DB_TOOLS = {
    "get_company_inventory",
    "get_company_telemetry_coverage",
    "get_company_rule_readiness",
    "get_company_disconnected_devices",
    "get_company_device",
    "scan_company_threshold",
}


class IOAV2Agent:
    def __init__(self, client):
        self.client = client
        self.max_iterations = 3
        self.conversation_history = []
        self.last_target = None
        self.current_token_usage = None

    def reset_token_usage(self):
        self.current_token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "source": "openai_chat_completions_usage"
        }

    def record_token_usage(self, response):
        usage = getattr(response, "usage", None)

        if not usage:
            return

        if self.current_token_usage is None:
            self.reset_token_usage()

        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (
            input_tokens + output_tokens
        )

        self.current_token_usage["input_tokens"] += input_tokens
        self.current_token_usage["output_tokens"] += output_tokens
        self.current_token_usage["total_tokens"] += total_tokens

    def get_token_usage(self):
        if not self.current_token_usage:
            return None

        if not self.current_token_usage["total_tokens"]:
            return None

        return dict(self.current_token_usage)

    def run(self, user_input):
        self.reset_token_usage()
        observations = []
        target = self.extract_target(user_input)
        if target != "SYSTEM":
            self.last_target = target

        for step in range(self.max_iterations):
            model_output = self.choose_next_step(
                user_input=user_input,
                observations=observations,
                target=target
            )

            if model_output.startswith("FINAL ANSWER:"):
                if not observations:
                    observations.append(
                        self.collect_required_evidence(target)
                    )
                    continue

                final_answer = self.clean_final_answer(model_output)
                self.save_to_history(user_input, final_answer)

                return {
                    "final_answer": final_answer,
                    "steps": observations,
                    "token_usage": self.get_token_usage()
                }

            thought, action = self.parse_action(model_output)

            if not action:
                if not observations:
                    observations.append(
                        self.collect_required_evidence(target)
                    )

                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                return {
                    "final_answer": final_answer,
                    "steps": observations,
                    "token_usage": self.get_token_usage()
                }

            if action not in TOOLS:
                final_answer = f"Invalid tool selected: {action}"

                return {
                    "final_answer": final_answer,
                    "steps": observations,
                    "token_usage": self.get_token_usage()
                }

            tool_output = self.execute_tool(
                action=action,
                target=target
            )

            observation = self.build_observation(
                iteration=step + 1,
                thought=thought,
                action=action,
                output=tool_output
            )

            observations.append(observation)

            if self.has_enough_system_evidence(target, observations):
                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                return {
                    "final_answer": final_answer,
                    "steps": observations,
                    "token_usage": self.get_token_usage()
                }

        final_answer = self.generate_final_answer(
            user_input=user_input,
            observations=observations
        )

        self.save_to_history(user_input, final_answer)

        return {
            "final_answer": final_answer,
            "steps": observations,
            "token_usage": self.get_token_usage()
        }

    def run_with_operational_context(self, user_input, operational_context):
        self.reset_token_usage()
        observations = [
            self.build_company_context_observation(operational_context)
        ]
        action = self.choose_company_tool(
            user_input,
            operational_context,
        )
        observations.append(
            self.build_observation(
                iteration=2,
                thought=self.company_tool_thought(action),
                action=action,
                output=self.execute_company_tool(
                    action,
                    user_input,
                    operational_context,
                ),
            )
        )
        final_answer = self.generate_context_answer(
            user_input,
            operational_context,
            observations,
        )
        self.save_to_history(user_input, final_answer)
        return {
            "final_answer": final_answer,
            "steps": observations,
            "token_usage": self.get_token_usage(),
        }

    def run_stream_with_operational_context(
        self,
        user_input,
        operational_context,
    ):
        self.reset_token_usage()
        observations = [
            self.build_company_context_observation(operational_context)
        ]

        for step in observations:
            yield self.company_thought_event(step)
            yield self.company_observation_event(step)

        action = self.choose_company_tool(user_input, operational_context)
        targeted_observation = self.build_observation(
            iteration=2,
            thought=self.company_tool_thought(action),
            action=action,
            output=self.execute_company_tool(
                action,
                user_input,
                operational_context,
            ),
        )
        observations.append(targeted_observation)
        yield self.company_thought_event(targeted_observation)
        yield self.company_observation_event(targeted_observation)

        final_answer = self.generate_context_answer(
            user_input,
            operational_context,
            observations,
        )
        self.save_to_history(user_input, final_answer)
        yield {
            "type": "final",
            "final_answer": final_answer,
            "token_usage": self.get_token_usage(),
        }

    def run_stream(self, user_input):
        self.reset_token_usage()
        observations = []
        target = self.extract_target(user_input)
        if target != "SYSTEM":
            self.last_target = target

        for step in range(self.max_iterations):
            model_output = self.choose_next_step(
                user_input=user_input,
                observations=observations,
                target=target
            )

            if model_output.startswith("FINAL ANSWER:"):
                if not observations:
                    observation = self.collect_required_evidence(target)
                    observations.append(observation)
                    yield {
                        "type": "thought",
                        "iteration": observation["iteration"],
                        "thought": observation["thought"],
                        "action": observation["action"],
                    }
                    yield {
                        "type": "observation",
                        "iteration": observation["iteration"],
                        "observation": observation,
                    }
                    continue

                final_answer = self.clean_final_answer(model_output)

                self.save_to_history(user_input, final_answer)

                yield {
                    "type": "final",
                    "final_answer": final_answer,
                    "token_usage": self.get_token_usage()
                }

                return

            thought, action = self.parse_action(model_output)

            if not action:
                if not observations:
                    observation = self.collect_required_evidence(target)
                    observations.append(observation)
                    yield {
                        "type": "thought",
                        "iteration": observation["iteration"],
                        "thought": observation["thought"],
                        "action": observation["action"],
                    }
                    yield {
                        "type": "observation",
                        "iteration": observation["iteration"],
                        "observation": observation,
                    }

                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                yield {
                    "type": "final",
                    "final_answer": final_answer,
                    "token_usage": self.get_token_usage()
                }

                return

            yield {
                "type": "thought",
                "iteration": step + 1,
                "thought": thought,
                "action": action
            }

            if action not in TOOLS:
                yield {
                    "type": "error",
                    "error": f"Invalid tool selected: {action}"
                }
                return

            tool_output = self.execute_tool(
                action=action,
                target=target
            )

            observation = self.build_observation(
                iteration=step + 1,
                thought=thought,
                action=action,
                output=tool_output
            )

            observations.append(observation)

            yield {
                "type": "observation",
                "iteration": step + 1,
                "observation": observation
            }

            if self.has_enough_system_evidence(target, observations):
                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                yield {
                    "type": "final",
                    "final_answer": final_answer,
                    "token_usage": self.get_token_usage()
                }

                return

        final_answer = self.generate_final_answer(
            user_input=user_input,
            observations=observations
        )

        self.save_to_history(user_input, final_answer)

        yield {
            "type": "final",
            "final_answer": final_answer,
            "token_usage": self.get_token_usage()
        }

    def extract_target(self, user_input):
        devices = get_all_latest_devices()
        device_ids = [
            device["device_id"]
            for device in devices
        ]

        if self.last_target and self.contains_context_reference(user_input):
            return self.last_target

        prompt = f"""
    Extract the target from the user request.

    Available devices:
    {json.dumps(device_ids, indent=2)}

    User request:
    {user_input}

    If the request is about the whole system, all devices, fleet health,
    overall health, unhealthy devices, critical devices, or alarms across devices,
    return SYSTEM.

    If the user refers to a previous device using phrases like "it", "its",
    "that device", "this device", or "same device", return the most recent
    device target if available.

    Otherwise, return exactly one device ID from the list.

    Return ONLY one value:
    - SYSTEM
    - or a device ID
    """

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )
        self.record_token_usage(response)

        target = response.choices[0].message.content.strip()

        if target in device_ids:
            self.last_target = target
            return target

        if target == "SYSTEM":
            return "SYSTEM"

        if self.last_target:
            return self.last_target

        return "SYSTEM"

    def choose_next_step(self, user_input, observations, target):
        prompt = f"""
    {IOA_V2_AGENT_PROMPT}
    
    User request:
    {user_input}
    
    Target:
    {target}
    
    Previous conversation:
    {json.dumps(self.conversation_history, indent=2)}
    
    Current observations:
    {json.dumps(observations, indent=2)}
    
    Available tools:
    - check_device_status
    - get_recent_logs
    - check_alarm_rules
    - check_system_overview
    - check_system_alarms
    
    Tool rules:
    - Use check_system_overview for fleet-wide health, all devices, unhealthy devices, or critical devices.
    - Use check_system_alarms for fleet-wide alarm summaries.
    - Use check_device_status only when Target is a specific device ID.
    - Use get_recent_logs only when Target is a specific device ID.
    - Use check_alarm_rules only when Target is a specific device ID.
    
    If Target is SYSTEM, do not use device-specific tools.
    
    ACTION must be exactly one tool name only.
    Do not include arguments, JSON, parentheses, or explanations.
    Put THOUGHT and ACTION on separate lines.
    Do not include ACTION inside THOUGHT.
    
    If more information is needed, respond in this exact format:
    THOUGHT: your reasoning
    ACTION: tool_name
    
    If enough information is already available from previous observations,
    do NOT call additional tools unnecessarily.
    
    When system-level tools already provide sufficient evidence,
    prefer generating a FINAL ANSWER instead of calling more tools.
    
    Do not repeat investigations already covered by previous observations.
    
    If enough information is available, respond in this exact format:
    FINAL ANSWER: your final diagnosis
    
    The final diagnosis must follow the shared Operational Diagnosis format:
    Summary, Evidence, Likely Cause, Suggested Next Action.
    
    Maximum reasoning guideline:
    - Fleet-level diagnosis usually requires only 1-2 system-level tools.
    - Avoid device-specific tools during fleet-wide investigations.
    """

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )
        self.record_token_usage(response)

        return response.choices[0].message.content.strip()

    def parse_action(self, model_output):
        thought = ""
        action = ""

        if "ACTION:" not in model_output:
            return thought, action

        before_action, after_action = model_output.split("ACTION:", 1)

        thought = before_action.replace("THOUGHT:", "").strip()

        action = after_action.strip()
        action = action.split()[0]
        action = action.replace("`", "").strip()

        return thought, action

    def execute_tool(self, action, target):
        if action in SYSTEM_LEVEL_TOOLS:
            return TOOLS[action]()

        if target == "SYSTEM":
            return {
                "error": "Device-specific tool called without a device target",
                "action": action
            }

        return TOOLS[action](target)

    def collect_required_evidence(self, target):
        action = (
            "check_system_overview"
            if target == "SYSTEM"
            else "check_device_status"
        )
        return self.build_observation(
            iteration=1,
            thought=(
                "Collect telemetry evidence before producing a final answer."
            ),
            action=action,
            output=self.execute_tool(action, target),
        )

    def build_observation(self, iteration, thought, action, output):
        return {
            "iteration": iteration,
            "thought": thought,
            "action": action,
            "output": output
        }

    def generate_final_answer(self, user_input, observations):
        prompt = f"""
    You are an IoT operations AI agent.

    {DIAGNOSIS_OUTPUT_FORMAT}

    User request:
    {user_input}

    Collected observations:
    {json.dumps(observations, indent=2)}

    Base your answer only on the collected observations.
    """

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )
        self.record_token_usage(response)

        return response.choices[0].message.content.strip()

    def build_company_context_observation(self, operational_context):
        return self.build_observation(
            iteration=1,
            thought=(
                "Verify the active Company MongoDB snapshot and its "
                "read-only provenance before selecting focused evidence."
            ),
            action="read_company_operational_context",
            output={
                "source": operational_context.get("source"),
                "record_count": operational_context.get("record_count"),
                "rules_status": operational_context.get("rules_status"),
                "provenance": operational_context.get("provenance"),
            },
        )

    def choose_company_tool(self, user_input, operational_context):
        prompt = f"""
    You are selecting one read-only Company DB evidence tool.

    User request:
    {user_input}

    Available snapshot fields:
    {json.dumps({
        "record_count": operational_context.get("record_count"),
        "has_summary": bool(operational_context.get("summary")),
        "has_alerts": bool(operational_context.get("alerts")),
        "sample_count": len(
            operational_context.get("sample_records") or []
        ),
    }, indent=2)}

    Choose exactly one tool:
    - inspect_company_fleet_summary
    - inspect_company_device_samples
    - inspect_company_alerts
    - inspect_company_provenance
    - get_company_inventory
    - get_company_telemetry_coverage
    - get_company_rule_readiness
    - get_company_disconnected_devices
    - get_company_device
    - scan_company_threshold

    Use get_company_device only when the request names a device.
    Use scan_company_threshold only when the request includes a numeric
    greater-than or above threshold.
    Return only the tool name.
    """
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": prompt}],
        )
        self.record_token_usage(response)
        action = response.choices[0].message.content.strip()
        allowed_tools = COMPANY_CONTEXT_TOOLS | COMPANY_DB_TOOLS

        if (
            action == "get_company_device"
            and not self.extract_company_identifier(user_input)
        ):
            return self.fallback_company_tool(user_input)

        if (
            action == "scan_company_threshold"
            and self.extract_threshold(user_input) is None
        ):
            return self.fallback_company_tool(user_input)

        if action in allowed_tools:
            return action

        return self.fallback_company_tool(user_input)

    def fallback_company_tool(self, user_input):
        lowered = user_input.lower()

        if self.extract_threshold(user_input) is not None and any(
            marker in lowered
            for marker in ("greater than", "above", ">", "lớn hơn", "vượt")
        ):
            return "scan_company_threshold"

        keyword_tools = (
            (
                ("disconnected", "offline", "mất kết nối", "mat ket noi"),
                "get_company_disconnected_devices",
            ),
            (
                ("coverage", "unmapped", "metric", "telemetry coverage"),
                "get_company_telemetry_coverage",
            ),
            (
                ("rule", "grafana", "luật", "luat"),
                "get_company_rule_readiness",
            ),
            (
                ("alert", "alarm", "cảnh báo", "canh bao"),
                "inspect_company_alerts",
            ),
            (
                ("inventory", "node", "device list", "danh sách"),
                "get_company_inventory",
            ),
        )

        for keywords, action in keyword_tools:
            if any(keyword in lowered for keyword in keywords):
                return action

        if self.extract_company_identifier(user_input):
            return "get_company_device"

        return "inspect_company_fleet_summary"

    def execute_company_tool(
        self,
        action,
        user_input,
        operational_context,
    ):
        if action == "inspect_company_fleet_summary":
            return {
                "source": operational_context.get("source"),
                "record_count": operational_context.get("record_count"),
                "distinct_device_count": operational_context.get(
                    "distinct_device_count"
                ),
                "summary": operational_context.get("summary"),
                "classification_status": operational_context.get(
                    "classification_status"
                ),
                "rules_status": operational_context.get("rules_status"),
            }

        if action == "inspect_company_device_samples":
            return {
                "source": operational_context.get("source"),
                "samples": operational_context.get("sample_records") or [],
            }

        if action == "inspect_company_alerts":
            return {
                "source": operational_context.get("source"),
                "alerts": operational_context.get("alerts"),
                "rules_status": operational_context.get("rules_status"),
                "rules_message": operational_context.get("rules_message"),
            }

        if action == "inspect_company_provenance":
            return {
                "source": operational_context.get("source"),
                "provenance": operational_context.get("provenance"),
                "interpretation_notes": operational_context.get(
                    "interpretation_notes"
                ),
            }

        try:
            if action == "get_company_inventory":
                return get_company_inventory_context()
            if action == "get_company_telemetry_coverage":
                return get_company_telemetry_coverage_context()
            if action == "get_company_rule_readiness":
                return get_company_rule_readiness_context()
            if action == "get_company_disconnected_devices":
                return get_company_disconnected_context()
            if action == "get_company_device":
                identifier = self.extract_company_identifier(user_input)
                if not identifier:
                    return {
                        "source": operational_context.get("source"),
                        "error": "No company device identifier was detected.",
                    }
                return get_company_device_context(identifier)
            if action == "scan_company_threshold":
                threshold = self.extract_threshold(user_input)
                if threshold is None:
                    return {
                        "source": operational_context.get("source"),
                        "error": "No numeric threshold was detected.",
                    }
                return scan_company_payload_threshold(threshold)
        except Exception as exc:
            return {
                "source": operational_context.get("source"),
                "tool": action,
                "error": f"Company DB tool failed: {exc}",
            }

        return {
            "source": operational_context.get("source"),
            "error": f"Unsupported Company DB tool: {action}",
        }

    def company_tool_thought(self, action):
        return (
            "Collect focused Company DB evidence with the read-only "
            f"{action} tool before producing the answer."
        )

    def company_thought_event(self, observation):
        return {
            "type": "thought",
            "iteration": observation["iteration"],
            "thought": observation["thought"],
            "action": observation["action"],
        }

    def company_observation_event(self, observation):
        return {
            "type": "observation",
            "iteration": observation["iteration"],
            "observation": observation,
        }

    def extract_company_identifier(self, user_input):
        tokens = [
            token.strip("()[]{}.,:/")
            for token in user_input.split()
            if token.strip("()[]{}.,:/")
        ]
        ignored = {
            "company",
            "device",
            "diagnose",
            "check",
            "show",
            "inspect",
            "thiết",
            "bị",
            "thiet",
            "bi",
        }

        for token in reversed(tokens):
            lowered = token.lower()
            if lowered in ignored:
                continue
            if (
                (
                    lowered.startswith("s")
                    and any(character.isdigit() for character in token)
                )
                or lowered.startswith(("dvi-", "dvi_", "nod_"))
                or "_" in token
                or "-" in token
            ):
                return token

        return ""

    def extract_threshold(self, user_input):
        matches = re.findall(r"-?\d+(?:\.\d+)?", user_input)

        if not matches:
            return None

        try:
            return float(matches[-1])
        except ValueError:
            return None

    def generate_context_answer(
        self,
        user_input,
        operational_context,
        observations,
    ):
        prompt = f"""
    You are an IoT operations AI agent.

    {COMPANY_CONTEXT_INSTRUCTION}

    {DIAGNOSIS_OUTPUT_FORMAT}

    User request:
    {user_input}

    Company DB observations:
    {json.dumps(observations, indent=2)}

    The source snapshot metadata is:
    {json.dumps({
        "source": operational_context.get("source"),
        "rules_status": operational_context.get("rules_status"),
    }, indent=2)}

    Base the answer only on the collected observations. If a focused tool
    returned an error, state that the evidence could not be retrieved.
    """
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": prompt}],
        )
        self.record_token_usage(response)
        return response.choices[0].message.content.strip()

    def clean_final_answer(self, model_output):
        return model_output.replace("FINAL ANSWER:", "").strip()

    def save_to_history(self, user_input, final_answer):
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        self.conversation_history.append({
            "role": "assistant",
            "content": final_answer
        })

    def contains_context_reference(self, user_input):
        lowered = user_input.lower()

        context_words = [
            "it",
            "its",
            "that device",
            "this device",
            "same device",
            "that one",
            "this one",
            "previous device",
            "the device"
        ]

        return any(word in lowered for word in context_words)

    def has_enough_system_evidence(self, target, observations):
        if target != "SYSTEM":
            return False

        actions = [
            observation["action"]
            for observation in observations
        ]

        return (
                "check_system_overview" in actions
                and "check_system_alarms" in actions
        )
