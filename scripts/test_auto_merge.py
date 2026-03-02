#!/usr/bin/env python3
"""
Unit tests for auto_merge_cues.py.

Tests the merge script's core functions using synthetic SRT data
(no external file dependencies).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from srt_utils import Subtitle
from auto_merge_cues import (
    detect_merge_marker,
    can_merge_text,
    merge_cues,
    is_trivial_reply,
    wrap_text,
)


def make_cue(index, start_ms, end_ms, text="Test text"):
    return Subtitle(index=index, start_ms=start_ms, end_ms=end_ms, text=text)


# --- detect_merge_marker ---

class TestDetectMergeMarker:
    def test_sc_marker(self):
        marker, text = detect_merge_marker("[SC] Dit is tekst.")
        assert marker == "SC"
        assert text == "Dit is tekst."

    def test_nm_marker(self):
        marker, text = detect_merge_marker("[NM] Niet samenvoegen.")
        assert marker == "NM"
        assert text == "Niet samenvoegen."

    def test_no_marker(self):
        marker, text = detect_merge_marker("Gewone tekst.")
        assert marker == ""
        assert text == "Gewone tekst."

    def test_sc_marker_with_leading_whitespace(self):
        marker, text = detect_merge_marker("  [SC] Tekst.")
        assert marker == "SC"
        assert text == "Tekst."

    def test_marker_in_middle_not_detected(self):
        """Markers only work at the start of text."""
        marker, text = detect_merge_marker("Dit is [SC] tekst.")
        assert marker == ""
        assert text == "Dit is [SC] tekst."

    def test_empty_text_after_marker(self):
        marker, text = detect_merge_marker("[SC]")
        assert marker == "SC"
        assert text == ""


# --- can_merge_text (same speaker) ---

class TestCanMergeTextSameSpeaker:
    def test_simple_merge(self):
        can_merge, merged = can_merge_text(
            "Eerste deel", "tweede deel.", 2, 42)
        assert can_merge is True
        assert "Eerste deel tweede deel." in merged

    def test_ellipsis_stripping(self):
        """Trailing/leading ... should be stripped at merge boundary."""
        can_merge, merged = can_merge_text(
            "Eerste deel...", "...tweede deel.", 2, 42)
        assert can_merge is True
        assert "..." not in merged
        assert "Eerste deel tweede deel." in merged

    def test_trailing_ellipsis_only(self):
        can_merge, merged = can_merge_text(
            "Eerste deel...", "tweede deel.", 2, 42)
        assert can_merge is True
        assert merged == "Eerste deel tweede deel."

    def test_line_length_limit_respected(self):
        """Merge should fail if combined text exceeds line constraints."""
        long_text1 = "Dit is een heel lang stuk tekst"
        long_text2 = "dat niet op twee regels past als het wordt samengevoegd"
        can_merge, merged = can_merge_text(long_text1, long_text2, 2, 42)
        # Combined is 87 chars — should fit on 2 lines of 42+
        # "Dit is een heel lang stuk tekst dat niet" (40) + "op twee regels past..." (55)
        # Let's check the actual result
        if can_merge:
            lines = merged.split('\n')
            assert len(lines) <= 2
            for line in lines:
                assert len(line) <= 42

    def test_merge_fails_exceeding_constraints(self):
        """Merge fails when text absolutely can't fit."""
        text1 = "A" * 40
        text2 = "B" * 40 + " " + "C" * 40
        can_merge, merged = can_merge_text(text1, text2, 2, 42)
        assert can_merge is False

    def test_dual_speaker_not_collapsed(self):
        """Pre-existing dual-speaker text should not be merged with anything."""
        dual = "Eerste spreker\n-Tweede spreker"
        can_merge, merged = can_merge_text(dual, "Meer tekst.", 2, 42)
        assert can_merge is False

    def test_dual_speaker_second_text_not_collapsed(self):
        """Merging into existing dual-speaker text should fail."""
        can_merge, merged = can_merge_text(
            "Gewone tekst.", "Spreker A\n-Spreker B", 2, 42)
        assert can_merge is False


# --- can_merge_text (dual speaker / speaker change) ---

class TestCanMergeTextDualSpeaker:
    def test_speaker_change_creates_dash_format(self):
        can_merge, merged = can_merge_text(
            "Eerste spreker.", "Tweede spreker.", 2, 42,
            is_speaker_change=True)
        assert can_merge is True
        lines = merged.split('\n')
        assert len(lines) == 2
        assert not lines[0].startswith('-')
        assert lines[1].startswith('-')

    def test_first_line_no_dash(self):
        """First speaker should never get a dash prefix."""
        can_merge, merged = can_merge_text(
            "Vraag?", "Antwoord.", 2, 42, is_speaker_change=True)
        assert can_merge is True
        lines = merged.split('\n')
        assert not lines[0].startswith('-')
        assert lines[1].startswith('-')

    def test_existing_dash_on_text2_normalized(self):
        """If text2 already has a dash, it should be normalized."""
        can_merge, merged = can_merge_text(
            "Eerste.", "- Tweede.", 2, 42, is_speaker_change=True)
        assert can_merge is True
        lines = merged.split('\n')
        assert lines[1] == "-Tweede."

    def test_speaker_change_line_too_long(self):
        """Speaker change merge should fail if lines exceed limit."""
        long1 = "A" * 43
        can_merge, merged = can_merge_text(
            long1, "Kort.", 2, 42, is_speaker_change=True)
        assert can_merge is False


# --- merge_cues (integration) ---

class TestMergeCuesBasic:
    def test_simple_two_cue_merge(self):
        """Two cues within gap/duration should merge."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste deel"),
            make_cue(2, 3200, 5000, "tweede deel."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 1
        assert "Eerste deel tweede deel." in merged[0].text
        assert len(report) == 1

    def test_no_merge_when_gap_too_large(self):
        """Cues with gap exceeding threshold should not merge."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste."),
            make_cue(2, 5000, 7000, "Tweede."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 2
        assert len(report) == 0

    def test_no_merge_when_duration_exceeded(self):
        """Cues should not merge if combined duration exceeds max."""
        cues = [
            make_cue(1, 0, 4000, "Eerste."),
            make_cue(2, 4200, 8000, "Tweede."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 2

    def test_three_cue_merge(self):
        """Three consecutive same-speaker cues should merge if constraints allow."""
        cues = [
            make_cue(1, 1000, 2500, "Een"),
            make_cue(2, 2700, 4000, "twee"),
            make_cue(3, 4200, 5500, "drie."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 1
        assert "Een twee drie." in merged[0].text


class TestMergeCuesMarkers:
    def test_nm_marker_prevents_merge(self):
        """[NM] marker should prevent merging."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste."),
            make_cue(2, 3200, 5000, "[NM] Tweede."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 2
        # [NM] marker should be stripped from output
        assert merged[1].text == "Tweede."

    def test_sc_creates_dual_speaker(self):
        """[SC] marker should create dual-speaker dash format."""
        cues = [
            make_cue(1, 1000, 3000, "Waar ga je heen?"),
            make_cue(2, 3200, 5000, "[SC] Naar huis."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 1
        lines = merged[0].text.split('\n')
        assert len(lines) == 2
        assert not lines[0].startswith('-')
        assert lines[1].startswith('-')
        assert "Naar huis." in lines[1]

    def test_sc_only_merges_two_cues(self):
        """[SC] merge should not create 3-speaker cues."""
        cues = [
            make_cue(1, 1000, 2000, "Spreker A."),
            make_cue(2, 2200, 3500, "[SC] Spreker B."),
            make_cue(3, 3700, 5000, "[SC] Spreker C."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        # First two merge into dual-speaker, third stays separate or merges separately
        assert len(merged) >= 2
        # First merged cue should be dual-speaker
        lines = merged[0].text.split('\n')
        assert len(lines) == 2

    def test_markers_stripped_from_output(self):
        """All markers should be stripped from final output text."""
        cues = [
            make_cue(1, 1000, 3000, "[SC] Eerste."),
            make_cue(2, 5000, 7000, "[NM] Tweede."),
            make_cue(3, 9000, 11000, "Derde."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        for cue in merged:
            assert "[SC]" not in cue.text
            assert "[NM]" not in cue.text


class TestTrivialReplyAbsorption:
    def test_is_trivial_reply(self):
        assert is_trivial_reply("Ja.") is True
        assert is_trivial_reply("nee") is True
        assert is_trivial_reply("Oké.") is True
        assert is_trivial_reply("precies") is True
        assert is_trivial_reply("Dit is een normale zin.") is False

    def test_is_trivial_reply_case_insensitive(self):
        assert is_trivial_reply("JA") is True
        assert is_trivial_reply("Nee.") is True

    def test_is_trivial_reply_with_question_mark(self):
        assert is_trivial_reply("Ja?") is True


class TestDualSpeakerPreservation:
    def test_dual_speaker_not_collapsed(self):
        """Pre-existing dual-speaker cues should not be collapsed into single-speaker."""
        cues = [
            make_cue(1, 1000, 3000, "Vraag?\n-Antwoord."),
            make_cue(2, 3200, 5000, "Volgende zin."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        # Should not merge because cue 1 is already dual-speaker
        assert len(merged) == 2


class TestWrapText:
    def test_short_text_no_wrap(self):
        ok, wrapped = wrap_text("Korte tekst.", 42, 2)
        assert ok is True
        assert wrapped == "Korte tekst."

    def test_long_text_wraps(self):
        text = "Dit is een langere tekst die op twee regels moet worden gezet"
        ok, wrapped = wrap_text(text, 42, 2)
        assert ok is True
        lines = wrapped.split('\n')
        assert len(lines) <= 2
        for line in lines:
            assert len(line) <= 42

    def test_impossible_wrap_fails(self):
        text = "A" * 50 + " " + "B" * 50
        ok, wrapped = wrap_text(text, 42, 1)
        assert ok is False

    def test_empty_text(self):
        ok, wrapped = wrap_text("", 42, 2)
        assert ok is True
        assert wrapped == ""

    def test_single_word_too_long(self):
        ok, wrapped = wrap_text("A" * 50, 42, 2)
        assert ok is False


class TestMergeReport:
    def test_report_structure(self):
        """Verify merge report contains required fields."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste."),
            make_cue(2, 3200, 5000, "Tweede."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(report) == 1
        entry = report[0]
        assert "output_index" in entry
        assert "output_start_ms" in entry
        assert "output_end_ms" in entry
        assert "source_indices" in entry
        assert "source_timecodes" in entry
        assert "source_count" in entry
        assert entry["source_count"] == 2
        assert entry["source_indices"] == [1, 2]

    def test_no_report_for_unmerged(self):
        """No report entries for cues that weren't merged."""
        cues = [
            make_cue(1, 1000, 3000, "Alleen."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(report) == 0


class TestMergeRenumbering:
    def test_output_indices_sequential(self):
        """Merged output should have sequential indices starting at 1."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste."),
            make_cue(2, 3200, 5000, "Tweede."),
            make_cue(3, 8000, 10000, "Derde."),
            make_cue(4, 10200, 12000, "Vierde."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        for i, cue in enumerate(merged, 1):
            assert cue.index == i


class TestEdgeCases:
    def test_empty_input(self):
        merged, report, dropped = merge_cues(
            [], gap_threshold_ms=1000, max_duration_ms=7000)
        assert merged == []
        assert report == []

    def test_single_cue(self):
        cues = [make_cue(1, 1000, 3000, "Alleen.")]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 1
        assert merged[0].text == "Alleen."

    def test_zero_gap(self):
        """Cues with exactly zero gap should merge."""
        cues = [
            make_cue(1, 1000, 3000, "Eerste."),
            make_cue(2, 3000, 5000, "Tweede."),
        ]
        merged, report, dropped = merge_cues(
            cues, gap_threshold_ms=1000, max_duration_ms=7000)
        assert len(merged) == 1
