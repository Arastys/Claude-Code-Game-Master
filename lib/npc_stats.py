#!/usr/bin/env python3
"""Stats-enrichment proxy for combat-relevant NPCs.

Extracted NPCs have null ac/hp/cr, so a GM can't run an encounter without inventing
numbers. This assigns a difficulty-TIER proxy (hp + a cr/difficulty label) to
combat-relevant NPCs and explicitly flags non-combatants as statless (distinct from
"not yet enriched"). The proxy is kit-agnostic and intentionally coarse — exact stat
blocks come from the kit's monster-manual agent at encounter time; this just makes
every combatant runnable out of the box.
"""

import json
import sys
from pathlib import Path

_BOSS_TERMS = ("king", "queen", "prince", "princess", "boss", "dragon", "war god",
               "champion", "lord", "rex", "the great", "emperor", "overlord")

# Coarse difficulty tiers (hp, cr-proxy, label).
_TIER_BOSS = {"hp": 120, "cr": 8, "difficulty": "boss"}
_TIER_STANDARD = {"hp": 45, "cr": 3, "difficulty": "standard"}
_TIER_MINION = {"hp": 18, "cr": 1, "difficulty": "minion"}

_COMBAT_ATTITUDES = {"hostile"}


def is_combatant(npc: dict) -> bool:
    if not isinstance(npc, dict):
        return False
    if str(npc.get("attitude", "")).lower() in _COMBAT_ATTITUDES:
        return True
    stats = npc.get("stats") or {}
    if stats.get("cr") not in (None, "", 0):
        return True
    hay = (str(npc.get("name", "")) + " " + str(npc.get("description", ""))).lower()
    if any(t in hay for t in _BOSS_TERMS):
        return True
    if "monster" in str(npc.get("source", "")).lower():
        return True
    return False


def _tier(npc: dict) -> dict:
    hay = (str(npc.get("name", "")) + " " + str(npc.get("description", ""))).lower()
    if any(t in hay for t in _BOSS_TERMS):
        return _TIER_BOSS
    # named individuals default to standard; very short/anonymous -> minion
    return _TIER_STANDARD


def enrich_npc(npc: dict) -> str:
    """Assign proxy stats or a statless flag. Returns 'combat' | 'statless' | 'skip'."""
    if not isinstance(npc, dict):
        return "skip"
    stats = npc.setdefault("stats", {})
    if is_combatant(npc):
        tier = _tier(npc)
        # don't clobber a real hp/cr if one was already present
        if not stats.get("hp"):
            stats["hp"] = tier["hp"]
        if not stats.get("cr"):
            stats["cr"] = tier["cr"]
        stats["difficulty"] = tier["difficulty"]
        stats["statless"] = False
        return "combat"
    stats["statless"] = True
    return "statless"


def enrich(npcs: dict) -> dict:
    report = {"combat": [], "statless": 0}
    for name, npc in (npcs or {}).items():
        result = enrich_npc(npc)
        if result == "combat":
            report["combat"].append(name)
        elif result == "statless":
            report["statless"] += 1
    return report


def run_enrich(campaign_dir) -> dict:
    path = Path(campaign_dir) / "npcs.json"
    npcs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = enrich(npcs)
    if npcs:
        path.write_text(json.dumps(npcs, indent=2))
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NPC stats-enrichment proxy")
    parser.add_argument("campaign_dir")
    args = parser.parse_args()
    r = run_enrich(args.campaign_dir)
    print(f"  combat NPCs statted: {len(r['combat'])}  {r['combat'][:8]}")
    print(f"  non-combatants flagged statless: {r['statless']}")


if __name__ == "__main__":
    main()
