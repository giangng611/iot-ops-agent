from openai import OpenAI
from dotenv import load_dotenv
import os

from agents.week1_agent import Week1Agent
from agents.week2_agent import Week2Agent

load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def choose_agent():
    print("Choose an agent:")
    print("1. Week 1 - Single-step tool calling")
    print("2. Week 2 - Multi-step reasoning agent")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        print("\nRunning Week 1 Agent...\n")
        return Week1Agent(client)

    if choice == "2":
        print("\nRunning Week 2 Agent...\n")
        return Week2Agent(client)

    print("\nInvalid choice. Defaulting to Week 1 Agent.\n")
    return Week1Agent(client)


def main():
    agent = choose_agent()

    print("IoT Ops AI Agent")
    print("Type 'exit' or 'quit' to quit.\n")

    while True:
        user_input = input("User: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            break

        try:
            answer = agent.run(user_input)
            print(f"\nAgent:\n{answer}\n")

        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    main()