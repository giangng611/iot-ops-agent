import json

from tools import TOOLS
from prompts import WEEK2_AGENT_PROMPT


class Week2Agent:
    def __init__(self, client):
        self.client = client
        self.max_iterations = 3
        self.conversation_history = []

    def choose_next_step(self, user_input, observations):
        prompt = f"""
{WEEK2_AGENT_PROMPT}

User request:
{user_input}
    
Previous conversation:
{json.dumps(self.conversation_history, indent=2)}
    
Current observations:
{json.dumps(observations, indent=2)}
    
Available tools:
- check_device_status
- get_recent_logs
- check_alarm_rules

ACTION must be exactly one tool name only.
Do not include arguments, JSON, parentheses, or explanations.
    
If more information is needed, respond in this exact format:
THOUGHT: your reasoning
ACTION: tool_name

Put THOUGHT and ACTION on separate lines.
Do not include ACTION inside THOUGHT.
    
If enough information is available, respond in this exact format:
FINAL ANSWER: your final diagnosis
"""
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages = [
                {"role": "system", "content": prompt}
            ]
        )

        return response.choices[0].message.content.strip()

    def parse_action(self, model_output):
        thought = ""
        action = ""

        if "ACTION:" in model_output:
            before_action, after_action = model_output.split("ACTION:", 1)

            thought = before_action.replace("THOUGHT:", "").strip()

            action = after_action.strip()
            action = action.split()[0]
            action = action.replace("`", "").strip()

        return thought, action

    def run(self, user_input):
        observations = []

        device_id = self.extract_device(user_input)

        print(f"\n[Target Device]: {device_id}")

        for step in range(self.max_iterations):
            print(f"\n--- Iteration {step + 1} ---")

            model_output = self.choose_next_step(user_input, observations)

            if model_output.startswith("FINAL ANSWER:"):
                final_answer = model_output.replace("FINAL ANSWER:", "").strip()

                self.conversation_history.append({
                    "role": "user",
                    "content": user_input
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_answer
                })

                return final_answer
            thought, action = self.parse_action(model_output)

            print(f"[Thought]: {thought}")
            print(f"[Action]: {action}")

            if action not in TOOLS:
                return f"Invalid tool selected: {action}"

            tool_output = TOOLS[action](device_id)

            observation = {
                "iteration": step + 1,
                "thought": thought,
                "action": action,
                "output": tool_output
            }

            observations.append(observation)

            print("[Latest Observation]:")
            print(json.dumps(observation, indent=2))

        final_answer = self.generate_final_answer(user_input, observations)

        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": final_answer
        })

        return {
            "final_answer": final_answer,
            "steps": observations
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
                {"role": "system", "content": prompt}
            ]
        )

        return response.choices[0].message.content.strip()

    def extract_device(self, user_input):

        prompt = f"""
    Extract the device ID from this request.

    Available devices:
    - sensor-001
    - sensor-002
    - gateway-003

    User request:
    {user_input}

    Return ONLY the device ID.
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

    def run_stream(self, user_input):
        observations = []

        for step in range(self.max_iterations):
            model_output = self.choose_next_step(user_input, observations)

            if model_output.startswith("FINAL ANSWER:"):
                final_answer = model_output.replace("FINAL ANSWER:", "").strip()
                yield {
                    "type": "final",
                    "final_answer": final_answer
                }
                return

            thought, action = self.parse_action(model_output)

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

            device_id = self.extract_device(user_input)

            tool_output = TOOLS[action](device_id)

            observation = {
                "iteration": step + 1,
                "thought": thought,
                "action": action,
                "output": tool_output
            }

            observations.append(observation)

            yield {
                "type": "observation",
                "iteration": step + 1,
                "observation": observation
            }

        final_answer = self.generate_final_answer(user_input, observations)

        yield {
            "type": "final",
            "final_answer": final_answer
        }
