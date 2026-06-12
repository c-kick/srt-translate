#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SetupRequirementsTest(unittest.TestCase):
    def test_setup_checks_for_compiler_before_installing_webrtcvad(self):
        source = (ROOT / "scripts" / "setup.sh").read_text()

        self.assertIn("command -v x86_64-linux-gnu-gcc", source)
        self.assertIn("sudo apt-get install build-essential", source)
        self.assertIn("-r scripts/requirements.txt", source)


if __name__ == "__main__":
    unittest.main()
