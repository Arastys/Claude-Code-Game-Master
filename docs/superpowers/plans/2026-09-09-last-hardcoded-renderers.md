# The Last Hardcoded Renderers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the last five places where the engine renders a character as if every world were D&D, or crashes on a world that is not.

**Architecture:** No new modules. Every fix reuses machinery that already exists and is already tested — `WorldKit.vitals()` / `.traits()`, `PlayerManager._read_vital`, `character_schema.stat_label`, and the `is_dnd5e` gate `save_character.py` already uses for 5e sheet furniture. The one genuinely new thing is test coverage for `tools/gm-statusline.sh`, which has none at all today.

**Tech Stack:** Python 3 (stdlib), bash + jq, pytest. Run everything with `uv run python`, never bare `python`.

**Spec:** `docs/superpowers/specs/2026-09-08-kit-driven-character-and-time-scale.md`, section "Deferred follow-ups (found during this plan, ruled out of its scope)". That section names four of the five sites; the fifth (`show_player` / `show_all_players` base lines) is the same defect family, found while scoping this plan, and Task 2 covers it.

## Global Constraints

- **The engine holds no game's concepts.** Nothing in `lib/` or `tools/` may name a campaign concept, branch on kit identity except through `WorldKit`, or invent a default for something a kit never declared. A fix that special-cases one world repeats the mistake being deleted.
- **5e sheet furniture — `ac`, `gold`, `xp`, `race`, `class` — renders only when the sheet actually carries it.** No `?` placeholders, no invented zeros, no `Unknown` / `Commoner` stand-ins. The single exception is a genuine `dnd5e` kit, gated exactly the way `features/character-creation/save_character.py:157-166` gates `DND_SHEET_DEFAULTS`.
- **Every vital is read through `PlayerManager._read_vital`.** It is a `@staticmethod` at `lib/player_manager.py:539` returning `(current, max)`, with `max` `None` for a plain-number track. Direct `char['hp']['current']` indexing is the crash this plan exists to delete.
- **Labels come from `character_schema.stat_label`.** It is the shared helper; a fourth casing convention is a defect.
- **All file writes use `encoding="utf-8"`.** Windows here, where `open()` defaults to cp1252.
- **Run the suite as** `uv run python -m pytest -q --continue-on-collection-errors`. `tests/test_reset_archive.py` cannot be collected on Windows (`os.geteuid` is POSIX-only) and aborts the run otherwise. Baseline is **31 failed / 791 passed**; the failing set must be byte-identical when you finish. **This pytest prints no final tally line** — count `^FAILED ` lines, never infer.

---

## File Structure

| File | Change |
|---|---|
| `lib/player_manager.py` | `revive` stops assuming dict-shaped hp; `show_player` / `show_all_players` base lines become kit-driven via a new `_identity_line` helper. |
| `lib/identity_onboarding.py` | `from_canon` stops inventing an armour class; gated on the `self._is_dnd5e` flag the class already computes. |
| `lib/session_manager.py` | The party-member block stops inventing four defaults and stops crashing on scalar hp. |
| `tools/gm-statusline.sh` | The HUD renders what the kit declares; gains `GM_WORLD_STATE_BASE` support so it is testable at all. |
| `tests/test_kit_driven_character_block.py` | Extended — it already owns "the engine must not invent 5e fields" tests. |
| `tests/test_statusline.py` (create) | First coverage for the HUD. |

---

### Task 1: Two crashes and one invented armour class

Two small defensive fixes of the same shape, batched into one task: both are "this code assumed a 5e sheet", both are a handful of lines, and a reviewer would accept or reject them together.

**Files:**
- Modify: `lib/player_manager.py` — `revive`, the `max_hp` block
- Modify: `lib/identity_onboarding.py` — `from_canon`'s returned `vitals` dict
- Test: `tests/test_kit_driven_character_block.py`

**Interfaces:**
- Consumes: `PlayerManager._read_vital(char, vital) -> (current, max)` (`lib/player_manager.py:539`, `@staticmethod`, `max` is `None` for a scalar track); `IdentityOnboarding._is_dnd5e` (`lib/identity_onboarding.py:40`, a bool set in `__init__`).
- Produces: `IdentityOnboarding._canon_vitals(sheet) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_kit_driven_character_block.py`:

```python
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
```

Add this module-level constant beside the file's existing rulesets:

```python
SCALAR_KIT = {
    "name": "custom",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_kit_driven_character_block.py -q -k "revive or from_canon"`
Expected: `AttributeError: 'int' object has no attribute 'get'` on the scalar-hp revive; assertion failures on the `ac` tests.

- [ ] **Step 3: Fix `revive`**

In `lib/player_manager.py`, replace this block:

```python
        max_hp = char.get('hp', {}).get('max', 0)
        new_hp = max(1, 1 if hp is None else hp)   # never alive at 0
        if max_hp:
            new_hp = min(new_hp, max_hp)
        char.setdefault('hp', {})
        char['hp']['current'] = new_hp
```

with:

```python
        _, max_hp = self._read_vital(char, 'hp')
        new_hp = max(1, 1 if hp is None else hp)   # never alive at 0
        if max_hp:
            new_hp = min(new_hp, max_hp)
        # Write back in the shape the sheet already uses. The old code assumed a
        # dict — `.get('max')` raised AttributeError on a kit that models hp as a
        # bare number, and the item assignment would have raised TypeError right
        # after — so on such a kit a dead character could never be revived.
        if isinstance(char.get('hp'), dict):
            char['hp']['current'] = new_hp
        else:
            char['hp'] = new_hp
```

- [ ] **Step 4: Fix `from_canon`**

In `lib/identity_onboarding.py`, replace this line inside the returned dict:

```python
            "vitals": {"hp": copy.deepcopy(sheet.get("hp", _default_vitals()["hp"])), "ac": sheet.get("ac", 10)},
```

with:

```python
            "vitals": self._canon_vitals(sheet),
```

and add this method to the same class, immediately above `from_canon`:

```python
    def _canon_vitals(self, sheet: Dict[str, Any]) -> Dict[str, Any]:
        """hp always; ac only when the sheet carries one, or on a 5e kit.

        The old unconditional `sheet.get("ac", 10)` gave an armour class to every
        canon NPC lifted into the PC slot, including on worlds that have no such
        concept. Same defect family as save_character.py's DND_SHEET_DEFAULTS, and
        gated the same way — through the kit, never through a name.
        """
        vitals = {"hp": copy.deepcopy(sheet.get("hp", _default_vitals()["hp"]))}
        if "ac" in sheet:
            vitals["ac"] = sheet["ac"]
        elif self._is_dnd5e:
            vitals["ac"] = 10
        return vitals
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_kit_driven_character_block.py -q`
Expected: all pass.

- [ ] **Step 6: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: 31 failures, the same 31. Count `^FAILED ` lines.

- [ ] **Step 7: Commit**

```bash
git add lib/player_manager.py lib/identity_onboarding.py tests/test_kit_driven_character_block.py
git commit -m "kit-render: revive survives scalar hp, from_canon stops inventing an armour class"
```

---

### Task 2: The two Python render surfaces

**Files:**
- Modify: `lib/player_manager.py` — `show_player` (~line 185) and `show_all_players` (~line 203)
- Modify: `lib/session_manager.py` — the party-member loop (~line 975)
- Test: `tests/test_kit_driven_character_block.py`

**Interfaces:**
- Consumes from Task 1: nothing.
- Consumes: `PlayerManager._read_vital` (`@staticmethod`), `PlayerManager._kit_vitals() -> List[str]`, `PlayerManager._vitals_summary(char) -> str` (already skips `hp`), `character_schema.stat_label(name) -> str`, `WorldKit(world_state_dir).vitals()`.
- Produces: `PlayerManager._identity_line(char, fallback_name='Unknown') -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_kit_driven_character_block.py`:

```python
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
    assert "Commoner" not in ctx
    assert "Unknown" not in ctx
    assert "AC:" not in ctx
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
```

Label casing, so nobody invents a fourth convention: `hp` renders as the literal
`HP:` and every other vital goes through `stat_label`, which is exactly what the
CHARACTER block does at `lib/session_manager.py:924-935`. `stat_label("hp")` would
give `Hp`, which is why hp is handled before the loop there and must be here too.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_kit_driven_character_block.py -q -k "show_ or party_members"`
Expected: assertion failures on `"?"`, `Gold`, `Commoner`, and a `TypeError`/`AttributeError` from the scalar-hp party sheet.

- [ ] **Step 3: Add the shared identity helper and rewrite the two show lines**

In `lib/player_manager.py`, add this method to `PlayerManager`, immediately above `show_player`:

```python
    def _identity_line(self, char: Dict, fallback_name: str = 'Unknown') -> str:
        """'Rhiannon - Level 0 Brythonic' — name, level, then whatever identity
        fields the sheet actually carries.

        Race and class are 5e furniture and are printed only when present. The old
        base line hardcoded '?' for both, so a world without classes advertised a
        missing one on every `gm-player.sh show`. Mirrors the CHARACTER brief's
        assembly in session_manager so the two surfaces cannot drift.
        """
        line = f"{char.get('name', fallback_name)} - Level {char.get('level', 1)}"
        for key in ('race', 'class'):
            if char.get(key):
                line += f" {char[key]}"
        return line

    def _detail_segments(self, char: Dict) -> str:
        """' (HP: 30/30, Gold: 12)' — HP when the kit declares it or the sheet
        carries it, gold only when the sheet actually has it, and never a value
        the declared-vitals summary is already going to print."""
        declared = self._kit_vitals()
        details = []
        if 'hp' in declared or 'hp' in char:
            current, maximum = self._read_vital(char, 'hp')
            details.append(
                f"HP: {current}/{maximum}" if maximum is not None else f"HP: {current}")
        if 'gold' in char and 'gold' not in declared:
            details.append(f"Gold: {char['gold']}")
        return f" ({', '.join(details)})" if details else ""
```

Then replace the `show_player` body's summary construction:

```python
        hp_cur, hp_max = self._read_vital(char, 'hp')
        hp_str = f"{hp_cur}/{hp_max}" if hp_max is not None else f"{hp_cur}"
        gold = char.get('gold', 0)
        summary = f"{char.get('name', name)} - {char.get('race', '?')} {char.get('class', '?')} Level {char.get('level', 1)} (HP: {hp_str}, Gold: {gold})"
        summary += self._vitals_summary(char)
```

with:

```python
        summary = self._identity_line(char, name) + self._detail_segments(char)
        summary += self._vitals_summary(char)
```

And in `show_all_players`, replace:

```python
        hp_cur, hp_max = self._read_vital(char, 'hp')
        hp_str = f"{hp_cur}/{hp_max}" if hp_max is not None else f"{hp_cur}"
        gold = char.get('gold', 0)
        return [
            f"{char.get('name', 'Unknown')} - {char.get('race', '?')} {char.get('class', '?')} Level {char.get('level', 1)} (HP: {hp_str}, Gold: {gold})"
            + self._vitals_summary(char)
```

with:

```python
        return [
            self._identity_line(char) + self._detail_segments(char)
            + self._vitals_summary(char)
```

Leave everything after those lines in both methods exactly as it is — the status and conditions suffixes are already correct.

- [ ] **Step 4: Rewrite the party-member line**

In `lib/session_manager.py`, replace the body of the `for npc_name, npc_data in shown_party:` loop down to and including its `lines.append(f"{npc_name} (Lvl ...")` statement:

```python
            for npc_name, npc_data in shown_party:
                sheet = npc_data.get('character_sheet', {})
                hp = sheet.get('hp', {'current': 10, 'max': 10})
                ac = sheet.get('ac', 10)
                level = sheet.get('level', 1)
                race = sheet.get('race', 'Unknown')
                cls = sheet.get('class', 'Commoner')
                conditions = sheet.get('conditions', [])
                cond_str = f" [{', '.join(conditions)}]" if conditions else ""
                desc = self._truncate(npc_data.get('description', ''), 180, full)

                lines.append(f"{npc_name} (Lvl {level} {race} {cls}) HP: {hp['current']}/{hp['max']} AC: {ac}{cond_str}")
```

with:

```python
            from player_manager import PlayerManager
            from character_schema import stat_label
            declared = WorldKit(self._wsd).vitals()
            for npc_name, npc_data in shown_party:
                sheet = npc_data.get('character_sheet', {})
                # Identity: level always, race and class only when the sheet
                # carries them. 'Unknown' and 'Commoner' were invented — on a world
                # with no classes every follower was reported as a Commoner.
                ident = f"Lvl {sheet.get('level', 1)}"
                for key in ('race', 'class'):
                    if sheet.get(key):
                        ident += f" {sheet[key]}"

                # Declared vitals, read through the shared helper so a kit that
                # models a track as a plain number does not crash the brief. hp is
                # special-cased to the literal "HP" and everything else goes
                # through stat_label — the same split the CHARACTER block makes at
                # session_manager.py:924-935, because stat_label("hp") is "Hp".
                rendered = set()
                segments = []
                if 'hp' in declared or 'hp' in sheet:
                    current, maximum = PlayerManager._read_vital(sheet, 'hp')
                    segments.append(f"HP: {current}/{maximum}" if maximum is not None
                                    else f"HP: {current}")
                    rendered.add('hp')
                for vital in declared:
                    if vital in rendered or vital not in sheet:
                        continue
                    current, maximum = PlayerManager._read_vital(sheet, vital)
                    label = stat_label(vital)
                    segments.append(f"{label}: {current}/{maximum}" if maximum is not None
                                    else f"{label}: {current}")
                    rendered.add(vital)
                if 'ac' in sheet and 'ac' not in rendered:
                    segments.append(f"AC: {sheet['ac']}")

                conditions = sheet.get('conditions', [])
                cond_str = f" [{', '.join(conditions)}]" if conditions else ""
                desc = self._truncate(npc_data.get('description', ''), 180, full)

                head = f"{npc_name} ({ident})"
                if segments:
                    head += " " + " ".join(segments)
                lines.append(f"{head}{cond_str}")
```

`WorldKit` is already imported at `lib/session_manager.py:21`; `self._wsd` is the world-state dir this manager was built with.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_kit_driven_character_block.py tests/test_kit_vitals.py tests/test_get_full_context.py -q`
Expected: all pass.

- [ ] **Step 6: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: the same 31 failures.

- [ ] **Step 7: Commit**

```bash
git add lib/player_manager.py lib/session_manager.py tests/test_kit_driven_character_block.py
git commit -m "kit-render: gm-player.sh show and the party block ask the kit"
```

---

### Task 3: The HUD

`tools/gm-statusline.sh` is the always-on heads-up display, re-run after every assistant message. It is the surface the player looks at most, it still prints `?` for race, class and AC and a `0gp` for worlds without coin, and it has **no test coverage at all**.

It is also currently untestable: it anchors on its own location (`ROOT=.../..`) and reads `$ROOT/world-state/...` directly, so a test cannot point it at a fixture. Adding `GM_WORLD_STATE_BASE` support is therefore part of the fix, not scope creep — it is the same one-line resolution `tools/common.sh:48` already uses.

**Files:**
- Modify: `tools/gm-statusline.sh`
- Test: `tests/test_statusline.py` (create)

**Interfaces:**
- Consumes: nothing from Tasks 1 and 2.
- Produces: nothing consumed later.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_statusline.py`:

```python
"""Tests for the always-on HUD.

`tools/gm-statusline.sh` had no coverage at all, which is how it stayed a
hardcoded 5e template through three plans that made every other character
surface kit-driven. It runs after every assistant message, so it is the most
visible renderer in the system and was the last one inventing placeholders.
"""

import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _run(world):
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "gm-statusline.sh")],
        input="{}", capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    return ANSI.sub("", proc.stdout)


def _world(tmp_path, slug, ruleset, character, overview=None):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / slug
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text(slug, encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (campaign / "character.json").write_text(json.dumps(character), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(
        json.dumps(overview or {"player_position": {"current_location": "Cwm Bychan"}}),
        encoding="utf-8")
    return world


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


def test_the_hud_honours_gm_world_state_base(tmp_path):
    """Without this the HUD reads the developer's live campaign during tests."""
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}}))
    assert "Rhiannon" in out


def test_the_hud_invents_no_placeholders_on_a_custom_kit(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}, "blood": 7,
                       "generation": 5}))
    assert "?" not in out
    assert "AC" not in out
    assert "gp" not in out
    assert "XP" not in out


def test_the_hud_shows_declared_vitals_and_traits(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}, "blood": 7,
                       "generation": 5}))
    assert "Blood 7" in out
    assert "Generation 5" in out


def test_the_hud_keeps_the_5e_furniture_for_a_5e_sheet(tmp_path):
    out = _run(_world(tmp_path, "realms", DND5E,
                      {"name": "Bram", "level": 3, "race": "Dwarf",
                       "class": "Cleric", "ac": 16, "gold": 12,
                       "hp": {"current": 20, "max": 24},
                       "xp": {"current": 900, "next_level": 2700}}))
    assert "Dwarf" in out and "Cleric" in out
    assert "AC 16" in out
    assert "12gp" in out
    assert "900/2700" in out
    assert "20/24" in out


def test_the_hud_survives_a_scalar_hp_sheet(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Nomad", "level": 1, "hp": 6}))
    assert "Nomad" in out
    assert "6" in out


def test_the_hud_still_reports_no_campaign_and_no_character(tmp_path):
    empty = tmp_path / "world-state"
    (empty / "campaigns").mkdir(parents=True)
    (empty / "active-campaign.txt").write_text("", encoding="utf-8")
    assert "no campaign yet" in _run(empty)

    world = tmp_path / "w2" / "world-state"
    (world / "campaigns" / "probe").mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    assert "no character yet" in _run(world)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_statusline.py -q`
Expected: most fail — the HUD reads the repo's own `world-state` rather than the fixture, so `Rhiannon` is absent and `?`/`AC`/`gp` are present.

- [ ] **Step 3: Point the HUD at `GM_WORLD_STATE_BASE`**

In `tools/gm-statusline.sh`, immediately after the `ROOT=` assignment, add:

```bash
# Same redirection every other tool honours (tools/common.sh): tests point this
# at a fixture tree so they never read or write the player's live campaign. This
# script does not source common.sh — require_active_campaign would exit non-zero
# and Claude Code would show nothing at all.
WORLD_BASE="${GM_WORLD_STATE_BASE:-$ROOT/world-state}"
```

Then replace `ACTIVE_FILE="$ROOT/world-state/active-campaign.txt"` with:

```bash
ACTIVE_FILE="$WORLD_BASE/active-campaign.txt"
```

and `CAMP="$ROOT/world-state/campaigns/$ACTIVE"` with:

```bash
CAMP="$WORLD_BASE/campaigns/$ACTIVE"
```

- [ ] **Step 4: Make the character read kit-driven**

In the same file, replace the whole `--- Character fields ---` jq block:

```bash
IFS=$'\t' read -r NAME RACE CLASS LEVEL AC GP HP_CUR HP_MAX XP_CUR XP_NEXT LOC < <(
    jq -r '
      [ (.name // .identity.name // "?"),
        (.race // .identity.race // "?"),
        (.class // .identity.class // "?"),
        (.level // .progression.level // 1),
        (.ac // .vitals.ac // "?"),
        (.gold // .inventory.gold // 0),
        (.hp.current // .vitals.hp.current // .hp // 0),
        (.hp.max // .vitals.hp.max // .hp // 0),
        (.xp.current // .progression.xp.current // .xp // 0),
        (.xp.next_level // .progression.xp.next_level // 0),
        (.current_location // .details.current_location // "?")
      ] | @tsv' "$CHAR"
)
```

with:

```bash
# The kit decides what this character HAS. Absent fields are omitted rather than
# rendered as "?" or an invented 0 — a world without coin has no gold line, and a
# world without classes advertises no missing class.
RULES="$CAMP/ruleset.json"
[ -f "$RULES" ] || RULES=/dev/null

IFS=$'\t' read -r NAME RACE CLASS LEVEL AC GP HP_CUR HP_MAX XP_CUR XP_NEXT LOC EXTRA < <(
    jq -rn --slurpfile c "$CHAR" --slurpfile k "$RULES" '
      def label: gsub("_"; " ") | split(" ")
                 | map((.[0:1] | ascii_upcase) + (.[1:] | ascii_downcase))
                 | join(" ");
      def shown($v): if ($v | type) == "object"
                     then (($v.current // 0) | tostring)
                          + (if $v.max != null then "/" + ($v.max | tostring) else "" end)
                     else ($v | tostring) end;
      ($c[0] // {}) as $ch
      | ($k[0] // {}) as $kit
      | ($ch.hp // $ch.vitals.hp) as $hp
      | (($kit.stat_schema.vitals // ["hp"]) - ["hp"]) as $vitals
      | ($kit.stat_schema.traits // []) as $traits
      | [ ($ch.name  // $ch.identity.name  // "")
        , ($ch.race  // $ch.identity.race  // "")
        , ($ch.class // $ch.identity.class // "")
        , ($ch.level // $ch.progression.level // 1)
        , ($ch.ac    // $ch.vitals.ac // "")
        , (if ($ch.gold // $ch.inventory.gold) != null
             then ($ch.gold // $ch.inventory.gold) | tostring else "" end)
        , (if ($hp | type) == "object" then ($hp.current // 0) else ($hp // 0) end)
        , (if ($hp | type) == "object" then ($hp.max // 0) else 0 end)
        , (($ch.xp.current // $ch.progression.xp.current // "") | tostring)
        , (($ch.xp.next_level // $ch.progression.xp.next_level // "") | tostring)
        , ($ch.current_location // $ch.details.current_location // "")
        , ( [ ($vitals[] | select($ch[.] != null) | (. | label) + " " + shown($ch[.]))
            , ($traits[] | select($ch[.] != null) | (. | label) + " " + ($ch[.] | tostring))
            ] | join("") )
        ] | @tsv')
```

`EXTRA` holds the kit's declared vitals beyond hp and its declared traits, already labelled, joined with `\x01` so a value containing a space cannot split a field.

- [ ] **Step 5: Make the render omit what the sheet does not have**

Replace the two `L1=` / `L2=` assignment lines:

```bash
L1="${TEAL}⚔ ${BOLD}${NAME}${RESET}  ${DIM}Lv${LEVEL} ${RACE} ${CLASS}${RESET}  ${SEP}  ${AMBER}${LOC}${RESET}"
L2="  HP ${HPC}${BAR}${RESET} ${HP_CUR}/${HP_MAX} ${SEPV} ${DIM}AC${RESET} ${AC} ${SEPV} ${GOLD}${GP}gp${RESET} ${SEPV} ${DIM}XP${RESET} ${XP_CUR}/${XP_NEXT} ${SEPV} ${STATEC}${STATE}${RESET}"
```

with:

```bash
IDENT="Lv${LEVEL}"
[ -n "$RACE" ]  && IDENT="$IDENT $RACE"
[ -n "$CLASS" ] && IDENT="$IDENT $CLASS"
L1="${TEAL}⚔ ${BOLD}${NAME}${RESET}  ${DIM}${IDENT}${RESET}"
[ -n "$LOC" ] && L1="$L1  ${SEP}  ${AMBER}${LOC}${RESET}"

# HP always (every kit has a body); everything else only when the sheet has it.
if [ "$HP_MAX" -gt 0 ] 2>/dev/null; then
    L2="  HP ${HPC}${BAR}${RESET} ${HP_CUR}/${HP_MAX}"
else
    L2="  HP ${HPC}${BAR}${RESET} ${HP_CUR}"
fi
# Kit-declared vitals and traits, already labelled by jq, \x01-separated.
if [ -n "$EXTRA" ]; then
    OLDIFS=$IFS; IFS=$'\001'
    for seg in $EXTRA; do
        [ -n "$seg" ] && L2="$L2 ${SEPV} ${DIM}${seg%% *}${RESET} ${seg#* }"
    done
    IFS=$OLDIFS
fi
[ -n "$AC" ] && L2="$L2 ${SEPV} ${DIM}AC${RESET} ${AC}"
[ -n "$GP" ] && L2="$L2 ${SEPV} ${GOLD}${GP}gp${RESET}"
[ -n "$XP_CUR" ] && [ -n "$XP_NEXT" ] && L2="$L2 ${SEPV} ${DIM}XP${RESET} ${XP_CUR}/${XP_NEXT}"
L2="$L2 ${SEPV} ${STATEC}${STATE}${RESET}"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_statusline.py -q`
Expected: all pass.

- [ ] **Step 7: Check it by eye against the live campaign**

Run: `bash tools/gm-statusline.sh </dev/null`

Expected: The Slow Heart has no `character.json`, so this must print the "no character yet" line and exit 0 — not an error and not a traceback. Paste what you see into your report.

- [ ] **Step 8: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors`
Expected: the same 31 failures.

- [ ] **Step 9: Commit**

```bash
git add tools/gm-statusline.sh tests/test_statusline.py
git commit -m "kit-render: the HUD asks the kit, and gets its first tests"
```

---

## Plan Self-Review

**Spec coverage.** The spec's deferred-follow-up list has four items: `gm-statusline.sh` → Task 3; the party-member block → Task 2; `revive` (the method behind `gm-player.sh revive`) → Task 1; `from_canon` → Task 1. The fifth site (`show_player` / `show_all_players`) is not in that list — it was found while scoping this plan, is the same defect family, and is covered by Task 2. Update the spec section when this lands so the record matches.

**Placeholders.** None. Every step carries the code or the assertions.

**Type consistency.** `_read_vital` returns `(current, max)` with `max` possibly `None` — every new call site handles `None` before formatting. `_identity_line` and `_detail_segments` both take the flat char dict and return `str`. `WorldKit(...).vitals()` returns `List[str]` in both Task 2 call sites. In bash, `EXTRA` is a single `\x01`-joined string, split with a scoped `IFS` that is restored.

**Known risks to watch.**
- Task 2 and Task 3 both change what the player sees every turn; if the reviews disagree about a separator or a label, prefer whatever `character_schema.stat_label` produces, since it is the shared convention.
- Task 3's jq is the least conventional code in the plan. If `--slurpfile` with `/dev/null` misbehaves on this platform, fall back to writing `{}` to a temp file and slurping that — but say so in the report rather than restructuring the query.
- `test_the_hud_invents_no_placeholders_on_a_custom_kit` asserts `"?" not in out`. If a location or name legitimately contains a question mark the test would misfire; no fixture here does.
