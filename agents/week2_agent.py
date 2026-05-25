import json

from tools import TOOLS
from prompts import WEEK2_AGENT_PROMPT


class Week2Agent:
    def __init__(self, client):
        self.client = client
        self.max_iterations = 3
        self.conversation_history = []