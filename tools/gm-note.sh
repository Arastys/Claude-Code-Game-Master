#!/bin/bash
# gm-note.sh - Record immutable world facts (wrapper for note_manager.py)

source "$(dirname "$0")/common.sh"

split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}
# DM_JSON=1 is the documented global envelope switch (lib/cli_output.py), and the
# manager honours it with no flag in sight — so fold it into JSON_FLAG here, or the
# human-only guards below would print their text ahead of an envelope.
[ "${DM_JSON:-}" = "1" ] && JSON_FLAG="--json"

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
    reject_bad_data_slot "category" "$1" || exit 1
    reject_bad_data_slot "fact" "$2" || exit 1
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
