"""Tests for world-kit-schema: per-campaign ruleset.json driving the generic core."""

from lib.world_kit import WorldKit


def test_loads_dcc_ruleset(dcc_world):
    k = WorldKit(dcc_world)
    assert k.name() == "Dungeon Crawler Carl"
    assert k.resolution_model() == "d20-vs-dc"
    assert k.progression_model() == "resource-axis"
    assert "monster-manual" in k.active_agents()


def test_resolves_through_generic_core(dcc_world):
    r = WorldKit(dcc_world).resolve(modifier=100, dc=5)
    assert r["success"] is True and "die" in r


def test_progression_is_resource_axis_not_5e_xp(dcc_world):
    k = WorldKit(dcc_world)
    s = k.advance_progression({}, amount=2_000_000)  # viewers
    assert k.level(s) >= 1
    # advancing "xp" does nothing here (this kit isn't xp-leveled)
    s2 = k.advance_progression({}, xp=999999)
    assert k.level(s2) == 0


def test_campaign_rules_preserved_and_consumed(dcc_world):
    rules = WorldKit(dcc_world).campaign_rules()
    assert "loot_box_system" in rules and "audience_system" in rules


def test_rules_doc_loads_on_demand(dcc_world):
    p = WorldKit(dcc_world).rules_doc_path()
    assert p is not None and p.name == "rules.md"
    assert "resource-axis" in p.read_text(encoding="utf-8")


def test_traits_default_to_empty_when_the_kit_declares_none(dcc_world):
    # WorldKit is already imported at module level in this file.
    assert WorldKit(dcc_world).traits() == []
