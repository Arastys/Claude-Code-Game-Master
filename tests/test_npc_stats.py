"""Tests for npc-stats-enrichment: combat-NPC proxy stats + statless flag."""

import json
from lib.npc_stats import is_combatant, enrich_npc, run_enrich


def test_hostile_npc_is_combatant_and_gets_stats():
    npc = {"name": "Hekla", "attitude": "hostile", "stats": {"ac": None, "hp": None, "cr": None}}
    assert is_combatant(npc)
    assert enrich_npc(npc) == "combat"
    assert npc["stats"]["hp"]
    assert npc["stats"]["cr"]
    assert npc["stats"]["statless"] is False


def test_boss_term_gets_boss_tier():
    npc = {"name": "King Rust", "attitude": "neutral", "stats": {}}
    enrich_npc(npc)
    assert npc["stats"]["difficulty"] == "boss"
    assert npc["stats"]["hp"] == 120


def test_friendly_noncombatant_flagged_statless():
    npc = {"name": "Limp Richard", "attitude": "friendly", "stats": {}}
    assert not is_combatant(npc)
    assert enrich_npc(npc) == "statless"
    assert npc["stats"]["statless"] is True
    assert not npc["stats"].get("hp")     # no proxy hp for non-combatants


def test_existing_real_stats_not_clobbered():
    npc = {"name": "Boss", "attitude": "hostile", "stats": {"hp": 999, "cr": 12}}
    enrich_npc(npc)
    assert npc["stats"]["hp"] == 999      # real value preserved
    assert npc["stats"]["cr"] == 12


def test_statless_flag_distinguishes_from_unenriched():
    # An unprocessed NPC has no 'statless' key; processed non-combatant has statless=True.
    npc = {"name": "X", "attitude": "neutral", "stats": {}}
    assert "statless" not in npc["stats"]
    enrich_npc(npc)
    assert npc["stats"]["statless"] is True


def test_run_enrich_writes(tmp_path):
    (tmp_path / "npcs.json").write_text(json.dumps({
        "Hekla": {"name": "Hekla", "attitude": "hostile", "stats": {}},
        "Shopkeep": {"name": "Shopkeep", "attitude": "friendly", "stats": {}},
    }))
    r = run_enrich(str(tmp_path))
    saved = json.loads((tmp_path / "npcs.json").read_text(encoding="utf-8"))
    assert saved["Hekla"]["stats"]["hp"]
    assert saved["Shopkeep"]["stats"]["statless"] is True
    assert "Hekla" in r["combat"]
