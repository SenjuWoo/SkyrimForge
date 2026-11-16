"""Small data kinds: BodySlide slider presets and slider groups (XML) and INI files (game tweaks and SKSE plugin INIs).

Quirks the game or the plugin tolerates are warnings, not errors: keys before any [Section] (many SKSE plugins
read flat key=value files), values that do not match the Bethesda type prefix (bFoo, iFoo, fFoo, uFoo, sFoo).
Framework INIs (_DISTR, _KID, _SWAP, SkyPatcher, FLM) belong to `lint`, which owns their grammars.
"""
from __future__ import annotations

import configparser
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .errors import ValidationError

FRAMEWORK_SUFFIXES = ("_distr.ini", "_kid.ini", "_swap.ini", "_flm.ini")
PREFIX_RX = {"b": re.compile(r"^[01]$|^(true|false)$", re.I), "i": re.compile(r"^-?\d+$"), "u": re.compile(r"^\d+$"),
             "f": re.compile(r"^-?\d+(\.\d*)?([eE][-+]?\d+)?$|^-?\.\d+$")}


def _issue(severity: str, code: str, message: str, line: int = 0) -> dict[str, Any]:
    return {"severity": severity, "code": code, "line": line, "message": message}


def _report(path: Path, kind: str, issues: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    errors = sum(item["severity"] == "error" for item in issues)
    return {"result": "FAIL" if errors else "PASS", "file": str(path), "kind": kind, "errors": errors,
            "warnings": sum(item["severity"] == "warning" for item in issues), "issues": issues, **extra}


def _xml(path: Path) -> ET.Element:
    try:
        return ET.fromstring(Path(path).read_bytes().lstrip(b"\xef\xbb\xbf"))
    except ET.ParseError as exc:
        raise ValidationError(f"{Path(path).name}: XML does not parse: {exc}") from exc


def bodyslide_preset(path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    try:
        root = _xml(path)
    except ValidationError as exc:
        return _report(path, "bodyslide-preset", [_issue("error", "BS-XML", str(exc))])
    if root.tag != "SliderPresets":
        issues.append(_issue("error", "BS-ROOT", f"root <{root.tag}> must be <SliderPresets>"))
    presets = root.findall("Preset")
    if not presets:
        issues.append(_issue("error", "BS-EMPTY", "no <Preset name=... set=...>"))
    for preset in presets:
        label = preset.get("name") or "?"
        if not preset.get("name"):
            issues.append(_issue("error", "BS-NAME", "a <Preset> has no name"))
        if not preset.get("set"):
            issues.append(_issue("warning", "BS-SET", f"preset {label!r} names no slider set"))
        for slider in preset.findall("SetSlider"):
            if not slider.get("name"):
                issues.append(_issue("error", "BS-SLIDER", f"preset {label!r}: a SetSlider has no name"))
            if slider.get("size") not in ("big", "small"):
                issues.append(_issue("error", "BS-SIZE", f"slider {slider.get('name')!r}: size must be big or small"))
            try:
                value = float(slider.get("value", ""))
                if not -100 <= value <= 200:
                    issues.append(_issue("warning", "BS-VALUE", f"slider {slider.get('name')!r}: value {value} is unusual"))
            except ValueError:
                issues.append(_issue("error", "BS-VALUE", f"slider {slider.get('name')!r}: value is not a number"))
    return _report(path, "bodyslide-preset", issues, presets=len(presets))


def slider_groups(path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    try:
        root = _xml(path)
    except ValidationError as exc:
        return _report(path, "slider-group", [_issue("error", "SG-XML", str(exc))])
    if root.tag != "SliderGroups":
        issues.append(_issue("error", "SG-ROOT", f"root <{root.tag}> must be <SliderGroups>"))
    groups = root.findall("Group")
    for group in groups:
        if not group.get("name"):
            issues.append(_issue("error", "SG-NAME", "a <Group> has no name"))
        if not group.findall("Member"):
            issues.append(_issue("warning", "SG-EMPTY", f"group {group.get('name')!r} has no members"))
    return _report(path, "slider-group", issues, groups=len(groups))


def ini(path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    text = Path(path).read_bytes().decode("utf-8-sig", errors="replace")
    parser = configparser.RawConfigParser(strict=False, interpolation=None, comment_prefixes=(";", "#"), inline_comment_prefixes=(";",))
    parser.optionxform = str  # type: ignore[assignment]
    first = next((n for n, line in enumerate(text.splitlines(), 1) if line.strip() and not line.strip().startswith((";", "#"))), 0)
    if first and not text.splitlines()[first - 1].strip().startswith("["):
        issues.append(_issue("warning", "INI-NO-SECTION", "keys before any [Section]: fine for SKSE plugins that read flat files, "
                             "ignored by the game's own INI loader", first))
        text = "[__top__]\n" + text
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        return _report(path, "ini", [_issue("error", "INI-SYNTAX", str(exc).splitlines()[0])] + issues)
    keys = 0
    for section in parser.sections():
        for key, value in parser.items(section):
            keys += 1
            rule = PREFIX_RX.get(key[:1]) if len(key) > 1 and key[1:2].isupper() else None
            if rule and not rule.match(value.strip()):
                issues.append(_issue("warning", "INI-TYPE", f"[{section}] {key}={value}: value does not match its {key[0]!r} prefix"))
    return _report(path, "ini", issues, sections=len([s for s in parser.sections() if s != "__top__"]), keys=keys)


def validate(path: Path) -> dict[str, Any]:
    low = Path(path).as_posix().casefold()
    if low.endswith(".xml") and "sliderpresets" in low:
        return bodyslide_preset(path)
    if low.endswith(".xml") and "slidergroups" in low:
        return slider_groups(path)
    if low.endswith(".ini"):
        if low.endswith(FRAMEWORK_SUFFIXES) or "/skypatcher/" in low:
            raise ValidationError(f"{Path(path).name} is a framework config: use `forge lint`, which owns that grammar")
        return ini(path)
    raise ValidationError(f"no data-kind validator for {Path(path).name}: BodySlide SliderPresets/SliderGroups .xml or .ini")


def validate_paths(paths: list[Path]) -> dict[str, Any]:
    reports = [validate(path) for path in paths]
    return {"result": "FAIL" if any(r["result"] == "FAIL" for r in reports) else "PASS", "files": len(reports),
            "errors": sum(r["errors"] for r in reports), "warnings": sum(r["warnings"] for r in reports), "reports": reports}
