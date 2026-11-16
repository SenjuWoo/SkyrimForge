"""Tiered facts, verified Nexus page IDs and goal routes (references/SKYRIM-FACTS.json).

Tiers: installed (read from the installed game or tool), primary (upstream source or official API), secondary
(community documentation), unverified. Only installed and primary facts may be enforced by code (`require`).
`plan` ranks goal routes by keyword and returns the commands to run, each checked against the real parser.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .strictjson import load

TIERS = ("installed", "primary", "secondary", "unverified")
ENFORCEABLE = {"installed", "primary"}
FIELDS = ("id", "claim", "tier", "source", "checked", "recheck")


def path() -> Path:
    return Path(__file__).resolve().parent / "references" / "SKYRIM-FACTS.json"


def load_facts(source: Path | None = None) -> dict[str, Any]:
    document = load(source or path())
    problems = validate(document)
    if problems:
        raise ValidationError("SKYRIM-FACTS.json is invalid: " + "; ".join(problems[:5]))
    return document


def validate(document: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(document, dict) or not isinstance(document.get("facts"), list):
        return ["root needs a facts list"]
    seen: set[str] = set()
    for index, fact in enumerate(document["facts"]):
        label = fact.get("id", f"#{index}") if isinstance(fact, dict) else f"#{index}"
        if not isinstance(fact, dict):
            problems.append(f"{label}: not an object"); continue
        for key in FIELDS:
            if not isinstance(fact.get(key), str) or not fact[key].strip():
                problems.append(f"{label}: missing {key}")
        if fact.get("tier") not in TIERS:
            problems.append(f"{label}: unknown tier {fact.get('tier')!r}")
        if fact.get("tier") == "primary" and "http" not in str(fact.get("source", "")):
            problems.append(f"{label}: a primary fact names its URL")
        if not str(fact.get("recheck", "")).startswith("forge "):
            problems.append(f"{label}: recheck must be a forge command")
        if label in seen:
            problems.append(f"{label}: duplicate id")
        seen.add(label)
    for page in document.get("pages", []):
        if not isinstance(page.get("nexus"), int) or page["nexus"] <= 0:
            problems.append(f"page {page.get('id')}: nexus id must be a positive integer")
    return problems


def require(fact_id: str) -> dict[str, Any]:
    """Return a fact only if it may be enforced; an unverified or secondary fact never gates behaviour."""
    for fact in load_facts()["facts"]:
        if fact["id"] == fact_id:
            if fact["tier"] not in ENFORCEABLE:
                raise ValidationError(f"fact {fact_id} is {fact['tier']}; it can inform, not enforce")
            return fact
    raise ValidationError(f"unknown fact {fact_id}")


def facts(query: str | None = None) -> dict[str, Any]:
    document = load_facts()
    rows, pages = document["facts"], document.get("pages", [])
    if query:
        needle = query.casefold()
        rows = [row for row in rows if needle in (row["id"] + " " + row["claim"]).casefold()]
        pages = [page for page in pages if needle in (page["id"] + " " + page["name"]).casefold()]
    return {"result": "PASS", "policy": document["policy"], "count": len(rows), "facts": rows,
            "pages": [{**page, "url": f"https://www.nexusmods.com/{page.get('game', 'skyrimspecialedition')}/mods/{page['nexus']}"} for page in pages]}


def plan(goal: str, available: set[str]) -> dict[str, Any]:
    if not goal.strip():
        raise ValidationError("describe the goal")
    text = goal.casefold()
    scored = []
    for route in load_facts()["routes"]:
        hits = [word for word in route["keywords"] if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text)]
        if hits:
            scored.append((len(hits), route, hits))
    scored.sort(key=lambda item: -item[0])
    routes = [{"goal": route["goal"], "matched": hits, "commands": [{"command": f"forge {name}", "available": name in available} for name in route["commands"]]}
              for _, route, hits in scored[:3]]
    return {"result": "PASS" if routes else "INCOMPLETE", "goal": goal, "routes": routes,
            "hint": None if routes else "no route matched; run forge capabilities for the full command list"}
