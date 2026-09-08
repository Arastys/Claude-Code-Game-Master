#!/usr/bin/env python3
"""Time management module for GM tools."""

import re
import sys
from pathlib import Path
from typing import Optional

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from campaign_manager import CampaignManager
from json_ops import JsonOperations

# Small elapsed-magnitude map for threat-clock ticks. Not a calendar parser:
# minutes / hours / same-day time-of-day → 1
# N day/days → N
# N week/weeks → 7*N
# N month/months → 30*N
# N year/years → 365*N
# anything else (including empty) → 1
#
# Large values are safe and intended: tick_time_clocks clamps with
# min(max, current + ticks), skips already-full clocks, and fires each consequence
# once on the fill transition. A decade-long skip filling every pending clock is the
# truthful outcome of a decade passing, not an overflow to guard against.
_DURATION_YEAR = re.compile(r"(\d+)\s*years?", re.IGNORECASE)
_DURATION_MONTH = re.compile(r"(\d+)\s*months?", re.IGNORECASE)
_DURATION_WEEK = re.compile(r"(\d+)\s*weeks?", re.IGNORECASE)
_DURATION_DAY = re.compile(r"(\d+)\s*days?", re.IGNORECASE)


def ticks_from_duration(text: str) -> int:
    """Map a free-text duration to threat-clock ticks (minimum 1)."""
    if not text or not str(text).strip():
        return 1
    s = str(text).strip()
    for pattern, factor in ((_DURATION_YEAR, 365), (_DURATION_MONTH, 30),
                            (_DURATION_WEEK, 7), (_DURATION_DAY, 1)):
        m = pattern.search(s)
        if m:
            return max(1, factor * int(m.group(1)))
    return 1


def ticks_for_elapsed(ticks: Optional[int] = None, duration: Optional[str] = None) -> int:
    """Resolve clock ticks for a time advance.

    Explicit ticks win over duration. Default (neither given) is 1, so a
    Dawn→Noon hop stays +1.
    """
    if ticks is not None:
        return max(1, int(ticks))
    if duration:
        return ticks_from_duration(duration)
    return 1


class TimeManager:
    """Manage campaign time state."""

    def __init__(self, world_state_dir: str = "world-state"):
        self.campaign_mgr = CampaignManager(world_state_dir)
        self.campaign_dir = self.campaign_mgr.get_active_campaign_dir()

        if self.campaign_dir is None:
            raise RuntimeError("No active campaign. Run /new-game or /import first.")

        self.json_ops = JsonOperations(str(self.campaign_dir))

    def update_time(self, time_of_day: str, date: str) -> bool:
        """Update the campaign time and date."""
        data = self.json_ops.load_json("campaign-overview.json")

        data['time_of_day'] = time_of_day
        data['current_date'] = date

        if not self.json_ops.save_json("campaign-overview.json", data):
            print(f"[ERROR] Failed to update time")
            return False

        print(f"[SUCCESS] Time updated to: {time_of_day}, {date}")
        return True

    def get_time(self) -> dict:
        """Get current campaign time."""
        data = self.json_ops.load_json("campaign-overview.json")
        return {
            'time_of_day': data.get('time_of_day', 'Unknown'),
            'current_date': data.get('current_date', 'Unknown')
        }


def _parse_ticks_flags(argv):
    """Parse [--ticks N] [--duration TEXT] from argv. No campaign required."""
    ticks = None
    duration = None
    i = 0
    while i < len(argv):
        if argv[i] == "--ticks":
            if i + 1 >= len(argv):
                print("[ERROR] --ticks requires a number", file=sys.stderr)
                sys.exit(1)
            try:
                ticks = int(argv[i + 1])
            except ValueError:
                print("[ERROR] --ticks must be an integer", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif argv[i] == "--duration":
            if i + 1 >= len(argv):
                print("[ERROR] --duration requires a value", file=sys.stderr)
                sys.exit(1)
            duration = argv[i + 1]
            i += 2
        else:
            print(f"[ERROR] Unknown argument: {argv[i]}", file=sys.stderr)
            sys.exit(1)
    return ticks, duration


def main():
    """CLI interface for time management."""
    if len(sys.argv) < 2:
        print("Usage: python lib/time_manager.py update <time_of_day> <date>")
        print("       python lib/time_manager.py get")
        print("       python lib/time_manager.py ticks [--ticks N] [--duration TEXT]")
        sys.exit(1)

    action = sys.argv[1]

    # ticks is a pure mapping — no campaign, so it can run before TimeManager().
    if action == "ticks":
        ticks, duration = _parse_ticks_flags(sys.argv[2:])
        print(ticks_for_elapsed(ticks=ticks, duration=duration))
        return

    try:
        manager = TimeManager()

        if action == 'update':
            if len(sys.argv) < 4:
                print("Usage: python lib/time_manager.py update <time_of_day> <date>")
                sys.exit(1)
            time_of_day = sys.argv[2]
            date = sys.argv[3]
            if not manager.update_time(time_of_day, date):
                sys.exit(1)

        elif action == 'get':
            time_info = manager.get_time()
            print(f"Time: {time_info['time_of_day']}")
            print(f"Date: {time_info['current_date']}")

        else:
            print(f"Unknown action: {action}")
            sys.exit(1)

    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
