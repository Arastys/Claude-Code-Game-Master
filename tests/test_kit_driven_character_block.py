"""The every-turn CHARACTER brief must render what the kit declares.

It was a fixed f-string carrying five D&D assumptions, so a custom kit read
`Level 0 Brythonic ? | HP: 30/30 | AC: ? | XP: 0 | Gold: 0` while the meter the
world actually runs on was invisible. `gm-player.sh show` has been kit-driven for
some time; the context brief kept a divergent hardcoded copy.
"""

import json

from lib.session_manager import SessionManager

HYBORIAN_RULESET = {
    "name": "The Hyborian Age",
    "kit": "hyborian",
    "stat_schema": {
        "attributes": ["might", "guile", "grit"],
        "vitals": ["hp", "vigor", "corruption"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}

DND5E_RULESET = {
    "name": "Forgotten Realms",
    "kit": "dnd5e",
    "stat_schema": {
        "attributes": ["str", "dex", "con", "int", "wis", "cha"],
        "vitals": ["hp"],
    },
    "progression": {"model": "xp-levels"},
    "resolution": {"model": "d20-vs-dc"},
}


def _world(tmp_path, slug, ruleset, character):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / slug
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text(slug, encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (campaign / "character.json").write_text(json.dumps(character), encoding="utf-8")
    return str(world)


def _character_line(world):
    ctx = SessionManager(world).get_full_context()
    body = ctx.split("--- CHARACTER ---", 1)[1]
    return body.strip().splitlines()[0]


def test_declared_vitals_are_rendered(tmp_path):
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 6, "race": "Cimmerian",
        "hp": {"current": 58, "max": 58},
        "vigor": {"current": 3, "max": 5}, "corruption": 2,
    })
    line = _character_line(world)
    assert "Conan" in line and "Level 6" in line
    assert "HP: 58/58" in line
    assert "Vigor: 3/5" in line          # dict-shaped vital
    assert "Corruption: 2" in line       # plain-number vital


def test_no_placeholders_for_concepts_the_kit_lacks(tmp_path):
    """The old line printed `?` for class and AC and invented `Gold: 0`."""
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 6, "race": "Cimmerian",
        "hp": {"current": 58, "max": 58},
    })
    line = _character_line(world)
    assert "?" not in line
    assert "Gold" not in line
    assert "AC" not in line
    assert "XP" not in line


def test_race_is_rendered_when_the_sheet_has_one(tmp_path):
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 6, "race": "Cimmerian",
        "hp": {"current": 58, "max": 58},
    })
    assert "Cimmerian" in _character_line(world)


def test_dnd5e_still_shows_its_own_sheet_fields(tmp_path):
    """Kit-driven must not mean 5e loses anything it authored."""
    world = _world(tmp_path, "forgotten-realms", DND5E_RULESET, {
        "name": "Thorin", "level": 3, "race": "Dwarf", "class": "Fighter",
        "hp": {"current": 28, "max": 28}, "ac": 16,
        "xp": {"current": 900, "next_level": 2700}, "gold": 150,
    })
    line = _character_line(world)
    assert "Thorin" in line and "Dwarf" in line and "Fighter" in line
    assert "HP: 28/28" in line
    assert "AC: 16" in line
    assert "XP: 900" in line
    assert "Gold: 150" in line


def test_a_vital_absent_from_the_sheet_is_skipped_not_zeroed(tmp_path):
    """A declared vital the character has never tracked must not read as 0."""
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 1, "hp": {"current": 10, "max": 10},
    })
    line = _character_line(world)
    assert "Vigor" not in line
    assert "Corruption" not in line


def test_conditions_line_is_unchanged(tmp_path):
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 1, "hp": {"current": 10, "max": 10},
        "conditions": ["Poisoned"],
    })
    ctx = SessionManager(world).get_full_context()
    assert "Conditions: Poisoned" in ctx


TRAIT_RULESET = {
    "name": "The Slow Heart",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["strength", "dexterity", "stamina"],
        "vitals": ["hp", "blood"],
        "traits": ["generation", "gift_tier"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_declared_traits_are_rendered(tmp_path):
    world = _world(tmp_path, "slow-heart", TRAIT_RULESET, {
        "name": "Rhiannon", "level": 0, "race": "Brythonic",
        "hp": {"current": 30, "max": 30}, "blood": 7,
        "generation": 5, "gift_tier": 1,
    })
    line = _character_line(world)
    assert "Blood: 7" in line
    assert "Generation: 5" in line
    assert "Gift Tier: 1" in line
    assert "?" not in line
    assert "Gold" not in line


def test_a_trait_absent_from_the_sheet_is_skipped(tmp_path):
    world = _world(tmp_path, "slow-heart", TRAIT_RULESET, {
        "name": "Rhiannon", "level": 0,
        "hp": {"current": 30, "max": 30}, "generation": 5,
    })
    line = _character_line(world)
    assert "Generation: 5" in line
    assert "Gift Tier" not in line


def test_a_kit_declaring_no_traits_is_unaffected(tmp_path):
    """The three kits above declare none; adding the bucket must change nothing."""
    world = _world(tmp_path, "hyborian", HYBORIAN_RULESET, {
        "name": "Conan", "level": 6, "hp": {"current": 58, "max": 58},
        "generation": 5,  # on the sheet but NOT declared -> not rendered
    })
    assert "Generation" not in _character_line(world)


SCALAR_HP_RULESET = {
    "name": "The Flat Track",
    "kit": "custom",
    "stat_schema": {"attributes": [], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_a_kit_modeling_hp_as_a_bare_number_does_not_crash(tmp_path):
    """Extra fix B: hp used to assume {current, max}; a scalar hp track crashed
    with AttributeError even though _read_vital already supports scalars for
    every other vital."""
    world = _world(tmp_path, "flat-track", SCALAR_HP_RULESET, {
        "name": "Nomad", "level": 2, "hp": 30,
    })
    line = _character_line(world)
    assert "HP: 30" in line
    assert "HP: 30/None" not in line
