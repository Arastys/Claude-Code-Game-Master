"""The --json envelope, through the bash wrappers, for the five tools that lacked it.

CLAUDE.md states "All tools take --json for structured returns" and
docs/conventions/tool-wrapper-contract.md makes it a documented convention. Five
tools did not implement it, and two of them wrote the flag to disk as data.

These drive the .sh wrappers rather than the Python entry points on purpose: a
`case` dispatcher that forwards only "$1" silently drops a trailing --json, and the
caller gets human text having asked for an envelope. Only a wrapper-level test sees
that.
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
        json.dumps({"current_date": "Late spring", "time_of_day": "Dusk",
                    "player_position": {"current_location": "Y Bedd"}}),
        encoding="utf-8")
    (campaign / "facts.json").write_text("{}", encoding="utf-8")
    return world, campaign


def _run(world, tool, *args):
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / tool), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))


def _envelope(proc):
    """Parse the envelope, failing loudly on a usage banner or leaked human text."""
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True, payload
    return payload["data"]


def test_note_add_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    data = _envelope(_run(world, "gm-note.sh", "lore", "The river remembers.", "--json"))
    assert data["category"] == "lore"
    assert data["fact"] == "The river remembers."


def test_note_add_does_not_leak_its_success_line_into_the_envelope(tmp_path):
    """add_fact prints [SUCCESS] from inside the manager; JSON mode must suppress
    it or json.loads sees text before the opening brace."""
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-note.sh", "lore", "A fact.", "--json")
    assert "[SUCCESS]" not in proc.stdout
    assert proc.stdout.lstrip().startswith("{")


def test_note_categories_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    _run(world, "gm-note.sh", "lore", "A fact.")
    assert "lore" in _envelope(_run(world, "gm-note.sh", "categories", "--json"))


def test_time_update_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    data = _envelope(_run(world, "gm-time.sh", "Dawn", "The ninth day", "--json"))
    assert data["time_of_day"] == "Dawn"
    assert data["current_date"] == "The ninth day"


def test_time_update_does_not_leak_human_text_into_the_envelope(tmp_path):
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-time.sh", "Dawn", "The ninth day", "--json")
    assert proc.stdout.lstrip().startswith("{")
    assert "[SUCCESS]" not in proc.stdout
