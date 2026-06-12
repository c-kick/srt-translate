#!/usr/bin/env python3
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "scripts" / "orchestrate.sh"


class OrchestratorAgentBackendTest(unittest.TestCase):
    def test_help_documents_codex_agent_option(self):
        result = subprocess.run(
            ["bash", str(ORCHESTRATOR), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertIn("--agent AGENT", result.stdout)
        self.assertIn("--codex", result.stdout)
        self.assertIn("Default: claude", result.stdout)

    def test_orchestrator_defaults_to_claude_and_dispatches_codex_only_when_requested(self):
        source = ORCHESTRATOR.read_text()

        self.assertIn("AGENT=\"claude\"", source)
        self.assertIn("--agent)", source)
        self.assertIn("--codex)", source)
        self.assertIn("invoke_agent()", source)
        self.assertIn("invoke_claude \"$@\"", source)
        self.assertIn("invoke_codex \"$@\"", source)
        self.assertIn("codex exec", source)
        self.assertIn("--add-dir", source)
        self.assertIn("effective_model_label", source)
        self.assertIn("Codex model: $(effective_model_label", source)
        self.assertIn("Models: setup=$(effective_model_label", source)
        self.assertNotIn("--ask-for-approval", source)

    def test_help_documents_external_source_overrides(self):
        result = subprocess.run(
            ["bash", str(ORCHESTRATOR), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertIn("--source-srt PATH", result.stdout)
        self.assertIn("--source-language LANG", result.stdout)
        self.assertIn("--output-srt PATH", result.stdout)
        self.assertIn("--source-ready", result.stdout)

    def test_orchestrator_can_translate_from_non_english_ready_source(self):
        source = ORCHESTRATOR.read_text()

        self.assertIn("SOURCE_SRT_OVERRIDE", source)
        self.assertIn("OUTPUT_SRT_OVERRIDE", source)
        self.assertIn("SOURCE_LANGUAGE", source)
        self.assertIn("SOURCE_READY", source)
        self.assertIn("write_source_ready_checkpoint()", source)
        self.assertIn("Translate from ${SOURCE_LANGUAGE} to Dutch", source)


if __name__ == "__main__":
    unittest.main()
