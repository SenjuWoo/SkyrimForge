from __future__ import annotations

from typing import Any

from .capabilities import registry as capability_registry
from .architecture import self_test as architecture_self_test
from .knowledge import self_test as knowledge_self_test
from .performance import self_test as performance_self_test
from .quality import self_test as quality_self_test
from .audio import self_test as audio_self_test
from .fomod import self_test as fomod_self_test
from .framework_builder import self_test as framework_builder_self_test
from .frameworks import self_test as framework_lint_self_test
from .native import self_test as native_self_test
from .nexus import self_test as nexus_self_test
from .papyrus import self_test as papyrus_self_test
from .skse_pe import self_test as skse_pe_self_test
from .telemetry import self_test as telemetry_self_test
from .textures import self_test as texture_self_test
from .maintenance import self_test as maintenance_self_test
from .vfs_sandbox import self_test as vfs_sandbox_self_test
from .version import VERSION
from .toolchain import load_catalog


def run_all() -> dict[str, Any]:
    catalog = load_catalog()
    checks = {
        "framework_lint": framework_lint_self_test(),
        "framework_builder": framework_builder_self_test(),
        "fomod": fomod_self_test(),
        "papyrus": papyrus_self_test(),
        "native": native_self_test(),
        "skse_pe": skse_pe_self_test(),
        "audio": audio_self_test(),
        "textures": texture_self_test(),
        "maintenance": maintenance_self_test(),
        "telemetry": telemetry_self_test(),
        "vfs_sandbox": vfs_sandbox_self_test(),
        "nexus": nexus_self_test(),
        "capabilities": capability_registry(),
        "architecture": architecture_self_test(),
        "knowledge": knowledge_self_test(),
        "quality": quality_self_test(),
        "performance": performance_self_test(),
        "toolchain": {"result": "PASS" if any(item["id"] == "bsarch" for item in catalog["tools"]) and all(not item.get("public_bundle_allowed", False) for item in catalog["tools"]) else "FAIL", "catalog_count": len(catalog["tools"])},
    }
    failed = [name for name, report in checks.items() if str(report.get("result", "FAIL")).upper() != "PASS"]
    return {
        "result": "PASS" if not failed else "FAIL",
        "version": VERSION,
        "failed": failed,
        "checks": checks,
        "evidence": "Built-in deterministic regression fixtures. External tool and Skyrim runtime evidence remain separate.",
    }
