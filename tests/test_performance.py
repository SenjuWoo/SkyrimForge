from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.performance import compare_reports, presentmon_csv, self_test

SCENARIO = {"name": "Whiterun gate", "game_version": "1.6.1170", "load_order": "profile",
            "resolution": "2560x1440", "graphics_preset": "high", "hardware": "test GPU"}


def report(frames, scenario=None):
    return {"schema": "skyrim-forge-benchmark/1", "scenario": scenario or SCENARIO, "frames_ms": frames}


class PerformanceTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_improvement_and_regression(self):
        base = report([16.7 + (i % 5) * 0.1 for i in range(300)])
        better = report([15.0 + (i % 5) * 0.1 for i in range(300)])
        worse = report([19.0 + (i % 5) * 0.1 for i in range(300)])
        self.assertEqual(compare_reports(base, better)["verdict"], "IMPROVEMENT")
        self.assertEqual(compare_reports(base, worse)["verdict"], "REGRESSION")

    def test_mismatched_scenario_is_rejected(self):
        base = report([16.0] * 200)
        other = report([15.0] * 200, {**SCENARIO, "resolution": "1920x1080"})
        result = compare_reports(base, other)
        self.assertEqual(result["verdict"], "INCOMPATIBLE")
        self.assertIn("resolution", result["mismatched_fields"])

    def test_small_sample_is_not_passed(self):
        base = report([16.0] * 200)
        tiny = report([15.0] * 20)
        self.assertEqual(compare_reports(base, tiny)["verdict"], "INSUFFICIENT")

    def test_csv_ingest_requires_scenario_and_reads_ms_column(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            lines = ["Application,MsBetweenPresents"] + [f"SkyrimSE.exe,{16.0 + i % 3}" for i in range(130)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            converted = presentmon_csv(path, SCENARIO)
            self.assertEqual(converted["sample_count"], 130)
            self.assertEqual(converted["scenario"]["source"], "PresentMon")

    def test_csv_without_frame_time_column_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            path.write_text("Application,Other\nSkyrimSE.exe,1\n", encoding="utf-8")
            with self.assertRaises(Exception):
                presentmon_csv(path, SCENARIO)

    def test_invalid_frame_values_fail(self):
        with self.assertRaises(Exception):
            compare_reports(report([16.0] * 130), report([0] * 130))


if __name__ == "__main__":
    unittest.main()
