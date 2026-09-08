"""Tests for the knowledge ledger.

facts.json holds world truth. This holds the contested half: who has actually
been told what, and who is confidently wrong.
"""

import pytest

from lib.knowledge_manager import (
    KnowledgeManager, TRUTHS, STANCES, STATUSES, UNAWARE,
)

DROWNED = "the child drowned in Nant Ddu"
AGELESS = "Rhiannon does not age"


def test_vocabulary_is_pinned_to_the_literals():
    """Pin the literals, not the constants against themselves. Adding a fourth
    stance would keep `assert x in STANCES` green while breaking every consumer
    that renders or branches on the three."""
    assert TRUTHS == ("true", "false", "unresolved")
    assert STANCES == ("knows", "suspects")
    assert STATUSES == ("active", "dormant")
    assert UNAWARE == "unaware"


def test_add_proposition_assigns_an_id_and_defaults(dcc_world):
    m = KnowledgeManager(dcc_world)
    entry = m.add_proposition(DROWNED)
    assert entry["id"] == "P1"
    assert entry["statement"] == DROWNED
    assert entry["truth"] == "unresolved"
    assert entry["status"] == "active"
    assert entry["stances"] == {}
    assert "about" not in entry


def test_ids_are_monotonic_and_never_reused(dcc_world):
    m = KnowledgeManager(dcc_world)
    assert m.add_proposition(DROWNED)["id"] == "P1"
    assert m.add_proposition(AGELESS)["id"] == "P2"
    # Going dormant is retirement; the counter does not rewind.
    m.set_status("P2", "dormant")
    assert m.add_proposition("a third thing")["id"] == "P3"


def test_a_false_proposition_is_how_a_lie_is_stored(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED, truth="false", session=2)
    m.set_stance("P1", "Mair", "knows", source="told by Rhiannon", session=2)
    entry = m.get_propositions()["P1"]
    assert entry["truth"] == "false"
    assert entry["stances"]["Mair"]["stance"] == "knows"
    assert entry["stances"]["Mair"]["source"] == "told by Rhiannon"
    assert entry["stances"]["Mair"]["since"] == 2


def test_absence_is_unaware_and_is_never_stored(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.stance_of("P1", "Gwen") == UNAWARE
    assert m.get_propositions()["P1"]["stances"] == {}


def test_forget_returns_a_knower_to_unaware_and_removes_the_record(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    assert m.stance_of("P1", "Mair") == "knows"
    m.forget("P1", "MAIR")  # case-insensitive, matching npcs_present
    assert m.stance_of("P1", "Mair") == UNAWARE
    assert m.get_propositions()["P1"]["stances"] == {}


def test_setting_a_stance_stamps_touched_and_since(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, session=1)
    assert m.get_propositions()["P1"]["touched"] == 1
    m.set_stance("P1", "Mair", "suspects", session=6)
    entry = m.get_propositions()["P1"]
    assert entry["touched"] == 6
    assert entry["stances"]["Mair"]["since"] == 6


def test_a_second_stance_replaces_the_first(dcc_world):
    """Suspicion hardening into certainty is one record changing, not two."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "suspects", session=3)
    m.set_stance("P1", "Mair", "knows", source="Eurgain told her", session=5)
    stances = m.get_propositions()["P1"]["stances"]
    assert list(stances) == ["Mair"]
    assert stances["Mair"] == {"stance": "knows", "since": 5,
                               "source": "Eurgain told her"}


def test_a_faction_holds_a_stance_of_its_own(dcc_world):
    """No inheritance: the faction knowing says nothing about the member."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Y Bleiddiaid", "knows")
    assert m.stance_of("P1", "Y Bleiddiaid") == "knows"
    assert m.stance_of("P1", "Mair") == UNAWARE


def test_who_knows_resolves_by_id(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    assert list(m.who_knows("P2")) == ["P2"]


def test_who_knows_resolves_by_case_insensitive_substring(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    assert list(m.who_knows("NANT DDU")) == ["P1"]


def test_an_ambiguous_substring_returns_every_match_rather_than_guessing(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition("the ford is watched")
    m.add_proposition("the ford is safe after dark")
    assert sorted(m.who_knows("the ford")) == ["P1", "P2"]


def test_who_knows_prefers_an_exact_id_over_a_statement_substring(dcc_world):
    """A statement that literally contains another proposition's id must not
    hijack a lookup by that id."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition("the marker stone reads P2")
    m.add_proposition(AGELESS)
    assert list(m.who_knows("P2")) == ["P2"]


def test_held_by_reports_every_proposition_one_entity_holds(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    m.add_proposition("the ford is watched")
    m.set_stance("P1", "Mair", "knows")
    m.set_stance("P3", "Mair", "suspects")
    held = m.held_by("Mair")
    assert sorted(held) == ["P1", "P3"]
    assert held["P1"]["stance"] == "knows"
    assert held["P3"]["stance"] == "suspects"


def test_held_by_an_entity_with_no_stances_is_empty(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.held_by("Gwen") == {}


def test_status_moves_between_active_and_dormant(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.set_status("P1", "dormant")["status"] == "dormant"
    assert m.set_status("P1", "active")["status"] == "active"


def test_operations_on_an_unknown_proposition_return_none(dcc_world):
    m = KnowledgeManager(dcc_world)
    assert m.set_stance("P99", "Mair", "knows") is None
    assert m.forget("P99", "Mair") is None
    assert m.set_status("P99", "dormant") is None
    assert m.stance_of("P99", "Mair") == UNAWARE


@pytest.mark.parametrize("bad", ["maybe", "TRUE-ish", ""])
def test_an_invalid_truth_value_is_refused(dcc_world, bad):
    with pytest.raises(ValueError):
        KnowledgeManager(dcc_world).add_proposition(AGELESS, truth=bad)


def test_an_invalid_stance_is_refused(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    with pytest.raises(ValueError):
        m.set_stance("P1", "Mair", "certain")


def test_an_invalid_status_is_refused(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    with pytest.raises(ValueError):
        m.set_status("P1", "retired")


def test_about_is_stored_only_when_given(dcc_world):
    m = KnowledgeManager(dcc_world)
    entry = m.add_proposition(AGELESS, about="Rhiannon")
    assert entry["about"] == "Rhiannon"
    assert "about" not in m.add_proposition(DROWNED)


def test_the_ledger_survives_a_reload(dcc_world):
    """Every method reloads from disk; nothing is cached in the instance."""
    KnowledgeManager(dcc_world).add_proposition(AGELESS, about="Rhiannon")
    KnowledgeManager(dcc_world).set_stance("P1", "Mair", "knows", session=4)
    fresh = KnowledgeManager(dcc_world).get_propositions()
    assert fresh["P1"]["about"] == "Rhiannon"
    assert fresh["P1"]["stances"]["Mair"]["since"] == 4


# --- CLI + wrapper ---

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(world, *args):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(world))
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "knowledge_manager.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))


def test_cli_add_emits_a_json_envelope_with_the_new_id(dcc_world):
    proc = _run_cli(dcc_world, "add", DROWNED, "--truth", "false", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["id"] == "P1"
    assert payload["data"]["truth"] == "false"


def test_cli_stance_records_and_reports(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_cli(dcc_world, "stance", "P1", "Mair", "knows",
                    "--source", "told by Eurgain", "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)["data"]
    assert data["stances"]["Mair"]["stance"] == "knows"
    assert data["stances"]["Mair"]["source"] == "told by Eurgain"


def test_cli_rejects_an_unknown_proposition_with_a_nonzero_exit(dcc_world):
    proc = _run_cli(dcc_world, "stance", "P99", "Mair", "knows", "--json")
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "P99" in payload["error"]


def test_cli_rejects_an_invalid_stance_at_the_argument_parser(dcc_world):
    """Must prove ARGPARSE rejected it, not merely that something failed.

    `returncode != 0` cannot tell argparse's clean exit(2) from a regression that
    dropped choices=STANCES, let the value reach set_stance, and raised ValueError
    — which also exits nonzero.
    """
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_cli(dcc_world, "stance", "P1", "Mair", "certain", "--json")
    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_who_knows_returns_matches(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.set_stance("P1", "Mair", "knows")
    proc = _run_cli(dcc_world, "who-knows", "Nant Ddu", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["P1"]["stances"]["Mair"]["stance"] == "knows"


def test_cli_held_by_returns_what_one_entity_holds(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.set_stance("P1", "Mair", "suspects")
    proc = _run_cli(dcc_world, "held-by", "Mair", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["P1"]["stance"] == "suspects"


def test_cli_list_filters_by_status(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    m.set_status("P2", "dormant")
    assert list(json.loads(_run_cli(dcc_world, "list", "--active", "--json").stdout)["data"]) == ["P1"]
    assert list(json.loads(_run_cli(dcc_world, "list", "--dormant", "--json").stdout)["data"]) == ["P2"]
    assert sorted(json.loads(_run_cli(dcc_world, "list", "--json").stdout)["data"]) == ["P1", "P2"]


def test_cli_list_with_both_status_flags_prefers_active(dcc_world):
    """Sane precedence, pinned: --active wins rather than returning nothing."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    m.set_status("P2", "dormant")
    proc = _run_cli(dcc_world, "list", "--active", "--dormant", "--json")
    assert proc.returncode == 0, proc.stderr
    assert list(json.loads(proc.stdout)["data"]) == ["P1"]


def test_cli_forget_returns_the_knower_to_unaware(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    proc = _run_cli(dcc_world, "forget", "P1", "Mair", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["stances"] == {}


def test_cli_status_moves_a_proposition_dormant(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_cli(dcc_world, "status", "P1", "dormant", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["status"] == "dormant"


def test_cli_with_no_action_prints_help_and_exits_nonzero(dcc_world):
    proc = _run_cli(dcc_world)
    assert proc.returncode != 0


# --- Wrapper-level tests ---
#
# The CLI tests above invoke lib/knowledge_manager.py directly and never touch
# tools/gm-know.sh. That is not enough. A wrapper written as a `case` dispatcher
# rather than a genuine `"$@"` pass-through prints a usage banner and exits 0
# while every test above stays green — that exact defect shipped once and
# survived three review gates. json.loads() below fails hard on a usage banner.


def _run_wrapper(world, *args):
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "gm-know.sh"), *args],
        capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))


def test_wrapper_add_reaches_the_python_manager(dcc_world):
    proc = _run_wrapper(dcc_world, "add", AGELESS, "--truth", "true", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["id"] == "P1"


def test_wrapper_stance_reaches_the_python_manager(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_wrapper(dcc_world, "stance", "P1", "Mair", "suspects", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["stances"]["Mair"]["stance"] == "suspects"


def test_wrapper_forget_reaches_the_python_manager(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    proc = _run_wrapper(dcc_world, "forget", "P1", "Mair", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["stances"] == {}


def test_wrapper_who_knows_reaches_the_python_manager(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(DROWNED)
    proc = _run_wrapper(dcc_world, "who-knows", "P1", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["P1"]["statement"] == DROWNED


def test_wrapper_held_by_reaches_the_python_manager(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.set_stance("P1", "Y Bleiddiaid", "knows")
    proc = _run_wrapper(dcc_world, "held-by", "Y Bleiddiaid", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["P1"]["stance"] == "knows"


def test_wrapper_list_reaches_the_python_manager(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_wrapper(dcc_world, "list", "--json")
    assert proc.returncode == 0, proc.stderr
    assert list(json.loads(proc.stdout)["data"]) == ["P1"]


def test_wrapper_status_reaches_the_python_manager(dcc_world):
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_wrapper(dcc_world, "status", "P1", "dormant", "--json")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["data"]["status"] == "dormant"


def test_session_number_is_public_and_matches_the_private_accessor(dcc_world):
    """Other modules must not reach through an underscore for this."""
    from lib.session_manager import SessionManager
    sm = SessionManager(dcc_world)
    assert sm.session_number() == sm._get_session_number()


def test_the_skill_exists_and_declares_its_frontmatter():
    """The action router loads skills by name; a missing name breaks the load."""
    skill = REPO_ROOT / ".claude" / "skills" / "gm-knowledge" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert body.startswith("---")
    assert "name: gm-knowledge" in body
    assert "description:" in body


def test_claude_md_routes_information_changes_to_the_ledger():
    body = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "gm-know.sh" in body
    assert "gm-knowledge" in body


def test_knowledge_json_is_in_the_snapshot_contract():
    """A save that omits the ledger restores a world where an NPC still holds
    `knows` on something the restored state never told them — this system's own
    failure mode, arriving through the save system instead of through the GM."""
    from lib.session_manager import SessionManager
    assert "knowledge.json" in SessionManager.SNAPSHOT_JSON_FILES
    assert "knowledge.json" in SessionManager.CONTRACT_FILES


def test_reset_clears_the_knowledge_ledger():
    """Stale propositions naming deleted NPCs would render into a new campaign's
    brief. factions.json is cleared for the weaker version of this reason."""
    body = (REPO_ROOT / "tools" / "gm-reset.sh").read_text(encoding="utf-8")
    story_block = body.split("STORY_FILES=(")[1].split(")")[0]
    assert "knowledge.json" in story_block
