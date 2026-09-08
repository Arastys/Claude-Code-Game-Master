"""A prose `room` must not poison the journal.

apply_stage used play_pack.room verbatim as a location key and as every present
NPC's location tag. npcs_present matches location by exact equality, so staged
NPCs became unreachable from any name a person would type.
"""

import json
from pathlib import Path

import pytest

from lib.entity_manager import npcs_present
from lib.play_pack import apply_stage, save_pack, _short_name

PROSE = ("Y Bedd — the offering stone on the shoulder above Cwm Bedd, at dusk. "
         "Turned earth where you came up.")


@pytest.mark.parametrize("room,expected", [
    (PROSE, "Y Bedd"),
    ("The Rusty Anchor", "The Rusty Anchor"),
    ("Barovia, the village", "Barovia"),
    ("Deck 12.", "Deck 12"),
    ("   ", "the stage"),
])
def test_short_name_derivation(room, expected):
    assert _short_name(room) == expected


def test_stage_keys_the_location_by_the_short_name(dcc_world):
    cdir = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl"
    overview = json.loads((cdir / "campaign-overview.json").read_text(encoding="utf-8"))
    overview["play_pack"] = {
        "whose_story": "Eurgain", "room": PROSE, "present": ["Nest"],
        "exits": [], "hook": "the cup", "offstage": [], "primer": "start here",
    }
    (cdir / "campaign-overview.json").write_text(json.dumps(overview, indent=2),
                                                 encoding="utf-8")
    apply_stage(cdir)

    locations = json.loads((cdir / "locations.json").read_text(encoding="utf-8"))
    assert "Y Bedd" in locations
    assert PROSE not in locations
    assert PROSE in locations["Y Bedd"]["description"]

    npcs = json.loads((cdir / "npcs.json").read_text(encoding="utf-8"))
    assert npcs["Nest"]["tags"]["locations"] == ["Y Bedd"]


def test_set_then_stage_leaves_the_pc_where_the_staged_cast_can_be_found(dcc_world):
    """The regression: `set` (save_pack) followed by `stage` (apply_stage) is the
    real back-to-back flow. save_pack used to write raw prose onto
    player_position.current_location while apply_stage keyed the staged NPCs'
    tags.locations by the short name — so npcs_present(...) at the PC's own
    position came back empty on the opening beat itself."""
    cdir = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl"
    save_pack(cdir, {
        "whose_story": "Eurgain", "room": PROSE, "present": ["Nest"],
        "exits": [], "hook": "the cup", "offstage": [], "primer": "start here",
    })
    apply_stage(cdir)

    overview = json.loads((cdir / "campaign-overview.json").read_text(encoding="utf-8"))
    assert overview["player_position"]["current_location"] == "Y Bedd"

    npcs = json.loads((cdir / "npcs.json").read_text(encoding="utf-8"))
    present = npcs_present(npcs, overview["player_position"]["current_location"])
    assert "Nest" in present


def test_a_well_formed_short_room_keeps_its_original_description(dcc_world):
    """room == room_key already — the description must not gain a redundant
    repeat of the room's own name (the constraint a short, well-formed room
    passes through unchanged, applied to the description too)."""
    cdir = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl"
    overview = json.loads((cdir / "campaign-overview.json").read_text(encoding="utf-8"))
    overview["play_pack"] = {
        "whose_story": "Eurgain", "room": "The Rusty Anchor", "present": [],
        "exits": [], "hook": "the cup", "offstage": [], "primer": "start here",
    }
    (cdir / "campaign-overview.json").write_text(json.dumps(overview, indent=2),
                                                 encoding="utf-8")
    apply_stage(cdir)

    locations = json.loads((cdir / "locations.json").read_text(encoding="utf-8"))
    assert locations["The Rusty Anchor"]["description"] == "start here"
    assert not locations["The Rusty Anchor"]["description"].startswith("The Rusty Anchor")
