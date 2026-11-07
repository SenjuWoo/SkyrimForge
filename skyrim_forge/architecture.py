# Rule-based mod architecture recommendation.
# It ranks known Skyrim implementation routes from the user's description and
# declared constraints, then states what still needs verification. It never
# claims a framework/tool is installed or that the recommendation will work.
from __future__ import annotations

from typing import Any

from .errors import ValidationError

SCHEMA = "skyrim-forge-architecture-recommendation/1"
REQUEST_SCHEMA = "skyrim-forge-architecture-request/1"

# Each candidate is an implementation route, not a dependency claim. Terms are
# matched as case-insensitive substrings; weights express how strongly a term
# points at that route. Keep this catalog small and evidence-based.
_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "id": "distribution.spid",
        "label": "SPID distribution",
        "workflow": "framework-config",
        "terms": {"spid": 8, "distribute": 5, "distribution": 5, "spell": 3, "perk": 3,
                  "item": 3, "npc": 2, "outfit": 3, "potion": 2},
        "frameworks": ["SPID"],
        "complexity": "low",
        "runtime_cost": "low",
        "save_risk": "low",
        "why": "SPID applies form distributions at load time without a plugin or script.",
        "checks": ["framework lint with the pinned SPID profile", "framework runtime log correlation", "load-order review"],
    },
    {
        "id": "distribution.kid",
        "label": "KID keyword distribution",
        "workflow": "framework-config",
        "terms": {"kid": 8, "keyword": 5, "distribute": 3, "distribution": 3, "item": 2,
                  "armor": 2, "weapon": 2, "form": 1},
        "frameworks": ["KID"],
        "complexity": "low",
        "runtime_cost": "low",
        "save_risk": "low",
        "why": "KID is the narrow route when the request is keyword-driven form distribution.",
        "checks": ["framework lint with the pinned KID profile", "framework runtime log correlation", "load-order review"],
    },
    {
        "id": "distribution.skypatcher",
        "label": "SkyPatcher config",
        "workflow": "framework-config",
        "terms": {"skypatcher": 8, "distribute": 3, "condition": 2, "patch": 2, "record": 2,
                  "form": 1},
        "frameworks": ["SkyPatcher"],
        "complexity": "low",
        "runtime_cost": "low",
        "save_risk": "low",
        "why": "SkyPatcher fits declarative record changes when its pinned grammar covers the property.",
        "checks": ["framework lint with the pinned SkyPatcher profile", "unsupported-property review", "runtime log correlation"],
    },
    {
        "id": "records.housecarl",
        "label": "houseCARL record patch",
        "workflow": "record-patch",
        "terms": {"patch": 4, "record": 4, "conflict": 4, "leveled": 3, "npc": 3, "outfit": 3,
                  "recipe": 3, "crafting": 2, "merge": 3, "load order": 2, "plugin": 2,
                  "esl": 2, "master": 2, "housecarl": 8},
        "frameworks": ["houseCARL"],
        "complexity": "medium",
        "runtime_cost": "none",
        "save_risk": "medium",
        "why": "Typed record editing is safer than byte surgery and preserves the existing load-order contract.",
        "checks": ["houseCARL parity check", "masters and FormID range validation", "record round-trip comparison", "load-order conflict scan"],
    },
    {
        "id": "records.synthesis",
        "label": "Mutagen/Synthesis patcher",
        "workflow": "record-patch",
        "terms": {"synthesis": 8, "mutagen": 8, "patcher": 6, "programmatic": 4,
                  "load order patch": 4, "repeatable": 2},
        "frameworks": ["Mutagen", "Synthesis"],
        "complexity": "medium",
        "runtime_cost": "none",
        "save_risk": "medium",
        "why": "A typed patcher is appropriate when the change must be regenerated from the current load order.",
        "checks": ["pinned Synthesis CLI and patcher source", "output record comparison", "master/index remap validation", "reproducible rerun"],
    },
    {
        "id": "script.papyrus",
        "label": "Papyrus gameplay script",
        "workflow": "papyrus",
        "terms": {"script": 5, "papyrus": 6, "quest": 5, "dialogue": 4, "magic effect": 4,
                  "ability": 3, "gameplay": 3, "event": 3, "alias": 3, "property": 2},
        "frameworks": ["Papyrus"],
        "complexity": "medium",
        "runtime_cost": "medium",
        "save_risk": "medium",
        "why": "Papyrus is the minimum route for quest/gameplay behaviour unless engine access is genuinely required.",
        "checks": ["source analysis for lifecycle/performance warnings", "compile with the verified compiler", "in-game event and save test"],
    },
    {
        "id": "native.skse",
        "label": "CommonLibSSE-NG plugin",
        "workflow": "native",
        "terms": {"skse": 8, "dll": 6, "native": 6, "hook": 7, "engine": 4,
                  "address library": 6, "commonlib": 7, "c++": 6, "per-frame": 3, "frame": 2},
        "frameworks": ["SKSE", "CommonLibSSE-NG", "Address Library"],
        "complexity": "high",
        "runtime_cost": "low",
        "save_risk": "high",
        "why": "A native plugin is justified only when the requirement is engine-level and no data/script route reaches it.",
        "checks": ["source-pinned scaffold", "MSVC/vcpkg build", "PE and import audit", "real SKSE load and coexistence test"],
    },
    {
        "id": "ui.mcm",
        "label": "MCM Helper menu",
        "workflow": "framework-config",
        "terms": {"mcm": 8, "menu": 5, "skyui": 6, "config": 4, "setting": 3, "ui": 4,
                  "widget": 2},
        "frameworks": ["SkyUI", "MCM Helper"],
        "complexity": "medium",
        "runtime_cost": "low",
        "save_risk": "low",
        "why": "MCM Helper is the current menu route; a menu alone does not justify a native plugin.",
        "checks": ["pinned MCM Helper interface", "menu open/close and save/reload test", "no duplicate legacy SKI config"],
    },
    {
        "id": "animation.oar",
        "label": "Open Animation Replacer",
        "workflow": "animation",
        "terms": {"animation": 6, "anim": 4, "behavior": 4, "oar": 8, "nemesis": 3,
                  "pandora": 4, "hkx": 3},
        "frameworks": ["Open Animation Replacer"],
        "complexity": "medium",
        "runtime_cost": "low",
        "save_risk": "low",
        "why": "OAR usually replaces animation selection without a new DLL; behavior generation is separate and version-specific.",
        "checks": ["OAR condition/config validation", "animation event coverage", "in-game visual and behavior test"],
    },
    {
        "id": "assets.texture",
        "label": "Texture replacement",
        "workflow": "asset",
        "terms": {"texture": 7, "dds": 6, "retexture": 7, "normal map": 5, "vram": 4,
                  "diffuse": 4, "alpha": 2, "resolution": 2},
        "frameworks": [],
        "complexity": "low",
        "runtime_cost": "low",
        "save_risk": "none",
        "why": "A texture replacement needs correct format, mipmaps and color space, not a plugin or script.",
        "checks": ["DDS header and mip-chain inspection", "normal/alpha semantics", "texture path and VRAM review", "in-game visual test"],
    },
    {
        "id": "assets.mesh",
        "label": "Mesh replacement",
        "workflow": "asset",
        "terms": {"mesh": 7, "nif": 7, "collision": 5, "model": 4, "geometry": 4,
                  "skinning": 4, "bone": 2},
        "frameworks": [],
        "complexity": "medium",
        "runtime_cost": "low",
        "save_risk": "none",
        "why": "Mesh work requires preserving geometry, partitions, collision and skinning; file size alone is not a metric.",
        "checks": ["NIF structural inspection", "texture path and collision review", "skinning/partition comparison", "in-game visual test"],
    },
    {
        "id": "lod.world",
        "label": "LOD generation",
        "workflow": "lod",
        "terms": {"lod": 8, "distant": 5, "dyndolod": 7, "xlodgen": 7, "texgen": 6,
                  "occlusion": 4},
        "frameworks": ["xLODGen", "TexGen", "DynDOLOD"],
        "complexity": "high",
        "runtime_cost": "low",
        "save_risk": "none",
        "why": "LOD is load-order and worldspace specific; generated output needs visual and performance review.",
        "checks": ["pinned LOD worker contract", "output inventory", "repeatable generation", "in-game distant-view test"],
    },
    {
        "id": "audio.voice",
        "label": "Voice/audio asset",
        "workflow": "asset",
        "terms": {"voice": 6, "dialogue audio": 7, "fuz": 7, "lip": 6, "xwm": 6,
                  "sound": 3, "audio": 5},
        "frameworks": [],
        "complexity": "medium",
        "runtime_cost": "low",
        "save_risk": "none",
        "why": "Audio work is a container/asset route; dialogue timing still needs runtime review.",
        "checks": ["FUZ/XWM/LIP container inspection", "voice-path validation", "in-game dialogue timing test"],
    },
    {
        "id": "packaging.fomod",
        "label": "FOMOD package",
        "workflow": "package",
        "terms": {"fomod": 8, "installer": 5, "package": 4, "option": 3, "archive": 2,
                  "bsa": 3, "ba2": 3},
        "frameworks": ["FOMOD"],
        "complexity": "low",
        "runtime_cost": "none",
        "save_risk": "none",
        "why": "Declarative FOMOD packaging is separate from the mod's runtime architecture.",
        "checks": ["FOMOD XML validation", "branch install simulation", "archive and path checks", "MO2/Vortex layout review"],
    },
)

_COMPLEXITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    if len(value) > limit:
        raise ValidationError(f"{name} exceeds {limit} characters")
    return value.strip()


def _optional_bool(data: dict[str, Any], name: str) -> bool | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValidationError(f"{name} must be a boolean")
    return value


def recommend(request: dict[str, Any]) -> dict[str, Any]:
    """Rank candidate routes; return unknowns instead of guessing when evidence is thin."""
    if not isinstance(request, dict):
        raise ValidationError("Architecture request must be a JSON object")
    schema = request.get("schema")
    if schema is not None and schema != REQUEST_SCHEMA:
        raise ValidationError(f"Unsupported architecture request schema: {schema}")
    description = _text(request.get("description"), "description", 4000)
    edition = str(request.get("edition", "unknown")).casefold()
    if edition not in {"se", "ae", "vr", "unknown"}:
        raise ValidationError("edition must be se, ae, vr or unknown")
    frequency = str(request.get("runtime_frequency", "unknown")).casefold()
    if frequency not in {"event", "occasional", "frame", "unknown"}:
        raise ValidationError("runtime_frequency must be event, occasional, frame or unknown")
    modifies = _optional_bool(request, "modifies_existing")
    performance = _optional_bool(request, "performance_sensitive") or False
    save_sensitive = _optional_bool(request, "save_sensitive") or False
    lower = " ".join(description.casefold().split())

    scored: list[dict[str, Any]] = []
    for item in _CANDIDATES:
        hits = [term for term in item["terms"] if term in lower]
        if not hits:
            continue
        score = sum(item["terms"][term] for term in hits)
        if frequency == "frame":
            score += 4 if item["id"] == "native.skse" else -2 if item["id"] == "script.papyrus" else 0
        if save_sensitive:
            score += 2 if item["id"].startswith("distribution.") else -1 if item["id"] in {"native.skse", "script.papyrus"} else 0
        if performance:
            score += 2 if item["id"] in {"native.skse", "assets.texture", "assets.mesh"} else 0
        if modifies:
            score += 1 if item["id"] in {"records.housecarl", "records.synthesis", "script.papyrus"} else 0
        scored.append({"id": item["id"], "label": item["label"], "score": score, "hits": hits,
                       "frameworks": item["frameworks"], "complexity": item["complexity"],
                       "runtime_cost": item["runtime_cost"], "save_risk": item["save_risk"],
                       "why": item["why"], "checks": item["checks"], "workflow": item["workflow"]})
    scored.sort(key=lambda row: (-row["score"], _COMPLEXITY_ORDER[row["complexity"]], row["id"]))
    questions: list[str] = []
    if edition == "unknown":
        questions.append("Confirm the target edition and executable version (SE, AE, VR or GOG); compatibility cannot be assumed.")
    if frequency == "unknown" and any(item["id"] in {"native.skse", "script.papyrus"} for item in scored[:2]):
        questions.append("Confirm how often the behaviour runs (event-driven, occasional polling, or per-frame).")
    if modifies is None:
        questions.append("Confirm whether this creates a new mod or changes an existing one, because save compatibility differs.")
    if not scored:
        return {
            "schema": SCHEMA, "result": "PASS", "status": "NEEDS_INPUT",
            "description": description, "recommendation": None, "alternatives": [],
            "confidence": "low", "questions": questions + [
                "Name the concrete behaviour and the game system it touches; no architecture can be recommended from this description yet."],
            "evidence": "Keyword/constraint routing only. No framework, API or runtime compatibility was verified.",
        }
    top = scored[0]
    margin = top["score"] - (scored[1]["score"] if len(scored) > 1 else 0)
    confidence = "high" if top["score"] >= 8 and margin >= 4 else "medium" if top["score"] >= 5 and margin >= 2 else "low"
    if confidence == "low":
        questions.append("The request matches several routes weakly; confirm the concrete behaviour before committing to an implementation.")
    recommendation = {key: top[key] for key in ("id", "label", "workflow", "frameworks", "complexity",
                                                "runtime_cost", "save_risk", "why", "checks")}
    recommendation["steps"] = [
        "Verify the target edition/runtime and installed dependencies before creating files.",
        "Use Forge's framework lint, record or native validation for the selected route.",
        "Run only the checks relevant to this mod type; do not claim runtime proof from static evidence.",
    ]
    return {
        "schema": SCHEMA, "result": "PASS", "status": "RECOMMENDED",
        "description": description, "recommendation": recommendation,
        "alternatives": scored[1:4], "confidence": confidence, "questions": questions,
        "constraints": {"edition": edition, "runtime_frequency": frequency,
                        "modifies_existing": modifies, "performance_sensitive": performance,
                        "save_sensitive": save_sensitive},
        "evidence": "Keyword/constraint routing only. Framework availability, API signatures and runtime behaviour remain unverified.",
    }


def self_test() -> dict[str, Any]:
    """Prove the selector is deterministic and does not turn ambiguity into confidence."""
    cases = [
        ({"description": "Distribute spells and perks to NPCs with SPID"}, "distribution.spid"),
        ({"description": "Replace armor textures with new DDS files and normal maps"}, "assets.texture"),
        ({"description": "Write an SKSE DLL that hooks engine code with Address Library"}, "native.skse"),
        ({"description": "Patch NPC records, outfits and leveled lists for compatibility"}, "records.housecarl"),
        ({"description": "Add an MCM menu with SkyUI settings for my mod"}, "ui.mcm"),
    ]
    checks = {}
    for request, expected in cases:
        report = recommend(request)
        actual = (report.get("recommendation") or {}).get("id")
        checks[expected] = actual == expected
    vague = recommend({"description": "Make my mod better"})
    checks["ambiguous_low_confidence"] = vague["confidence"] == "low" and vague["recommendation"] is None
    checks["deterministic"] = recommend({"description": "SPID spell distribution"}) == recommend({"description": "SPID spell distribution"})
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
