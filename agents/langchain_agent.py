import json

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from prompts import COMPANY_CONTEXT_INSTRUCTION, DIAGNOSIS_OUTPUT_FORMAT

from storage.telemetry_store import (
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
        self.model = model

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

    def extract_message_token_usage(self, message):
        usage = getattr(message, "usage_metadata", None) or {}
        response_metadata = getattr(message, "response_metadata", {}) or {}
        token_usage = response_metadata.get("token_usage") or {}

        input_tokens = (
            usage.get("input_tokens")
            or token_usage.get("prompt_tokens")
            or token_usage.get("input_tokens")
            or 0
        )
        output_tokens = (
            usage.get("output_tokens")
            or token_usage.get("completion_tokens")
            or token_usage.get("output_tokens")
            or 0
        )
        total_tokens = (
            usage.get("total_tokens")
            or token_usage.get("total_tokens")
            or input_tokens + output_tokens
        )

        if not total_tokens:
            return None

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens
        }

    def sum_token_usage(self, messages):
        usage_items = [
            usage for usage in (
                self.extract_message_token_usage(message)
                for message in messages
            )
            if usage
        ]

        if not usage_items:
            return None

        return {
            "input_tokens": sum(item["input_tokens"] for item in usage_items),
            "output_tokens": sum(item["output_tokens"] for item in usage_items),
            "total_tokens": sum(item["total_tokens"] for item in usage_items),
            "source": "langchain_message_metadata"
        }

    def run(self, user_input, operational_context=None):
        if operational_context is not None:
            response = self.model.invoke([
                {
                    "role": "system",
                    "content": (
                        f"{COMPANY_CONTEXT_INSTRUCTION}\n"
                        f"{DIAGNOSIS_OUTPUT_FORMAT}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User request:\n{user_input}\n\n"
                        "Company operational context:\n"
                        f"{json.dumps(operational_context, indent=2)}"
                    ),
                },
            ])
            token_usage = self.extract_message_token_usage(response)
            return {
                "final_answer": response.content,
                "token_usage": (
                    {**token_usage, "source": "langchain_message_metadata"}
                    if token_usage
                    else None
                ),
                "steps": [{
                    "iteration": 1,
                    "thought": "Use the selected Company DB operational context.",
                    "action": "read_company_operational_context",
                    "workflow": {
                        "framework": "LangChain",
                        "node_id": "company_context",
                        "node_label": "Company context",
                    },
                    "output": {
                        "source": operational_context.get("source"),
                        "record_count": operational_context.get("record_count"),
                    },
                }],
            }

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
        token_usage = self.sum_token_usage(messages)

        return {
            "final_answer": final_message.content,
            "token_usage": token_usage,
            "steps": [
                {
                    "iteration": 1,
                    "thought": "LangChain agent selected and executed tools using its internal agent loop.",
                    "action": "LangChain create_agent",
                    "workflow": {
                        "framework": "LangChain",
                        "node_id": "agent_loop",
                        "node_label": "Agent loop"
                    },
                    "output": {
                        "framework": "LangChain",
                        "messages_count": len(messages),
                        "token_usage": token_usage
                    }
                }
            ]
        }
