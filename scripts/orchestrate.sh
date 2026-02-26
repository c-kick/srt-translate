#!/usr/bin/env bash
#
# srt-orchestrate.sh — Deterministic pipeline for srt-translate skill
#
# Invokes Claude Code in headless mode (-p) per phase group, each with a
# fresh context containing ONLY the instructions relevant to that phase.
# This eliminates attention degradation from irrelevant instructions.
#
# Usage:
#   ./scripts/orchestrate.sh /path/to/video.mkv [--resume] [--phase N] [--speech-sync]
#
# Requirements:
#   - claude CLI in PATH
#   - ffmpeg, ffprobe, python3
#   - scripts/venv/ with ffsubsync, webrtcvad, pysubs2
#
# Environment:
#   CLAUDE_CODE_MAX_OUTPUT_TOKENS  (default: 128000)
#   SKILL_DIR                      (default: auto-detected from script location)
#   LOG_DIR                        (default: /mnt/nas/video/.claude/logs/srt-translate)
#

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${SKILL_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

LOG_DIR="${LOG_DIR:-/mnt/nas/video/.claude/logs/srt-translate}"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-128000}"

# Max cues per translation batch before forcing a context-clearing sub-invocation
BATCH_SIZE=100
MAX_BATCHES_PER_INVOCATION=6

# ─── Argument parsing ──────────────────────────────────────────────────────

RESUME=false
FRESH=false
START_PHASE=""
SPEECH_SYNC=false
KEEP_SDH=false
MAX_BATCHES=0  # 0 = unlimited
VIDEO_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)       RESUME=true; shift ;;
        --fresh)        FRESH=true; shift ;;
        --phase)        START_PHASE="$2"; shift 2 ;;
        --speech-sync)  SPEECH_SYNC=true; shift ;;
        --keep-sdh)     KEEP_SDH=true; shift ;;
        --max-batches)  MAX_BATCHES="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 /path/to/video.mkv [--resume] [--fresh] [--phase N] [--speech-sync] [--keep-sdh] [--max-batches N]"
            echo ""
            echo "Options:"
            echo "  --resume        Resume from last checkpoint"
            echo "  --fresh         Delete any checkpoint and start from phase 0 (non-interactive)"
            echo "  --phase N       Start from phase N (0, 2, 3)"
            echo "  --speech-sync   Run Phase 10 (speech sync) after Phase 9"
            echo "  --keep-sdh      Keep SDH cues (default: remove them before translation)"
            echo "  --max-batches N Limit translation to N batches (for testing)"
            exit 0
            ;;
        -*)             echo "Unknown option: $1" >&2; exit 1 ;;
        *)              VIDEO_FILE="$1"; shift ;;
    esac
done

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

mkdir -p "$LOG_DIR" "$BATCH_CONTEXT_DIR" "$WORK_DIR"

# ─── Skill file paths ──────────────────────────────────────────────────────

SHARED_CONSTRAINTS="${SKILL_DIR}/base/shared-constraints.md"
WORKFLOW_SETUP="${SKILL_DIR}/base/workflow-setup.md"
WORKFLOW_TRANSLATE="${SKILL_DIR}/base/workflow-translate.md"
WORKFLOW_POST="${SKILL_DIR}/base/workflow-post.md"

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
    n="$(tr -d '\r' < "$1" 2>/dev/null | grep -cE '^[0-9]+$')" || true
    echo "${n:-0}"
}

# Invoke claude with a prompt assembled from files + inline instructions
# Usage: invoke_claude "task description" file1.md file2.md ... <<< "inline prompt"
invoke_claude() {
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
    log "  Context files: $*"

    # --allowedTools ensures non-interactive execution
    # Unset CLAUDECODE to allow running from within a Claude Code session
    echo "$prompt" | env -u CLAUDECODE claude -p \
        --allowedTools "Read,Glob,Grep,Edit,Write,Bash(python3:*),Bash(cat:*),Bash(grep:*),Bash(wc:*),Bash(mv:*),Bash(cp:*),Bash(mkdir:*),Bash(ffprobe:*),Bash(ffmpeg:*),Bash(head:*),Bash(tail:*),Bash(sed:*),Bash(scripts/*)" \
        --output-format text \
        2>"${LOG_DIR}/claude_stderr_$(date +%s).log"

    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log "WARNING: Claude exited with code $exit_code for: $description"
    fi
    return $exit_code
}

# ─── Phase Group: Setup (Phases 0-1) ───────────────────────────────────────

run_setup() {
    log "═══ Phase Group: Setup (Phases 0a, 0, 1) ═══"

    invoke_claude "Setup & Classification" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_SETUP" \
        <<EOF

## Task

Translate the subtitles for this video: ${VIDEO_FILE}

1. Run pre-flight checks (existing .nl.srt may be overwritten — do NOT ask for confirmation)
2. Detect and extract source subtitles
3. Sync source to audio (Phase 0)
4. Classify content (Phase 1)
5. Write checkpoint to: ${CHECKPOINT_FILE}

**Paths:**
- Video: ${VIDEO_FILE}
- Source SRT (after sync): ${SOURCE_SRT}
- Output SRT: ${OUTPUT_SRT}
- Checkpoint: ${CHECKPOINT_FILE}
- Scripts dir: ${SKILL_DIR}/scripts

**Working directory:** ${VIDEO_DIR}

After classification, write the checkpoint file as specified in the workflow. The orchestrator reads the classification to determine which translator and exemplars to load for Phase 2.
EOF

    # Validate checkpoint was written
    if [[ ! -f "$CHECKPOINT_FILE" ]]; then
        die "Setup phase did not write checkpoint file: $CHECKPOINT_FILE"
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

        invoke_claude "Translation batches ${current_batch}-${end_of_group}" \
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

**Framerate:** ${framerate} fps — use the corresponding CPS values from the constraints table.

**SDH mode:** $($KEEP_SDH && echo "KEEP — translate SDH cues as-is, preserve all hearing-impaired descriptions." || echo "REMOVE — skip SDH-only cues entirely (do not output them). Strip inline SDH tags from mixed cues (cues with both dialogue and SDH content) before translating the dialogue.")

**Paths:**
- Source SRT: ${SOURCE_SRT}
- Output SRT (write here): ${WORK_DIR}/draft.nl.srt
- Scripts dir: ${SKILL_DIR}/scripts
- Batch context dir: ${BATCH_CONTEXT_DIR}
- Work dir (temp files): ${WORK_DIR}

**Working directory:** ${WORK_DIR}

**Batch plan:** Process ${BATCH_SIZE} cues per batch. Extract each batch with:
\`\`\`bash
python3 ${SKILL_DIR}/scripts/extract_cues.py ${SOURCE_SRT} --start N --end M --output ${WORK_DIR}/batch_source.srt
\`\`\`

$(if [[ $current_batch -eq 1 ]]; then
    echo "**This is the first batch group.** Use the Write tool for the first batch, then \`cat >>\` for subsequent batches."
else
    echo "**Continuing from batch $current_batch.** Append to existing ${WORK_DIR}/draft.nl.srt with \`cat >>\`."
fi)

## Previous Context

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
5. After the last batch in this group, update the checkpoint: ${CHECKPOINT_FILE}
EOF

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

# ─── Phase Group: Post-processing (Phases 3-9+) ────────────────────────────

run_postprocessing() {
    log "═══ Phase Group: Post-Processing (Phases 3-9) ═══"

    local classification
    classification="$(checkpoint_get "Classification" | tr '[:upper:]' '[:lower:]')"

    # Read framerate from checkpoint (default 25 for legacy)
    local framerate min_gap
    framerate="$(checkpoint_get "Framerate")"
    [[ -z "$framerate" ]] && framerate=25
    if [[ "$framerate" == "24" ]]; then
        min_gap=125
    else
        min_gap=120
    fi

    # Determine genre merge parameters (fps-aware for documentary/drama)
    local gap_threshold max_duration
    case "$classification" in
        documentary)
            gap_threshold=1000
            [[ "$framerate" == "24" ]] && max_duration=7007 || max_duration=7000
            ;;
        drama)
            gap_threshold=1000
            [[ "$framerate" == "24" ]] && max_duration=7007 || max_duration=7000
            ;;
        comedy)         gap_threshold=800;  max_duration=6000 ;;
        fast-unscripted) gap_threshold=500; max_duration=6000 ;;
        *)
            gap_threshold=1000
            [[ "$framerate" == "24" ]] && max_duration=7007 || max_duration=7000
            ;;
    esac

    log "Framerate: $framerate | Min gap: ${min_gap}ms | Max duration: ${max_duration}ms"

    local speech_sync_instruction=""
    if $SPEECH_SYNC; then
        speech_sync_instruction="After Phase 9, also run Phase 10 (Speech Sync) as described in the workflow."
    fi

    # Fix trailing commas at end of cues → ellipsis (continuation marker)
    # Matches comma followed by blank line (= end of cue).
    # Mid-cue commas (line 1 of 2-line cue) are followed by text, not blank line → untouched.
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

    invoke_claude "Post-processing (Phases 3-9)" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_POST" \
        "$COMMON_ERRORS" \
        "$TRANSLATION_DEFAULTS" \
        <<EOF

## Task

Run post-processing phases 3 through 9 (and log) on the translated draft.

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
- Classification: ${classification}
- Framerate: ${framerate} fps
- --gap-threshold: ${gap_threshold}
- --max-duration: ${max_duration}
- --min-gap: ${min_gap}
- --fps: ${framerate}
- --close-gaps: 1000 (Auteursbond: gaps < 1s closed in Phase 5)

**Checkpoint:**
$(cat "$CHECKPOINT_FILE")

## Instructions

Execute all phases in order:

1. **Phase 3:** Structural fix on draft.nl.srt
2. **Phase 4:** Script merge with genre parameters above
3. **Phase 5:** CPS validation — fix outliers > 17
4. **Phase 6:** Linguistic review — all cues in ~80-cue chunks
5. **Phase 7:** Finalize (validate, renumber, add credit, rename to ${OUTPUT_SRT})
6. **Phase 8:** Line balance QC (auto-fix)
7. **Phase 9:** VAD timing QC
${speech_sync_instruction}
8. **Write log** to ${LOG_DIR}/$(date +%Y-%m-%d)_${VIDEO_BASENAME}.md

All phases are mandatory. Do not skip any phase.

After the log is written, report the final statistics.
EOF

    if [[ ! -f "$OUTPUT_SRT" ]]; then
        log "WARNING: Expected output not found at $OUTPUT_SRT — check Claude's output"
    else
        log "Post-processing complete. Output: $OUTPUT_SRT"
    fi
}

# ─── Main execution ────────────────────────────────────────────────────────

main() {
    log "╔══════════════════════════════════════════════╗"
    log "║  srt-translate orchestrator v13              ║"
    log "╠══════════════════════════════════════════════╣"
    log "║  Video: $(basename "$VIDEO_FILE")"
    log "║  Skill: ${SKILL_DIR}"
    log "║  Logs:  ${LOG_DIR}"
    log "║  SDH:   $($KEEP_SDH && echo "keep" || echo "remove (default)")"
    log "╚══════════════════════════════════════════════╝"

    # Determine starting point
    local start_group="setup"

    # --fresh: delete checkpoint + work artifacts and skip prompt
    if $FRESH; then
        rm -f "$CHECKPOINT_FILE"
        rm -rf "$WORK_DIR"
        rm -rf "$BATCH_CONTEXT_DIR"
        log "Fresh run: checkpoint, work dir, and batch context deleted."
    fi

    # If a checkpoint exists and no explicit --resume or --phase was given, ask
    if [[ -f "$CHECKPOINT_FILE" ]] && ! $RESUME && [[ -z "$START_PHASE" ]]; then
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
        log "Cleaning up temp files..."
        rm -rf "$WORK_DIR"
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
