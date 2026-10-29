#!/usr/bin/env python3
"""Offline structural validator for MCM Helper menus (config.json, keybinds.json, settings.ini, translations).

Rules come from MCM-Helper docs/config.schema.json + keybinds.schema.json (a303348, v1.6.3) and the parser
source (strict RapidJSON). Structural validity is not runtime proof: open the menu in game.

    python validate_mcm.py <mod-root | MCM | MCM/Config | MCM/Config/<Mod> | config.json> [--strict]
Exit 0 = no errors (and no warnings with --strict), 1 = findings, 2 = nothing to validate.
"""
from __future__ import annotations

import argparse
import configparser
import json
import re
import sys
from pathlib import Path

TYPES = {"empty", "header", "text", "toggle", "hiddenToggle", "slider", "stepper", "menu", "enum", "color", "keymap", "input"}
SOURCE_TYPES = {"PropertyValueBool", "PropertyValueInt", "PropertyValueFloat", "ModSettingBool", "ModSettingInt", "ModSettingFloat", "GlobalValue"}
FORM_RE = re.compile(r'^[^\\/:*?"<>|]+\.es[lmp]\|(0[Xx])?[\dA-Fa-f]{1,8}$')
SETTING_RE = re.compile(r"^[A-Za-z][^:]*:.+$")
VALUE = {"sourceType", "sourceForm", "defaultValue", "scriptName", "propertyName"}
TEXT = {"sourceForm", "scriptName", "propertyName", "defaultValue", "sourceType"}
VALUE_KEYS = {
    "toggle": VALUE, "hiddenToggle": VALUE, "color": VALUE, "keymap": VALUE,
    "stepper": VALUE | {"options"}, "enum": VALUE | {"options", "shortNames"},
    "slider": VALUE | {"min", "max", "step", "formatString"},
    "text": TEXT | {"value"}, "menu": TEXT | {"options", "shortNames"}, "input": TEXT,
}
CONTROL_KEYS = {"type", "id", "text", "help", "position", "groupCondition", "groupBehavior", "groupControl", "action", "valueOptions", "ignoreConflicts"}
ALLOWED_SOURCES = {"toggle": {"Bool", "Int"}, "hiddenToggle": {"Bool", "Int"}, "slider": {"Float", "Int"},
                   "stepper": {"Int"}, "enum": {"Int"}, "color": {"Int"}, "keymap": {"Int"}}
PREFIX = {"Bool": "b", "Int": "iur", "Float": "f"}
LANGUAGES = ("CZECH", "ENGLISH", "FRENCH", "GERMAN", "ITALIAN", "POLISH", "RUSSIAN", "SPANISH", "JAPANESE")
OPS = {"OR", "AND", "ONLY", "NOT"}


class Report:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, level: str, file: Path | str, message: str) -> None:
        self.items.append((level, str(file), message))

    def count(self, level: str) -> int:
        return sum(1 for item in self.items if item[0] == level)


def load_json(path: Path, rep: Report):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        rep.add("ERROR", path, "UTF-8 BOM: MCM Helper's parser does not skip it; save as UTF-8 without BOM")
        raw = raw[3:]
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        rep.add("ERROR", path, f"not strict JSON (comments and trailing commas are rejected by the game): {error}")
        return None


def check_form(value, where: str, path: Path, rep: Report) -> None:
    if not isinstance(value, str) or not FORM_RE.match(value):
        rep.add("ERROR", path, f"{where}: form must be 'Plugin.esp|HEXID' (local id), got {value!r}")


def check_condition(cond, path: Path, where: str, rep: Report, refs: set[int]) -> None:
    if isinstance(cond, bool):
        rep.add("ERROR", path, f"{where}: groupCondition must be int >= 1, array, or one-key object")
    elif isinstance(cond, int):
        if cond < 1:
            rep.add("ERROR", path, f"{where}: group ids start at 1")
        refs.add(cond)
    elif isinstance(cond, list):
        for item in cond:
            check_condition(item, path, where, rep, refs)
    elif isinstance(cond, dict):
        if not cond or set(cond) - OPS:
            rep.add("ERROR", path, f"{where}: groupCondition object keys must be from {sorted(OPS)}")
        elif len(cond) > 1:  # shipped mods do this; the parser keeps one conjunction per object (last key wins)
            rep.add("WARNING", path, f"{where}: several operators in one groupCondition object; the schema allows one, nest objects instead")
        for value in cond.values():
            check_condition(value, path, where, rep, refs)
    else:
        rep.add("ERROR", path, f"{where}: groupCondition must be int >= 1, array, or one-key object")


def check_action(action, path: Path, where: str, rep: Report) -> None:
    if not isinstance(action, dict):
        rep.add("ERROR", path, f"{where}: action must be an object")
        return
    kind = action.get("type")
    if kind not in ("CallFunction", "CallGlobalFunction"):
        rep.add("ERROR", path, f"{where}: action.type must be CallFunction or CallGlobalFunction")
    if not action.get("function"):
        rep.add("ERROR", path, f"{where}: action.function is required")
    allowed = {"type", "function", "params"} | ({"form", "scriptName"} if kind == "CallFunction" else {"script"})
    for key in sorted(set(action) - allowed):
        rep.add("ERROR", path, f"{where}: action has unknown/misplaced key {key!r}")
    if kind == "CallGlobalFunction" and not action.get("script"):
        rep.add("WARNING", path, f"{where}: CallGlobalFunction without 'script'")
    if "form" in action:
        check_form(action["form"], f"{where}.action.form", path, rep)
    params = action.get("params", [])
    if not isinstance(params, list) or any(not isinstance(p, (bool, int, float, str)) for p in params):
        rep.add("ERROR", path, f"{where}: action.params must be an array of boolean/number/string")


def check_control(ctl, where: str, path: Path, rep: Report, ctx: dict) -> None:
    if not isinstance(ctl, dict):
        rep.add("ERROR", path, f"{where}: control must be an object")
        return
    kind = ctl.get("type")
    if kind not in TYPES:
        rep.add("ERROR", path, f"{where}: type must be one of {sorted(TYPES)}, got {kind!r}")
        return
    for key in sorted(set(ctl) - CONTROL_KEYS):
        rep.add("ERROR", path, f"{where}: unknown control key {key!r}")
    if "ignoreConflicts" in ctl and kind != "keymap":
        rep.add("ERROR", path, f"{where}: ignoreConflicts only applies to keymap")
    if "groupControl" in ctl and kind not in ("toggle", "hiddenToggle"):  # ContentHandler.cpp registers only these two
        rep.add("WARNING", path, f"{where}: groupControl on {kind} is ignored at runtime (only toggle/hiddenToggle drive groups)")
    for key in ("text", "help"):
        text = ctl.get(key)
        if isinstance(text, str):
            ctx["strings"].append(text)
            if key == "text" and text and not text.startswith("$"):
                ctx["unloc"].append(text)
    cid = ctl.get("id")
    if cid is not None:
        # a hiddenToggle legitimately mirrors a visible control's id to drive a group
        if cid in ctx["ids"] and "hiddenToggle" not in (kind, ctx["ids"][cid]):
            rep.add("WARNING", path, f"{where}: id {cid!r} is used by two visible controls")
        ctx["ids"].setdefault(cid, kind)
    if "groupControl" in ctl and kind in ("toggle", "hiddenToggle"):
        group = ctl["groupControl"]
        if isinstance(group, int) and not isinstance(group, bool) and group >= 1:
            ctx["scope_controls"].add(group)
        else:
            rep.add("ERROR", path, f"{where}: groupControl must be int >= 1")
    if "groupCondition" in ctl:
        check_condition(ctl["groupCondition"], path, where, rep, ctx["scope_refs"])
    if ctl.get("groupBehavior", "disable") not in ("disable", "hide", "skip"):
        rep.add("ERROR", path, f"{where}: groupBehavior must be disable|hide|skip")
    if "action" in ctl:
        check_action(ctl["action"], path, where, rep)
    if "position" in ctl and (not isinstance(ctl["position"], int) or isinstance(ctl["position"], bool)):
        rep.add("ERROR", path, f"{where}: position must be an integer")
    opts = ctl.get("valueOptions")
    if opts is None:
        if kind in ("slider", "stepper", "enum", "menu"):
            rep.add("ERROR", path, f"{where}: {kind} needs valueOptions")
        return
    if kind in ("empty", "header") or not isinstance(opts, dict):
        rep.add("ERROR", path, f"{where}: valueOptions not allowed here / must be an object")
        return
    for key in sorted(set(opts) - VALUE_KEYS[kind]):
        rep.add("ERROR", path, f"{where}: valueOptions key {key!r} not valid for {kind}")
    source = opts.get("sourceType")
    if "sourceForm" in opts:
        check_form(opts["sourceForm"], f"{where}.valueOptions.sourceForm", path, rep)
    if kind in ALLOWED_SOURCES:
        if source is not None and source not in SOURCE_TYPES:
            rep.add("ERROR", path, f"{where}: unknown sourceType {source!r}")
        elif source and source != "GlobalValue":
            family = re.sub(r"^(PropertyValue|ModSetting)", "", source)
            if family not in ALLOWED_SOURCES[kind]:
                rep.add("WARNING", path, f"{where}: {kind} stores {sorted(ALLOWED_SOURCES[kind])}, sourceType is {source}")
            if source.startswith("ModSetting"):
                if not cid:
                    rep.add("ERROR", path, f"{where}: ModSetting source needs an id like 'key:Section'")
                else:
                    ctx["mod_settings"].append((where, cid, family))
            elif not opts.get("propertyName"):
                rep.add("ERROR", path, f"{where}: PropertyValue source needs valueOptions.propertyName")
        elif source == "GlobalValue" and "sourceForm" not in opts:
            rep.add("ERROR", path, f"{where}: GlobalValue source needs sourceForm")
        if source is None and ("propertyName" in opts or "scriptName" in opts):
            rep.add("ERROR", path, f"{where}: propertyName/scriptName need a PropertyValue* sourceType (schema)")
    elif source is not None:
        ctx["unused_source"].append(where)
    if kind == "slider":
        lo, hi, step = (opts.get(k) for k in ("min", "max", "step"))
        if None in (lo, hi, step):
            rep.add("WARNING", path, f"{where}: slider should set min, max and step")
        elif all(isinstance(v, (int, float)) for v in (lo, hi, step)):
            if lo >= hi or step <= 0:
                rep.add("ERROR", path, f"{where}: slider needs min < max and step > 0")
    if kind in ("stepper", "enum", "menu"):
        options = opts.get("options")
        if options is None and kind != "stepper":
            rep.add("INFO", path, f"{where}: {kind} has no options; a script must call SetMenuOptions before it is shown")
        elif not isinstance(options, list) or not options or any(not isinstance(o, str) for o in options):
            rep.add("ERROR", path, f"{where}: {kind} needs a non-empty string array 'options'")
        else:
            ctx["strings"].extend(options)
            if kind == "menu" and len(options) > 128:
                rep.add("ERROR", path, f"{where}: menu holds at most 128 options")
            short = opts.get("shortNames")
            if short is not None:
                if not isinstance(short, list) or len(short) != len(options):
                    rep.add("ERROR", path, f"{where}: shortNames must match options length")
                else:
                    ctx["strings"].extend(s for s in short if isinstance(s, str))
    if kind == "keymap" and cid and not ({"sourceType", "propertyName"} & set(opts)):
        ctx["hotkeys"].add(cid)  # no value source = a keybinds.json hotkey


def check_content(content, where: str, path: Path, rep: Report, ctx: dict) -> None:
    if not isinstance(content, list):
        rep.add("ERROR", path, f"{where}: content must be an array")
        return
    ctx["scope_controls"], ctx["scope_refs"] = set(), set()
    for index, ctl in enumerate(content):
        check_control(ctl, f"{where}[{index}]", path, rep, ctx)
        if isinstance(ctl, dict) and ctl.get("type") == "keymap" and ctl.get("id") and "valueOptions" not in ctl:
            ctx["hotkeys"].add(ctl["id"])
    for missing in sorted(ctx["scope_refs"] - ctx["scope_controls"]):
        rep.add("INFO", path, f"{where}: groupCondition uses group {missing} but no toggle/hiddenToggle on this page defines it (page-scoped in the parser; verify in game)")


def check_page_body(node: dict, where: str, path: Path, rep: Report, ctx: dict) -> None:
    has_content, has_custom = "content" in node, "customContent" in node
    custom_used = has_custom and bool(node["customContent"])  # shipped mods pair "content": [] with a splash
    if has_content and custom_used and node["content"]:
        rep.add("WARNING", path, f"{where}: content and customContent are documented as mutually exclusive")
    elif not (has_content or has_custom) and where != "$":  # a pages-only menu has an empty main page; many shipped mods rely on it
        rep.add("WARNING", path, f"{where}: page has neither content nor customContent")
    if has_content:
        check_content(node["content"], f"{where}.content", path, rep, ctx)
    if custom_used:
        custom = node["customContent"]
        if not isinstance(custom, dict) or not custom.get("source"):
            rep.add("ERROR", path, f"{where}: customContent.source is required")
        else:
            for axis, limit in (("x", 770), ("y", 446)):
                if axis in custom and not isinstance(custom[axis], (int, float)):
                    rep.add("ERROR", path, f"{where}: customContent.{axis} must be a number")
                elif axis in custom and not 0 <= custom[axis] < limit:
                    rep.add("WARNING", path, f"{where}: customContent.{axis} is outside the {limit}px config area (schema maximum)")


def check_config(path: Path, rep: Report) -> dict | None:
    data = load_json(path, rep)
    if not isinstance(data, dict):
        return None
    ctx = {"strings": [], "ids": {}, "mod_settings": [], "hotkeys": set(), "scope_controls": set(), "scope_refs": set(), "unloc": [], "unused_source": []}
    for key in ("modName", "displayName"):
        if not isinstance(data.get(key), str) or not data[key]:
            rep.add("ERROR", path, f"{key} is required")
    mod = data.get("modName", "")
    if isinstance(mod, str) and mod.lower() != path.parent.name.lower():
        rep.add("ERROR", path, f"modName {mod!r} must equal the folder name {path.parent.name!r}")
    if re.search(r"\.es[lmp]$", str(mod), re.I):
        rep.add("ERROR", path, "modName must not include the plugin extension")
    if isinstance(data.get("displayName"), str):
        ctx["strings"].append(data["displayName"])
    if "minMcmVersion" in data and (not isinstance(data["minMcmVersion"], int) or isinstance(data["minMcmVersion"], bool)):
        rep.add("ERROR", path, "minMcmVersion must be an integer version code")
    elif "minMcmVersion" in data and data["minMcmVersion"] < 9:
        rep.add("WARNING", path, "minMcmVersion below 9 has no effect (support began at code 9; the schema's own minimum is 13)")
    if data.get("cursorFillMode", "leftToRight") not in ("leftToRight", "topToBottom"):
        rep.add("ERROR", path, "cursorFillMode must be leftToRight|topToBottom")
    reqs = data.get("pluginRequirements", [])
    if not isinstance(reqs, list) or any(not isinstance(r, str) for r in reqs):
        rep.add("ERROR", path, "pluginRequirements must be an array of plugin file names")
    if "$schema" not in data:
        rep.add("INFO", path, "no $schema (optional; helps editors validate)")
    check_page_body(data, "$", path, rep, ctx)
    pages = data.get("pages", [])
    if not isinstance(pages, list):
        rep.add("ERROR", path, "pages must be an array")
        pages = []
    for index, page in enumerate(pages):
        where = f"pages[{index}]"
        if not isinstance(page, dict) or not page.get("pageDisplayName"):
            rep.add("ERROR", path, f"{where}: pageDisplayName is required")
            continue
        ctx["strings"].append(page["pageDisplayName"])
        if not page["pageDisplayName"].startswith("$"):
            ctx["unloc"].append(page["pageDisplayName"])
        extra = set(page) - {"pageDisplayName", "content", "customContent", "cursorFillMode"}
        for key in sorted(extra):
            rep.add("ERROR", path, f"{where}: unknown page key {key!r}")
        if "cursorFillMode" in page:
            rep.add("INFO", path, f"{where}: per-page cursorFillMode is used by the shipped SkyUI_SE config but absent from the schema")
        check_page_body(page, where, path, rep, ctx)
    ctx["mod"] = mod
    return ctx


def check_settings(path: Path, ctx: dict, rep: Report) -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True, comment_prefixes=(";", "#"))
    parser.optionxform = str
    try:
        parser.read_string(path.read_text(encoding="utf-8-sig"))
    except (configparser.Error, UnicodeDecodeError) as error:
        rep.add("ERROR", path, f"settings.ini unreadable: {error}")
        return
    known: set[str] = set()
    for section in parser.sections():
        for key, value in parser.items(section):
            known.add(f"{key}:{section}")
            letter, text = key[:1], (value or "").strip()
            if letter not in "bfirsu":
                rep.add("WARNING", path, f"[{section}] {key}: first letter must be a type prefix b f i r s u")
                continue
            bad = (letter == "b" and text.lower() not in ("0", "1", "true", "false")) or \
                  (letter in "iu" and not re.fullmatch(r"-?\d+", text)) or \
                  (letter == "f" and not re.fullmatch(r"-?\d*\.?\d+(e[-+]?\d+)?", text, re.I)) or \
                  (letter == "r" and not re.fullmatch(r"\d+(\s*,\s*\d+){2}|\d+", text))
            if bad:
                rep.add("WARNING", path, f"[{section}] {key}={text!r} does not look like a '{letter}' value")
    for where, cid, family in ctx["mod_settings"]:
        if not SETTING_RE.match(cid):
            rep.add("ERROR", path, f"{where}: ModSetting id {cid!r} must be 'key:Section' (no colon = never saved)")
        elif cid not in known:
            rep.add("WARNING", path, f"{where}: ModSetting {cid!r} has no default in settings.ini")
        elif cid[:1] not in PREFIX.get(family, ""):
            rep.add("WARNING", path, f"{where}: id prefix {cid[:1]!r} does not match a {family} setting")


def check_keybinds(path: Path, ctx: dict, rep: Report) -> None:
    data = load_json(path, rep)
    if not isinstance(data, dict):
        return
    for key in sorted(set(data) - {"$schema", "modName", "keybinds"}):
        rep.add("ERROR", path, f"unknown top-level key {key!r}")
    if not data.get("modName"):
        rep.add("ERROR", path, "modName is required")
    elif str(data["modName"]).lower() != path.parent.name.lower():
        rep.add("ERROR", path, "modName must equal the folder name")
    binds = data.get("keybinds")
    if not isinstance(binds, list):
        rep.add("ERROR", path, "keybinds array is required")
        return
    seen: set[str] = set()
    for index, bind in enumerate(binds):
        where = f"keybinds[{index}]"
        if not isinstance(bind, dict) or not bind.get("id") or not isinstance(bind.get("action"), dict):
            rep.add("ERROR", path, f"{where}: id and action are required")
            continue
        for key in sorted(set(bind) - {"id", "desc", "action"}):
            rep.add("ERROR", path, f"{where}: unknown key {key!r}")
        if bind["id"] in seen:
            rep.add("ERROR", path, f"{where}: duplicate id {bind['id']!r}")
        seen.add(bind["id"])
        if isinstance(bind.get("desc"), str):
            ctx["strings"].append(bind["desc"])
            if not bind["desc"].startswith("$"):
                ctx["unloc"].append(bind["desc"])
        action, kind = bind["action"], bind["action"].get("type")
        need = {"CallFunction": ("form", "function"), "SendEvent": ("form",), "CallGlobalFunction": ("script", "function"), "RunConsoleCommand": ("command",)}
        if kind not in need:
            rep.add("ERROR", path, f"{where}: action.type must be one of {sorted(need)}")
            continue
        for key in need[kind]:
            if not action.get(key):
                rep.add("ERROR", path, f"{where}: {kind} requires {key!r}")
        if "form" in action:
            check_form(action["form"], f"{where}.action.form", path, rep)
    for hot in sorted(ctx["hotkeys"] - seen):
        rep.add("ERROR", path, f"keymap control id {hot!r} has no entry in keybinds.json")
    for orphan in sorted(seen - ctx["hotkeys"]):
        rep.add("WARNING", path, f"keybind {orphan!r} has no keymap control, so the user cannot choose a key")


def read_translation(path: Path, rep: Report) -> set[str]:
    raw = path.read_bytes()
    if not raw.startswith(b"\xff\xfe"):
        rep.add("ERROR", path, "translation must be UTF-16 LE with BOM")
        return set()
    keys = set()
    for line in raw.decode("utf-16").splitlines():
        if line.startswith("$"):
            key = line.split("\t", 1)[0]
            if "\t" not in line:
                rep.add("INFO", path, f"{key!r}: no TAB between key and value")
            keys.add(key)
    return keys


def check_translations(root: Path, mod: str, ctx: dict, rep: Report) -> None:
    used = {s for s in ctx["strings"] if s.startswith("$") and "{" not in s}  # '{}' templates are matched by SkyUI, not whole-string
    folder = root / "Interface" / "Translations"
    files = {lang: folder / f"{mod}_{lang}.txt" for lang in LANGUAGES if (folder / f"{mod}_{lang}.txt").is_file()}
    if not files:
        if used:
            rep.add("WARNING", folder, f"{len(used)} $Key strings used but no {mod}_<LANGUAGE>.txt shipped (ok only if another mod defines them)")
        return
    for lang, file in files.items():
        keys = read_translation(file, rep)
        for string in sorted(used):
            if string not in keys:
                rep.add("WARNING", file, f"no key {string!r} here (fine only if the game or another mod defines it; whole string must equal a key)")
    if "ENGLISH" in files and len(files) < len(LANGUAGES):
        rep.add("INFO", folder, f"languages without a file show raw $Keys (no ENGLISH fallback); shipped: {sorted(files)}")


def locate(arg: Path) -> list[Path]:
    if arg.is_file():
        return [arg.parent] if arg.name == "config.json" else []
    if (arg / "config.json").is_file():
        return [arg]
    for candidate in (arg / "MCM" / "Config", arg / "Config", arg):
        if candidate.is_dir() and any((child / "config.json").is_file() for child in candidate.iterdir() if child.is_dir()):
            return sorted(child for child in candidate.iterdir() if (child / "config.json").is_file())
    return []


def validate(arg: Path) -> Report:
    rep = Report()
    folders = locate(arg)
    if not folders:
        rep.add("ERROR", arg, "no MCM config folder (config.json) found")
        return rep
    for folder in folders:
        ctx = check_config(folder / "config.json", rep)
        if ctx is None:
            continue
        if (folder / "settings.ini").is_file():
            check_settings(folder / "settings.ini", ctx, rep)
        elif ctx["mod_settings"]:
            rep.add("WARNING", folder, "controls use ModSettings but settings.ini is missing")
        if (folder / "keybinds.json").is_file():
            check_keybinds(folder / "keybinds.json", ctx, rep)
        elif ctx["hotkeys"]:
            rep.add("ERROR", folder, f"keymap hotkeys {sorted(ctx['hotkeys'])} need keybinds.json")
        if ctx["unloc"]:
            rep.add("INFO", folder, f"{len(ctx['unloc'])} label(s) are plain text, not $Keys, so they cannot be translated, e.g. {ctx['unloc'][:2]}")
        if ctx["unused_source"]:
            rep.add("INFO", folder, f"sourceType on {len(ctx['unused_source'])} string control(s) is ignored (deprecated for text/menu/input)")
        root =folder.parent.parent.parent if folder.parent.name.lower() == "config" and folder.parent.parent.name.lower() == "mcm" else None
        if root is not None:
            check_translations(root, ctx["mod"], ctx, rep)
            plugins = [p for p in root.iterdir() if p.suffix.lower() in (".esp", ".esl", ".esm")]
            if plugins and not any(p.stem.lower() == str(ctx["mod"]).lower() for p in plugins):
                rep.add("INFO", root, f"no plugin named {ctx['mod']}.esp/.esl/.esm at this root (modName must be the plugin that owns the quest)")
        else:
            rep.add("INFO", folder, "not inside MCM/Config under a mod root: translations and plugin name not checked")
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path)
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    args = ap.parse_args(argv)
    if not locate(args.path):
        print(f"ERROR   {args.path}: no MCM config folder (config.json) found")
        return 2
    rep = validate(args.path)
    for level, file, message in rep.items:
        print(f"{level:7} {file}: {message}")
    errors, warnings = rep.count("ERROR"), rep.count("WARNING")
    print(f"RESULT: {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
