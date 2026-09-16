from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("validate_contracts", ROOT / "07-scripts" / "validate_contracts.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ContractTests(unittest.TestCase):
    def test_valid_examples_pass_and_invalid_examples_are_rejected(self):
        report = MODULE.validate_examples(ROOT / "00-contracts", ROOT / "00-contracts" / "examples")
        self.assertEqual(len(report), 5)
        self.assertTrue(all(item["invalid_rejected"] for item in report.values()))


if __name__ == "__main__":
    unittest.main()
