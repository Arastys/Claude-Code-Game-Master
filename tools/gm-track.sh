#!/bin/bash
# gm-track.sh - World tracks (thin wrapper for world_tracks.py)
#
#   gm-track.sh list                                  Show all world tracks
#   gm-track.sh add "Y Cof" 6 [--current N] [--note "..."]
#              [--thresholds-json '[{"at":3,"consequence":"..."}]']
#                                                     New world-level meter
#   gm-track.sh adjust "Y Cof" --delta 2              Move it (clamped to [0,max])
#   gm-track.sh set "Y Cof" --value 4                 Set it absolutely
#   gm-track.sh remove "Y Cof"                        Remove a track
#
# Thresholds crossed while CLIMBING fire into the consequence engine.
# Crossings in BOTH directions are reported. All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/world_tracks.py" "$@"
