from openai import OpenAI
from dotenv import load_dotenv
import os
from tools import check_device_status, get_recent_logs, check_alarm_rules
from prompts import SYSTEM_PROMPT

load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def select_tool(user_input):
    text = user_input.lower()

    if "status" in text or "device" in text:
        return "check_device_status", check_device_status()

    if "log" in text:
        return "get_recent_logs", get_recent_logs()

    if "alarm" in text or "rule" in text:
        return "check_alarm_rules", check_alarm_rules()

    return None, None

def ask_llm(user_input, tool_name, tool_output):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
            {
                "role": "system",
                "content": f"Tool used: {tool_name}\nTool output: {tool_output}"
            }
        ]
    )

    return response.choices[0].message.content


def main():
    print("IoT Ops AI Agent - Week 1")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("User: ")

        if user_input.lower() == "exit":
            break

        tool_name, tool_output = select_tool(user_input)

        if tool_name is None:
            print("Agent: I do not have a tool for that request yet.\n")
            continue

        answer = ask_llm(user_input, tool_name, tool_output)
        print(f"\nAgent:\n{answer}\n")


if __name__ == "__main__":
    main()
