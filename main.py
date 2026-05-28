from openai import OpenAI
from dotenv import load_dotenv
import os

from agents.ioa_v1_agent import IOAV1Agent
from agents.ioa_v2_agent import IOAV2Agent

load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def choose_agent():
    print("Choose an agent:")
    print("1. IOA V1 - Single-step tool calling")
    print("2. IOA V2 - Multi-step reasoning agent")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        print("\nRunning IOA V1 Agent...\n")
        return IOAV1Agent(client)

    if choice == "2":
        print("\nRunning IOA V2 Agent...\n")
        return IOAV2Agent(client)

    print("\nInvalid choice. Defaulting to IOA V1 Agent.\n")
    return IOAV1Agent(client)


def main():
    agent = choose_agent()

    print("IoT Ops AI Agent")
    print("Type '/home' to switch agent mode.")
    print("Type 'exit' or 'quit' to quit.\n")

    while True:
        user_input = input("User: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            break

        if user_input in ["1", "2"]:
            print("You already selected an agent mode. Type a request, or type 'exit' to quit.\n")
            continue

        if user_input.lower() == "/home":
            print("\nReturning to home menu...\n")

            agent = choose_agent()

            continue

        try:
            answer = agent.run(user_input)
            print(f"\nAgent:\n{answer}\n")

        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    main()