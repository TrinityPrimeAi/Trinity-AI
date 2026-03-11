import json
import os
from datetime import datetime

class FactsManager:
    def __init__(self, base_dir="memory"):
        self.base_dir = base_dir
        self.facts_path = os.path.join(base_dir, "facts.json")

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        if not os.path.exists(self.facts_path):
            with open(self.facts_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)

    def add_fact(self, text: str):
        fact = {
            "fact": text.strip(),
            "timestamp": datetime.now().isoformat()
        }

        data = self.load_facts()
        data.append(fact)

        with open(self.facts_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_facts(self):
        try:
            with open(self.facts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def formatted_facts(self):
        facts = self.load_facts()
        if not facts:
            return ""

        return "\n".join(f"- {f['fact']}" for f in facts)
