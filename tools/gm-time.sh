#!/bin/bash
# gm-time.sh - Update campaign time (wrapper for time_manager.py)
#
#   gm-time.sh <time_of_day> <date> [--ticks N] [--duration "<text>"]
# Time-clocks advance by elapsed magnitude: minutes/hours/same-day → 1 tick,
# N days → N ticks, N weeks → 7*N ticks, N months → 30*N ticks, N years → 365*N
# ticks (longest unit present in --duration wins). Default (neither flag) is 1.

source "$(dirname "$0")/common.sh"

split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}
# DM_JSON=1 is the documented global envelope switch (lib/cli_output.py), and the
# manager honours it with no flag in sight — so fold it into JSON_FLAG here, or the
# human-only guards below would print their text ahead of an envelope.
[ "${DM_JSON:-}" = "1" ] && JSON_FLAG="--json"

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: gm-time.sh <time_of_day> <date> [--ticks N] [--duration \"<text>\"]"
    echo "Example: gm-time.sh \"Dawn\" \"16th day of Harvestmoon, Year 1247\""
    echo "         gm-time.sh \"Noon\" \"19th of Harvestmoon\" --duration \"3 days\""
    exit 1
fi

# No verb here either: $1 and $2 are the time of day and the date. A stray flag in
# either slot was written to the overview and then advanced every time-clock.
reject_bad_data_slot "time_of_day" "$1" || exit 1
reject_bad_data_slot "date" "$2" || exit 1

TIME_OF_DAY="$1"
DATE="$2"
shift 2

TICKS_FLAG=""
DURATION=""
while [ $# -gt 0 ]; do
    case "$1" in
        --ticks)
            if [ $# -lt 2 ]; then
                echo "[ERROR] --ticks requires a number" >&2
                exit 1
            fi
            TICKS_FLAG="$2"
            shift 2
            ;;
        --duration)
            if [ $# -lt 2 ]; then
                echo "[ERROR] --duration requires a value" >&2
                exit 1
            fi
            DURATION="$2"
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            echo "Usage: gm-time.sh <time_of_day> <date> [--ticks N] [--duration \"<text>\"]"
            exit 1
            ;;
    esac
done

require_active_campaign

$PYTHON_CMD "$LIB_DIR/time_manager.py" update "$TIME_OF_DAY" "$DATE" $JSON_FLAG
RESULT=$?
if [ $RESULT -ne 0 ]; then exit $RESULT; fi

# Pressure: time passing advances every advance_on=time threat clock,
# scaled to how much time actually passed (default 1).
RESOLVE_ARGS=(ticks)
if [ -n "$TICKS_FLAG" ]; then
    RESOLVE_ARGS+=(--ticks "$TICKS_FLAG")
fi
if [ -n "$DURATION" ]; then
    RESOLVE_ARGS+=(--duration "$DURATION")
fi
CLOCK_TICKS=$($PYTHON_CMD "$LIB_DIR/time_manager.py" "${RESOLVE_ARGS[@]}")
RESULT=$?
if [ $RESULT -ne 0 ]; then exit $RESULT; fi

if [ -n "$JSON_FLAG" ]; then
    $PYTHON_CMD "$LIB_DIR/threat_clocks.py" tick-time --ticks "$CLOCK_TICKS" >/dev/null
else
    $PYTHON_CMD "$LIB_DIR/threat_clocks.py" tick-time --ticks "$CLOCK_TICKS"
fi

# Reactivity: time passing can fire on_time consequences (e.g. nightfall, deadlines).
[ -z "$JSON_FLAG" ] && echo ""
if [ -n "$JSON_FLAG" ]; then
    # The envelope is the whole of stdout in JSON mode; the tick still runs and
    # still fires consequences, but its human report is suppressed.
    bash "$TOOLS_DIR/gm-consequence.sh" tick >/dev/null
else
    bash "$TOOLS_DIR/gm-consequence.sh" tick
fi
# Propagate the tick's status. Every earlier step in this script checks $? and
# exits on failure; this one used to discard it, so a failed consequence tick was
# reported as success.
exit $?
