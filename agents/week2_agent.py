import json

from tools import TOOLS
from prompts import WEEK2_AGENT_PROMPT
from database import get_all_latest_devices


SYSTEM_LEVEL_TOOLS = [
    "check_system_overview",
    "check_system_alarms"
]


class Week2Agent:
    def __init__(self, client):
        self.client = client
        self.max_iterations = 3
        self.conversation_history = []
        self.last_target = None

    def run(self, user_input):
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
                final_answer = self.clean_final_answer(model_output)
                self.save_to_history(user_input, final_answer)

                return {
                    "final_answer": final_answer,
                    "steps": observations
                }

            thought, action = self.parse_action(model_output)

            if not action:
                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                return {
                    "final_answer": final_answer,
                    "steps": observations
                }

            if action not in TOOLS:
                final_answer = f"Invalid tool selected: {action}"

                return {
                    "final_answer": final_answer,
                    "steps": observations
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
                    "steps": observations
                }

        final_answer = self.generate_final_answer(
            user_input=user_input,
            observations=observations
        )

        self.save_to_history(user_input, final_answer)

        return {
            "final_answer": final_answer,
            "steps": observations
        }

    def run_stream(self, user_input):
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
                final_answer = self.clean_final_answer(model_output)

                self.save_to_history(user_input, final_answer)

                yield {
                    "type": "final",
                    "final_answer": final_answer
                }

                return

            thought, action = self.parse_action(model_output)

            if not action:
                final_answer = self.generate_final_answer(
                    user_input=user_input,
                    observations=observations
                )

                self.save_to_history(user_input, final_answer)

                yield {
                    "type": "final",
                    "final_answer": final_answer
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
                    "final_answer": final_answer
                }

                return

        final_answer = self.generate_final_answer(
            user_input=user_input,
            observations=observations
        )

        self.save_to_history(user_input, final_answer)

        yield {
            "type": "final",
            "final_answer": final_answer
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
    {WEEK2_AGENT_PROMPT}
    
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
    
    User request:
    {user_input}
    
    Collected observations:
    {json.dumps(observations, indent=2)}
    
    Based only on the observations, provide:
    1. Summary
    2. Evidence
    3. Likely cause
    4. Suggested next action
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