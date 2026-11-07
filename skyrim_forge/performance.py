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
# These are different measurements. Treating GPU active time as a presented-frame
# interval can invent a large "improvement" that the game never produced.
METRICS = {
    "msbetweenpresents": "msBetweenPresents",
    "msbetweendisplaychange": "msBetweenDisplayChange",
    "msgpuactive": "MsGPUActive",
}
METRIC_HELP = ", ".join(METRICS.values())


def _metric_name(report: dict[str, Any]) -> str | None:
    scenario = report.get("scenario")
    raw = scenario.get("metric") if isinstance(scenario, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    return METRICS.get(raw.strip().casefold(), "__INVALID__")


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
    """Compare frame-time reports; reject mismatched metrics, scenarios and small samples."""
    if not 0 <= tolerance_percent <= 100:
        raise ValidationError("tolerance_percent must be between 0 and 100")
    base_scenario = _scenario(baseline)
    cand_scenario = _scenario(candidate)
    base_metric = _metric_name(baseline)
    cand_metric = _metric_name(candidate)
    mismatches = [field for field in SCENARIO_FIELDS if base_scenario[field] != cand_scenario[field]]
    if base_metric is None or cand_metric is None:
        mismatches.append("metric")
        return {"schema": SCHEMA, "result": "FAIL", "verdict": "INCOMPATIBLE",
                "mismatched_fields": mismatches, "baseline": base_scenario, "candidate": cand_scenario,
                "metric": None, "verification": "MISSING_METRIC",
                "evidence": f"Both reports must declare one measurement metric: {METRIC_HELP}."}
    if base_metric not in METRICS.values() or cand_metric not in METRICS.values():
        return {"schema": SCHEMA, "result": "FAIL", "verdict": "INVALID_METRIC",
                "mismatched_fields": ["metric"], "baseline": base_scenario, "candidate": cand_scenario,
                "metric": {"baseline": base_metric, "candidate": cand_metric},
                "verification": "INVALID_METRIC",
                "evidence": f"Unknown measurement metric; supported metrics are {METRIC_HELP}."}
    if base_metric != cand_metric:
        return {"schema": SCHEMA, "result": "FAIL", "verdict": "INCOMPATIBLE",
                "mismatched_fields": ["metric"], "baseline": base_scenario, "candidate": cand_scenario,
                "metric": {"baseline": base_metric, "candidate": cand_metric},
                "verification": "METRIC_MISMATCH",
                "evidence": f"Cannot compare {base_metric} with {cand_metric}; use the same measurement for both captures."}
    for field in ("process", "process_id"):
        base_value = baseline.get("scenario", {}).get(field)
        cand_value = candidate.get("scenario", {}).get(field)
        if (base_value or cand_value) and base_value != cand_value:
            mismatches.append(field)
    if mismatches:
        return {"schema": SCHEMA, "result": "FAIL", "verdict": "INCOMPATIBLE",
                "mismatched_fields": mismatches, "baseline": base_scenario, "candidate": cand_scenario,
                "metric": base_metric, "verification": "SCENARIO_MISMATCH",
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
        verdict, result = "IMPROVEMENT", "PARTIAL"
    else:
        verdict, result = "NO_MEASURABLE_CHANGE", "PARTIAL"
    warnings: list[str] = []
    if deltas["slow_frame_ratio"] > tolerance_percent:
        warnings.append("Slow-frame ratio increased beyond tolerance; inspect the raw capture.")
    return {
        "schema": SCHEMA, "result": result, "verdict": verdict,
        "scenario": {**base_scenario, "metric": base_metric}, "tolerance_percent": tolerance_percent,
        "metric": base_metric, "verification": "FRAME_TIME_COMPARISON_ONLY", "runtime_verified": False,
        "baseline": base_metrics, "candidate": cand_metrics, "delta_percent": deltas,
        "warnings": warnings,
        "definitions": {"p95_ms": "nearest-rank 95th percentile frame time, lower is better",
                        "slow_frame_ratio": "fraction of frames slower than 2x the median"},
        "evidence": "Frame-time arithmetic from supplied captures. The comparison is mathematical; it does not prove an in-game performance win, visual quality or gameplay correctness.",
    }


def _metric_column(names: dict[str, str], metric: str) -> str:
    key = metric.casefold()
    if key not in names:
        raise ValidationError(f"CSV has no {metric} column; supported metrics are {METRIC_HELP}")
    return names[key]


def presentmon_csv(path: Path, scenario: dict[str, Any], *, metric: str | None = None,
                   process: str | None = None) -> dict[str, Any]:
    """Read a PresentMon-style CSV; require an explicit metric and one process."""
    scenario = dict(scenario)
    requested = metric if metric is not None else scenario.get("metric")
    if not isinstance(requested, str) or not requested.strip():
        raise ValidationError(f"metric is required before importing a capture; choose {METRIC_HELP}")
    canonical = METRICS.get(requested.strip().casefold())
    if canonical is None:
        raise ValidationError(f"Unsupported capture metric {requested!r}; choose {METRIC_HELP}")
    scenario["metric"] = canonical
    scenario.setdefault("source", "PresentMon")
    for field in SCENARIO_FIELDS:
        if not isinstance(scenario.get(field), str) or not scenario[field].strip():
            raise ValidationError(f"scenario.{field} is required before importing a capture")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError("CSV has no header")
        names = {name.casefold(): name for name in reader.fieldnames}
        column = _metric_column(names, canonical)
        app_column = next((names[key] for key in ("application", "processname", "process") if key in names), None)
        pid_column = next((names[key] for key in ("processid", "process_id", "pid") if key in names), None)
        rows = list(reader)
    if process and app_column is None and pid_column is None:
        raise ValidationError("CSV has no process identity column; cannot filter the requested process")
    selected_app: str | None = None
    selected_pid: str | None = None
    if process:
        wanted = str(process).strip()
        if wanted.isdigit() and pid_column is not None:
            selected_pid = wanted
        elif app_column is not None:
            selected_app = wanted
        else:
            raise ValidationError("CSV has no usable process column for the requested filter")
    else:
        apps = {row.get(app_column, "").strip() for row in rows if app_column and row.get(app_column, "").strip()}
        pids = {row.get(pid_column, "").strip() for row in rows if pid_column and row.get(pid_column, "").strip()}
        if len(apps) > 1:
            raise ValidationError(f"mixed-process capture; choose one process: {', '.join(sorted(apps))}")
        if len(pids) > 1:
            raise ValidationError(f"multiple process IDs in capture; choose one process: {', '.join(sorted(pids))}")
        selected_app = next(iter(apps), None)
        selected_pid = next(iter(pids), None)
    if selected_app and pid_column and not selected_pid:
        matching_pids = {row.get(pid_column, "").strip() for row in rows
                         if row.get(app_column, "").strip().casefold() == selected_app.casefold()
                         and row.get(pid_column, "").strip()}
        if len(matching_pids) == 1:
            selected_pid = matching_pids.pop()
    frames: list[float] = []
    for row in rows:
        app = row.get(app_column, "").strip() if app_column else ""
        pid = row.get(pid_column, "").strip() if pid_column else ""
        if selected_app and app.casefold() != selected_app.casefold():
            continue
        if selected_pid and pid != selected_pid:
            continue
        try:
            value = float(row.get(column, ""))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            frames.append(value)
    if not frames:
        raise ValidationError("CSV contains no positive frame times for the selected metric and process")
    if selected_app is None and process and not str(process).isdigit() and app_column:
        selected_app = str(process).strip()
    if selected_app:
        scenario["process"] = selected_app
    if selected_pid:
        scenario["process_id"] = selected_pid
    return {"schema": SCHEMA, "scenario": scenario, "sample_count": len(frames), "frames_ms": frames}


def self_test() -> dict[str, Any]:
    """Prove metric matching, regression detection, metadata rejection and insufficient evidence."""
    scenario = {"name": "Whiterun gate", "game_version": "1.6.1170", "load_order": "profile",
                "resolution": "2560x1440", "graphics_preset": "high", "hardware": "test GPU",
                "metric": "msBetweenPresents"}
    base = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [16.7 + (i % 5) * 0.1 for i in range(300)]}
    better = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [15.0 + (i % 5) * 0.1 for i in range(300)]}
    worse = {"schema": SCHEMA, "scenario": scenario, "frames_ms": [19.0 + (i % 5) * 0.1 for i in range(300)]}
    other = {"schema": SCHEMA, "scenario": {**scenario, "resolution": "1920x1080"}, "frames_ms": better["frames_ms"]}
    gpu = {"schema": SCHEMA, "scenario": {**scenario, "metric": "MsGPUActive"}, "frames_ms": [5.0] * 300}
    tiny = {"schema": SCHEMA, "scenario": scenario, "frames_ms": base["frames_ms"][:20]}
    improvement = compare_reports(base, better)
    regression = compare_reports(base, worse)
    mismatch = compare_reports(base, other)
    mixed_metric = compare_reports(base, gpu)
    insufficient = compare_reports(base, tiny)
    checks = {
        "improvement_detected": improvement["verdict"] == "IMPROVEMENT" and improvement["result"] == "PARTIAL",
        "regression_detected": regression["verdict"] == "REGRESSION",
        "mismatched_scenario_rejected": mismatch["verdict"] == "INCOMPATIBLE",
        "mixed_metric_rejected": mixed_metric["verdict"] == "INCOMPATIBLE",
        "small_sample_not_passed": insufficient["verdict"] == "INSUFFICIENT",
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
