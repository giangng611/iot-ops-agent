import json

from tools import TOOLS
from prompts import SYSTEM_PROMPT, TOOL_SELECTION_PROMPT


class IOAV1Agent:
    def __init__(self, client):
        self.client = client
        self.conversation_history = []
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

    def extract_device(self, user_input):
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
Extract the device ID from the user request.

Available devices:
- sensor-001
- sensor-002
- gateway-003

If the user does not mention a device, return sensor-001.

Return only the device ID.
"""
                },
                {"role": "user", "content": user_input}
            ]
        )
        self.record_token_usage(response)

        return response.choices[0].message.content.strip()

    def select_tool(self, user_input):
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": TOOL_SELECTION_PROMPT},
                {"role": "user", "content": user_input}
            ]
        )
        self.record_token_usage(response)

        tool_name = response.choices[0].message.content.strip()

        if tool_name not in TOOLS:
            return None

        return tool_name

    def ask_llm(self, user_input, device_id, tool_name, tool_output):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        messages.extend(self.conversation_history)

        messages.append({
            "role": "user",
            "content": user_input
        })

        messages.append({
            "role": "system",
            "content": (
                f"Target device: {device_id}\n"
                f"Tool used: {tool_name}\n"
                f"Tool output JSON:\n{json.dumps(tool_output, indent=2)}"
            )
        })

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
        self.record_token_usage(response)

        return response.choices[0].message.content

    def run(self, user_input):
        self.reset_token_usage()
        device_id = self.extract_device(user_input)
        tool_name = self.select_tool(user_input)

        if tool_name is None:
            return {
                "final_answer": "I do not have a suitable tool for that request yet.",
                "token_usage": self.get_token_usage()
            }

        tool_output = TOOLS[tool_name](device_id)

        print(f"\n[Target Device]: {device_id}")
        print(f"[Tool selected]: {tool_name}")
        print("[Tool output]:")
        print(json.dumps(tool_output, indent=2))

        answer = self.ask_llm(
            user_input,
            device_id,
            tool_name,
            tool_output
        )

        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": answer
        })

        return {
            "final_answer": answer,
            "token_usage": self.get_token_usage()
        }
