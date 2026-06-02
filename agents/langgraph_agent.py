from typing import TypedDict, List, Dict, Any

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from prompts import DIAGNOSIS_OUTPUT_FORMAT

from telemetry_store import (
    get_all_latest_devices,
    get_latest_status,
    get_device_telemetry_history
)


class LangGraphState(TypedDict):
    user_input: str
    selected_tool: str
    tool_output: Any
    final_answer: str
    steps: List[Dict[str, Any]]


class LangGraphAgent:
    def __init__(self):
        self.model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2
        )

        graph = StateGraph(LangGraphState)

        graph.add_node("select_tool", self.select_tool_node)
        graph.add_node("run_tool", self.run_tool_node)
        graph.add_node("generate_answer", self.generate_answer_node)

        graph.add_edge(START, "select_tool")
        graph.add_edge("select_tool", "run_tool")
        graph.add_edge("run_tool", "generate_answer")
        graph.add_edge("generate_answer", END)

        self.graph = graph.compile()

    def select_tool_node(self, state):
        user_input = state["user_input"].lower()

        if "history" in user_input or "trend" in user_input:
            selected_tool = "get_device_history"
        elif "diagnose" in user_input and self.extract_device_id(user_input):
            selected_tool = "get_device_status"
        else:
            selected_tool = "get_fleet_status"

        steps = state.get("steps", [])
        steps.append({
            "iteration": 1,
            "thought": "LangGraph selected an operational telemetry tool based on the user request.",
            "action": selected_tool,
            "output": {
                "selected_tool": selected_tool
            }
        })

        return {
            "selected_tool": selected_tool,
            "steps": steps
        }

    def run_tool_node(self, state):
        selected_tool = state["selected_tool"]
        user_input = state["user_input"]
        device_id = self.extract_device_id(user_input)

        if selected_tool == "get_device_status" and device_id:
            tool_output = get_latest_status(device_id)

        elif selected_tool == "get_device_history" and device_id:
            tool_output = get_device_telemetry_history(device_id)

        else:
            tool_output = get_all_latest_devices()

        steps = state.get("steps", [])
        steps.append({
            "iteration": 2,
            "thought": "LangGraph executed the selected tool and collected telemetry evidence.",
            "action": selected_tool,
            "output": tool_output
        })

        return {
            "tool_output": tool_output,
            "steps": steps
        }

    def generate_answer_node(self, state):
        prompt = f"""
    You are an IoT operations assistant.

    {DIAGNOSIS_OUTPUT_FORMAT}

    User request:
    {state["user_input"]}

    Telemetry/tool result:
    {state["tool_output"]}
    """

        response = self.model.invoke(prompt)

        steps = state.get("steps", [])
        steps.append({
            "iteration": 3,
            "thought": "LangGraph generated the final operational diagnosis using the shared diagnosis output format.",
            "action": "generate_answer",
            "output": {
                "framework": "LangGraph",
                "output_format": "Operational Diagnosis: Summary, Evidence, Likely Cause, Suggested Next Action",
                "graph_nodes": [
                    "select_tool",
                    "run_tool",
                    "generate_answer"
                ]
            }
        })

        return {
            "final_answer": response.content,
            "steps": steps
        }

    def run(self, user_input):
        result = self.graph.invoke({
            "user_input": user_input,
            "selected_tool": "",
            "tool_output": None,
            "final_answer": "",
            "steps": []
        })

        return {
            "final_answer": result["final_answer"],
            "steps": result["steps"]
        }

    def run_stream(self, user_input):
        result = self.run(user_input)

        for step in result["steps"]:
            yield {
                "type": "thought",
                "iteration": step["iteration"],
                "thought": step["thought"],
                "action": step["action"]
            }

            yield {
                "type": "observation",
                "iteration": step["iteration"],
                "observation": {
                    "output": step["output"]
                }
            }

        yield {
            "type": "final",
            "final_answer": result["final_answer"]
        }

    def extract_device_id(self, text):
        for token in text.replace(",", " ").split():
            if token.startswith("gateway-") or token.startswith("sensor-"):
                return token.strip()

        return None