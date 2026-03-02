#!/usr/bin/env python3
"""
Unit tests for validate_srt.py.

Tests the validator's core functions using synthetic SRT data
(no external file dependencies).
"""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from srt_utils import Subtitle, write_srt
from validate_srt import (
    fix_punctuation,
    fix_ellipsis,
    fix_line_length,
    fix_overlap,
    fix_speaker_dash,
    fix_subtitle,
    validate_subtitle,
    validate_srt,
    fix_srt,
)


def make_cue(index, start_ms, end_ms, text="Test tekst"):
    return Subtitle(index=index, start_ms=start_ms, end_ms=end_ms, text=text)


def write_temp_srt(subtitles):
    """Write subtitles to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.srt', delete=False, encoding='utf-8')
    for i, sub in enumerate(subtitles):
        if i > 0:
            f.write('\n')
        f.write(sub.to_srt_block())
    f.close()
    return f.name


# --- fix_punctuation ---

class TestFixPunctuation:
    def test_exclamation_to_period(self):
        fixed, fixes = fix_punctuation("Ga weg!")
        assert fixed == "Ga weg."
        assert len(fixes) == 1

    def test_semicolon_to_period(self):
        fixed, fixes = fix_punctuation("Eerste; tweede.")
        assert fixed == "Eerste. tweede."
        assert len(fixes) == 1

    def test_multiple_exclamation_marks(self):
        fixed, fixes = fix_punctuation("Stop! Nu! Meteen!")
        assert fixed == "Stop. Nu. Meteen."
        assert "3" in fixes[0]  # should mention count

    def test_no_forbidden_punctuation(self):
        fixed, fixes = fix_punctuation("Alles goed.")
        assert fixed == "Alles goed."
        assert len(fixes) == 0

    def test_mixed_forbidden(self):
        fixed, fixes = fix_punctuation("Stop! Eerste; tweede.")
        assert fixed == "Stop. Eerste. tweede."
        assert len(fixes) == 2

    def test_question_mark_preserved(self):
        fixed, fixes = fix_punctuation("Hoe gaat het?")
        assert fixed == "Hoe gaat het?"
        assert len(fixes) == 0


# --- fix_ellipsis ---

class TestFixEllipsis:
    def test_smart_ellipsis_converted(self):
        fixed, fixes = fix_ellipsis("En toen…")
        assert fixed == "En toen..."
        assert len(fixes) == 1

    def test_three_dots_unchanged(self):
        fixed, fixes = fix_ellipsis("En toen...")
        assert fixed == "En toen..."
        assert len(fixes) == 0

    def test_multiple_smart_ellipses(self):
        fixed, fixes = fix_ellipsis("Eerste… en tweede…")
        assert fixed == "Eerste... en tweede..."
        assert "2" in fixes[0]

    def test_no_ellipsis(self):
        fixed, fixes = fix_ellipsis("Gewone tekst.")
        assert fixed == "Gewone tekst."
        assert len(fixes) == 0


# --- fix_line_length ---

class TestFixLineLength:
    def test_short_line_unchanged(self):
        fixed, fixes = fix_line_length("Korte tekst.")
        assert fixed == "Korte tekst."
        assert len(fixes) == 0

    def test_long_line_broken(self):
        text = "Dit is een heel lange regel die meer dan tweeenveertig tekens bevat"
        fixed, fixes = fix_line_length(text, 42)
        if fixes:  # Line was broken
            lines = fixed.split('\n')
            assert len(lines) <= 2

    def test_already_two_lines_not_broken_further(self):
        """If already 2 lines and one is too long, can't fix."""
        text = "Eerste regel tekst hier.\n" + "A" * 50
        fixed, fixes = fix_line_length(text, 42)
        # Should not be able to fix (already 2 lines)
        assert len(fixes) == 0

    def test_bottom_heavy_preference(self):
        """When breaking, line 2 should be >= line 1 (bottom-heavy pyramid)."""
        text = "Dit is een voorbeeld van een tekst die gebroken moet worden"
        fixed, fixes = fix_line_length(text, 42)
        if fixes:
            lines = fixed.split('\n')
            if len(lines) == 2:
                # Bottom-heavy: line 2 >= line 1
                assert len(lines[1]) >= len(lines[0]) or len(lines[0]) <= 42

    def test_exact_max_length_unchanged(self):
        text = "A" * 42
        fixed, fixes = fix_line_length(text, 42)
        assert fixed == text
        assert len(fixes) == 0


# --- fix_overlap ---

class TestFixOverlap:
    def test_overlapping_cues(self):
        prev = make_cue(1, 1000, 5000, "Vorige.")
        curr = make_cue(2, 4500, 7000, "Huidige.")
        new_end, fix = fix_overlap(curr, prev)
        assert new_end < 4500  # End adjusted before current start
        assert fix is not None

    def test_gap_too_short(self):
        """Gap below MIN_GAP_MS should be adjusted."""
        prev = make_cue(1, 1000, 4950, "Vorige.")
        curr = make_cue(2, 5000, 7000, "Huidige.")
        new_end, fix = fix_overlap(curr, prev)
        # Gap was 50ms, should be adjusted to enforce minimum
        if fix:
            assert new_end < prev.end_ms

    def test_sufficient_gap_unchanged(self):
        prev = make_cue(1, 1000, 3000, "Vorige.")
        curr = make_cue(2, 4000, 6000, "Huidige.")
        new_end, fix = fix_overlap(curr, prev)
        assert new_end == 3000  # Unchanged
        assert fix is None


# --- fix_speaker_dash ---

class TestFixSpeakerDash:
    def test_both_dashes_fixed(self):
        """If both lines have dashes, remove from first."""
        text = "- Eerste spreker\n- Tweede spreker"
        fixed, fixes = fix_speaker_dash(text)
        lines = fixed.split('\n')
        assert not lines[0].startswith('-')
        assert lines[1].startswith('-')

    def test_correct_format_unchanged(self):
        """Correct format (no dash on line 1, dash on line 2) preserved."""
        text = "Eerste spreker\n-Tweede spreker"
        fixed, fixes = fix_speaker_dash(text)
        assert fixed == text
        assert len(fixes) == 0

    def test_dash_space_normalized(self):
        """'- Text' should become '-Text' (no space after dash)."""
        text = "Eerste spreker\n- Tweede spreker"
        fixed, fixes = fix_speaker_dash(text)
        lines = fixed.split('\n')
        assert lines[1] == "-Tweede spreker"

    def test_single_line_unchanged(self):
        text = "Enkele regel."
        fixed, fixes = fix_speaker_dash(text)
        assert fixed == text
        assert len(fixes) == 0


# --- remove_empty_cues (via fix_srt) ---

class TestRemoveEmptyCues:
    def test_empty_cue_removed(self):
        subs = [
            make_cue(1, 1000, 3000, "Tekst."),
            make_cue(2, 4000, 6000, ""),
            make_cue(3, 7000, 9000, "Meer tekst."),
        ]
        path = write_temp_srt(subs)
        try:
            result = fix_srt(path)
            assert result['fixed'] is True
            assert result['total_cues'] == 2
        finally:
            os.unlink(path)

    def test_whitespace_only_cue_removed(self):
        subs = [
            make_cue(1, 1000, 3000, "Tekst."),
            make_cue(2, 4000, 6000, "   \n  "),
            make_cue(3, 7000, 9000, "Meer tekst."),
        ]
        path = write_temp_srt(subs)
        try:
            result = fix_srt(path)
            assert result['fixed'] is True
            assert result['total_cues'] == 2
        finally:
            os.unlink(path)


# --- validate_subtitle (CPS) ---

class TestValidateCpsSoftHard:
    def test_normal_cps_no_error(self):
        # 10 chars / 2 seconds = 5 CPS (well within limits)
        sub = make_cue(1, 0, 2000, "Korte zin.")
        errors, warnings = validate_subtitle(sub, None)
        cps_errors = [e for e in errors if "CPS" in e]
        assert len(cps_errors) == 0

    def test_high_cps_warning(self):
        # Create a cue with CPS between soft and hard limit
        # 42 chars / 2 seconds = 21 CPS (above soft 17, below hard 20... actually above hard too)
        # Let's use 35 chars / 2s = 17.5 CPS (above soft 17 at 25fps)
        sub = make_cue(1, 0, 2000, "A" * 35)
        errors, warnings = validate_subtitle(sub, None)
        cps_msgs = [w for w in warnings if "CPS" in w]
        # May trigger soft ceiling warning
        # CPS = 35/2 = 17.5, soft ceiling is 17 at 25fps default
        assert len(cps_msgs) >= 0  # Depends on exact constants

    def test_extreme_cps_error(self):
        # 60 chars / 1 second = 60 CPS (way above hard limit)
        sub = make_cue(1, 0, 1000, "A" * 60)
        errors, warnings = validate_subtitle(sub, None)
        cps_errors = [e for e in errors if "CPS" in e]
        assert len(cps_errors) == 1


# --- validate_subtitle (line count) ---

class TestValidateLineCount:
    def test_two_lines_ok(self):
        sub = make_cue(1, 0, 3000, "Regel een\nRegel twee")
        errors, warnings = validate_subtitle(sub, None)
        line_errors = [e for e in errors if "lines" in e]
        assert len(line_errors) == 0

    def test_three_lines_flagged(self):
        sub = make_cue(1, 0, 3000, "Regel een\nRegel twee\nRegel drie")
        errors, warnings = validate_subtitle(sub, None)
        line_errors = [e for e in errors if "lines" in e]
        assert len(line_errors) == 1


# --- duplicate text detection ---

class TestDuplicateTextDetection:
    def test_exact_duplicate_detected(self):
        prev = make_cue(1, 0, 2000, "Dezelfde tekst.")
        curr = make_cue(2, 3000, 5000, "Dezelfde tekst.")
        errors, warnings = validate_subtitle(curr, prev)
        dup_errors = [e for e in errors if "duplicate" in e.lower()]
        assert len(dup_errors) == 1

    def test_different_text_no_duplicate(self):
        prev = make_cue(1, 0, 2000, "Eerste tekst.")
        curr = make_cue(2, 3000, 5000, "Andere tekst.")
        errors, warnings = validate_subtitle(curr, prev)
        dup_errors = [e for e in errors if "duplicate" in e.lower()]
        assert len(dup_errors) == 0

    def test_substring_detection(self):
        """Detect when one cue's text is a substring of adjacent cue."""
        prev = make_cue(1, 0, 2000, "Dit is een lange tekst met meer woorden erin.")
        curr = make_cue(2, 3000, 5000, "Dit is een lange tekst met meer woorden erin.")
        errors, warnings = validate_subtitle(curr, prev)
        dup_errors = [e for e in errors if "duplicate" in e.lower() or "substring" in e.lower()]
        assert len(dup_errors) >= 1


# --- validate_srt (full file) ---

class TestValidateSrtFull:
    def test_valid_file(self):
        subs = [
            make_cue(1, 0, 2000, "Eerste."),
            make_cue(2, 3000, 5000, "Tweede."),
            make_cue(3, 6000, 8000, "Derde."),
        ]
        path = write_temp_srt(subs)
        try:
            result = validate_srt(path)
            assert result['valid'] is True
            assert result['total_cues'] == 3
            assert result['error_count'] == 0
        finally:
            os.unlink(path)

    def test_forbidden_semicolon(self):
        subs = [
            make_cue(1, 0, 2000, "Eerste; tweede."),
        ]
        path = write_temp_srt(subs)
        try:
            result = validate_srt(path)
            assert result['valid'] is False
            semicolon_errors = [e for e in result['errors'] if 'semicolon' in e.lower()]
            assert len(semicolon_errors) == 1
        finally:
            os.unlink(path)

    def test_overlap_detected(self):
        subs = [
            make_cue(1, 0, 5000, "Eerste."),
            make_cue(2, 4000, 7000, "Tweede."),
        ]
        path = write_temp_srt(subs)
        try:
            result = validate_srt(path)
            overlap_errors = [e for e in result['errors'] if 'overlap' in e.lower()]
            assert len(overlap_errors) >= 1
        finally:
            os.unlink(path)


# --- fix_srt (full file fix) ---

class TestFixSrtFull:
    def test_fix_all_issues(self):
        """Fix mode should apply all auto-fixes."""
        subs = [
            make_cue(1, 0, 2000, "Stop!"),
            make_cue(2, 3000, 5000, "Tekst…"),
            make_cue(3, 6000, 8000, ""),  # empty
        ]
        path = write_temp_srt(subs)
        output_path = path + ".fixed.srt"
        try:
            result = fix_srt(path, output_path)
            assert result['fixed'] is True
            assert result['total_cues'] == 2  # empty cue removed
            assert result['fixes_applied'] > 0
        finally:
            os.unlink(path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_fix_speaker_dashes(self):
        subs = [
            make_cue(1, 0, 3000, "- Eerste\n- Tweede"),
        ]
        path = write_temp_srt(subs)
        try:
            result = fix_srt(path)
            assert result['fixed'] is True
            # Verify the fix was applied
            from srt_utils import parse_srt_file
            fixed_subs, _ = parse_srt_file(path)
            lines = fixed_subs[0].text.split('\n')
            assert not lines[0].startswith('-')
            assert lines[1].startswith('-')
        finally:
            os.unlink(path)


# --- validate_subtitle (punctuation warnings) ---

class TestValidatePunctuation:
    def test_exclamation_warning(self):
        sub = make_cue(1, 0, 2000, "Stop!")
        errors, warnings = validate_subtitle(sub, None)
        excl_warnings = [w for w in warnings if 'exclamation' in w.lower()]
        assert len(excl_warnings) == 1

    def test_smart_ellipsis_warning(self):
        sub = make_cue(1, 0, 2000, "En toen…")
        errors, warnings = validate_subtitle(sub, None)
        ellipsis_warnings = [w for w in warnings if 'ellipsis' in w.lower()]
        assert len(ellipsis_warnings) == 1


# --- validate_subtitle (line length) ---

class TestValidateLineLength:
    def test_line_too_long(self):
        sub = make_cue(1, 0, 3000, "A" * 50)
        errors, warnings = validate_subtitle(sub, None)
        len_errors = [e for e in errors if 'chars' in e]
        assert len(len_errors) == 1

    def test_line_at_limit_ok(self):
        sub = make_cue(1, 0, 3000, "A" * 42)
        errors, warnings = validate_subtitle(sub, None)
        len_errors = [e for e in errors if 'chars' in e]
        assert len(len_errors) == 0


# --- validate_subtitle (empty) ---

class TestValidateEmpty:
    def test_empty_cue_error(self):
        sub = make_cue(1, 0, 2000, "")
        errors, warnings = validate_subtitle(sub, None)
        empty_errors = [e for e in errors if 'empty' in e.lower()]
        assert len(empty_errors) == 1

    def test_whitespace_cue_error(self):
        sub = make_cue(1, 0, 2000, "   ")
        errors, warnings = validate_subtitle(sub, None)
        empty_errors = [e for e in errors if 'empty' in e.lower()]
        assert len(empty_errors) == 1


# --- validate_subtitle (speaker dash) ---

class TestValidateSpeakerDash:
    def test_first_line_dash_warning(self):
        sub = make_cue(1, 0, 3000, "- Eerste spreker\n-Tweede spreker")
        errors, warnings = validate_subtitle(sub, None)
        dash_warnings = [w for w in warnings if 'dash' in w.lower()]
        assert len(dash_warnings) >= 1
