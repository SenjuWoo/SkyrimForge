# Deterministic frame-time evidence ingestion and comparison.
# It compares like-for-like scenarios and reports frame-time percentiles; it
# never turns a single play session or an unmatched capture into an FPS claim.
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from .errors import ValidationError

SCHEMA = "skyrim-forge-benchmark/1"
MIN_SAMPLES = 120
SCENARIO_FIELDS = ("name", "game_version", "load_order", "resolution", "graphics_preset", "hardware")


def _frames(report: dict[str, Any]) -> list[float]:
    values = report.get("frames_ms")
    if not isinstance(values, list) or not values:
        raise ValidationError("frames_ms must be a non-empty list")
    frames: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValidationError("every frame time must be a positive finite number of milliseconds")
        frames.append(float(value))
    declared = report.get("sample_count")
    if declared is not None and declared != len(frames):
        raise ValidationError("sample_count does not match frames_ms")
    return frames


def _scenario(report: dict[str, Any]) -> dict[str, str]:
    scenario = report.get("scenario")
    if not isinstance(scenario, dict):
        raise ValidationError("scenario metadata is required")
    result: dict[str, str] = {}
    for field in SCENARIO_FIELDS:
        value = scenario.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"scenario.{field} is required for a comparable benchmark")
        result[field] = value.strip()
    return result


def metrics(frames: list[float]) -> dict[str, Any]:
    """Nearest-rank percentiles are defined here so comparisons are reproducible."""
    ordered = sorted(frames)
    count = len(ordered)

    def percentile(fraction: float) -> float:
        index = max(0, min(count - 1, math.ceil(fraction * count) - 1))
        return ordered[index]

    median = percentile(0.5)
    return {
        "sample_count": count,
        "mean_ms": round(sum(ordered) / count, 4),
        "median_ms": round(median, 4),
        "p95_ms": round(percentile(0.95), 4),
        "p99_ms": round(percentile(0.99), 4),
        "slow_frame_ratio": round(sum(1 for value in ordered if value > median * 2.0) / count, 6),
    }


def _delta(baseline: float, candidate: float) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else 100.0
    return round((candidate - baseline) / baseline * 100.0, 3)


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any], tolerance_percent: float = 2.0) -> dict[str, Any]:
    """Compare frame-time reports; reject mismatched scenarios and insufficient samples."""
    if not 0 <= tolerance_percent <= 100:
        raise ValidationError("tolerance_percent must be between 0 and 100")
    base_scenario = _scenario(baseline)
    cand_scenario = _scenario(candidate)
    mismatches = [field for field in SCENARIO_FIELDS if base_scenario[field] != cand_scenario[field]]
    if mismatches:
        return {"schema": SCHEMA, "result": "FAIL", "verdict": "INCOMPATIBLE",
                "mismatched_fields": mismatches, "baseline": base_scenario, "candidate": cand_scenario,
                "evidence": "Benchmark scenarios differ; no performance comparison is valid."}
    base_frames = _frames(baseline)
    cand_frames = _frames(candidate)
    base_metrics = metrics(base_frames)
    cand_metrics = metrics(cand_frames)
    deltas = {key: _delta(base_metrics[key], cand_metrics[key])
              for key in ("mean_ms", "median_ms", "p95_ms", "p99_ms", "slow_frame_ratio")}
    if min(len(base_frames), len(cand_frames)) < MIN_SAMPLES:
        verdict, result = "INSUFFICIENT", "PARTIAL"
    elif max(deltas["mean_ms"], deltas["p95_ms"], deltas["p99_ms"]) > tolerance_percent:
        verdict, result = "REGRESSION", "FAIL"
    elif min(deltas["p95_ms"], deltas["p99_ms"]) < -tolerance_percent:
        verdict, result = "IMPROVEMENT", "PASS"
    else:
        verdict, result = "NO_MEASURABLE_CHANGE", "PASS"
    warnings: list[str] = []
    if deltas["slow_frame_ratio"] > tolerance_percent:
        warnings.append("Slow-frame ratio increased beyond tolerance; inspect the raw capture.")
    return {
        "schema": SCHEMA, "result": result, "verdict": verdict,
        "scenario": base_scenario, "tolerance_percent": tolerance_percent,
        "baseline": base_metrics, "candidate": cand_metrics, "delta_percent": deltas,
        "warnings": warnings,
        "definitions": {"p95_ms": "nearest-rank 95th percentile frame time, lower is better",
                        "slow_frame_ratio": "fraction of frames slower than 2x the median"},
        "evidence": "Frame-time arithmetic from supplied captures. Comparable scene and hardware metadata are caller-asserted; no claim is made about visual quality or gameplay.",
    }


def presentmon_csv(path: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    """Read a PresentMon-style CSV with a millisecond frame-time column."""
    scenario = dict(scenario)
    scenario.setdefault("source", "PresentMon")
    for field in SCENARIO_FIELDS:
        if not isinstance(scenario.get(field), str) or not scenario[field].strip():
            raise ValidationError(f"scenario.{field} is required before importing a capture")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError("CSV has no header")
        names = {name.casefold(): name for name in reader.fieldnames}
        column = next((names[key] for key in ("msbetweenpresents", "msbetweendisplaychange", "msgpuactive")
                       if key in names), None)
        if column is None:
            raise ValidationError("CSV has no msBetweenPresents, msBetweenDisplayChange or MsGPUActive column")
        frames: list[float] = []
        for row in reader:
            try:
                value = float(row.get(column, ""))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and value > 0:
                frames.append(value)
    if not frames:
        raise ValidationError("CSV contains no positive frame times")
    return {"schema": SCHEMA, "scenario": scenario, "sample_count": len(frames), "frames_ms": frames}


def self_test() -> dict[str, Any]:
    """Prove comparison, regression detection, metadata rejection and insufficient evidence."""
    scenario = {"name": "Whiterun gate", "game_version": "1.6.1170", "load_order": "profile",
                "resolution": "2560x1440", "graphics_preset": "high", "hardware": "test GPU"}
    base = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [16.7 + (i % 5) * 0.1 for i in range(300)]}
    better = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [15.0 + (i % 5) * 0.1 for i in range(300)]}
    worse = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [19.0 + (i % 5) * 0.1 for i in range(300)]}
    other = {"schema": SCHEMA, "scenario": {**scenario, "resolution": "1920x1080"}, "frames_ms": better["frames_ms"]}
    tiny = {"schema": SCHEMA, "scenario": scenario, "frames_ms": base["frames_ms"][:20]}
    improvement = compare_reports(base, better)
    regression = compare_reports(base, worse)
    mismatch = compare_reports(base, other)
    insufficient = compare_reports(base, tiny)
    checks = {
        "improvement_detected": improvement["verdict"] == "IMPROVEMENT",
        "regression_detected": regression["verdict"] == "REGRESSION",
        "mismatched_scenario_rejected": mismatch["verdict"] == "INCOMPATIBLE",
        "small_sample_not_passed": insufficient["verdict"] == "INSUFFICIENT",
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
