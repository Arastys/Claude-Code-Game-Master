#!/usr/bin/env bash
# gm-statusline.sh - Always-on game HUD for the AI Game Master.
#
# Auto-derives a 3-line heads-up display from the active campaign's state
# files (character.json + campaign-overview.json). The agent does NOTHING
# extra: these files are already persisted every turn per the golden rule,
# and Claude Code re-runs this script after every assistant message.
#
# Wired via the project's .claude/settings.json `statusLine` setting, so it
# only overrides the global status line inside this repo.

input=$(cat)  # Claude Code JSON payload on stdin (unused; we read state files)

# Anchor to repo root via this script's location, not cwd.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Same redirection every other tool honours (tools/common.sh): tests point this
# at a fixture tree so they never read or write the player's live campaign. This
# script does not source common.sh — require_active_campaign would exit non-zero
# and Claude Code would show nothing at all.
WORLD_BASE="${GM_WORLD_STATE_BASE:-$ROOT/world-state}"

# 256-color palette (kept light: docs warn multi-line + heavy ANSI can glitch)
GREEN=$'\033[38;5;42m'
AMBER=$'\033[38;5;214m'
RED=$'\033[38;5;203m'
TEAL=$'\033[38;5;51m'
GOLD=$'\033[38;5;220m'
DIM=$'\033[38;5;244m'
FAINT=$'\033[38;5;238m'
BOLD=$'\033[1m'
RESET=$'\033[0m'
SEP="${DIM}·${RESET}"
SEPV="${FAINT}│${RESET}"   # vertical segment separator for the vitals line

# Horizontal rule that frames the HUD (drawn both above and below it) to set it
# apart from the conversation above and the input/permissions area below. Width
# auto-detects the terminal; falls back to 80 when stdout is not a tty (the usual
# case for a status-line subprocess). Args let the rule react to danger state:
#   divider [rule_color] [ornament_color]
# Defaults are a calm faint rule with a teal ornament.
divider() {
    local rule="${1:-$FAINT}" orn="${2:-$TEAL}"
    local cols mid half left right
    cols=$(tput cols 2>/dev/null)
    case "$cols" in ''|*[!0-9]*) cols=80 ;; esac
    [ "$cols" -gt 120 ] && cols=120
    [ "$cols" -lt 24  ] && cols=24
    mid="◆"                                  # single-width ornament (no wrap)
    half=$(( (cols - 1) / 2 ))
    printf -v left  '%*s' "$half" '';            left="${left// /─}"
    printf -v right '%*s' "$(( cols - 1 - half ))" ''; right="${right// /─}"
    printf '%s%s%s%s%s%s%s\n' "$rule" "$left" "$orn" "$mid" "$rule" "$right" "$RESET"
}

ACTIVE_FILE="$WORLD_BASE/active-campaign.txt"
if [ ! -f "$ACTIVE_FILE" ] || [ ! -s "$ACTIVE_FILE" ]; then
    divider
    printf '%s⚔ %sGM%s  %sno campaign yet%s  %s  %s%s/gm%s %sto begin — import a book, build a world, or jump into a one-shot%s\n' \
        "$TEAL" "$BOLD" "$RESET" "$DIM" "$RESET" "$SEP" "$BOLD" "$TEAL" "$RESET" "$DIM" "$RESET"
    divider
    exit 0
fi
ACTIVE=$(tr -d '[:space:]' < "$ACTIVE_FILE")

CAMP="$WORLD_BASE/campaigns/$ACTIVE"
CHAR="$CAMP/character.json"
OVER="$CAMP/campaign-overview.json"

if [ ! -f "$CHAR" ]; then
    divider
    printf '%s⚔ %sGM%s  %s%s%s  %sno character yet%s  %s  %s%s/gm%s %sto begin — "who are you in this world?"%s\n' \
        "$TEAL" "$BOLD" "$RESET" "$BOLD" "$ACTIVE" "$RESET" "$DIM" "$RESET" "$SEP" "$BOLD" "$TEAL" "$RESET" "$DIM" "$RESET"
    divider
    exit 0
fi

# --- Character fields -------------------------------------------------------
# The kit decides what this character HAS. Absent fields are omitted rather than
# rendered as "?" or an invented 0 — a world without coin has no gold line, and a
# world without classes advertises no missing class.
RULES="$CAMP/ruleset.json"
[ -f "$RULES" ] || RULES=/dev/null

# Row fields are read with IFS=$'\x1f' (ASCII Unit Separator), not a literal
# tab, and CR is stripped first. Two platform quirks combine badly otherwise:
# (1) tab is one of bash's "blank" IFS characters, so `read` collapses runs of
# them and silently drops empty fields — exactly the fields this design needs
# to stay empty (an absent stat must read as "", not disappear and shift every
# field after it); (2) this platform's jq writes CRLF, so an unstripped \r
# lands inside the last field (EXTRA). Neither is the --slurpfile risk the
# plan called out; both are verified on this platform, not assumed.
IFS=$'\x1f' read -r NAME RACE CLASS LEVEL AC GP HP_CUR HP_MAX XP_CUR XP_NEXT LOC EXTRA < <(
    jq -rn --slurpfile c "$CHAR" --slurpfile k "$RULES" '
      # Named to_label, not label: jq reserves "label" for its label/break
      # control-flow syntax, so `def label:` is a compile error.
      def to_label: gsub("_"; " ") | split(" ")
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
        , ( [ ($vitals[] | select($ch[.] != null) | (. | to_label) + " " + shown($ch[.]))
            , ($traits[] | select($ch[.] != null) | (. | to_label) + " " + ($ch[.] | tostring))
            ] | join("") )
        ] | @tsv' | tr -d '\r' | tr '\t' '\037')

# Conditions array -> status label; fall back to HP-derived state.
CONDS=$(jq -r '(.conditions // []) | map(ascii_downcase) | join(", ")' "$CHAR" 2>/dev/null)

# --- Overview fields (location/time/date) -----------------------------------
DATE="" ; TOD="" ; OLOC=""
if [ -f "$OVER" ]; then
    IFS=$'\t' read -r DATE TOD OLOC < <(
        jq -r '[ (.current_date // ""), (.time_of_day // ""), (.player_position.current_location // "") ] | @tsv' "$OVER"
    )
fi
# Prefer overview's live location if present.
[ -n "$OLOC" ] && LOC="$OLOC"

# --- HP bar -----------------------------------------------------------------
BAR_W=10
if [ "$HP_MAX" -gt 0 ] 2>/dev/null; then
    PCT=$(( HP_CUR * 100 / HP_MAX ))
    FILLED=$(( HP_CUR * BAR_W / HP_MAX ))
else
    PCT=0 ; FILLED=0
fi
[ "$FILLED" -gt "$BAR_W" ] && FILLED=$BAR_W
[ "$FILLED" -lt 0 ] && FILLED=0
EMPTY=$(( BAR_W - FILLED ))

# HP state drives the bar color AND the frame: calm when healthy, amber when
# wounded, a bold red glow when critical.
if   [ "$PCT" -ge 50 ]; then HPC="$GREEN"; STATE="Normal";   RULEC="$FAINT";        ORNC="$TEAL";          STATEC="$DIM"
elif [ "$PCT" -ge 25 ]; then HPC="$AMBER"; STATE="Wounded";  RULEC="$AMBER";        ORNC="$AMBER";         STATEC="$AMBER"
else                         HPC="$RED";   STATE="Critical"; RULEC="${BOLD}${RED}"; ORNC="${BOLD}${RED}";  STATEC="${BOLD}${RED}"
fi
# A named condition (poisoned, etc.) overrides the label but keeps the HP color.
[ -n "$CONDS" ] && { STATE="$CONDS"; [ "$PCT" -ge 50 ] && STATEC="$AMBER"; }

BAR=""
[ "$FILLED" -gt 0 ] && printf -v F "%${FILLED}s" && BAR="${F// /█}"
[ "$EMPTY"  -gt 0 ] && printf -v E "%${EMPTY}s"  && BAR="${BAR}${E// /░}"

# --- Render (3 lines) -------------------------------------------------------
# Build each line as a string, then emit. Clearer than one packed printf.

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

# Top rule — frames the HUD off from the conversation above.
divider "$RULEC" "$ORNC"

printf '%s\n' "$L1"
printf '%s\n' "$L2"

# Line 3: world clock (only if we have it)
if [ -n "$DATE" ] || [ -n "$TOD" ]; then
    printf '  %s%s %s %s%s\n' "$DIM" "$DATE" "$SEP" "$TOD" "$RESET"
fi

# Closing rule — separates the HUD from the input / permissions area below.
divider "$RULEC" "$ORNC"
