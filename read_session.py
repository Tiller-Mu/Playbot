import json
import sys

try:
    with open('workspace/sessions/1cf4b80d-881b-46e0-8534-dfea74a168c8.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        status = data.get("status")
        history = data.get("action_history", [])
        print(f"Status: {status}")
        print(f"Action Count: {len(history)}")
        if len(history) > 0:
            print("First Action URL:", history[0].get("url"))
except Exception as e:
    print(f"Error: {e}")
