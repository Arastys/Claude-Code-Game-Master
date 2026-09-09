# Verbless Writes and the `--json` Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop two write tools from accepting a malformed argument as data, and make the documented `--json` contract true for the five tools that do not honour it.

**Architecture:** Two new helpers in `tools/common.sh` — one that pulls `--json` out of the positional arguments so a `case`-dispatching wrapper can forward it explicitly, one that refuses a hyphen-leading value in a positional data slot. Then the five managers get the `lib/cli_output.py` wiring every other manager already uses. No new modules.

**Tech Stack:** bash, Python 3 (stdlib), pytest. Run everything with `uv run python`, never bare `python`.

**Spec:** `docs/superpowers/specs/2026-09-09-verbless-writes-and-json.md`

## Global Constraints

- **A positional data slot never accepts a value beginning with `-`.** A category, a fact, a time of day and a date never legitimately start with a hyphen; a value that does is a mistake every time. Note that `--json` specifically is caught earlier, by arity, because `split_json_flag` removes it before the count is checked — the hyphen guard is what catches every other stray flag.
- **`--json` is honoured or refused, never absorbed.** No tool may write a flag to disk as content.
- **The `--json` envelope is exactly two shapes**, defined in `lib/cli_output.py`: `{"ok": true, "data": …}` and `{"ok": false, "error": "…", "code": null}`. The wiring is fixed: `wants_json()` to detect, `strip_json_flag()` before argparse, `emit()` / `emit_error()` to output. `emit_error` returns `1`, so callers write `sys.exit(emit_error(...))`.
- **A manager that `print()`s human text from inside its logic must suppress it in JSON mode**, or the envelope arrives preceded by garbage. `lib/consequence_manager.py` does this with `contextlib.redirect_stdout`.
- **Every changed verb gets a wrapper-level subprocess test** driving the `.sh` through `bash`. A previous plan shipped a verb that printed usage and exited 0 through three review gates because only the Python entry point was tested.
- **Tests never touch the live campaign.** Always `GM_WORLD_STATE_BASE` against a fixture.
- **All file writes use `encoding="utf-8"`** — Windows here, where `open()` defaults to cp1252.
- **Run the suite as** `uv run python -m pytest -q --continue-on-collection-errors`. Baseline **31 failed / 819 passed**; the failing set must be byte-identical afterwards. **This pytest prints no final tally line** — count `^FAILED ` lines, never infer, and never gate a commit behind a piped test run (a pipeline's exit status is the last command's, so `pytest … | tail && git commit` commits on failure).

---

## File Structure

| File | Change |
|---|---|
| `tools/common.sh` | Add `split_json_flag` and `reject_flag_in_data_slot`. |
| `tools/gm-note.sh` | Guard both data slots; forward `--json`. |
| `tools/gm-time.sh` | Guard both data slots; forward `--json`; propagate the consequence tick's exit status. |
| `tools/gm-plot.sh`, `gm-location.sh`, `gm-campaign.sh` | Forward `--json` through every `case` branch. |
| `lib/note_manager.py`, `time_manager.py`, `plot_manager.py`, `location_manager.py`, `campaign_manager.py` | Add the `cli_output` wiring. |
| `tests/test_verbless_write_guard.py` (create) | Reproduce the corruption, then guard it. |
| `tests/test_json_wrappers_tools.py` (create) | Envelope through every wrapper verb. |
| `CLAUDE.md`, `docs/conventions/tool-wrapper-contract.md` | Correct two false claims. |

**Task 1 alone closes the corruption hole.** Tasks 2–4 are the contract cleanup. If work stops after Task 1, the dangerous defect is fixed and the branch is still coherent.

---

### Task 1: The guard

**Files:**
- Modify: `tools/common.sh` (add two functions)
- Modify: `tools/gm-note.sh`, `tools/gm-time.sh`
- Test: `tests/test_verbless_write_guard.py` (create)

**Interfaces:**
- Produces, for Tasks 2 and 3: `split_json_flag "$@"` sets `JSON_FLAG` (`"--json"` or `""`) and leaves the remaining arguments in the `GM_ARGS` array; `reject_flag_in_data_slot <slot-name> <value>` returns 1 and prints to stderr when the value begins with `-`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verbless_write_guard.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_verbless_write_guard.py -q`
Expected: the four refusal tests fail — the commands currently succeed and write.

- [ ] **Step 3: Add the two helpers to `tools/common.sh`**

Append immediately after the `validate_name()` function:

```bash
# Pull --json out of the positional arguments.
#
# A `case`-dispatching wrapper cannot simply forward "$@" to Python: several
# branches pass only "$1"/"$2", so a trailing --json is silently dropped and the
# caller gets human text having asked for an envelope. Pulling the flag out first
# lets every branch forward it explicitly.
#
# Sets JSON_FLAG to "--json" or "", and leaves the remaining arguments in GM_ARGS.
# Callers re-apply them with:
#     split_json_flag "$@"; set -- ${GM_ARGS+"${GM_ARGS[@]}"}
# The ${GM_ARGS+...} form is required: a bare "${GM_ARGS[@]}" on an empty array
# errors under `set -u`.
split_json_flag() {
    JSON_FLAG=""
    GM_ARGS=()
    local _a
    for _a in "$@"; do
        if [ "$_a" = "--json" ]; then
            JSON_FLAG="--json"
        else
            GM_ARGS+=("$_a")
        fi
    done
}

# Refuse a value beginning with a hyphen in a positional DATA slot.
#
# gm-note.sh and gm-time.sh take no subcommand — their first positional IS data —
# so every string was a valid category and a valid time of day, and no invocation
# could be malformed. `gm-note.sh list --json` recorded a permanent fact whose text
# was "--json"; `gm-time.sh list --json` set the campaign date to "--json" and
# advanced every time-clock. A category, a fact, a time of day and a date never
# legitimately begin with "-", so a value that does is a mistake every time.
reject_flag_in_data_slot() {
    local _slot="$1" _value="$2"
    case "$_value" in
        -*)
            echo "[ERROR] $_slot cannot begin with '-' (got: $_value)" >&2
            echo "        This position takes data, not a flag." >&2
            return 1
            ;;
    esac
    return 0
}
```

- [ ] **Step 4: Guard `tools/gm-note.sh`**

Replace everything from `source "$(dirname "$0")/common.sh"` to the end of the file with:

```bash
source "$(dirname "$0")/common.sh"

split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}

if [ "$#" -lt 1 ]; then
    echo "Usage: gm-note.sh <category> <fact>"
    echo "       gm-note.sh categories"
    echo ""
    echo "Categories: session_events, plot_local, plot_regional, plot_world,"
    echo "            player_choices, npc_relations, lore, rules"
    echo ""
    echo "Example: gm-note.sh \"volcano\" \"The volcano god demands royal blood\""
    exit 1
fi

require_active_campaign

if [ "$1" = "categories" ]; then
    [ -z "$JSON_FLAG" ] && echo "Fact Categories:"
    $PYTHON_CMD "$LIB_DIR/note_manager.py" categories $JSON_FLAG
    exit $?
elif [ "$#" -eq 2 ]; then
    # This wrapper has no verb: $1 and $2 are data, so nothing else can reject a
    # stray flag before it reaches disk.
    reject_flag_in_data_slot "category" "$1" || exit 1
    reject_flag_in_data_slot "fact" "$2" || exit 1
    $PYTHON_CMD "$LIB_DIR/note_manager.py" add "$1" "$2" $JSON_FLAG
    exit $?
else
    echo "Usage: gm-note.sh <category> <fact>" >&2
    if [ -n "$JSON_FLAG" ]; then
        # Stripping --json left too few arguments, which means it was sitting in a
        # data slot. Say so: the bare usage line would not tell the caller that the
        # flag they passed was about to become the fact's text.
        echo "[ERROR] --json is a flag, not content — it cannot occupy <category> or <fact>." >&2
    fi
    exit 1
fi
```

`$JSON_FLAG` is deliberately unquoted so an empty value expands to nothing rather than an empty argument.

**Two different mechanisms protect these slots, and it matters which fires when.**
For `gm-note.sh list --json`, `split_json_flag` removes the flag first, so only one
argument remains and the **arity** check refuses it — `reject_flag_in_data_slot`
never runs. The guard is what catches every *other* hyphen-leading value:
`--type`, `-x`, an unexpanded `$VAR` that came back as `-`. Both are required;
neither covers the other's case. This is why the `if [ -n "$JSON_FLAG" ]` line
above exists: without it the arity path refuses correctly but explains nothing, and
the plan's own `test_the_refusal_names_the_offending_value` fails.

- [ ] **Step 5: Guard `tools/gm-time.sh`**

Immediately after `source "$(dirname "$0")/common.sh"`, insert:

```bash
split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}
```

Then immediately after the existing `if [ -z "$1" ] || [ -z "$2" ]; then … fi` usage block, insert:

```bash
# No verb here either: $1 and $2 are the time of day and the date. A stray flag in
# either slot was written to the overview and then advanced every time-clock.
reject_flag_in_data_slot "time_of_day" "$1" || exit 1
reject_flag_in_data_slot "date" "$2" || exit 1
```

Finally, replace the last two lines of the file:

```bash
bash "$TOOLS_DIR/gm-consequence.sh" tick
exit 0
```

with:

```bash
bash "$TOOLS_DIR/gm-consequence.sh" tick
# Propagate the tick's status. Every earlier step in this script checks $? and
# exits on failure; this one used to discard it, so a failed consequence tick was
# reported as success.
exit $?
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_verbless_write_guard.py -q`
Expected: all pass.

- [ ] **Step 7: Confirm no regression**

Run: `uv run python -m pytest -q --continue-on-collection-errors > out.txt 2>&1; grep -c '^FAILED ' out.txt`
Expected: `31`. Compare the sorted `FAILED` names against a run taken before you started.

- [ ] **Step 8: Commit**

```bash
git add tools/common.sh tools/gm-note.sh tools/gm-time.sh tests/test_verbless_write_guard.py
git commit -m "tools: refuse a flag in a positional data slot, and propagate the time tick"
```

---

### Task 2: `--json` for the two verbless tools

**Files:**
- Modify: `lib/note_manager.py`, `lib/time_manager.py`
- Test: `tests/test_json_wrappers_tools.py` (create)

**Interfaces:**
- Consumes from Task 1: `split_json_flag`, `JSON_FLAG` (both wrappers already forward it).
- Consumes: `lib/cli_output.py` — `wants_json(argv=None) -> bool`, `strip_json_flag(argv=None) -> list`, `emit(data=None, message=None, json_mode=False)`, `emit_error(message, json_mode=False, code=None) -> int`.

**On suppressing human output.** `NoteManager.add_fact` and `TimeManager.update_time` `print()` `[SUCCESS]` lines from inside their logic. In JSON mode that text arrives before the envelope and breaks `json.loads`. Wrap those calls in `contextlib.redirect_stdout(io.StringIO())`, the same treatment `lib/consequence_manager.py` uses.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_json_wrappers_tools.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_json_wrappers_tools.py -q`
Expected: `json.decoder.JSONDecodeError` — the managers still print human text.

- [ ] **Step 3: Wire `lib/note_manager.py`**

Replace the whole `main()` with:

```python
def main():
    """CLI interface for note management."""
    import contextlib
    import io as _io
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    json_mode = wants_json()
    argv = strip_json_flag(sys.argv)

    if len(argv) < 2:
        print("Usage: python lib/note_manager.py add <category> <fact>")
        print("       python lib/note_manager.py get [category]")
        print("       python lib/note_manager.py categories")
        sys.exit(1)

    action = argv[1]

    try:
        manager = NoteManager()

        if action == 'add':
            if len(argv) < 4:
                sys.exit(emit_error(
                    "usage: note_manager.py add <category> <fact>", json_mode))
            category, fact = argv[2], argv[3]
            # add_fact prints [SUCCESS] from inside the manager; in JSON mode that
            # text would precede the envelope and break json.loads.
            sink = _io.StringIO()
            with contextlib.redirect_stdout(sink if json_mode else sys.stdout):
                ok = manager.add_fact(category, fact)
            if not ok:
                sys.exit(emit_error(f"could not record fact in {category}", json_mode))
            emit({"category": category, "fact": fact}, json_mode=json_mode)

        elif action == 'get':
            category = argv[2] if len(argv) > 2 else None
            facts = manager.get_facts(category)
            if json_mode:
                emit(facts, json_mode=True)
            else:
                print(json.dumps(facts, indent=2))

        elif action == 'categories':
            categories = manager.list_categories()
            if json_mode:
                emit(categories, json_mode=True)
            else:
                for cat in categories:
                    print(f"  - {cat}")

        else:
            sys.exit(emit_error(f"unknown action: {action}", json_mode))

    except RuntimeError as e:
        sys.exit(emit_error(str(e), json_mode))
```

- [ ] **Step 4: Wire `lib/time_manager.py`**

Replace the whole `main()` with:

```python
def main():
    """CLI interface for time management."""
    import contextlib
    import io as _io
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    json_mode = wants_json()
    argv = strip_json_flag(sys.argv)

    if len(argv) < 2:
        print("Usage: python lib/time_manager.py update <time_of_day> <date>")
        print("       python lib/time_manager.py get")
        print("       python lib/time_manager.py ticks [--ticks N] [--duration TEXT]")
        sys.exit(1)

    action = argv[1]

    # ticks is a pure mapping — no campaign, so it can run before TimeManager().
    # It prints a bare number that gm-time.sh captures in a command substitution,
    # so it must stay a bare number even in JSON mode.
    if action == "ticks":
        ticks, duration = _parse_ticks_flags(argv[2:])
        print(ticks_for_elapsed(ticks=ticks, duration=duration))
        return

    try:
        manager = TimeManager()

        if action == 'update':
            if len(argv) < 4:
                sys.exit(emit_error(
                    "usage: time_manager.py update <time_of_day> <date>", json_mode))
            time_of_day, date = argv[2], argv[3]
            sink = _io.StringIO()
            with contextlib.redirect_stdout(sink if json_mode else sys.stdout):
                ok = manager.update_time(time_of_day, date)
            if not ok:
                sys.exit(emit_error("could not update time", json_mode))
            emit({"time_of_day": time_of_day, "current_date": date},
                 json_mode=json_mode)

        elif action == 'get':
            time_info = manager.get_time()
            if json_mode:
                emit(time_info, json_mode=True)
            else:
                print(f"Time: {time_info['time_of_day']}")
                print(f"Date: {time_info['current_date']}")

        else:
            sys.exit(emit_error(f"unknown action: {action}", json_mode))

    except RuntimeError as e:
        sys.exit(emit_error(str(e), json_mode))
```

**`ticks` must keep printing a bare number.** `gm-time.sh` captures it with `CLOCK_TICKS=$(… ticks …)` and passes it to `threat_clocks.py tick-time --ticks`. Wrapping it in an envelope would break the clock advance. The wrapper never forwards `--json` to that call, but the guard above makes it safe regardless.

- [ ] **Step 5: Suppress the wrapper's own human output in JSON mode**

In `tools/gm-time.sh`, the trailing consequence tick prints human text that would follow the envelope. Replace:

```bash
bash "$TOOLS_DIR/gm-consequence.sh" tick
```

with:

```bash
if [ -n "$JSON_FLAG" ]; then
    # The envelope is the whole of stdout in JSON mode; the tick still runs and
    # still fires consequences, but its human report is suppressed.
    bash "$TOOLS_DIR/gm-consequence.sh" tick >/dev/null
else
    bash "$TOOLS_DIR/gm-consequence.sh" tick
fi
```

and change the preceding bare `echo ""` to `[ -z "$JSON_FLAG" ] && echo ""`.

Also silence the clock tick in JSON mode — replace:

```bash
$PYTHON_CMD "$LIB_DIR/threat_clocks.py" tick-time --ticks "$CLOCK_TICKS"
```

with:

```bash
if [ -n "$JSON_FLAG" ]; then
    $PYTHON_CMD "$LIB_DIR/threat_clocks.py" tick-time --ticks "$CLOCK_TICKS" >/dev/null
else
    $PYTHON_CMD "$LIB_DIR/threat_clocks.py" tick-time --ticks "$CLOCK_TICKS"
fi
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_json_wrappers_tools.py tests/test_verbless_write_guard.py -q`
Expected: all pass. Task 1's tests must still pass — `test_a_legitimate_time_update_still_works_and_still_ticks` proves the clock still advances despite the new redirection.

- [ ] **Step 7: Confirm no regression**

Run the suite; expect the same 31.

- [ ] **Step 8: Commit**

```bash
git add lib/note_manager.py lib/time_manager.py tools/gm-time.sh tests/test_json_wrappers_tools.py
git commit -m "note/time: honour --json instead of writing it to disk"
```

---

### Task 3: `--json` for the three `case` dispatchers

**Files:**
- Modify: `lib/plot_manager.py`, `lib/location_manager.py`, `lib/campaign_manager.py`
- Modify: `tools/gm-plot.sh`, `tools/gm-location.sh`, `tools/gm-campaign.sh`
- Test: `tests/test_json_wrappers_tools.py` (append)

**Interfaces:**
- Consumes from Task 1: `split_json_flag`, `JSON_FLAG`.

**Why the wrapper change is not optional.** `gm-plot.sh` forwards `"$@"` for `add` and `list`, but passes only `"$1"` (or `"$1" "$2"`) for `show`, `search`, `update`, `complete` and `fail`, and nothing at all for `counts` and `threads`. Adding `cli_output` to the manager therefore fixes two verbs out of nine; the other seven silently drop the flag. `gm-location.sh` and `gm-campaign.sh` have the same shape.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_json_wrappers_tools.py`:

```python
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
    world, _ = _world(tmp_path)
    assert _run(world, "gm-plot.sh", "threads", "--json").returncode == 0


def test_location_list_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    _run(world, "gm-location.sh", "add", "Y Bedd", "the ridge")
    assert _envelope(_run(world, "gm-location.sh", "list", "--json")) is not None


def test_campaign_list_emits_an_envelope(tmp_path):
    world, _ = _world(tmp_path)
    assert _envelope(_run(world, "gm-campaign.sh", "list", "--json")) is not None


def test_no_tool_ever_writes_the_flag_as_data(tmp_path):
    """The blanket guarantee: --json is honoured or refused, never absorbed."""
    world, campaign = _world(tmp_path)
    for tool, args in [("gm-note.sh", ["list"]), ("gm-time.sh", ["list"])]:
        proc = _run(world, tool, *args, "--json")
        assert proc.returncode != 0, f"{tool} accepted a flag as data"
    assert json.loads((campaign / "facts.json").read_text(encoding="utf-8")) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_json_wrappers_tools.py -q -k "plot or location or campaign"`
Expected: `JSONDecodeError` on each — human text, not an envelope.

- [ ] **Step 3: Wire the three managers**

In each of `lib/plot_manager.py`, `lib/location_manager.py` and `lib/campaign_manager.py`, apply the same three changes to `main()`:

1. At the top of `main()`, beside the existing `import argparse`:

```python
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    json_mode = wants_json()
```

2. Change the `parser.parse_args()` call to strip the flag first:

```python
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
```

3. In each action branch, where the code currently `print()`s a formatted string, emit the underlying data instead when `json_mode` is true. The formatted output stays for human mode. For example, `plot_manager.py`'s `list` branch becomes:

```python
    if args.action == 'list':
        plots = manager.list_plots(args.type, args.status)
        if json_mode:
            emit(plots, json_mode=True)
        else:
            print(manager.format_plot_list(plots))
```

Apply that shape to every branch that produces output. Branches that only mutate and `sys.exit(1)` on failure should emit `{"ok": true, "data": {...}}` describing what changed, and route their failure through `sys.exit(emit_error(...))`.

Read each `main()` in full before editing — the three differ in how many branches they have and what each returns. Do not guess at a branch you have not read. Counted with `grep -c "args.action =="`: **`plot_manager.py` has 9 branches, `location_manager.py` has 6, `campaign_manager.py` has 9.** All three currently call a bare `parser.parse_args()`, so the `strip_json_flag(sys.argv[1:])` change applies identically to each.

Two branches worth knowing before you start: `plot_manager.py`'s `counts` already prints `json.dumps(manager.get_plot_counts())` — it needs the envelope wrapped around existing data, not new data — and `threads` has `manager.get_active_threads()` in hand before formatting, so both are straightforward to emit.

- [ ] **Step 4: Forward the flag in the three wrappers**

In each of `tools/gm-plot.sh`, `tools/gm-location.sh` and `tools/gm-campaign.sh`:

1. Immediately after `source "$(dirname "$0")/common.sh"`, insert:

```bash
split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}
```

2. Append `$JSON_FLAG` (unquoted, so an empty value vanishes) to **every** `$PYTHON_CMD "$LIB_DIR/<manager>.py" …` invocation in the `case`. Counted with `grep -c PYTHON_CMD`: **`gm-plot.sh` has 11, `gm-location.sh` has 6, `gm-campaign.sh` has 11.** Re-count in the file you are editing and confirm afterwards that none was missed — a branch whose flag you forget is a verb whose `--json` silently does nothing, which is the exact defect this task exists to fix.

   Note that `grep -c PYTHON_CMD` also counts the `PYTHON_CMD=$(find_python)` style lines and any helper invocation, so read the matches rather than trusting the number alone.

3. Where a branch prints a human header before calling Python, guard it with `[ -z "$JSON_FLAG" ] &&` so the envelope is not preceded by text.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_json_wrappers_tools.py -q`

- [ ] **Step 6: Confirm no regression**

Run the suite; expect the same 31.

- [ ] **Step 7: Commit**

```bash
git add lib/plot_manager.py lib/location_manager.py lib/campaign_manager.py \
        tools/gm-plot.sh tools/gm-location.sh tools/gm-campaign.sh \
        tests/test_json_wrappers_tools.py
git commit -m "plot/location/campaign: forward --json through every case branch"
```

---

### Task 4: Make the two documented claims true

**Files:**
- Modify: `docs/conventions/tool-wrapper-contract.md`
- Test: `tests/test_json_wrappers_tools.py` (append one)

**Interfaces:** none.

`CLAUDE.md` says "All tools take `--json` for structured returns." After Tasks 2 and 3 that is true, so the sentence stands unchanged — verify it rather than editing it.

`docs/conventions/tool-wrapper-contract.md`'s "Enforcement point" section says `tests/test_json_wrappers_*.py` covers "player, npc, session, consequence". **None of those four files exists.** Only `tests/test_json_wrappers_onboard.py` does, plus the new `tests/test_json_wrappers_tools.py`. Envelope assertions do live in ten other files (`test_faction_manager.py`, `test_knowledge_manager.py`, `test_world_tracks.py`, `test_kit_systems.py`, `test_play_pack.py`, and others), so the contract is better enforced than the doc's sentence implies — just not where it says.

The doc's **OKF frontmatter also carries `- { resource: /tests/test_json_wrappers_player.py }`**, a resource pointer to one of the files that was never written. Fix that line too; a frontmatter resource that does not resolve is the same false claim in a machine-readable slot.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_json_wrappers_tools.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python -m pytest tests/test_json_wrappers_tools.py -q -k contract`
Expected: fails on the first name the doc lists that has no file.

- [ ] **Step 3: Correct the doc**

Rewrite the "Enforcement point" section's first sentence to name only files that exist, and to say plainly where the envelope is actually asserted. Also correct the frontmatter `resource:` line that points at `/tests/test_json_wrappers_player.py`. Read the current section before editing; keep its voice, and keep the closing point that a new manager gets no enforcement until a matching test exists.

- [ ] **Step 4: Verify the CLAUDE.md claim is now true**

Run each of the five tools with `--json` against a throwaway campaign and confirm each either emits an envelope or exits non-zero. Paste the results into your report. Do not edit `CLAUDE.md` unless one of them still fails, in which case say so rather than weakening the sentence.

- [ ] **Step 5: Confirm no regression, then commit**

```bash
git add docs/conventions/tool-wrapper-contract.md tests/test_json_wrappers_tools.py
git commit -m "docs: the wrapper contract names enforcement files that exist"
```

---

## Plan Self-Review

**Spec coverage.** Requirement 1 → Task 1 Steps 3-5. Requirement 2 → Tasks 2 and 3, plus `test_no_tool_ever_writes_the_flag_as_data`. Requirement 3 → Task 3. Requirement 4 → Task 2. Requirement 5 → Task 1 Step 5. Requirement 6 → Task 4. Requirement 7 → every test file drives `.sh` through `bash`.

**Placeholders.** Task 3 Step 3 deliberately does not paste all three `main()` bodies — they are long and differ, and pasting a body I have not verified line-by-line is how earlier plans shipped defects. The instruction is explicit that the implementer reads each before editing, and the shape to apply is given concretely.

**Type consistency.** `JSON_FLAG` is a bash string, `""` or `"--json"`, always unquoted at use so empty expands to nothing. `GM_ARGS` is a bash array, always re-applied as `${GM_ARGS+"${GM_ARGS[@]}"}`. `reject_flag_in_data_slot` returns 0 or 1 and is always used as `… || exit 1`. In Python, `json_mode` is a bool from `wants_json()`, and `emit_error` returns 1 for `sys.exit(emit_error(...))`.

**Known risks.**
- `split_json_flag` removes **every** `--json`, including one a user meant as literal fact text. Recording a fact whose content is exactly `--json` becomes impossible. That is an acceptable loss for a guard that prevents silent corruption, and it is what requirement 1 asks for.
- Task 2 redirects stdout around `update_time`. Task 1's `test_a_legitimate_time_update_still_works_and_still_ticks` is the guard that the clock still advances; keep it green.
- `gm-campaign.sh` is the only wrapper of the three whose `case` does not end in `exit $?`. Check its exit-status handling while editing, and report if forwarding the flag changes it.
