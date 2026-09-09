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

SCALAR_KIT = {
    "name": "custom",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
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


def test_revive_survives_a_sheet_whose_hp_is_a_plain_number(tmp_path):
    """A kit may model hp as a bare int. `revive` read char['hp'].get('max') and
    then assigned char['hp']['current'], so on such a kit reviving raised
    AttributeError and the character could never come back."""
    from pathlib import Path
    from lib.player_manager import PlayerManager
    world = _world(tmp_path, "scalar-hp", SCALAR_KIT, {
        "name": "Nomad", "level": 1, "hp": 0, "status": "dead",
        "died_at": "somewhen", "stats": {"might": 3},
    })
    assert PlayerManager(world).revive("Nomad", reason="dragged back")["success"] is True
    stored = json.loads(
        (Path(world) / "campaigns" / "scalar-hp" / "character.json").read_text(
            encoding="utf-8"))
    assert stored["status"] == "alive"
    assert stored["hp"] == 1          # still a plain number, not a dict
    assert "died_at" not in stored


def test_revive_still_clamps_against_a_dict_shaped_max(tmp_path):
    from pathlib import Path
    from lib.player_manager import PlayerManager
    world = _world(tmp_path, "dict-hp", SCALAR_KIT, {
        "name": "Nomad", "level": 1, "hp": {"current": 0, "max": 4},
        "status": "dead", "stats": {"might": 3},
    })
    PlayerManager(world).revive("Nomad", hp=99)
    stored = json.loads(
        (Path(world) / "campaigns" / "dict-hp" / "character.json").read_text(
            encoding="utf-8"))
    assert stored["hp"] == {"current": 4, "max": 4}


def _world_with_npc(tmp_path, slug, ruleset, npc_sheet):
    """`_world` writes a PC but no npcs.json; from_canon needs one."""
    from pathlib import Path
    world = _world(tmp_path, slug, ruleset,
                   {"name": "Placeholder", "level": 1, "hp": {"current": 1, "max": 1}})
    (Path(world) / "campaigns" / slug / "npcs.json").write_text(json.dumps({
        "Mair": {"description": "a weaver", "attitude": "neutral",
                 "character_sheet": npc_sheet},
    }), encoding="utf-8")
    return world


def test_from_canon_does_not_invent_an_armour_class(tmp_path):
    """Lifting a canon NPC to PC gave every world an `ac`. Same defect family as
    save_character.py's DND_SHEET_DEFAULTS, which is already kit-gated."""
    from lib.identity_onboarding import IdentityOnboarding
    world = _world_with_npc(tmp_path, "no-armour", SCALAR_KIT,
                            {"level": 2, "hp": {"current": 6, "max": 6}})
    assert "ac" not in IdentityOnboarding(world).from_canon("Mair")["vitals"]


def test_from_canon_keeps_an_authored_armour_class_on_any_kit(tmp_path):
    from lib.identity_onboarding import IdentityOnboarding
    world = _world_with_npc(tmp_path, "authored-ac", SCALAR_KIT,
                            {"level": 2, "ac": 13, "hp": {"current": 6, "max": 6}})
    assert IdentityOnboarding(world).from_canon("Mair")["vitals"]["ac"] == 13


def test_from_canon_still_defaults_armour_class_on_dnd5e(tmp_path):
    from lib.identity_onboarding import IdentityOnboarding
    world = _world_with_npc(tmp_path, "realms", DND5E_RULESET,
                            {"level": 2, "hp": {"current": 9, "max": 9}})
    assert IdentityOnboarding(world).from_canon("Mair")["vitals"]["ac"] == 10


PARTY_KIT = {
    "name": "custom",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp", "blood"]},
    "progression": {"model": "milestone"},
}


def _party_world(tmp_path, slug, ruleset, pc, party_sheet):
    """`_world` writes the PC; party members need npcs.json alongside it."""
    from pathlib import Path
    world = _world(tmp_path, slug, ruleset, pc)
    (Path(world) / "campaigns" / slug / "npcs.json").write_text(json.dumps({
        "Mair": {"description": "a weaver", "attitude": "neutral",
                 "is_party_member": True, "character_sheet": party_sheet},
    }), encoding="utf-8")
    return world


def test_show_player_omits_race_class_and_gold_a_custom_kit_never_declared(tmp_path):
    """The base line hardcoded '?' for race and class and a Gold field for every
    world — the same defect the CHARACTER brief was fixed for, on the surface the
    GM reads when they run `gm-player.sh show`."""
    from lib.player_manager import PlayerManager
    world = _world(tmp_path, "brythonic", PARTY_KIT, {
        "name": "Rhiannon", "level": 0, "hp": {"current": 30, "max": 30},
        "blood": 7, "stats": {"might": 3},
    })
    out = PlayerManager(world).show_player("Rhiannon")
    assert "Rhiannon" in out
    assert "?" not in out
    assert "Gold" not in out
    assert "Blood: 7" in out


def test_show_player_keeps_race_class_and_gold_when_the_sheet_has_them(tmp_path):
    from lib.player_manager import PlayerManager
    world = _world(tmp_path, "with-furniture", PARTY_KIT, {
        "name": "Bram", "level": 3, "race": "Dwarf", "class": "Cleric",
        "gold": 12, "hp": {"current": 20, "max": 20}, "stats": {"might": 3},
    })
    out = PlayerManager(world).show_player("Bram")
    assert "Dwarf" in out and "Cleric" in out
    assert "Gold: 12" in out


def test_show_all_players_uses_the_same_identity_line(tmp_path):
    from lib.player_manager import PlayerManager
    world = _world(tmp_path, "all-players", PARTY_KIT, {
        "name": "Rhiannon", "level": 0, "hp": {"current": 30, "max": 30},
        "stats": {"might": 3},
    })
    line = PlayerManager(world).show_all_players()[0]
    assert "?" not in line
    assert "Gold" not in line


def test_party_members_do_not_become_unknown_commoners(tmp_path):
    """race 'Unknown' and class 'Commoner' were invented: on a world with no
    classes every follower was reported as a Commoner, and the block indexed
    hp['current'] directly, which raises on a scalar-hp sheet."""
    world = _party_world(
        tmp_path, "party-kit", PARTY_KIT,
        {"name": "Rhiannon", "level": 0, "hp": {"current": 30, "max": 30}},
        {"level": 2, "hp": 6, "blood": 3})

    ctx = SessionManager(world).get_full_context()
    # Scoped to the PARTY MEMBERS section: the session header renders its own
    # unrelated "Unknown Campaign" / "Unknown" location-time boilerplate on a
    # minimal test world with no campaign.json, which a bare `ctx`-wide
    # assertion would trip regardless of how the party block itself renders.
    party_section = ctx.split("--- PARTY MEMBERS ---", 1)[1].split("--- NPC VOICES", 1)[0]
    assert "Commoner" not in party_section
    assert "Unknown" not in party_section
    assert "AC:" not in party_section
    assert "Mair (Lvl 2)" in ctx
    assert "HP: 6" in ctx
    assert "Blood: 3" in ctx


def test_party_members_keep_5e_fields_when_the_sheet_carries_them(tmp_path):
    world = _party_world(
        tmp_path, "party-5e", DND5E_RULESET,
        {"name": "Bram", "level": 3, "hp": {"current": 20, "max": 20}},
        {"level": 2, "race": "Human", "class": "Fighter", "ac": 16,
         "hp": {"current": 9, "max": 9}})

    ctx = SessionManager(world).get_full_context()
    assert "Mair (Lvl 2 Human Fighter)" in ctx
    assert "AC: 16" in ctx
    assert "HP: 9/9" in ctx
