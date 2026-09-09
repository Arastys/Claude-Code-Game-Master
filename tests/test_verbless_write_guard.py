"""gm-note.sh and gm-time.sh take no subcommand, so their first positional IS data.

Every string was therefore a valid category and a valid time of day, and nothing
could be malformed. Probing the live campaign with `gm-note.sh list --json`
recorded a permanent fact whose text was "--json"; `gm-time.sh list --json` set the
date to "--json" and advanced every time-clock two segments. Both printed
[SUCCESS] and exited 0.
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _world(tmp_path):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / "probe"
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    (campaign / "ruleset.json").write_text(
        json.dumps({"name": "custom",
                    "stat_schema": {"attributes": ["might"], "vitals": ["hp"]},
                    "progression": {"model": "milestone"}}), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(
        json.dumps({"current_date": "Late spring, 2000 BC",
                    "time_of_day": "Dusk",
                    "player_position": {"current_location": "Y Bedd"}}),
        encoding="utf-8")
    (campaign / "facts.json").write_text("{}", encoding="utf-8")
    (campaign / "threat-clocks.json").write_text(json.dumps(
        {"Rhiwallon stops asking": {"current": 0, "max": 4,
                                    "advance_on": "time", "consequence": "..."}}),
        encoding="utf-8")
    return world, campaign


def _run(world, tool, *args):
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / tool), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))


def _read(campaign, name):
    return json.loads((campaign / name).read_text(encoding="utf-8"))


def test_note_refuses_a_flag_in_the_fact_slot(tmp_path):
    """The exact command that corrupted the live campaign."""
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "list", "--json")
    assert proc.returncode != 0
    assert _read(campaign, "facts.json") == {}


def test_time_refuses_a_flag_in_the_date_slot(tmp_path):
    """The second corrupting command: it also ticked a threat clock."""
    world, campaign = _world(tmp_path)
    before_overview = _read(campaign, "campaign-overview.json")
    proc = _run(world, "gm-time.sh", "list", "--json")
    assert proc.returncode != 0
    assert _read(campaign, "campaign-overview.json") == before_overview
    assert _read(campaign, "threat-clocks.json")["Rhiwallon stops asking"]["current"] == 0


def test_note_refuses_a_hyphen_category_without_any_json_flag(tmp_path):
    """The guard is about hyphens in data slots, not about --json specifically."""
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "--type", "a fact")
    assert proc.returncode != 0
    assert _read(campaign, "facts.json") == {}


def test_time_refuses_a_hyphen_time_of_day_without_any_json_flag(tmp_path):
    world, campaign = _world(tmp_path)
    before = _read(campaign, "campaign-overview.json")
    proc = _run(world, "gm-time.sh", "-x", "Some date")
    assert proc.returncode != 0
    assert _read(campaign, "campaign-overview.json") == before


def test_the_refusal_names_the_offending_value(tmp_path):
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "list", "--json")
    assert "--json" in proc.stderr


def test_a_legitimate_note_still_records(tmp_path):
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "lore", "The river remembers.")
    assert proc.returncode == 0, proc.stderr
    facts = _read(campaign, "facts.json")
    assert facts["lore"][0]["fact"] == "The river remembers."


def test_a_legitimate_time_update_still_works_and_still_ticks(tmp_path):
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-time.sh", "Dawn", "Late spring, the ninth day")
    assert proc.returncode == 0, proc.stderr
    overview = _read(campaign, "campaign-overview.json")
    assert overview["time_of_day"] == "Dawn"
    assert overview["current_date"] == "Late spring, the ninth day"
    assert _read(campaign, "threat-clocks.json")["Rhiwallon stops asking"]["current"] == 1


def test_note_categories_still_works(tmp_path):
    world, _ = _world(tmp_path)
    assert _run(world, "gm-note.sh", "categories").returncode == 0


def test_note_refuses_an_empty_category(tmp_path):
    """The hyphen check alone lets this through: an empty string does not match
    `-*`. `CAT=""; FACT="a fact"; gm-note.sh "$CAT" "$FACT"` recorded a fact
    under category "" and exited 0 before this fix — the identical corruption
    the hyphen guard exists to prevent, just reached by an empty variable
    instead of a stray flag."""
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "", "a fact")
    assert proc.returncode != 0
    assert _read(campaign, "facts.json") == {}


def test_note_refuses_an_empty_fact(tmp_path):
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "lore", "")
    assert proc.returncode != 0
    assert _read(campaign, "facts.json") == {}


def test_note_refuses_a_whitespace_only_category_and_fact(tmp_path):
    """The exact repro from the review: CAT=""; FACT=""; gm-note.sh "$CAT"
    "$FACT" — both empty. A whitespace-only value is the same shape of mistake
    and must be refused too."""
    world, campaign = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "   ", "   ")
    assert proc.returncode != 0
    assert _read(campaign, "facts.json") == {}


def test_the_empty_refusal_names_the_slot(tmp_path):
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "", "a fact")
    assert "category" in proc.stderr
    assert "cannot be empty" in proc.stderr
