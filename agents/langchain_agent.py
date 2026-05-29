from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from prompts import DIAGNOSIS_OUTPUT_FORMAT

from database import (
    get_all_latest_devices,
    get_latest_status,
    get_device_telemetry_history
)


@tool
def get_fleet_status() -> str:
    """Return the latest telemetry status for all IoT devices."""
    devices = get_all_latest_devices()
    return str(devices)


@tool
def get_device_status(device_id: str) -> str:
    """Return the latest telemetry status for one IoT device."""
    device = get_latest_status(device_id)

    if not device:
        return f"No telemetry found for device {device_id}."

    return str(device)


@tool
def get_device_history(device_id: str) -> str:
    """Return recent telemetry history for one IoT device."""
    history = get_device_telemetry_history(device_id)
    return str(history)


class LangChainAgent:
    def __init__(self):
        model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2
        )

        self.agent = create_agent(
            model=model,
            tools=[
                get_fleet_status,
                get_device_status,
                get_device_history
            ],
            system_prompt=f"""
You are an IoT operations assistant.

{DIAGNOSIS_OUTPUT_FORMAT}

Use the available tools to inspect fleet telemetry, device status,
and device telemetry history before producing the final answer.
"""
        )

    def run(self, user_input):
        result = self.agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        })

        messages = result.get("messages", [])

        if not messages:
            return {
                "final_answer": "No response generated.",
                "steps": []
            }

        final_message = messages[-1]

        return {
            "final_answer": final_message.content,
            "steps": [
                {
                    "iteration": 1,
                    "thought": "LangChain agent selected and executed tools using its internal agent loop.",
                    "action": "LangChain create_agent",
                    "output": {
                        "framework": "LangChain",
                        "messages_count": len(messages)
                    }
                }
            ]
        }