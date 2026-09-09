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
import sys
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


def _run_dm_json(world, tool, *args):
    """Same as _run, but with the ambient DM_JSON=1 envelope switch set and no
    --json flag anywhere — this is what should also produce (gm-note.sh,
    gm-time.sh) or refuse to produce (campaign_manager.py's bare-string verbs)
    an envelope purely from the environment."""
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / tool), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world), "DM_JSON": "1"},
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


def test_plot_list_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    _run(world, "gm-plot.sh", "add", "The Cup", "--description", "A thread.")
    assert isinstance(_envelope(_run(world, "gm-plot.sh", "list", "--json")), (list, dict))


def test_plot_show_forwards_json_through_a_single_argument_branch(tmp_path):
    """`show` passes only "$1" to Python, so a trailing --json was dropped and the
    caller got human text having asked for an envelope. This is the branch shape
    that made a whole verb's flag invisible."""
    world, _ = _world(tmp_path)
    _run(world, "gm-plot.sh", "add", "The Cup", "--description", "A thread.")
    data = _envelope(_run(world, "gm-plot.sh", "show", "The Cup", "--json"))
    assert "Cup" in json.dumps(data)


def test_plot_counts_forwards_json_through_a_no_argument_branch(tmp_path):
    world, _ = _world(tmp_path)
    assert _envelope(_run(world, "gm-plot.sh", "counts", "--json")) is not None


def test_plot_threads_forwards_json(tmp_path):
    """`threads` forwarded NO arguments at all before the fix and still exited 0, so
    a returncode-only assertion passed against the broken wrapper. Parse the
    envelope instead — that is the only thing the flag was asked for."""
    world, _ = _world(tmp_path)
    assert _envelope(_run(world, "gm-plot.sh", "threads", "--json")) is not None


def test_location_list_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    _run(world, "gm-location.sh", "add", "Y Bedd", "the ridge")
    assert _envelope(_run(world, "gm-location.sh", "list", "--json")) is not None


def test_campaign_list_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    assert _envelope(_run(world, "gm-campaign.sh", "list", "--json")) is not None


def test_dm_json_env_yields_exactly_one_envelope_from_each_of_the_five_tools(tmp_path):
    """DM_JSON=1 alone (no --json flag anywhere) must produce exactly one
    parseable envelope on stdout for every one of the five tools this branch
    fixed. Before this fix, gm-note.sh and gm-time.sh never folded DM_JSON into
    JSON_FLAG, so a downstream manager emitted an envelope purely from reading
    DM_JSON out of the environment itself while the wrapper's own human-only
    guards (the "Fact Categories:" header, the blank-line separator, the visible
    threat-clock/consequence tick) printed text alongside it — json.loads(stdout)
    saw leaked text or multiple concatenated objects rather than one clean
    envelope."""
    world, _ = _world(tmp_path)
    _run(world, "gm-plot.sh", "add", "The Cup", "--description", "A thread.")
    _run(world, "gm-location.sh", "add", "Y Bedd", "the ridge")
    cases = [
        ("gm-note.sh", ["categories"]),
        ("gm-time.sh", ["Dawn", "The ninth day"]),
        ("gm-plot.sh", ["list"]),
        ("gm-location.sh", ["list"]),
        ("gm-campaign.sh", ["list"]),
    ]
    for tool, args in cases:
        proc = _run_dm_json(world, tool, *args)
        assert proc.returncode == 0, (tool, proc.stdout, proc.stderr)
        payload = json.loads(proc.stdout)  # raises on leaked text or extra objects
        assert payload["ok"] is True, (tool, payload)


def test_campaign_manager_path_ignores_ambient_dm_json(tmp_path):
    """`lib/campaign_manager.py`'s `path`/`active`/`slugify`/`resolve` are
    plumbing consumed as a BARE STRING inside `$( )` at roughly twenty call
    sites (tools/gm-search.sh, gm-session.sh, gm-npc.sh, gm-playpack.sh,
    gm-extract.sh, plus several .claude/commands and world-builder). An ambient
    DM_JSON=1 must not turn their output into an envelope — only a literal
    --json on the invocation itself counts — or `CAMPAIGN_DIR=$(... path)`
    silently becomes garbage. This drives the manager directly (the layer the
    fix touches; test_slug_unify.py uses the same direct-invocation pattern for
    `slugify`), because tools/gm-campaign.sh's own pre-existing
    `[ "${DM_JSON:-}" = "1" ] && JSON_FLAG="--json"` fold (added for its
    genuinely-structured verbs like `list`/`info`) still converts an ambient
    DM_JSON=1 into a literal --json before invoking Python for every action —
    including `path` and `active` — so it cannot be told apart there from an
    explicit flag. That wrapper-level gap is out of this fix's scope."""
    world, _ = _world(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "campaign_manager.py"), "path"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world), "DM_JSON": "1"},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert not out.startswith("{"), out
    assert out.endswith("probe"), out


def test_campaign_manager_active_ignores_ambient_dm_json(tmp_path):
    world, _ = _world(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "campaign_manager.py"), "active"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world), "DM_JSON": "1"},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert not out.startswith("{"), out
    assert out == "probe"


def test_campaign_manager_path_with_explicit_json_flag_still_envelopes(tmp_path):
    """The explicit flag is exactly what still asks for the envelope, with or
    without DM_JSON in the environment."""
    world, _ = _world(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "campaign_manager.py"), "path", "--json"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"].endswith("probe")


def test_no_tool_ever_writes_the_flag_as_data(tmp_path):
    """The blanket guarantee: --json is honoured or refused, never absorbed."""
    world, campaign = _world(tmp_path)
    for tool, args in [("gm-note.sh", ["list"]), ("gm-time.sh", ["list"])]:
        proc = _run(world, tool, *args, "--json")
        assert proc.returncode != 0, f"{tool} accepted a flag as data"
    assert json.loads((campaign / "facts.json").read_text(encoding="utf-8")) == {}


def test_location_get_on_a_missing_name_is_a_clean_error_envelope(tmp_path):
    """get_location prints its [ERROR] to STDOUT, so an unquieted call puts human
    text ahead of the envelope and json.loads sees garbage."""
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-location.sh", "get", "Nowhere At All", "--json")
    assert "[ERROR]" not in proc.stdout, proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert proc.returncode != 0


def test_location_connections_on_a_missing_name_still_parses(tmp_path):
    """get_connections() calls get_location() internally, which printed
    "[ERROR] Location '...' not found" to stdout ahead of the envelope."""
    world, _ = _world(tmp_path)
    proc = _run(world, "gm-location.sh", "connections", "Nowhere At All", "--json")
    assert "[ERROR]" not in proc.stdout, proc.stdout
    assert _envelope(proc) == []


def test_the_wrapper_contract_names_enforcement_files_that_exist():
    """The convention doc claims four enforcement test files; none exists.

    Two places hide a filename here, and a naive path regex sees only one of them:
    the OKF frontmatter carries `- { resource: /tests/test_json_wrappers_player.py }`,
    and the prose says `tests/test_json_wrappers_*.py (player, npc, session,
    consequence)` — where three of the four names are bare words inside a
    parenthesis, not paths. Check both, or this test passes while three false
    claims stand.
    """
    import re
    doc = (REPO_ROOT / "docs" / "conventions" / "tool-wrapper-contract.md").read_text(
        encoding="utf-8")
    tests_dir = REPO_ROOT / "tests"

    def _missing(stem):
        return not (tests_dir / f"test_json_wrappers_{stem}.py").exists()

    missing = [f"test_json_wrappers_{n}.py"
               for n in re.findall(r"tests/test_json_wrappers_(\w+)\.py", doc)
               if _missing(n)]

    glob_list = re.search(r"tests/test_json_wrappers_\*\.py`?\s*\(([^)]*)\)", doc)
    if glob_list:
        missing += [f"test_json_wrappers_{w.strip()}.py (from the glob's own list)"
                    for w in re.split(r",\s*", glob_list.group(1))
                    if w.strip() and _missing(w.strip())]

    assert not missing, "doc names enforcement files that do not exist: " + ", ".join(missing)
