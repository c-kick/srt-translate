#!/usr/bin/env bash
# Create GitHub issues from TODO.md items
# Usage: GITHUB_TOKEN=ghp_xxx ./create_issues.sh
# Or:    gh auth login && ./create_issues.sh

set -euo pipefail

REPO="c-kick/srt-translate"

# Check for authentication
if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
  USE_GH=true
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  USE_GH=false
else
  echo "Error: No authentication found."
  echo "Either run 'gh auth login' or set GITHUB_TOKEN=ghp_xxx"
  exit 1
fi

create_issue() {
  local title="$1"
  local body="$2"
  local labels="${3:-}"

  if [[ "$USE_GH" == true ]]; then
    if [[ -n "$labels" ]]; then
      gh issue create --repo "$REPO" --title "$title" --body "$body" --label "$labels"
    else
      gh issue create --repo "$REPO" --title "$title" --body "$body"
    fi
  else
    local label_json=""
    if [[ -n "$labels" ]]; then
      label_json=$(printf '"%s"' "$labels" | sed 's/,/","/g')
      label_json=', "labels": ['"$label_json"']'
    fi
    curl -s -X POST "https://api.github.com/repos/$REPO/issues" \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Accept: application/vnd.github+json" \
      -d "$(cat <<PAYLOAD
{
  "title": $(printf '%s' "$title" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "body": $(printf '%s' "$body" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
  $label_json
}
PAYLOAD
)" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("html_url","ERROR: "+str(d)))'
  fi
}

echo "Creating 6 issues from TODO.md..."
echo

# Issue 1: Skill Triggering Description
echo "1/6: Skill Triggering Description"
create_issue \
  "Improve SKILL.md trigger description for edge cases" \
  "$(cat <<'EOF'
## Context

The SKILL.md description could be more aggressive about edge cases to improve trigger accuracy. Currently it may miss unusual phrasings.

## Suggested Improvements

Add explicit mentions of:
- Reviewing existing NL subtitles against EN source
- Requests mentioning `.srt` files with Dutch/Nederlands/NL
- Subtitle QC or quality check requests for Dutch

## Why

This would improve the accuracy of skill triggering and reduce missed activations for valid use cases.

_Source: TODO.md — "Skill Triggering Description"_
EOF
)" "enhancement"
echo

# Issue 2: Workflow Density in Post-Processing
echo "2/6: Workflow Density in Post-Processing"
create_issue \
  "Reduce workflow-post.md density to prevent phase skipping" \
  "$(cat <<'EOF'
## Problem

`workflow-post.md` covers Phases 3–9+LOG in a single context load. If Claude occasionally skips or conflates phases, the density could be a factor.

## Proposed Solutions

Consider one or more of:
- Adding explicit phase-transition markers (e.g. "Phase N complete. Proceeding to Phase N+1.")
- A checklist Claude must tick through before moving to the next phase
- Splitting post-processing into two phase groups if context pressure becomes an issue

_Source: TODO.md — "Workflow Density in Post-Processing"_
EOF
)" "enhancement"
echo

# Issue 3: Batch Context Continuity
echo "3/6: Batch Context Continuity"
create_issue \
  "Add cumulative glossary for batch context continuity" \
  "$(cat <<'EOF'
## Problem

Translation batches write context summaries to `batchN_context.md`, and subsequent batches read them. When a new Claude invocation starts (every 6 batches), nuanced character voice decisions or terminology choices from earlier batches may lose fidelity through summarization.

## Proposed Solution

- A cumulative running glossary file that grows across all batches (character names, T-V register choices, recurring terminology) rather than per-batch summaries alone
- Having each new invocation read the glossary in addition to the batch context files

_Source: TODO.md — "Batch Context Continuity"_
EOF
)" "enhancement"
echo

# Issue 4: End-to-End Regression Testing
echo "4/6: End-to-End Regression Testing"
create_issue \
  "Add end-to-end regression testing for the pipeline" \
  "$(cat <<'EOF'
## Problem

No automated way to smoke-test the full pipeline. Regressions can go unnoticed.

## Proposed Solution

A lightweight regression test that could catch regressions faster:
- Translate the first 20 cues of a known file and check constraint compliance on the output
- Compare merge ratios and CPS distributions against a reference baseline
- Could be a `--test` flag on `orchestrate.sh` that runs a truncated pipeline on a bundled test file

_Source: TODO.md — "End-to-End Regression Testing"_
EOF
)" "enhancement"
echo

# Issue 5: Phase-Level Error Recovery
echo "5/6: Phase-Level Error Recovery"
create_issue \
  "Add per-phase checkpointing and resume capability" \
  "$(cat <<'EOF'
## Problem

Individual phase failures restart the entire phase group. If Phase 6 (linguistic review) fails mid-way through a large file, there's no mechanism to resume from the last reviewed chunk.

## Proposed Solution

- Per-phase checkpointing within post-processing (e.g. writing a `phase_N_complete` marker)
- Allowing `--phase N` to resume within the post-processing group rather than restarting from Phase 3

_Source: TODO.md — "Phase-Level Error Recovery"_
EOF
)" "enhancement"
echo

# Issue 6: Venv Permission Mismatch in Headless Subprocess
echo "6/6: Venv Permission Mismatch in Headless Subprocess"
create_issue \
  "Fix venv permission mismatch in headless subprocess runs" \
  "$(cat <<'EOF'
## Status

**STILL OPEN** — fix attempted 2026-03-07 (cd to SKILL_DIR) was insufficient.

## Symptom

Phase 4b (trim-to-speech) and Phase 9 (VAD timing) are silently skipped during orchestrated headless runs.

## History

- Cold War S01E01 (2026-03-06): skipped with "requires user approval that wasn't granted"
- Das Auto (2026-03-07): skipped with "no venv" after cd-fix was applied

## Root Cause (updated analysis)

Two compounding problems:

1. **Pattern depth:** `Bash(scripts/*)` in `--allowedTools` may only match one path level deep (i.e. `scripts/foo` but not `scripts/venv/bin/python3`). Whether Claude'\''s permission system treats `*` as a recursive glob or single-level is unverified.

2. **cwd conflict:** The `cd "$SKILL_DIR"` fix sets the subprocess cwd to SKILL_DIR, which helps with permission pattern matching — but `workflow-post.md` uses relative paths for work files (e.g. `merged.nl.srt`, `trimmed.nl.srt`) that are relative to WORK_DIR. With cwd=SKILL_DIR these paths break, causing the venv script to fail silently.

These two problems are in tension: permission matching wants cwd=SKILL_DIR; work file paths want cwd=WORK_DIR.

## Recommended Fix

Create `scripts/run-venv.sh` — a thin wrapper that calls the venv python using its absolute path:

```bash
#!/usr/bin/env bash
exec "$(dirname "${BASH_SOURCE[0]}")/venv/bin/python3" "$@"
```

- Add `Bash(scripts/run-venv.sh:*)` to `--allowedTools`
- Update `workflow-post.md` to call `scripts/run-venv.sh` instead of `scripts/venv/bin/python3`
- This is cwd-agnostic and single-level, so it matches cleanly regardless of cwd

_Source: TODO.md — "Venv Permission Mismatch in Headless Subprocess"_
EOF
)" "bug"
echo

echo "Done! All 6 issues created."
