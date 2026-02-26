#!/usr/bin/env python3
"""
Tests for merge-aware and draft-mapping cue matching (Levels 1+2).

Tests the new timecode-based NL→EN mapping in vad_timing_check.py
and the draft mapping in save_draft_mapping.py.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import Subtitle

from vad_timing_check import (
    match_source_cues,
    load_merge_report,
    build_merge_timecode_map,
    match_source_cues_enhanced,
    load_draft_mapping,
    build_draft_timecode_map,
    _match_by_proximity,
    _nearest_en,
    _draft_lookup,
)
from save_draft_mapping import build_mapping


def make_cue(index, start_ms, end_ms, text=""):
    return Subtitle(index=index, start_ms=start_ms, end_ms=end_ms, text=text)


class TestOriginalMatching(unittest.TestCase):
    """Verify the original match_source_cues still works unchanged."""

    def test_exact_match(self):
        nl = [make_cue(1, 1000, 2000)]
        en = [make_cue(1, 1000, 2000)]
        matches = match_source_cues(nl, en)
        self.assertEqual(len(matches[1]), 1)
        self.assertEqual(matches[1][0].start_ms, 1000)

    def test_proximity_match(self):
        nl = [make_cue(1, 1000, 2000)]
        en = [make_cue(1, 1300, 2300)]
        matches = match_source_cues(nl, en, tolerance_ms=500)
        self.assertEqual(len(matches[1]), 1)

    def test_no_match_beyond_tolerance(self):
        nl = [make_cue(1, 1000, 2000)]
        en = [make_cue(1, 5000, 6000)]
        matches = match_source_cues(nl, en, tolerance_ms=500)
        self.assertEqual(len(matches[1]), 0)


class TestMergeReportLoading(unittest.TestCase):
    """Test merge report loading and timecode map construction."""

    def test_load_merge_report_nonexistent(self):
        self.assertEqual(load_merge_report("/nonexistent/path.json"), [])
        self.assertEqual(load_merge_report(None), [])

    def test_load_merge_report_valid(self):
        data = {
            "merges": [
                {
                    "output_index": 5,
                    "output_start_ms": 10000,
                    "output_end_ms": 14000,
                    "source_indices": [5, 6],
                    "source_timecodes": [
                        {"start_ms": 10000, "end_ms": 12000},
                        {"start_ms": 12500, "end_ms": 14000},
                    ],
                    "source_count": 2,
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            merges = load_merge_report(f.name)
        os.unlink(f.name)

        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]['output_start_ms'], 10000)

    def test_build_merge_timecode_map(self):
        merges = [
            {
                "output_start_ms": 10000,
                "source_timecodes": [
                    {"start_ms": 10000, "end_ms": 12000},
                    {"start_ms": 12500, "end_ms": 14000},
                ],
            },
            {
                "output_start_ms": 20000,
                "source_timecodes": [
                    {"start_ms": 20000, "end_ms": 22000},
                    {"start_ms": 22100, "end_ms": 24000},
                ],
            },
        ]
        tc_map = build_merge_timecode_map(merges)
        self.assertIn(10000, tc_map)
        self.assertIn(20000, tc_map)
        self.assertEqual(len(tc_map[10000]), 2)


class TestEnhancedMatching(unittest.TestCase):
    """Test merge-aware NL→EN matching."""

    def setUp(self):
        # EN cues: 20 cues, each 2s long, 500ms apart
        self.en_cues = [
            make_cue(i, i * 2500, i * 2500 + 2000, f"EN cue {i}")
            for i in range(1, 21)
        ]

    def test_merged_cue_matches_both_sources(self):
        """A merged NL cue (from EN 5+6) should match both EN 5 and EN 6."""
        # EN cue 5: 12500-14500, EN cue 6: 15000-17000
        # Merged NL cue starts at 12500, ends at 17000
        nl_cues = [make_cue(1, 12500, 17000, "Merged cue")]

        merge_tc_map = {
            12500: [
                {"start_ms": 12500, "end_ms": 14500},
                {"start_ms": 15000, "end_ms": 17000},
            ]
        }

        matches = match_source_cues_enhanced(
            nl_cues, self.en_cues, merge_tc_map=merge_tc_map)

        self.assertIn(1, matches)
        matched_indices = [en.index for en in matches[1]]
        self.assertIn(5, matched_indices)
        self.assertIn(6, matched_indices)

    def test_non_merged_cue_uses_proximity(self):
        """Non-merged cues fall back to proximity matching."""
        nl_cues = [make_cue(1, 2500, 4500, "Single cue")]
        merge_tc_map = {99999: []}  # No match for this NL cue's start_ms

        matches = match_source_cues_enhanced(
            nl_cues, self.en_cues, merge_tc_map=merge_tc_map)

        self.assertIn(1, matches)
        self.assertTrue(len(matches[1]) > 0)
        # Should match EN cue 1 (start_ms=2500)
        self.assertEqual(matches[1][0].index, 1)

    def test_no_merge_report_falls_back(self):
        """With no merge report, behaves like proximity matching."""
        nl_cues = [make_cue(1, 2500, 4500)]

        matches = match_source_cues_enhanced(
            nl_cues, self.en_cues, merge_tc_map=None)

        self.assertIn(1, matches)
        self.assertTrue(len(matches[1]) > 0)

    def test_merge_timecode_tolerance(self):
        """Merge matching works within 50ms tolerance of output_start_ms."""
        nl_cues = [make_cue(1, 12530, 17000)]  # 30ms off from 12500

        merge_tc_map = {
            12500: [
                {"start_ms": 12500, "end_ms": 14500},
                {"start_ms": 15000, "end_ms": 17000},
            ]
        }

        matches = match_source_cues_enhanced(
            nl_cues, self.en_cues, merge_tc_map=merge_tc_map)

        matched_indices = [en.index for en in matches[1]]
        self.assertIn(5, matched_indices)
        self.assertIn(6, matched_indices)

    def test_merge_timecode_beyond_tolerance(self):
        """Merge matching does NOT match beyond 50ms tolerance."""
        nl_cues = [make_cue(1, 12600, 17000)]  # 100ms off from 12500

        merge_tc_map = {
            12500: [
                {"start_ms": 12500, "end_ms": 14500},
                {"start_ms": 15000, "end_ms": 17000},
            ]
        }

        matches = match_source_cues_enhanced(
            nl_cues, self.en_cues, merge_tc_map=merge_tc_map)

        # Should NOT use merge map, falls back to proximity
        matched_indices = [en.index for en in matches[1]]
        # Proximity should find EN 5 (12500) but not necessarily EN 6
        self.assertIn(5, matched_indices)


class TestDraftMapping(unittest.TestCase):
    """Test draft mapping loading and NL→EN chain."""

    def test_load_draft_mapping_nonexistent(self):
        self.assertEqual(load_draft_mapping(None), [])
        self.assertEqual(load_draft_mapping("/nonexistent.json"), [])

    def test_load_draft_mapping_valid(self):
        data = {
            "mappings": [
                {"nl_start_ms": 1000, "nl_end_ms": 3000,
                 "en_start_ms": 1000, "en_end_ms": 3000},
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            mappings = load_draft_mapping(f.name)
        os.unlink(f.name)

        self.assertEqual(len(mappings), 1)

    def test_build_draft_timecode_map(self):
        mappings = [
            {"nl_start_ms": 1000, "nl_end_ms": 3000,
             "en_start_ms": 1000, "en_end_ms": 3000},
            {"nl_start_ms": 5000, "nl_end_ms": 7000,
             "en_start_ms": 5000, "en_end_ms": 7000},
            {"nl_start_ms": 9000, "nl_end_ms": 11000,
             "en_start_ms": None, "en_end_ms": None},  # unmatched
        ]
        tc_map = build_draft_timecode_map(mappings)
        self.assertIn(1000, tc_map)
        self.assertIn(5000, tc_map)
        self.assertNotIn(9000, tc_map)  # None entries excluded

    def test_draft_lookup_hit(self):
        en_cues = [
            make_cue(1, 1000, 3000),
            make_cue(2, 5000, 7000),
        ]
        draft_tc_map = {
            1000: {"en_start_ms": 1000, "en_end_ms": 3000},
        }
        result = _draft_lookup(1000, draft_tc_map, en_cues, tolerance=50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].index, 1)

    def test_draft_lookup_miss(self):
        en_cues = [make_cue(1, 1000, 3000)]
        draft_tc_map = {
            5000: {"en_start_ms": 5000, "en_end_ms": 7000},
        }
        result = _draft_lookup(1000, draft_tc_map, en_cues, tolerance=50)
        self.assertEqual(len(result), 0)

    def test_enhanced_matching_with_draft(self):
        """Draft mapping takes priority over proximity for non-merged cues."""
        en_cues = [
            make_cue(1, 1000, 3000),
            make_cue(2, 3500, 5500),
            make_cue(3, 6000, 8000),
        ]
        # NL cue has start_ms=1000, which proximity would match to EN 1.
        # Draft mapping says this NL cue corresponds to EN at 1000-3000.
        nl_cues = [make_cue(1, 1000, 3000)]

        draft_tc_map = {
            1000: {"en_start_ms": 1000, "en_end_ms": 3000},
        }

        matches = match_source_cues_enhanced(
            nl_cues, en_cues, draft_tc_map=draft_tc_map)

        self.assertEqual(len(matches[1]), 1)
        self.assertEqual(matches[1][0].index, 1)


class TestDraftMappingWithMerge(unittest.TestCase):
    """Test the full chain: merge report + draft mapping together."""

    def test_full_chain(self):
        """
        Scenario: EN has cues 1-10. NL draft had cues matching EN 1-10
        by timecodes. Phase 4 merged NL cues 3+4 into one. Phase 9
        should correctly map the merged NL cue back to EN 3 and EN 4.
        """
        en_cues = [
            make_cue(i, i * 3000, i * 3000 + 2500, f"EN {i}")
            for i in range(1, 11)
        ]
        # After merging, NL cue 3 spans EN 3+4 time range
        # EN 3: 9000-11500, EN 4: 12000-14500
        nl_cues = [
            make_cue(1, 3000, 5500),   # matches EN 1
            make_cue(2, 6000, 8500),   # matches EN 2
            make_cue(3, 9000, 14500),  # merged from EN 3+4
            make_cue(4, 15000, 17500), # matches EN 5
        ]

        merge_tc_map = {
            9000: [
                {"start_ms": 9000, "end_ms": 11500},
                {"start_ms": 12000, "end_ms": 14500},
            ]
        }

        # Draft mapping: draft NL cue at 9000 → EN 9000-11500,
        #                draft NL cue at 12000 → EN 12000-14500
        draft_tc_map = {
            3000: {"en_start_ms": 3000, "en_end_ms": 5500},
            6000: {"en_start_ms": 6000, "en_end_ms": 8500},
            9000: {"en_start_ms": 9000, "en_end_ms": 11500},
            12000: {"en_start_ms": 12000, "en_end_ms": 14500},
            15000: {"en_start_ms": 15000, "en_end_ms": 17500},
        }

        matches = match_source_cues_enhanced(
            nl_cues, en_cues, merge_tc_map, draft_tc_map)

        # NL cue 1 → EN 1
        self.assertEqual(matches[1][0].index, 1)
        # NL cue 2 → EN 2
        self.assertEqual(matches[2][0].index, 2)
        # NL cue 3 (merged) → EN 3 + EN 4
        merged_indices = sorted(en.index for en in matches[3])
        self.assertEqual(merged_indices, [3, 4])
        # NL cue 4 → EN 5
        self.assertEqual(matches[4][0].index, 5)


class TestSaveDraftMapping(unittest.TestCase):
    """Test the build_mapping function from save_draft_mapping.py."""

    def test_exact_match(self):
        nl_cues = [make_cue(1, 1000, 3000)]
        en_cues = [make_cue(1, 1000, 3000)]
        result = build_mapping(nl_cues, en_cues)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['en_start_ms'], 1000)
        self.assertEqual(result[0]['en_end_ms'], 3000)

    def test_proximity_match(self):
        nl_cues = [make_cue(1, 1050, 3050)]
        en_cues = [make_cue(1, 1000, 3000)]
        result = build_mapping(nl_cues, en_cues, tolerance_ms=500)
        self.assertEqual(result[0]['en_start_ms'], 1000)

    def test_no_match(self):
        nl_cues = [make_cue(1, 1000, 3000)]
        en_cues = [make_cue(1, 50000, 52000)]
        result = build_mapping(nl_cues, en_cues, tolerance_ms=500, fallback_ms=1000)
        self.assertIsNone(result[0]['en_start_ms'])

    def test_fallback_match(self):
        """Nearest EN cue within fallback tolerance."""
        nl_cues = [make_cue(1, 1000, 3000)]
        en_cues = [make_cue(1, 1800, 3800)]  # 800ms off
        result = build_mapping(nl_cues, en_cues, tolerance_ms=500, fallback_ms=1000)
        self.assertEqual(result[0]['en_start_ms'], 1800)

    def test_sdh_skip_sequential_numbering(self):
        """
        Scenario: EN has cues 1,2,3(SDH),4,5. Claude translates to NL
        with sequential numbering 1,2,3,4 (skipping SDH). The mapping
        should still match by timecodes regardless of index mismatch.
        """
        en_cues = [
            make_cue(1, 1000, 3000, "EN 1"),
            make_cue(2, 4000, 6000, "EN 2"),
            make_cue(3, 7000, 9000, "[sound effect]"),  # SDH
            make_cue(4, 10000, 12000, "EN 4"),
            make_cue(5, 13000, 15000, "EN 5"),
        ]
        # NL draft: Claude skipped SDH cue and numbered sequentially
        nl_cues = [
            make_cue(1, 1000, 3000, "NL 1"),
            make_cue(2, 4000, 6000, "NL 2"),
            make_cue(3, 10000, 12000, "NL 3"),  # was EN 4
            make_cue(4, 13000, 15000, "NL 4"),  # was EN 5
        ]

        result = build_mapping(nl_cues, en_cues)

        # NL 1 → EN 1
        self.assertEqual(result[0]['en_indices'], [1])
        # NL 2 → EN 2
        self.assertEqual(result[1]['en_indices'], [2])
        # NL 3 → EN 4 (not EN 3/SDH)
        self.assertEqual(result[2]['en_indices'], [4])
        # NL 4 → EN 5
        self.assertEqual(result[3]['en_indices'], [5])

    def test_multiple_en_within_tolerance(self):
        """When multiple EN cues are within tolerance, all are matched."""
        nl_cues = [make_cue(1, 5000, 9000)]
        en_cues = [
            make_cue(1, 5000, 6500),
            make_cue(2, 5200, 7000),  # within 500ms of NL start
        ]
        result = build_mapping(nl_cues, en_cues, tolerance_ms=500)
        self.assertEqual(len(result[0]['en_indices']), 2)


class TestHelperFunctions(unittest.TestCase):
    """Test _match_by_proximity and _nearest_en."""

    def test_match_by_proximity_range(self):
        en_cues = [
            make_cue(1, 1000, 3000),
            make_cue(2, 3500, 5500),
            make_cue(3, 6000, 8000),
        ]
        nl = make_cue(1, 1000, 5000)  # spans EN 1 and 2
        result = _match_by_proximity(nl, en_cues, tolerance_ms=500)
        indices = [en.index for en in result]
        self.assertIn(1, indices)
        self.assertIn(2, indices)

    def test_nearest_en_within_tolerance(self):
        en_cues = [make_cue(1, 5000, 7000)]
        nl = make_cue(1, 5300, 7300)
        result = _nearest_en(nl, en_cues, tolerance_ms=500)
        self.assertEqual(len(result), 1)

    def test_nearest_en_beyond_tolerance(self):
        en_cues = [make_cue(1, 50000, 52000)]
        nl = make_cue(1, 1000, 3000)
        result = _nearest_en(nl, en_cues, tolerance_ms=500)
        self.assertEqual(len(result), 0)

    def test_nearest_en_empty(self):
        nl = make_cue(1, 1000, 3000)
        result = _nearest_en(nl, [], tolerance_ms=500)
        self.assertEqual(len(result), 0)


class TestAutoMergeCuesReport(unittest.TestCase):
    """Test that auto_merge_cues.py produces the enhanced merge report."""

    def test_merge_report_has_timecodes(self):
        """Verify the merge report includes output_start_ms, output_end_ms,
        and source_timecodes when cues are merged."""
        from auto_merge_cues import merge_cues

        cues = [
            make_cue(1, 1000, 3000, "First cue"),
            make_cue(2, 3200, 5000, "Second cue"),  # 200ms gap
            make_cue(3, 10000, 12000, "Third cue"),  # 5000ms gap — no merge
        ]

        merged, report = merge_cues(cues, gap_threshold_ms=1000,
                                     max_duration_ms=7000)

        # Cues 1+2 should merge, cue 3 stays separate
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(report), 1)

        entry = report[0]
        self.assertIn('output_start_ms', entry)
        self.assertIn('output_end_ms', entry)
        self.assertIn('source_timecodes', entry)
        self.assertEqual(entry['output_start_ms'], 1000)
        self.assertEqual(entry['output_end_ms'], 5000)
        self.assertEqual(len(entry['source_timecodes']), 2)
        self.assertEqual(entry['source_timecodes'][0]['start_ms'], 1000)
        self.assertEqual(entry['source_timecodes'][1]['start_ms'], 3200)


if __name__ == '__main__':
    unittest.main()
