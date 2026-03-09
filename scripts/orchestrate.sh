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
BATCH_SIZE=100
MAX_BATCHES_PER_INVOCATION=6

# ─── Argument parsing ──────────────────────────────────────────────────────

RESUME=false
FRESH=false
POLISH=false
START_PHASE=""
SPEECH_SYNC=false
KEEP_SDH=false
KEEP_WORK=false
MAX_BATCHES=0  # 0 = unlimited
VIDEO_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)       RESUME=true; shift ;;
        --fresh)        FRESH=true; shift ;;
        --polish)       POLISH=true; shift ;;
        --phase)        START_PHASE="$2"; shift 2 ;;
        --speech-sync)  SPEECH_SYNC=true; shift ;;
        --keep-sdh)     KEEP_SDH=true; shift ;;
        --keep-work)    KEEP_WORK=true; shift ;;
        --max-batches)  MAX_BATCHES="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 /path/to/video.mkv [--resume] [--fresh] [--polish] [--phase N] [--speech-sync] [--keep-sdh] [--max-batches N]"
            echo ""
            echo "Options:"
            echo "  --resume        Resume from last checkpoint"
            echo "  --fresh         Delete any checkpoint and start from phase 0 (non-interactive)"
            echo "  --polish        Skip translation — run post-processing on existing .nl.srt"
            echo "                  Runs setup (Phase 0-1) then jumps straight to Phase 3."
            echo "                  Saves ~80%% of token cost vs a full retranslation."
            echo "  --phase N       Start from phase N (0, 2, 3)"
            echo "  --speech-sync   Run Phase 10 (speech sync) after Phase 9"
            echo "  --keep-sdh      Keep SDH cues (default: remove them before translation)"
            echo "  --keep-work     Preserve work directory after successful completion (for debugging)"
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
GLOSSARY_FILE="${WORK_DIR}/translation_glossary.md"
HANDOFF_FILE="${BATCH_CONTEXT_DIR}/invocation_handoff.txt"

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
# Usage: invoke_claude [--model MODEL] "task description" file1.md file2.md ... <<< "inline prompt"
invoke_claude() {
    local model=""

    # Parse optional --model flag
    if [[ "$1" == "--model" ]]; then
        model="$2"
        shift 2
    fi

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

    # Build model flag if specified
    local model_args=()
    if [[ -n "$model" ]]; then
        model_args=(--model "$model")
    fi

    # --allowedTools ensures non-interactive execution
    # Unset CLAUDECODE to allow running from within a Claude Code session
    # cd to SKILL_DIR so relative paths like scripts/run-venv.sh resolve correctly
    # and Bash(scripts/*) permission pattern matches them regardless of launch cwd.
    local exit_code
    (cd "$SKILL_DIR" && echo "$prompt" | env -u CLAUDECODE claude -p \
        "${model_args[@]}" \
        --allowedTools "Read,Glob,Grep,Edit,Write,Bash(python3:*),Bash(cat:*),Bash(grep:*),Bash(wc:*),Bash(mv:*),Bash(cp:*),Bash(mkdir:*),Bash(ffprobe:*),Bash(ffmpeg:*),Bash(head:*),Bash(tail:*),Bash(sed:*),Bash(scripts/*)" \
        --output-format text \
        2>"${LOG_DIR}/claude_stderr_$(date +%s).log")
    exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log "WARNING: Claude exited with code $exit_code for: $description"
    fi
    return $exit_code
}

# ─── Phase Group: Setup (Phases 0-1) ───────────────────────────────────────

run_setup() {
    log "═══ Phase Group: Setup (Phases 0a, 0, 0b, 1) ═══"

    invoke_claude --model "$MODEL_SETUP" "Setup & Classification" \
        "$SHARED_CONSTRAINTS" \
        "$WORKFLOW_SETUP" \
        <<EOF

## Task

Translate the subtitles for this video: ${VIDEO_FILE}

1. Run pre-flight checks (existing .nl.srt may be overwritten — do NOT ask for confirmation)
2. Detect and extract source subtitles
3. Sync source to audio (Phase 0)
4. Run title card detection (Phase 0b) — always attempt, silently skip if no API key or timeout
5. Classify content (Phase 1)
6. Write checkpoint to: ${CHECKPOINT_FILE}

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

        invoke_claude --model "$MODEL_TRANSLATE" "Translation batches ${current_batch}-${end_of_group}" \
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
- Glossary file: ${GLOSSARY_FILE}
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

    invoke_claude --model "$MODEL_TRANSLATE" "Speaker change marker pass" \
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

    invoke_claude --model "$MODEL_POST" "Post-processing (Phases 3-9)" \
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
3. **Phase 4b:** Trim to speech → trimmed.nl.srt + trim_report.json. If trim fails, copy merged.nl.srt to trimmed.nl.srt and continue.
4. **Phase 5:** CPS optimization on trimmed.nl.srt (NOT merged.nl.srt) — fix outliers > 17
5. **Phase 6:** Linguistic review — all cues in ~80-cue chunks
6. **Phase 7:** Finalize (validate, renumber, add credit, rename to ${OUTPUT_SRT})
7. **Phase 8:** Line balance QC (auto-fix)
8. **Phase 9:** VAD timing QC
${speech_sync_instruction}
9. **Phase 11:** Final grammar scan — read entire subtitle, fix any grammar/punctuation errors
10. **Write log** to ${LOG_DIR}/$(date +%Y-%m-%d)_${VIDEO_BASENAME}.md

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
    log "║  srt-translate orchestrator v14              ║"
    log "╠══════════════════════════════════════════════╣"
    log "║  Video: $(basename "$VIDEO_FILE")"
    log "║  Skill: ${SKILL_DIR}"
    log "║  Logs:  ${LOG_DIR}"
    log "║  SDH:   $($KEEP_SDH && echo "keep" || echo "remove (default)")"
    log "║  Mode:  $($POLISH && echo "--polish (skip translation, post-process existing NL)" || echo "full pipeline")"
    log "║  Models: setup=${MODEL_SETUP} translate=${MODEL_TRANSLATE} post=${MODEL_POST}"
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
