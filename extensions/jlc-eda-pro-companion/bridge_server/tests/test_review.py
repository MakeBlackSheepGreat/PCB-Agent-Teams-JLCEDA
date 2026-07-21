from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "review.py"
SPEC = importlib.util.spec_from_file_location("companion_review", MODULE_PATH)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class PreflightTests(unittest.TestCase):
    def test_valid_payload_passes(self) -> None:
        payload = {
            "board": {"layers": [1, 2], "outlineLines": [{"startX": 0, "startY": 0, "endX": 10, "endY": 0}]},
            "components": [{"designator": "U1", "pads": [{"number": "1", "net": "VCC"}, {"number": "2", "net": "GND"}]}],
            "nets": ["VCC", "GND"],
            "existing_tracks": [{"net": "VCC"}],
            "existing_vias": [],
        }

        report = review.build_preflight(payload)

        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["summary"]["power_nets"], ["GND", "VCC"])

    def test_unknown_pad_net_fails(self) -> None:
        payload = {
            "board": {"layers": [1, 2], "outline": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}]},
            "components": [{"designator": "R1", "pads": [{"number": "1", "net": "MISSING"}]}],
            "nets": ["GND"],
        }

        report = review.build_preflight(payload)

        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any(item["code"] == "UNKNOWN_PAD_NET" for item in report["findings"]))

    def test_duplicate_designators_fail(self) -> None:
        payload = {
            "board": {"layers": [1, 2], "outlineLines": [{"startX": 0, "startY": 0, "endX": 1, "endY": 0}]},
            "components": [{"designator": "C1", "pads": []}, {"designator": "C1", "pads": []}],
            "nets": ["GND"],
        }

        report = review.build_preflight(payload)

        self.assertTrue(any(item["code"] == "DUPLICATE_DESIGNATOR" for item in report["findings"]))
