#!/usr/bin/env python3
import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TitleCardWorkflowPrivacyTest(unittest.TestCase):
    def test_network_fetch_cli_accepts_imdb_id_not_local_media_paths(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "fetch_foreign_subtitle.py"),
                "--help",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertIn("IMDB_ID", result.stdout)
        self.assertNotIn("EN_SRT", result.stdout)
        self.assertNotIn("VIDEO_FILE", result.stdout)

    def test_local_detector_has_no_network_imports(self):
        source = (SCRIPTS / "detect_title_cards.py").read_text()
        tree = ast.parse(source)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module.split(".")[0])

        self.assertNotIn("urllib", imported_modules)
        self.assertNotIn("requests", imported_modules)
        self.assertNotIn("api.opensubtitles.com", source)

    def test_workflow_uses_split_fetch_and_detect_commands(self):
        workflow = (ROOT / "base" / "workflow-setup.md").read_text()
        orchestrator = (SCRIPTS / "orchestrate.sh").read_text()

        self.assertNotIn("fetch_title_cards.py", workflow)
        self.assertIn("fetch_foreign_subtitle.py", workflow)
        self.assertIn("detect_title_cards.py", workflow)
        self.assertIn("by IMDb ID only", orchestrator)
        self.assertIn("run_title_card_detection()", orchestrator)
        self.assertIn("merge_title_cards.py", orchestrator)

    def test_local_detector_finds_foreign_cue_without_nearby_english_start(self):
        sys.path.insert(0, str(SCRIPTS))
        from detect_title_cards import detect_title_cards

        en_srt = """1
00:00:01,000 --> 00:00:03,000
Existing dialogue

2
00:00:08,000 --> 00:00:09,000
More dialogue
"""
        foreign_srt = """1
00:00:01,100 --> 00:00:03,100
Dialogo existente

2
00:00:05,000 --> 00:00:06,200
Madrid, 1936
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            en_path = tmp_path / "source.en.srt"
            foreign_path = tmp_path / "foreign.srt"
            output_path = tmp_path / "title_cards.srt"
            en_path.write_text(en_srt, encoding="utf-8")
            foreign_path.write_text(foreign_srt, encoding="utf-8")

            count = detect_title_cards(en_path, foreign_path, output_path)

            self.assertEqual(count, 1)
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("Madrid, 1936", output)
            self.assertNotIn("Dialogo existente", output)

    def test_local_detector_recovers_global_timing_offset(self):
        sys.path.insert(0, str(SCRIPTS))
        from detect_title_cards import detect_title_cards

        en_srt = """1
00:00:11,000 --> 00:00:13,000
Existing dialogue

2
00:00:18,000 --> 00:00:19,000
More dialogue
"""
        foreign_srt = """1
00:00:01,100 --> 00:00:03,100
Dialogo existente

2
00:00:05,000 --> 00:00:06,200
Madrid, 1936

3
00:00:08,100 --> 00:00:09,100
Mas dialogo
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            en_path = tmp_path / "source.en.srt"
            foreign_path = tmp_path / "foreign.srt"
            output_path = tmp_path / "title_cards.srt"
            en_path.write_text(en_srt, encoding="utf-8")
            foreign_path.write_text(foreign_srt, encoding="utf-8")

            count = detect_title_cards(en_path, foreign_path, output_path)

            self.assertEqual(count, 1)
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("00:00:14,900 --> 00:00:16,100", output)
            self.assertIn("Madrid, 1936", output)

    def test_local_detector_suppresses_unreliable_foreign_timing(self):
        sys.path.insert(0, str(SCRIPTS))
        from detect_title_cards import detect_title_cards

        en_srt = """1
00:00:01,000 --> 00:00:02,000
One

2
00:00:04,000 --> 00:00:05,000
Two
"""
        foreign_srt = """1
00:10:01,000 --> 00:10:02,000
Uno

2
00:10:04,000 --> 00:10:05,000
Dos

3
00:10:08,000 --> 00:10:09,000
Tres
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            en_path = tmp_path / "source.en.srt"
            foreign_path = tmp_path / "foreign.srt"
            output_path = tmp_path / "title_cards.srt"
            en_path.write_text(en_srt, encoding="utf-8")
            foreign_path.write_text(foreign_srt, encoding="utf-8")

            count = detect_title_cards(en_path, foreign_path, output_path)

            self.assertEqual(count, 0)
            self.assertFalse(output_path.exists())

    def test_local_detector_uses_interval_overlap_after_alignment(self):
        sys.path.insert(0, str(SCRIPTS))
        from detect_title_cards import detect_title_cards

        en_srt = """1
00:00:33,363 --> 00:00:37,057
for a German,
is burdened by history.

2
00:00:41,000 --> 00:00:42,000
Next line
"""
        foreign_srt = """1
00:00:35,230 --> 00:00:39,037
para un alemán,
está abrumado por la historia.

2
00:00:41,000 --> 00:00:42,000
Siguiente línea

3
00:00:44,000 --> 00:00:45,000
Missing caption
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            en_path = tmp_path / "source.en.srt"
            foreign_path = tmp_path / "foreign.srt"
            output_path = tmp_path / "title_cards.srt"
            en_path.write_text(en_srt, encoding="utf-8")
            foreign_path.write_text(foreign_srt, encoding="utf-8")

            count = detect_title_cards(en_path, foreign_path, output_path)

            self.assertEqual(count, 1)
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("Missing caption", output)
            self.assertNotIn("para un alemán", output)

    def test_merge_helper_inserts_title_cards_in_time_order(self):
        helper = SCRIPTS / "merge_title_cards.py"
        en_srt = """1
00:00:01,000 --> 00:00:03,000
Existing dialogue

2
00:00:08,000 --> 00:00:09,000
More dialogue
"""
        title_cards = """1
00:00:05,000 --> 00:00:06,200
Madrid, 1936
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            en_path = tmp_path / "source.en.srt"
            tc_path = tmp_path / "title_cards.srt"
            en_path.write_text(en_srt, encoding="utf-8")
            tc_path.write_text(title_cards, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(helper), str(en_path), str(tc_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Merged 1 title card(s)", result.stdout)
            merged = en_path.read_text(encoding="utf-8")
            self.assertIn('[TITLE CARD: "Madrid, 1936"]', merged)
            self.assertLess(merged.index("Existing dialogue"), merged.index("[TITLE CARD"))
            self.assertLess(merged.index("[TITLE CARD"), merged.index("More dialogue"))

    def test_extract_title_cards_from_source_removes_marker_wrapper(self):
        helper = SCRIPTS / "extract_title_cards.py"
        source = """1
00:00:01,000 --> 00:00:03,000
Existing dialogue

2
00:00:05,000 --> 00:00:06,200
[TITLE CARD: "Madrid, 1936"]
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "source.en.srt"
            output_path = tmp_path / "title_cards.srt"
            source_path.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(helper), str(source_path), "--output", str(output_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Extracted 1 title card cue(s)", result.stdout)
            extracted = output_path.read_text(encoding="utf-8")
            self.assertIn("Madrid, 1936", extracted)
            self.assertNotIn("[TITLE CARD:", extracted)

    def test_filter_missing_subtitles_keeps_only_cues_not_covered_by_existing_translation(self):
        helper = SCRIPTS / "filter_missing_subtitles.py"
        candidates = """1
00:00:05,000 --> 00:00:06,200
Madrid, 1936

2
00:00:10,000 --> 00:00:12,000
Already translated
"""
        existing = """1
00:00:09,900 --> 00:00:12,100
Al vertaald
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            candidates_path = tmp_path / "candidates.srt"
            existing_path = tmp_path / "existing.nl.srt"
            output_path = tmp_path / "missing.srt"
            candidates_path.write_text(candidates, encoding="utf-8")
            existing_path.write_text(existing, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    str(candidates_path),
                    str(existing_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Wrote 1 missing cue(s)", result.stdout)
            missing = output_path.read_text(encoding="utf-8")
            self.assertIn("Madrid, 1936", missing)
            self.assertNotIn("Already translated", missing)

    def test_merge_missing_subtitles_updates_existing_translation_in_time_order(self):
        helper = SCRIPTS / "merge_missing_subtitles.py"
        existing = """1
00:00:01,000 --> 00:00:03,000
Bestaande dialoog

2
00:00:08,000 --> 00:00:09,000
Meer dialoog
"""
        missing = """1
00:00:05,000 --> 00:00:06,200
Madrid, 1936
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing_path = tmp_path / "existing.nl.srt"
            missing_path = tmp_path / "missing.nl.srt"
            existing_path.write_text(existing, encoding="utf-8")
            missing_path.write_text(missing, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(helper), str(existing_path), str(missing_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Merged 1 missing cue(s)", result.stdout)
            merged = existing_path.read_text(encoding="utf-8")
            self.assertIn("Madrid, 1936", merged)
            self.assertLess(merged.index("Bestaande dialoog"), merged.index("Madrid, 1936"))
            self.assertLess(merged.index("Madrid, 1936"), merged.index("Meer dialoog"))

    def test_merge_missing_subtitles_pushes_inserted_cue_after_previous_gap(self):
        helper = SCRIPTS / "merge_missing_subtitles.py"
        existing = """1
00:00:01,000 --> 00:00:03,000
Bestaande dialoog
"""
        missing = """1
00:00:02,900 --> 00:00:04,000
Ontbrekende ondertitel
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing_path = tmp_path / "existing.nl.srt"
            missing_path = tmp_path / "missing.nl.srt"
            existing_path.write_text(existing, encoding="utf-8")
            missing_path.write_text(missing, encoding="utf-8")

            subprocess.run(
                [sys.executable, str(helper), str(existing_path), str(missing_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            merged = existing_path.read_text(encoding="utf-8")
            self.assertIn("00:00:03,120 --> 00:00:04,000", merged)

    def test_align_augmented_cues_uses_reference_timings_in_separate_output(self):
        helper = SCRIPTS / "align_augmented_cues_to_reference.py"
        base = """1
00:00:01,000 --> 00:00:03,000
Bestaande dialoog

2
00:00:08,000 --> 00:00:09,000
Meer dialoog
"""
        reference = """1
00:00:05,500 --> 00:00:06,700
Madrid, 1936
"""
        translated = """1
00:00:05,000 --> 00:00:06,200
Madrid, 1936
"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "existing.nl.srt"
            reference_path = tmp_path / "missing.foreign.srt"
            translated_path = tmp_path / "missing.nl.srt"
            output_path = tmp_path / "existing.dut.srt"
            base_path.write_text(base, encoding="utf-8")
            reference_path.write_text(reference, encoding="utf-8")
            translated_path.write_text(translated, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    str(base_path),
                    str(reference_path),
                    str(translated_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Wrote 1 aligned cue(s)", result.stdout)
            self.assertEqual(base_path.read_text(encoding="utf-8"), base)
            aligned = output_path.read_text(encoding="utf-8")
            self.assertIn("00:00:05,500 --> 00:00:06,700", aligned)
            self.assertIn("Madrid, 1936", aligned)
            self.assertLess(aligned.index("Bestaande dialoog"), aligned.index("Madrid, 1936"))
            self.assertLess(aligned.index("Madrid, 1936"), aligned.index("Meer dialoog"))

    def test_orchestrator_documents_augment_missing_mode(self):
        orchestrator = (SCRIPTS / "orchestrate.sh").read_text()
        readme = (ROOT / "README.md").read_text()
        skill = (ROOT / "SKILL.md").read_text()

        self.assertIn("--augment-missing", orchestrator)
        self.assertIn("run_augment_missing()", orchestrator)
        self.assertIn("extract_title_cards.py", orchestrator)
        self.assertIn("filter_missing_subtitles.py", orchestrator)
        self.assertIn("merge_missing_subtitles.py", orchestrator)
        self.assertIn('run_title_card_detection "detect-only"', orchestrator)
        self.assertIn("--augment-missing", readme)
        self.assertIn("--augment-missing", skill)

    def test_orchestrator_cue_counter_handles_utf8_bom(self):
        orchestrator = (SCRIPTS / "orchestrate.sh").read_text()

        self.assertIn(r"\xEF\xBB\xBF", orchestrator)
        self.assertIn("strip UTF-8 BOM", orchestrator)


if __name__ == "__main__":
    unittest.main()
