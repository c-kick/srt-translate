#!/usr/bin/env bash
# Create GitHub issues from TODO.md
# Usage: ./create_issues.sh
# Requires: gh CLI authenticated (run `gh auth login` first)

set -euo pipefail

REPO="c-kick/srt-translate"

echo "Creating issues for $REPO from TODO.md..."
echo ""

# Issue 1: Skill Triggering Description
gh issue create --repo "$REPO" \
  --title "Improve SKILL.md trigger accuracy for edge cases" \
  --body "$(cat <<'EOF'
## Description

The SKILL.md description could be more aggressive about edge cases to improve trigger accuracy. Currently it may miss unusual phrasings.

## Suggested improvements

Consider adding explicit mentions of:
- Reviewing existing NL subtitles against EN source
- Requests mentioning `.srt` files with Dutch/Nederlands/NL
- Subtitle QC or quality check requests for Dutch

## Context

From `TODO.md` — "Skill Triggering Description" section.
EOF
)"
echo "Created: Skill Triggering Description"

# Issue 2: Workflow Density in Post-Processing
gh issue create --repo "$REPO" \
  --title "Reduce workflow density in post-processing (workflow-post.md)" \
  --body "$(cat <<'EOF'
## Description

`workflow-post.md` covers Phases 3–9+LOG in a single context load. If Claude occasionally skips or conflates phases, the density could be a factor.

## Suggested improvements

Consider:
- Adding explicit phase-transition markers (e.g. "Phase N complete. Proceeding to Phase N+1.")
- A checklist Claude must tick through before moving to the next phase
- Splitting post-processing into two phase groups if context pressure becomes an issue

## Context

From `TODO.md` — "Workflow Density in Post-Processing" section.
EOF
)"
echo "Created: Workflow Density in Post-Processing"

# Issue 3: Batch Context Continuity
gh issue create --repo "$REPO" \
  --title "Improve batch context continuity across Claude invocations" \
  --body "$(cat <<'EOF'
## Description

Translation batches write context summaries to `batchN_context.md`, and subsequent batches read them. When a new Claude invocation starts (every 6 batches), nuanced character voice decisions or terminology choices from earlier batches may lose fidelity through summarization.

## Suggested improvements

Consider:
- A cumulative running glossary file that grows across all batches (character names, T-V register choices, recurring terminology) rather than per-batch summaries alone
- Having each new invocation read the glossary in addition to the batch context files

## Context

From `TODO.md` — "Batch Context Continuity" section.
EOF
)"
echo "Created: Batch Context Continuity"

# Issue 4: End-to-End Regression Testing
gh issue create --repo "$REPO" \
  --title "Add end-to-end regression testing for the translation pipeline" \
  --body "$(cat <<'EOF'
## Description

No automated way to smoke-test the full pipeline. A lightweight regression test could catch regressions faster.

## Suggested improvements

- Translate the first 20 cues of a known file and check constraint compliance on the output
- Compare merge ratios and CPS distributions against a reference baseline
- Could be a `--test` flag on `orchestrate.sh` that runs a truncated pipeline on a bundled test file

## Context

From `TODO.md` — "End-to-End Regression Testing" section.
EOF
)"
echo "Created: End-to-End Regression Testing"

# Issue 5: Phase-Level Error Recovery
gh issue create --repo "$REPO" \
  --title "Add phase-level error recovery and checkpointing" \
  --body "$(cat <<'EOF'
## Description

Individual phase failures restart the entire phase group. If Phase 6 (linguistic review) fails mid-way through a large file, there's no mechanism to resume from the last reviewed chunk.

## Suggested improvements

Consider:
- Per-phase checkpointing within post-processing (e.g. writing a `phase_N_complete` marker)
- Allowing `--phase N` to resume within the post-processing group rather than restarting from Phase 3

## Context

From `TODO.md` — "Phase-Level Error Recovery" section.
EOF
)"
echo "Created: Phase-Level Error Recovery"

# Issue 6: Venv Permission Mismatch in Headless Subprocess
gh issue create --repo "$REPO" \
  --title "Fix venv permission mismatch in headless subprocess runs" \
  --label "bug" \
  --body "$(cat <<'EOF'
## Description

**STILL OPEN.** Fix attempted 2026-03-07 (cd to SKILL_DIR) was insufficient — phases still skipped in Das Auto (2026-03-07). Error message changed from "requires user approval" to "no venv", indicating a different failure mode.

## Symptom

Phase 4b (trim-to-speech) and Phase 9 (VAD timing) are silently skipped during orchestrated headless runs.

## History

- Cold War S01E01 (2026-03-06): skipped with "requires user approval that wasn't granted"
- Das Auto (2026-03-07): skipped with "no venv" after cd-fix was applied

## Root cause (updated analysis)

Two compounding problems:

1. **Pattern depth:** `Bash(scripts/*)` in `--allowedTools` may only match one path level deep (i.e. `scripts/foo` but not `scripts/venv/bin/python3`). Whether Claude's permission system treats `*` as a recursive glob or single-level is unverified.

2. **cwd conflict:** The `cd "$SKILL_DIR"` fix sets the subprocess cwd to SKILL_DIR, which helps with permission pattern matching — but the workflow-post.md uses relative paths for work files (e.g. `merged.nl.srt`, `trimmed.nl.srt`) that are relative to WORK_DIR. With cwd=SKILL_DIR these paths break, causing the venv script to fail silently. Claude interprets the failure as "no venv" and falls back to copying.

These two problems are in tension: permission matching wants cwd=SKILL_DIR; work file paths want cwd=WORK_DIR.

## Recommended fix

Create `scripts/run-venv.sh` — a thin wrapper that calls the venv python using its absolute path:

```bash
#!/usr/bin/env bash
exec "$(dirname "${BASH_SOURCE[0]}")/venv/bin/python3" "$@"
```

Add `Bash(scripts/run-venv.sh:*)` to `--allowedTools`. Update workflow-post.md to call `scripts/run-venv.sh` instead of `scripts/venv/bin/python3`. This is cwd-agnostic and single-level, so it matches cleanly regardless of whether cwd is SKILL_DIR or WORK_DIR.

## Context

From `TODO.md` — "Venv Permission Mismatch in Headless Subprocess" section.
EOF
)"
echo "Created: Venv Permission Mismatch"

echo ""
echo "All 6 issues created successfully!"
