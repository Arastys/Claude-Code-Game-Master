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


NO_HP_RULESET = {
    "name": "The Vein Court",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["poise", "cunning"],
        "vitals": ["composure", "blood"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_a_kit_declaring_no_hp_does_not_invent_it(tmp_path):
    """FIX 2: WorldKit.vitals() only forces ['hp'] for an under-declared kit — a
    kit that legitimately declares vitals without hp (composure/blood) must not
    get an invented `HP: 0`."""
    world = _world(tmp_path, "vein-court", NO_HP_RULESET, {
        "name": "Rhiannon", "level": 0,
        "composure": {"current": 3, "max": 4}, "blood": 7,
    })
    line = _character_line(world)
    assert "HP" not in line
    assert "Composure: 3/4" in line
    assert "Blood: 7" in line


def test_hp_still_shows_when_the_sheet_carries_it_even_if_undeclared(tmp_path):
    """The gate is 'declared OR on the sheet' — an hp the kit doesn't declare but
    the sheet already tracks must still be shown, never hidden either."""
    world = _world(tmp_path, "vein-court", NO_HP_RULESET, {
        "name": "Rhiannon", "level": 0, "hp": {"current": 5, "max": 5},
        "composure": {"current": 3, "max": 4},
    })
    line = _character_line(world)
    assert "HP: 5/5" in line


GOLD_VITAL_RULESET = {
    "name": "The Barter World",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["grit"],
        "vitals": ["hp", "gold"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_gold_declared_as_a_vital_renders_once(tmp_path):
    """FIX 3: a world where coin is a resource meter declares `gold` as a vital;
    the 5e-furniture block used to append a second, unconditional `Gold: 12`."""
    world = _world(tmp_path, "barter-world", GOLD_VITAL_RULESET, {
        "name": "A", "level": 1,
        "hp": {"current": 5, "max": 5}, "gold": 12,
    })
    line = _character_line(world)
    assert line.count("Gold") == 1
    assert "Gold: 12" in line


DUAL_BUCKET_RULESET = {
    "name": "The Blood Ledger",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["grit"],
        "vitals": ["hp", "blood"],
        "traits": ["blood"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_a_name_declared_in_both_vitals_and_traits_renders_once(tmp_path):
    """FIX 3: a name declared in both buckets (e.g. `blood`) must emit once, not
    once per bucket."""
    world = _world(tmp_path, "blood-ledger", DUAL_BUCKET_RULESET, {
        "name": "B", "level": 1,
        "hp": {"current": 5, "max": 5}, "blood": 7,
    })
    line = _character_line(world)
    assert line.count("Blood") == 1
    assert "Blood: 7" in line


AC_TRAIT_RULESET = {
    "name": "The Armored Court",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["grit"],
        "vitals": ["hp"],
        "traits": ["ac"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_a_trait_named_ac_does_not_collide_with_5e_furniture(tmp_path):
    """FIX 3: a trait named `ac` used to render alongside the unconditional 5e
    `AC:` furniture line — two label conventions for the same value."""
    world = _world(tmp_path, "armored-court", AC_TRAIT_RULESET, {
        "name": "C", "level": 1,
        "hp": {"current": 5, "max": 5}, "ac": 14,
    })
    line = _character_line(world)
    assert line.count("14") == 1


RACE_TRAIT_RULESET = {
    "name": "The Twice-Named",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["grit"],
        "vitals": ["hp"],
        "traits": ["race"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
}


def test_race_declared_as_a_trait_does_not_double_with_identity(tmp_path):
    """FIX 3: `race` is already folded into the identity segment; declaring it
    again as a trait must not print the value twice."""
    world = _world(tmp_path, "twice-named", RACE_TRAIT_RULESET, {
        "name": "D", "level": 1, "race": "Cimmerian",
        "hp": {"current": 5, "max": 5},
    })
    line = _character_line(world)
    assert line.count("Cimmerian") == 1
