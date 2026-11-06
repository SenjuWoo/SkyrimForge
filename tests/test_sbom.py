"""The SBOM must describe mixed licensing, not declare the GPL skills as MIT."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from scripts import validate_repository as validator

try:
    import jsonschema
except ImportError:  # the released runtime does not need it; tests and CI do
    jsonschema = None


class SbomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = validator.manifest()
        cls.sbom = validator.build_sbom(cls.manifest)
        cls.files = {entry["fileName"]: entry for entry in cls.sbom["files"]}
        cls.contains = {rel["relatedSpdxElement"] for rel in cls.sbom["relationships"]
                        if rel["relationshipType"] == "CONTAINS"}

    def test_document_and_packages_have_the_required_spdx_fields(self) -> None:
        self.assertEqual(self.sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(self.sbom["dataLicense"], "CC0-1.0")
        for key in ("SPDXID", "name", "documentNamespace", "creationInfo", "packages", "files", "relationships"):
            self.assertIn(key, self.sbom)
        self.assertRegex(self.sbom["creationInfo"]["created"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        for package in self.sbom["packages"]:
            for key in ("SPDXID", "name", "downloadLocation", "filesAnalyzed", "licenseConcluded",
                        "licenseDeclared", "copyrightText", "licenseInfoFromFiles", "packageVerificationCode"):
                self.assertIn(key, package)

    def test_licences_match_the_notices(self) -> None:
        licenses = {package["SPDXID"]: package["licenseDeclared"] for package in self.sbom["packages"]}
        self.assertEqual(licenses["SPDXRef-Package-Forge"], "MIT")
        self.assertEqual(licenses["SPDXRef-Package-HouseCARL-Skills"], "GPL-3.0-only")
        self.assertEqual(licenses["SPDXRef-Package-SPDX-Schema"], "CC-BY-3.0")
        gpl = [name for name in self.files if "/skills/housecarl/" in name]
        self.assertTrue(gpl)
        self.assertEqual(self.files[gpl[0]]["licenseConcluded"], "GPL-3.0-only")
        self.assertEqual(self.files["./skyrim_forge/vfs_sandbox.py"]["licenseConcluded"], "MIT")
        self.assertEqual(self.files["./references/spdx-2.3.schema.json"]["licenseConcluded"], "CC-BY-3.0")

    def test_every_file_is_contained_once_and_hashed(self) -> None:
        self.assertEqual(len(self.files), len(self.manifest["files"]))
        self.assertEqual(len(self.contains), len(self.files))
        hashes = {entry["fileName"]: entry["checksums"][0]["checksumValue"] for entry in self.sbom["files"]}
        for row in self.manifest["files"]:
            self.assertEqual(hashes["./" + row["path"]], row["sha256"])

    def test_sbom_validates_against_the_official_spdx_schema(self) -> None:
        if jsonschema is None:
            if os.environ.get("CI"):
                self.fail("jsonschema must be installed in CI to validate the SBOM")
            self.skipTest("install the test extra: pip install jsonschema")
        schema = json.loads((validator.ROOT / "references/spdx-2.3.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft7Validator.check_schema(schema)
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(self.sbom))
        self.assertEqual([error.message for error in errors], [])

    def test_namespace_is_unique_per_commit(self) -> None:
        self.assertIn(validator.VERSION, self.sbom["documentNamespace"])
        self.assertNotIn("example.invalid", self.sbom["documentNamespace"])


if __name__ == "__main__":
    unittest.main()
