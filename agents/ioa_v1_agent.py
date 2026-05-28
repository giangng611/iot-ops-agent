import json

from tools import TOOLS
from prompts import SYSTEM_PROMPT, TOOL_SELECTION_PROMPT


class IOAV1Agent:
    def __init__(self, client):
        self.client = client
        self.conversation_history = []

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

        return response.choices[0].message.content.strip()

    def select_tool(self, user_input):
        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": TOOL_SELECTION_PROMPT},
                {"role": "user", "content": user_input}
            ]
        )

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

        return response.choices[0].message.content

    def run(self, user_input):
        device_id = self.extract_device(user_input)
        tool_name = self.select_tool(user_input)

        if tool_name is None:
            return "I do not have a suitable tool for that request yet."

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

        return answer