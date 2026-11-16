"""Read-only Nexus Mods lookups through the public GraphQL v2 API (no key). Uploading stays manual.

Endpoint https://api.nexusmods.com/v2/graphql; queries `legacyModsByDomain` (by game domain + mod id) and
`mods` (name wildcard filter, sorted by endorsements). Game domain for Skyrim SE/AE: skyrimspecialedition.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .errors import ToolError, ValidationError
from .version import VERSION

API = "https://api.nexusmods.com/v2/graphql"
GAME = "skyrimspecialedition"


def _query(query: str, variables: dict[str, Any], *, opener: Any = None) -> dict[str, Any]:
    request = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": f"SkyrimForge/{VERSION}"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=60) as response:
            document = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ToolError(f"Nexus API unreachable: {exc}") from exc
    if document.get("errors"):
        raise ToolError("Nexus API error: " + "; ".join(item.get("message", "") for item in document["errors"]))
    return document["data"]


def mod(mod_id: int, *, game: str = GAME, description: bool = False, opener: Any = None) -> dict[str, Any]:
    if mod_id <= 0:
        raise ValidationError("mod id must be a positive integer")
    fields = "name modId version summary updatedAt endorsements author game { domainName }" + (" description" if description else "")
    data = _query("query($ids:[CompositeDomainWithIdInput!]!){ legacyModsByDomain(ids:$ids){ nodes{ %s } } }" % fields,
                  {"ids": [{"gameDomain": game, "modId": int(mod_id)}]}, opener=opener)
    nodes = data["legacyModsByDomain"]["nodes"]
    if not nodes:
        return {"result": "FAIL", "game": game, "mod_id": mod_id, "reason": "no such mod on this game domain"}
    node = dict(nodes[0])
    if description and node.get("description"):
        text = re.sub(r"<br\s*/?>", "\n", node.pop("description"))
        node["description_text"] = re.sub(r"\n\s*\n+", "\n", re.sub(r"\[/?[a-z*]+[^\]]*\]", "", text)).strip()[:6000]
    return {"result": "PASS", **node, "url": f"https://www.nexusmods.com/{game}/mods/{node['modId']}"}


def find(name: str, *, game: str = GAME, limit: int = 10, opener: Any = None) -> dict[str, Any]:
    if not name.strip():
        raise ValidationError("give part of a mod name")
    if not 1 <= limit <= 50:
        raise ValidationError("limit must be from 1 to 50")
    data = _query("query($f:ModsFilter,$c:Int){ mods(filter:$f, count:$c, sort:[{endorsements:{direction:DESC}}]){ "
                  "nodes{ name modId version summary endorsements author } } }",
                  {"f": {"gameDomainName": [{"value": game, "op": "EQUALS"}], "name": [{"value": name, "op": "WILDCARD"}]}, "c": limit},
                  opener=opener)
    rows = [{**node, "url": f"https://www.nexusmods.com/{game}/mods/{node['modId']}"} for node in data["mods"]["nodes"]]
    return {"result": "PASS", "game": game, "query": name, "count": len(rows), "mods": rows}
