#!/usr/bin/env bash
#
# srt-orchestrate.sh — Deterministic pipeline for srt-translate skill
#
# Invokes an AI coding agent in headless mode per phase group, each with a
# fresh context containing ONLY the instructions relevant to that phase.
# This eliminates attention degradation from irrelevant instructions.
# Claude is the default backend; Codex is opt-in via --agent codex or --codex.
#
# Usage:
#   ./scripts/orchestrate.sh /path/to/video.mkv [--resume] [--phase N] [--speech-sync] [--agent claude|codex]
#   ./scripts/orchestrate.sh /path/to/video.mkv --augment-missing [--agent claude|codex]
#
# Requirements:
#   - claude CLI in PATH for the default backend, or codex CLI in PATH with --agent codex
#   - ffmpeg, ffprobe, python3
#   - scripts/venv/ with ffsubsync, webrtcvad, pysubs2
#
# Environment:
#   CLAUDE_CODE_MAX_OUTPUT_TOKENS  (default: 128000)
#   SKILL_DIR                      (default: auto-detected from script location)
#   LOG_DIR                        (default: /mnt/nas/video/.claude/logs/srt-translate)
#   MODEL_SETUP                    (default: sonnet)  — Phase 0-1: extraction, sync, classification
#   MODEL_TRANSLATE                (default: opus)    — Phase 2: EN→NL translation
#   MODEL_POST                     (default: sonnet)  — Phase 3-9: post-processing, QC
#

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${SKILL_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

LOG_DIR="${LOG_DIR:-/mnt/nas/video/.claude/logs/srt-translate}"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-128000}"

# Model selection per phase — optimizes cost by matching model capability to task complexity.
# Phase 0-1 (setup): tool orchestration + simple classification → Sonnet
# Phase 2 (translation): professional EN→NL literary translation → Opus
# Phase 3-9 (post-processing): script execution + linguistic review → Sonnet
MODEL_SETUP="${MODEL_SETUP:-sonnet}"
MODEL_TRANSLATE="${MODEL_TRANSLATE:-opus}"
MODEL_POST="${MODEL_POST:-sonnet}"

# Max cues per translation batch before forcing a context-clearing sub-invocation
BATCH_SIZE=200
MAX_BATCHES_PER_INVOCATION=6

# ─── Argument parsing ──────────────────────────────────────────────────────

RESUME=false
FRESH=false
POLISH=false
AUGMENT_MISSING=false
START_PHASE=""
SPEECH_SYNC=false
KEEP_SDH=false
KEEP_WORK=false
NO_EMBEDDED=false  # if true: skip embedded-subtitle extraction, force external .en.srt
MAX_BATCHES=0  # 0 = unlimited
VIDEO_FILE=""
SOURCE_SRT_OVERRIDE=""
OUTPUT_SRT_OVERRIDE=""
SOURCE_LANGUAGE="English"
SOURCE_READY=false
AGENT="claude"     # claude by default; set via --agent codex or --codex to use Codex
EFFORT="medium"    # passed to claude -p --effort (low|medium|high|xhigh|max). Ignored by Codex.
BUDGET_CAP_USD=""  # passed to claude -p --max-budget-usd, per invocation. Ignored by Codex.
MODEL_OVERRIDE=""  # if set, overrides MODEL_SETUP/TRANSLATE/POST
MODEL_SETUP_OVERRIDE=""      # --model-setup: wins over --model and env var
MODEL_TRANSLATE_OVERRIDE=""  # --model-translation: wins over --model and env var
MODEL_POST_OVERRIDE=""       # --model-post: wins over --model and env var

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)       RESUME=true; shift ;;
        --fresh)        FRESH=true; shift ;;
        --polish)       POLISH=true; shift ;;
        --augment-missing) AUGMENT_MISSING=true; shift ;;
        --phase)        START_PHASE="$2"; shift 2 ;;
        --speech-sync)  SPEECH_SYNC=true; shift ;;
        --keep-sdh)     KEEP_SDH=true; shift ;;
        --keep-work)    KEEP_WORK=true; shift ;;
        --no-embedded)  NO_EMBEDDED=true; shift ;;
        --source-srt)   SOURCE_SRT_OVERRIDE="$2"; shift 2 ;;
        --source-language) SOURCE_LANGUAGE="$2"; shift 2 ;;
        --output-srt)   OUTPUT_SRT_OVERRIDE="$2"; shift 2 ;;
        --source-ready) SOURCE_READY=true; shift ;;
        --max-batches)  MAX_BATCHES="$2"; shift 2 ;;
        --effort)       EFFORT="$2"; shift 2 ;;
        --budget-cap-usd) BUDGET_CAP_USD="$2"; shift 2 ;;
        --agent)        AGENT="$2"; shift 2 ;;
        --codex)        AGENT="codex"; shift ;;
        --model)        MODEL_OVERRIDE="$2"; shift 2 ;;
        --model-setup)       MODEL_SETUP_OVERRIDE="$2"; shift 2 ;;
        --model-translation) MODEL_TRANSLATE_OVERRIDE="$2"; shift 2 ;;
        --model-post)        MODEL_POST_OVERRIDE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 /path/to/video.mkv [--resume] [--fresh] [--polish] [--augment-missing] [--phase N] [--speech-sync] [--keep-sdh] [--max-batches N] [--agent AGENT]"
            echo ""
            echo "Options:"
            echo "  --resume        Resume from last checkpoint"
            echo "  --fresh         Delete any checkpoint and start from phase 0 (non-interactive)"
            echo "  --polish        Skip translation — run post-processing on existing .nl.srt"
            echo "                  Runs setup (Phase 0-1) then jumps straight to Phase 3."
            echo "                  Saves ~80%% of token cost vs a full retranslation."
            echo "  --augment-missing"
            echo "                  Add only missing burned-in/title-card cues to an existing .nl.srt."
            echo "                  Runs setup/title-card detection, translates missing cues only, then merges."
            echo "  --phase N       Start from phase N (0, 2, 3)"
            echo "  --speech-sync   Run Phase 10 (speech sync) after Phase 9"
            echo "  --keep-sdh      Keep SDH cues (default: remove them before translation)"
            echo "  --keep-work     Preserve work directory after successful completion (for debugging)"
            echo "  --no-embedded   Skip embedded subtitle extraction; use the existing external .en.srt only."
            echo "                  Use when the video has burn-in subs or embedded subs covering only foreign-language parts."
            echo "  --source-srt PATH"
            echo "                  Use this subtitle file as source instead of VIDEO_BASE.en.srt."
            echo "  --source-language LANG"
            echo "                  Source subtitle language for translation prompts. Default: English"
            echo "  --output-srt PATH"
            echo "                  Write final Dutch subtitle here instead of VIDEO_BASE.nl.srt."
            echo "  --source-ready  Treat --source-srt as already synced/classified input; skip setup and start at translation."
            echo "  --max-batches N Limit translation to N batches (for testing)"
            echo "  --effort LEVEL  Thinking effort: low|medium|high|xhigh|max (applies to every invocation)"
            echo "  --agent AGENT   Agent backend to use: claude or codex. Default: claude"
            echo "  --codex         Convenience alias for --agent codex"
            echo "  --budget-cap-usd AMOUNT"
            echo "                  Hard cost cap in USD applied PER CLAUDE INVOCATION (not per run). Ignored by Codex."
            echo "                  If exceeded, claude aborts with exit 1 and the phase fails."
            echo "                  Scope per invocation:"
            echo "                    Setup        : one invocation (Phases 0-1)"
            echo "                    Translation  : one invocation per group of up to 6 batches"
            echo "                                   (= up to 1200 cues per invocation)"
            echo "                    Post         : three invocations (structural / review / finalize)"
            echo "                  See cost_log.jsonl for historical per-invocation costs."
            echo "  --model MODEL   Override MODEL_SETUP, MODEL_TRANSLATE and MODEL_POST."
            echo "                  For Codex, Claude aliases (sonnet/opus/haiku) are ignored so Codex uses its configured default."
            echo "                  Use MODEL_* env vars for per-phase control."
            echo "  --model-setup MODEL        Override model for Phases 0-1 (wins over --model and MODEL_SETUP env var)"
            echo "  --model-translation MODEL  Override model for Phase 2 (wins over --model and MODEL_TRANSLATE env var)"
            echo "  --model-post MODEL         Override model for Phases 3-10 (wins over --model and MODEL_POST env var)"
            exit 0
            ;;
        -*)             echo "Unknown option: $1" >&2; exit 1 ;;
        *)              VIDEO_FILE="$1"; shift ;;
    esac
done

if [[ -n "$MODEL_OVERRIDE" ]]; then
    MODEL_SETUP="$MODEL_OVERRIDE"
    MODEL_TRANSLATE="$MODEL_OVERRIDE"
    MODEL_POST="$MODEL_OVERRIDE"
fi
[[ -n "$MODEL_SETUP_OVERRIDE"     ]] && MODEL_SETUP="$MODEL_SETUP_OVERRIDE"
[[ -n "$MODEL_TRANSLATE_OVERRIDE" ]] && MODEL_TRANSLATE="$MODEL_TRANSLATE_OVERRIDE"
[[ -n "$MODEL_POST_OVERRIDE"      ]] && MODEL_POST="$MODEL_POST_OVERRIDE"

case "$AGENT" in
    claude|codex) ;;
    *) echo "Error: Invalid --agent: $AGENT (valid: claude, codex)" >&2; exit 1 ;;
esac

if $POLISH && $AUGMENT_MISSING; then
    echo "Error: --polish and --augment-missing are mutually exclusive." >&2
    exit 1
fi

if [[ -z "$VIDEO_FILE" ]]; then
    echo "Error: No video file specified." >&2
    echo "Usage: $0 /path/to/video.mkv [--resume] [--phase N] [--speech-sync] [--keep-sdh]" >&2
    exit 1
fi

if [[ ! -f "$VIDEO_FILE" ]]; then
    echo "Error: Video file not found: $VIDEO_FILE" >&2
    exit 1
fi

# ─── Path setup ─────────────────────────────────────────────────────────────

VIDEO_DIR="$(cd "$(dirname "$VIDEO_FILE")" && pwd)"
VIDEO_BASENAME="$(basename "$VIDEO_FILE" | sed -E 's/\.(en|nl)\.(srt|sub|ass)$/.\2/' | sed 's/\.[^.]*$//')"
VIDEO_FILE="$(cd "$VIDEO_DIR" && pwd)/$(basename "$VIDEO_FILE")"

CHECKPOINT_FILE="${LOG_DIR}/${VIDEO_BASENAME}_checkpoint.md"
BATCH_CONTEXT_DIR="${LOG_DIR}/batch_context_${VIDEO_BASENAME}"
OUTPUT_SRT="${VIDEO_DIR}/${VIDEO_BASENAME}.nl.srt"
SOURCE_SRT="${VIDEO_DIR}/${VIDEO_BASENAME}.en.srt"
WORK_DIR="${LOG_DIR}/work_${VIDEO_BASENAME}"
GLOSSARY_FILE="${WORK_DIR}/translation_glossary.md"
HANDOFF_FILE="${BATCH_CONTEXT_DIR}/invocation_handoff.txt"

if [[ -n "$SOURCE_SRT_OVERRIDE" ]]; then
    SOURCE_SRT="$(cd "$(dirname "$SOURCE_SRT_OVERRIDE")" && pwd)/$(basename "$SOURCE_SRT_OVERRIDE")"
fi
if [[ -n "$OUTPUT_SRT_OVERRIDE" ]]; then
    OUTPUT_SRT="$(cd "$(dirname "$OUTPUT_SRT_OVERRIDE")" && pwd)/$(basename "$OUTPUT_SRT_OVERRIDE")"
fi

mkdir -p "$LOG_DIR" "$BATCH_CONTEXT_DIR" "$WORK_DIR"

# ─── Skill file paths ──────────────────────────────────────────────────────

SHARED_CONSTRAINTS="${SKILL_DIR}/base/shared-constraints.md"
WORKFLOW_SETUP="${SKILL_DIR}/base/workflow-setup.md"
WORKFLOW_TRANSLATE="${SKILL_DIR}/base/workflow-translate.md"
WORKFLOW_POST_STRUCTURAL="${SKILL_DIR}/base/workflow-post-structural.md"
WORKFLOW_POST_REVIEW="${SKILL_DIR}/base/workflow-post-review.md"
WORKFLOW_POST_FINALIZE="${SKILL_DIR}/base/workflow-post-finalize.md"

# References (loaded selectively per phase)
COMMON_ERRORS="${SKILL_DIR}/references/common-errors.md"
DUTCH_PATTERNS="${SKILL_DIR}/references/dutch-patterns.md"
TRANSLATION_DEFAULTS="${SKILL_DIR}/references/translation-defaults.md"

# Exemplars (loaded for Phase 2)
EXEMPLAR_CONDENSATION="${SKILL_DIR}/references/exemplars/condensation.md"
EXEMPLAR_IDIOM="${SKILL_DIR}/references/exemplars/idiom-adaptation.md"
EXEMPLAR_V2="${SKILL_DIR}/references/exemplars/v2-word-order.md"
EXEMPLAR_DOCUMENTARY="${SKILL_DIR}/references/exemplars/documentary.md"
EXEMPLAR_DRAMA="${SKILL_DIR}/references/exemplars/drama.md"
EXEMPLAR_DUAL_SPEAKER="${SKILL_DIR}/references/exemplars/dual-speaker.md"

# ─── Helper functions ───────────────────────────────────────────────────────

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

# Read a value from the checkpoint file
checkpoint_get() {
    local key="$1"
    grep -oP "(?<=\*\*${key}:\*\* ).*" "$CHECKPOINT_FILE" 2>/dev/null \
        | tr -d '\r`' \
        | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
        || echo ""
}

# Count cues in an SRT file (handles both Unix and Windows line endings)
count_cues() {
    local n
    # write_srt emits UTF-8-SIG; strip UTF-8 BOM so cue 1 is counted.
    n="$(tr -d '\r' < "$1" 2>/dev/null | sed $'1s/^\xEF\xBB\xBF//' | grep -cE '^[0-9]+$')" || true
    echo "${n:-0}"
}

checkpoint_set() {
    local key="$1"
    local value="$2"
    local line="- **${key}:** ${value}"

    if [[ ! -f "$CHECKPOINT_FILE" ]]; then
        return 0
    fi

    if grep -q "^- \*\*${key}:\*\*" "$CHECKPOINT_FILE"; then
        perl -0pi -e "s{^- \\Q**${key}:**\\E .*}{$line}m" "$CHECKPOINT_FILE"
    else
        printf '\n%s\n' "$line" >> "$CHECKPOINT_FILE"
    fi
}

is_claude_model_alias() {
    case "${1:-}" in
        sonnet|opus|haiku) return 0 ;;
        *) return 1 ;;
    esac
}

effective_model_label() {
    local model="${1:-}"
    if [[ "$AGENT" == "codex" ]]; then
        if [[ -z "$model" ]] || is_claude_model_alias "$model"; then
            echo "codex default"
        else
            echo "$model"
        fi
    else
        echo "${model:-default}"
    fi
}

extract_imdb_id() {
    local name
    name="$(basename "$VIDEO_FILE")"
    if [[ "$name" =~ imdb-tt([0-9]+) ]]; then
        echo "${BASH_REMATCH[1]}"
    elif [[ "$name" =~ tt([0-9]+) ]]; then
        echo "${BASH_REMATCH[1]}"
    else
        echo ""
    fi
}

write_source_ready_checkpoint() {
    [[ -f "$SOURCE_SRT" ]] || die "--source-ready requires source SRT: $SOURCE_SRT"

    local source_cues
    source_cues="$(count_cues "$SOURCE_SRT")"
    [[ "$source_cues" -gt 0 ]] || die "--source-ready source has no cues: $SOURCE_SRT"

    local framerate="25"
    local detected_rate
    detected_rate="$(ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate \
        -of default=noprint_wrappers=1:nokey=1 "$VIDEO_FILE" 2>/dev/null || true)"
    if [[ "$detected_rate" =~ ^([0-9]+)/([0-9]+)$ && "${BASH_REMATCH[2]}" -ne 0 ]]; then
        local rounded
        rounded="$(awk -v n="${BASH_REMATCH[1]}" -v d="${BASH_REMATCH[2]}" 'BEGIN { printf "%.0f", n / d }')"
        case "$rounded" in
            24|25) framerate="$rounded" ;;
        esac
    fi

    cat > "$CHECKPOINT_FILE" <<EOF
# Translation Checkpoint

## Video
- **File:** ${VIDEO_FILE}
- **Source:** ${SOURCE_SRT}
- **Output:** ${OUTPUT_SRT}

## Progress
- **Current phase:** 1 (source-ready checkpoint)
- **Next phase:** 2 (translation)

## Phase 1 Results
- **Framerate:** ${framerate}
- **Classification:** documentary
- **Source cues:** ${source_cues}
- **Source language:** ${SOURCE_LANGUAGE}
- **Source type:** external ready source SRT
- **Sync method:** skipped (--source-ready)
- **Title cards:** skipped (--source-ready source is timing/content authority)

## Terminology
- Michail Gorbatsjov
- Michail Sergejevitsj Gorbatsjov
- Raisa Gorbatsjova
- Werner Herzog
- Sovjet-Unie
- Koude Oorlog
- glasnost
- perestrojka

## Register
- Historical/biographical documentary with narration, archival material, and interview segments.
- Use clear, formal documentary Dutch for narration.
- Use respectful spoken Dutch for interviews with Gorbatsjov and political figures.
- Translate from ${SOURCE_LANGUAGE} to Dutch; do not assume the source is English.
EOF

    log "Source-ready checkpoint written: $CHECKPOINT_FILE"
    log "Source language: ${SOURCE_LANGUAGE} | Source cues: ${source_cues} | Framerate: ${framerate}"
}

# Background heartbeat: emits a log line every HEARTBEAT_INTERVAL seconds
# Usage: _run_heartbeat PID DESCRIPTION [MONITOR_FILE]
_run_heartbeat() {
    local pid="$1"
    local description="$2"
    local monitor_file="${3:-}"
    local interval="${HEARTBEAT_INTERVAL:-60}"
    local start_time=$SECONDS
    local last_cues=-1

    while kill -0 "$pid" 2>/dev/null; do
        sleep "$interval"
        kill -0 "$pid" 2>/dev/null || break

        local elapsed=$(( SECONDS - start_time ))
        local min=$(( elapsed / 60 ))

        local status=""
        if [[ -n "$monitor_file" ]]; then
            if [[ -f "$monitor_file" ]]; then
                local cues
                cues="$(count_cues "$monitor_file")"
                if [[ "$last_cues" -ge 0 && "$cues" -gt "$last_cues" ]]; then
                    status="${cues} cues (+$(( cues - last_cues )))"
                elif [[ "$last_cues" -ge 0 && "$cues" -eq "$last_cues" ]]; then
                    status="${cues} cues (unchanged)"
                else
                    status="${cues} cues"
                fi
                last_cues="$cues"
            else
                status="awaiting output file"
            fi
        fi

        log "♥ ${description} — ${min}m elapsed${status:+, ${status}}"
    done
}

# Invoke the configured agent with a prompt assembled from files + inline instructions
# Usage: invoke_agent [--model MODEL] [--heartbeat-file FILE] "task description" file1.md file2.md ... <<< "inline prompt"
invoke_agent() {
    case "$AGENT" in
        claude) invoke_claude "$@" ;;
        codex)  invoke_codex "$@" ;;
        *)      die "Invalid agent backend: $AGENT" ;;
    esac
}

invoke_claude() {
    local model=""
    local heartbeat_file=""

    # Parse optional flags
    while [[ "${1:-}" == --* ]]; do
        case "$1" in
            --model) model="$2"; shift 2 ;;
            --heartbeat-file) heartbeat_file="$2"; shift 2 ;;
            *) break ;;
        esac
    done

    local description="$1"
    shift
    local prompt=""

    # Concatenate all file arguments
    for f in "$@"; do
        if [[ -f "$f" ]]; then
            prompt+="$(cat "$f")"$'\n\n---\n\n'
        else
            log "WARNING: File not found, skipping: $f"
        fi
    done

    # Append stdin (inline prompt) if available
    if [[ ! -t 0 ]]; then
        prompt+="$(cat)"
    fi

    log "Invoking Claude: $description"
    [[ -n "$model" ]] && log "  Model: $model"
    log "  Context files: $*"

    # Build optional flags
    local extra_args=()
    if [[ -n "$model" ]]; then
        extra_args+=(--model "$model")
    fi
    if [[ -n "${EFFORT:-}" ]]; then
        extra_args+=(--effort "$EFFORT")
    fi
    if [[ -n "${BUDGET_CAP_USD:-}" ]]; then
        extra_args+=(--max-budget-usd "$BUDGET_CAP_USD")
    fi

    # --allowedTools ensures non-interactive execution
    # Unset CLAUDECODE to allow running from within a Claude Code session
    # cd to SKILL_DIR so relative paths like scripts/run-venv.sh resolve correctly
    # and Bash(scripts/*) permission pattern matches them regardless of launch cwd.
    local json_out
    json_out="$(mktemp "${LOG_DIR}/claude_json_XXXXXX.tmp")"
    local stderr_log="${LOG_DIR}/claude_stderr_$(date +%s).log"

    # Run claude -p in background with heartbeat monitoring
    (cd "$SKILL_DIR" && echo "$prompt" | env -u CLAUDECODE claude -p \
        "${extra_args[@]}" \
        --allowedTools "Read,Glob,Grep,Edit,Write,Bash(python3:*),Bash(cat:*),Bash(grep:*),Bash(wc:*),Bash(mv:*),Bash(cp:*),Bash(mkdir:*),Bash(ffprobe:*),Bash(ffmpeg:*),Bash(head:*),Bash(tail:*),Bash(sed:*),Bash(scripts/*)" \
        --output-format json \
        2>"$stderr_log") > "$json_out" &
    local claude_pid=$!

    _run_heartbeat "$claude_pid" "$description" "$heartbeat_file" &
    local heartbeat_pid=$!

    # Trap signals to prevent orphaned background processes.
    # Without this, Ctrl+C or SIGTERM kills the shell but leaves claude + heartbeat running
    # (the orchestrator is typically launched detached: `bash orchestrate.sh > log 2>&1 &`
    # so SIGHUP is not delivered to children on parent exit).
    trap "kill $claude_pid $heartbeat_pid 2>/dev/null; exit 130" INT TERM

    # Use || to prevent set -e from aborting on non-zero claude exit.
    # Without this, a claude timeout/failure triggers set -e BEFORE exit_code=$? runs,
    # silently killing the script — the exact failure mode this feature is meant to prevent.
    local exit_code
    wait "$claude_pid" && exit_code=0 || exit_code=$?

    # Stop heartbeat cleanly and remove signal trap
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    trap - INT TERM

    # Extract and log cost/usage data
    if [[ -s "$json_out" ]] && /usr/bin/jq -e '.usage' "$json_out" >/dev/null 2>&1; then
        local cost_log="${LOG_DIR}/cost_log.jsonl"
        /usr/bin/jq -c '{
            timestamp: now | strftime("%Y-%m-%dT%H:%M:%SZ"),
            description: $desc,
            model: $mdl,
            total_cost_usd: .total_cost_usd,
            input_tokens: .usage.input_tokens,
            output_tokens: .usage.output_tokens,
            cache_creation_input_tokens: .usage.cache_creation_input_tokens,
            cache_read_input_tokens: .usage.cache_read_input_tokens
        }' --arg desc "$description" --arg mdl "${model:-default}" \
            "$json_out" >> "$cost_log" 2>/dev/null

        local cost input_tok output_tok cache_read
        cost="$(/usr/bin/jq -r '.total_cost_usd // "n/a"' "$json_out")"
        input_tok="$(/usr/bin/jq -r '.usage.input_tokens // "n/a"' "$json_out")"
        output_tok="$(/usr/bin/jq -r '.usage.output_tokens // "n/a"' "$json_out")"
        cache_read="$(/usr/bin/jq -r '.usage.cache_read_input_tokens // 0' "$json_out")"
        log "  Cost: \$${cost} | Input: ${input_tok} (cached: ${cache_read}) | Output: ${output_tok}"
    fi

    # Print the text result (equivalent to old --output-format text behavior)
    /usr/bin/jq -r '.result // empty' "$json_out" 2>/dev/null
    rm -f "$json_out"

    if [[ $exit_code -ne 0 ]]; then
        if grep -q "Exceeded USD budget" "$stderr_log" 2>/dev/null; then
            log "ERROR: Budget cap (\$${BUDGET_CAP_USD}) exceeded for: $description"
            log "  Raise --budget-cap-usd or inspect ${LOG_DIR}/cost_log.jsonl for historical costs."
        else
            log "WARNING: Claude exited with code $exit_code for: $description"
        fi
    fi
    return $exit_code
}


invoke_codex() {
    local model=""
    local heartbeat_file=""

    while [[ "${1:-}" == --* ]]; do
        case "$1" in
            --model) model="$2"; shift 2 ;;
            --heartbeat-file) heartbeat_file="$2"; shift 2 ;;
            *) break ;;
        esac
    done

    local description="$1"
    shift
    local prompt=""

    for f in "$@"; do
        if [[ -f "$f" ]]; then
            prompt+="$(cat "$f")"$'\n\n---\n\n'
        else
            log "WARNING: File not found, skipping: $f"
        fi
    done

    if [[ ! -t 0 ]]; then
        prompt+="$(cat)"
    fi

    log "Invoking Codex: $description"
    log "  Codex model: $(effective_model_label "$model")"
    if [[ -n "$model" ]] && is_claude_model_alias "$model"; then
        log "  Ignored Claude model alias for Codex: $model"
    fi
    log "  Context files: $*"

    local extra_args=(--cd "$SKILL_DIR" --sandbox workspace-write --skip-git-repo-check)
    extra_args+=(--add-dir "$SKILL_DIR" --add-dir "$VIDEO_DIR" --add-dir "$LOG_DIR")
    extra_args+=(--add-dir "$(dirname "$SOURCE_SRT")" --add-dir "$(dirname "$OUTPUT_SRT")")

    case "$model" in
        ""|sonnet|opus|haiku)
            ;;
        *)
            extra_args+=(--model "$model")
            ;;
    esac

    local output_file
    output_file="$(mktemp "${LOG_DIR}/codex_result_XXXXXX.tmp")"
    local run_log="${LOG_DIR}/codex_run_$(date +%s).log"
    extra_args+=(--output-last-message "$output_file")

    (cd "$SKILL_DIR" && printf '%s\n' "$prompt" | codex exec "${extra_args[@]}" - >"$run_log" 2>&1) &
    local codex_pid=$!

    _run_heartbeat "$codex_pid" "$description" "$heartbeat_file" &
    local heartbeat_pid=$!

    trap "kill $codex_pid $heartbeat_pid 2>/dev/null; exit 130" INT TERM

    local exit_code
    wait "$codex_pid" && exit_code=0 || exit_code=$?

    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    trap - INT TERM

    if [[ -s "$output_file" ]]; then
        cat "$output_file"
    fi
    rm -f "$output_file"

    if [[ $exit_code -ne 0 ]]; then
        log "WARNING: Codex exited with code $exit_code for: $description"
        log "  See Codex run log: $run_log"
    fi
    return $exit_code
}

# ─── Phase Group: Setup (Phases 0-1) ───────────────────────────────────────

run_title_card_detection() {
    local mode="${1:-merge}"
    log "═══ Setup: Title Card Detection (Phase 0b) ═══"

    if [[ ! -f "$SOURCE_SRT" ]]; then
        log "Title cards skipped: source SRT not found: $SOURCE_SRT"
        checkpoint_set "Title cards" "skipped (source SRT not found)"
        return 0
    fi

    if grep -q '\[TITLE CARD:' "$SOURCE_SRT"; then
        log "Title cards already present in source SRT; not re-running detection."
        checkpoint_set "Source cues" "$(count_cues "$SOURCE_SRT")"
        checkpoint_set "Title cards" "already present in source SRT"
        return 0
    fi

    local imdb_id
    imdb_id="$(extract_imdb_id)"
    if [[ -z "$imdb_id" ]]; then
        log "Title cards skipped: no IMDb ID found in video filename."
        checkpoint_set "Title cards" "skipped (no IMDb ID found in filename)"
        return 0
    fi

    local foreign_srt="${WORK_DIR}/foreign.srt"
    local title_cards_srt="${WORK_DIR}/title_cards.srt"
    rm -f "$title_cards_srt"

    local fetch_status=0
    # Privacy boundary: fetch by IMDb ID only; local paths stay out of OpenSubtitles.
    "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/fetch_foreign_subtitle.py" \
        "$imdb_id" \
        --output "$foreign_srt" \
        --timeout 15 || fetch_status=$?

    if [[ ! -s "$foreign_srt" ]]; then
        case "$fetch_status" in
            1)
                log "Title cards skipped: no usable foreign subtitle found for tt${imdb_id}."
                checkpoint_set "Title cards" "skipped (IMDb ID found: tt${imdb_id}; no usable foreign subtitle found)"
                ;;
            2)
                log "Title cards skipped: OpenSubtitles unavailable or API key not configured."
                checkpoint_set "Title cards" "skipped (IMDb ID found: tt${imdb_id}; OpenSubtitles unavailable or API key not configured)"
                ;;
            *)
                log "Title cards skipped: foreign subtitle fetch failed with status ${fetch_status}."
                checkpoint_set "Title cards" "skipped (IMDb ID found: tt${imdb_id}; foreign subtitle fetch failed: ${fetch_status})"
                ;;
        esac
        return 0
    fi

    local detect_status=0
    "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/detect_title_cards.py" \
        "$SOURCE_SRT" \
        "$foreign_srt" \
        --output "$title_cards_srt" || detect_status=$?

    if [[ ! -s "$title_cards_srt" ]]; then
        if [[ "$detect_status" -eq 2 ]]; then
            log "Title cards skipped: detector could not parse subtitle files."
            checkpoint_set "Title cards" "skipped (IMDb ID found: tt${imdb_id}; detector parse error)"
        else
            log "Title cards: none detected from foreign subtitle."
            checkpoint_set "Title cards" "none detected (IMDb ID found: tt${imdb_id}; foreign subtitle fetched)"
        fi
        return 0
    fi

    local cards_count
    cards_count="$(count_cues "$title_cards_srt")"
    if [[ "$mode" == "detect-only" ]]; then
        checkpoint_set "Title cards" "${cards_count} found for augment mode, not merged into source (IMDb ID: tt${imdb_id})"
        log "Title cards detected for augment mode: ${cards_count}; source left unchanged."
    else
        "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/merge_title_cards.py" \
            "$SOURCE_SRT" \
            "$title_cards_srt"

        local source_count
        source_count="$(count_cues "$SOURCE_SRT")"
        checkpoint_set "Source cues" "$source_count"
        checkpoint_set "Title cards" "${cards_count} found and merged into source (IMDb ID: tt${imdb_id})"
        log "Title cards merged: ${cards_count}; source now has ${source_count} cues."
    fi
}

run_setup() {
    log "═══ Phase Group: Setup (Phases 0a, 0, 0b, 1) ═══"

    invoke_agent --model "$MODEL_SETUP" "Setup & Classification" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_SETUP" \
        <<EOF

## Task

Translate the subtitles for this video: ${VIDEO_FILE}

$($NO_EMBEDDED && cat <<'NOEMB'
**MODE: --no-embedded is SET.**
- Do NOT run ffprobe for embedded subtitle streams.
- Do NOT extract embedded subtitles.
- REQUIRE that ${SOURCE_SRT} exists before proceeding. If missing, fail with a clear error.
- Sync the external .en.srt directly (see workflow-setup Phase 0 external path).
- Reason: the video has burn-in subs or embedded subs that cover only foreign-language parts, not the main dialogue.
NOEMB
)

1. Run pre-flight checks (existing .nl.srt may be overwritten — do NOT ask for confirmation)
2. Detect and extract source subtitles
3. Sync source to audio (Phase 0)
4. Classify content (Phase 1)
5. Write checkpoint to: ${CHECKPOINT_FILE}

Do not run title card detection in this agent invocation. The parent orchestrator
runs Phase 0b deterministically after this checkpoint is written.

**Paths:**
- Video: ${VIDEO_FILE}
- Source SRT (after sync): ${SOURCE_SRT}
- Output SRT: ${OUTPUT_SRT}
- Work dir: ${WORK_DIR}
- Checkpoint: ${CHECKPOINT_FILE}
- Scripts dir: ${SKILL_DIR}/scripts

**Working directory:** ${VIDEO_DIR}

After classification, write the checkpoint file as specified in the workflow. The orchestrator reads the classification to determine which translator and exemplars to load for Phase 2.
EOF

    # Validate checkpoint was written
    if [[ ! -f "$CHECKPOINT_FILE" ]]; then
        die "Setup phase did not write checkpoint file: $CHECKPOINT_FILE"
    fi

    if [[ "$SOURCE_LANGUAGE" != "English" ]]; then
        checkpoint_set "Title cards" "skipped (source language is ${SOURCE_LANGUAGE}; source subtitle is treated as complete)"
        checkpoint_set "Source cues" "$(count_cues "$SOURCE_SRT")"
        log "Title cards skipped: source language is ${SOURCE_LANGUAGE}; source subtitle is treated as complete."
    elif $AUGMENT_MISSING; then
        run_title_card_detection "detect-only"
    else
        run_title_card_detection
    fi

    local classification
    classification="$(checkpoint_get "Classification")"
    if [[ -z "$classification" ]]; then
        die "Checkpoint missing classification. Check $CHECKPOINT_FILE"
    fi

    local framerate
    framerate="$(checkpoint_get "Framerate")"
    if [[ -z "$framerate" ]]; then
        log "WARNING: Checkpoint missing framerate. Defaulting to 25."
    fi

    log "Classification: $classification | Framerate: ${framerate:-25}"
    log "Setup complete. Checkpoint: $CHECKPOINT_FILE"
}

# ─── Phase Group: Translation (Phase 2) ────────────────────────────────────

run_translation() {
    log "═══ Phase Group: Translation (Phase 2) ═══"

    # Read classification and framerate from checkpoint
    local classification
    classification="$(checkpoint_get "Classification" | tr '[:upper:]' '[:lower:]')"
    [[ -z "$classification" ]] && die "No classification in checkpoint"

    local framerate
    framerate="$(checkpoint_get "Framerate")"
    [[ -z "$framerate" ]] && framerate=25
    log "Framerate: $framerate"

    local source_cues
    source_cues="$(checkpoint_get "Source cues")"
    [[ -z "$source_cues" ]] && source_cues="$(count_cues "$SOURCE_SRT")"

    # Select translator file
    local translator="${SKILL_DIR}/translators/${classification}.md"
    [[ -f "$translator" ]] || die "No translator found: $translator"

    # Select genre-specific exemplars
    local genre_exemplars=()
    case "$classification" in
        documentary)
            genre_exemplars=("$EXEMPLAR_DOCUMENTARY")
            ;;
        drama|comedy)
            genre_exemplars=("$EXEMPLAR_DRAMA" "$EXEMPLAR_DUAL_SPEAKER")
            ;;
        fast-unscripted)
            genre_exemplars=("$EXEMPLAR_DUAL_SPEAKER")
            ;;
    esac

    # Calculate batch plan
    local total_batches=$(( (source_cues + BATCH_SIZE - 1) / BATCH_SIZE ))
    if [[ "$MAX_BATCHES" -gt 0 && "$total_batches" -gt "$MAX_BATCHES" ]]; then
        log "Capping total batches from $total_batches to $MAX_BATCHES (--max-batches)"
        total_batches="$MAX_BATCHES"
    fi
    local start_batch=1

    # Check if resuming mid-translation
    local batches_done
    batches_done="$(checkpoint_get "Batches completed" | grep -oP '^\d+' || echo "0")"

    # Fallback: derive from "Last translated cue" if "Batches completed" is missing
    if [[ "$batches_done" -eq 0 ]]; then
        local last_cue
        last_cue="$(checkpoint_get "Last translated cue" | grep -oP '^\d+' || echo "0")"
        if [[ "$last_cue" -gt 0 ]]; then
            batches_done=$(( last_cue / BATCH_SIZE ))
            log "Derived batches done from last translated cue ${last_cue}: ${batches_done}"
        fi
    fi

    # Fallback: find highest-numbered batch context file
    if [[ "$batches_done" -eq 0 ]]; then
        local highest_batch
        highest_batch="$(find "$BATCH_CONTEXT_DIR" -name 'batch*_context.md' -printf '%f\n' 2>/dev/null \
            | grep -oP '\d+' | sort -n | tail -1 || true)"
        if [[ -n "$highest_batch" && "$highest_batch" -gt 0 ]]; then
            batches_done="$highest_batch"
            log "Derived batches done from context files: ${batches_done} (highest batch context found)"
        fi
    fi

    if [[ "$batches_done" -gt 0 ]]; then
        start_batch=$(( batches_done + 1 ))
        log "Resuming from batch $start_batch (${batches_done} already done)"
    fi

    log "Source cues: $source_cues | Total batches: $total_batches | Starting: $start_batch"

    # Process batches in groups of MAX_BATCHES_PER_INVOCATION
    local current_batch=$start_batch
    while [[ $current_batch -le $total_batches ]]; do
        local end_of_group=$(( current_batch + MAX_BATCHES_PER_INVOCATION - 1 ))
        [[ $end_of_group -gt $total_batches ]] && end_of_group=$total_batches

        local cue_start=$(( (current_batch - 1) * BATCH_SIZE + 1 ))
        local cue_end=$(( end_of_group * BATCH_SIZE ))
        [[ $cue_end -gt $source_cues ]] && cue_end=$source_cues

        log "── Translation invocation: batches ${current_batch}-${end_of_group} (cues ${cue_start}-${cue_end}) ──"

        # Gather batch context from previous invocations (last 2 summaries)
        local prev_context=""
        for (( b = current_batch - 2; b < current_batch; b++ )); do
            local ctx_file="${BATCH_CONTEXT_DIR}/batch${b}_context.md"
            if [[ -f "$ctx_file" ]]; then
                prev_context+="$(cat "$ctx_file")"$'\n\n'
            fi
        done

        # Load invocation handoff from previous group (if continuation)
        local handoff_context=""
        if [[ $current_batch -gt 1 ]]; then
            if [[ -f "$HANDOFF_FILE" ]]; then
                handoff_context="$(cat "$HANDOFF_FILE")"
                log "Loaded invocation handoff from previous group"
            else
                log "WARNING: Continuation invocation without handoff file — speaker change state unknown at boundary"
            fi
        fi

        # Load cumulative glossary (persists across all invocations)
        local glossary_content=""
        if [[ -f "$GLOSSARY_FILE" ]]; then
            glossary_content="$(cat "$GLOSSARY_FILE")"
        fi

        invoke_agent --model "$MODEL_TRANSLATE" --heartbeat-file "${WORK_DIR}/draft.nl.srt" "Translation batches ${current_batch}-${end_of_group}" \
            "$SHARED_CONSTRAINTS" \
            "$WORKFLOW_TRANSLATE" \
            "$translator" \
            "$DUTCH_PATTERNS" \
            "$COMMON_ERRORS" \
            "$EXEMPLAR_CONDENSATION" \
            "$EXEMPLAR_IDIOM" \
            "$EXEMPLAR_V2" \
            "${genre_exemplars[@]}" \
            <<EOF

## Task

Translate cues ${cue_start} through ${cue_end} of the source subtitle file.

**Source language:** ${SOURCE_LANGUAGE}
**Translation direction:** Translate from ${SOURCE_LANGUAGE} to Dutch. Do not assume the source text is English unless the source language is English.

**Framerate:** ${framerate} fps — use the corresponding CPS values from the constraints table.

**SDH mode:** $($KEEP_SDH && echo "KEEP — translate SDH cues as-is, preserve all hearing-impaired descriptions." || echo "REMOVE — skip SDH-only cues entirely (do not output them). Strip inline SDH tags from mixed cues (cues with both dialogue and SDH content) before translating the dialogue.")

**Paths:**
- Source SRT: ${SOURCE_SRT}
- Output SRT (write here): ${WORK_DIR}/draft.nl.srt
- Scripts dir: ${SKILL_DIR}/scripts
- Batch context dir: ${BATCH_CONTEXT_DIR}
- Glossary file: ${GLOSSARY_FILE}
- Work dir (temp files): ${WORK_DIR}

**Working directory:** ${WORK_DIR}

**Batch plan:** Process ${BATCH_SIZE} cues per batch. Extract each batch directly:
\`\`\`bash
python3 ${SKILL_DIR}/scripts/extract_cues.py ${SOURCE_SRT} --start N --end M --stdout
\`\`\`
This prints the source cues directly — read them from the command output. No separate Read call needed.

$(if [[ $current_batch -eq 1 ]]; then
    echo "**This is the first batch group.** Use the Write tool for the first batch, then \`cat >>\` for subsequent batches."
else
    echo "**Continuing from batch $current_batch.** Append to existing ${WORK_DIR}/draft.nl.srt with \`cat >>\`."
fi)

## Cumulative Glossary

$(if [[ -n "$glossary_content" ]]; then
    echo "$glossary_content"
else
    echo "No glossary yet — you will create it after your first batch."
fi)

## Invocation Handoff

$(if [[ -n "$handoff_context" ]]; then
    echo "**This is a continuation invocation.** The previous invocation ended with this state:"
    echo ""
    echo "$handoff_context"
    echo ""
    echo "Use this to determine whether the first cue in your first batch needs an [SC] marker."
else
    echo "First invocation — no handoff from a previous invocation."
fi)

## Previous Batch Context

$(if [[ -n "$prev_context" ]]; then
    echo "$prev_context"
else
    echo "First invocation — no previous batch context."
fi)

## Checkpoint

$(cat "$CHECKPOINT_FILE")

## Instructions

1. Extract and translate ${BATCH_SIZE} cues at a time (use extract_cues.py)
2. Write each batch directly to ${WORK_DIR}/draft.nl.srt (NEVER to terminal)
3. Run per-batch grammar verification after each batch
4. Write batch context summary after each batch to ${BATCH_CONTEXT_DIR}/batchN_context.md
5. After each batch, update the cumulative glossary at ${GLOSSARY_FILE} (see workflow instructions)
6. After the last batch in this group, update the checkpoint: ${CHECKPOINT_FILE}
EOF

        # Write invocation handoff from last batch context of this group
        # Uses full batch context (read by Claude, not parsed by scripts — KISS)
        local last_ctx="${BATCH_CONTEXT_DIR}/batch${end_of_group}_context.md"
        if [[ -f "$last_ctx" ]]; then
            cp "$last_ctx" "$HANDOFF_FILE"
            log "Wrote invocation handoff from batch ${end_of_group}"
        else
            log "WARNING: No batch context file for batch ${end_of_group} — cannot write handoff"
        fi

        current_batch=$(( end_of_group + 1 ))
    done

    # Validate output exists
    if [[ ! -f "${WORK_DIR}/draft.nl.srt" ]]; then
        die "Translation phase did not produce draft.nl.srt"
    fi

    local output_cues
    output_cues="$(count_cues "${WORK_DIR}/draft.nl.srt")"
    log "Translation complete. Draft cues: $output_cues (source: $source_cues)"
}

# ─── Polish: Speaker Change Marker Pass ───────────────────────────────────
#
# In --polish mode, Phase 2 (translation) is skipped, so the draft NL file
# has no [SC]/[NM] markers. Without markers, the merge script (Phase 4)
# cannot distinguish speaker changes and produces false merges.
#
# This pass reads the EN source and NL draft side-by-side and adds [SC]/[NM]
# markers to the NL cues — no text changes, only marker insertion.
# Uses Opus for reliability (Sonnet produces fewer [SC] markers).

run_marker_pass() {
    log "═══ Polish: Speaker Change Marker Pass ═══"

    local source_cues
    source_cues="$(count_cues "$SOURCE_SRT")"
    local draft_cues
    draft_cues="$(count_cues "${WORK_DIR}/draft.nl.srt")"
    log "  Source: $source_cues EN cues | Draft: $draft_cues NL cues"

    local classification
    classification="$(checkpoint_get "Classification" | tr '[:upper:]' '[:lower:]')"

    invoke_agent --model "$MODEL_TRANSLATE" --heartbeat-file "${WORK_DIR}/draft.nl.srt" "Speaker change marker pass" \
        "$SHARED_CONSTRAINTS" \
        <<EOF

## Task — Speaker Change Marker Pass (Polish Mode)

You have an English source SRT and a Dutch translation SRT. Your ONLY job is to
add \`[SC]\` and \`[NM]\` markers to the Dutch cues. Do NOT change any text,
timestamps, or cue structure.

**Classification:** ${classification}
**Genre defaults for [SC]:**
- Documentary: consecutive cues from the same narrator get NO marker. Mark [SC] at every transition to/from interview subjects, film clips, archival dialogue, voiceover changes.
- Comedy/fast-unscripted: assume speaker change unless clearly the same speaker. When in doubt, mark [SC].
- Drama: mark [SC] at every speaker change. When uncertain, prefer [SC] over omitting.

### Rules

1. Read the EN source to understand WHO is speaking in each cue
2. For each NL cue, determine if the speaker changed from the previous cue
3. If yes: prepend \`[SC]\` to the NL cue text (before any other text)
4. If ambiguous: prepend \`[NM]\`
5. If same speaker continues: do nothing (no marker)
6. **Do NOT modify any NL text** — only prepend markers
7. **Do NOT change timestamps or cue numbers**
8. **Do NOT remove or add cues**

### Process

Work in chunks of ~200 cues:
1. Extract EN cues with: \`python3 ${SKILL_DIR}/scripts/extract_cues.py ${SOURCE_SRT} --start N --end M --output ${WORK_DIR}/en_chunk.srt\`
2. Extract NL cues with: \`python3 ${SKILL_DIR}/scripts/extract_cues.py ${WORK_DIR}/draft.nl.srt --start N --end M --output ${WORK_DIR}/nl_chunk.srt\`
3. Read both chunks, compare speakers, determine markers
4. Write the marked-up NL chunk back

After processing all chunks, reassemble into ${WORK_DIR}/draft.nl.srt using the Write tool (first chunk) and Edit tool (append subsequent chunks). Verify the final cue count matches the original (${draft_cues}).

**Paths:**
- EN source: ${SOURCE_SRT}
- NL draft (read + overwrite): ${WORK_DIR}/draft.nl.srt
- Scripts dir: ${SKILL_DIR}/scripts
- Work dir: ${WORK_DIR}

**Working directory:** ${WORK_DIR}
EOF

    local marked_cues
    marked_cues="$(count_cues "${WORK_DIR}/draft.nl.srt")"
    log "Marker pass complete. Draft cues: $marked_cues (was: $draft_cues)"

    if [[ "$marked_cues" -lt $(( draft_cues - 5 )) ]]; then
        log "WARNING: Marker pass lost cues ($draft_cues → $marked_cues) — this should not happen"
    fi
}

# ─── Augment: Add Missing Title-Card Cues ──────────────────────────────────
#
# This mode updates an existing Dutch subtitle by inserting only the missing
# burned-in/title-card subtitles. It deliberately skips the full post-processing
# stack so an existing translation is not rewritten as a side effect.

run_augment_missing() {
    log "═══ Augment Missing Burned-In Subtitles ═══"

    [[ -f "$OUTPUT_SRT" ]] || die "--augment-missing requires an existing .nl.srt at: $OUTPUT_SRT"
    [[ -f "$SOURCE_SRT" ]] || die "--augment-missing requires a source .en.srt at: $SOURCE_SRT"

    local title_cards_srt="${WORK_DIR}/title_cards_for_augment.srt"
    local detected_title_cards_srt="${WORK_DIR}/title_cards.srt"
    local missing_foreign_srt="${WORK_DIR}/missing_title_cards.foreign.srt"
    local missing_nl_srt="${WORK_DIR}/missing_title_cards.nl.srt"
    rm -f "$title_cards_srt" "$missing_foreign_srt" "$missing_nl_srt"

    if [[ -s "$detected_title_cards_srt" ]]; then
        cp "$detected_title_cards_srt" "$title_cards_srt"
    else
        local extract_status=0
        "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/extract_title_cards.py" \
            "$SOURCE_SRT" \
            --output "$title_cards_srt" || extract_status=$?
    fi

    if [[ ! -s "$title_cards_srt" ]]; then
        log "Augment missing: no title-card cues found in source after setup."
        checkpoint_set "Augment missing" "none (no title-card cues found)"
        return 0
    fi

    local filter_status=0
    "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/filter_missing_subtitles.py" \
        "$title_cards_srt" \
        "$OUTPUT_SRT" \
        --output "$missing_foreign_srt" || filter_status=$?

    if [[ ! -s "$missing_foreign_srt" ]]; then
        log "Augment missing: all detected title-card cues are already covered by the existing Dutch subtitle."
        checkpoint_set "Augment missing" "none (all detected cues already covered)"
        return 0
    fi

    local missing_count
    missing_count="$(count_cues "$missing_foreign_srt")"
    log "Augment missing: translating ${missing_count} missing cue(s)."

    local classification
    classification="$(checkpoint_get "Classification" | tr '[:upper:]' '[:lower:]')"
    [[ -z "$classification" ]] && classification="documentary"

    local translator="${SKILL_DIR}/translators/${classification}.md"
    [[ -f "$translator" ]] || translator="${SKILL_DIR}/translators/documentary.md"

    invoke_agent --model "$MODEL_TRANSLATE" --heartbeat-file "$missing_nl_srt" "Translate missing burned-in subtitles" \
        "$SHARED_CONSTRAINTS" \
        "$translator" \
        "$DUTCH_PATTERNS" \
        "$COMMON_ERRORS" \
        "$EXEMPLAR_CONDENSATION" \
        "$EXEMPLAR_IDIOM" \
        "$EXEMPLAR_V2" \
        <<EOF

## Task — Translate Missing Burned-In Subtitles Only

Read this SRT file and translate every cue in it to Dutch:

${missing_foreign_srt}

The source cue text may come from a non-English OpenSubtitles file. It is a
semantic proxy for burned-in/on-screen subtitles missing from the existing Dutch
subtitle. Translate the meaning into natural Dutch subtitles.

**Output path:** ${missing_nl_srt}
**Expected cue count:** ${missing_count}

Rules:
1. Preserve every cue number, timestamp, and cue boundary exactly.
2. Translate only the cue text.
3. Do not add \`[SC]\`, \`[NM]\`, comments, explanations, credits, or markdown.
4. Write the complete translated SRT to ${missing_nl_srt}. Do not write translated cues to the terminal.
5. After writing, verify the output has exactly ${missing_count} cues.
EOF

    [[ -s "$missing_nl_srt" ]] || die "Augment missing translation did not produce: $missing_nl_srt"

    local translated_count
    translated_count="$(count_cues "$missing_nl_srt")"
    if [[ "$translated_count" -ne "$missing_count" ]]; then
        die "Augment missing translation cue count mismatch: expected ${missing_count}, got ${translated_count}"
    fi

    "$SKILL_DIR/scripts/run-venv.sh" "$SKILL_DIR/scripts/merge_missing_subtitles.py" \
        "$OUTPUT_SRT" \
        "$missing_nl_srt"

    local output_cues
    output_cues="$(count_cues "$OUTPUT_SRT")"
    checkpoint_set "Augment missing" "${translated_count} cue(s) translated and merged"
    log "Augment missing complete. Output: ${OUTPUT_SRT} (${output_cues} cues)"

    if $KEEP_WORK; then
        log "Work directory preserved (--keep-work): ${WORK_DIR}"
    else
        log "Cleaning up temp files..."
        rm -rf "$WORK_DIR"
    fi
}

# ─── Phase Group: Post-processing (Phases 3-9+) ────────────────────────────
#
# Split into 3 sub-invocations so each starts with a clean context:
#   1. Structural (Phases 3-5): fix, merge, trim, CPS
#   2. Review (Phase 6): linguistic review
#   3. Finalize (Phases 7-11 + log): QC, grammar scan, log

# Read checkpoint values shared by all post-processing functions
_postprocessing_init() {
    PP_CLASSIFICATION="$(checkpoint_get "Classification" | tr '[:upper:]' '[:lower:]')"

    PP_FRAMERATE="$(checkpoint_get "Framerate")"
    [[ -z "$PP_FRAMERATE" ]] && PP_FRAMERATE=25
    if [[ "$PP_FRAMERATE" == "24" ]]; then
        PP_MIN_GAP=125
    else
        PP_MIN_GAP=120
    fi

    case "$PP_CLASSIFICATION" in
        documentary)
            PP_GAP_THRESHOLD=1000
            [[ "$PP_FRAMERATE" == "24" ]] && PP_MAX_DURATION=7007 || PP_MAX_DURATION=7000
            ;;
        drama)
            PP_GAP_THRESHOLD=1000
            [[ "$PP_FRAMERATE" == "24" ]] && PP_MAX_DURATION=7007 || PP_MAX_DURATION=7000
            ;;
        comedy)         PP_GAP_THRESHOLD=800;  PP_MAX_DURATION=6000 ;;
        fast-unscripted) PP_GAP_THRESHOLD=500; PP_MAX_DURATION=6000 ;;
        *)
            PP_GAP_THRESHOLD=1000
            [[ "$PP_FRAMERATE" == "24" ]] && PP_MAX_DURATION=7007 || PP_MAX_DURATION=7000
            ;;
    esac

    log "Framerate: $PP_FRAMERATE | Min gap: ${PP_MIN_GAP}ms | Max duration: ${PP_MAX_DURATION}ms"

    # Fix trailing commas at end of cues → ellipsis (continuation marker)
    local draft="${WORK_DIR}/draft.nl.srt"
    if [[ -f "$draft" ]]; then
        local before after
        before="$(grep -c ',$' "$draft" 2>/dev/null)" || true
        before="${before:-0}"
        python3 -c "
import re, sys
p = sys.argv[1]
with open(p) as f: t = f.read()
t = re.sub(r',\n\n', '...\n\n', t)
t = re.sub(r',\r\n\r\n', '...\r\n\r\n', t)
with open(p,'w') as f: f.write(t)
" "$draft"
        after="$(grep -c ',$' "$draft" 2>/dev/null)" || true
        after="${after:-0}"
        log "Continuation fix: $((before - after)) end-of-cue commas → '...', ${after} mid-cue commas kept"
    fi
}

run_postprocessing_structural() {
    log "═══ Post-Processing: Structural (Phases 3-5) ═══"

    invoke_agent --model "$MODEL_POST" "Post-processing: structural (Phases 3-5)" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_POST_STRUCTURAL" \
        "$COMMON_ERRORS" \
        "$TRANSLATION_DEFAULTS" \
        <<EOF

## Task

Run post-processing phases 3 through 5 on the translated draft.

**Paths:**
- Video: ${VIDEO_FILE}
- Source SRT: ${SOURCE_SRT}
- Draft SRT: ${WORK_DIR}/draft.nl.srt
- Output SRT: ${OUTPUT_SRT}
- Scripts dir: ${SKILL_DIR}/scripts
- Log dir: ${LOG_DIR}
- Work dir (temp files): ${WORK_DIR}

**Working directory:** ${WORK_DIR}

**Genre parameters:**
- Classification: ${PP_CLASSIFICATION}
- Framerate: ${PP_FRAMERATE} fps
- --gap-threshold: ${PP_GAP_THRESHOLD}
- --max-duration: ${PP_MAX_DURATION}
- --min-gap: ${PP_MIN_GAP}
- --fps: ${PP_FRAMERATE}
- --close-gaps: 1000 (Auteursbond: gaps < 1s closed in Phase 5)

**Checkpoint:**
$(cat "$CHECKPOINT_FILE")

## Instructions

Execute these phases in order:

1. **Pre-Phase-3:** Save draft mapping
2. **Phase 3:** Structural fix on draft.nl.srt
3. **Phase 4:** Script merge with genre parameters above
4. **Phase 4b:** Trim to speech → trimmed.nl.srt + trim_report.json. If trim fails, copy merged.nl.srt to trimmed.nl.srt and continue.
5. **Phase 5:** CPS optimization on trimmed.nl.srt (NOT merged.nl.srt) — fix outliers > 17

All phases are mandatory. Do not skip any phase.
EOF

    # Verify intermediate output exists
    if [[ ! -f "${WORK_DIR}/trimmed.nl.srt" && ! -f "${WORK_DIR}/merged.nl.srt" ]]; then
        log "WARNING: Structural phases did not produce trimmed.nl.srt or merged.nl.srt"
    else
        log "Structural phases complete."
    fi
}

run_postprocessing_review() {
    log "═══ Post-Processing: Linguistic Review (Phase 6) ═══"

    invoke_agent --model "$MODEL_POST" "Post-processing: linguistic review (Phase 6)" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_POST_REVIEW" \
        "$COMMON_ERRORS" \
        <<EOF

## Task

Run Phase 6 (Linguistic Review) on the merged subtitle file.

**Paths:**
- Video: ${VIDEO_FILE}
- Source SRT: ${SOURCE_SRT}
- Merged SRT: ${WORK_DIR}/merged.nl.srt
- Merge report: ${WORK_DIR}/merge_report.json
- Scripts dir: ${SKILL_DIR}/scripts
- Work dir (temp files): ${WORK_DIR}

**Working directory:** ${WORK_DIR}

**Genre:** ${PP_CLASSIFICATION}

## Instructions

Work through the full merged.nl.srt in chunks of ~80 cues.
Review and fix all linguistic issues per the workflow.
EOF

    log "Linguistic review complete."
}

run_postprocessing_finalize() {
    log "═══ Post-Processing: Finalize + QC (Phases 7-11) ═══"

    local speech_sync_instruction=""
    if $SPEECH_SYNC; then
        speech_sync_instruction="6. **Phase 10:** Speech sync (extend to speech boundaries)"
    fi

    invoke_agent --model "$MODEL_POST" "Post-processing: finalize + QC (Phases 7-11)" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_POST_FINALIZE" \
        "$COMMON_ERRORS" \
        "$TRANSLATION_DEFAULTS" \
        <<EOF

## Task

Run finalization and QC phases on the reviewed subtitle file.

**Paths:**
- Video: ${VIDEO_FILE}
- Source SRT: ${SOURCE_SRT}
- Merged SRT: ${WORK_DIR}/merged.nl.srt
- Output SRT: ${OUTPUT_SRT}
- Merge report: ${WORK_DIR}/merge_report.json
- Draft mapping: ${WORK_DIR}/draft_mapping.json
- Scripts dir: ${SKILL_DIR}/scripts
- Log dir: ${LOG_DIR}
- Work dir (temp files): ${WORK_DIR}

**Working directory:** ${WORK_DIR}

**Genre parameters:**
- Classification: ${PP_CLASSIFICATION}
- Framerate: ${PP_FRAMERATE} fps

**Checkpoint:**
$(cat "$CHECKPOINT_FILE")

## Instructions

Execute these phases in order:

1. **Phase 7:** Finalize (validate, renumber, add credit, rename to ${OUTPUT_SRT})
2. **Phase 8:** Line balance QC (auto-fix)
3. **Phase 9:** VAD timing QC
${speech_sync_instruction}
4. **Phase 11:** Final grammar scan — read entire subtitle, fix any grammar/punctuation errors
5. **Write log** to ${LOG_DIR}/$(date +%Y-%m-%d)_${VIDEO_BASENAME}.md

All phases are mandatory. Do not skip any phase.

After the log is written, report the final statistics.
EOF

    if [[ ! -f "$OUTPUT_SRT" ]]; then
        log "WARNING: Expected output not found at $OUTPUT_SRT — check ${AGENT}'s output"
    else
        log "Post-processing complete. Output: $OUTPUT_SRT"
    fi
}

run_postprocessing() {
    _postprocessing_init
    run_postprocessing_structural
    run_postprocessing_review
    run_postprocessing_finalize
}

# ─── Main execution ────────────────────────────────────────────────────────

main() {
    log "╔══════════════════════════════════════════════╗"
    log "║  srt-translate orchestrator v14              ║"
    log "╠══════════════════════════════════════════════╣"
    log "║  Video: $(basename "$VIDEO_FILE")"
    log "║  Skill: ${SKILL_DIR}"
    log "║  Logs:  ${LOG_DIR}"
    log "║  SDH:   $($KEEP_SDH && echo "keep" || echo "remove (default)")"
    $NO_EMBEDDED && log "║  Source: external .en.srt only (embedded skipped)"
    [[ -n "$SOURCE_SRT_OVERRIDE" ]] && log "║  Source SRT: ${SOURCE_SRT}"
    [[ "$SOURCE_LANGUAGE" != "English" ]] && log "║  Source language: ${SOURCE_LANGUAGE}"
    [[ -n "$OUTPUT_SRT_OVERRIDE" ]] && log "║  Output SRT: ${OUTPUT_SRT}"
    local mode_label="full pipeline"
    $POLISH && mode_label="--polish (skip translation, post-process existing NL)"
    $AUGMENT_MISSING && mode_label="--augment-missing (add missing burned-in subtitles only)"
    log "║  Mode:  ${mode_label}"
    log "║  Agent: ${AGENT}"
    log "║  Models: setup=$(effective_model_label "$MODEL_SETUP") translate=$(effective_model_label "$MODEL_TRANSLATE") post=$(effective_model_label "$MODEL_POST")"
    [[ -n "$EFFORT" ]]         && log "║  Effort: ${EFFORT}"
    [[ -n "$BUDGET_CAP_USD" ]] && log "║  Budget cap: \$${BUDGET_CAP_USD} per invocation"
    if [[ "$AGENT" == "codex" && -n "$BUDGET_CAP_USD" ]]; then
        log "║  Note: budget cap is Claude-only and will be ignored by Codex"
    fi
    log "╚══════════════════════════════════════════════╝"

    # Determine starting point
    local start_group="setup"

    if $SOURCE_READY; then
        write_source_ready_checkpoint
        start_group="translation"
    fi

    # --fresh: delete checkpoint + work artifacts and skip prompt
    if $FRESH; then
        rm -f "$CHECKPOINT_FILE"
        rm -rf "$WORK_DIR"
        rm -rf "$BATCH_CONTEXT_DIR"
        log "Fresh run: checkpoint, work dir, and batch context deleted."
        if $SOURCE_READY; then
            mkdir -p "$WORK_DIR" "$BATCH_CONTEXT_DIR"
            write_source_ready_checkpoint
            start_group="translation"
        fi
    fi

    # If a checkpoint exists and no explicit --resume or --phase was given, ask
    if [[ -f "$CHECKPOINT_FILE" ]] && ! $RESUME && [[ -z "$START_PHASE" ]] && ! $AUGMENT_MISSING && ! $SOURCE_READY; then
        local current_phase
        current_phase="$(checkpoint_get "Current phase")"
        log "Checkpoint found: $CHECKPOINT_FILE"
        log "  Status: $current_phase"
        echo ""
        echo "A previous run was found for this video."
        echo "  [r] Resume from checkpoint"
        echo "  [f] Start fresh (deletes checkpoint)"
        echo "  [q] Quit"
        echo ""
        read -r -p "Choice [r/f/q]: " choice
        case "$choice" in
            r|R) RESUME=true ;;
            f|F) rm -f "$CHECKPOINT_FILE"; rm -rf "$WORK_DIR"; rm -f "$BATCH_CONTEXT_DIR"/batch*_context.md; log "Checkpoint, work dir, and batch context deleted. Starting fresh." ;;
            *)   log "Aborted."; exit 0 ;;
        esac
        echo ""
    fi

    if $RESUME && [[ -f "$CHECKPOINT_FILE" ]]; then
        local current_phase
        current_phase="$(checkpoint_get "Current phase")"
        local next_phase
        next_phase="$(checkpoint_get "Next phase")"

        log "Resuming from checkpoint. Current: $current_phase | Next: $next_phase"

        # Determine resume point from checkpoint fields.
        # Primary: "Next phase" (set when a phase completes cleanly).
        # Fallback: "Current phase" (always present — critical for crash recovery
        # where the interrupted phase never wrote "Next phase").
        local resume_hint="${next_phase:-$current_phase}"

        case "$resume_hint" in
            *"2"*|*"translat"*|*"Translat"*)  start_group="translation" ;;
            *"3"*|*"post"*|*"Post"*)           start_group="postprocessing" ;;
            *"1"*|*"classif"*|*"setup"*)       start_group="setup" ;;
            *)
                # Last resort: check if work dir has a draft → translation was in progress
                if [[ -f "${WORK_DIR}/draft.nl.srt" ]]; then
                    log "No phase match from checkpoint, but draft.nl.srt exists — resuming translation"
                    start_group="translation"
                else
                    start_group="setup"
                fi
                ;;
        esac
    fi

    if [[ -n "$START_PHASE" ]]; then
        case "$START_PHASE" in
            0|1)  start_group="setup" ;;
            2)    start_group="translation" ;;
            3|4|5|6|7|8|9) start_group="postprocessing" ;;
            *)    die "Invalid phase: $START_PHASE (valid: 0-9)" ;;
        esac
        log "Override: starting from phase group '$start_group'"
    fi

    # --augment-missing: run setup/title-card detection, translate only missing
    # detected cues, and merge them into the existing Dutch subtitle.
    if $AUGMENT_MISSING; then
        [[ -f "$OUTPUT_SRT" ]] || die "--augment-missing requires an existing .nl.srt at: $OUTPUT_SRT"
        run_setup
        run_augment_missing
        return
    fi

    # --polish: run setup, seed draft, add SC markers, then post-process
    if $POLISH; then
        [[ -f "$OUTPUT_SRT" ]] || die "--polish requires an existing .nl.srt at: $OUTPUT_SRT"
        run_setup
        log "Polish mode: seeding draft from existing translation: $OUTPUT_SRT"
        cp "$OUTPUT_SRT" "${WORK_DIR}/draft.nl.srt"
        log "  Copied → ${WORK_DIR}/draft.nl.srt ($(count_cues "${WORK_DIR}/draft.nl.srt") cues)"
        run_marker_pass
        run_postprocessing
        return
    fi

    # Execute phase groups
    case "$start_group" in
        setup)
            run_setup
            run_translation
            run_postprocessing
            ;;
        translation)
            run_translation
            run_postprocessing
            ;;
        postprocessing)
            run_postprocessing
            ;;
    esac

    # ─── Safety net: ensure translated work is never lost ─────────────────────
    local draft_file="${WORK_DIR}/draft.nl.srt"
    local draft_cues=0
    if [[ -f "$draft_file" ]]; then
        draft_cues="$(count_cues "$draft_file")"
    fi

    # Check if post-processing actually produced a fresh output
    # (output must exist, have cues, AND be newer than the draft)
    local output_cues=0
    local output_is_fresh=false
    if [[ -f "$OUTPUT_SRT" ]]; then
        output_cues="$(count_cues "$OUTPUT_SRT")"
        if [[ -f "$draft_file" ]]; then
            [[ "$OUTPUT_SRT" -nt "$draft_file" ]] && output_is_fresh=true
        else
            # No draft to compare against (e.g. --phase 3 re-run) — trust it
            output_is_fresh=true
        fi
    fi

    if $output_is_fresh && [[ "$output_cues" -gt 0 ]]; then
        # Post-processing succeeded
        if $KEEP_WORK; then
            log "Work directory preserved (--keep-work): ${WORK_DIR}"
        else
            log "Cleaning up temp files..."
            rm -rf "$WORK_DIR"
        fi
        log ""
        log "═══ Pipeline complete ═══"
        log "Output: ${OUTPUT_SRT} (${output_cues} cues)"
    elif [[ "$draft_cues" -gt 0 ]]; then
        # Post-processing failed but draft exists — save it
        log "WARNING: Post-processing did not produce valid output (${output_cues} cues, fresh=${output_is_fresh})"
        log "Draft has ${draft_cues} cues — saving to output as safety net"
        if [[ -f "$OUTPUT_SRT" ]]; then
            log "Backing up existing output to ${OUTPUT_SRT}.bak"
            cp "$OUTPUT_SRT" "${OUTPUT_SRT}.bak"
        fi
        cp "$draft_file" "$OUTPUT_SRT"
        log ""
        log "═══ Pipeline complete (PARTIAL — post-processing failed) ═══"
        log "Output: ${OUTPUT_SRT} (${draft_cues} cues, raw draft — NOT post-processed)"
        log "Re-run with --phase 3 to post-process."
        log "Work dir preserved: ${WORK_DIR}"
    else
        # Nothing produced at all
        log ""
        log "═══ Pipeline complete (FAILED — no output) ═══"
        log "Neither post-processing nor translation produced output."
        [[ -d "$WORK_DIR" ]] && log "Work dir preserved: ${WORK_DIR}"
    fi
    log "Logs: ${LOG_DIR}"
}

main "$@"
