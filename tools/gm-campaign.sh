#!/bin/bash
# gm-campaign.sh - Multi-campaign management for GM tools
# Thin CLI wrapper - logic in lib/campaign_manager.py

# Source common utilities
source "$(dirname "$0")/common.sh"

# Pull --json out of the positional arguments before the case dispatches: several
# branches forward only "$1"/"$2", so a trailing flag would be silently dropped
# and the caller would get human text having asked for an envelope.
split_json_flag "$@"
set -- ${GM_ARGS+"${GM_ARGS[@]}"}

# The explicit flag and the ambient switch mean different things to the scalar
# verbs below. `path` and `active` are plumbing — gm-search.sh, gm-session.sh,
# gm-npc.sh and gm-playpack.sh all capture them in $( ) as bare strings. A
# caller who TYPED --json wants an envelope and will parse it; DM_JSON=1 set
# once in .env cannot know a caller is capturing a bare path, and enveloping it
# silently breaks every path built from it. Same reasoning that keeps
# time_manager.py's `ticks` bare. Capture the explicit flag BEFORE the ambient
# fold below overwrites JSON_FLAG, and forward EXPLICIT_JSON (never JSON_FLAG)
# for exactly those two verbs.
EXPLICIT_JSON="$JSON_FLAG"

# DM_JSON=1 is the documented global envelope switch (lib/cli_output.py), and the
# manager honours it with no flag in sight — so fold it into JSON_FLAG here, or the
# human-only guards below would print their text ahead of an envelope. Every
# verb OTHER than path/active is genuine structured output and forwards this
# folded variable, honouring the ambient switch same as before.
[ "${DM_JSON:-}" = "1" ] && JSON_FLAG="--json"

ACTION=$1
shift

show_usage() {
    echo "Campaign Manager"
    echo "================"
    echo ""
    echo "Usage: gm-campaign.sh <action> [args]"
    echo ""
    echo "Actions:"
    echo "  list                  - List all campaigns"
    echo "  switch <name>         - Switch to a different campaign"
    echo "  create <name>         - Create a new campaign"
    echo "  delete <name> [--yes] - Delete a campaign (requires confirmation)"
    echo "  info [name]           - Show campaign details (defaults to active)"
    echo "  active                - Show active campaign name"
    echo "  path [name]           - Show campaign directory path"
    echo ""
    echo "Examples:"
    echo "  gm-campaign.sh list                     # See all campaigns"
    echo "  gm-campaign.sh create conan             # Create campaign for Conan"
    echo "  gm-campaign.sh switch theron            # Switch to Theron's campaign"
    echo "  gm-campaign.sh info                     # Info about current campaign"
    echo ""
    echo "Current active campaign: $(get_active_campaign)"
}

case "$ACTION" in
    "list")
        $PYTHON_CMD "$LIB_DIR/campaign_manager.py" list $JSON_FLAG
        ;;

    "switch")
        if [ -z "$1" ]; then
            echo "Usage: gm-campaign.sh switch <campaign_name>"
            echo ""
            echo "Available campaigns:"
            # No $JSON_FLAG here: this listing is decoration inside a usage error
            # that exits 1 — the flag is refused on this path, not absorbed.
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" list
            exit 1
        fi
        $PYTHON_CMD "$LIB_DIR/campaign_manager.py" switch "$1" $JSON_FLAG
        ;;

    "create")
        if [ -z "$1" ]; then
            echo "Usage: gm-campaign.sh create <name> [--campaign-name \"Display Name\"]"
            echo ""
            echo "Example: gm-campaign.sh create conan --campaign-name \"The Barbarian's Destiny\""
            exit 1
        fi
        NAME="$1"
        shift
        $PYTHON_CMD "$LIB_DIR/campaign_manager.py" create "$NAME" "$@" $JSON_FLAG
        ;;

    "delete")
        # A flag in the name slot means the name was omitted — never treat it as one.
        case "${1:-}" in
            ""|-*)
                echo "Usage: gm-campaign.sh delete <campaign_name> [--yes]"
                exit 1
                ;;
        esac
        CAMPAIGN_NAME="$1"
        shift

        # --yes / --confirm: delete without prompting (non-interactive use)
        ASSUME_YES=0
        for arg in "$@"; do
            case "$arg" in
                --yes|--confirm) ASSUME_YES=1 ;;
            esac
        done

        # Show info about what will be deleted. The preview is for a human at the
        # confirmation prompt below; in --json mode it would print a second envelope
        # ahead of the delete's own, so the whole preview is skipped.
        if [ -z "$JSON_FLAG" ]; then
            echo "Campaign to delete: $CAMPAIGN_NAME"
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" info "$CAMPAIGN_NAME"
            echo ""
        fi

        CONFIRM="yes"
        if [ "$ASSUME_YES" -eq 0 ]; then
            if [ ! -t 0 ]; then
                error "No terminal to confirm on. Re-run with --yes to delete non-interactively."
                exit 1
            fi
            read -p "Are you sure you want to DELETE this campaign? (type 'yes' to confirm): " CONFIRM
        fi

        if [ "$CONFIRM" = "yes" ]; then
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" delete "$CAMPAIGN_NAME" --confirm $JSON_FLAG
        else
            echo "Deletion cancelled."
        fi
        ;;

    "info")
        if [ -z "$1" ]; then
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" info $JSON_FLAG
        else
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" info "$1" $JSON_FLAG
        fi
        ;;

    "active")
        # Bare-string plumbing verb: forward the explicit flag only, never the
        # ambient-folded one (see EXPLICIT_JSON above).
        $PYTHON_CMD "$LIB_DIR/campaign_manager.py" active $EXPLICIT_JSON
        ;;

    "path")
        # Bare-string plumbing verb: forward the explicit flag only, never the
        # ambient-folded one (see EXPLICIT_JSON above).
        if [ -z "$1" ]; then
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" path $EXPLICIT_JSON
        else
            $PYTHON_CMD "$LIB_DIR/campaign_manager.py" path "$1" $EXPLICIT_JSON
        fi
        ;;

    "")
        show_usage
        ;;

    *)
        echo "Unknown action: $ACTION"
        echo ""
        show_usage
        exit 1
        ;;
esac
