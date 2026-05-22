from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from tools import check_device_status, get_recent_logs, check_alarm_rules, TOOLS
from prompts import SYSTEM_PROMPT, TOOL_SELECTION_PROMPT

load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

conversation_history = []

def select_tool_with_llm(user_input):
    response = client.chat.completions.create(
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

def ask_llm(user_input, tool_name, tool_output):
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": user_input
    })

    messages.append({
        "role": "system",
        "content": (
            f"Tool used: {tool_name}\n"
            f"Tool output JSON:\n{json.dumps(tool_output, indent=2)}"
        )
    })

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages
    )

    return response.choices[0].message.content

def main():
    print("IoT Ops AI Agent - Week 1")
    print("Type 'exit' or 'quit' to quit.\n")

    while True:
        user_input = input("User: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            break

        try:
            tool_name = select_tool_with_llm(user_input)

            if tool_name is None:
                print("Agent: I do not have a suitable tool for that request yet.\n")
                continue

            tool_output = TOOLS[tool_name]()

            print(f"\n[Tool selected]: {tool_name}")
            print("[Tool output]:")
            print(json.dumps(tool_output, indent=2))

            answer = ask_llm(user_input, tool_name, tool_output)

            print(f"\nAgent:\n{answer}\n")

            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": answer})

        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()