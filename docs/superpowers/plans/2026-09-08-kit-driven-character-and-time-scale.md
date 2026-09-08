# Kit-Driven Character Render & Time Scale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the every-turn CHARACTER brief render what the World Kit declares instead of a hardcoded D&D line, give kits a declared home for fixed traits, and let elapsed time be expressed in months and years.

**Architecture:** No new modules. Task 1 deletes a hardcoded f-string in `session_manager` and rebuilds the line from `WorldKit.vitals()`, reusing `PlayerManager._read_vital` (already a `@staticmethod`) so the dict-vs-scalar handling is not duplicated. Task 2 adds one optional `stat_schema.traits` list that the engine renders without interpreting. Task 3 extends two regexes.

**Tech Stack:** Python 3.11+, pytest (in the `dev` extra).

**Spec:** `docs/superpowers/specs/2026-09-08-kit-driven-character-and-time-scale.md`
**Campaign context:** `docs/superpowers/specs/2026-09-08-the-slow-heart-design.md`

## Global Constraints

- Python is invoked as `uv run python` — never bare `python` or `python3`.
- Tests run with `uv run --extra dev pytest`; **always** pass `--ignore=tests/test_reset_archive.py` on a full-suite run (it fails collection on Windows — `os.geteuid` is POSIX-only).
- **Baseline: 31 pre-existing failures** in `test_extraction_gate` (15), `test_bootstrap_no_campaign` (9), `test_slug_unify` (3), `test_wrapper_cwd_anchoring` (2), `test_plot_types` (2). 27 of those need Windows Developer Mode (`os.symlink`); the rest are path-separator assertions. **Do not fix any of them.** The bar is no NEW failures.
- **The engine must never know what a kit's field means.** No fix may name `blood`, `generation`, `gift_tier`, or any other campaign-specific concept in `lib/`. A change that special-cases one is a defect, not a fix.
- Every behaviour is proved against **at least three kits** — `dnd5e`, the resource-axis DCC fixture, and a `custom`/`hyborian` kit with extra vitals — using `_make_world(tmp_path, slug, ruleset)` from `tests/test_kit_vitals.py`.
- Files opened for read/write specify `encoding="utf-8"` (the repo was swept for this; do not regress it).

---

## File Structure

**Created:**
- `tests/test_kit_driven_character_block.py` — the CHARACTER block across three kits (Tasks 1 and 2).

**Modified:**
- `lib/session_manager.py` — replace the hardcoded character line (Task 1), render declared traits (Task 2).
- `lib/world_kit.py` — add a `traits()` accessor (Task 2).
- `lib/time_manager.py` — month/year durations (Task 3).
- `tests/test_world_kit.py` — cover `traits()` (Task 2).
- `tests/test_threat_clocks.py` — extend; it is the file that already covers `ticks_from_duration` (Task 3).
- `docs/modules/game-core-and-world-kit.md` — document `stat_schema.traits`.
- `docs/modules/scene-context.md` — the CHARACTER block is now kit-driven.
- `docs/schema-reference.md` — `stat_schema.traits`.

---

### Task 1: Render the CHARACTER block from the kit

**Files:**
- Modify: `lib/session_manager.py` (the `--- CHARACTER ---` block)
- Test: `tests/test_kit_driven_character_block.py`

**Interfaces:**
- Consumes: `WorldKit.vitals()` (`world_kit.py:83`), `PlayerManager._read_vital` (`player_manager.py:535`, a `@staticmethod` returning `(current, max)` where `max` is `None` for plain-number tracks), `character_schema.to_flat`.
- Produces: no new public interface — a behavioural change to `get_full_context()`'s output.

**What the block does today.** `lib/session_manager.py` (search for `--- CHARACTER ---`) ends in:

```python
lines.append(f"{name} - Level {level} {race} {cls} | HP: {hp_cur}/{hp_max} | AC: {ac} | XP: {xp_val} | Gold: {gold}")
lines.append(f"Conditions: {cond_str}")
```

with `race`/`cls` defaulting to `'?'`, `ac` to `'?'`, and `gold` to `0`. Replace the first line; keep the `Conditions:` line exactly as it is.

**The rule:** assemble segments from what exists. Name, level and HP always. Then every kit-declared vital beyond `hp`. Then the 5e sheet fields **only when the key is present on the sheet** — never a `?`, never an invented `0`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_kit_driven_character_block.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_kit_driven_character_block.py -v`
Expected: FAIL — `test_no_placeholders_for_concepts_the_kit_lacks` and
`test_declared_vitals_are_rendered` fail against the hardcoded line (`?` present,
vitals absent). `test_dnd5e_still_shows_its_own_sheet_fields` should already PASS;
**if it fails at this step, stop and report** — you would be changing 5e behaviour.

- [ ] **Step 3: Write the implementation**

In `lib/session_manager.py`, replace only the single `lines.append(f"{name} - Level ...")`
statement (keep the `char` loading above it and the `Conditions:` line below it):

```python
            # Assembled from what the kit declares and the sheet actually carries —
            # never a fixed template. The old line printed `?` for class and AC and an
            # invented `Gold: 0` on worlds with no coinage, while hiding every kit
            # vital beyond hp. `gm-player.sh show` has been kit-driven for some time;
            # this block kept a divergent hardcoded copy.
            from player_manager import PlayerManager

            identity = f"{name} - Level {level}"
            for key in ("race", "class"):
                if char.get(key):
                    identity += f" {char[key]}"
            segments = [identity, f"HP: {hp_cur}/{hp_max}"]

            declared = kit.vitals() if kit is not None else ["hp"]
            for vital in declared:
                if vital == "hp" or vital not in char:
                    continue
                cur, mx = PlayerManager._read_vital(char, vital)
                label = vital.replace("_", " ").title()
                segments.append(f"{label}: {cur}/{mx}" if mx is not None
                                else f"{label}: {cur}")

            # 5e sheet furniture: shown when the sheet carries it, never invented.
            if "ac" in char:
                segments.append(f"AC: {char['ac']}")
            if "xp" in char:
                raw = char["xp"]
                segments.append(
                    f"XP: {raw.get('current', 0) if isinstance(raw, dict) else raw}")
            if "gold" in char:
                segments.append(f"Gold: {char['gold']}")

            lines.append(" | ".join(segments))
```

Delete the now-unused `race`, `cls`, `ac`, `xp`, `xp_val` and `gold` locals above it.
`kit` is already in scope from the KIT block earlier in the method and may be `None`;
the `if kit is not None` guard mirrors how that block handles it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_kit_driven_character_block.py -v`
Expected: PASS — 6 passed

Then the suites that touch this block:

Run: `uv run --extra dev pytest tests/test_get_full_context.py tests/test_kit_vitals.py tests/test_party_promote.py tests/test_lean_core.py -v`
Expected: no NEW failures.

- [ ] **Step 5: Commit**

```bash
git add lib/session_manager.py tests/test_kit_driven_character_block.py
git commit -m "$(cat <<'EOF'
scene-context: render the CHARACTER line from the kit, not a hardcoded 5e template

The line the GM reads every turn was a fixed f-string carrying five D&D
assumptions. A custom kit read `Level 0 Brythonic ? | AC: ? | XP: 0 | Gold: 0`
while every declared vital beyond hp was invisible — including meters the world
runs its whole resolution on. Gold was printed from a .get() default, so removing
it from the sheet changed nothing the GM saw.

Segments are now assembled from what the kit declares and the sheet carries.
gm-player.sh show has been kit-driven for some time; this block kept a divergent
copy, and reuses its PlayerManager._read_vital staticmethod rather than
duplicating the dict-vs-scalar handling.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 2: Give kits a declared home for fixed traits

**Files:**
- Modify: `lib/world_kit.py` (add `traits()`), `lib/session_manager.py` (render them)
- Test: `tests/test_world_kit.py`, `tests/test_kit_driven_character_block.py` (append)

**Interfaces:**
- Consumes: `WorldKit.stat_schema()` (`world_kit.py:80`).
- Produces: `WorldKit.traits() -> List[str]` — the kit's declared fixed-trait field names, `[]` when the kit declares none.

**The concept.** `attributes` are rolled; `vitals` are resources that move. A **trait** is
a fixed property of the character that the world cares about and the engine does not
understand — a generation, a lineage, a caste, a clearance level, a corporate rank.

**The engine must never learn what any of them mean.** It renders `Name: value` and
nothing more. No validation of the value, no defaulting, no special cases. If you find
yourself writing the name of a specific trait in `lib/`, stop.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_world_kit.py`:

```python
def test_traits_default_to_empty_when_the_kit_declares_none(dcc_world):
    # WorldKit is already imported at module level in this file.
    assert WorldKit(dcc_world).traits() == []
```

Append to `tests/test_kit_driven_character_block.py`:

```python
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
```

That last test is the one that matters: it proves the engine renders **because the kit
declared**, not because the key happens to exist.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_world_kit.py tests/test_kit_driven_character_block.py -v`
Expected: FAIL — `AttributeError: 'WorldKit' object has no attribute 'traits'`

- [ ] **Step 3: Write the implementation**

In `lib/world_kit.py`, add next to `vitals()`:

```python
    def traits(self) -> List[str]:
        """Fixed character traits this world declares — a generation, a lineage, a
        clearance level, a caste.

        Distinct from `attributes` (rolled) and `vitals` (resources that move): a
        trait is a fixed property the world cares about and the engine deliberately
        does not understand. It is rendered as a labelled value and never
        interpreted, validated or defaulted. A kit declaring none gets [].
        """
        return (self.stat_schema() or {}).get("traits") or []
```

Update the `ruleset.json` shape comment at the top of `world_kit.py` (around line 17) to
show `traits` alongside `attributes` and `vitals`.

In `lib/session_manager.py`, after the vitals loop from Task 1 and **before** the 5e
sheet-furniture block:

```python
            for trait in (kit.traits() if kit is not None else []):
                if trait not in char:
                    continue
                segments.append(f"{trait.replace('_', ' ').title()}: {char[trait]}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_world_kit.py tests/test_kit_driven_character_block.py -v`
Expected: PASS — 9 in the character-block file, plus the world-kit case.

- [ ] **Step 5: Update the docs and commit**

In `docs/modules/game-core-and-world-kit.md`, document the third bucket:

```markdown
### `stat_schema.traits` — fixed properties the engine does not understand

`attributes` are rolled and `vitals` are resources that move. A **trait** is a fixed
property of a character that the world cares about: a generation, a lineage, a caste,
a clearance level. The engine renders a declared trait as a labelled value in the
CHARACTER brief and does nothing else with it — no validation, no defaults, no
interpretation. A kit that declares none is unaffected.

This is the seam that keeps a campaign's vocabulary out of `lib/`. If the engine ever
needs to know what a particular trait *means*, that is a design error.
```

Add `traits` to the `stat_schema` example in `docs/schema-reference.md`, and note in
`docs/modules/scene-context.md` that the CHARACTER block is kit-driven.

```bash
git add lib/world_kit.py lib/session_manager.py tests/test_world_kit.py \
        tests/test_kit_driven_character_block.py docs/
git commit -m "$(cat <<'EOF'
world-kit: declare fixed traits in stat_schema, rendered but never interpreted

attributes are rolled and vitals move; a world's fixed properties — a generation,
a lineage, a caste, a clearance level — had no declared home and were invisible to
the GM. Adding any of them to lib/ would hardcode one campaign into the engine the
way `class` hardcodes 5e.

stat_schema.traits is a list of field names. The engine renders `Name: value` and
does nothing else: no validation, no defaults, no special cases. A kit declaring
none is unaffected, and a value on the sheet that the kit did not declare is not
rendered.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 3: Understand months and years in elapsed durations

**Files:**
- Modify: `lib/time_manager.py`
- Test: `tests/test_threat_clocks.py` — it already covers `ticks_from_duration`; append there rather than starting a new file.

**Interfaces:**
- Consumes: nothing new.
- Produces: `ticks_from_duration` additionally recognises `N month(s)` → `30*N` and `N year(s)` → `365*N`.

**Why large tick counts are safe, and not something to guard against.**
`ThreatClockManager.tick_time_clocks` (`threat_clocks.py:92-103`) computes
`min(mx, cur + ticks)`, skips clocks already full, and fires each consequence once on
the fill transition. A forty-year skip therefore fills every pending time-clock and
fires each consequence exactly once — it cannot overflow and cannot double-fire. That is
the truthful outcome of forty years passing, not a bug to be prevented. **Do not add a
cap, a scale factor, or any special handling for large values.**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_threat_clocks.py` (it already imports from `lib.time_manager`; add `ticks_from_duration` to that import if it is not there):

```python
# Elapsed durations must scale past a week. A campaign that skips decades of
# practice and centuries of torpor could express neither: ticks_from_duration knew
# only days and weeks, so "10 years" advanced clocks as far as waiting a moment.


@pytest.mark.parametrize("text,expected", [
    ("3 days", 3),
    ("2 weeks", 14),
    ("1 month", 30),
    ("6 months", 180),
    ("1 year", 365),
    ("10 years", 3650),
    ("40 years of deliberate practice", 14600),
])
def test_durations_scale(text, expected):
    assert ticks_from_duration(text) == expected


def test_longest_unit_wins_when_several_appear():
    """'2 years 3 months' is two years, not three months."""
    assert ticks_from_duration("2 years 3 months") == 730


def test_unparseable_duration_still_falls_back_to_one():
    assert ticks_from_duration("a while later") == 1
    assert ticks_from_duration("") == 1
    assert ticks_from_duration(None) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --extra dev pytest tests/test_threat_clocks.py -v`
Expected: FAIL — the month/year cases return 1.

- [ ] **Step 3: Write the implementation**

In `lib/time_manager.py`, extend the comment block and add two patterns above the
existing week/day ones:

```python
# Small elapsed-magnitude map for threat-clock ticks. Not a calendar parser:
# minutes / hours / same-day time-of-day → 1
# N day/days → N
# N week/weeks → 7*N
# N month/months → 30*N
# N year/years → 365*N
# anything else (including empty) → 1
#
# Large values are safe and intended: tick_time_clocks clamps with
# min(max, current + ticks), skips already-full clocks, and fires each consequence
# once on the fill transition. A decade-long skip filling every pending clock is the
# truthful outcome of a decade passing, not an overflow to guard against.
_DURATION_YEAR = re.compile(r"(\d+)\s*years?", re.IGNORECASE)
_DURATION_MONTH = re.compile(r"(\d+)\s*months?", re.IGNORECASE)
_DURATION_WEEK = re.compile(r"(\d+)\s*weeks?", re.IGNORECASE)
_DURATION_DAY = re.compile(r"(\d+)\s*days?", re.IGNORECASE)
```

and in `ticks_from_duration`, check year then month **before** week and day, so the
longest unit present wins:

```python
    for pattern, factor in ((_DURATION_YEAR, 365), (_DURATION_MONTH, 30),
                            (_DURATION_WEEK, 7), (_DURATION_DAY, 1)):
        m = pattern.search(s)
        if m:
            return max(1, factor * int(m.group(1)))
    return 1
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_threat_clocks.py tests/test_world_tick.py -v`
Expected: PASS, with no new failures in the tick suite.

Then the full regression pass:

Run: `uv run --extra dev pytest --ignore=tests/test_reset_archive.py`
Expected: **31 failures**, the same set as the stated baseline. Report the count and
confirm the failing set is unchanged.

- [ ] **Step 5: Commit**

```bash
git add lib/time_manager.py tests/test_threat_clocks.py
git commit -m "$(cat <<'EOF'
time: understand months and years in elapsed durations

ticks_from_duration knew only days and weeks, so "10 years" and "a century"
advanced threat clocks exactly as far as waiting a moment — unusable for a
campaign built on decade-long training and century-long sleep. The longest unit
present now wins, so "2 years 3 months" is two years.

Large tick counts need no guarding: tick_time_clocks clamps, skips already-full
clocks, and fires each consequence once on the fill transition, so a long skip
filling every pending clock is the truthful outcome rather than an overflow.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

## Notes for the executor

- **Baseline the suite first.** Run `uv run --extra dev pytest --ignore=tests/test_reset_archive.py` before Task 1 and keep the failing-test list. The bar is no *new* failures against 31.
- **Tasks 1 and 2 are strictly sequential** — Task 2 extends the segment assembly Task 1 builds. Task 3 is independent and may run any time.
- **The single acceptance question for Tasks 1 and 2:** could a kit that has never heard of vampires express this? If a fix names `blood`, `generation` or `gift_tier` anywhere in `lib/`, it has failed regardless of whether the tests pass.
- **`lib/session_manager.py` line numbers drift.** Anchor on the `--- CHARACTER ---` marker, not on a number.
- **Do not touch threat-clock tick semantics.** Clamping and once-per-fill firing are correct and deliberate; Task 3's whole point is that they already handle large values.
- Deferred to their own plans, deliberately out of scope here: per-NPC belief state ("who knows what"), machine-readable NPC generation, and the repo-wide `parser.print_help()`-under-`--json` behaviour.
