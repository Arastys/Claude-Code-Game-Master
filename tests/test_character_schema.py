"""Tests for open-character-schema: migration + kit-aware validation + kit-driven XP."""

import json
from pathlib import Path

from lib.character_schema import is_open_schema, to_flat, to_open_schema
from lib.player_manager import PlayerManager
from lib.schemas import validate_character
from lib.world_kit import WorldKit


def _char(dcc_world):
    p = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl" / "character.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_migration_to_open_schema(dcc_world):
    new = to_open_schema(_char(dcc_world))
    assert is_open_schema(new)
    assert new["identity"]["name"] == "Tandy"
    assert set(new) >= {"identity", "vitals", "attributes", "progression", "inventory", "conditions"}
    assert isinstance(new["attributes"], dict) and new["attributes"]
    assert "hp" in new["vitals"]


def test_migration_is_idempotent(dcc_world):
    once = to_open_schema(_char(dcc_world))
    assert to_open_schema(once) == once


def test_dcc_character_validates_against_its_kit(dcc_world):
    new = to_open_schema(_char(dcc_world))
    ok, errs = validate_character(new, WorldKit(dcc_world))
    assert ok, errs


def test_non_5e_kit_with_custom_attributes_validates():
    paul = {
        "identity": {"name": "Paul Atreides"},
        "vitals": {"hp": {"current": 10, "max": 10}},
        "attributes": {"prescience": 5, "spice_tolerance": 3},
        "progression": {"level": 1},
        "inventory": {"gold": 0, "items": []},
        "conditions": [],
    }

    class DuneKit:
        def stat_schema(self):
            return {"attributes": ["prescience", "spice_tolerance"]}

    ok, errs = validate_character(paul, DuneKit())
    assert ok, errs


def test_attributes_outside_kit_schema_are_flagged():
    char = {"identity": {}, "vitals": {}, "attributes": {"strength": 1},
            "progression": {}, "inventory": {}, "conditions": []}

    class DuneKit:
        def stat_schema(self):
            return {"attributes": ["prescience"]}

    ok, errs = validate_character(char, DuneKit())
    assert not ok and any("not in active kit" in e for e in errs)


def test_xp_thresholds_delegate_to_kit(dcc_world, tmp_path):
    # Write an xp-levels kit into a copy and confirm thresholds come from it.
    ruleset = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl" / "ruleset.json"
    ruleset.write_text(json.dumps({
        "name": "Custom", "stat_schema": {"attributes": []},
        "progression": {"model": "xp-levels", "thresholds": [50, 120, 250]},
        "resolution": {"model": "d20-vs-dc"}, "active_agents": [],
    }), encoding="utf-8")
    pm = PlayerManager(dcc_world)
    assert pm._xp_thresholds() == [0, 50, 120, 250]  # kit-driven, not the 5e table


def test_xp_thresholds_default_when_kit_not_xp_levels(dcc_world):
    # DCC ships resource-axis -> falls back to the default table (unchanged behavior).
    pm = PlayerManager(dcc_world)
    assert pm._xp_thresholds() == PlayerManager.DEFAULT_XP_THRESHOLDS


def test_flat_sheet_validates_directly(dcc_world):
    # Regression: the old open-shape validator reported a loaded (flat) sheet as
    # entirely missing. The consolidated validator accepts both shapes.
    ok, errs = validate_character(_char(dcc_world), WorldKit(dcc_world))
    assert ok, errs


def test_nameless_traveler_validates_without_race_or_class():
    ok, errs = validate_character({"name": "A nameless traveler", "level": 1})
    assert ok, errs


def test_to_flat_does_not_invent_gold_when_the_open_shape_has_none():
    """The third writer of a phantom `gold`.

    save_character.py and identity_onboarding both learned to withhold gold on a
    non-dnd5e kit, and this conversion put it straight back on the way to flat —
    so an onboarded PC on a coinless world still persisted `gold: 0`. Absence is
    safe: every reader uses char.get('gold', 0).
    """
    onboarded = {
        "identity": {"name": "Rhiannon"},
        "vitals": {"hp": {"current": 30, "max": 30}},
        "attributes": {"strength": 4},
        "progression": {"level": 0},
        "inventory": {"items": []},
    }
    assert "gold" not in to_flat(onboarded)


def test_to_flat_carries_an_authored_gold_across():
    """Withholding must not become dropping — a 5e sheet keeps what it authored."""
    authored = {
        "identity": {"name": "Thorin"},
        "vitals": {"hp": {"current": 10, "max": 10}},
        "attributes": {"str": 15},
        "progression": {"level": 1},
        "inventory": {"gold": 25, "items": ["Longsword"]},
    }
    flat = to_flat(authored)
    assert flat["gold"] == 25
    assert flat["equipment"] == ["Longsword"]


def test_to_flat_carries_an_authored_zero_gold_across():
    """An explicit 0 is a value, not an absence — membership, not truthiness."""
    authored = {
        "identity": {"name": "Pauper"},
        "vitals": {"hp": {"current": 10, "max": 10}},
        "attributes": {"str": 10},
        "progression": {"level": 1},
        "inventory": {"gold": 0, "items": []},
    }
    assert to_flat(authored)["gold"] == 0
