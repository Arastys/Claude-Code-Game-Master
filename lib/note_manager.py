#!/usr/bin/env python3
"""Note/fact management module for GM tools."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from campaign_manager import CampaignManager
from json_ops import JsonOperations


class NoteManager:
    """Manage campaign facts and notes."""

    def __init__(self, world_state_dir: str = "world-state"):
        self.campaign_mgr = CampaignManager(world_state_dir)
        self.campaign_dir = self.campaign_mgr.get_active_campaign_dir()

        if self.campaign_dir is None:
            raise RuntimeError("No active campaign. Run /new-game or /import first.")

        self.json_ops = JsonOperations(str(self.campaign_dir))

        # Ensure facts file exists
        facts_path = self.campaign_dir / "facts.json"
        if not facts_path.exists():
            self.json_ops.save_json("facts.json", {})

    def add_fact(self, category: str, fact: str) -> bool:
        """Add a fact to the specified category."""
        facts = self.json_ops.load_json("facts.json")

        if category not in facts:
            facts[category] = []

        timestamp = datetime.now(timezone.utc).isoformat()
        facts[category].append({
            'fact': fact,
            'timestamp': timestamp
        })

        if not self.json_ops.save_json("facts.json", facts):
            print(f"[ERROR] Failed to save fact")
            return False

        print(f"[SUCCESS] Recorded fact in {category}: {fact}")
        return True

    def get_facts(self, category: str = None) -> dict:
        """Get facts, optionally filtered by category."""
        facts = self.json_ops.load_json("facts.json")
        if category:
            return {category: facts.get(category, [])}
        return facts

    def list_categories(self) -> list:
        """List all fact categories."""
        facts = self.get_facts()
        return list(facts.keys())


def main():
    """CLI interface for note management."""
    import contextlib
    import io as _io
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    json_mode = wants_json()
    argv = strip_json_flag(sys.argv)

    if len(argv) < 2:
        print("Usage: python lib/note_manager.py add <category> <fact>")
        print("       python lib/note_manager.py get [category]")
        print("       python lib/note_manager.py categories")
        sys.exit(1)

    action = argv[1]

    try:
        manager = NoteManager()

        if action == 'add':
            if len(argv) < 4:
                sys.exit(emit_error(
                    "usage: note_manager.py add <category> <fact>", json_mode))
            category, fact = argv[2], argv[3]
            # add_fact prints [SUCCESS] from inside the manager; in JSON mode that
            # text would precede the envelope and break json.loads.
            sink = _io.StringIO()
            with contextlib.redirect_stdout(sink if json_mode else sys.stdout):
                ok = manager.add_fact(category, fact)
            if not ok:
                sys.exit(emit_error(f"could not record fact in {category}", json_mode))
            emit({"category": category, "fact": fact}, json_mode=json_mode)

        elif action == 'get':
            category = argv[2] if len(argv) > 2 else None
            facts = manager.get_facts(category)
            if json_mode:
                emit(facts, json_mode=True)
            else:
                print(json.dumps(facts, indent=2))

        elif action == 'categories':
            categories = manager.list_categories()
            if json_mode:
                emit(categories, json_mode=True)
            else:
                for cat in categories:
                    print(f"  - {cat}")

        else:
            sys.exit(emit_error(f"unknown action: {action}", json_mode))

    except RuntimeError as e:
        sys.exit(emit_error(str(e), json_mode))


if __name__ == "__main__":
    main()
