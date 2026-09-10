# Play Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four defects that corrupt campaign state or report wrong numbers during play.

**Architecture:** Four independent small fixes, each in one file, each with the reproduction that found it turned into a regression test. No new modules. Two reuse a pattern the repo already has — `save_character.py`'s `is_dnd5e` gate and `PlayerManager._read_vital`.

**Tech Stack:** Python 3 (stdlib), pytest. Run everything with `uv run python`, never bare `python`.

**Spec:** `docs/superpowers/specs/2026-09-10-untouched-surface-audit.md` — findings V1, V2, V3, V4.

## Global Constraints

- **The engine holds no game's concepts.** Nothing in `lib/` may name a campaign concept, branch on kit identity outside `WorldKit`, or invent a default for something a kit never declared. The single exception is a genuinely `dnd5e` kit, gated exactly the way `features/character-creation/save_character.py:157-166` gates `DND_SHEET_DEFAULTS`.
- **A wrong answer must become a loud refusal, never a quieter wrong answer.** Three of these four defects are silent: they print success, or echo the input, while doing something else. The fix in each case is to fail visibly.
- **Every vital is read through `PlayerManager._read_vital`** (`@staticmethod`, returns `(current, max)`, `max` is `None` for a plain-number track).
- **All file writes use `encoding="utf-8"`** — Windows here, where `open()` defaults to cp1252.
- **Tests never touch the live campaign.** Always `GM_WORLD_STATE_BASE` against a fixture under `tmp_path`. `world-state/campaigns/the-slow-heart/` is real user data.
- **Run the suite as** `uv run python -m pytest -q --continue-on-collection-errors`. Baseline **854 passing / 31 failing**; the failing set must be byte-identical afterwards. This pytest prints **no tally line** — count `^FAILED ` lines. Never gate a commit behind a piped test run: a pipeline exits with its *last* command's status, so `pytest … | tail && git commit` commits on failure. See `docs/gotchas/running-the-suite.md`.

---

## File Structure

| File | Change |
|---|---|
| `lib/dice.py` | Parse strictly: normalise whitespace, `fullmatch`, refuse what it cannot parse. |
| `lib/consequence_manager.py` | Clear the rollback snapshot on a tick that fires nothing. |
| `lib/npc_manager.py` | Gate the party-member sheet's 5e furniture on the kit; carry declared vitals and traits. |
| `lib/validators.py` | Accept every real name; reject only what is actually dangerous. |
| `tests/test_dice_strict_parsing.py` (create) | V1's reproductions. |
| `tests/test_consequence_rollback.py` (create) | V2's reproduction. |
| `tests/test_party_member_kit_sheet.py` (create) | V3's reproduction. |
| `tests/test_validators_names.py` (create) | V4's reproduction. |

Tasks 1 and 4 are independent single-file changes. Task 2 is a four-line change. Task 3 is the largest and touches the most-read renderer, so it goes last.

---

### Task 1: The dice roller must not print arithmetic it did not do

**Files:**
- Modify: `lib/dice.py` — the three patterns (~lines 45-47) and the standard-roll branch (~line 101)
- Test: `tests/test_dice_strict_parsing.py` (create)

**Interfaces:**
- Produces: `DiceRoller.roll(notation)` raises `ValueError` on any notation it cannot parse in full, rather than silently parsing a prefix.

**Why this is first.** `CLAUDE.md` says "the dice are why the world feels real" and instructs `uv run python lib/dice.py "1d20+<total>"`. `match()` accepts a prefix and discards the tail; `format_roll_result` then echoes the *original* notation. So the output asserts arithmetic the total does not contain, and nothing reveals it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dice_strict_parsing.py`:

```python
"""The dice roller must never print a modifier it did not apply.

`simple_pattern.match()` accepted a prefix and dropped the tail, while
format_roll_result echoed the notation as typed. So "1d20 + 5" rolled a bare d20
and printed "1d20 + 5: [20] = 20" — the +5 silently gone — and "1d6+2d8" was
parsed as 1d6+2 with the d8 vanished. CLAUDE.md tells the GM to run this tool by
hand, so a space in the notation was enough.
"""

import pytest

from lib.dice import DiceRoller


@pytest.fixture
def roller():
    return DiceRoller()


def test_spaces_around_the_modifier_still_apply_it(roller):
    """The failure that started this: a space made the +5 disappear."""
    result = roller.roll("1d20 + 5")
    assert result["modifier"] == 5
    assert result["total"] == sum(result["rolls"]) + 5


def test_a_notation_it_cannot_parse_is_refused_not_guessed(roller):
    """1d6+2d8 was silently read as 1d6+2. A loud refusal is the only honest
    answer until multi-group notation is actually supported."""
    with pytest.raises(ValueError):
        roller.roll("1d6+2d8")


@pytest.mark.parametrize("notation", ["1d20 gibberish", "d20+5", "1d20+", "1d20++5", "hello"])
def test_malformed_notation_raises(roller, notation):
    with pytest.raises(ValueError):
        roller.roll(notation)


@pytest.mark.parametrize("notation,expected_mod", [
    ("1d20+5", 5), ("1d20-2", -2), ("1d20", 0),
    ("  1d20+5  ", 5), ("1d20 +5", 5), ("1d20+ 5", 5), ("2d6+3", 3),
])
def test_every_accepted_form_applies_its_modifier(roller, notation, expected_mod):
    result = roller.roll(notation)
    assert result["modifier"] == expected_mod
    assert result["total"] == sum(result["rolls"]) + expected_mod


def test_advantage_keeps_its_modifier_through_whitespace(roller):
    result = roller.roll("2d20kh1 + 3")
    assert result["type"] == "advantage"
    assert result["modifier"] == 3
    assert result["total"] == max(result["rolls"]) + 3


def test_disadvantage_keeps_its_modifier_through_whitespace(roller):
    result = roller.roll("2d20kl1 + 3")
    assert result["type"] == "disadvantage"
    assert result["modifier"] == 3
    assert result["total"] == min(result["rolls"]) + 3


def test_a_zero_sided_die_is_still_refused(roller):
    """Pre-existing guard; must survive the parsing change."""
    with pytest.raises(ValueError):
        roller.roll("1d0")


def test_the_printed_total_matches_the_printed_notation(roller):
    """The whole defect in one assertion: whatever the output echoes, the total
    must contain."""
    from lib.dice import DiceRoller as _D
    result = roller.roll("1d20+7")
    assert str(result["total"]) == str(sum(result["rolls"]) + 7)
    assert result["notation"].replace(" ", "") == "1d20+7"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_dice_strict_parsing.py -q`
Expected: the whitespace and refusal tests fail — `"1d20 + 5"` currently returns `modifier == 0`, and `"1d6+2d8"` returns a result instead of raising.

- [ ] **Step 3: Parse strictly**

In `lib/dice.py`, the three patterns currently read:

```python
        self.simple_pattern = re.compile(r'(\d+)d(\d+)([+-]\d+)?')
        self.advantage_pattern = re.compile(r'(\d+)d(\d+)kh(\d+)([+-]\d+)?')  # keep highest
        self.disadvantage_pattern = re.compile(r'(\d+)d(\d+)kl(\d+)([+-]\d+)?')  # keep lowest
```

Leave the patterns as they are and change **how they are applied**. At the top of `roll()`, replace:

```python
        notation = notation.strip()
```

with:

```python
        # Strip ALL internal whitespace, not just the ends. "1d20 + 5" is the
        # natural spelling of what CLAUDE.md tells the GM to type, and it used to
        # parse as a bare d20 with the +5 silently discarded.
        original = notation
        notation = re.sub(r'\s+', '', notation)
```

Then change every `.match(notation)` in `roll()` to `.fullmatch(notation)` — there are three, one per pattern. And at the end of `roll()`, where no pattern matched, the method must raise rather than fall through. Add this immediately after the standard-roll branch:

```python
        # Nothing matched in full. Refusing is the only honest answer: `match()`
        # used to accept a prefix and drop the tail, so "1d6+2d8" became 1d6+2
        # and the d8 vanished from a total that still printed the original
        # notation. Multi-group notation is a feature, not a parse this can fake.
        raise ValueError(
            f"Unsupported dice notation: {original!r}. "
            "Use NdM, NdM+K, NdM-K, NdMkhK or NdMklK (one dice group)."
        )
```

Keep `result['notation']` set to `original` so the output still echoes what the caller typed — that is now safe, because the two can no longer disagree.

**Before you finish, check every caller.** `grep -rn "DiceRoller\|dice.py" lib/ tools/ features/ .claude/ tests/` and confirm nothing relies on the old lenient behaviour — in particular that no caller passes a notation this now rejects. If one does, report it rather than loosening the parser.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_dice_strict_parsing.py -q`
Expected: all pass.

- [ ] **Step 5: Check it by hand, the way the GM would**

Run each of these and paste the output into your report:

```bash
export PYTHONIOENCODING=utf-8
for n in "1d20+5" "1d20 + 5" "1d20-2" "3d6" "2d20kh1+3" "1d6+2d8"; do uv run python lib/dice.py "$n"; done
```

Expected: the first five roll correctly with their modifiers applied; `1d6+2d8` prints a clear error. Note whether the error is readable — this is the surface a human reads mid-scene.

- [ ] **Step 6: Confirm no regression, then commit**

```bash
git add lib/dice.py tests/test_dice_strict_parsing.py
git commit -m "dice: parse in full or refuse, so a printed modifier is always applied"
```

---

### Task 2: A tick that fires nothing is not a beat to roll back

**Files:**
- Modify: `lib/consequence_manager.py` — the `if expired or fired:` block at ~line 251
- Test: `tests/test_consequence_rollback.py` (create)

**Interfaces:** none produced.

`tick()` writes `data['_snapshot']` and calls `save_json` **only** inside `if expired or fired:`. A tick that fires nothing therefore leaves the previous beat's snapshot in place and saves nothing, so a later `rollback_last()` restores that stale snapshot and discards everything added since — while printing `[SUCCESS]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_consequence_rollback.py`:

```python
"""rollback must never destroy state it did not create.

tick() wrote its rollback snapshot only when something expired or fired, so a
tick that fired nothing left the previous beat's snapshot in place. A later
rollback restored it, discarding every consequence added in between — and
reported [SUCCESS] while doing so.
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
    (campaign / "ruleset.json").write_text(json.dumps(
        {"name": "custom", "stat_schema": {"attributes": ["might"], "vitals": ["hp"]},
         "progression": {"model": "milestone"}}), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(json.dumps(
        {"player_position": {"current_location": "Cwm Bedd"}}), encoding="utf-8")
    return world, campaign


def _run(world, *args):
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "gm-consequence.sh"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)}, cwd=str(REPO_ROOT))


def _active(campaign):
    data = json.loads((campaign / "consequences.json").read_text(encoding="utf-8"))
    return [c.get("consequence") for c in data.get("active", [])]


def test_a_no_op_tick_does_not_leave_a_stale_rollback_snapshot(tmp_path):
    """The exact sequence that destroyed two consequences."""
    world, campaign = _world(tmp_path)
    _run(world, "add", "The bell tolls", "on arrival",
         "--trigger-type", "on_location", "--match", "Cwm Bedd")
    _run(world, "tick")                      # fires — writes a snapshot
    _run(world, "add", "A second thing", "later")
    _run(world, "add", "A third thing", "later still")
    assert len(_active(campaign)) == 3

    _run(world, "tick")                      # fires nothing
    proc = _run(world, "rollback")

    # Either it refuses, or it rolls back to the state before the LAST tick.
    # What it must never do is silently drop the two additions.
    assert "A second thing" in _active(campaign), proc.stdout + proc.stderr
    assert "A third thing" in _active(campaign), proc.stdout + proc.stderr


def test_a_no_op_tick_reports_nothing_to_roll_back(tmp_path):
    world, campaign = _world(tmp_path)
    _run(world, "add", "The bell tolls", "on arrival",
         "--trigger-type", "on_location", "--match", "Cwm Bedd")
    _run(world, "tick")
    _run(world, "tick")                      # fires nothing — clears the snapshot
    proc = _run(world, "rollback")
    assert proc.returncode != 0
    assert "No reactive beat" in (proc.stdout + proc.stderr)


def test_rollback_immediately_after_a_firing_tick_still_works(tmp_path):
    """The feature must survive the fix."""
    world, campaign = _world(tmp_path)
    _run(world, "add", "The bell tolls", "on arrival",
         "--trigger-type", "on_location", "--match", "Cwm Bedd")
    before = _active(campaign)
    _run(world, "tick")
    proc = _run(world, "rollback")
    assert proc.returncode == 0, proc.stderr
    assert _active(campaign) == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_consequence_rollback.py -q`
Expected: the first two fail — the additions are destroyed and rollback reports success.

- [ ] **Step 3: Clear the stale snapshot**

In `lib/consequence_manager.py`, the tick's write currently ends:

```python
        if expired or fired:
            ...                                   # provenance, snapshot, etc.
            self.json_ops.save_json(self.consequences_file, data)
        return {
```

Insert an `elif` between that block's end and the `return`, so it reads:

```python
        if expired or fired:
            ...                                   # unchanged
            self.json_ops.save_json(self.consequences_file, data)
        elif data.get('_snapshot'):
            # A tick that fires nothing is not a beat. Leaving the previous
            # beat's snapshot in place made `rollback` restore it and discard
            # everything added since — two consequences destroyed under a
            # [SUCCESS] line. Only write when there is something stale to clear,
            # so the common no-op tick still costs no disk I/O.
            data['_snapshot'] = None
            self.json_ops.save_json(self.consequences_file, data)
        return {
```

Note the alternative considered and rejected: refreshing the snapshot on *every* tick would make rollback always lossless but would turn the common no-op tick into a write on every move and every time advance. Clearing is cheaper and gives the honest answer — there was no beat, so there is nothing to undo.

- [ ] **Step 4: Run the tests to verify they pass, then the suite**

- [ ] **Step 5: Commit**

```bash
git add lib/consequence_manager.py tests/test_consequence_rollback.py
git commit -m "consequence: a tick that fires nothing clears the rollback snapshot"
```

---

### Task 3: Widen the name validator to every real name, and narrow it to what is dangerous

**Files:**
- Modify: `lib/validators.py` — `validate_name` (~line 36)
- Test: `tests/test_validators_names.py` (create)

**Interfaces:** none produced; the signature is unchanged.

`^[a-zA-Z0-9\s\-']+$` rejects any non-ASCII letter and any period. `NPCManager.create_batch` — the import path — does not call the validator, so extraction creates such NPCs freely; every runtime verb calls it first and refuses. The result is an NPC the world contains and the tools cannot touch.

The alphabet was never the point. What a validator here must actually stop is a name that could escape a JSON key into a path or a control sequence.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validators_names.py`:

```python
"""A name the importer accepts must be a name the runtime can write to.

validate_name's ASCII-only alphabet rejected any diacritic and any period, but
NPCManager.create_batch (the import path) never called it — so extraction created
NPCs that every runtime verb then refused. The campaign contained a character the
tools could not touch.

The alphabet was never the point. The validator exists to stop a name escaping a
JSON key into a path or a control sequence.
"""

import pytest

from lib.validators import Validators


@pytest.fixture
def v():
    return Validators()


@pytest.mark.parametrize("name", [
    "Eurgain", "Cadwal", "Nant Ddu", "Y Bleiddiaid",       # the live campaign
    "Bran ap Llŷr", "Ffraid", "Myrddin",                    # Welsh, this setting
    "Père Anselme", "Zoë", "Núñez", "Þórr",                 # other diacritics
    "St. Cuthbert", "Mr. Wednesday",                        # periods
    "O'Brien", "Jean-Luc", "Mordecai the 3rd",              # already allowed
])
def test_every_real_name_is_accepted(v, name):
    ok, err = v.validate_name(name)
    assert ok, f"{name!r} rejected: {err}"


@pytest.mark.parametrize("name", [
    "../../etc/passwd", "a/b", "a\\b", "a\x00b", "a\nb", "a\tb",
    "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b",
])
def test_what_is_actually_dangerous_is_refused(v, name):
    ok, _ = v.validate_name(name)
    assert not ok, f"{name!r} should be refused"


@pytest.mark.parametrize("name", ["", "   ", None])
def test_empty_is_still_refused(v, name):
    ok, _ = v.validate_name(name)
    assert not ok


def test_over_length_is_still_refused(v):
    ok, _ = v.validate_name("x" * 101)
    assert not ok


def test_the_importer_and_the_runtime_now_agree(tmp_path):
    """create_batch creates without validating; every runtime verb validates.
    A name one accepts and the other refuses is the defect."""
    import json
    from lib.npc_manager import NPCManager
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / "probe"
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps({"name": "custom"}), encoding="utf-8")
    (campaign / "npcs.json").write_text("{}", encoding="utf-8")

    m = NPCManager(str(world))
    m.create_batch([{"name": "Bran ap Llŷr", "description": "a bard",
                     "attitude": "neutral"}])
    assert m.update_npc("Bran ap Llŷr", "sang at the ford") is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_validators_names.py -q`
Expected: the diacritic and period cases fail, and the last test fails at `update_npc`.

- [ ] **Step 3: Replace the alphabet with a denylist**

In `lib/validators.py`, replace:

```python
        # Check characters
        pattern = r"^[a-zA-Z0-9\s\-']+$"
        if not re.match(pattern, name):
            return False, "Invalid name. Use only letters, numbers, spaces, hyphens, and apostrophes"
```

with:

```python
        # Reject what is dangerous, not what is unfamiliar.
        #
        # The old rule was an ASCII allowlist, so it refused every diacritic and
        # every period — while NPCManager.create_batch, the import path, never
        # called this at all. Extraction therefore created NPCs (Bran ap Llŷr,
        # St. Cuthbert) that every runtime verb then refused to touch, which is
        # how a campaign ends up containing a character its own tools cannot
        # write to. A Welsh or French name is not a security problem.
        #
        # What a name must not do is escape a JSON key into a filesystem path or
        # a terminal control sequence, so those are what this refuses.
        if _NAME_FORBIDDEN.search(name):
            return False, ("Invalid name: cannot contain path separators, "
                           "control characters, or any of : * ? \" < > |")
```

and add this module-level constant beside the other module-level definitions at the top of the file:

```python
# Path separators, the Windows-illegal filename set, and C0 control characters.
# Everything else — letters in any script, digits, spaces, hyphens, apostrophes,
# periods, commas — is a legitimate name somewhere.
_NAME_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]")
```

Keep the empty check and the length check exactly as they are. Confirm `re` is already imported at module level.

**Then check the blast radius.** `grep -rn "validate_name" lib/ tools/ features/` and confirm no caller depends on the ASCII guarantee — in particular that nothing turns a validated name straight into a filename without slugifying. `lib/campaign_manager.py` slugifies campaign names separately; report what you find for locations and NPCs.

- [ ] **Step 4: Run the tests, then the suite**

`tests/test_slug_unify.py` and any location test are the ones most likely to notice; both must stay green.

- [ ] **Step 5: Commit**

```bash
git add lib/validators.py tests/test_validators_names.py
git commit -m "validators: accept every real name, refuse only what is dangerous"
```

---

### Task 4: The party-member sheet asks the kit

**Files:**
- Modify: `lib/npc_manager.py` — `PARTY_MEMBER_DEFAULTS` (~line 20) and `_party_sheet_for_npc` (~line 48)
- Test: `tests/test_party_member_kit_sheet.py` (create)

**Interfaces:**
- Consumes: `lib/world_kit.py` — `WorldKit(world_state_dir).kit() -> str`, `.vitals() -> List[str]`, `.traits() -> List[str]`.
- Consumes: `PlayerManager._read_vital(char, vital) -> (current, max)`.

This is the eleventh instance of the invented-5e-field family and the one that reaches furthest: `gm-player.sh become` copies a party sheet into `character.json`, so the Death Protocol hand-off makes the next PC a "Level 1 Unknown Commoner, AC 10" in a world with none of those concepts.

It goes last because it touches the most-read renderer, and because Tasks 1-3 landing first means a regression here is easy to bisect.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_party_member_kit_sheet.py`:

```python
"""A party member's sheet must hold what the kit declares, not a 5e template.

PARTY_MEMBER_DEFAULTS hardcoded race "Unknown", class "Commoner", ac 10, six 5e
ability scores, saves, attack_bonus, damage and xp, with no kit gate — and
gm-player.sh become copies that sheet into character.json, so the Death Protocol
hand-off produced a "Level 1 Unknown Commoner, AC 10" PC on any world.
"""

import json

import pytest

from lib.npc_manager import NPCManager

CUSTOM = {
    "name": "custom",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp", "blood"],
                    "traits": ["generation"]},
    "progression": {"model": "milestone"},
}
DND5E = {
    "name": "dnd5e",
    "stat_schema": {"attributes": ["str", "dex", "con", "int", "wis", "cha"],
                    "vitals": ["hp"]},
    "progression": {"model": "xp-levels"},
}


def _world(tmp_path, ruleset, npcs):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / "probe"
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (campaign / "npcs.json").write_text(json.dumps(npcs), encoding="utf-8")
    return str(world), campaign


def _sheet(campaign, name):
    data = json.loads((campaign / "npcs.json").read_text(encoding="utf-8"))
    return data[name].get("character_sheet", {})


def test_a_custom_kit_gets_no_5e_furniture(tmp_path):
    world, campaign = _world(tmp_path, CUSTOM, {
        "Grimjaw": {"description": "a smith", "attitude": "neutral"}})
    assert NPCManager(world).promote_to_party_member("Grimjaw") is True
    sheet = _sheet(campaign, "Grimjaw")
    for invented in ("race", "class", "ac", "saves", "attack_bonus", "damage", "xp"):
        assert invented not in sheet, f"{invented} invented on a custom kit"


def test_a_custom_kit_still_gets_the_universals(tmp_path):
    world, campaign = _world(tmp_path, CUSTOM, {
        "Grimjaw": {"description": "a smith", "attitude": "neutral"}})
    NPCManager(world).promote_to_party_member("Grimjaw")
    sheet = _sheet(campaign, "Grimjaw")
    assert sheet["level"] == 1
    assert sheet["hp"] == {"current": 10, "max": 10}
    assert sheet["conditions"] == []


def test_a_dnd5e_kit_still_gets_its_whole_sheet(tmp_path):
    world, campaign = _world(tmp_path, DND5E, {
        "Sildar": {"description": "a knight", "attitude": "friendly"}})
    NPCManager(world).promote_to_party_member("Sildar")
    sheet = _sheet(campaign, "Sildar")
    assert sheet["race"] == "Unknown"
    assert sheet["class"] == "Commoner"
    assert sheet["ac"] == 10
    assert sheet["xp"] == 0
    assert set(sheet["stats"]) == {"str", "dex", "con", "int", "wis", "cha"}


def test_a_declared_vital_the_npc_carries_is_kept(tmp_path):
    world, campaign = _world(tmp_path, CUSTOM, {
        "Mair": {"description": "a weaver", "attitude": "neutral", "blood": 4}})
    NPCManager(world).promote_to_party_member("Mair")
    assert _sheet(campaign, "Mair")["blood"] == 4


def test_a_declared_trait_the_npc_carries_is_kept(tmp_path):
    world, campaign = _world(tmp_path, CUSTOM, {
        "Mair": {"description": "a weaver", "attitude": "neutral", "generation": 6}})
    NPCManager(world).promote_to_party_member("Mair")
    assert _sheet(campaign, "Mair")["generation"] == 6


def test_the_party_block_renders_a_kit_sheet_without_crashing(tmp_path):
    """format_party_status indexes hp as a dict in several places."""
    world, campaign = _world(tmp_path, CUSTOM, {
        "Grimjaw": {"description": "a smith", "attitude": "neutral"}})
    m = NPCManager(world)
    m.promote_to_party_member("Grimjaw")
    out = m.format_party_status()
    assert "Grimjaw" in out
    assert "Commoner" not in out
    assert "AC" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_party_member_kit_sheet.py -q`
Expected: the custom-kit tests fail — every invented field is present.

- [ ] **Step 3: Split the defaults and gate the 5e half**

In `lib/npc_manager.py`, replace the single `PARTY_MEMBER_DEFAULTS` dict with two, mirroring how `features/character-creation/save_character.py` separates universals from `DND_SHEET_DEFAULTS`:

```python
# Universals: every world has a body, a place in some progression, and things
# that can happen to it. These are safe on any kit.
PARTY_MEMBER_DEFAULTS = {
    "level": 1,
    "hp": {"current": 10, "max": 10},
    "skills": {},
    "equipment": [],
    "features": [],
    "conditions": [],
}

# 5e sheet furniture. Applied ONLY when the active kit is genuinely dnd5e, the
# same gate save_character.py uses for DND_SHEET_DEFAULTS. Without it, promoting
# an NPC on a world with no classes produced a "Level 1 Unknown Commoner, AC 10"
# — and gm-player.sh become copies that sheet into character.json, so the Death
# Protocol hand-off made it the player's next character.
DND_PARTY_DEFAULTS = {
    "race": "Unknown",
    "class": "Commoner",
    "ac": 10,
    "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "saves": {"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0},
    "attack_bonus": 2,
    "damage": "1d6",
    "xp": 0,
}
```

Then in `_party_sheet_for_npc`, after the existing `sheet = copy.deepcopy(PARTY_MEMBER_DEFAULTS)`, add the kit-driven half. Read the function in full first — it already copies `hp`/`ac` from `npc.stats` "when real", and that logic must keep working for a 5e kit:

```python
    kit = WorldKit(world_state_dir)
    if kit.kit() == 'dnd5e':
        sheet.update(copy.deepcopy(DND_PARTY_DEFAULTS))
    # Whatever the kit declares and the NPC record actually carries rides along,
    # so a follower on a world with `blood` and `generation` keeps them instead
    # of being handed six ability scores it has no use for.
    for name in list(kit.vitals()) + list(kit.traits()):
        if name != 'hp' and name in npc:
            sheet[name] = copy.deepcopy(npc[name])
```

`_party_sheet_for_npc` is currently a module-level function taking only `npc`, so it needs the world-state dir threaded in. Find its caller (`promote_to_party_member`) and pass `self._wsd`, or make it a method — **read both before choosing, and say in your report which you did and why.** Import `WorldKit` at module level; `lib/npc_manager.py` does not currently import it.

- [ ] **Step 4: Fix the renderers that index hp as a dict**

The spec records five crash sites in this file where HP is indexed as a nested dict: `format_npc_status` (~:240), `promote_to_party_member` (~:509,512), `update_npc_hp` (~:570-583), `set_npc_stat` (~:628-631), `format_party_status` (~:769-783). Route each through `PlayerManager._read_vital`, and write back in the shape the sheet already uses:

```python
        if isinstance(sheet.get('hp'), dict):
            sheet['hp']['current'] = new_hp
        else:
            sheet['hp'] = new_hp
```

Also make the 5e furniture render conditionally in `format_npc_status` and `format_party_status` — `AC: {sheet.get('ac', 10)}` and `Level … {race} {class}` must not print a value the sheet does not carry. `lib/session_manager.py`'s party-member block was fixed for exactly this and is the pattern to copy: `hp` renders as the literal `HP:`, every other declared vital goes through `character_schema.stat_label`, and furniture appears only when present.

If Step 4 turns out to be larger than the rest of the task combined, **stop and report** rather than half-doing it — it can become its own task.

- [ ] **Step 5: Run the tests, then the suite**

Run: `uv run python -m pytest tests/test_party_member_kit_sheet.py tests/test_npc_manager.py -q` if that second file exists, then the full suite.

- [ ] **Step 6: Verify the Death Protocol path by hand**

Promote an NPC on a custom kit, then run `gm-player.sh become` against a fixture and show the resulting `character.json`. It must not contain `race`, `class`, `ac` or `xp`. Paste it into your report.

- [ ] **Step 7: Commit**

```bash
git add lib/npc_manager.py tests/test_party_member_kit_sheet.py
git commit -m "npc: the party sheet asks the kit instead of assuming a 5e commoner"
```

---

## Plan Self-Review

**Spec coverage.** V1 → Task 1. V2 → Task 2. V4 → Task 3. V3 → Task 4, which also absorbs the scalar-hp crash sites the spec lists in the same file because they are unavoidable once the sheet stops guaranteeing a dict.

**Placeholders.** None. Every step carries the code or the assertions. Task 4 Step 3 deliberately does not paste `_party_sheet_for_npc` in full — its existing "copy hp/ac from npc.stats when real" logic must survive, and pasting a body I have not verified line by line is how earlier plans in this repo shipped defects. The instruction is to read it first and report the choice made.

**Type consistency.** `roll()` returns the same dict shape and now raises `ValueError` instead of falling through. `validate_name` keeps `(bool, Optional[str])`. `_read_vital` returns `(current, max)` with `max` possibly `None`, and every new call site handles `None` before formatting. `kit.vitals()` and `kit.traits()` both return `List[str]`.

**Known risks.**
- Task 1 makes the parser stricter, so a caller passing something previously tolerated will now raise. Step 3 requires a caller sweep before finishing.
- Task 3 widens what `validate_name` accepts, so anything downstream turning a name into a filename without slugifying becomes reachable with a new character set. Step 3 requires that sweep too.
- Task 4 is the only task that changes what a live campaign's `npcs.json` will contain on the next promote. It does not migrate existing sheets — an already-promoted 5e-shaped party member keeps its fields, and the renderers must tolerate that. Say so if any test suggests otherwise.
