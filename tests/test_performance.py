from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.performance import compare_reports, presentmon_csv, self_test

SCENARIO = {"name": "Whiterun gate", "game_version": "1.6.1170", "load_order": "profile",
            "resolution": "2560x1440", "graphics_preset": "high", "hardware": "test GPU",
            "metric": "msBetweenPresents"}


def report(frames, scenario=None):
    return {"schema": "skyrim-forge-benchmark/1", "scenario": scenario or SCENARIO, "frames_ms": frames}


class PerformanceTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_improvement_and_regression(self):
        base = report([16.7 + (i % 5) * 0.1 for i in range(300)])
        better = report([15.0 + (i % 5) * 0.1 for i in range(300)])
        worse = report([19.0 + (i % 5) * 0.1 for i in range(300)])
        improved = compare_reports(base, better)
        self.assertEqual(improved["verdict"], "IMPROVEMENT")
        self.assertEqual(improved["result"], "PARTIAL")
        self.assertEqual(improved["verification"], "FRAME_TIME_COMPARISON_ONLY")
        self.assertFalse(improved["runtime_verified"])
        self.assertEqual(compare_reports(base, worse)["verdict"], "REGRESSION")

    def test_mismatched_scenario_is_rejected(self):
        base = report([16.0] * 200)
        other = report([15.0] * 200, {**SCENARIO, "resolution": "1920x1080"})
        result = compare_reports(base, other)
        self.assertEqual(result["verdict"], "INCOMPATIBLE")
        self.assertIn("resolution", result["mismatched_fields"])

    def test_mixed_metrics_are_rejected(self):
        base = report([16.0] * 200)
        other = report([5.0] * 200, {**SCENARIO, "metric": "MsGPUActive"})
        result = compare_reports(base, other)
        self.assertEqual(result["verdict"], "INCOMPATIBLE")
        self.assertEqual(result["mismatched_fields"], ["metric"])
        self.assertNotIn("IMPROVEMENT", str(result))

    def test_missing_metric_is_rejected(self):
        scenario = {key: value for key, value in SCENARIO.items() if key != "metric"}
        result = compare_reports(report([16.0] * 200, scenario), report([15.0] * 200, scenario))
        self.assertEqual(result["verdict"], "INCOMPATIBLE")
        self.assertEqual(result["mismatched_fields"], ["metric"])

    def test_unknown_metric_is_invalid(self):
        scenario = {**SCENARIO, "metric": "pixelsPerSecond"}
        result = compare_reports(report([16.0] * 200, scenario), report([15.0] * 200, scenario))
        self.assertEqual(result["verdict"], "INVALID_METRIC")

    def test_small_sample_is_not_passed(self):
        base = report([16.0] * 200)
        tiny = report([15.0] * 20)
        self.assertEqual(compare_reports(base, tiny)["verdict"], "INSUFFICIENT")

    def test_csv_ingest_requires_explicit_metric_and_single_process(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            lines = ["Application,ProcessId,MsBetweenPresents,MsGPUActive"] + [
                f"SkyrimSE.exe,42,{16.0 + i % 3},5.0" for i in range(130)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            converted = presentmon_csv(path, SCENARIO, metric="msBetweenPresents", process="SkyrimSE.exe")
            self.assertEqual(converted["sample_count"], 130)
            self.assertEqual(converted["scenario"]["metric"], "msBetweenPresents")
            self.assertEqual(converted["scenario"]["process"], "SkyrimSE.exe")
            self.assertEqual(converted["scenario"]["process_id"], "42")
            self.assertEqual(converted["frames_ms"][0], 16.0)

    def test_csv_without_explicit_metric_fails_when_ambiguous(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            path.write_text("Application,MsBetweenPresents,MsGPUActive\nSkyrimSE.exe,16,5\n", encoding="utf-8")
            scenario = {key: value for key, value in SCENARIO.items() if key != "metric"}
            with self.assertRaises(Exception):
                presentmon_csv(path, scenario)

    def test_csv_mixed_processes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            lines = ["Application,MsBetweenPresents"] + [
                "SkyrimSE.exe,16.0", "Explorer.exe,4.0"]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(Exception):
                presentmon_csv(path, SCENARIO)

    def test_csv_without_frame_time_column_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.csv"
            path.write_text("Application,Other\nSkyrimSE.exe,1\n", encoding="utf-8")
            with self.assertRaises(Exception):
                presentmon_csv(path, SCENARIO, metric="msBetweenPresents")

    def test_invalid_frame_values_fail(self):
        with self.assertRaises(Exception):
            compare_reports(report([16.0] * 130), report([0] * 130))


if __name__ == "__main__":
    unittest.main()
