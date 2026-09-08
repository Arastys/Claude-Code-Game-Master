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
        if not (location or "").strip():
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
