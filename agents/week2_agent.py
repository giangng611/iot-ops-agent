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
    
If more information is needed, respond in this exact format:
THOUGHT: your reasoning
ACTION: tool_name
    
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
        lines = model_output.splitlines()

        thought = ""
        action = ""

        for line in lines:
            if line.startswith("THOUGHT:"):
                thought = line.replace("THOUGHT:", "").strip()
            elif line.startswith("ACTION:"):
                action = line.replace("ACTION:", "").strip()

        return thought, action

    def run(self, user_input):
        observations = []

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

            tool_output = TOOLS[action]()

            observation = {
                "tool": action,
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

        return final_answer

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


