#!/usr/bin/env python3
"""
Factions — the live half of the world's politics.

world-bible.json carries a `factions` graph, but the bible is a confirm-locked
reference document with no write path: it says who exists, not who currently holds
what. This owns the mutable half — standing the PC has earned, who belongs to which
faction, which ground each one claims, and how they regard each other.

`standing` is clamped to [-5, +5] so it drops straight into
game_core.reaction_roll as its `track_value`.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager

STANDING_MIN = -5
STANDING_MAX = 5


def _clamp_standing(value: Any) -> int:
    return max(STANDING_MIN, min(STANDING_MAX, int(value)))


def _has_ci(items: List[Any], value: str) -> bool:
    """Case-insensitive membership, matching entity_manager.npcs_present."""
    needle = str(value or "").strip().lower()
    return any(str(i).strip().lower() == needle for i in (items or []))


def _without_ci(items: List[Any], value: str) -> List[Any]:
    needle = str(value or "").strip().lower()
    return [i for i in (items or []) if str(i).strip().lower() != needle]


class FactionManager(EntityManager):
    """Standing, membership, territory and relations for the world's factions."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.factions_file = "factions.json"

    def _load(self) -> Dict[str, Any]:
        return self.json_ops.load_json(self.factions_file) or {}

    def _save(self, data: Dict[str, Any]) -> None:
        self.json_ops.save_json(self.factions_file, data)

    def add_faction(self, name: str, standing: int = 0,
                    note: str = None) -> Dict[str, Any]:
        """Create or reset a faction. Matches add_clock/add_track: create-or-reset, not upsert."""
        data = self._load()
        entry = {
            "standing": _clamp_standing(standing),
            "members": [],
            "territory": [],
            "relations": {},
        }
        if note:
            entry["note"] = note
        data[name] = entry
        self._save(data)
        return entry

    def set_standing(self, name: str, value: int) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["standing"] = _clamp_standing(value)
        self._save(data)
        return faction

    def adjust_standing(self, name: str, delta: int) -> Optional[Dict[str, Any]]:
        faction = self._load().get(name)
        if faction is None:
            return None
        return self.set_standing(name, int(faction.get("standing", 0)) + int(delta))

    def add_member(self, name: str, npc: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        members = faction.setdefault("members", [])
        if not _has_ci(members, npc):
            members.append(npc)
            self._save(data)
        return faction

    def remove_member(self, name: str, npc: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["members"] = _without_ci(faction.get("members"), npc)
        self._save(data)
        return faction

    def remove_faction(self, name: str) -> bool:
        data = self._load()
        if name in data:
            del data[name]
            self._save(data)
            return True
        return False

    def get_factions(self) -> Dict[str, Any]:
        return self._load()

    def claim(self, name: str, location: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        territory = faction.setdefault("territory", [])
        if not _has_ci(territory, location):
            territory.append(location)
            self._save(data)
        return faction

    def release(self, name: str, location: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["territory"] = _without_ci(faction.get("territory"), location)
        self._save(data)
        return faction

    def holders_of(self, location: str) -> List[str]:
        """Every faction claiming this place. More than one means contested."""
        if not str(location or "").strip():
            return []
        return [name for name, f in self._load().items()
                if _has_ci(f.get("territory"), location)]

    def contested(self) -> Dict[str, List[str]]:
        """Ground more than one faction claims: location (as stored) -> claimants."""
        claimants: Dict[str, List[str]] = {}
        display: Dict[str, str] = {}
        for name, faction in self._load().items():
            for place in faction.get("territory") or []:
                key = str(place).strip().lower()
                if not key:
                    continue
                display.setdefault(key, str(place))
                claimants.setdefault(key, []).append(name)
        return {display[k]: v for k, v in claimants.items() if len(v) > 1}

    def set_relation(self, name: str, other: str,
                     stance: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction.setdefault("relations", {})[other] = stance
        self._save(data)
        return faction

    @staticmethod
    def render(factions: Dict[str, Any]) -> str:
        """One line per faction for the GM-visible context."""
        lines = []
        for name, f in factions.items():
            parts = [f"standing {int(f.get('standing', 0)):+d}"]
            if f.get("territory"):
                parts.append("holds: " + ", ".join(f["territory"]))
            if f.get("members"):
                parts.append("members: " + ", ".join(f["members"]))
            for other, stance in (f.get("relations") or {}).items():
                parts.append(f"vs {other}: {stance}")
            lines.append(f"{name}: " + " | ".join(parts))
        return "\n".join(lines)


def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="Factions")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("name")
    p.add_argument("--standing", type=int, default=0); p.add_argument("--note")
    p = sub.add_parser("standing"); p.add_argument("name")
    p.add_argument("--set", dest="set_value", type=int)
    p.add_argument("--delta", type=int)
    p = sub.add_parser("member"); p.add_argument("name"); p.add_argument("npc")
    p = sub.add_parser("unmember"); p.add_argument("name"); p.add_argument("npc")
    p = sub.add_parser("claim"); p.add_argument("name"); p.add_argument("location")
    p = sub.add_parser("release"); p.add_argument("name"); p.add_argument("location")
    p = sub.add_parser("relation"); p.add_argument("name")
    p.add_argument("other"); p.add_argument("stance")
    p = sub.add_parser("holders"); p.add_argument("location")
    sub.add_parser("contested")
    p = sub.add_parser("remove"); p.add_argument("name")
    sub.add_parser("list")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = FactionManager()
    if args.action == "add":
        out = m.add_faction(args.name, standing=args.standing, note=args.note)
    elif args.action == "standing":
        if args.set_value is None and args.delta is None:
            sys.exit(emit_error("pass --set or --delta", json_mode))
        out = (m.set_standing(args.name, args.set_value) if args.set_value is not None
               else m.adjust_standing(args.name, args.delta))
    elif args.action == "member":
        out = m.add_member(args.name, args.npc)
    elif args.action == "unmember":
        out = m.remove_member(args.name, args.npc)
    elif args.action == "claim":
        out = m.claim(args.name, args.location)
    elif args.action == "release":
        out = m.release(args.name, args.location)
    elif args.action == "relation":
        out = m.set_relation(args.name, args.other, args.stance)
    elif args.action == "holders":
        out = m.holders_of(args.location)
    elif args.action == "contested":
        out = m.contested()
    elif args.action == "remove":
        out = {"removed": m.remove_faction(args.name)}
    else:
        out = m.get_factions()

    if out is None:
        sys.exit(emit_error(f"no such faction: {args.name}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2))
        if args.action == "list":
            print(FactionManager.render(out))


if __name__ == "__main__":
    main()
