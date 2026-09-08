# Knowledge Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the world a record of who has actually been told what, so an NPC never reacts to information nobody ever gave them.

**Architecture:** A new per-campaign `knowledge.json` holding propositions (a statement plus a truth value) and stances (one named entity's relationship to a proposition). A new `lib/knowledge_manager.py` owns it, mirroring `lib/faction_manager.py` exactly — same `EntityManager` base, same load/save shape, same `main()` + `--json` envelope, same thin `"$@"` bash wrapper. The scene brief gains a WHO KNOWS WHAT block that is silent unless the ledger has something relevant to the room. No propagation, no inheritance, no dice.

**Tech Stack:** Python 3 (stdlib only), `argparse`, pytest, bash wrappers. Run everything with `uv run python`, never bare `python`.

**Spec:** `docs/superpowers/specs/2026-09-08-knowledge-ledger.md`

## Global Constraints

- **The engine holds no game's concepts.** Nothing in `lib/` may name a campaign concept, branch on kit identity, or invent a default for something a kit never declared. Every change must be expressible by a world that has never heard of vampires and equally by one that has never heard of D&D.
- **`unaware / suspects / knows`** are the only stances. `true / false / unresolved` are the only truth values. `active / dormant` are the only statuses.
- **Absence is `unaware`, and is never stored.** No code path may write an "unaware" stance record.
- **No inheritance.** A faction's stance is never copied to, or inferred for, its members. The brief may report the asymmetry; it may never assert that a member knows.
- **Ids are monotonic and never reused.** There is no delete verb for a proposition.
- **Every wrapper verb gets a wrapper-level subprocess test** driving `tools/gm-know.sh` through `bash`, not only `lib/knowledge_manager.py` through `sys.executable`. A previous plan shipped a verb that printed a usage banner and exited 0 through three review gates because only the Python entry point was tested.
- **Test against three kits** — `dnd5e`, the resource-axis DCC fixture, and a `custom` kit — using the existing `_make_world(tmp_path, slug, ruleset)` builder in `tests/test_kit_vitals.py`. A change that works for only one has not met the bar.
- **All file writes use `encoding="utf-8"`.** This repo runs on Windows where `open()` defaults to cp1252.
- **Run the suite as** `uv run python -m pytest -q --continue-on-collection-errors`. `tests/test_reset_archive.py` fails to collect on Windows (`os.geteuid` is POSIX-only) and will interrupt the run otherwise. The baseline is **31 failed / 719 passed**; the failing set must be byte-identical when you finish. pytest on this machine does not print a final tally line — count `^FAILED ` lines and cross-check against the progress markers rather than inferring.

---

## File Structure

| File | Responsibility |
|---|---|
| `lib/knowledge_manager.py` (create) | The whole ledger: storage, stance queries, and the pure render used by the brief. One file, matching `faction_manager.py` in size and shape. |
| `tools/gm-know.sh` (create) | Thin `"$@"` pass-through wrapper. No `case` dispatch. |
| `tests/test_knowledge_manager.py` (create) | Manager behaviour, CLI envelope, wrapper subprocess. |
| `tests/test_knowledge_in_context.py` (create) | The brief block across three kits, including silence. |
| `lib/session_manager.py` (modify) | Public `session_number()`; the WHO KNOWS WHAT block. |
| `.claude/skills/gm-knowledge/SKILL.md` (create) | On-demand GM workflow: when to write a stance, and how the ledger shapes narration. |
| `CLAUDE.md` (modify) | Persistence table rows, living-world paragraph, action router row. |
| `docs/modules/living-world.md` (modify) | Document the ledger alongside tracks and factions. |

---

### Task 1: The ledger core

**Files:**
- Create: `lib/knowledge_manager.py`
- Test: `tests/test_knowledge_manager.py`

**Interfaces:**
- Consumes: `lib/entity_manager.py` — `EntityManager.__init__(world_state_dir)`, and `self.json_ops.load_json(name)` / `save_json(name, data)` which resolve paths inside the active campaign.
- Produces, for Tasks 2 and 3:
  - `KnowledgeManager(world_state_dir=None)`
  - `add_proposition(statement, truth="unresolved", about=None, status="active", session=0) -> dict` (the entry plus `id`)
  - `set_stance(pid, knower, stance, source=None, session=0) -> dict | None`
  - `forget(pid, knower) -> dict | None`
  - `stance_of(pid, knower) -> str`
  - `set_status(pid, status) -> dict | None`
  - `get_propositions() -> dict`
  - `who_knows(needle) -> dict`
  - `held_by(knower) -> dict`
  - Module constants `TRUTHS`, `STANCES`, `STATUSES`, `UNAWARE`, `BRIEF_LIMIT`
  - Static helpers `_record_in(entry, knower)` and `_stance_in(entry, knower)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_manager.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'lib.knowledge_manager'`.

- [ ] **Step 3: Write the implementation**

Create `lib/knowledge_manager.py`:

```python
#!/usr/bin/env python3
"""
The knowledge ledger — who has actually been told what.

`facts.json` holds world truth: global, unowned, uncontested. This owns the
contested half. A proposition is a statement with a truth value; a stance is one
named entity's relationship to it. Deception needs no separate machinery — a
proposition marked `false` that someone holds as `knows` is a character who is
certain and wrong.

Nothing here decides who learns what. A stance is written when the fiction moves
information, the same way a faction standing is written when a bargain is kept.
There is no propagation and no inheritance: a faction's stance says nothing about
its members, because a ledger that infers knowledge nobody was given fails at the
one job it has.

Absence is `unaware` and is never stored, so recording ignorance — the common
case — costs nothing.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager

TRUTHS = ("true", "false", "unresolved")
STANCES = ("knows", "suspects")
STATUSES = ("active", "dormant")
UNAWARE = "unaware"
BRIEF_LIMIT = 5


def _norm(value: Any) -> str:
    """Case-insensitive key, matching entity_manager.npcs_present."""
    return str(value or "").strip().lower()


def _one_of(value: Any, allowed: tuple, field: str) -> str:
    normalized = _norm(value)
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {allowed}, got {value!r}")
    return normalized


class KnowledgeManager(EntityManager):
    """Propositions, and who holds a stance on them."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.knowledge_file = "knowledge.json"

    def _load(self) -> Dict[str, Any]:
        data = self.json_ops.load_json(self.knowledge_file) or {}
        data.setdefault("next_id", 1)
        data.setdefault("propositions", {})
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.json_ops.save_json(self.knowledge_file, data)

    @staticmethod
    def _record_in(entry: Dict[str, Any], knower: str) -> Optional[Dict[str, Any]]:
        """The stance record this knower holds on this entry, or None."""
        needle = _norm(knower)
        for held, record in (entry.get("stances") or {}).items():
            if _norm(held) == needle:
                return record
        return None

    @staticmethod
    def _stance_in(entry: Dict[str, Any], knower: str) -> str:
        return (KnowledgeManager._record_in(entry, knower) or {}).get("stance", UNAWARE)

    def add_proposition(self, statement: str, truth: str = "unresolved",
                        about: str = None, status: str = "active",
                        session: int = 0) -> Dict[str, Any]:
        """Create a proposition and return it with its assigned id."""
        truth = _one_of(truth, TRUTHS, "truth")
        status = _one_of(status, STATUSES, "status")
        data = self._load()
        pid = f"P{data['next_id']}"
        data["next_id"] = int(data["next_id"]) + 1  # monotonic; ids are never reused
        entry = {
            "statement": str(statement),
            "truth": truth,
            "status": status,
            "touched": int(session),
            "stances": {},
        }
        if about:
            entry["about"] = str(about)
        data["propositions"][pid] = entry
        self._save(data)
        return dict(entry, id=pid)

    def set_stance(self, pid: str, knower: str, stance: str,
                   source: str = None, session: int = 0) -> Optional[Dict[str, Any]]:
        """Record that this entity knows or suspects. Replaces any earlier stance."""
        stance = _one_of(stance, STANCES, "stance")
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        record = {"stance": stance, "since": int(session)}
        if source:
            record["source"] = str(source)
        stances = entry.setdefault("stances", {})
        for held in [k for k in stances if _norm(k) == _norm(knower)]:
            del stances[held]
        stances[knower] = record
        entry["touched"] = int(session)
        self._save(data)
        return dict(entry, id=pid)

    def forget(self, pid: str, knower: str) -> Optional[Dict[str, Any]]:
        """Remove a stance, returning that knower to `unaware`."""
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        stances = entry.setdefault("stances", {})
        for held in [k for k in stances if _norm(k) == _norm(knower)]:
            del stances[held]
        self._save(data)
        return dict(entry, id=pid)

    def stance_of(self, pid: str, knower: str) -> str:
        """`knows`, `suspects`, or `unaware`. Unaware is never stored."""
        return self._stance_in(self._load()["propositions"].get(pid) or {}, knower)

    def set_status(self, pid: str, status: str) -> Optional[Dict[str, Any]]:
        status = _one_of(status, STATUSES, "status")
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        entry["status"] = status
        self._save(data)
        return dict(entry, id=pid)

    def get_propositions(self) -> Dict[str, Any]:
        return self._load()["propositions"]

    def who_knows(self, needle: str) -> Dict[str, Any]:
        """Resolve by exact id first, else by case-insensitive substring of the
        statement. A substring matching several returns all of them rather than
        guessing which was meant."""
        props = self.get_propositions()
        if needle in props:
            return {needle: props[needle]}
        n = _norm(needle)
        return {pid: e for pid, e in props.items()
                if n and n in _norm(e.get("statement"))}

    def held_by(self, knower: str) -> Dict[str, Any]:
        """Every proposition this entity holds a stance on, with that stance.

        Named `held_by` rather than `knows` so the verb never collides with the
        stance value of the same name.
        """
        out = {}
        for pid, entry in self.get_propositions().items():
            stance = self._stance_in(entry, knower)
            if stance != UNAWARE:
                out[pid] = dict(entry, id=pid, stance=stance)
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q`
Expected: all pass.

- [ ] **Step 5: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: 31 failed, the same 31 as the baseline. Count `^FAILED ` lines; do not infer from a summary line, which this pytest does not print.

- [ ] **Step 6: Commit**

```bash
git add lib/knowledge_manager.py tests/test_knowledge_manager.py
git commit -m "knowledge-ledger: propositions and stances, with absence as unaware"
```

---

### Task 2: The CLI, the wrapper, and a public session number

**Files:**
- Modify: `lib/knowledge_manager.py` (append `main()`)
- Create: `tools/gm-know.sh`
- Modify: `lib/session_manager.py` (add `session_number()` beside `_get_session_number()` at line 1496)
- Test: `tests/test_knowledge_manager.py` (append)

**Interfaces:**
- Consumes from Task 1: every `KnowledgeManager` method listed there.
- Consumes: `lib/cli_output.py` — `wants_json(argv=None) -> bool`, `strip_json_flag(argv=None) -> list`, `emit(data=None, message=None, json_mode=False)`, `emit_error(message, json_mode=False, code=None) -> int` (returns 1, so `sys.exit(emit_error(...))` is the idiom).
- Produces: `SessionManager.session_number() -> int`, used by Task 3 and by this task's `main()`.

**Note on the session number.** `campaign-overview.json` has a `session_count` field, but `campaign_manager.py` writes it once at creation and nothing ever increments it — it reads 0 forever. Do not use it. The live number is `SessionManager._get_session_number()`, derived from matched start/end pairs in `session-log.md`; this task adds a public alias so other modules are not reaching through an underscore.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_knowledge_manager.py`:

```python
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
    KnowledgeManager(dcc_world).add_proposition(AGELESS)
    proc = _run_cli(dcc_world, "stance", "P1", "Mair", "certain", "--json")
    assert proc.returncode != 0


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q -k "cli or wrapper or session_number"`
Expected: failures — the CLI has no `main()`, `tools/gm-know.sh` does not exist, and `SessionManager` has no `session_number`.

- [ ] **Step 3: Add the public session accessor**

In `lib/session_manager.py`, immediately **before** `def _get_session_number(self) -> int:` (line 1496), insert:

```python
    def session_number(self) -> int:
        """Public alias for the current session number.

        Other modules need this and should not reach through an underscore for
        it. The derivation stays in _get_session_number, which the rest of this
        class already calls.
        """
        return self._get_session_number()

```

- [ ] **Step 4: Append `main()` to `lib/knowledge_manager.py`**

```python
def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="The knowledge ledger")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("statement")
    p.add_argument("--truth", choices=TRUTHS, default="unresolved")
    p.add_argument("--about")
    p.add_argument("--status", choices=STATUSES, default="active")
    p = sub.add_parser("stance"); p.add_argument("pid"); p.add_argument("knower")
    p.add_argument("stance", choices=STANCES); p.add_argument("--source")
    p = sub.add_parser("forget"); p.add_argument("pid"); p.add_argument("knower")
    p = sub.add_parser("who-knows"); p.add_argument("needle")
    p = sub.add_parser("held-by"); p.add_argument("knower")
    p = sub.add_parser("status"); p.add_argument("pid")
    p.add_argument("status", choices=STATUSES)
    p = sub.add_parser("list")
    p.add_argument("--active", action="store_true")
    p.add_argument("--dormant", action="store_true")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = KnowledgeManager()
    session = _current_session()

    if args.action == "add":
        out = m.add_proposition(args.statement, truth=args.truth,
                                about=args.about, status=args.status,
                                session=session)
    elif args.action == "stance":
        out = m.set_stance(args.pid, args.knower, args.stance,
                           source=args.source, session=session)
    elif args.action == "forget":
        out = m.forget(args.pid, args.knower)
    elif args.action == "who-knows":
        out = m.who_knows(args.needle)
    elif args.action == "held-by":
        out = m.held_by(args.knower)
    elif args.action == "status":
        out = m.set_status(args.pid, args.status)
    else:
        props = m.get_propositions()
        if args.active:
            props = {k: v for k, v in props.items() if v.get("status") == "active"}
        elif args.dormant:
            props = {k: v for k, v in props.items() if v.get("status") == "dormant"}
        out = props

    if out is None:
        sys.exit(emit_error(f"no such proposition: {args.pid}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Add this helper just above `main()`, so the session lookup stays out of the class and the import stays lazy:

```python
def _current_session() -> int:
    """The live session number, or 0 if it cannot be read.

    Imported lazily: session_manager is a large module and the ledger itself has
    no need of it. Never read `session_count` from campaign-overview.json —
    campaign_manager writes it once at creation and nothing increments it.
    """
    try:
        from session_manager import SessionManager
        return SessionManager().session_number()
    except Exception:
        return 0
```

- [ ] **Step 5: Create the wrapper**

Create `tools/gm-know.sh`:

```bash
#!/bin/bash
# gm-know.sh - The knowledge ledger (thin wrapper for knowledge_manager.py)
#
#   gm-know.sh add "<statement>" [--truth true|false|unresolved] [--about "X"] [--status active|dormant]
#   gm-know.sh stance P4 "Mair" knows|suspects [--source "told by Eurgain"]
#   gm-know.sh forget P4 "Mair"              Return them to unaware
#   gm-know.sh who-knows P4|"substring"      Every stance on a proposition
#   gm-know.sh held-by "Mair"                Everything one entity holds
#   gm-know.sh list [--active|--dormant]     All propositions
#   gm-know.sh status P4 active|dormant      Retire it, or wake it up
#
# A proposition is a statement with a truth value; a stance is one entity's
# relationship to it. A `false` proposition someone `knows` is how a lie is
# stored. Absence is `unaware` — never record that someone does not know.
# Knowers are NPCs, factions, or the PC, and there is NO inheritance: a faction
# knowing something says nothing about its members.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/knowledge_manager.py" "$@"
```

Then make it executable:

```bash
chmod +x tools/gm-know.sh
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q`
Expected: all pass.

- [ ] **Step 7: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: the same 31 baseline failures.

- [ ] **Step 8: Commit**

```bash
git add lib/knowledge_manager.py lib/session_manager.py tools/gm-know.sh tests/test_knowledge_manager.py
git commit -m "gm-know: CLI and wrapper for the ledger, plus a public session number"
```

---

### Task 3: The WHO KNOWS WHAT block in the scene brief

**Files:**
- Modify: `lib/knowledge_manager.py` (add `relevant()` and `render()`)
- Modify: `lib/session_manager.py` (insert the block immediately before `# --- Pending Consequences ---`, line 1051)
- Test: `tests/test_knowledge_in_context.py` (create)

**Interfaces:**
- Consumes from Task 1: `KnowledgeManager._record_in`, `_stance_in`, `BRIEF_LIMIT`, `UNAWARE`, `_norm`.
- Consumes from Task 2: nothing at runtime.
- Produces:
  - `KnowledgeManager.relevant(propositions, present, limit=BRIEF_LIMIT) -> (list[tuple[str, dict]], int)` — the shown propositions and the dormant count.
  - `KnowledgeManager.render(propositions, present, factions=None, limit=BRIEF_LIMIT) -> str` — the block body, or `""` when nothing qualifies.

**Rendering rules, exactly.**
- A proposition is shown when its status is `active` **and** it is relevant: some entity in `present` holds a stance on it, or its `about` matches an entity in `present`.
- Shown propositions are sorted most-recently-`touched` first, ties broken by id ascending, then capped at `limit`.
- The roster under each proposition is every name in `present`, in the order given, followed by any other stance holder not already in `present` — that second group is how a faction or an absent witness appears at all.
- A roster name with no stance renders `unaware`. `knows` renders upper-case `KNOWS`; `suspects` renders lower-case.
- Truth renders as `(true)`, `(FALSE)` — upper-case, because a false proposition someone believes is the thing most worth catching — or `(unresolved)`.
- When `factions` is supplied and a roster name is a key in it holding `knows`, any present NPC who is a member of that faction and is `unaware` is named on the faction's line: `— Mair does not` for one, `— Mair, Gwen do not` for several.
- The dormant count is appended as a final line when it is greater than zero: `2 dormant propositions not shown.` (singular: `1 dormant proposition not shown.`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_in_context.py`:

```python
"""The WHO KNOWS WHAT block — the discipline half of the ledger.

The point is the negative space: the block must show me what a present NPC does
NOT know, so I never have them react to something nobody told them. It must also
stay silent in a world that never uses it.
"""

import json

import pytest

from lib.knowledge_manager import KnowledgeManager
from lib.session_manager import SessionManager
from tests.test_kit_vitals import _make_world

MILESTONE_RULESET = {
    "name": "custom",
    "stat_schema": {"attributes": ["might", "cunning"], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
}
DND5E_RULESET = {
    "name": "dnd5e",
    "stat_schema": {
        "attributes": ["str", "dex", "con", "int", "wis", "cha"],
        "vitals": ["hp"],
    },
    "progression": {"model": "xp-levels"},
}
RESOURCE_AXIS_RULESET = {
    "name": "dcc",
    "stat_schema": {"attributes": ["str", "agi"], "vitals": ["hp"]},
    "progression": {"model": "resource-axis", "axis": "viewers"},
}

DROWNED = "the child drowned in Nant Ddu"
AGELESS = "Rhiannon does not age"


def _world_with_npcs(tmp_path, slug, ruleset, npcs, location="Cwm Bychan"):
    world = _make_world(tmp_path, slug, ruleset)
    campaign = world / "campaigns" / slug
    (campaign / "npcs.json").write_text(json.dumps(npcs), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(
        json.dumps({"player_position": {"current_location": location}}),
        encoding="utf-8")
    return world


def _npc(location="Cwm Bychan"):
    return {"description": "a villager", "attitude": "neutral",
            "tags": {"locations": [location]}}


# --- The pure renderer ---

def test_render_is_empty_when_nothing_is_relevant(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Someone Far Away", "knows")
    assert KnowledgeManager.render(m.get_propositions(), ["Mair"]) == ""


def test_render_shows_a_present_npc_who_does_not_know(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, truth="true")
    m.set_stance("P1", "Mair", "knows", source="told by Eurgain", session=5)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair", "Gwen"])
    assert "P1" in out
    assert AGELESS in out
    assert "(true)" in out
    assert "KNOWS" in out
    assert "s5, told by Eurgain" in out
    assert "Gwen" in out and "unaware" in out


def test_a_false_proposition_is_marked_loudly(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED, truth="false")
    m.set_stance("P1", "Mair", "knows", session=2)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "(FALSE)" in out


def test_a_proposition_about_a_present_npc_shows_even_when_nobody_present_holds_it(dcc_world):
    """Dramatic irony: the thing is about her and she has not been told."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "P1" in out
    assert "unaware" in out


def test_an_absent_stance_holder_still_appears_under_the_proposition(dcc_world):
    """A faction is how the leak becomes visible; it is never 'present'."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "Y Bleiddiaid" in out


def test_a_faction_that_knows_names_the_member_who_does_not(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    factions = {"Y Bleiddiaid": {"members": ["Mair", "Gwen"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"], factions=factions)
    assert "— Mair does not" in out


def test_two_members_who_do_not_know_are_named_together(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    factions = {"Y Bleiddiaid": {"members": ["Mair", "Gwen"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair", "Gwen"],
                                  factions=factions)
    assert "— Mair, Gwen do not" in out


def test_a_member_who_already_knows_is_not_named(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    m.set_stance("P1", "Mair", "knows", session=2)
    factions = {"Y Bleiddiaid": {"members": ["Mair"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"], factions=factions)
    assert "does not" not in out


def test_dormant_propositions_are_counted_not_shown(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    m.add_proposition("a third", status="dormant")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert DROWNED not in out
    assert "2 dormant propositions not shown." in out


def test_one_dormant_proposition_is_singular(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "1 dormant proposition not shown." in out


def test_only_the_five_most_recently_touched_are_shown(dcc_world):
    m = KnowledgeManager(dcc_world)
    for i in range(7):
        m.add_proposition(f"thing {i}")
        m.set_stance(f"P{i + 1}", "Mair", "knows", session=i)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "thing 6" in out and "thing 2" in out
    assert "thing 1" not in out and "thing 0" not in out


def test_relevant_reports_the_shown_set_and_the_dormant_count(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    shown, dormant = KnowledgeManager.relevant(m.get_propositions(), ["Mair"])
    assert [pid for pid, _ in shown] == ["P1"]
    assert dormant == 1


# --- In the scene brief, across three kits ---

@pytest.mark.parametrize("slug,ruleset", [
    ("custom-kit", MILESTONE_RULESET),
    ("forgotten-realms", DND5E_RULESET),
    ("dcc-axis", RESOURCE_AXIS_RULESET),
])
def test_an_empty_ledger_leaves_the_brief_completely_silent(tmp_path, slug, ruleset):
    world = _world_with_npcs(tmp_path, slug, ruleset, {"Mair": _npc()})
    ctx = SessionManager(world).get_full_context()
    assert "WHO KNOWS WHAT" not in ctx


@pytest.mark.parametrize("slug,ruleset", [
    ("custom-kit", MILESTONE_RULESET),
    ("forgotten-realms", DND5E_RULESET),
    ("dcc-axis", RESOURCE_AXIS_RULESET),
])
def test_the_block_appears_for_every_kit_when_the_ledger_is_used(tmp_path, slug, ruleset):
    world = _world_with_npcs(tmp_path, slug, ruleset,
                             {"Mair": _npc(), "Gwen": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition(AGELESS, truth="true")
    m.set_stance("P1", "Mair", "knows", source="told by Eurgain", session=5)
    ctx = SessionManager(world).get_full_context()
    assert "--- WHO KNOWS WHAT (present) ---" in ctx
    assert AGELESS in ctx
    assert "Gwen" in ctx


def test_a_ledger_with_nothing_relevant_to_this_room_stays_silent(tmp_path):
    """An active proposition about people who are elsewhere must not fill the brief."""
    world = _world_with_npcs(tmp_path, "custom-kit", MILESTONE_RULESET,
                             {"Mair": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition("something in another valley")
    m.set_stance("P1", "A Stranger", "knows")
    assert "WHO KNOWS WHAT" not in SessionManager(world).get_full_context()


def test_the_block_sits_before_pending_consequences(tmp_path):
    world = _world_with_npcs(tmp_path, "custom-kit", MILESTONE_RULESET,
                             {"Mair": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    ctx = SessionManager(world).get_full_context()
    assert ctx.index("WHO KNOWS WHAT") < ctx.index("PENDING CONSEQUENCES")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_knowledge_in_context.py -q`
Expected: `AttributeError: type object 'KnowledgeManager' has no attribute 'render'`.

- [ ] **Step 3: Add `relevant()` and `render()` to `lib/knowledge_manager.py`**

Insert both as static methods on `KnowledgeManager`, after `_stance_in`:

```python
    @staticmethod
    def relevant(propositions: Dict[str, Any], present,
                 limit: int = BRIEF_LIMIT):
        """(shown, dormant_count) — the active propositions this room can act on.

        Relevant means someone in `present` holds a stance, or `about` names one
        of them. Relevance is what keeps the block short enough to read every
        beat: an active proposition concerning people who are nowhere near this
        scene stays silent until they walk on.

        Most recently touched first, ties broken by id so the order is stable
        across runs.
        """
        present_norm = {_norm(p) for p in (present or []) if _norm(p)}
        shown, dormant = [], 0
        for pid, entry in (propositions or {}).items():
            if _norm(entry.get("status", "active")) == "dormant":
                dormant += 1
                continue
            holders = {_norm(k) for k in (entry.get("stances") or {})}
            about = _norm(entry.get("about"))
            if (holders & present_norm) or (about and about in present_norm):
                shown.append((pid, entry))
        shown.sort(key=lambda pe: (-int(pe[1].get("touched", 0) or 0), pe[0]))
        return shown[:limit], dormant

    @staticmethod
    def render(propositions: Dict[str, Any], present, factions=None,
               limit: int = BRIEF_LIMIT) -> str:
        """The WHO KNOWS WHAT body, or "" when nothing qualifies.

        `factions` is passed in rather than read here so this module never
        touches another manager's file. It is only used to name a present member
        who is unaware of what their own faction knows — the tension that makes
        the leak visible. It never implies the member knows.
        """
        shown, dormant = KnowledgeManager.relevant(propositions, present, limit)
        if not shown:
            return ""

        roster_base = [str(p) for p in (present or []) if str(p).strip()]
        lines = []
        for pid, entry in shown:
            truth = entry.get("truth", "unresolved")
            lines.append(
                f'{pid}  "{entry.get("statement", "")}"  '
                f'({"FALSE" if truth == "false" else truth})')

            seen = {_norm(n) for n in roster_base}
            roster = list(roster_base)
            for holder in (entry.get("stances") or {}):
                if _norm(holder) not in seen:
                    roster.append(holder)
                    seen.add(_norm(holder))
            width = max(len(n) for n in roster)

            for name in roster:
                record = KnowledgeManager._record_in(entry, name)
                if record is None:
                    lines.append(f"    {name.ljust(width)}  {UNAWARE}")
                    continue
                stance = record.get("stance", UNAWARE)
                label = "KNOWS" if stance == "knows" else stance
                detail = f"s{record.get('since', 0)}"
                if record.get("source"):
                    detail += f", {record['source']}"
                line = f"    {name.ljust(width)}  {label.ljust(8)} {detail}"
                blind = KnowledgeManager._members_unaware(
                    entry, name, stance, present, factions)
                if blind:
                    verb = "does not" if len(blind) == 1 else "do not"
                    line += f"  — {', '.join(blind)} {verb}"
                lines.append(line)

        if dormant:
            noun = "proposition" if dormant == 1 else "propositions"
            lines.append(f"{dormant} dormant {noun} not shown.")
        return "\n".join(lines)

    @staticmethod
    def _members_unaware(entry, name, stance, present, factions):
        """Present members of `name` (a faction that knows) who are unaware.

        Reports the asymmetry. It never asserts that the member knows — that
        would be the inheritance this system exists to refuse.
        """
        if stance != "knows" or not factions:
            return []
        faction = None
        for fname, fdata in factions.items():
            if _norm(fname) == _norm(name):
                faction = fdata
                break
        if not isinstance(faction, dict):
            return []
        members = {_norm(x) for x in (faction.get("members") or [])}
        return [str(p) for p in (present or [])
                if _norm(p) in members
                and KnowledgeManager._stance_in(entry, p) == UNAWARE]
```

- [ ] **Step 4: Wire it into the scene brief**

In `lib/session_manager.py`, insert immediately **before** the line `        # --- Pending Consequences ---` (line 1051):

```python
        # --- Knowledge ledger (who has actually been told what; silent unless used) ---
        knowledge = self.json_ops.load_json("knowledge.json") or {}
        if knowledge.get("propositions"):
            from knowledge_manager import KnowledgeManager
            roster = [npc_name for npc_name, _ in present_npcs]
            if isinstance(char, dict) and char.get("name"):
                roster.append(char["name"])
            block = KnowledgeManager.render(
                knowledge["propositions"], roster,
                factions=self.json_ops.load_json("factions.json") or {})
            if block:
                lines.append("")
                lines.append("--- WHO KNOWS WHAT (present) ---")
                lines.append(block)

```

Both `present_npcs` and `char` are already in scope at that point — `present_npcs` is assigned unconditionally at line 1002, `char` in the CHARACTER section above it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_knowledge_in_context.py -q`
Expected: all pass.

- [ ] **Step 6: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: the same 31 baseline failures. `tests/test_get_full_context.py` in particular must stay green — it characterizes this exact function.

- [ ] **Step 7: Commit**

```bash
git add lib/knowledge_manager.py lib/session_manager.py tests/test_knowledge_in_context.py
git commit -m "scene-context: a WHO KNOWS WHAT block, silent unless the ledger is used"
```

---

### Task 4: The `gm-knowledge` Skill and the wiring that makes it findable

**Files:**
- Create: `.claude/skills/gm-knowledge/SKILL.md`
- Modify: `CLAUDE.md` (persistence table, living-world bullet, action router)
- Modify: `docs/modules/living-world.md`
- Test: `tests/test_knowledge_manager.py` (append two)

**Interfaces:**
- Consumes: the `tools/gm-know.sh` verbs from Task 2 and the block name from Task 3.
- Produces: nothing code-facing.

**Why a Skill.** The eight existing `gm-*` skills are loaded on demand by the action router. This one is different in kind: it is not triggered by a player saying "I attack", it is triggered by information moving. The skill's job is to say when to write a stance, and to carry the narration obligation the spec puts on the PC's own stances.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_knowledge_manager.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q -k "skill or claude_md"`
Expected: `FileNotFoundError` on the skill, and an assertion failure on `CLAUDE.md`.

- [ ] **Step 3: Write the Skill**

Create `.claude/skills/gm-knowledge/SKILL.md`:

```markdown
---
name: gm-knowledge
description: The knowledge ledger — who has actually been told what. Load when information moves (someone witnesses, confesses, lies, overhears, or is deliberately kept in the dark), when you are about to have an NPC act on something, or when the WHO KNOWS WHAT block shows a stance you are unsure how to play.
---

# Who Knows What

The ledger exists to stop one specific failure: an NPC reacting to information
nobody ever gave them. That failure is silent — nothing crashes, the scene just
quietly stops being a world that can keep a secret.

## The model

A **proposition** is a statement with a truth value. A **stance** is one named
entity's relationship to it: `knows`, `suspects`, or — by having no record at all
— `unaware`.

A lie needs no special machinery. A proposition marked `false` that someone holds
as `knows` is a character who is certain and wrong. Write the falsehood as its own
proposition; do not try to encode the deception on the true one.

Knowers are NPCs, factions, or the PC. **There is no inheritance.** A faction
knowing something says nothing about any member, and you must never play a member
as knowing because their faction does. The brief will show you the gap; closing it
is a scene, not a lookup.

## When to write

Write a stance the moment the fiction moves information, before you narrate:

| What happened | Command |
|---|---|
| Someone witnessed it | `gm-know.sh stance P4 "Mair" knows --source "saw it at the ford"` |
| Someone was told | `gm-know.sh stance P4 "Mair" knows --source "told by Eurgain"` |
| Someone half-caught it | `gm-know.sh stance P4 "Gwen" suspects --source "overheard"` |
| A new secret enters play | `gm-know.sh add "<the claim>" --truth true --about "Rhiannon"` |
| Someone believes a lie | `gm-know.sh add "<the lie>" --truth false` then a `knows` stance on the dupe |
| They were wrong, or it was retconned | `gm-know.sh forget P4 "Mair"` |
| The thread is spent | `gm-know.sh status P4 dormant` |

Before a scene where it matters: `gm-know.sh who-knows "<substring>"` for one
proposition, `gm-know.sh held-by "Mair"` for one person.

**Do not seed a ledger ahead of play.** Same rule as the anti-gazetteer rule for
locations: a proposition exists once it is in play, not because it might be later.

## Reading the block

`--- WHO KNOWS WHAT (present) ---` shows the active propositions relevant to this
room — someone here holds a stance, or the statement is about someone here. The
useful signal is the `unaware` lines. Read them as a list of things the person in
front of the player cannot say, cannot react to, and would be surprised by.

`(FALSE)` beside a statement someone `KNOWS` is the single most playable line in
the block. That character is confident. Play them confident.

A faction line ending `— Mair does not` means the organisation holds something its
own member has not been told. That is a scene waiting to happen, not a bookkeeping
note.

## Narrating the PC's own stances

The player has no view of this ledger, so their character's stances land entirely
in your prose.

- The PC holds `suspects`: never write her as certain. Say the doubt out loud —
  she is fairly sure, though no one has actually told her.
- The PC holds `knows` on a proposition marked `false`: write her as certain, and
  let the world correct her. Do not hedge on her behalf, and do not wink at the
  player.
- The PC is `unaware`: she cannot act on it. If the player acts on it anyway,
  that is the player knowing something their character does not — resolve it in
  the fiction rather than by quietly granting her the knowledge.

## What this does not do

Information does not spread on its own. There is no tick, no propagation along
faction relations, and no roll for spying. Espionage is played out in fiction and
its outcome written here by hand.
```

- [ ] **Step 4: Wire `CLAUDE.md`**

In the **State Persistence** table, add these two rows immediately after the `NPC mood/goal/secret` row:

```markdown
| **Information moved** — someone witnessed, was told, overheard, or was deliberately kept in the dark | `gm-know.sh stance <id> "<who>" knows\|suspects --source "..."` (`add` a new proposition first; a lie is `--truth false` + a `knows` stance) |
| A knowledge thread is spent / retconned | `gm-know.sh status <id> dormant` / `gm-know.sh forget <id> "<who>"` |
```

In the **Action Router** table, add this row after the `Narrate / voice an NPC` row:

```markdown
| Information moves, or an NPC is about to act on something | Who knows what | `gm-knowledge` |
```

In **The living world**, add this bullet immediately after the **World tracks & factions** bullet:

```markdown
- **Who knows what:** `gm-know.sh` records which NPCs, factions and the PC have actually been told a thing. Write a stance the moment information moves, before narrating. The scene brief surfaces the `unaware` lines for whoever is present — read them as what the person in front of the player cannot say. A faction knowing something never means its members do.
```

- [ ] **Step 5: Document the module**

In `docs/modules/living-world.md`, add a section after the faction section. Do not hand-type an OKF stamp — the `okf.mjs` tooling is not installed on this machine, so the body change ships unstamped and the drift is a known work item:

```markdown
## The knowledge ledger (`knowledge.json`)

Threat clocks and world tracks move pressure; factions hold standing and ground.
The knowledge ledger holds the contested half of what is true: who has actually
been told a thing.

A **proposition** is a statement plus a truth value (`true` / `false` /
`unresolved`) and a status (`active` / `dormant`). A **stance** is one named
entity's relationship to it — `knows` or `suspects`. Absence of a stance is
`unaware` and is never stored, so recording ignorance costs nothing.

Deception falls out of the truth value: a `false` proposition someone holds as
`knows` is a character who is certain and wrong. Knowers are NPCs, factions, or
the PC, and there is no inheritance — a faction's stance is never copied to its
members, because a ledger that infers knowledge nobody was given fails at its only
job.

Written with `tools/gm-know.sh`, owned by `lib/knowledge_manager.py`, and surfaced
in the scene brief as `--- WHO KNOWS WHAT (present) ---` for the propositions
relevant to whoever is in the room. Nothing propagates on its own: the GM moves
information, the same way the GM moves a faction standing.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_knowledge_manager.py -q`
Expected: all pass.

- [ ] **Step 7: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: the same 31 baseline failures.

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/gm-knowledge/SKILL.md CLAUDE.md docs/modules/living-world.md tests/test_knowledge_manager.py
git commit -m "gm-knowledge: the skill, the router rows, and the module doc"
```

---

## Plan Self-Review

**Spec coverage.** Requirement 1 → Task 1 `add_proposition`. Requirement 2 → Task 1 `set_stance` plus the touched/since stamping test. Requirement 3 → Task 1 `forget`. Requirement 4 → Task 1 `test_absence_is_unaware_and_is_never_stored`. Requirement 5 → Task 1 `who_knows` / `held_by`, including the ambiguous-substring and id-precedence cases. Requirement 6 → Task 1 `set_status`. Requirement 7 → Task 3 in full, including the silence test across three kits. Requirement 8 → Task 2, every verb with both a CLI and a wrapper test. The spec's kit-agnosticism section is enforced by the Global Constraints and by Task 3's three-kit parametrization. The spec's "player character's stances" section has no code — it is a narration obligation, and it lands in Task 4's Skill.

**Placeholders.** None. Every code step carries the actual code; every test step carries the actual assertions.

**Type consistency.** `pid` is a `str` id everywhere. `session` is an `int` everywhere. `render` returns `str` (empty when nothing qualifies); `relevant` returns `(list[tuple[str, dict]], int)`. `set_stance` / `forget` / `set_status` return `dict | None`; `add_proposition` always returns a `dict` because it cannot fail on a missing id. `who_knows` / `held_by` / `get_propositions` return `dict`. The `held_by` entries carry an extra `stance` key that `get_propositions` entries do not — Task 2's CLI test asserts it and Task 1's `test_held_by_reports_every_proposition_one_entity_holds` pins it.

**Known divergence to watch.** Task 2 and Task 3 both modify `lib/session_manager.py` — Task 2 adds `session_number()` near line 1496, Task 3 inserts the brief block near line 1051. They do not overlap, but Task 3's line anchor will have shifted by the lines Task 2 added, so locate it by the `# --- Pending Consequences ---` comment rather than by number.
