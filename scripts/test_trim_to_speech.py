#!/usr/bin/env python3
"""
Tests for trim_to_speech.py — uses synthetic speech maps, no audio needed.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import Subtitle

from trim_to_speech import compute_trim, trim_all


def make_cue(index, start_ms, end_ms, text="Tekst."):
    return Subtitle(index=index, start_ms=start_ms, end_ms=end_ms, text=text)


# Default test parameters (25fps)
DEFAULTS = dict(
    search_range=2000,
    comfort_buffer=250,
    min_trim=400,
    cps_soft_ceiling=17,
    cps_hard_limit=20,
    min_duration_ms=830,
    min_gap_ms=120,
)


class TestBasicTrim(unittest.TestCase):
    """Test the core trim decision."""

    def test_basic_trim(self):
        """Cue lingers 800ms after speech → trimmed to speech_end + buffer."""
        cue = make_cue(1, 1000, 3000, "Kort zinnetje.")
        result = compute_trim(cue, speech_ends=[2200], **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 2200 + 250)  # speech_end + buffer
        self.assertEqual(result['trim_ms'], 3000 - 2450)
        self.assertEqual(result['method'], 'full')

    def test_large_linger(self):
        """Cue lingers 1500ms → full trim."""
        cue = make_cue(1, 0, 3000, "Kort.")
        result = compute_trim(cue, speech_ends=[1500], **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 1750)
        self.assertEqual(result['trim_ms'], 1250)


class TestSkipConditions(unittest.TestCase):
    """Test all the skip conditions."""

    def test_skip_speech_extends_past_cue(self):
        """Speech ends AFTER cue end → don't trim."""
        cue = make_cue(1, 1000, 2000, "Tekst.")
        result = compute_trim(cue, speech_ends=[2500], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(result['reason'], 'speech_extends_past_cue')

    def test_skip_no_transition(self):
        """No speech transition near cue → skip."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        result = compute_trim(cue, speech_ends=[], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(result['reason'], 'no_transition')

    def test_skip_below_min_trim(self):
        """Linger of 300ms < min_trim 400ms → skip."""
        cue = make_cue(1, 1000, 2550, "Tekst.")
        # speech ends at 2300 → linger = 250ms < min_trim 400
        result = compute_trim(cue, speech_ends=[2300], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(result['reason'], 'below_min_trim')

    def test_skip_buffer_exceeds_current_end(self):
        """Speech ends just before cue end, buffer would push past → skip."""
        cue = make_cue(1, 1000, 2100, "Tekst.")
        # speech ends at 1900 → linger = 200ms. With min_trim=100, linger passes
        # the min_trim check. new_end = 1900+250 = 2150 > cue end 2100 → skip
        params = dict(DEFAULTS, min_trim=100)
        result = compute_trim(cue, speech_ends=[1900], **params)
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(result['reason'], 'buffer_exceeds_current_end')

    def test_skip_min_duration(self):
        """Trim would push duration below min_duration_ms → skip."""
        cue = make_cue(1, 1000, 3000, "Lange tekst hier en daar.")
        # speech ends at 1100 → new_end = 1350 → duration = 350ms < 830ms
        result = compute_trim(cue, speech_ends=[1100], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(result['reason'], 'min_duration')


class TestMinGapEnforcement(unittest.TestCase):
    """Test that min_gap_ms is enforced (not just overlap prevention)."""

    def test_gap_ok(self):
        """Trim leaves enough gap to next cue."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        next_cue = make_cue(2, 3500, 5000, "Meer.")
        result = compute_trim(
            cue, speech_ends=[2000], next_cue=next_cue, **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 2250)  # 3500 - 2250 = 1250 > 120

    def test_gap_clamp(self):
        """Trim + buffer would violate min_gap → clamp."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        next_cue = make_cue(2, 2300, 4000, "Meer.")
        # new_end = 2000+250 = 2250, but 2300-2250 = 50 < min_gap 120
        # clamp to 2300-120 = 2180
        result = compute_trim(
            cue, speech_ends=[2000], next_cue=next_cue, **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 2180)

    def test_gap_clamp_violates_min_duration(self):
        """Gap clamping pushes duration below minimum → skip."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        next_cue = make_cue(2, 1900, 4000, "Meer.")
        # new_end clamped to 1900-120=1780, duration=780 < 830ms → skip
        result = compute_trim(
            cue, speech_ends=[1500], next_cue=next_cue, **DEFAULTS)
        self.assertEqual(result['action'], 'skip')

    def test_last_cue_no_gap_constraint(self):
        """Last cue in file has no next-cue gap constraint."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        result = compute_trim(
            cue, speech_ends=[2000], next_cue=None, **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 2250)


class TestCPSGuard(unittest.TestCase):
    """Test CPS ceiling enforcement."""

    def test_full_trim_under_ceiling(self):
        """CPS after trim still under ceiling → full trim."""
        # 5 chars, 5000ms → 1 CPS. Trim to 3250ms → 5/3.25 = 1.5 CPS → fine
        cue = make_cue(1, 0, 5000, "Kort.")
        result = compute_trim(cue, speech_ends=[3000], **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['method'], 'full')

    def test_partial_trim_at_ceiling(self):
        """Full trim would exceed soft ceiling → partial trim."""
        # 90 chars, cue 0-6000ms = 15 CPS. Speech ends at 4500ms.
        # Full trim to 4750ms → 90/4.75 = 18.9 CPS (> soft ceiling 17, < hard 20)
        # Partial: end where CPS = 17 → 90/17*1000 = 5294ms
        cue = make_cue(1, 0, 6000, "A" * 90)
        result = compute_trim(cue, speech_ends=[4500], **DEFAULTS)
        self.assertEqual(result['action'], 'partial_trim')
        self.assertEqual(result['method'], 'partial')
        self.assertLessEqual(result['new_cps'], 17)
        self.assertGreater(result['trim_ms'], 0)

    def test_skip_cps_hard_limit(self):
        """CPS already near hard limit → skip."""
        # 40 chars, 2100ms → 19 CPS. Any trim makes it worse.
        # Speech ends at 500. target_end for cps_soft=17: 40/17*1000 = 2353 > 2100 → skip
        cue = make_cue(1, 0, 2100, "A" * 40)
        result = compute_trim(cue, speech_ends=[500], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')


class TestBatchTrim(unittest.TestCase):
    """Test batch processing."""

    def test_no_cascading_overlaps(self):
        """Trimming multiple sequential cues preserves min_gap."""
        cues = [
            make_cue(1, 0, 2000, "Een."),
            make_cue(2, 2200, 4000, "Twee."),
            make_cue(3, 4200, 6000, "Drie."),
        ]
        speech_ends = [1200, 3200, 5200]
        results = trim_all(cues, speech_ends, **DEFAULTS)

        # Check gaps between cues
        for i in range(len(cues) - 1):
            gap = cues[i + 1].start_ms - cues[i].end_ms
            self.assertGreaterEqual(gap, 120,
                f'Gap between cue {i+1} and {i+2}: {gap}ms < 120ms')

    def test_dry_run_no_modification(self):
        """Dry run must not modify cues."""
        cues = [make_cue(1, 0, 3000, "Test.")]
        original_end = cues[0].end_ms
        trim_all(cues, [1500], dry_run=True, **DEFAULTS)
        self.assertEqual(cues[0].end_ms, original_end)

    def test_dry_run_still_reports(self):
        """Dry run still returns trim decisions."""
        cues = [make_cue(1, 0, 3000, "Test.")]
        results = trim_all(cues, [1500], dry_run=True, **DEFAULTS)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['action'], 'trim')

    def test_actual_trim_modifies_cues(self):
        """Non-dry-run actually modifies cue end times."""
        cues = [make_cue(1, 0, 3000, "Test.")]
        trim_all(cues, [1500], dry_run=False, **DEFAULTS)
        self.assertNotEqual(cues[0].end_ms, 3000)
        self.assertEqual(cues[0].end_ms, 1750)  # 1500 + 250 buffer


class TestEdgeCases(unittest.TestCase):
    """Miscellaneous edge cases."""

    def test_speech_end_exactly_at_cue_end(self):
        """Speech ends exactly at cue end → linger is 0 < min_trim → skip."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        result = compute_trim(cue, speech_ends=[3000], **DEFAULTS)
        self.assertEqual(result['action'], 'skip')

    def test_multiple_speech_ends_picks_nearest(self):
        """With multiple transitions, find_nearest picks closest to cue end."""
        cue = make_cue(1, 5000, 8000, "Tekst.")
        # speech ends at 6000, 7200, 9000
        # cue end = 8000, nearest = 7200 (distance 800)
        result = compute_trim(cue, speech_ends=[6000, 7200, 9000], **DEFAULTS)
        self.assertEqual(result['action'], 'trim')
        self.assertEqual(result['new_end'], 7200 + 250)

    def test_empty_cue_list(self):
        """Empty cue list produces empty results."""
        results = trim_all([], [1500], **DEFAULTS)
        self.assertEqual(results, [])

    def test_single_cue_file(self):
        """Single cue with no next cue trims normally."""
        cues = [make_cue(1, 0, 5000, "Kort.")]
        results = trim_all(cues, [3000], **DEFAULTS)
        self.assertEqual(results[0]['action'], 'trim')
        self.assertEqual(cues[0].end_ms, 3250)


if __name__ == '__main__':
    unittest.main()
